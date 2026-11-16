"""Bounded read-only observations of resources from one bound deployment receipt.

CLI responses stay in memory. Reports contain projections, never raw logs,
credential material or arbitrary service messages. A receipt is a local assertion;
resource ownership and the deployed image are checked again against OCI.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-operating-observation/1"
STATES = {"passed", "failed", "unknown"}
RESOURCE_TYPES = {"oci_container_instances_container_instance", "oci_load_balancer_load_balancer"}


def modules():
    import importlib.util
    spec = importlib.util.spec_from_file_location("oci_operations_common", ROOT / "scripts/kit_common.py")
    common = importlib.util.module_from_spec(spec); spec.loader.exec_module(common)
    return common, common.project_module()


def role_config(store, p, component="web"):
    roles = p.helper("environments").component_configs(store.environment_config)
    chosen = next((c for c in roles if c["component_role"] == component), None)
    if chosen is None:
        raise ValueError("Unknown runtime component.")
    return chosen


def receipt_at(store, p, selected=None, *, component="web"):
    """Read only the selected stack's private receipts; newest interrupted work blocks."""
    config = role_config(store, p, component)
    infrastructure = config.get("infrastructure")
    if not infrastructure or config["role"] == "source":
        raise ValueError("An OCI target is required.")
    directory = store.project / infrastructure / ".gate/receipts"
    _, fd = p.open_project(directory)
    try:
        names = os.listdir(fd)
        if len(names) > 200:
            raise ValueError("Receipt bound exceeded.")
        items = []
        for name in names:
            if not name.endswith(".json"):
                continue
            value = p.object_at(fd, name, private=True)
            if value.get("schema") != "oci-deploy-receipt/2":
                continue
            started = value.get("started_at")
            if not isinstance(started, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:\+00:00|Z)", started):
                raise ValueError("Invalid receipt timestamp.")
            epoch = dt.datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp()
            if epoch > time.time() + 30:
                raise ValueError("Future receipt.")
            items.append((epoch, name, value))
        if not items:
            raise ValueError("No deployment receipt.")
        latest = max(item[0] for item in items)
        candidates = [item for item in items if item[0] == latest]
        if len(candidates) != 1:
            raise ValueError("Ambiguous latest deployment.")
        _, name, value = candidates[0]
        if selected is not None and Path(selected).expanduser().absolute() != directory / name:
            raise ValueError("Only the latest selected-stack receipt can be observed.")
        if value.get("kind") != "apply" or value.get("status") != "applied" or not p.valid_hash(value.get("plan_sha256")):
            raise ValueError("Review interrupted deployment before observation.")
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py")
        gate.named_workload.sources(store.project / infrastructure, config["blueprint"])
        expected = {"schema": "oci-deploy-environment-binding/1", "project_path": str(store.project),
                    "project_identity": p.identity(store.root_fd), "environment": store.environment,
                    "configuration_sha256": p.digest(p.canonical(store.environment_config)), "infrastructure": infrastructure,
                    "component_role": component,
                    **({"web_compartment_id": store.environment_config["target"]["compartment_id"]} if component == "worker" else {}),
                    "blueprint": config["blueprint"], "role": config["role"], "backend": config.get("backend"),
                    "target": config["target"], "sources": gate.source_binding()}
        binding = value.get("project_environment")
        if not config.get("backend") or not isinstance(binding, dict) or any(binding.get(k) != v for k, v in expected.items()):
            raise ValueError("Stale or wrong environment receipt.")
        resources = value.get("resources")
        if not isinstance(resources, list) or not 1 <= len(resources) <= 100:
            raise ValueError("Missing bounded resource inventory.")
        seen = set()
        for resource in resources:
            if not isinstance(resource, dict):
                raise ValueError("Invalid inventory.")
            identifier = resource.get("id")
            if resource.get("type") not in RESOURCE_TYPES:
                continue
            if (not isinstance(identifier, str) or not re.fullmatch(r"ocid1\.[a-z0-9]+\.[a-z0-9.-]{10,240}", identifier)
                    or identifier in seen or resource.get("compartment_id") != config["target"].get("compartment_id")):
                raise ValueError("Resource binding mismatch.")
            seen.add(identifier)
        return value, p.digest(p.canonical(value))
    finally:
        os.close(fd)


