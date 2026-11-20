"""Bounded, private SLO projection. Neither operator input nor a read grants release approval."""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-sre-monitor/1"
HOURS = 28 * 24
METRICS = ("EligibleRequests", "SuccessfulRequests", "WithinLatencyTarget", "Heartbeat")


def require(condition):
    if not condition:
        raise ValueError("Invalid or incomplete private SRE monitor configuration.")


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def label(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z][a-z0-9-]{0,39}", value))


def policy(value, env):
    required = {
        "schema",
        "environment",
        "journey",
        "availability_bps",
        "latency_bps",
        "latency_ms",
        "primary_role",
        "backup_role",
        "runbook_sha256",
    }
    require(isinstance(value, dict) and required <= set(value) <= required | {"hours", "drill"})
    require(
        value["schema"] == "oci-sre-monitor-input/1"
        and value["environment"] == env
        and all(label(value[key]) for key in ("journey", "primary_role", "backup_role"))
        and value["primary_role"] != value["backup_role"]
    )
    require(
        isinstance(value["runbook_sha256"], str)
        and re.fullmatch(r"[a-f0-9]{64}", value["runbook_sha256"])
        and all(integer(value[key], 1, 10000) for key in ("availability_bps", "latency_bps"))
        and integer(value["latency_ms"], 1, 60000)
    )
    return value


def summarize(hours, config, end):
    """Closed UTC hours; every accepted hour has 60 complete minute samples."""
    require(isinstance(hours, list) and len(hours) <= HOURS)
    seen = {}
    for row in hours:
        require(isinstance(row, dict) and set(row) == {"end", "minutes", "eligible", "successful", "within"})
        stamp = row["end"]
        require(integer(stamp, end - HOURS * 3600 + 3600, end) and stamp % 3600 == 0 and stamp not in seen)
        require(
            integer(row["minutes"], 0, 60)
            and all(integer(row[k], 0, 10**12) for k in ("eligible", "successful", "within"))
            and row["within"] <= row["successful"] <= row["eligible"]
        )
        seen[stamp] = row
    complete = [item for item in seen.values() if item["minutes"] == 60]
    n, ok, fast = (sum(item[key] for item in complete) for key in ("eligible", "successful", "within"))
    if not seen:
        state = "no-data"
    elif len(complete) != HOURS:
        state = (
            "collecting-history"
            if len(complete) == len(seen) and max(seen) == end and end - min(seen) == (len(seen) - 1) * 3600
            else "incomplete-telemetry"
        )
    elif n == 0:
        state = "no-traffic"
    elif n < 100:
        state = "low-traffic"
    else:
        state = (
            "met"
            if ok * 10000 >= n * config["availability_bps"] and fast * 10000 >= n * config["latency_bps"]
            else "missed"
        )
    return {
        "status": state,
        "window_end": end,
        "window_hours": HOURS,
        "complete_hours": len(complete),
        "eligible": n,
        "successful": ok,
        "within_latency_target": fast,
        "latency_ms": config["latency_ms"],
        "observed_availability_percent": 100 * ok / n if n else None,
        "observed_within_target_percent": 100 * fast / n if n else None,
        "availability_target_bps": config["availability_bps"],
        "latency_target_bps": config["latency_bps"],
        "last_hour_requests": seen[end]["eligible"] if end in seen and seen[end]["minutes"] == 60 else None,
        "errors": n - ok,
        "low_traffic": n < 100,
    }


def drill(record, config, now):
    if record is None:
        return {"status": "unknown"}
    require(
        isinstance(record, dict)
        and set(record)
        == {
            "environment",
            "primary_role",
            "runbook_sha256",
            "fired_at",
            "received_at",
            "recovered_at",
            "cleared_at",
            "evidence_sha256",
        }
    )
    require(
        label(record["environment"])
        and label(record["primary_role"])
        and all(
            isinstance(record[k], str) and re.fullmatch(r"[0-9a-f]{64}", record[k])
            for k in ("runbook_sha256", "evidence_sha256")
        )
    )
    times = [record[k] for k in ("fired_at", "received_at", "recovered_at", "cleared_at")]
    require(all(integer(t, 1, now) for t in times) and all(a < b for a, b in zip(times, times[1:])))
    matches = (
        record["environment"] == config["environment"]
        and record["primary_role"] == config["primary_role"]
        and record["runbook_sha256"] == config["runbook_sha256"]
    )
    return {
        "status": "owner-recorded" if matches and now - times[-1] <= 30 * 86400 else "stale-or-unbound",
        "delivery_seconds": times[1] - times[0],
        "time_to_clear_seconds": times[3] - times[2],
        "receipt_authenticated": False,
    }


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def points(call, compartment, namespace, name, dims, start, end, interval, stat):
    """A single exact stream; pages, ambiguous dimensions and invalid values are unknown."""
    period = {"1h": 3600, "1m": 60}[interval]
    query = name + "[" + interval + "]{" + ",".join(f'{k} = "{v}"' for k, v in dims.items()) + "}." + stat + "()"
    try:
        payload = call(
            [
                "monitoring",
                "metric-data",
                "summarize-metrics-data",
                "--compartment-id",
                compartment,
                "--namespace",
                namespace,
                "--query-text",
                query,
                "--resolution",
                interval,
                "--start-time",
                iso(start),
                "--end-time",
                iso(end),
            ]
        )
        rows = payload["data"]
        if payload.get("opc-next-page") or not isinstance(rows, list) or len(rows) != 1:
            return {}
        row = rows[0]
        if (
            row.get("compartment-id") != compartment
            or row.get("namespace") != namespace
            or row.get("name") != name
            or row.get("dimensions") != dims
        ):
            return {}
        data = row["aggregated-datapoints"]
        if not isinstance(data, list) or len(data) > (end - start) // period + 1:
            return {}
        result = {}
        for item in data:
            d = dt.datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            t, v = d.timestamp(), item["value"]
            if (
                d.tzinfo is None
                or not t.is_integer()
                or t % period
                or not start <= t <= end
                or t in result
                or type(v) not in {int, float}
                or not 0 <= v <= 10**12
                or v != int(v)
            ):
                return {}
            result[int(t)] = int(v)
        return {k: v for k, v in result.items() if start < k <= end}
    except Exception:
        return {}


