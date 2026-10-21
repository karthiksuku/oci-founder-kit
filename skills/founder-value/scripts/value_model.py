#!/usr/bin/env python3
"""Founder value model: cloud cost, gross margin, runway and payback by option.

Reads a `founder-value-scenario/1` JSON file and compares each option (for
example, the current cloud and OCI) month by month over a fixed horizon.

What it reports for every option:
  - cloud bill at list price and in cash after credits
  - durable gross margin (list price) and cash gross margin (after credits)
  - credit usage, expiry and the "credit cliff" month
  - runway in fully funded months
  - AI cost per action when an `ai_usage` profile is present
  - the largest cost drivers and every line that has no price

What it reports for every non-baseline option against the baseline:
  - payback month, with and without credits
  - cumulative cash difference over the horizon
  - durable monthly saving at the end of the horizon

Rules that the model will not bend:
  - An unpriced line is unknown, never zero. Totals exclude it and the
    result is marked INCOMPLETE.
  - Credits are cash relief, not margin. Durable margin ignores them.
  - Output is deterministic: no clock reads, no network.

Standard library only. Exit codes: 0 ok, 2 invalid input, 3 incomplete
result with --strict.

Usage:
  python3 value_model.py scenario.json [--format md|json] [--out FILE] [--strict]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "founder-value-scenario/1"
EVIDENCE = ("measured", "stated", "sourced", "assumed")
REPORT_MONTHS = (1, 3, 6, 12, 13, 18, 24, 36)
TOP_DRIVERS = 3


class ScenarioError(ValueError):
    """Raised when a scenario cannot be simulated."""


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_non_negative(obj: dict, keys: tuple, where: str, errors: list) -> None:
    for key in keys:
        if key in obj and obj[key] is not None:
            if not _num(obj[key]) or obj[key] < 0:
                errors.append(f"{where}.{key} must be a non-negative number")


def _validate_tiers(tiers: Any, where: str, errors: list) -> None:
    """Tiers must be a list of {from, to, price} that starts at 0 with no gaps or overlaps."""
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"{where}.tiers must be a non-empty list")
        return
    for i, tier in enumerate(tiers):
        if (not isinstance(tier, dict) or not _num(tier.get("from")) or not _num(tier.get("price"))
                or not (tier.get("to") is None or _num(tier.get("to")))):
            errors.append(f"{where}.tiers[{i}] needs numeric from and price, and a numeric or null to")
            return
    ordered = sorted(tiers, key=lambda t: t["from"])
    if ordered[0]["from"] != 0:
        errors.append(f"{where}.tiers must start at 0")
    for prev, tier in zip(ordered, ordered[1:]):
        if prev.get("to") is None or tier["from"] != prev["to"]:
            errors.append(f"{where}.tiers must be contiguous: each tier starts where the previous one ends")
            return
    for tier in ordered:
        if tier.get("to") is not None and tier["to"] <= tier["from"]:
            errors.append(f"{where}.tiers has a tier whose to is not above its from")
            return


def _validate_line(line: Any, where: str, errors: list) -> None:
    if not isinstance(line, dict):
        errors.append(f"{where} must be an object")
        return
    if not isinstance(line.get("id"), str) or not line["id"]:
        errors.append(f"{where}.id must be a non-empty string")
    if line.get("basis", "fixed") not in ("fixed", "per_customer"):
        errors.append(f"{where}.basis must be 'fixed' or 'per_customer'")
    has_amount = line.get("amount") is not None
    has_qty = line.get("quantity") is not None
    if has_amount and has_qty:
        errors.append(f"{where} sets both amount and quantity; use one")
    if not has_amount and not has_qty:
        errors.append(f"{where} needs amount or quantity")
    if has_amount and (line.get("unit_price") is not None or line.get("tiers")):
        errors.append(f"{where} sets amount together with a price; use one")
    _check_non_negative(line, ("amount", "quantity", "hours_per_month", "unit_price"), where, errors)
    if line.get("tiers") is not None:
        _validate_tiers(line["tiers"], where, errors)
    if line.get("evidence") is not None and line["evidence"] not in EVIDENCE:
        errors.append(f"{where}.evidence must be one of {', '.join(EVIDENCE)}")
    if line.get("group") is not None and (not isinstance(line["group"], str) or line["group"] == "ai"):
        errors.append(f"{where}.group must be a name other than 'ai'")


def _validate_option(key: str, option: Any, is_baseline: bool, errors: list) -> None:
    where = f"options.{key}"
    if not isinstance(option, dict):
        errors.append(f"{where} must be an object")
        return
    lines = option.get("lines")
    if not isinstance(lines, list):
        errors.append(f"{where}.lines must be a list")
        lines = []
    ids = [line["id"] for line in lines if isinstance(line, dict) and isinstance(line.get("id"), str)]
    if len(ids) != len(set(ids)):
        errors.append(f"{where}.lines has duplicate ids")
    if "ai" in ids:
        errors.append(f"{where}.lines must not use the reserved id 'ai'")
    for i, line in enumerate(lines):
        _validate_line(line, f"{where}.lines[{i}]", errors)
    for block in ("credits", "migration", "ai"):
        if option.get(block) is not None and not isinstance(option[block], dict):
            errors.append(f"{where}.{block} must be an object")
            return
    credits = option.get("credits")
    if credits is not None:
        if not _num(credits.get("amount")) or credits["amount"] < 0:
            errors.append(f"{where}.credits.amount must be a non-negative number")
        for k in ("start_month", "valid_months"):
            if not isinstance(credits.get(k), int) or isinstance(credits.get(k), bool) or credits[k] < 1:
                errors.append(f"{where}.credits.{k} must be a positive integer")
    migration = option.get("migration")
    if migration is not None:
        if is_baseline:
            errors.append(f"{where}.migration is not allowed on the baseline option")
        _check_non_negative(migration, ("one_time_cost",), f"{where}.migration", errors)
        if not isinstance(migration.get("start_month", 1), int) or migration.get("start_month", 1) < 1:
            errors.append(f"{where}.migration.start_month must be a positive integer")
        if not isinstance(migration.get("dual_run_months", 0), int) or migration.get("dual_run_months", 0) < 0:
            errors.append(f"{where}.migration.dual_run_months must be a non-negative integer")
    ai = option.get("ai")
    if ai is not None:
        _check_non_negative(ai, ("input_per_mtok", "cached_input_per_mtok", "output_per_mtok"),
                            f"{where}.ai", errors)


def validate_scenario(s: Any) -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    errors: list[str] = []
    if not isinstance(s, dict):
        return ["scenario must be a JSON object"]
    if s.get("schema") != SCHEMA:
        errors.append(f"schema must be '{SCHEMA}'")
    if not isinstance(s.get("currency"), str) or len(s.get("currency", "")) != 3:
        errors.append("currency must be a three-letter code such as USD")
    horizon = s.get("horizon_months")
    if not isinstance(horizon, int) or not 1 <= horizon <= 120:
        errors.append("horizon_months must be an integer from 1 to 120")
    business = s.get("business")
    if not isinstance(business, dict):
        errors.append("business must be an object")
    else:
        for key in ("customers_start", "arpa_monthly", "opex_monthly", "cash_on_hand"):
            if not _num(business.get(key)):
                errors.append(f"business.{key} is required")
        _check_non_negative(business, ("customers_start", "customer_growth_monthly", "arpa_monthly",
                                       "other_cogs_per_customer_monthly", "opex_monthly",
                                       "cash_on_hand"), "business", errors)
    options = s.get("options")
    if not isinstance(options, dict) or len(options) < 2:
        errors.append("options must contain at least two options")
        return errors
    baseline = s.get("baseline", "current")
    if not isinstance(baseline, str) or baseline not in options:
        errors.append(f"baseline {baseline!r} is not one of the options")
    for key, option in options.items():
        _validate_option(key, option, key == baseline, errors)
    usage = s.get("ai_usage")
    if usage is not None and not isinstance(usage, dict):
        errors.append("ai_usage must be an object")
    elif usage is not None:
        _check_non_negative(usage, ("actions_per_customer_monthly", "input_tokens_per_action",
                                    "output_tokens_per_action"), "ai_usage", errors)
        share = usage.get("cached_input_share", 0)
        if not _num(share) or not 0 <= share <= 1:
            errors.append("ai_usage.cached_input_share must be between 0 and 1")
    return errors


# --------------------------------------------------------------------------
# Unit costs
# --------------------------------------------------------------------------

def tiered_cost(quantity: float, tiers: list[dict]) -> float:
    """Price a monthly quantity against ordered tiers of {from, to, price}."""
    total = 0.0
    for tier in sorted(tiers, key=lambda t: t["from"]):
        upper = tier.get("to")
        top = quantity if upper is None else min(quantity, upper)
        span = top - tier["from"]
        if span > 0:
            total += span * tier["price"]
    return total


def line_monthly_cost(line: dict, customers: float) -> tuple[float | None, float]:
    """Return (cost or None when unpriced, billed quantity) for one month."""
    scale = customers if line.get("basis") == "per_customer" else 1.0
    if line.get("amount") is not None:
        return line["amount"] * scale, scale
    quantity = line["quantity"] * line.get("hours_per_month", 1) * scale
    if line.get("tiers"):
        return tiered_cost(quantity, line["tiers"]), quantity
    if line.get("unit_price") is None:
        return None, quantity
    return quantity * line["unit_price"], quantity


def ai_cost_per_action(usage: dict, prices: dict) -> float | None:
    """Model cost of one AI action, or None when a needed price is missing."""
    p_in, p_out = prices.get("input_per_mtok"), prices.get("output_per_mtok")
    if p_in is None or p_out is None:
        return None
    p_cached = prices.get("cached_input_per_mtok")
    p_cached = p_in if p_cached is None else p_cached
    tokens_in = usage.get("input_tokens_per_action", 0)
    share = usage.get("cached_input_share", 0)
    tokens_out = usage.get("output_tokens_per_action", 0)
    cost = tokens_in * (1 - share) * p_in + tokens_in * share * p_cached + tokens_out * p_out
    return cost / 1_000_000


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------

def _customers(business: dict, month: int) -> float:
    growth = business.get("customer_growth_monthly", 0) or 0
    return business["customers_start"] * (1 + growth) ** (month - 1)


def _option_bill(option: dict, usage: dict | None, customers: float) -> dict:
    """List-price bill for one month, split by line, plus unpriced line ids."""
    by_line: dict[str, float] = {}
    unpriced: list[str] = []
    for line in option["lines"]:
        cost, _ = line_monthly_cost(line, customers)
        if cost is None:
            unpriced.append(line["id"])
        else:
            by_line[line["id"]] = cost
    ai_cost = 0.0
    per_action = None
    ai = option.get("ai") or {}
    if usage and not ai.get("included_in_lines"):
        per_action = ai_cost_per_action(usage, ai)
        if per_action is None:
            unpriced.append("ai")
        else:
            ai_cost = per_action * usage.get("actions_per_customer_monthly", 0) * customers
            by_line["ai"] = ai_cost
    return {"by_line": by_line, "unpriced": unpriced, "ai_cost": ai_cost,
            "ai_per_action": per_action, "total": sum(by_line.values())}


def _credit_window(credits: dict | None, month: int) -> bool:
    if not credits:
        return False
    start = credits["start_month"]
    return start <= month < start + credits["valid_months"]


def _simulate_baseline(s: dict, use_credits: bool = True) -> tuple[dict, list[float]]:
    """Simulate the baseline first; dual running pays its cash bill, after its own credits."""
    zeros = [0.0] * s["horizon_months"]
    base = _simulate_option(s, s.get("baseline", "current"), zeros, use_credits=use_credits)
    return base, [row["cloud_cash"] for row in base["months"]]


def _simulate_option(s: dict, key: str, baseline_cash: list[float], use_credits: bool = True) -> dict:
    business, usage = s["business"], s.get("ai_usage")
    option = s["options"][key]
    credits = option.get("credits") if use_credits else None
    migration = option.get("migration") or {}
    remaining = credits["amount"] if credits else 0.0
    applied_total = expired = 0.0
    cash = business["cash_on_hand"]
    months, line_totals, unpriced = [], {}, set()
    for m in range(1, s["horizon_months"] + 1):
        customers = _customers(business, m)
        bill = _option_bill(option, usage, customers)
        unpriced.update(bill["unpriced"])
        for line_id, cost in bill["by_line"].items():
            line_totals[line_id] = line_totals.get(line_id, 0.0) + cost
        in_window = _credit_window(credits, m)
        if credits and not in_window and remaining > 0 and m >= credits["start_month"]:
            expired, remaining = expired + remaining, 0.0
        available_at_start = in_window and remaining > 0
        applied = min(remaining, bill["total"]) if in_window else 0.0
        remaining -= applied
        applied_total += applied
        migration_cash = _migration_cash(migration, baseline_cash, m)
        revenue = customers * business["arpa_monthly"]
        other_cogs = customers * (business.get("other_cogs_per_customer_monthly") or 0)
        cloud_cash = bill["total"] - applied
        burn = business["opex_monthly"] + cloud_cash + other_cogs + migration_cash - revenue
        cash -= burn
        months.append({
            "month": m, "customers": customers, "revenue": revenue,
            "cloud_list": bill["total"], "ai_cost": bill["ai_cost"],
            "credits_applied": applied, "cloud_cash": cloud_cash,
            "migration_cash": migration_cash, "other_cogs": other_cogs,
            "gross_margin_durable": _margin(revenue, bill["total"] + other_cogs),
            "gross_margin_cash": _margin(revenue, cloud_cash + other_cogs),
            "net_burn": burn, "cash_end": cash,
            "credit_available": available_at_start,
        })
    started = credits and credits["start_month"] <= s["horizon_months"]
    if started and remaining > 0 and not _credit_window(credits, s["horizon_months"] + 1):
        expired, remaining = expired + remaining, 0.0
    summary = _summarise(option, months, line_totals, sorted(unpriced), credits,
                         applied_total, expired, usage)
    groups = {line["id"]: line.get("group", "other") for line in option["lines"]}
    summary["group_costs_last"] = _group_costs(bill["by_line"], groups)
    return {"label": option.get("label", key), "months": months, "summary": summary}


def _group_costs(by_line: dict[str, float], groups: dict[str, str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for line_id, cost in by_line.items():
        group = "ai" if line_id == "ai" else groups.get(line_id, "other")
        totals[group] = totals.get(group, 0.0) + cost
    return totals


def _margin_bridge(base: dict, option: dict) -> list[dict]:
    """Durable margin change at the horizon, split by cost group, in points."""
    revenue = option["months"][-1]["revenue"]
    if revenue <= 0:
        return []
    b, o = base["summary"]["group_costs_last"], option["summary"]["group_costs_last"]
    steps = [{"group": g, "points": (b.get(g, 0.0) - o.get(g, 0.0)) / revenue * 100}
             for g in sorted(set(b) | set(o))]
    return sorted(steps, key=lambda step: abs(step["points"]), reverse=True)


def _migration_cash(migration: dict, baseline_cash: list[float], month: int) -> float:
    if not migration:
        return 0.0
    start = migration.get("start_month", 1)
    cost = migration.get("one_time_cost", 0) if month == start else 0.0
    if start <= month < start + migration.get("dual_run_months", 0):
        cost += baseline_cash[month - 1]
    return cost


def _margin(revenue: float, cogs: float) -> float | None:
    return None if revenue <= 0 else (revenue - cogs) / revenue


def _summarise(option, months, line_totals, unpriced, credits, applied, expired, usage) -> dict:
    last = months[-1]
    drivers = sorted(line_totals.items(), key=lambda kv: kv[1], reverse=True)[:TOP_DRIVERS]
    runway = next((row["month"] - 1 for row in months if row["cash_end"] < 0), None)
    summary = {
        "unpriced": unpriced,
        "cloud_list_first": months[0]["cloud_list"],
        "cloud_list_last": last["cloud_list"],
        "cloud_cash_first": months[0]["cloud_cash"],
        "cloud_cash_last": last["cloud_cash"],
        "cloud_list_per_customer_last": (last["cloud_list"] / last["customers"]
                                         if last["customers"] else None),
        "gross_margin_durable_last": last["gross_margin_durable"],
        "gross_margin_cash_last": last["gross_margin_cash"],
        "runway_months": runway,
        "cash_end": last["cash_end"],
        "top_drivers": [{"id": k, "horizon_cost": v} for k, v in drivers],
        "ai_cost_per_action": None,
        "credits": None,
    }
    if usage and not (option.get("ai") or {}).get("included_in_lines"):
        summary["ai_cost_per_action"] = ai_cost_per_action(usage, option.get("ai") or {})
    if credits:
        summary["credits"] = _credit_summary(credits, months, applied, expired)
    return summary


def _credit_summary(credits: dict, months: list[dict], applied: float, expired: float) -> dict:
    start = credits["start_month"]
    cliff = next((row["month"] for row in months
                  if row["month"] > start and not row["credit_available"]
                  and months[row["month"] - 2]["credit_available"]), None)
    before = after = None
    if cliff is not None:
        before = months[cliff - 2]["cloud_cash"]
        after = months[cliff - 1]["cloud_cash"]
    return {"granted": credits["amount"], "applied": applied, "expired": expired,
            "start_month": start, "valid_months": credits["valid_months"],
            "cliff_month": cliff, "cloud_cash_before_cliff": before,
            "cloud_cash_after_cliff": after}


def _payback(baseline: dict, option: dict) -> tuple[int | None, float]:
    cumulative = 0.0
    payback = None
    for b, o in zip(baseline["months"], option["months"]):
        cumulative += (b["cloud_cash"] + b["migration_cash"]) - (o["cloud_cash"] + o["migration_cash"])
        if payback is None and cumulative >= 0:
            payback = b["month"]
        elif cumulative < 0:
            payback = None
    return payback, cumulative


def _points(option_row: dict, base_row: dict) -> float | None:
    a, b = option_row["gross_margin_durable"], base_row["gross_margin_durable"]
    return None if a is None or b is None else (a - b) * 100


def _compare(s: dict, results: dict) -> dict:
    base_key = s.get("baseline", "current")
    base = results[base_key]
    base_nc, base_nc_cash = _simulate_baseline(s, use_credits=False)
    comparisons = {}
    for key, result in results.items():
        if key == base_key:
            continue
        payback, cumulative = _payback(base, result)
        no_credit = _simulate_option(s, key, base_nc_cash, use_credits=False)
        payback_nc, cumulative_nc = _payback(base_nc, no_credit)
        burns = [row["net_burn"] for row in base["months"] if row["net_burn"] > 0]
        avg_burn = sum(burns) / len(burns) if burns else None
        comparisons[key] = {
            "against": base_key,
            "durable_gross_margin_delta_points_first": _points(result["months"][0], base["months"][0]),
            "durable_gross_margin_delta_points_last": _points(result["months"][-1], base["months"][-1]),
            "margin_bridge": _margin_bridge(base, result),
            "runway_equivalent_months": cumulative / avg_burn if avg_burn else None,
            "payback_month": payback,
            "payback_month_without_credits": payback_nc,
            "cumulative_cash_saving": cumulative,
            "cumulative_cash_saving_without_credits": cumulative_nc,
            "durable_monthly_saving_at_horizon": (base["summary"]["cloud_list_last"]
                                                  - result["summary"]["cloud_list_last"]),
            "runway_months": {"baseline": base["summary"]["runway_months"],
                              "option": result["summary"]["runway_months"]},
        }
    return comparisons


def simulate(scenario: dict) -> dict:
    """Simulate every option and compare non-baseline options to the baseline."""
    errors = validate_scenario(scenario)
    if errors:
        raise ScenarioError("; ".join(errors))
    s = copy.deepcopy(scenario)
    base_key = s.get("baseline", "current")
    base, baseline_cash = _simulate_baseline(s)
    results = {key: base if key == base_key else _simulate_option(s, key, baseline_cash)
               for key in s["options"]}
    incomplete = any(r["summary"]["unpriced"] for r in results.values())
    evidence: dict[str, int] = {}
    assumed: list[str] = []
    for key, option in s["options"].items():
        for line in option["lines"]:
            cls = line.get("evidence", "assumed")
            evidence[cls] = evidence.get(cls, 0) + 1
            if cls == "assumed":
                assumed.append(f"{key}.{line['id']}")
    return {
        "schema": SCHEMA,
        "name": s.get("name", ""),
        "as_of": s.get("as_of"),
        "currency": s["currency"],
        "horizon_months": s["horizon_months"],
        "baseline": s.get("baseline", "current"),
        "status": "INCOMPLETE" if incomplete else "COMPLETE",
        "evidence": evidence,
        "assumed_lines": assumed,
        "notes": s.get("notes", []),
        "options": results,
        "comparisons": _compare(s, results),
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _money(value: float | None, cur: str) -> str:
    return "unknown" if value is None else f"{cur} {value:,.0f}"


def _unit_money(value: float | None, cur: str) -> str:
    return "unknown" if value is None else f"{cur} {value:.5f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _signed(value: float) -> str:
    return "0.0" if abs(value) < 0.05 else f"{value:+.1f}"


def _signed_points(value: float | None) -> str:
    return "n/a" if value is None else f"{_signed(value)} points"


def _months(value: int | None, horizon: int) -> str:
    return f"beyond {horizon} months" if value is None else f"{value} months"


def _render_headline(r: dict, key: str, cmp: dict) -> list[str]:
    cur, h = r["currency"], r["horizon_months"]
    base, opt = r["options"][cmp["against"]], r["options"][key]
    bs, os_ = base["summary"], opt["summary"]
    first_b, first_o = base["months"][0], opt["months"][0]
    rows = [
        ("Cloud bill at list, month 1", _money(bs["cloud_list_first"], cur), _money(os_["cloud_list_first"], cur)),
        ("Durable gross margin, month 1", _pct(first_b["gross_margin_durable"]),
         _pct(first_o["gross_margin_durable"])),
        ("Cash gross margin, month 1", _pct(first_b["gross_margin_cash"]), _pct(first_o["gross_margin_cash"])),
        (f"Cloud bill at list, month {h}", _money(bs["cloud_list_last"], cur), _money(os_["cloud_list_last"], cur)),
        (f"Cloud cost per customer, month {h}", _money(bs["cloud_list_per_customer_last"], cur),
         _money(os_["cloud_list_per_customer_last"], cur)),
        (f"Durable gross margin, month {h}", _pct(bs["gross_margin_durable_last"]),
         _pct(os_["gross_margin_durable_last"])),
        (f"Cash gross margin, month {h}", _pct(bs["gross_margin_cash_last"]), _pct(os_["gross_margin_cash_last"])),
        ("Runway", _months(bs["runway_months"], h), _months(os_["runway_months"], h)),
        (f"Cash at month {h}", _money(bs["cash_end"], cur), _money(os_["cash_end"], cur)),
    ]
    if bs["ai_cost_per_action"] is not None or os_["ai_cost_per_action"] is not None:
        rows.append(("AI cost per action", _unit_money(bs["ai_cost_per_action"], cur),
                     _unit_money(os_["ai_cost_per_action"], cur)))
    out = [f"## {opt['label']} compared with {base['label']}", "",
           f"| Measure | {base['label']} | {opt['label']} |", "|---|---:|---:|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    pay = cmp["payback_month"]
    pay_nc = cmp["payback_month_without_credits"]
    gm_first, gm_last = (cmp["durable_gross_margin_delta_points_first"],
                         cmp["durable_gross_margin_delta_points_last"])
    runway_eq = cmp["runway_equivalent_months"]
    out += ["",
            f"- Durable gross margin change: {_signed_points(gm_first)} in month 1, "
            f"{_signed_points(gm_last)} in month {h}.",
            "- Cash kept over the horizon is worth "
            + ("n/a (the baseline does not burn cash)" if runway_eq is None
               else f"{runway_eq:.1f} months of the baseline's average net burn")
            + ".",
            f"- Payback: {'not within ' + str(h) + ' months' if pay is None else 'month ' + str(pay)}"
            f" with credits; {'not within ' + str(h) + ' months' if pay_nc is None else 'month ' + str(pay_nc)}"
            " without credits.",
            f"- Cumulative cash difference over {h} months: {_money(cmp['cumulative_cash_saving'], cur)}"
            f" ({_money(cmp['cumulative_cash_saving_without_credits'], cur)} without credits)."
            " Positive means the option keeps more cash.",
            f"- Durable monthly saving at month {h}: {_money(cmp['durable_monthly_saving_at_horizon'], cur)}"
            " at list price. Negative means the option costs more once credits are gone."]
    if cmp["margin_bridge"]:
        out += ["", f"Durable gross margin bridge, month {h} (points, positive favours {opt['label']}):", "",
                "| Cost group | Points |", "|---|---:|"]
        out += [f"| {step['group']} | {_signed(step['points'])} |" for step in cmp["margin_bridge"]]
    return out


def _render_credits(r: dict) -> list[str]:
    cur = r["currency"]
    out = []
    for key, opt in r["options"].items():
        c = opt["summary"]["credits"]
        if not c:
            continue
        line = (f"- **{opt['label']}:** {_money(c['granted'], cur)} granted, {_money(c['applied'], cur)} used, "
                f"{_money(c['expired'], cur)} expired unused.")
        if c["cliff_month"] is not None:
            line += (f" Credit cliff in month {c['cliff_month']}: cash cloud cost goes from "
                     f"{_money(c['cloud_cash_before_cliff'], cur)} to {_money(c['cloud_cash_after_cliff'], cur)}"
                     " a month.")
        else:
            line += " No credit cliff inside the horizon."
        out.append(line)
    return (["## Credits and the credit cliff", ""] + out + [""]) if out else []


def _render_months(r: dict) -> list[str]:
    cur, h = r["currency"], r["horizon_months"]
    picks = [m for m in REPORT_MONTHS if m <= h] + ([h] if h not in REPORT_MONTHS else [])
    out = ["## Selected months", ""]
    for opt in r["options"].values():
        out += [f"**{opt['label']}**", "",
                "| Month | Customers | Revenue | Cloud at list | Credits used | Cloud cash | Durable GM | Cash end |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for m in picks:
            row = opt["months"][m - 1]
            out.append(f"| {m} | {row['customers']:,.0f} | {_money(row['revenue'], cur)} | "
                       f"{_money(row['cloud_list'], cur)} | {_money(row['credits_applied'], cur)} | "
                       f"{_money(row['cloud_cash'], cur)} | {_pct(row['gross_margin_durable'])} | "
                       f"{_money(row['cash_end'], cur)} |")
        out.append("")
    return out


def _render_drivers(r: dict) -> list[str]:
    cur, h = r["currency"], r["horizon_months"]
    out = [f"## Largest cost drivers over {h} months", ""]
    for opt in r["options"].values():
        items = ", ".join(f"`{d['id']}` {_money(d['horizon_cost'], cur)}" for d in opt["summary"]["top_drivers"])
        out.append(f"- **{opt['label']}:** {items or 'none priced'}")
    return out + [""]


def render_markdown(r: dict) -> str:
    """Render a simulation result as a decision-ready Markdown report."""
    out = [f"# Founder value model: {r['name'] or 'scenario'}", ""]
    meta = f"Currency {r['currency']}, horizon {r['horizon_months']} months"
    if r.get("as_of"):
        meta += f", inputs as of {r['as_of']}"
    out += [meta + ".", ""]
    if r["status"] == "INCOMPLETE":
        out += ["> **INCOMPLETE.** Some lines have no price, so totals leave them out. "
                "Do not present these numbers as a full estimate.", ""]
        for opt in r["options"].values():
            if opt["summary"]["unpriced"]:
                out.append(f"> - {opt['label']}: " + ", ".join(f"`{u}`" for u in opt["summary"]["unpriced"]))
        out.append("")
    for key, cmp in r["comparisons"].items():
        out += _render_headline(r, key, cmp) + [""]
    out += _render_credits(r)
    out += _render_drivers(r)
    out += _render_months(r)
    ev = ", ".join(f"{k} {v}" for k, v in sorted(r["evidence"].items()))
    out += ["## Evidence behind the inputs", "", f"Cost lines by evidence class: {ev}.", ""]
    if r["assumed_lines"]:
        out += ["Confirm these assumed lines before using the result in a decision: "
                + ", ".join(f"`{a}`" for a in r["assumed_lines"]) + ".", ""]
    for note in r.get("notes") or []:
        out.append(f"- {note}")
    out += ["", "Method: list-price bills per month, credits applied to the bill until spent or expired, "
            "migration and dual running charged as cash, runway counted in fully funded months. "
            "Durable margin ignores credits. This is a planning model, not a quote or financial advice."]
    return "\n".join(out).rstrip() + "\n"


def _round(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare cloud options on margin, runway and payback.")
    parser.add_argument("scenario", type=Path, help="founder-value-scenario/1 JSON file")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--out", type=Path, help="write the report here instead of stdout")
    parser.add_argument("--strict", action="store_true", help="exit 3 when any line is unpriced")
    args = parser.parse_args(argv)
    try:
        scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
        result = simulate(scenario)
    except (OSError, json.JSONDecodeError, ScenarioError) as exc:
        sys.stderr.write(f"value_model: {exc}\n")
        return 2
    text = (json.dumps(_round(result), indent=2) + "\n" if args.format == "json"
            else render_markdown(result))
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.strict and result["status"] == "INCOMPLETE":
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
