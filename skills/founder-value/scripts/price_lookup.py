#!/usr/bin/env python3
"""Look up OCI list prices and stamp them into a founder value scenario.

Source: Oracle's public price list API (no authentication)
    https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/

These are public PAY_AS_YOU_GO list prices. They are not a quote and they do
not include your discounts, commitments, credits, taxes or support terms.
Every filled price records the part number, metric, the API's lastUpdated
value and the date it was checked, so a reader can tell how old it is.

Commands:
  python3 price_lookup.py search "E5 - OCPU" [--currency USD]
  python3 price_lookup.py part B97384 [--currency USD]
  python3 price_lookup.py fill scenario.json --out scenario.priced.json

`fill` prices every line that has a `part_number` (unless `price_locked` is
true) and the `input_part`, `cached_input_part` and `output_part` fields of
an option's `ai` block. AI parts must be priced per 1,000,000 tokens; any
other metric is refused rather than converted by guesswork.

Standard library only. Exit codes: 0 ok, 1 network or API error,
2 invalid input, 4 one or more parts could not be priced.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

API_URL = "https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/"
SOURCE = "Oracle public price list API (PAY_AS_YOU_GO list price)"
MODEL = "PAY_AS_YOU_GO"
OPEN_TOP = 999_999_999  # the API marks an unbounded top tier with rangeMax of 999999999 or more
TOKEN_METRIC = "1,000,000 Tokens"
AI_FIELDS = (("input_part", "input_per_mtok"),
             ("cached_input_part", "cached_input_per_mtok"),
             ("output_part", "output_per_mtok"))

Fetch = Callable[[str], "tuple[dict | None, str | None]"]


def parse_item(item: dict, currency: str) -> dict:
    """Normalise one API item to a flat price or a list of tiers."""
    loc = next((c for c in item.get("currencyCodeLocalizations", [])
                if c.get("currencyCode") == currency), None)
    if loc is None:
        raise LookupError(f"{item.get('partNumber')} has no {currency} price")
    part = item.get("partNumber")
    prices = [p for p in loc.get("prices", []) if isinstance(p, dict) and p.get("model") == MODEL]
    if not prices:
        raise LookupError(f"{part} has no {MODEL} price in {currency}")
    if any(not isinstance(p.get("value"), (int, float)) or isinstance(p.get("value"), bool) for p in prices):
        raise LookupError(f"{part} has a {MODEL} price without a numeric value")
    record = {"part_number": part, "display_name": item.get("displayName"),
              "metric": item.get("metricName"), "service_category": item.get("serviceCategory"),
              "currency": currency, "unit_price": None, "tiers": None}
    ranged = [p for p in prices if "rangeMin" in p or "rangeMax" in p]
    if not ranged and len(prices) == 1:
        record["unit_price"] = prices[0]["value"]
        return record
    if len(ranged) != len(prices):
        raise LookupError(f"{part} has several {MODEL} prices without ranges; price it by hand")
    record["tiers"] = _tiers(part, prices)
    return record


def _tiers(part: str | None, prices: list[dict]) -> list[dict]:
    """Convert API ranges to contiguous tiers that start at 0; refuse any other shape."""
    ordered = sorted(prices, key=lambda x: x.get("rangeMin") or 0)
    tiers, expected_from = [], 0
    for i, p in enumerate(ordered):
        start, top = p.get("rangeMin") or 0, p.get("rangeMax")
        if start != expected_from:
            raise LookupError(f"{part} has tiers with a gap or overlap at {start}; price it by hand")
        open_top = top is None or top >= OPEN_TOP
        if open_top and i != len(ordered) - 1:
            raise LookupError(f"{part} has an unbounded tier before its last tier; price it by hand")
        tiers.append({"from": start, "to": None if open_top else top, "price": p["value"]})
        expected_from = top
    return tiers


def fetch_part(part_number: str, currency: str = "USD", timeout: float = 60) -> tuple[dict | None, str | None]:
    """Fetch one part from the live API. Returns (item or None, lastUpdated)."""
    query = urllib.parse.urlencode({"partNumber": part_number, "currencyCode": currency})
    data = _get_json(f"{API_URL}?{query}", timeout)
    items = data.get("items") or []
    match = next((i for i in items if i.get("partNumber") == part_number), None)
    return match, data.get("lastUpdated")


def fetch_all(currency: str = "USD", timeout: float = 120) -> tuple[list[dict], str | None]:
    """Fetch the whole price list for one currency."""
    data = _get_json(f"{API_URL}?{urllib.parse.urlencode({'currencyCode': currency})}", timeout)
    return data.get("items") or [], data.get("lastUpdated")


def _get_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "founder-value-kit/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode("utf-8"))


def search(items: list[dict], query: str, currency: str) -> list[dict]:
    """Case-insensitive display-name search, skipping items without the currency."""
    needle = query.lower()
    rows = []
    for item in items:
        if needle in (item.get("displayName") or "").lower():
            try:
                rows.append(parse_item(item, currency))
            except LookupError:
                continue
    return rows


def _provenance(record: dict, last_updated: str | None, today: str) -> dict:
    return {"source": SOURCE, "part_number": record["part_number"], "metric": record["metric"],
            "price_list_updated": last_updated, "checked_at": today}


def _fill_line(line: dict, currency: str, fetch: Fetch, today: str, where: str) -> tuple[dict, dict]:
    if line.get("price_locked"):
        return line, {"where": where, "status": "kept", "detail": "price_locked"}
    if line.get("amount") is not None:
        return line, {"where": where, "status": "refused",
                      "detail": "line has an amount; remove it to price by part number"}
    item, last_updated = fetch(line["part_number"])
    if item is None:
        return line, {"where": where, "status": "not_found", "detail": line["part_number"]}
    try:
        record = parse_item(item, currency)
    except LookupError as exc:
        return line, {"where": where, "status": "refused", "detail": str(exc)}
    expected = line.get("expected_metric")
    if expected and expected.lower() not in (record["metric"] or "").lower():
        return line, {"where": where, "status": "refused",
                      "detail": f"metric '{record['metric']}' does not match '{expected}'"}
    filled = {k: v for k, v in line.items() if k not in ("unit_price", "tiers")}
    if record["tiers"]:
        filled["tiers"] = record["tiers"]
    else:
        filled["unit_price"] = record["unit_price"]
    filled["price_source"] = _provenance(record, last_updated, today)
    filled["evidence"] = "sourced"
    return filled, {"where": where, "status": "filled",
                    "detail": f"{record['part_number']} {record['display_name']} per {record['metric']}"}


def _fill_ai(ai: dict, currency: str, fetch: Fetch, today: str, where: str) -> tuple[dict, list[dict]]:
    filled, report, sources = dict(ai), [], []
    for part_key, price_key in AI_FIELDS:
        part = ai.get(part_key)
        if not part:
            continue
        item, last_updated = fetch(part)
        if item is None:
            report.append({"where": f"{where}.{part_key}", "status": "not_found", "detail": part})
            continue
        try:
            record = parse_item(item, currency)
        except LookupError as exc:
            report.append({"where": f"{where}.{part_key}", "status": "refused", "detail": str(exc)})
            continue
        if record["metric"] != TOKEN_METRIC or record["unit_price"] is None:
            report.append({"where": f"{where}.{part_key}", "status": "refused",
                           "detail": f"{part} is priced per '{record['metric']}', not per {TOKEN_METRIC}"})
            filled.pop(price_key, None)
            continue
        filled[price_key] = record["unit_price"]
        sources.append(_provenance(record, last_updated, today))
        report.append({"where": f"{where}.{part_key}", "status": "filled",
                       "detail": f"{part} {record['display_name']}"})
    if sources:
        filled["price_source"] = {"source": SOURCE, "parts": sources, "checked_at": today,
                                  "price_list_updated": sources[0]["price_list_updated"]}
    return filled, report


def fill_scenario(scenario: dict, fetch: Fetch, today: str | None = None) -> tuple[dict, list[dict]]:
    """Return a priced copy of the scenario and a per-field report."""
    today = today or dt.date.today().isoformat()
    if not isinstance(scenario, dict) or not isinstance(scenario.get("options", {}), dict):
        raise ValueError("scenario must be an object whose options are an object")
    s = copy.deepcopy(scenario)
    currency = s.get("currency", "USD")
    report: list[dict] = []
    for key, option in (s.get("options") or {}).items():
        if not isinstance(option, dict):
            report.append({"where": f"options.{key}", "status": "refused", "detail": "option is not an object"})
            continue
        lines_given = isinstance(option.get("lines"), list)
        new_lines = []
        for line in option["lines"] if lines_given else []:
            if not isinstance(line, dict) or not line.get("part_number"):
                new_lines.append(line)
                continue
            filled, entry = _fill_line(line, currency, fetch, today, f"options.{key}.lines.{line.get('id')}")
            new_lines.append(filled)
            report.append(entry)
        if lines_given:
            option["lines"] = new_lines
        if isinstance(option.get("ai"), dict):
            option["ai"], ai_report = _fill_ai(option["ai"], currency, fetch, today, f"options.{key}.ai")
            report.extend(ai_report)
    return s, report


def _format_record(r: dict) -> str:
    if r["tiers"]:
        tiers = "; ".join(f"{t['from']:g}-{'up' if t['to'] is None else format(t['to'], 'g')}: {t['price']:g}"
                          for t in r["tiers"])
        price = f"tiers [{tiers}]"
    else:
        price = f"{r['unit_price']:g}"
    return f"{r['part_number']}\t{r['currency']} {price}\tper {r['metric']}\t{r['display_name']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCI list price lookup for founder value scenarios.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_search = sub.add_parser("search", help="search display names")
    p_search.add_argument("query")
    p_part = sub.add_parser("part", help="show one part number")
    p_part.add_argument("part_number")
    p_fill = sub.add_parser("fill", help="price a scenario's part numbers")
    p_fill.add_argument("scenario", type=Path)
    p_fill.add_argument("--out", type=Path, required=True)
    for p in (p_search, p_part, p_fill):
        p.add_argument("--currency", default=None, help="currency code (default USD, or the scenario's)")
        p.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"price_lookup: price list API unavailable ({exc}). "
                         "Keep affected lines unpriced; do not substitute remembered prices.\n")
        return 1


def _run(args: argparse.Namespace) -> int:
    if args.command == "search":
        currency = args.currency or "USD"
        items, last_updated = fetch_all(currency, max(args.timeout, 120))
        rows = search(items, args.query, currency)
        sys.stdout.write(f"# price list lastUpdated {last_updated}; {len(rows)} match(es)\n")
        sys.stdout.writelines(_format_record(r) + "\n" for r in rows)
        return 0 if rows else 4
    if args.command == "part":
        currency = args.currency or "USD"
        item, last_updated = fetch_part(args.part_number, currency, args.timeout)
        if item is None:
            sys.stderr.write(f"price_lookup: {args.part_number} not found\n")
            return 4
        sys.stdout.write(f"# price list lastUpdated {last_updated}\n{_format_record(parse_item(item, currency))}\n")
        return 0
    try:
        scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"price_lookup: cannot read scenario: {exc}\n")
        return 2
    if not isinstance(scenario, dict):
        sys.stderr.write("price_lookup: scenario must be a JSON object\n")
        return 2
    currency = args.currency or scenario.get("currency", "USD")
    cache: dict[str, tuple[Any, Any]] = {}

    def fetch(part: str) -> tuple[dict | None, str | None]:
        if part not in cache:
            cache[part] = fetch_part(part, currency, args.timeout)
        return cache[part]

    try:
        filled, report = fill_scenario(scenario, fetch)
    except ValueError as exc:
        sys.stderr.write(f"price_lookup: {exc}\n")
        return 2
    args.out.write_text(json.dumps(filled, indent=2) + "\n", encoding="utf-8")
    for entry in report:
        sys.stdout.write(f"{entry['status']:<9} {entry['where']}: {entry['detail']}\n")
    return 4 if any(e["status"] in ("not_found", "refused") for e in report) else 0


if __name__ == "__main__":
    sys.exit(main())
