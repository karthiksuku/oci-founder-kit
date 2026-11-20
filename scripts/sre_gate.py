"""Offline, fail-closed production promotion for the two reference web journeys.

Private JSON is not a trust anchor. A protected verifier signs the exact binding,
observations and raw-artifact digests. The OCI deploy gate recomputes this decision.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
POLICY = "oci-founder-production/1"
NAMESPACE = "oci-founder-production-v1"
SCHEMA = "oci-sre-attestation/1"
TRUST = Path("/etc/oci-founder-kit/sre-verifiers")
# Names are the protected verifiers' expected observations, not commands from the application.
REQUIRED = {
    "application_ci": ("build", "lint_types", "unit_boundary", "regression", "api_contract", "disposable_integration", "ui_accessibility"),
    "image_runtime": ("immutable_image", "architecture", "direct_health_200", "graceful_shutdown", "configuration_validation"),
    "browser_journey": ("hosted_login", "main_action", "reload_persistence"),
    "user_isolation": ("permitted_own_record", "denied_other_read", "denied_other_write"),
    "performance": ("bounded_load", "latency_target_met", "error_target_met"),
    "dependency_recovery": ("dependency_timeout_observed", "recovery_verified"),
    "rollback": ("previous_digest_restored", "user_workflow_verified"),
    "restore": ("isolated_target", "workflow_on_restored_data", "recovery_targets_met"),
    "hardening": ("code_security_review", "non_root_runtime", "least_privilege", "private_secrets",
                  "restricted_ingress", "tls", "private_state", "private_backups", "runtime_identity_boundary"),
    "monitoring_drill": ("alert_fired", "primary_received", "fallback_assigned", "recovery_cleared",
                        "no_data_detected", "runbook", "user_sli_instrumented"),
    "migration_parity": ("route_parity", "cookie_redirect_cache", "user_workflow_parity"),
    "traffic_return": ("source_preserved", "rehearsed_return", "source_behavior_verified"),
    "service_ownership": ("external_data_retained", "external_auth_retained", "single_job_owner"),
}
MIGRATION = ("migration_parity", "traffic_return", "service_ownership")
CONTROLS = tuple(x for x in REQUIRED if x not in MIGRATION) + ("security_scan", "oci_registry_scan")
LIMIT = 24 * 60 * 60
HEX = re.compile(r"[0-9a-f]{64}")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
SAFE = (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError, subprocess.SubprocessError)


def project_module():
    spec = importlib.util.spec_from_file_location("oci_sre_project", ROOT / "scripts/project.py")
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    return p


def profile_controls(profile):
    return CONTROLS + MIGRATION if profile == "hosting-first-nextjs" else CONTROLS


def revision(project, p):
    # Invoke no hooks, external diff, or project program. Never retain filenames or git diagnostics.
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0"}
    def git(args):
        return subprocess.run(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                               "-c", "core.untrackedCache=false", "-c", "diff.ignoreSubmodules=none",
                               "-C", str(project), *args], capture_output=True, timeout=10, check=True, env=env).stdout
    if (Path(os.fsdecode(git(["rev-parse", "--show-toplevel"]).rstrip(b"\n"))) != project
            or git(["ls-files", "--others", "--exclude-standard", "-z"])
            or git(["diff", "--cached", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "HEAD"])):
        raise ValueError("Commit the reviewed candidate in a clean project root.")
    commit = git(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        raise ValueError("Unknown revision.")
    algorithm = "sha1" if len(commit) == 40 else "sha256"
    # Compare raw tracked bytes directly. git diff/status would invoke repository-
    # configured filters on files, which is inappropriate on a production verifier.
    rows = git(["ls-tree", "-r", "-z", commit]).split(b"\0")
    if not 1 < len(rows) <= 10001 or rows[-1]:
        raise ValueError("Unsupported source tree.")
    total = 0
    private_path = p.helper("hooks").private_path
    for entry in rows[:-1]:
        meta, name = entry.split(b"\t", 1)
        mode, kind, oid = meta.split()
        rel = Path(os.fsdecode(name))
        if (mode not in {b"100644", b"100755"} or kind != b"blob" or rel.is_absolute()
                or ".." in rel.parts or private_path(rel.as_posix())):
            raise ValueError("Unsupported tracked input.")
        _, fd = p.open_project(project / rel.parent)
        try:
            data = p.read_at(fd, rel.name, maximum=16 * p.LIMIT)
            executable = bool(os.stat(rel.name, dir_fd=fd, follow_symlinks=False).st_mode & stat.S_IXUSR)
        finally:
            os.close(fd)
        total += len(data)
        if (total > 256 * p.LIMIT or executable != (mode == b"100755")
                or hashlib.new(algorithm, b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest().encode() != oid):
            raise ValueError("Tracked worktree differs from the candidate commit.")
    if git(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip() != commit:
        raise ValueError("The candidate changed during inspection.")
    return commit


def fresh(value, now, window=LIMIT):
    return type(value) is int and 0 <= now - value <= window


def digest(value):
    return hashlib.sha256(value).hexdigest()


def trusted_key(path, p):
    # Administrative configuration is independent of the application and of its CI artifacts.
    # Check every component, including directories: no symlinks or writable trust parents.
    if path.anchor != "/" or ".." in path.parts:
        raise ValueError("Invalid trust path.")
    fd = os.open("/", p.DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, p.DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("Independent administrator trust is required.")
        key_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(key_fd, "rb") as key:
            info = os.fstat(key.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0 or info.st_mode & 0o022):
                raise ValueError("Unsafe verifier key.")
            raw = key.read(1025)
    finally:
        os.close(fd)
    parts = raw.strip().split()
    if (len(raw) > 1024 or len(parts) < 2 or parts[0] != b"ssh-ed25519"
            or not re.fullmatch(rb"[A-Za-z0-9+/]{68}", parts[1]) or b"\n" in raw.rstrip(b"\n")):
        raise ValueError("Expected one Ed25519 verifier key.")
    return b" ".join(parts[:2])


def signature_valid(payload, signature, public_key):
    if len(signature) > 4096 or not signature.startswith(b"-----BEGIN SSH SIGNATURE-----\n"):
        return False
    with tempfile.TemporaryDirectory(prefix="oci-sre-verify-") as temporary:
        base = Path(temporary)
        (base / "allow").write_bytes(b"protected-verifier " + public_key + b"\n")
        (base / "signature").write_bytes(signature)
        result = subprocess.run(["/usr/bin/ssh-keygen", "-Y", "verify", "-f", str(base / "allow"),
                                 "-I", "protected-verifier", "-n", NAMESPACE, "-s", str(base / "signature")],
                                input=payload, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, timeout=5)
    return result.returncode == 0


def summary_checks(summary, proof, prod_config, p, plan_sha, now):
    saved = summary.get("project_environment") or {}
    return (summary.get("kind") == "apply" and summary.get("plan_sha256") == plan_sha
            and type(summary.get("expires_at_epoch")) in {float, int}
            and type(summary.get("created_at_epoch")) in {float, int}
            and 0 < summary["expires_at_epoch"] - summary["created_at_epoch"] <= LIMIT
            and summary["created_at_epoch"] <= now <= summary["expires_at_epoch"]
            and saved.get("role") == "production" and saved.get("environment") == prod_config["name"]
            and saved.get("component_role") == "web"
            and saved.get("configuration_sha256") == p.digest(p.canonical(prod_config))
            and proof.get("schema") == "oci-named-workload-proof/1"
            and proof.get("image_digest") == prod_config["target"].get("image_digest"))


def indicator(row, name, binding, now, p):
    if (not isinstance(row, dict) or set(row) != {"observed_at", "artifact_sha256", "observations"}
            or not fresh(row["observed_at"], now) or not p.valid_hash(row["artifact_sha256"])
            or not isinstance(row["observations"], dict)):
        return "unknown"
    data = row["observations"]
    if name in {"security_scan", "oci_registry_scan"}:
        scanner = p.helper("sre_scan")
        if name == "security_scan":
            return scanner.gate_status(data, image_digest=binding["image_digest"], now=now,
                                       source_revision=binding["source_revision"])
        return scanner.registry_status(data, image_digest=binding["image_digest"], now=now)
    expected = set(REQUIRED[name])
    if name == "restore":
        expected |= {"recovery_seconds", "data_age_seconds"}
    if set(data) != expected or any(type(data[key]) is not bool for key in REQUIRED[name]):
        return "unknown"
    if name == "restore" and any(type(data[k]) not in {int, float} or not math.isfinite(data[k]) or data[k] < 0
                                 for k in ("recovery_seconds", "data_age_seconds")):
        return "unknown"
    return "passed" if all(data[key] for key in REQUIRED[name]) else "failed"


def reports(binding, raw, signature, pub, now, p):
    if not signature_valid(raw, signature, pub):
        raise ValueError("Invalid signature.")
    value = json.loads(raw, object_pairs_hook=p.unique)
    if (not isinstance(value, dict) or set(value) != {"schema", "binding", "issued_at", "controls"}
            or value["schema"] != SCHEMA or value["binding"] != binding or not fresh(value["issued_at"], now)
            or not isinstance(value["controls"], dict) or set(value["controls"]) != set(profile_controls(binding["profile"]))):
        raise ValueError("Evidence does not match the candidate.")
    return {name: indicator(row, name, binding, now, p) if isinstance(row, dict) and type(row.get("observed_at")) is int
            and row["observed_at"] <= value["issued_at"] else "unknown" for name, row in value["controls"].items()}


def request(project, *, environment, rehearsal, plan_sha256, _applying=None):
    """Return a new projection every time. Nothing the project can write is a trust root."""
    project = Path(project).expanduser().absolute()
    p = project_module()
    result = {"schema": "oci-sre-decision/1", "status": "blocked", "policy": POLICY, "approval_granted": False,
              "checks": [], "cloud_write": False}
    def row(name, status, owner, action, observed=None):
        result["checks"].append({"id": name, "status": status, "owner": owner, "recheck": action,
                                 "age_seconds": None if observed is None else max(0, int(time.time()) - observed)})
    try:
        if not p.valid_hash(plan_sha256):
            raise ValueError("Invalid plan identity.")
        with p.Store(project, environment=environment) as prod:
            prod.read()
            env = p.helper("environments")
            configs = env.list_configs(prod, p)
            cfg = prod.environment_config
            env.validate_isolation(cfg, configs)
            if cfg["role"] != "production":
                raise ValueError("Not production.")
            name = "sre-" + plan_sha256
            raw = signature = value = None
            try:
                raw = p.read_at(prod.evidence_fd, name + ".json", private=True)
                signature = p.read_at(prod.evidence_fd, name + ".sig", private=True, maximum=4096)
                value = json.loads(raw, object_pairs_hook=p.unique)
                if rehearsal is None:  # The low-level apply has no caller-controlled rehearsal selector.
                    rehearsal = value["binding"]["rehearsal"]
            except FileNotFoundError:
                pass
            if not isinstance(rehearsal, str) or not re.fullmatch("[a-z][a-z0-9-]{0,39}", rehearsal):
                row("attestation", "unknown", "release-engineer", "Select a rehearsal and obtain protected-verifier evidence.")
                return result
            stage = next((c for c in configs if c["name"] == rehearsal and c["role"] == "rehearsal"), None)
            image = cfg["target"].get("image_digest")
            if not (stage and stage["blueprint"] == cfg["blueprint"] and isinstance(image, str) and IMAGE.fullmatch(image)
                    and stage["target"].get("image_digest") == image):
                row("rehearsal_binding", "failed", "release-engineer", "Select distinct rehearsal and production targets with the identical tested image.")
                return result
            with p.Store(project, environment=rehearsal) as staging:
                staging.read()
                # Use the exact same framework detection and safe application path as the planner.
                plan = p.helper("sre_plan").request(project, environment=rehearsal, p=p)
                profile = plan["profile"]
                if not plan["critical_journey_declared"]:
                    row("critical_journey", "unknown", "application-owner", "Declare the critical customer journey and assertions in the private rehearsal profile.")
                    return result
                if profile not in {"taskboard", "hosting-first-nextjs"}:
                    row("journey_profile", "unknown", "application-owner", "Use the reference Taskboard or an identified hosting-first Next.js application.")
                    return result
                try:
                    _, receipt = p.helper("operations").receipt_at(staging, p)
                except SAFE:
                    row("rehearsal_deployment", "unknown", "release-engineer", "Rehearse this candidate and verify the current deployment receipt.")
                    return result
            now = time.time()
            stack = project / cfg["infrastructure"]
            if _applying is None:
                _, gate_fd = p.open_project(stack / ".gate")
                try:
                    summary = p.object_at(gate_fd, "plan-summary.json", private=True)
                    # The gate later rehashes and evaluates the full binary before any apply.
                    actual = digest(p.read_at(gate_fd, "tfplan", private=True, maximum=64 * 1024 * 1024))
                finally:
                    os.close(gate_fd)
            else:
                summary, actual = _applying
            proof = summary.get("workload_proof") or {}
            if actual != plan_sha256 or not summary_checks(summary, proof, cfg, p, plan_sha256, now):
                row("production_plan", "failed", "release-engineer", "Review a fresh exact production workload plan.")
                return result
            ident = p.identity(prod.root_fd)
            key_path = TRUST / ident / (environment + ".pub")
            result["verifier_public_key_path"] = str(key_path)
            binding = {"policy": POLICY, "plan_sha256": plan_sha256, "source_revision": revision(project, p),
                       "project_identity": ident, "source_sha256": p.source_fingerprint(prod.root_fd), "kit_sha256": p.kit_fingerprint(),
                       "image_digest": image, "profile": profile, "environment": environment, "rehearsal": rehearsal,
                       "critical_journey": plan["critical_journey"], "journey_sha256": plan["journey_sha256"],
                       "production_sha256": p.digest(p.canonical(cfg)), "rehearsal_sha256": p.digest(p.canonical(stage)),
                       "rehearsal_receipt_sha256": receipt}
            result["binding"] = binding
            result["required_controls"] = list(profile_controls(profile))
            keys = {}
            try:
                pub = trusted_key(key_path, p)
                if raw and signature:
                    keys = reports(binding, raw, signature, pub, time.time(), p)
                row("protected_verifier", "passed" if keys else "unknown", "release-engineer",
                    "Collect a current signed protected-verifier result for the exact release binding.")
            except SAFE:
                row("protected_verifier", "unknown", "administrator", "Check the enrolled public key, signature, clocks and exact candidate binding.")
            for control in profile_controls(profile):
                observed = value["controls"][control]["observed_at"] if keys and isinstance(value["controls"][control], dict) else None
                row(control, keys.get(control, "unknown"), "release-engineer", "Rerun the protected " + control + " check.",
                    observed if type(observed) is int else None)
            if keys and all(c["status"] == "passed" for c in result["checks"]):
                result["status"] = "passed"
                result["attestation_sha256"] = digest(raw)
    except SAFE:
        row("candidate_binding", "unknown", "release-engineer", "Check clean Git revision, private plan, environment and readable evidence.")
    return result


def assemble(challenge, report_dir, output):
    """For the protected coordinator only; this never signs and never executes supplied code."""
    p = project_module()
    challenge = p.helper("kit_common").private_json(Path(challenge))
    b = challenge.get("binding")
    binding_fields = {"policy", "plan_sha256", "source_revision", "project_identity", "source_sha256", "kit_sha256",
                      "image_digest", "profile", "environment", "rehearsal", "production_sha256", "rehearsal_sha256",
                      "rehearsal_receipt_sha256", "critical_journey", "journey_sha256"}
    if (challenge.get("schema") != "oci-sre-decision/1" or not isinstance(b, dict) or set(b) != binding_fields
            or not re.fullmatch("[a-z][a-z0-9-]{1,47}", str(b["critical_journey"]))
            or b["policy"] != POLICY or b["profile"] not in {"taskboard", "hosting-first-nextjs"}
            or not IMAGE.fullmatch(str(b["image_digest"])) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(b["source_revision"]))
            or not all(p.valid_hash(b[k]) for k in binding_fields if k.endswith("sha256") or k == "project_identity")):
        raise ValueError("The selected challenge is not supported.")
    names = profile_controls(b["profile"])
    controls = {}
    now = int(time.time())
    binding_sha = p.digest(p.canonical(b))
    _, fd = p.open_project(Path(report_dir).absolute())
    try:
        for name in names:
            raw = p.read_at(fd, name + ".json", private=True)
            report = json.loads(raw, object_pairs_hook=p.unique)
            if (not isinstance(report, dict) or set(report) != {"schema", "id", "binding_sha256", "observed_at",
                                                               "observations", "raw_artifact_sha256"}
                    or report["schema"] != "oci-sre-control/1" or report["id"] != name
                    or report["binding_sha256"] != binding_sha):
                raise ValueError("A verifier output belongs to the wrong candidate or control.")
            # Hash exact bytes of private original test output independently of the signed projection.
            proof = p.read_at(fd, name + ".artifact", private=True, maximum=16*p.LIMIT)
            if not proof or p.digest(proof) != report["raw_artifact_sha256"]:
                raise ValueError("Missing or changed underlying test artifact.")
            row = {"observed_at": report["observed_at"], "artifact_sha256": p.digest(proof),
                   "observations": report["observations"]}
            if indicator(row, name, b, now, p) != "passed":
                raise ValueError("A mandatory check is missing, failed or stale: " + name)
            controls[name] = row
    finally:
        os.close(fd)
    payload = {"schema": SCHEMA, "issued_at": now, "binding": b, "controls": controls}
    destination = Path(output).absolute()
    _, dest = p.open_project(destination.parent)
    try:
        p.helper("environments").put(dest, destination.name, p.canonical(payload) + b"\n")
    finally:
        os.close(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble checked artifacts in an independently protected verifier. Does not sign or authorize production.")
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        assemble(args.challenge, args.report_dir, args.out)
    except SAFE:
        raise SystemExit("Cannot assemble: inspect the private challenge, mandatory results, freshness and actual artifact hashes.") from None
