#!/usr/bin/env python3
"""Read-only coverage of the selected founder journey; never an approval source."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-founder-journey/1"


def project_module():
    spec = importlib.util.spec_from_file_location("oci_journey_project", ROOT / "scripts/project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(environment, *arguments):
    # Commands are run from the selected application root. Never print private paths.
    return ["python3", ".oci-founder-kit/scripts/kit.py", *arguments,
            "--project", ".", "--environment", environment]


def runtime_status(value, config, p):
    """A report can describe HTTPS behavior; it cannot prove hosted identity."""
    if (not config["target"].get("image_digest") or not config["target"].get("origin")
            or value.get("selected_image_digest") != config["target"].get("image_digest")):
        return "invalid"
    if value.get("schema") == "oci-runtime-probe/1":
        rows = value.get("checks")
        if (value.get("scope") != "selected-https-origin" or value.get("read_only") is not True
                or not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or rows[0].get("id") != "https_health"
                or rows[0].get("status") != value.get("status")):
            return "invalid"
    else:
        expected = {"health", "readiness", "production-signed-out-session", "unsigned-api-denied", "authenticated-exercise"}
        rows = value.get("checks")
        if (value.get("scope") != "anonymous-read-checks"
                or value.get("runner_sha256") != p.digest((ROOT / "blueprints/fullstack-container/production_check.py").read_bytes())
                or value.get("target_origin_sha256") != hashlib.sha256(config["target"].get("origin", "").encode()).hexdigest()
                or not isinstance(rows, list) or len(rows) != len(expected)
                or any(not isinstance(row, dict) for row in rows)
                or {row.get("check") for row in rows} != expected
                or any(row.get("status") not in {"passed", "failed", "unknown", "skipped"} for row in rows)):
            return "invalid"
        states = {row["check"]: row["status"] for row in rows}
        if states["authenticated-exercise"] != "skipped":
            return "invalid"
        expected_status = "failed" if "failed" in states.values() else "unknown" if "unknown" in states.values() else "passed"
        if value.get("status") != expected_status:
            return "invalid"
    return {"passed": "reported", "failed": "failed", "unknown": "unknown"}.get(value.get("status"), "invalid")


def request(project: Path, *, environment: str, journey="build"):
    if not environment or journey not in {"build", "migrate"}:
        raise ValueError("Select an explicit named target and a supported journey.")
    p = project_module()
    common, architecture = p.helper("kit_common"), p.helper("architecture")
    with p.Store(project, environment=environment) as store:
        state = store.read()
        config = store.environment_config
        if config["role"] == "source" or journey == "migrate" and state["task"] != "migrate":
            raise ValueError("Select an OCI target with the matching migration workflow.")
        initial = common.bound(store, p, SCHEMA)
        progress, _, _ = p.report(store, state)
        selected, states, counts = architecture.reports(store, p, common)
        try:
            dashboard = p.helper("dashboard").view(store, p)
        except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError):
            # Malformed private evidence must not hide the remaining acceptance gaps.
            dashboard = {"observations": {}}
            counts["unreadable"] += 1
        gates = []

        def add(identifier, status, owner, instruction, *arguments, evidence_class="not-collected"):
            gates.append({"id": identifier, "status": status, "owner": owner,
                          "evidence_class": evidence_class, "next_action": instruction,
                          "recheck_command": command(environment, *arguments) if arguments else None})

        local = next((row["status"] for row in progress["steps"] if row["id"] == "local-workflow"), "not-recorded")
        add("local_application", {"owner-recorded": "owner-recorded", "stale": "stale"}.get(local, "missing"), "agent",
            "Demonstrate the application's primary user workflow and preserve its source; retain actual commands and outcomes privately.",
            "status", evidence_class="owner-recorded" if local == "owner-recorded" else "not-collected")
        foundation = p.helper("foundation").inspect(store, p)
        add("foundation_configuration", "configured" if foundation["status"] == "configured" else "missing", "administrator",
            "Resolve the selected foundation's missing choices; configuration does not establish effective IAM or deployed resources.",
            "foundation", "inspect", evidence_class="local-configuration")

        ready_schema = "oci-workload-readiness/1"
        readiness = selected.get(ready_schema, {})
        access = readiness.get("access")
        access_state = states.get(ready_schema, "missing")
        if access_state == "current":
            access_state = "unknown"
            if readiness.get("mode") == "live-read-only" and isinstance(access, dict):
                rows = architecture.check_rows(access)
                if access.get("schema") != "oci-readiness/1" or access.get("mode") != "live-read-only" or rows is None:
                    access_state = "invalid"
                elif "blocked" in rows.values():
                    access_state = "failed"
                elif access.get("status") == "passed" and all(rows.get(key) == "passed" for key in ("region_subscription", "compartment_access")):
                    access_state = "reported"
        add("operator_read_access", access_state, "administrator",
            "Run the selected profile's bounded read checks; successful reads do not grant deployment or state-write permissions.",
            "doctor", "--live", evidence_class="live-read-only-report" if access_state == "reported" else "not-collected")

        operating_schema = "oci-operating-observation/1/web"
        operating = dashboard["observations"].get(operating_schema, {})
        operation_state = states.get(operating_schema, "missing")
        if operation_state == "current":
            operation_state = "unknown"
            if (operating.get("mode") == "live-read-only"
                    and operating.get("observed_at") == selected[operating_schema].get("observed_at")):
                checks = {row["id"]: row["status"] for row in operating.get("checks", [])}
                if checks.get("image_identity") == "failed":
                    operation_state = "failed"
                elif operating.get("image_identity_verified") is True:
                    operation_state = "observed"
        add("deployed_image", operation_state, "agent",
            "Read back the exact deployed digest using the latest bound deployment receipt; inspect partial attempts before any new plan.",
            "observe", "--live", evidence_class="live-read-only-report" if operation_state == "observed" else "not-collected")

        runtime_schema = "oci-production-check/1" if config["blueprint"] == "fullstack-container" else "oci-runtime-probe/1"
        runtime_state = states.get(runtime_schema, "missing")
        if runtime_state == "current":
            runtime_state = runtime_status(selected[runtime_schema], config, p)
        add("https_application", runtime_state, "agent",
            "Run current HTTPS behavior checks. A health response alone does not prove hosted sign-in, data durability or OCI image identity.",
            "verify", "--kind", "runtime", evidence_class="bound-https-report" if runtime_state == "reported" else "not-collected")

        manual = (
            ("effective_iam_isolation", "administrator", "Verify intended operator/runtime access and denial across unrelated environments, including state; readable metadata is insufficient."),
            ("hosted_sign_in", "agent", "Complete real hosted login, callback, logout and expiry against the deployed app with synthetic accounts."),
            ("two_user_isolation", "agent", "Prove one synthetic user cannot read or mutate another user's private application data and attachments."),
            ("durable_persistence", "agent", "Verify accepted application data survives an approved workload restart; retain database and storage dependencies."),
            ("isolated_restore", "owner", "Approve an exact isolated recovery plan, restore representative data and verify application workflows without touching production."),
            ("image_rollback", "owner", "Review the previous accepted digest, approve its new exact rollback plan and verify actual application behavior afterward."),
            ("retained_resources_and_costs", "owner", "Review retained resources and dated costs after the trial; approve each cleanup plan separately and verify its outcome."),
        )
        for identifier, owner, instruction in manual:
            add(identifier, "missing", owner, instruction, evidence_class="manual-review-required")

        if journey == "migrate":
            schema = "oci-migration-parity/1"
            parity = states.get(schema, "missing")
            if parity == "current":
                parity = architecture.parity_status(selected[schema], config, p)
            add("hosting_parity", parity, "agent",
                "Review the exact private migration contract and source-versus-target report; bounded HTTP parity does not cover browser workflows or authorize cutover.",
                "verify", "--help", evidence_class="bound-https-report" if parity == "reported" else "not-collected")
            for identifier, instruction in (
                ("browser_workflows", "Verify navigation, hydration, cookies, redirects, uploads, streaming and cache behavior for meaningful user workflows."),
                ("retained_services", "Verify OCI connectivity, TLS, callback origins and measured latency to the retained database, authentication and storage providers."),
                ("background_work_ownership", "Prove target workers and schedulers remain disabled until a separately reviewed ownership transfer; prevent duplicate effects."),
                ("traffic_rollback", "Rehearse restoring traffic to the preserved source through a separate exact reviewed plan; keep data migration outside hosting acceptance."),
            ):
                add(identifier, "missing", "owner" if identifier == "traffic_rollback" else "agent", instruction,
                    evidence_class="manual-review-required")

        if common.bound(store, p, SCHEMA) != initial:
            raise ValueError("Source or target changed while reading evidence; repeat the report.")
        blocking = {"missing", "failed", "unknown", "stale", "ambiguous", "invalid"}
        next_gate = next(row for row in gates if row["status"] in blocking)
        return {"schema": SCHEMA, "environment": environment, "journey": journey,
                "status": "failed" if any(row["status"] == "failed" for row in gates) else "incomplete",
                "gates": gates, "next_action": next_gate, "evidence_counts": counts,
                "handoff_rules": [
                    "Review and approve each exact cloud plan BEFORE its write: foundation/IAM, image upload, backend initialization or locking, resource apply, synthetic app writes, traffic changes and cleanup are separate operations.",
                    "Image publication is a cloud write. Terraform apply is not the first cloud write when publication or remote-state operations happen earlier.",
                    "These application templates use Linux AMD64 images on CI.Standard.E4.Flex. Do not offer Ampere/ARM64 as an available path; capacity remains unknown until verified.",
                    "Use the returned architecture control_counts and actual check outcomes in the handoff; do not guess counts or claim a complete live journey.",
                    "Browser-based temporary sessions and API signing keys are supported operator choices; API-key registration is not universally required."],
                "journey_accepted": False, "approval_granted": False, "network_requests": 0,
                "agent_evidence": {"restricted_local_harness": "not-established-by-this-report",
                                   "ordinary_agent_session": "not-established-by-this-report",
                                   "approved_live_oci_journey": "incomplete"},
                "scope": "Read-only coverage from private local reports. Reported checks and owner records are not authenticated end-to-end proof. Unimplemented acceptance contracts remain explicit manual gates; no cloud action or evidence write occurs."}


def render(value):
    print("Founder journey: " + value["journey"] + " · " + value["environment"] + " · " + value["status"])
    for row in value["gates"]:
        print(row["id"] + ": " + row["status"] + " · " + row["evidence_class"])
    next_gate = value["next_action"]
    print("Next: " + next_gate["next_action"])
    if next_gate["recheck_command"]:
        print("Recheck: " + shlex.join(next_gate["recheck_command"]))
    for rule in value["handoff_rules"]:
        print("Handoff: " + rule)
    print(value["scope"])
