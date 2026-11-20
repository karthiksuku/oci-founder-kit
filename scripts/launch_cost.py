"""Offline USD launch estimates and a private, environment-bound cleanup comparison."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RATES = ROOT / "recipes/launch-cost/rates.json"
SOURCE = "Oracle public price list API (PAY_AS_YOU_GO list price)"
PRICE_URL = "https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/"
SKUS = {
    "container_cpu": ("B93113", "OCPU Per Hour"),
    "container_memory": ("B93114", "Gigabyte Per Hour"),
    "load_balancer": ("B93030", "Load Balancer"),
    "load_balancer_bandwidth": ("B93031", "Mbps Per Hour"),
}
BASE = ("app_compute", "load_balancer")
EXTRAS = ("database_identity", "object_storage", "registry", "state_backups", "network_transfer",
          "monitoring", "workers", "source_overlap", "other")
GROUPS = BASE + EXTRAS
COST_FIELDS = ("demo_24h_usd", "run_30d_usd")
KEEP_FIELDS = ("kept_count", "kept_30d_usd")


class CostInputError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(valid, code="COST_INPUT"):
    if not valid:
        raise CostInputError(code)


def number(value):
    return type(value) in (int, float) and 0 <= value <= 10 ** 12


def dated(value, today):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
    parsed = dt.date.fromisoformat(value)
    require(0 <= (today - parsed).days <= 30)
    return parsed


def unit_rate(row, sku, metric, today):
    src = row.get("price_source")
    require(isinstance(src, dict) and row.get("part_number") == src.get("part_number") == sku
            and row.get("expected_metric") == src.get("metric") == metric
            and row.get("evidence") == "sourced" and src.get("source") == SOURCE)
    dated(src.get("checked_at"), today)
    if row.get("tiers") is None:
        require(number(row.get("unit_price")))
        return row["unit_price"], "flat"
    tiers = row["tiers"]
    require(row.get("unit_price") is None and isinstance(tiers, list) and 1 <= len(tiers) <= 30)
    previous = 0
    for i, tier in enumerate(tiers):
        require(isinstance(tier, dict) and number(tier.get("from")) and tier["from"] == previous
                and number(tier.get("price")) and "to" in tier)
        previous = tier["to"]
        require(previous is None if i == len(tiers) - 1 else number(previous) and previous > tier["from"])
    # Shared tenancy-wide allowances and tier usage are unknown before launch.
    return max(t["price"] for t in tiers), "highest listed tier"


def infra_rates(env, rates, attached, today):
    require(isinstance(rates, dict) and rates.get("schema") == "oci-launch-rates/1" and rates.get("currency") == "USD")
    lines = rates["options"]["oci"]["lines"]
    require(isinstance(lines, list) and len(lines) <= len(SKUS) and all(isinstance(line, dict) for line in lines))
    by_id = {line.get("id"): line for line in lines}
    require(len(by_id) == len(lines) and set(by_id) <= SKUS.keys())
    units = {"container_cpu": env["target"].get("ocpus"), "container_memory": env["target"].get("memory_gbs"),
             "load_balancer": 1, "load_balancer_bandwidth": 10}
    result = []
    for key, (sku, metric) in SKUS.items():
        input_line = by_id.get(key, {})
        try:
            price, basis = unit_rate(input_line, sku, metric, today)
            checked = input_line["price_source"]["checked_at"]
        except (ValueError, TypeError):
            price, basis, checked = None, "missing, stale or mismatched price", None
        quantity = units[key] if attached and number(units[key]) and units[key] > 0 else None
        result.append({"id": key, "part_number": sku, "unit": metric, "quantity": quantity,
                       "unit_usd": price, "rate_basis": basis, "price_checked_at": checked})
    return result


def assumption_template(env, binding, today):
    items = {key: dict.fromkeys(KEEP_FIELDS if key in BASE else COST_FIELDS + KEEP_FIELDS) for key in GROUPS}
    return {"schema": "oci-launch-assumptions/1", "environment": env["name"], "target_sha256": binding,
            "currency": "USD", "as_of": today.isoformat(), "items": items}


def validate_items(items, *, cleanup):
    require(isinstance(items, dict) and set(items) <= set(GROUPS))
    for key, row in items.items():
        fields = ("count", "usd_30d") if cleanup else KEEP_FIELDS if key in BASE else COST_FIELDS + KEEP_FIELDS
        count_key, keep_key = fields[-2:]
        require(isinstance(row, dict) and set(row) <= set(fields))
        for field, amount in row.items():
            if amount is not None:
                require(number(amount))
                if field == count_key:
                    require(type(amount) is int and amount <= 1000000)
        require(row.get(count_key) != 0 or row.get(keep_key) in (None, 0))
    return items


def subtotal(values):
    known = [v for v in values.values() if v is not None]
    unknown = [k for k, value in values.items() if value is None]
    total = round(sum(known), 4) if known else None
    return {"known_usd": total, "estimate_usd": None if unknown else total, "unknown": unknown}


def after_cleanup(comparison, expected, template, as_of, today):
    unknown = {"status": "unknown", "estimated_delta_30d_usd": None}
    if comparison is None:
        return unknown
    require(isinstance(comparison, dict) and set(comparison) == set(template) and
            all(comparison.get(k) == template[k] for k in ("schema", "environment", "estimate_sha256",
                                                           "estimate_as_of", "currency")))
    require(dated(comparison["as_of"], today) >= as_of and isinstance(comparison["inventory_evidence_sha256"], str)
            and re.fullmatch(r"[a-f0-9]{64}", comparison["inventory_evidence_sha256"]))
    actual = validate_items(comparison["items"], cleanup=True)
    rows = {}
    deltas = {}
    complete_counts = True
    for key in GROUPS:
        before = expected.get(key, {})
        after = actual.get(key, {})
        n, m = before.get("kept_count"), after.get("count")
        a, b = before.get("kept_30d_usd"), after.get("usd_30d")
        delta = None if a is None or b is None else round(b - a, 4)
        complete_counts &= n is not None and m is not None
        rows[key] = {"expected_count": n, "reported_count": m,
                     "count_delta": None if n is None or m is None else m - n,
                     "expected_30d_usd": a, "repriced_30d_usd": b, "delta_30d_usd": delta}
        deltas[key] = delta
    total = subtotal(deltas)["estimate_usd"]
    return {"status": "compared" if total is not None and complete_counts else "incomplete",
            "basis": "owner-reviewed inventory and repricing", "as_of": comparison["as_of"],
            "inventory_evidence_sha256": comparison["inventory_evidence_sha256"],
            "items": rows, "estimated_delta_30d_usd": total, "independently_verified": False}


def forecast(env, binding, rates, assumptions, cleanup, *, attached, today):
    require(env["role"] in {"rehearsal", "production"} and env["blueprint"] == "web-container", "COST_TARGET")
    template = assumption_template(env, binding, today)
    data = template if assumptions is None else assumptions
    require(isinstance(data, dict) and set(data) == set(template) and
            all(data.get(k) == template[k] for k in ("schema", "environment", "target_sha256", "currency")))
    # Reconstruct the original forecast when reconciling a later cleanup.
    # A historical comparison must never make expired input current for a new launch.
    quote_day = today
    if cleanup is not None:
        require(isinstance(cleanup, dict) and isinstance(cleanup.get("estimate_as_of"), str))
        quote_day = dt.date.fromisoformat(cleanup["estimate_as_of"])
        require(quote_day <= today)
    as_of = dated(data["as_of"], quote_day)
    inputs = validate_items(data["items"], cleanup=False)
    infra = infra_rates(env, rates, attached, quote_day)
    windows = {}
    for hours, field in ((24, "demo_24h"), (720, "run_30d")):
        values = {r["id"]: None if r["quantity"] is None or r["unit_usd"] is None
                  else hours * r["quantity"] * r["unit_usd"] for r in infra}
        values.update({k: inputs.get(k, {}).get(field + "_usd") for k in EXTRAS})
        windows[field] = subtotal(values)
    keep = subtotal({k: inputs.get(k, {}).get("kept_30d_usd") for k in GROUPS})
    identity = hashlib.sha256(json.dumps([quote_day.isoformat(), data, rates, infra, windows, keep], sort_keys=True,
                                        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    after_template = {"schema": "oci-launch-cleanup/1", "environment": env["name"], "currency": "USD",
                      "estimate_sha256": identity, "estimate_as_of": quote_day.isoformat(), "as_of": today.isoformat(),
                      "inventory_evidence_sha256": None,
                      "items": {key: {"count": None, "usd_30d": None} for key in GROUPS}}
    after = after_cleanup(cleanup, inputs, after_template, quote_day, today)
    complete = (all(w["estimate_usd"] is not None for w in (*windows.values(), keep))
                and all(inputs.get(key, {}).get("kept_count") is not None for key in GROUPS)
                and (cleanup is None or after["status"] == "compared"))
    return {"schema": "oci-launch-cost/1", "environment": env["name"], "target_sha256": binding,
            "status": "estimated" if complete else "incomplete", "currency": "USD",
            "estimate_sha256": identity, "as_of": quote_day.isoformat(), "assumptions_as_of": as_of.isoformat(),
            "historical_comparison": quote_day < today, "source": PRICE_URL,
            "blueprint_source_verified": attached, "terraform_plan_priced": False, "infrastructure": infra, **windows,
            "owner_input_items": inputs, "retained_30d": keep, "after_cleanup": after,
            "assumptions_template": template, "cleanup_template": after_template,
            "cloud": "not_checked", "approval_granted": False, "spending_cap": False}


def request(project, *, environment, rates=None, assumptions=None, after_cleanup=None, p):
    private = p.helper("kit_common").private_json
    with p.Store(project, environment=environment) as store:
        env = store.environment_config
        require(env["role"] in {"rehearsal", "production"} and env["blueprint"] == "web-container", "COST_TARGET")
        try:
            p.helper("deployment_config").infrastructure(store, p)
            attached = True
        except (ValueError, OSError):
            attached = False
        result = forecast(env, p.digest(p.canonical(env)), private(rates) if rates else json.loads(RATES.read_bytes()),
                          private(assumptions) if assumptions else None, private(after_cleanup) if after_cleanup else None,
                          attached=attached, today=dt.datetime.now(dt.timezone.utc).date())
        # Reuse the dashboard's existing environment, time, receipt and currency validation.
        observations = p.helper("dashboard").view(store, p)["observations"]
        snapshot = observations.get("oci-operating-observation/1/web", {}).get("costs")
        result["reported_usage"] = {"status": "reported", **snapshot} if snapshot else {"status": "unknown"}
        return result


def summary_lines(result):
    lines = [f"Launch cost preview for {result['environment']} (USD, forecast dated {result['as_of']})"]
    for field, label in (("demo_24h", "24-hour demo"), ("run_30d", "30 days running"),
                         ("retained_30d", "Next 30 days after planned cleanup")):
        item = result[field]
        amount = item["known_usd"]
        estimate = "unknown" if amount is None else f"USD {amount:,.4f}"
        if item["unknown"]:
            lines.append(f"{label}: known subtotal {estimate}. Unpriced: {', '.join(item['unknown'])}")
        else:
            lines.append(f"{label}: estimated {estimate}")
    for key, item in result["owner_input_items"].items():
        count, amount = item.get("kept_count"), item.get("kept_30d_usd")
        if (count or amount):
            cost = "unknown" if amount is None else f"USD {amount:,.4f}"
            lines.append(f"Expected to remain: {key}, count {count if count is not None else 'unknown'}, next 30 days {cost}")
    usage = result["reported_usage"]
    lines.append("Reported Usage API cost: " + (
        f"{usage['currency']} {usage['reported_amount']:,.4f} ({usage['period_start_utc']} to {usage['period_end_utc']})"
        if usage["status"] == "reported" else "unknown"))
    comparison = result["after_cleanup"]
    delta = comparison["estimated_delta_30d_usd"]
    lines.append("Post-cleanup inventory comparison: " + comparison["status"] +
                 (f" (USD {delta:+,.4f} estimated difference for 30 days)" if delta is not None else ""))
    for key, item in comparison.get("items", {}).items():
        if item["count_delta"] or item["delta_30d_usd"]:
            changed = item["delta_30d_usd"]
            cost = "unknown" if changed is None else f"USD {changed:+,.4f}"
            count = item["reported_count"]
            lines.append(f"After cleanup: {key}, reported count {count if count is not None else 'unknown'}, estimated difference {cost}")
    if not result["blueprint_source_verified"]:
        lines.append("Attach the reviewed web-container Terraform source for this environment to estimate its shape.")
    lines.append("Review missing assumptions in docs/LAUNCH-COST.md. Budget alerts are soft limits.")
    return lines