class Client:
    """Use the existing bounded runner, explicit profile and fresh session checks."""
    def __init__(self, p, target, config_file):
        self.files = p.helper("readiness").load("skills/oci-deploy/scripts/image_gate.py")
        self.auth = p.helper("readiness").load("skills/oci-deploy/scripts/backend_auth.py")
        self.binary = self.files.fingerprint("oci")
        self.target = target
        self.config_file = Path(config_file).expanduser().absolute()
        self.settings = {"auth": {"api_key": "APIKey", "security_token": "SecurityToken"}[target["auth"]],
                         "config_file_profile": target["profile"]}
        self.context = self.auth.inspect(self.settings, self.config_file)
        self.config_hash = self.files.sha(self.auth._read(self.config_file))
        self.deadline, self.requests = time.monotonic() + 120, 0

    def check(self):
        if (self.auth.inspect(self.settings, self.config_file) != self.context
                or self.files.sha(self.auth._read(self.config_file)) != self.config_hash):
            raise ValueError("Authentication changed; reauthenticate and repeat observation.")

    def __call__(self, arguments):
        self.check()
        self.requests += 1
        if self.requests > 20 or time.monotonic() >= self.deadline:
            raise ValueError("Observation request bound exceeded.")
        env = {key: value for key, value in os.environ.items() if not key.startswith("OCI_")}
        env["OCI_CLI_AUTO_PROMPT"] = "False"
        raw = self.files.run(self.binary, [*arguments, "--region", self.target["region"],
            "--profile", self.target["profile"], "--auth", self.target["auth"],
            "--config-file", str(self.config_file), "--output", "json", "--cli-rc-file", os.devnull,
            "--no-retry", "--connection-timeout", "5", "--read-timeout", "10"],
            timeout=min(20, max(1, self.deadline - time.monotonic())), environment=env)
        self.check()
        value = self.files.parse(raw)
        if not isinstance(value, dict) or "data" not in value:
            raise ValueError("Unrecognized service response.")
        return value


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Missing service timestamp.")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires timezone.")
    return parsed.timestamp()