def user_hours(call, target, instance, config, end):
    dims = {"resourceId": instance, "journey": config["journey"]}
    samples = []
    for name in METRICS:
        selected = dims if name == "Heartbeat" else dict(dims, latencyMs=str(config["latency_ms"]))
        samples.append(
            [
                points(
                    call, target["compartment_id"], "founder_app", name, selected, end - HOURS * 3600, end, "1h", stat
                )
                for stat in ("sum", "count")
            ]
        )
    stamps = set().union(*(d for pair in samples for d in pair))
    hours = []
    for stamp in sorted(stamps):
        complete = (
            all(count.get(stamp) == 60 and stamp in total for total, count in samples)
            and samples[-1][0].get(stamp) == 60
        )
        vals = [s[0].get(stamp, 0) for s in samples[:3]]
        if not 0 <= vals[2] <= vals[1] <= vals[0]:
            complete, vals = False, [0, 0, 0]
        hours.append(
            dict(end=stamp, minutes=60 if complete else 0, eligible=vals[0], successful=vals[1], within=vals[2])
        )
    return hours


def probe(call, target, receipt, now):
    rows = [r for r in receipt["resources"] if r["type"] == "oci_health_checks_http_monitor"]
    if len(rows) != 1 or rows[0].get("compartment_id") != target["compartment_id"]:
        return {"status": "unknown"}
    identifier = rows[0].get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"ocid1\.httpmonitor\.[a-zA-Z0-9.-]{10,240}", identifier):
        return {"status": "unknown"}
    host = urlsplit(target.get("origin", "")).hostname
    try:
        m = call(["health-checks", "http-monitor", "get", "--monitor-id", identifier])["data"]
        if (
            m["id"] != identifier
            or m["compartment-id"] != target["compartment_id"]
            or m["is-enabled"] is not True
            or m["targets"] != [host]
            or m.get("port", 443) != 443
            or m["protocol"] != "HTTPS"
            or m["method"] != "GET"
            or m["path"] != target["health_path"]
            or m["interval-in-seconds"] != 60
        ):
            return {"status": "unknown"}
        vps = m["vantage-point-names"]
        if not isinstance(vps, list) or not 1 <= len(vps) <= 3 or len(set(vps)) != len(vps):
            return {"status": "unknown"}
        payload = call(
            [
                "health-checks",
                "http-probe-result",
                "list",
                "--probe-configuration-id",
                identifier,
                "--start-time-greater-than-or-equal-to",
                str((now - 300) * 1000),
                "--sort-order",
                "DESC",
                "--limit",
                "64",
            ]
        )
        results = payload["data"]
        if payload.get("opc-next-page") or not isinstance(results, list) or len(results) > 63:
            return {"status": "unknown"}
        per_vp = {k: {} for k in vps}
        for item in results:
            vp, millis = item["vantage-point-name"], item["start-time"]
            if (
                vp not in per_vp
                or item["probe-configuration-id"] != identifier
                or item["target"] != host
                or type(millis) not in (float, int)
                or not (now - 300) * 1000 <= millis <= now * 1000
                or millis in per_vp[vp]
                or type(item.get("is-healthy")) is not bool
            ):
                return {"status": "unknown"}
            per_vp[vp][millis] = item["is-healthy"] and item.get("status-code") == 200
        states = []
        for data in per_vp.values():
            last = sorted(data, reverse=True)[:3]
            if not last or now * 1000 - last[0] > 120000:
                states.append("unknown")
            elif (
                len(last) == 3
                and all(not data[t] for t in last)
                and all(30000 <= a - b <= 90000 for a, b in zip(last, last[1:]))
            ):
                states.append("failed")
            else:
                states.append("passing" if data[last[0]] else "degraded")
        return {
            "status": next((s for s in ("failed", "unknown", "degraded") if s in states), "passing"),
            "vantage_points": len(vps),
            "samples": len(results),
            "scope": "external synthetic; excluded from real-user counts",
        }
    except Exception:
        return {"status": "unknown"}


