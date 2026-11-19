"""Read-only, private Well-Architected evidence review for one explicit environment.

The report projects existing bound evidence. It does not collect cloud data,
authenticate local reports, certify a workload or authorize an operation.
"""
from __future__ import annotations

import importlib.util
import datetime as dt
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-kit-architecture/1"
FRESH_SECONDS = 86400
READINESS = "oci-workload-readiness/1"
OPERATING = "oci-operating-observation/1"
SCHEMAS = {READINESS, OPERATING, "oci-runtime-probe/1", "oci-production-check/1",
           "oci-migration-parity/1", "oci-operating-costs/1"}
SOURCE = "https://docs.oracle.com/en/solutions/oci-best-practices/index.html"


def modules():
    spec = importlib.util.spec_from_file_location("oci_architecture_common", ROOT / "scripts/kit_common.py")
    common = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(common)
        return common, common.project_module()
    finally:
        sys.dont_write_bytecode = previous


def reports(store, p, common):
    """Select unique newest reports; malformed/newer evidence cannot revive a pass.

    Returned report dictionaries are private input, not an output projection.
    Callers validate the selected schema's content before interpreting it.
    """
    binding = common.bound(store, p, "unused")
    now = int(time.time())
    names = os.listdir(store.evidence_fd)
    if len(names) > 200:
        raise ValueError("Evidence exceeds the bounded review inventory.")
    grouped = {}
    states = {schema: "missing" for schema in SCHEMAS if schema != OPERATING}
    states.update({OPERATING + "/" + role: "missing" for role in ("web", "worker")})
    counts = {"stale": 0, "unreadable": 0, "ambiguous": 0, "discarded": 0}
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        try:
            value = p.object_at(store.evidence_fd, name, private=True)
        except (ValueError, OSError, UnicodeError, RecursionError):
            counts["unreadable"] += 1
            continue
        schema = value.get("schema")
        if not isinstance(schema, str) or schema not in SCHEMAS:
            continue
        selection = schema
        if schema == OPERATING:
            role = value.get("component_role")
            if role not in ("web", "worker"):
                counts["unreadable"] += 1
                continue
            selection += "/" + role
        if any(value.get(key) != wanted for key, wanted in binding.items() if key != "schema"):
            counts["stale"] += 1
            if states[selection] == "missing":
                states[selection] = "stale"
            continue
        observed = value.get("observed_at")
        if type(observed) is not int:
            states[selection] = "invalid"
            counts["unreadable"] += 1
            continue
        grouped.setdefault(selection, []).append(value)
    selected = {}
    for selection, candidates in grouped.items():
        # An undatable report for this binding makes chronology uncertain.
        if states[selection] == "invalid":
            continue
        latest = max(value["observed_at"] for value in candidates)
        newest = [value for value in candidates if value["observed_at"] == latest]
        counts["discarded"] += len(candidates) - len(newest)
        if len(newest) != 1:
            states[selection] = "ambiguous"
            counts["ambiguous"] += len(newest)
        elif not 0 <= now - latest <= FRESH_SECONDS:
            states[selection] = "stale"
            counts["stale"] += 1
        else:
            states[selection] = "current"
            selected[selection] = newest[0]
    return selected, states, counts


def check_rows(value, *, field="check", statuses=("passed", "blocked", "unknown")):
    """Reject duplicate or malformed checks instead of selecting a convenient row."""
    rows = value.get("checks")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        return None
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get(field), str)
                or len(row[field]) > 100 or row[field] in result or row.get("status") not in statuses):
            return None
        result[row[field]] = row["status"]
    return result


def reference(value, p, *, mode):
    return {"schema": value["schema"], "sha256": p.digest(p.canonical(value)),
            "observed_at": value["observed_at"], "age_seconds": max(0, int(time.time()) - value["observed_at"]),
            "mode": mode}


