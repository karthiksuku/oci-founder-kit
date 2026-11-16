#!/usr/bin/env python3
"""Render a private, network-free environment dashboard from the existing reports."""

from __future__ import annotations

import html
import datetime as dt
import importlib.util
import math
import os
import re
from pathlib import Path
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
FRESH_SECONDS = 86400


def project_module():
    spec = importlib.util.spec_from_file_location("oci_dashboard_project", ROOT / "scripts/project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def view(store, p) -> dict:
    state = store.read()
    progress, source, _ = p.report(store, state)
    target_hash = progress["target_sha256"]
    kit_hash = p.kit_fingerprint()
    now = int(time.time())
    names = os.listdir(store.evidence_fd)
    if len(names) > 200:
        raise ValueError("Dashboard evidence exceeds its bound.")
    observations = {}
    latest_seen = {}
    stale = unreadable = 0
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        try:
            data = p.object_at(store.evidence_fd, name, private=True)
        except (ValueError, OSError, UnicodeError, RecursionError):
            unreadable += 1
            continue
        schema = data.get("schema")
        if schema not in {"oci-workload-readiness/1", "oci-runtime-probe/1", "oci-migration-parity/1",
                          "oci-production-check/1", "oci-operating-costs/1", "oci-operating-observation/1"}:
            continue
        observed = data.get("observed_at")
        if (data.get("environment") != store.environment or data.get("target_sha256") != target_hash
                or data.get("source_sha256") != source or data.get("kit_sha256") != kit_hash
                or type(observed) is not int or not 0 <= now - observed <= FRESH_SECONDS):
            stale += 1
            continue
        selection = schema + ("/" + str(data.get("component_role")) if schema == "oci-operating-observation/1" else "")
        if observed < latest_seen.get(selection, -1):
            continue
        tied = observed == latest_seen.get(selection)
        latest_seen[selection] = observed
        observations.pop(selection, None)
        if tied:
            unreadable += 1
            continue
        # Never forward arbitrary payloads, raw receipt fields, resource labels or errors to HTML.
        if schema == "oci-operating-observation/1":
            component = data.get("component_role")
            if (component not in {"web", "worker"} or data.get("status") not in {"passed", "failed", "unknown"}
                    or data.get("mode") not in {"live-read-only", "injected-test-client"}
                    or not p.valid_hash(data.get("receipt_sha256"))):
                unreadable += 1
                continue
            configs = p.helper("environments").component_configs(store.environment_config)
            selected = next((c for c in configs if c["component_role"] == component), None)
            if selected is None:
                unreadable += 1
                continue
            try:
                _, receipt_hash = p.helper("operations").receipt_at(store, p, component=component)
                if receipt_hash != data["receipt_sha256"]:
                    raise ValueError("Deployment changed since observation.")
            except (ValueError, OSError, KeyError, TypeError):
                stale += 1
                continue
            checks = data.get("checks")
            identifiers = {"container_instance", "image_identity", "load_balancer", "certificate_expiry", "recent_work_requests", "metrics"}
            if (not isinstance(checks, list) or len(checks) != len(identifiers)
                    or {c.get("id") for c in checks if isinstance(c, dict)} != identifiers
                    or any(c.get("status") not in {"passed", "failed", "unknown"} for c in checks)):
                unreadable += 1
                continue
            image_passed = next(c["status"] for c in checks if c["id"] == "image_identity") == "passed"
            verified = (data["mode"] == "live-read-only" and data.get("image_identity_verified") is True and image_passed
                        and data.get("observed_image_digest") == selected["target"].get("image_digest")
                        and isinstance(data.get("observed_image_digest"), str))
            item = {"observed_at": observed, "status": data["status"], "mode": data["mode"],
                    "image_identity_verified": verified, "component_role": component,
                    "failed_checks": sum(c["status"] == "failed" for c in checks),
                    "checks": [{"id": c["id"], "status": c["status"]} for c in checks]}
            costs = data.get("costs")
            if data["mode"] == "live-read-only" and isinstance(costs, dict) and costs.get("status") == "reported":
                amount = costs.get("reported_amount")
                try:
                    dates = [dt.datetime.fromisoformat(costs[key].replace("Z", "+00:00")) for key in ("period_start_utc", "period_end_utc")]
                    dated = all(d.tzinfo is not None for d in dates) and dates[0] < dates[1] <= dt.datetime.now(dt.timezone.utc)
                except (ValueError, TypeError, KeyError, AttributeError):
                    dated = False
                if (dated and type(amount) in {int, float} and math.isfinite(amount) and abs(amount) <= 10 ** 12
                        and isinstance(costs.get("currency"), str) and re.fullmatch(r"[A-Z]{3}", costs["currency"])):
                    item["costs"] = {key: costs[key] for key in ("reported_amount", "currency", "period_start_utc", "period_end_utc")}
            schema += "/" + component
        elif schema == "oci-operating-costs/1":
            keys = ("estimated_monthly_usd", "observed_period_usd", "overlap_monthly_usd")
            amounts = {key: data.get(key) for key in keys}
            dates = {}
            try:
                for key in ("period_start_utc", "period_end_utc", "pricing_observed_at_utc"):
                    value = data.get(key)
                    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
                        raise ValueError("Missing dated cost basis.")
                    dates[key] = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                if not dates["period_start_utc"] < dates["period_end_utc"] <= dt.datetime.now(dt.timezone.utc):
                    raise ValueError("Invalid observed billing period.")
                if dates["pricing_observed_at_utc"] > dt.datetime.now(dt.timezone.utc):
                    raise ValueError("Invalid pricing observation date.")
            except ValueError:
                unreadable += 1
                continue
            if (not p.valid_hash(data.get("pricing_evidence_sha256")) or not p.valid_hash(data.get("usage_evidence_sha256"))
                    or any(value is not None and (type(value) not in {int, float} or not math.isfinite(value)
                            or not 0 <= value <= 10 ** 12) for value in amounts.values())
                    or type(data.get("retained_resources_count")) is not int
                    or not 0 <= data["retained_resources_count"] <= 1000000):
                unreadable += 1
                continue
            item = {"observed_at": observed, **amounts, "retained_resources_count": data["retained_resources_count"],
                    **{key: data[key] for key in dates},
                    "basis": "owner-recorded; inspect private dated pricing and usage evidence"}
        else:
            status = data.get("status")
            if status not in {"passed", "blocked", "incomplete", "failed", "unknown"}:
                unreadable += 1
                continue
            rows = data.get("checks", [])
            if not isinstance(rows, list) or len(rows) > 200:
                unreadable += 1
                continue
            failures = sum(1 for row in rows if isinstance(row, dict)
                           and row.get("status", row.get("parity")) in {"failed", "blocked"})
            item = {"observed_at": observed, "status": status, "failed_checks": failures}
        if schema not in observations or observed > observations[schema]["observed_at"]:
            observations[schema] = item
    steps = {item["id"]: item["status"] for item in progress["steps"]}
    return {"schema": "oci-local-dashboard/1", "environment": store.environment,
            "role": progress["role"], "blueprint": progress["blueprint"],
            "selected_image_digest": store.environment_config["target"].get("image_digest"),
            "deployed_image_identity": "OCI-readback-matched" if observations.get("oci-operating-observation/1/web", {}).get("image_identity_verified") else "not-independently-verified", "deployment": steps.get("deployment", "unobserved"),
            "backup_and_rollback_evidence": steps.get("recovery", "not-recorded"),
            "observations": observations, "stale_reports": stale, "unreadable_reports": unreadable,
            "next_action": progress["next_action"]["id"], "generated_at": now,
            "production_ready": False, "costs_are_spending_caps": False,
            "scope": "Private local view of current bound reports; no polling, telemetry, raw secrets or cloud requests. Owner records are not independent proof. Reports older than 24 hours are stale."}


def page(data: dict) -> bytes:
    escape = lambda value: html.escape(str(value), quote=True)
    observations = data["observations"]
    rows = "".join(f"<tr><th>{escape(schema)}</th><td>{escape(item.get('status', 'owner-recorded'))} · {escape(item.get('mode', 'owner-recorded'))}</td>"
                   f"<td>{escape(item.get('failed_checks', '—'))}</td><td>{escape(dt.datetime.fromtimestamp(item['observed_at'], dt.timezone.utc).isoformat())}</td></tr>"
                   for schema, item in observations.items())
    costs = observations.get("oci-operating-costs/1", {})
    observed_costs = observations.get("oci-operating-observation/1/web", {}).get("costs", {})
    reported = (f"{observed_costs['currency']} {observed_costs['reported_amount']:,.2f}" if observed_costs else "Unknown")
    diagnostics = "".join(f"<li>{escape(item['component_role'])}: {escape(check['id'])} — {escape(check['status'])}</li>"
                          for item in observations.values() if "component_role" in item for check in item["checks"])
    money = lambda key: "Unknown" if costs.get(key) is None else f"USD {costs[key]:,.2f}"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>OCI Founder Kit · private environment</title>
<style>body{{background:#0b1220;color:#edf2fc;font:16px/1.6 system-ui;margin:0}}main{{max-width:1040px;margin:auto;padding:48px 24px}}
h1{{font-size:clamp(2rem,5vw,3.6rem);line-height:1.1}}h2{{font-size:1.1rem}}.eyebrow{{color:#76e6cd}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}}
section{{background:#131f32;border:1px solid #2c3f59;border-radius:18px;padding:22px;margin:20px 0}}.grid section{{margin:0}}
code{{overflow-wrap:anywhere;color:#a1cfef}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px 6px;border-bottom:1px solid #2c3f59}}
p,small{{color:#bdcde1}}.value{{font-size:1.5rem;color:#fff}}footer{{margin-top:24px}}</style></head>
<body><main><p class="eyebrow">OCI FOUNDER KIT · PRIVATE LOCAL REPORT</p>
<h1>{escape(data['environment'])}</h1><p>{escape(data['role'])} · {escape(data['blueprint'])}</p>
<div class="grid"><section><h2>Deployment</h2><p>{escape(data['deployment'])}</p><small>Image identity: {escape(data['deployed_image_identity'])}</small></section>
<section><h2>Recovery evidence</h2><p>{escape(data['backup_and_rollback_evidence'])}</p><small>Review isolated restore and rollback results.</small></section>
<section><h2>Next action</h2><p class="value">{escape(data['next_action'])}</p><small>{data['stale_reports']} stale · {data['unreadable_reports']} unreadable reports</small></section></div>
<section><h2>Selected image digest</h2><code>{escape(data['selected_image_digest'] or 'Not selected')}</code><p>Selection alone does not establish which image is deployed.</p></section>
<section><h2>Current observations</h2><table><thead><tr><th>Report</th><th>Result</th><th>Failed checks</th><th>Observed UTC</th></tr></thead><tbody>{rows or '<tr><td colspan="4">No current bound reports. Run doctor or verify for this environment.</td></tr>'}</tbody></table><ul>{diagnostics}</ul></section>
<section><h2>Usage API reported cost</h2><p class="value">{escape(reported)}</p><small>{escape(observed_costs.get('period_start_utc', 'Period unknown'))} — {escape(observed_costs.get('period_end_utc', ''))}</small><p>Selected receipt resources only. Reporting may lag; this is not the final invoice or a spending cap. Missing billing access never means zero.</p></section>
<div class="grid"><section><h2>Estimated monthly cost</h2><p class="value">{money('estimated_monthly_usd')}</p></section>
<section><h2>Observed period cost</h2><p class="value">{money('observed_period_usd')}</p><small>{escape(costs.get('period_start_utc', 'Period unknown'))} — {escape(costs.get('period_end_utc', ''))}</small></section>
<section><h2>Migration overlap / month</h2><p class="value">{money('overlap_monthly_usd')}</p></section></div>
<section><h2>Retained billable resources</h2><p>{escape(costs.get('retained_resources_count', 'Unknown'))}</p><p>Costs are owner-recorded evidence. Inspect the dated pricing source, billing period and retained-resource inventory. Budget alerts are not spending caps.</p></section>
<footer><small>{escape(data['scope'])} This page does not certify production readiness.</small></footer></main></body></html>"""
    return document.encode()


def render(project: Path, *, environment: str) -> dict:
    p = project_module()
    with p.Store(project, environment=environment, write=True) as store:
        data = view(store, p)
        raw = page(data)
        name = "dashboard-" + uuid.uuid4().hex + ".html"
        p.helper("environments").put(store.fd, name, raw)
        os.fsync(store.fd)
        return {"schema": data["schema"], "environment": environment,
                "path": f".oci-kit/environments/{environment}/{name}", "network_requests": 0,
                "scope": data["scope"]}
