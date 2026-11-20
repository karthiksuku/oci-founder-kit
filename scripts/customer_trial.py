"""Prepare one private tester handoff for a named, observed OCI rehearsal."""
from __future__ import annotations

import os
import time
import uuid

PREPARE_CHECKS = {"synthetic_data_only", "tester_completed_sign_in", "anonymous_denied",
                  "uninvited_account_denied", "access_expiry_configured", "session_revocation_rehearsed"}
CLOSE_CHECKS = {"assignment_removed", "existing_session_denied", "fresh_sign_in_denied"}


def sample_text(value, limit=400):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and value.isprintable()


def reviewed(input_data, checks, now):
    flags = input_data.get("checks")
    timestamp = input_data.get("observed_at")
    return (isinstance(flags, dict) and set(flags) == checks and all(v is True for v in flags.values())
            and type(timestamp) is int and 0 <= now - timestamp <= 86400)


def persist(store, p, name, data):
    """Publish complete private JSON under the existing per-project exclusive lock."""
    raw = p.canonical(data) + b"\n"
    try:
        if p.read_at(store.fd, name, private=True) != raw:
            raise ValueError("This trial record already exists with different contents.")
    except FileNotFoundError:
        temporary = ".trial-" + uuid.uuid4().hex
        try:
            p.helper("environments").put(store.fd, temporary, raw)
            os.rename(temporary, name, src_dir_fd=store.fd, dst_dir_fd=store.fd)
            os.fsync(store.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=store.fd)
            except FileNotFoundError:
                pass


def candidate(store, p):
    common = p.helper("kit_common")
    schema = "oci-operating-observation/1/web"
    selected, states, counts = p.helper("architecture").reports(store, p, common)
    observation = p.helper("dashboard").view(store, p)["observations"].get(schema, {})
    target = store.environment_config["target"]
    if (not target.get("origin") or counts["unreadable"] or states[schema] != "current"
            or observation.get("mode") != "live-read-only"
            or any(row["status"] == "failed" for row in observation.get("checks", [])
                   if row["id"] in ("container_instance", "load_balancer", "certificate_expiry"))
            or observation.get("image_identity_verified") is not True
            or observation.get("observed_at") != selected[schema].get("observed_at")):
        return None
    _, receipt = p.helper("operations").receipt_at(store, p)
    return {**common.bound(store, p, "oci-customer-trial-binding/1"),
            "receipt_sha256": receipt, "image_digest": target["image_digest"]}


def request(project, *, action, environment, trial_id, input_file, p):
    now = int(time.time())
    if (action in {"inspect", "prepare"}) != (trial_id is None):
        raise ValueError("Select a single trial by its identifier for feedback or closure.")
    if trial_id is not None and not p.valid_hash(trial_id):
        raise ValueError("Invalid trial identifier.")
    if (action in {"prepare", "feedback", "close"}) != (input_file is not None):
        raise ValueError("Select the appropriate private trial input.")
    data = p.helper("kit_common").private_json(input_file) if input_file else {}
    with p.Store(project, environment=environment, write=action != "inspect") as store:
        if store.environment_config["role"] != "rehearsal":
            raise ValueError("Only a named rehearsal can host a customer trial.")
        report = {"schema": "oci-customer-trial/1", "environment": environment,
                  "sent": False, "cloud_calls": 0, "production_approval": False}
        if action in {"inspect", "prepare"}:
            binding = candidate(store, p)
            if not binding:
                return {**report, "status": "incomplete", "next_action":
                        "Run observe --live for this rehearsal and obtain a current passing readback of the deployed image."}
            challenge = p.digest(p.canonical(binding))
            if action == "inspect":
                return {**report, "status": "needs-access-review", "candidate_sha256": challenge,
                        "required_owner_checks": sorted(PREPARE_CHECKS),
                        "next_action": "Configure access at the app identity provider. Test the controls in docs/CUSTOMER-TRIAL.md."}
            if (set(data) != {"candidate_sha256", "task", "expires_at", "observed_at", "checks"}
                    or data["candidate_sha256"] != challenge or not reviewed(data, PREPARE_CHECKS, now)
                    or not sample_text(data["task"]) or type(data["expires_at"]) is not int
                    or not now < data["expires_at"] <= data["observed_at"] + 7 * 86400):
                raise ValueError("Check the reviewed access, candidate, task and expiry.")
            brief = {"binding": binding, "access_evidence": "owner-recorded", "review": data,
                     "origin": store.environment_config["target"]["origin"]}
            trial_id = p.digest(p.canonical(brief))
            name = "trial-" + trial_id + ".json"
            persist(store, p, name, brief)
            try:
                p.object_at(store.fd, "closed-" + name, private=True)
            except FileNotFoundError:
                return {**report, "status": "prepared", "trial_id": trial_id,
                        "private_brief": f".oci-kit/environments/{environment}/{name}",
                        "next_action": "Share only the origin, synthetic task and expiry with the authorized tester."}
            return {**report, "status": "closed", "trial_id": trial_id}
        name = "trial-" + trial_id + ".json"
        brief = p.object_at(store.fd, name, private=True)
        if (p.digest(p.canonical(brief)) != trial_id or brief["binding"]["environment"] != environment
                or data.get("trial_id") != trial_id):
            raise ValueError("Input and recorded trial must match the named rehearsal.")
        if action == "close":
            if (set(data) != {"trial_id", "checks", "observed_at"}
                    or not reviewed(data, CLOSE_CHECKS, now)
                    or data["observed_at"] < brief["review"]["observed_at"]):
                raise ValueError("Record removal and both denial checks after revoking the test identity.")
            persist(store, p, "closed-" + name, data)
            return {**report, "status": "closed", "revocation_evidence": "owner-recorded",
                    "next_action": "Review retained resources and recurring costs before any separately approved cleanup."}
        if (set(data) != {"trial_id", "outcome", "observed", "expected", "observed_at"}
                or data["outcome"] not in ("unaided", "with-help", "blocked")
                or not all(sample_text(data[k], 700) for k in ("observed", "expected"))
                or type(data["observed_at"]) is not int
                or not brief["review"]["observed_at"] <= data["observed_at"] <= min(now, brief["review"]["expires_at"])):
            raise ValueError("Supply a de-identified observation from the trial period.")
        try:
            closure = p.object_at(store.fd, "closed-" + name, private=True)
            if data["observed_at"] > closure["observed_at"]:
                raise ValueError("Observation was recorded after the trial closed.")
        except FileNotFoundError:
            pass
        # This is a retrospective tester observation. The URL may have been
        # redeployed since the task was performed. Never infer that past image.
        filename = "trial-feedback-" + p.digest(p.canonical(data)) + ".json"
        try:
            regression = p.object_at(store.fd, filename, private=True)
            if regression.get("observation") != data or regression.get("intended_binding") != brief["binding"]:
                raise ValueError("Recorded feedback does not match the trial.")
        except FileNotFoundError:
            current = candidate(store, p)
            revision = "unknown"
            if current is not None:
                revision = "current-match" if current == brief["binding"] else "current-target-changed"
            regression = {"intended_binding": brief["binding"], "task": brief["review"]["task"],
                          "observation": data, "test_status": "not-run", "readback_at_recording": revision,
                          "image_during_tester_action": "unverified"}
            persist(store, p, filename, regression)
        return {**report, "status": "recorded", "outcome": data["outcome"],
                "private_regression": f".oci-kit/environments/{environment}/{filename}",
                "readback_at_recording": regression["readback_at_recording"],
                "image_during_tester_action": "unverified",
                "next_action": "Reproduce the observation locally with synthetic data and test the expected behavior."}