def parity_status(value, config, p):
    """Validate the existing project.verify envelope, never its unprovided contract."""
    target, rows = config["target"], value.get("checks")
    if (value.get("scope") != "selected-https-origins" or value.get("read_only") is not True
            or value.get("runner_sha256") != p.digest((ROOT / "scripts/migration.py").read_bytes())
            or not target.get("image_digest") or not target.get("origin")
            or value.get("selected_image_digest") != target["image_digest"]
            or value.get("target_image_digest") != target["image_digest"]
            or value.get("target_origin_sha256") != p.digest(target["origin"].encode())
            or value.get("source_revision_sha256") != value.get("source_sha256")
            or not p.valid_hash(value.get("contract_sha256"))
            or not p.valid_hash(value.get("source_origin_sha256"))
            or not isinstance(value.get("run_id"), str) or not re.fullmatch(r"[0-9a-f]{24}", value["run_id"])
            or not isinstance(rows, list) or not 1 <= len(rows) <= 16
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                   or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", row["id"])
                   or any(row.get(side) not in ("passed", "failed", "unknown") for side in ("source", "target", "parity")) for row in rows)
            or len({row["id"] for row in rows}) != len(rows)):
        return "invalid"
    try:
        dates = [dt.datetime.fromisoformat(value[key].replace("Z", "+00:00")) for key in ("started_at_utc", "finished_at_utc")]
        observed = value["observed_at"]
        if (type(observed) is not int or any(date.tzinfo is None for date in dates)
                or not 0 <= dates[1].timestamp() - dates[0].timestamp() <= FRESH_SECONDS
                or not 0 <= observed + 1 - dates[1].timestamp() <= FRESH_SECONDS
                or not 0 <= time.time() - dates[1].timestamp() <= FRESH_SECONDS):
            return "invalid"
    except (TypeError, AttributeError, ValueError, KeyError, OverflowError):
        return "invalid"
    if value.get("interrupted") is not False or value.get("contract_expired_during_run") is not False:
        return "unknown"
    if value.get("status") == "passed":
        return "reported" if all(all(row[side] == "passed" for side in ("source", "target", "parity")) for row in rows) else "invalid"
    if value.get("status") == "failed":
        return "failed" if any(row["parity"] == "failed" for row in rows) else "invalid"
    return "unknown" if value.get("status") == "unknown" else "invalid"