def overall(report):
    # This reports signals for triage; it is never a production promotion decision.
    user = report["users"]["status"]
    external = report["synthetic"]["status"]
    checks = report.get("operating_checks", [])
    if user == "missed" or external in {"failed", "degraded"} or any(c["status"] == "failed" for c in checks):
        return "failed"
    if report.get("mode") != "live-read-only":
        return "incomplete"
    if (
        user != "met"
        or external != "passing"
        or report.get("heartbeat", {}).get("status") != "current"
        or not checks
        or any(c["status"] != "passed" for c in checks)
    ):
        return "incomplete"
    return "observed"


def dashboard_summary(data):
    """Allowlisted projection from a private, already bound monitor observation."""
    users = data["users"]
    require(
        data.get("production_ready") is False
        and data["mode"] in {"owner-recorded", "live-read-only", "injected-test-client"}
        and data["status"] in {"observed", "incomplete", "failed"}
        and users["status"]
        in {"met", "missed", "low-traffic", "no-traffic", "no-data", "collecting-history", "incomplete-telemetry"}
        and users["window_hours"] == HOURS
        and integer(users["complete_hours"], 0, HOURS)
    )
    for key in ("eligible", "successful", "within_latency_target"):
        require(integer(users[key], 0, HOURS * 10**12))
    require(
        users["within_latency_target"] <= users["successful"] <= users["eligible"]
        and (
            users["status"] not in {"met", "missed"} or (users["eligible"] >= 100 and users["complete_hours"] == HOURS)
        )
    )
    external = data["synthetic"]["status"]
    require(external in {"failed", "unknown", "degraded", "passing"})
    return {
        "observed_at": data["observed_at"],
        "status": data["status"],
        "mode": data["mode"],
        "slo": users["status"],
        "eligible": users["eligible"],
        "successful": users["successful"],
        "within": users["within_latency_target"],
        "hours": users["complete_hours"],
        "synthetic": external,
    }


def request(
    project, *, environment, input_file=None, live=False, write=False, config_file=Path("~/.oci/config"), client=None
):
    spec = importlib.util.spec_from_file_location("sre_ops", ROOT / "scripts/operations.py")
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    common, p = ops.modules()
    common.select(project, environment, required=True)
    with p.Store(project, environment=environment, write=write) as store:
        store.read()
        now = int(time.time())
        report = {
            **common.bound(store, p, SCHEMA),
            "observed_at": now,
            "status": "unknown",
            "mode": "local",
            "production_ready": False,
            "required_input": "private-monitor-contract",
            "guide": "docs/SRE-MONITORING.md",
        }
        if input_file is None:
            return report
        c = policy(common.private_json(input_file), environment)
        end = now // 3600 * 3600
        aggregate = c.get("hours", [])
        report.update(
            drill=drill(c.get("drill"), c, now),
            responder_roles=[c["primary_role"], c["backup_role"]],
            runbook_sha256=c["runbook_sha256"],
            synthetic={"status": "unknown"},
            journey=c["journey"],
            mode="owner-recorded",
        )
        if live:
            require("hours" not in c)
            config = ops.role_config(store, p)
            receipt, receipt_hash = ops.receipt_at(store, p)
            call = client if client is not None else ops.Client(p, config["target"], config_file)
            operating = ops.collect(config, receipt, call)
            report.update(
                receipt_sha256=receipt_hash,
                mode="live-read-only" if client is None else "injected-test-client",
                operating_checks=operating["checks"],
                observed_image_digest=operating["observed_image_digest"],
                saturation=operating["metrics"],
            )
            instance = next(
                r["id"] for r in receipt["resources"] if r["type"] == "oci_container_instances_container_instance"
            )
            if operating["image_identity_verified"]:
                aggregate = user_hours(call, config["target"], instance, c, end)
                dims = {"resourceId": instance, "journey": c["journey"]}
                minute = now // 60 * 60
                heartbeat = points(
                    call,
                    config["target"]["compartment_id"],
                    "founder_app",
                    "Heartbeat",
                    dims,
                    minute - 600,
                    minute,
                    "1m",
                    "max",
                )
                seen = max((t for t, v in heartbeat.items() if v == 1), default=None)
                report["heartbeat"] = {
                    "status": "current" if seen and now - seen <= 300 else "unknown",
                    "last_seen": seen,
                }
            report["synthetic"] = probe(call, config["target"], receipt, now)
            if isinstance(call, ops.Client):
                call.check()
            require(receipt_hash == ops.receipt_at(store, p)[1] and common.current(report, store, p))
        report["users"] = summarize(aggregate, c, end)
        report["status"] = overall(report)
        report.pop("required_input")
        if write:
            report["evidence"] = p.save_report(store, report, "sre-monitor")
        return report
