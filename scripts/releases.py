"""Private append-only release observations and digest-only rollback proposals.

No cloud calls. Local target adoption does not authorize a backend operation,
Terraform apply, traffic change or destructive cleanup. Historical evidence is
retained; each rollback needs a fresh exact deploy plan and behavioral checks.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-kit-release-record/1"
PROPOSAL = "oci-kit-rollback-proposal/1"
EVIDENCE = {"oci-runtime-probe/1", "oci-migration-parity/1", "oci-production-check/1"}
IMAGE = re.compile(r"([a-z0-9.-]+\.ocir\.io/[a-z0-9_./-]+)@(sha256:[0-9a-f]{64})")


def modules():
    spec = importlib.util.spec_from_file_location("oci_releases_common", ROOT / "scripts/kit_common.py")
    common = importlib.util.module_from_spec(spec); spec.loader.exec_module(common)
    p = common.project_module()
    return common, p, p.helper("environments"), p.helper("operations")


def records(fd, p, environment):
    names = os.listdir(fd)
    if len(names) > 500:
        raise ValueError("Release ledger bound exceeded; review retained records.")
    result, previous = [], None
    for name in sorted(n for n in names if n.startswith("release-")):
        match = re.fullmatch(r"release-([0-9]{6})-([0-9a-f]{64})\.json", name)
        if not match or int(match[1]) != len(result) + 1:
            raise ValueError("Release ledger sequence changed.")
        value = p.object_at(fd, name, private=True)
        if (p.digest(p.canonical(value)) != match[2] or value.get("schema") != SCHEMA or
                value.get("environment") != environment or value.get("previous_record_sha256") != previous or
                not re.fullmatch(r"sha256:[0-9a-f]{64}", value.get("image_digest", ""))):
            raise ValueError("Release record identity changed.")
        previous = match[2]
        result.append((previous, value))
    return result


def evidence_at(store, p, selected):
    if selected is None:
        raise ValueError("Select the explicit passed runtime or migration report.")
    path = Path(selected)
    if not path.is_absolute():
        path = store.project / path
    expected = store.project / ".oci-kit/environments" / store.environment / "evidence"
    if path.parent != expected or not p.NAME.fullmatch(path.name):
        raise ValueError("Select evidence from this environment's private evidence directory.")
    return p.object_at(store.evidence_fd, path.name, private=True)


def latest_observation(store, p):
    names = os.listdir(store.evidence_fd)
    if len(names) > 500:
        raise ValueError("Evidence inspection bound exceeded.")
    items = []
    for name in names:
        if name.startswith("observe-") and name.endswith(".json"):
            if not p.NAME.fullmatch(name):
                raise ValueError("Invalid observation path.")
            value = p.object_at(store.evidence_fd, name, private=True)
            if type(value.get("observed_at")) is not int:
                raise ValueError("Invalid observation timestamp.")
            items.append(value)
    if not items:
        raise ValueError("Collect a current read-only observation first.")
    newest = max(item["observed_at"] for item in items)
    latest = [item for item in items if item["observed_at"] == newest]
    if len(latest) != 1:
        raise ValueError("Ambiguous latest observation; collect a new report.")
    return latest[0]


def acceptance(store, p, common, operations, receipt, evidence):
    _, receipt_hash = operations.receipt_at(store, p, receipt)
    observation = latest_observation(store, p)
    behavior = evidence_at(store, p, evidence)
    image = store.environment_config["target"].get("image_digest")
    if (observation.get("schema") != "oci-operating-observation/1" or not common.current(observation, store, p)
            or observation.get("mode") != "live-read-only" or observation.get("component_role", "web") != "web"
            or observation.get("image_identity_verified") is not True or observation.get("observed_image_digest") != image
            or observation.get("receipt_sha256") != receipt_hash or observation.get("status") == "failed"):
        raise ValueError("Current live image observation and deployment receipt are required.")
    if (behavior.get("schema") not in EVIDENCE or behavior.get("status") != "passed"
            or not common.current(behavior, store, p) or behavior.get("selected_image_digest") != image):
        raise ValueError("Current passed behavior evidence for the selected image is required.")
    return receipt_hash, observation, behavior


def proposal_result(store, filename, value, digest):
    base = ".oci-kit/environments/" + store.environment + "/releases/"
    return {"schema": "oci-kit-release-action/1", "status": "review-required", "action": "rollback",
            "proposal_sha256": digest, "proposal": base + filename,
            "variables": base + value["variables_file"], "expires_at": value["expires_at"],
            "cloud_write": False, "approval_granted": False,
            "next_action": "Review the private digest-only proposal, then approve its exact hash to adopt local configuration. A new cloud plan remains required."}


def request(project, *, environment, action="list", receipt=None, evidence=None, variables=None, approve=None):
    common, p, env, operations = modules()
    common.select(project, environment, required=True)
    if action not in {"list", "record", "rollback"} or (approve is not None and action != "rollback"):
        raise ValueError("Unsupported release operation.")
    adopt = None
    with p.Store(project, environment=environment, write=action != "list") as store:
        store.read()
        try:
            fd = env.private_directory(store.fd, "releases", p, create=action != "list")
        except FileNotFoundError:
            return {"schema": "oci-kit-release-list/1", "status": "passed", "environment": environment, "records": [], "cloud_write": False}
        try:
            ledger = records(fd, p, environment)
            if action == "list":
                return {"schema": "oci-kit-release-list/1", "status": "passed", "environment": environment,
                        "records": [{"record_sha256": digest, "image_digest": record["image_digest"],
                                     "recorded_at": record["observed_at"], "acceptance_scope": record["acceptance_scope"],
                                     "production_ready": False} for digest, record in ledger], "cloud_write": False}
            if store.environment_config["role"] == "source":
                raise ValueError("Select an OCI target environment.")
            current_image = store.environment_config["target"].get("image_digest")
            if action == "record":
                receipt_hash, observation, behavior = acceptance(store, p, common, operations, receipt, evidence)
                if ledger and ledger[-1][1]["receipt_sha256"] == receipt_hash:
                    raise ValueError("This deployment already has an immutable release observation.")
                value = {**common.bound(store, p, SCHEMA), "observed_at": int(time.time()),
                         "image_digest": current_image, "receipt_sha256": receipt_hash,
                         "observation_sha256": p.digest(p.canonical(observation)),
                         "behavior_sha256": p.digest(p.canonical(behavior)),
                         "behavior_schema": behavior["schema"], "acceptance_scope": {
                             "oci-runtime-probe/1": "anonymous-https-health",
                             "oci-migration-parity/1": "selected-migration-https-checks",
                             "oci-production-check/1": "selected-application-checks"}[behavior["schema"]],
                         "previous_record_sha256": ledger[-1][0] if ledger else None,
                         "previous_image_digest": ledger[-1][1]["image_digest"] if ledger else None,
                         "production_ready": False, "cloud_write": False,
                         "scope": "Bound deployment, observed image and selected behavior checks; not complete security, recovery or production acceptance."}
                digest = p.digest(p.canonical(value))
                env.put(fd, f"release-{len(ledger)+1:06d}-{digest}.json", p.canonical(value) + b"\n")
                os.fsync(fd)
                return {"schema": "oci-kit-release-action/1", "status": "passed", "action": "record",
                        "record_sha256": digest, "acceptance_scope": value["acceptance_scope"],
                        "production_ready": False, "cloud_write": False}
            if len(ledger) < 2 or ledger[-1][1]["image_digest"] != current_image:
                raise ValueError("Rollback requires the currently selected accepted image and a previous accepted release.")
            previous = next(((digest, value) for digest, value in reversed(ledger[:-1]) if value["image_digest"] != current_image), None)
            if previous is None:
                raise ValueError("No previous different accepted image exists.")
            _, receipt_hash = operations.receipt_at(store, p, receipt)
            if receipt_hash != ledger[-1][1]["receipt_sha256"]:
                raise ValueError("Review the latest deployment before rollback.")
            binding = common.bound(store, p, PROPOSAL)
            if approve is None:
                if variables is None:
                    raise ValueError("Select existing private deployment variables.")
                path = Path(variables).expanduser().absolute()
                values = common.private_json(path)
                match = IMAGE.fullmatch(values.get("app_image", ""))
                if not match or match[2] != current_image:
                    raise ValueError("Variables must select the current digest-pinned OCI image.")
                replacement = dict(values, app_image=match[1] + "@" + previous[1]["image_digest"])
                replacement_hash = p.digest(p.canonical(replacement))
                variables_file = "rollback-variables-" + replacement_hash + ".json"
                try:
                    existing = p.object_at(fd, variables_file, private=True)
                    if existing != replacement:
                        raise ValueError("Rollback variables changed.")
                except FileNotFoundError:
                    env.put(fd, variables_file, p.canonical(replacement) + b"\n")
                now = int(time.time())
                destination = "rollback-" + str(now) + "-" + replacement_hash[:16] + ".tfvars.json"
                stack = store.project / store.environment_config["infrastructure"]
                _, stack_fd = p.open_project(stack)
                try:
                    if destination in os.listdir(stack_fd):
                        raise ValueError("Rollback destination already exists; preserve it and prepare a new proposal.")
                finally:
                    os.close(stack_fd)
                value = {**binding, "observed_at": now, "expires_at": now + 3600,
                         "current_record_sha256": ledger[-1][0], "previous_record_sha256": previous[0],
                         "receipt_sha256": receipt_hash, "variables_source": str(path),
                         "variables_source_sha256": p.digest(p.canonical(values)), "variables_file": variables_file,
                         "variables_sha256": replacement_hash, "stack_variables_file": destination,
                         "infrastructure": store.environment_config["infrastructure"], "from_image_digest": current_image,
                         "to_image_digest": previous[1]["image_digest"],
                         "target": dict(store.environment_config["target"], image_digest=previous[1]["image_digest"]),
                         "local_configuration_only": True, "cloud_approval_granted": False,
                         "scope": "Only app_image digest and local environment image selection change; adoption creates the named new private stack variable file. Database compatibility, image availability and behavior require fresh verification; single-instance replacement may interrupt service."}
                digest = p.digest(p.canonical(value)); filename = "rollback-" + digest + ".json"
                env.put(fd, filename, p.canonical(value) + b"\n"); os.fsync(fd)
                return proposal_result(store, filename, value, digest)
            if not p.valid_hash(approve):
                raise ValueError("Approval must identify the exact private proposal hash.")
            value = p.object_at(fd, "rollback-" + approve + ".json", private=True)
            if (value.get("schema") != PROPOSAL or p.digest(p.canonical(value)) != approve or not common.current(value, store, p, age=3600)
                    or type(value.get("expires_at")) is not int or value["expires_at"] <= time.time()
                    or value["expires_at"] - value["observed_at"] != 3600
                    or value.get("current_record_sha256") != ledger[-1][0] or value.get("previous_record_sha256") != previous[0]
                    or value.get("receipt_sha256") != receipt_hash or value.get("from_image_digest") != current_image
                    or value.get("to_image_digest") != previous[1]["image_digest"]):
                raise ValueError("Proposal expired or source, environment, receipt or release changed.")
            original = common.private_json(Path(value["variables_source"]))
            if p.digest(p.canonical(original)) != value["variables_source_sha256"]:
                raise ValueError("Original private variables changed after review.")
            if not re.fullmatch(r"rollback-variables-[0-9a-f]{64}\.json", value["variables_file"]):
                raise ValueError("Unsafe proposal variable path.")
            replacement = p.object_at(fd, value["variables_file"], private=True)
            match = IMAGE.fullmatch(original.get("app_image", ""))
            if (not match or replacement != dict(original, app_image=match[1] + "@" + previous[1]["image_digest"])
                    or p.digest(p.canonical(replacement)) != value["variables_sha256"]
                    or value.get("target") != dict(store.environment_config["target"], image_digest=previous[1]["image_digest"])):
                raise ValueError("Only the reviewed image digest may change.")
            if (value.get("infrastructure") != store.environment_config["infrastructure"]
                    or not re.fullmatch(r"rollback-[0-9]{10}-[0-9a-f]{16}\.tfvars\.json", value.get("stack_variables_file", ""))):
                raise ValueError("Unsafe stack variable destination.")
            # Consume before adoption. Interruptions remain visible and never reuse approval.
            env.put(fd, "adoption-attempt-" + approve + ".json", p.canonical({"proposal_sha256": approve,
                    "attempted_at": int(time.time()), "cloud_write": False}) + b"\n"); os.fsync(fd)
            adopt = value
        finally:
            os.close(fd)
    expected = {key: adopt[key] for key in ("target_sha256", "source_sha256", "kit_sha256")}
    env.configure(project, name=environment, target=adopt["target"], expected_binding=expected)
    _, stack_fd = p.open_project(Path(project).expanduser().absolute() / adopt["infrastructure"])
    try:
        env.put(stack_fd, adopt["stack_variables_file"], p.canonical(replacement) + b"\n")
        os.fsync(stack_fd)
    finally:
        os.close(stack_fd)
    with p.Store(project, environment=environment, write=True) as store:
        fd = env.private_directory(store.fd, "releases", p)
        try:
            env.put(fd, "adoption-result-" + approve + ".json", p.canonical({
                **common.bound(store, p, "oci-kit-rollback-adoption/1"), "observed_at": int(time.time()),
                "proposal_sha256": approve, "local_configuration_adopted": True, "cloud_write": False}) + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
    return {"schema": "oci-kit-release-action/1", "status": "passed", "action": "rollback-local-adoption",
            "proposal_sha256": approve, "configuration_backup": True, "previous_evidence": "stale",
            "variables": ".oci-kit/environments/" + environment + "/releases/" + adopt["variables_file"],
            "stack_variables": str(Path(adopt["infrastructure"]) / adopt["stack_variables_file"]),
            "var_file": adopt["stack_variables_file"],
            "cloud_write": False, "approval_granted": False,
            "next_action": "Prepare and approve a NEW backend operation and exact deployment plan, then verify actual behavior. No cloud rollback has run."}