def collect(config, receipt, call):
    target, checks = config["target"], []
    image_verified = False
    metrics = None

    def add(name, status, recovery, **details):
        checks.append({"id": name, "status": status, "recovery": recovery, **details})

    def read(arguments):
        # Deliberately hide SDK/CLI exception strings: they can contain request data.
        try:
            payload = call(arguments)
            return payload.get("data"), bool(payload.get("opc-next-page"))
        except Exception:
            return None, True

    instances = [r for r in receipt["resources"] if r.get("type") == "oci_container_instances_container_instance"]
    balancers = [r for r in receipt["resources"] if r.get("type") == "oci_load_balancer_load_balancer"]
    # Current application blueprints have one instance; do not silently cover only one of many.
    if len(instances) != 1 or len(balancers) > 1:
        raise ValueError("Unsupported observation topology.")
    instance = instances[0]["id"]
    data, _ = read(["container-instances", "container-instance", "get", "--container-instance-id", instance])
    owned = isinstance(data, dict) and data.get("id") == instance and data.get("compartment-id") == target["compartment_id"]
    state = data.get("lifecycle-state") if owned else None
    add("container_instance", "passed" if state == "ACTIVE" else "failed" if state in {"FAILED", "DELETED", "INACTIVE"} else "unknown",
        "Inspect the selected instance and reviewed deployment attempt; do not retry a write automatically.")
    containers = data.get("containers") if owned else None
    digest = target.get("image_digest")
    if isinstance(containers, list) and len(containers) == 1 and isinstance(containers[0], dict):
        identifier = containers[0].get("container-id", containers[0].get("id"))
        if isinstance(identifier, str) and re.fullmatch(r"ocid1\.(?:compute)?container\.[a-z0-9.-]{10,240}", identifier):
            container, _ = read(["container-instances", "container", "get", "--container-id", identifier])
            if (isinstance(container, dict) and container.get("id") == identifier
                    and container.get("container-instance-id") == instance and container.get("compartment-id") == target["compartment_id"]):
                url = container.get("image-url", "")
                image_verified = bool(isinstance(url, str) and re.fullmatch(r"[a-z0-9.-]+\.ocir\.io/[a-z0-9_./-]+@sha256:[0-9a-f]{64}", url)
                                      and url.rsplit("@", 1)[-1] == digest)
                add("image_identity", "passed" if image_verified else "failed", "Compare the deployed image with the reviewed immutable digest.")
    if not any(c["id"] == "image_identity" for c in checks):
        add("image_identity", "unknown", "Allow metadata reads for the selected instance and container; tags do not establish immutable identity.")
    for resource in balancers:
        identifier = resource["id"]
        lb, _ = read(["lb", "load-balancer", "get", "--load-balancer-id", identifier])
        health = None
        if isinstance(lb, dict) and lb.get("id") == identifier and lb.get("compartment-id") == target["compartment_id"]:
            health, _ = read(["lb", "load-balancer-health", "get", "--load-balancer-id", identifier])
        status = health.get("status") if isinstance(health, dict) else None
        add("load_balancer", "passed" if status == "OK" else "failed" if status in {"CRITICAL", "WARNING"} else "unknown",
            "Inspect backend health, the app port, health route and selected subnet rules.")
    if not balancers:
        add("load_balancer", "unknown", "No load balancer exists in this receipt; verify the selected HTTPS endpoint separately.")
    certificate = target.get("certificate_id")
    expiry_days = None
    if certificate:
        cert, _ = read(["certs-mgmt", "certificate", "get", "--certificate-id", certificate])
        if isinstance(cert, dict) and cert.get("id") == certificate and cert.get("lifecycle-state") == "ACTIVE":
            try:
                version = cert.get("current-version", {})
                expiry_days = math.floor((timestamp(version["validity"]["time-not-after"]) - time.time()) / 86400)
            except (ValueError, TypeError, KeyError, OverflowError):
                pass
    add("certificate_expiry", "unknown" if expiry_days is None else "failed" if expiry_days < 14 else "passed",
        "The certificate owner must renew it before expiry; separately verify hostname, chain and HTTPS behavior.", days_remaining=expiry_days)
    work, paged = read(["container-instances", "work-request", "list", "--compartment-id", target["compartment_id"],
        "--resource-id", instance, "--limit", "20", "--sort-by", "timeAccepted", "--sort-order", "DESC"])
    items = work.get("items") if isinstance(work, dict) else work
    failures = None
    if isinstance(items, list) and len(items) <= 20:
        scoped = all(isinstance(item, dict) and item.get("compartment-id") == target["compartment_id"]
                     and item.get("status") in {"ACCEPTED", "CANCELED", "CANCELING", "FAILED", "IN_PROGRESS", "SUCCEEDED"}
                     and isinstance(item.get("resources"), list)
                     and any(r.get("identifier") == instance for r in item["resources"] if isinstance(r, dict)) for item in items)
        if scoped:
            failures = sum(item.get("status") == "FAILED" for item in items)
    completed = isinstance(items, list) and all(isinstance(item, dict) and item.get("status") in {"SUCCEEDED", "FAILED"} for item in items)
    add("recent_work_requests", "failed" if failures else "passed" if failures == 0 and not paged and completed else "unknown",
        "Review private work-request failures; this bounded sample is not a complete history.", failed_count=failures, truncated=paged)
    end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = end - dt.timedelta(minutes=15)
    result, paged = read(["monitoring", "metric-data", "summarize-metrics-data", "--compartment-id", target["compartment_id"],
        "--namespace", "oci_computecontainerinstance", "--query-text", f'CpuUtilization[1m]{{resourceId = "{instance}"}}.mean()',
        "--start-time", start.isoformat(), "--end-time", end.isoformat()])
    if isinstance(result, list) and len(result) == 1 and not paged:
        row = result[0]
        if (isinstance(row, dict) and row.get("namespace") == "oci_computecontainerinstance"
                and row.get("compartment-id") == target["compartment_id"]
                and row.get("name") == "CpuUtilization" and isinstance(row.get("dimensions"), dict)
                and row["dimensions"].get("resourceId") == instance):
            points = row.get("aggregated-datapoints")
            if isinstance(points, list) and 1 <= len(points) <= 30:
                try:
                    times = [timestamp(point["timestamp"]) for point in points]
                    values = [point["value"] for point in points]
                    if (len(set(times)) == len(times) and all(start.timestamp() <= t <= end.timestamp() for t in times)
                            and all(type(v) in {int, float} and math.isfinite(v) and 0 <= v <= 100 for v in values)):
                        metrics = {"cpu_mean_percent": sum(values) / len(values), "sample_count": len(values),
                                   "requested_period_seconds": 900, "sample_span_seconds": max(times) - min(times),
                                   "coverage": "available-samples-only"}
                except (ValueError, KeyError, TypeError, OverflowError):
                    pass
    add("metrics", "passed" if metrics else "unknown", "Allow scoped Monitoring reads; absent samples do not mean zero utilization.")
    return {"status": "failed" if any(c["status"] == "failed" for c in checks) else "unknown" if any(c["status"] == "unknown" for c in checks) else "passed",
            "checks": checks, "image_identity_verified": image_verified, "observed_image_digest": digest if image_verified else None,
            "metrics": metrics, "receipt_resource_count": len(receipt["resources"]), "raw_logs_collected": False}