def review(store, p, common):
    state = store.read()
    selected, states, counts = reports(store, p, common)
    try:
        dashboard = p.helper("dashboard").view(store, p)
    except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError):
        # One unrecognized private report must not leak input or create success.
        dashboard = {"observations": {}, "backup_and_rollback_evidence": "unknown"}
        counts["unreadable"] += 1
    target = store.environment_config["target"]
    environment = store.environment
    doctor = selected.get(READINESS)
    rows = None
    if (doctor and doctor.get("mode") in ("offline", "live-read-only")
            and doctor.get("status") in ("passed", "blocked", "incomplete", "unknown")):
        rows = check_rows(doctor)
    if doctor and rows is None:
        states[READINESS] = "invalid"
    observation = selected.get(OPERATING + "/web")
    # The dashboard independently checks the latest deployment receipt, resource
    # binding, image and complete operation-check vocabulary before projection.
    operating = dashboard["observations"].get(OPERATING + "/web") if observation else None
    if operating and operating["observed_at"] != observation["observed_at"]:
        operating = None
    if observation and not operating:
        states[OPERATING + "/web"] = "stale"
    live = operating is not None and operating["mode"] == "live-read-only"
    controls = []

    def add(pillar, name, status, owner, instruction, *, evidence=None, scope=None, command="doctor", arguments=()):
        controls.append({"pillar": pillar, "id": name, "status": status, "owner": owner,
                         "instruction": instruction, "scope": scope or "This selected control only; broader acceptance remains separate.",
                         "evidence": evidence or [],
                         "recheck_command": ["python3", ".oci-founder-kit/scripts/kit.py", command,
                                             *arguments, "--project", ".", "--environment", environment]})

    def missing(selection):
        return "stale" if states[selection] == "stale" else "unknown"

    def prerequisite(pillar, name, check, owner, instruction):
        result = rows.get(check, "unknown") if rows is not None else "unknown"
        status = "failed" if result == "blocked" else "observed" if result == "passed" and doctor["mode"] == "live-read-only" else "unknown"
        if rows is None:
            status = missing(READINESS)
        evidence = [reference(doctor, p, mode=doctor["mode"])] if rows is not None else []
        add(pillar, name, status, owner, instruction, evidence=evidence, arguments=("--live",),
            scope="Current selected-resource metadata check; not a complete access or network audit.")

    def observed(pillar, name, check, owner, instruction):
        verdict = next((c["status"] for c in operating["checks"] if c["id"] == check), "unknown") if operating else "unknown"
        status = "failed" if verdict == "failed" and live else "observed" if verdict == "passed" and live else missing(OPERATING + "/web")
        evidence = [reference(observation, p, mode=operating["mode"])] if operating else []
        add(pillar, name, status, owner, instruction, evidence=evidence, command="observe", arguments=("--live",))

    prerequisite("security", "private_application_subnet", "app_subnet_id", "administrator",
                 "Verify the selected app subnet forbids public IPs and belongs to the selected VCN; review routes and NSGs separately.")
    prerequisite("security", "private_registry", "registry", "administrator",
                 "Read the selected repository privacy setting and review its pull/push policies separately.")
    observed("security", "certificate_validity", "certificate_expiry", "application-owner",
             "Check the selected certificate validity and renewal responsibility; separately test hostname, chain and public HTTPS behavior.")
    add("security", "effective_iam_and_state_isolation", "unknown", "administrator",
        "Review inherited allow/deny policies and demonstrate permitted and denied state/workload operations with separate identities.",
        scope="Readable resources, distinct compartments and saved policies do not prove effective authorization.")
    add("security", "hosted_identity_and_two_user_isolation", "unknown", "application-owner",
        "Complete hosted sign-in and two-user isolation checks on the actual deployment with privately held sessions.",
        scope="Anonymous health checks and owner records do not establish hosted authentication or authorization.", command="verify")

    observed("reliability", "container_health", "container_instance", "agent",
             "Inspect the selected instance state and latest deployment attempt before preparing any retry.")
    observed("reliability", "load_balancer_health", "load_balancer", "agent",
             "Inspect selected backend health and verify application behavior before accepting deployment.")
    recovery = dashboard["backup_and_rollback_evidence"]
    add("reliability", "isolated_restore_and_rollback", "owner-recorded" if recovery == "owner-recorded" else "stale" if recovery == "stale" else "unknown",
        "application-owner", "Demonstrate isolated data restoration and rollback to the accepted image; retain private results and resource cleanup evidence.",
        scope="A recovery checkpoint is an owner record, not independently verified recovery.", command="status")
    add("reliability", "capacity_and_redundancy", "unknown", "application-owner",
        "Review interruption tolerance and actual capacity. Quota availability does not establish capacity or high availability.",
        scope="The default single-instance topology has an interruption window; no redundancy or availability guarantee is inferred.")

    add("performance-cost", "compute_sizing", "configured" if {"ocpus", "memory_gbs"}.issubset(target) else "unknown", "application-owner",
        "Compare selected sizing against representative workload measurements and workload-specific performance targets.",
        scope="Configured sizing is not measured throughput, latency or headroom.")
    observed("performance-cost", "utilization_observation", "metrics", "application-owner",
             "Review workload metrics and run representative performance tests before changing sizing.")
    billing = operating.get("costs") if live else None
    owner_costs = dashboard["observations"].get("oci-operating-costs/1") if selected.get("oci-operating-costs/1") else None
    cost_status = "observed" if billing else "owner-recorded" if owner_costs else "unknown"
    cost_evidence = [reference(observation, p, mode="live-read-only")] if billing else []
    add("performance-cost", "reported_usage_cost", cost_status, "founder",
        "Collect scoped Usage API evidence and review reporting lag, migration overlap and retained resources privately.", evidence=cost_evidence,
        scope="Missing billing access is unknown, never zero. Reported usage is not a final invoice or spending cap.", command="observe", arguments=("--live",))

    observed("operations", "deployed_image_identity", "image_identity", "agent",
             "Read back the exact deployed image digest and compare it with the reviewed environment and current deployment receipt.")
    # An image check saying passed is insufficient without the exact readback guard.
    if controls[-1]["status"] == "observed" and not operating["image_identity_verified"]:
        controls[-1]["status"] = "unknown"
    observed("operations", "recent_deployment_failures", "recent_work_requests", "agent",
             "Review recent selected-resource work requests; prepare any repair as a new exact plan.")
    add("operations", "environment_binding", "configured", "founder",
        "Keep rehearsal and production explicit, preserve private backups and obtain fresh exact-plan approval for each cloud change.",
        scope="The selected configuration is valid locally; it grants no cloud authorization.", command="status")

    prerequisite("distributed-cloud", "external_dependency_connectivity", "network_egress", "application-owner",
                 "Verify TLS, DNS, callbacks and meaningful database/storage/identity workflows from the actual OCI target.")
    add("distributed-cloud", "background_work_ownership", "unknown", "application-owner",
        "Prove which environment owns each scheduler and worker before a separately reviewed ownership transfer.",
        scope="A saved preference cannot prove that jobs are disabled at the retained source or target.")
    parity = selected.get("oci-migration-parity/1")
    parity_state = "not-applicable" if state["task"] != "migrate" else missing("oci-migration-parity/1")
    parity_evidence = []
    if state["task"] == "migrate" and parity:
        result = parity_status(parity, store.environment_config, p)
        parity_state = {"reported": "tested", "failed": "failed"}.get(result, "unknown")
        if result != "invalid":
            parity_evidence = [reference(parity, p, mode=parity["scope"])]
    add("distributed-cloud", "hosting_migration_parity", parity_state, "application-owner",
        "Review source-versus-target browser and HTTP workflows, external providers and traffic rollback before cutover.", evidence=parity_evidence,
        scope="Selected parity checks do not establish deployed image identity, all browser behavior or traffic-cutover acceptance.",
        command="verify", arguments=("--kind", "migration"))

    pillars = [("security", "Security and compliance"), ("reliability", "Reliability and resilience"),
               ("performance-cost", "Performance and cost optimization"), ("operations", "Operational efficiency"),
               ("distributed-cloud", "Distributed cloud")]
    return {"schema": SCHEMA, "status": "failed" if any(c["status"] == "failed" for c in controls) else "incomplete",
            "environment": environment, "generated_at": int(time.time()), "framework_source": SOURCE,
            "framework_checked_date": "2026-11-19", "read_only": True, "cloud_requests": False,
            "approval_granted": False, "certified": False, "production_ready": False,
            "control_counts": {status: sum(c["status"] == status for c in controls) for status in sorted({c["status"] for c in controls})},
            "pillars": [{"id": key, "title": title, "controls": [{k: v for k, v in row.items() if k != "pillar"}
                          for row in controls if row["pillar"] == key]} for key, title in pillars],
            "evidence_review": counts, "scope": "Selected existing private reports, not a complete Well-Architected audit. Reports are locally held and not authenticated attestations. Observed means a narrow recorded live read; configured, tested and owner-recorded are separate evidence levels. No score or certification is assigned."}


def request(project, *, environment):
    if not environment:
        raise ValueError("Select an explicit OCI target environment.")
    common, p = modules()
    with p.Store(project, environment=environment) as store:
        if store.environment_config["role"] == "source":
            raise ValueError("Select an OCI rehearsal or production environment.")
        initial = common.bound(store, p, SCHEMA)
        result = review(store, p, common)
        if initial != common.bound(store, p, SCHEMA):
            raise ValueError("Source or toolkit changed during architecture review; repeat the read-only review.")
        result["binding"] = {key: initial[key] for key in ("target_sha256", "source_sha256", "kit_sha256")}
        return result