def costs(config, private, call, resource_ids):
    """Optional bounded Usage API read. Empty/partial/currency-mixed data stays unknown."""
    expected = {"tenant_id", "period_start_utc", "period_end_utc"}
    if set(private) != expected or not re.fullmatch(r"ocid1\.tenancy\.[a-z0-9.-]{10,240}", private.get("tenant_id", "")):
        raise ValueError("Invalid private billing choices.")
    start, end = timestamp(private["period_start_utc"]), timestamp(private["period_end_utc"])
    if not 0 < end - start <= 31 * 86400 or end > time.time() or any(value % 86400 for value in (start, end)):
        raise ValueError("Billing period must be UTC midnight boundaries, at most 31 completed days.")
    target = config["target"]
    if (not isinstance(resource_ids, list) or not 1 <= len(resource_ids) <= 100 or len(set(resource_ids)) != len(resource_ids)
            or any(not isinstance(identifier, str) or not re.fullmatch(r"ocid1\.[a-z0-9]+\.[a-z0-9.-]{10,240}", identifier) for identifier in resource_ids)):
        raise ValueError("Select a bounded exact resource inventory for cost collection.")
    result = {"status": "unknown", "reported_amount": None, "currency": None,
              "period_start_utc": private["period_start_utc"], "period_end_utc": private["period_end_utc"],
              "basis": "Usage API; reporting can lag and does not establish the final invoice or a spending cap."}
    dimensions = [{"key": "compartmentId", "value": target["compartment_id"]}, {"key": "region", "value": target["region"]}]
    try:
        value = call(["usage-api", "usage-summary", "request-summarized-usages", "--tenant-id", private["tenant_id"],
            "--granularity", "DAILY", "--query-type", "COST", "--limit", "500", "--is-aggregate-by-time", "false",
            "--time-usage-started", private["period_start_utc"],
            "--time-usage-ended", private["period_end_utc"], "--group-by", '["compartmentId","region","resourceId"]',
            "--filter", json.dumps({"operator": "AND", "dimensions": dimensions, "filters": [{"operator": "OR", "dimensions": [{"key": "resourceId", "value": identifier} for identifier in resource_ids]}]}, separators=(",", ":"))])
        rows = value["data"]["items"]
        if value.get("opc-next-page") or not isinstance(rows, list) or not 1 <= len(rows) <= 500:
            return result
        amounts, currencies, coverage = [], set(), set()
        for row in rows:
            amount = row.get("computed-amount")
            if (row.get("compartment-id") != target["compartment_id"] or row.get("region") != target["region"]
                    or row.get("is-forecast") is True or row.get("tenant-id", private["tenant_id"]) != private["tenant_id"]
                    or row.get("resource-id") not in resource_ids or type(amount) not in {int, float}
                    or not math.isfinite(amount) or abs(amount) > 10 ** 12
                    or not isinstance(row.get("currency"), str) or not re.fullmatch(r"[A-Z]{3}", row["currency"])
                    or not start <= timestamp(row["time-usage-started"]) < timestamp(row["time-usage-ended"]) <= end):
                return result
            interval_start, interval_end = timestamp(row["time-usage-started"]), timestamp(row["time-usage-ended"])
            pair = (row["resource-id"], interval_start)
            if interval_start % 86400 or interval_end - interval_start != 86400 or pair in coverage:
                return result
            coverage.add(pair)
            currencies.add(row["currency"]); amounts.append(amount)
        expected_coverage = {(identifier, day) for identifier in resource_ids for day in range(int(start), int(end), 86400)}
        if len(currencies) == 1 and coverage == expected_coverage:
            result.update(status="reported", reported_amount=sum(amounts), currency=currencies.pop())
    except Exception:
        pass
    return result


def request(project, *, environment, live=False, receipt=None, config_file=Path("~/.oci/config"), cost_config=None, component="web", client=None):
    common, p = modules()
    common.select(project, environment, required=True)
    if not live:
        return p.helper("dashboard").render(project, environment=environment)
    with p.Store(project, environment=environment, write=True) as store:
        store.read()
        initial = common.bound(store, p, SCHEMA)
        config = role_config(store, p, component)
        selected, receipt_hash = receipt_at(store, p, receipt, component=component)
        call = client if client is not None else Client(p, config["target"], config_file)
        value = collect(config, selected, call)
        if cost_config is not None:
            identifiers = [r["id"] for r in selected["resources"] if r.get("type") in RESOURCE_TYPES]
            value["costs"] = costs(config, common.private_json(cost_config), call, identifiers)
        if isinstance(call, Client):
            call.check()
        if common.bound(store, p, SCHEMA) != initial or receipt_at(store, p, receipt, component=component)[1] != receipt_hash:
            raise ValueError("Source, target or receipt changed during observation.")
        value.update(initial, observed_at=int(time.time()), receipt_sha256=receipt_hash, component_role=component, mode="live-read-only" if client is None else "injected-test-client",
                     production_ready=False, scope="Bound resource metadata only; application behavior, effective IAM, recovery and final billing need separate evidence.")
        value["evidence"] = p.save_report(store, value, "observe")
        return value
