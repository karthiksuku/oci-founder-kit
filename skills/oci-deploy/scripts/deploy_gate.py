#!/usr/bin/env python3
"""Approval-gated Terraform for OCI: plan, approve the exact plan, apply, receipt, teardown.

  plan             terraform plan -out, then a summary with the plan's SHA-256, the
                   target (region, compartment, profile), every resource change,
                   access (IAM) changes called out, the Terraform binary used and an
                   expiry fixed at plan time
  apply            applies the saved plan only when --approve equals its SHA-256, the
                   approval has not expired, the same Terraform binary is used, and the
                   plan's contents still match the summary. The plan is consumed before
                   Terraform runs, so an approval is good for one attempt
  destroy-plan     the same, for terraform plan -destroy
  destroy          applies a destroy plan under the same rules
  verify-teardown  checks recorded resources for terminal states; absent Search
                   results or unsupported identifiers remain unknown, not success
  status           shows the pending plan and receipts
  image-plan       prepares an exact-image publication plan using a registry receipt
  image-push       publishes only that approved image to its private immutable OCIR repository

What this gate does NOT guarantee: the approval is the plan's hash, which the agent
can read. Nothing here proves that a person saw or approved the plan, and anything
running as the same OS user can edit gate files, the environment or call Terraform
directly. The owner's approval in the conversation, and an "ask" permission rule for
the apply and destroy commands, are the controls for that. See SKILL.md.

Standard library only. Exit codes: 0 ok, 1 terraform or OCI CLI failure, 2 bad input,
3 refused by the gate, 4 teardown incomplete, 5 applied but not recorded.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

GATE_DIR = ".gate"
PLAN_FILE = "tfplan"
SUMMARY_FILE = "plan-summary.json"
SUMMARY_MD = "plan-summary.md"
ERROR_LOG = "last-error.log"
DEFAULT_MAX_AGE_MINUTES = 120
CLOCK_SKEW_SECONDS = 300
TARGET_KEYS = {"region": ("region",), "compartment_ocid": ("compartment_ocid", "compartment_id"),
               "profile": ("config_file_profile", "profile", "oci_profile"),
               "tenancy_ocid": ("tenancy_ocid",), "home_region": ("home_region",),
               "auth": ("auth",)}
GONE_STATES = {"TERMINATED", "DELETED"}
OCID = re.compile(r"^ocid1\.[a-z0-9_-]+\.[a-z0-9_-]+\.([a-z0-9_-]*)\.[a-z0-9]+$")
REGION = re.compile(r"^[a-z]+-[a-z]+-\d+$")
ACCESS_PREFIXES = ("oci_identity_", "oci_identity_domains_")


class GateRefused(Exception):
    """The gate refused an action."""


class GateInputError(Exception):
    """The request itself is invalid."""


class TerraformError(Exception):
    """Terraform or the OCI CLI exited with an error."""


class AppliedButUnrecorded(Exception):
    """Terraform applied, but the result could not be recorded."""


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

def _gate(stack: Path, create: bool) -> Path:
    gate = stack / GATE_DIR
    if gate.is_symlink():
        raise GateInputError(f"{gate} is a symlink; the gate directory must be a real directory")
    if create:
        gate.mkdir(mode=0o700, exist_ok=True)
    if gate.exists():
        if gate.lstat().st_uid != os.getuid():
            raise GateInputError(f"{gate} is owned by another user")
        gate.chmod(0o700)
    return gate


def _no_symlink(path: Path) -> Path:
    if path.is_symlink():
        raise GateRefused(f"{path.name} is a symlink; refusing to use it")
    return path


def _write_private(path: Path, text: str) -> None:
    _no_symlink(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(0o600)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> tuple[str, float]:
    epoch = time.time()
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), epoch


# --------------------------------------------------------------------------
# Terraform
# --------------------------------------------------------------------------

def terraform_binary() -> dict:
    """Resolve $TF_BIN (default terraform) to one absolute executable and fingerprint it."""
    value = os.environ.get("TF_BIN", "terraform")
    if not value or any(ch.isspace() for ch in value):
        raise GateInputError("TF_BIN must be a single executable path without arguments")
    resolved = shutil.which(value)
    if not resolved:
        raise GateInputError(f"Terraform executable not found: {value}")
    path = Path(resolved).resolve()
    return {"path": str(path), "sha256": sha256_bytes(path.read_bytes())}


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("TF_CLI_ARGS")}


def run_terraform(binary: dict, args: list[str], stack: Path, gate: Path | None) -> str:
    result = subprocess.run([binary["path"]] + args, cwd=stack, capture_output=True, text=True,
                            errors="replace", env=_child_env(), check=False)
    if result.returncode != 0:
        where = ""
        if gate is not None:
            _write_private(gate / ERROR_LOG, f"$ terraform {' '.join(args)}\n--- stdout\n{result.stdout}\n"
                                             f"--- stderr\n{result.stderr}\n")
            where = f" Full output is in {GATE_DIR}/{ERROR_LOG} (it may contain sensitive values)."
        raise TerraformError(f"terraform {args[0]} failed (exit {result.returncode}).{where}")
    return result.stdout


# --------------------------------------------------------------------------
# Summaries and receipts
# --------------------------------------------------------------------------

def _action(actions: list[str]) -> str | None:
    if set(actions) == {"create", "delete"}:
        return "replace"
    for action in ("create", "update", "delete"):
        if actions == [action]:
            return action
    return None


def describe_plan(plan: dict) -> dict:
    """The parts of `terraform show -json <plan>` an approver needs, with no values."""
    variables = plan.get("variables") or {}
    target = {}
    for key, names in TARGET_KEYS.items():
        value = next((variables[n].get("value") for n in names if isinstance(variables.get(n), dict)), None)
        if isinstance(value, str):
            target[key] = value
    changes = {"create": 0, "update": 0, "delete": 0, "replace": 0}
    resources = []
    for change in plan.get("resource_changes") or []:
        if change.get("mode") == "data":
            continue
        action = _action((change.get("change") or {}).get("actions") or [])
        if action is None:
            continue
        changes[action] += 1
        resources.append({"address": change.get("address"), "type": change.get("type"), "action": action})
    return {"target": target, "changes": changes, "resources": resources,
            "access_changes": [r["address"] for r in resources if str(r["type"]).startswith(ACCESS_PREFIXES)],
            "destructive": changes["delete"] > 0 or changes["replace"] > 0,
            "outputs": sorted((plan.get("output_changes") or {}).keys()),
            "terraform_version": plan.get("terraform_version")}


def render_summary(summary: dict, stack: Path) -> str:
    verb = "destroy" if summary["kind"] == "destroy" else "apply"
    headline = "This plan DESTROYS resources." if summary["destructive"] else "This plan creates or changes resources."
    target = summary["target"]
    lines = [f"## Terraform {verb} plan: {summary['stack']}", "", headline, "",
             f"Target: region {target.get('region', 'unknown')}, compartment "
             f"{target.get('compartment_ocid', 'unknown')}, profile {target.get('profile', 'default')}.",
             "Changes: " + ", ".join(f"{k} {v}" for k, v in summary["changes"].items()) + ".", ""]
    if summary["access_changes"]:
        lines += ["ACCESS CHANGES (IAM): " + ", ".join(f"`{a}`" for a in summary["access_changes"])
                  + ". These widen what identities can do; review them on their own.", ""]
    if summary.get("required_backend"):
        lines += ["Required state backend: OCI. Bucket IAM, versioning and recovery require separate verification.", ""]
    lines += [f"Account: {target.get('tenancy_ocid', 'not declared — verify privately')}; "
              f"authentication: {target.get('auth', 'provider default')}; "
              f"IAM home region: {target.get('home_region', 'same as target or separately verified')}.", ""]
    lines += ["| Action | Resource | Type |", "|---|---|---|"]
    lines += [f"| {r['action']} | `{r['address']}` | {r['type']} |" for r in summary["resources"]]
    expires = dt.datetime.fromtimestamp(summary["expires_at_epoch"], dt.timezone.utc)
    lines += ["", f"Plan SHA-256: `{summary['plan_sha256']}`", "",
              "Show this summary to the owner. Only after they approve this exact plan, run:", "",
              f"    python3 deploy_gate.py {verb} --dir {stack} --approve {summary['plan_sha256']}", "",
              f"The approval expires at {expires.strftime('%Y-%m-%d %H:%M UTC')}; re-plan after that."]
    return "\n".join(lines) + "\n"


def _clean_str(values: dict, sensitive: dict, key: str) -> str | None:
    value = values.get(key)
    if sensitive.get(key) or not isinstance(value, str):
        return None
    return value


def state_resources(module: dict) -> list[dict]:
    """Managed resources from `terraform show -json`, keeping only non-sensitive ids and names."""
    found = []
    for resource in module.get("resources") or []:
        if resource.get("mode") != "managed":
            continue
        values = resource.get("values") or {}
        sensitive = resource.get("sensitive_values") or {}
        ocid = _clean_str(values, sensitive, "id")
        found.append({"address": resource.get("address"), "type": resource.get("type"),
                      "id": ocid if ocid and ocid.startswith("ocid1.") else None,
                      "name": _clean_str(values, sensitive, "display_name") or _clean_str(values, sensitive, "name"),
                      "compartment_id": _clean_str(values, sensitive, "compartment_id")})
    for child in module.get("child_modules") or []:
        found += state_resources(child)
    return found


def _read_state(binary: dict, stack: Path, gate: Path) -> list[dict]:
    text = run_terraform(binary, ["show", "-json"], stack, gate)
    if not text.strip():
        raise ValueError("terraform show returned no state")
    return state_resources((json.loads(text).get("values") or {}).get("root_module") or {})


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def require_backend(stack: Path, expected: str | None) -> None:
    """Check initialized backend type without exposing its credential-bearing config.

    This verifies local Terraform metadata, not remote bucket IAM/versioning.
    Keep those checks in the workload's architecture review.
    """
    if expected is None:
        return
    if expected != "oci":
        raise GateRefused("Unsupported required backend; re-plan with a supported backend.")
    data_dir = Path(os.environ.get("TF_DATA_DIR", ".terraform"))
    if not data_dir.is_absolute():
        data_dir = stack / data_dir
    if data_dir.is_symlink():
        raise GateRefused("Backend metadata directory is a symlink.")
    path = _no_symlink(data_dir / "terraform.tfstate")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("not regular")
            raw = handle.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("too large")
        metadata = json.loads(raw)
        backend = metadata.get("backend")
        if not isinstance(backend, dict) or backend.get("type") != expected:
            raise ValueError("wrong backend")
    except (OSError, ValueError, AttributeError):
        raise GateRefused("An initialized OCI remote backend is required. Configure it privately before planning.") from None


def cmd_plan(stack: Path, kind: str, var_files: list[str], max_age: int,
             required_backend: str | None = None) -> int:
    if max_age <= 0:
        raise GateInputError("--max-age-minutes must be positive")
    binary = terraform_binary()
    gate = _gate(stack, create=True)
    plan_path = _no_symlink(gate / PLAN_FILE)
    for stale in (plan_path, gate / SUMMARY_FILE, gate / SUMMARY_MD):
        _no_symlink(stale).unlink(missing_ok=True)
    run_terraform(binary, ["init", "-input=false", "-no-color"], stack, gate)
    require_backend(stack, required_backend)
    args = ["plan", "-input=false", "-no-color", f"-out={plan_path}"]
    args += ["-destroy"] if kind == "destroy" else []
    args += [f"-var-file={f}" for f in var_files]
    run_terraform(binary, args, stack, gate)
    _no_symlink(plan_path).chmod(0o600)
    plan_bytes = plan_path.read_bytes()
    described = describe_plan(json.loads(run_terraform(binary, ["show", "-json", str(plan_path)], stack, gate)))
    target = described["target"]
    if not re.fullmatch(r"ocid1\.compartment\.[a-z0-9_-]+\.[a-z0-9_-]*\.[a-z0-9]+", target.get("compartment_ocid", "")):
        raise GateRefused("A dedicated non-root compartment must be declared in the plan variables.")
    if not REGION.fullmatch(target.get("region", "")) or not target.get("profile"):
        raise GateRefused("Declare the selected region and OCI profile in the plan variables.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", target["profile"]):
        raise GateRefused("The selected OCI profile has an invalid format.")
    if "tenancy_ocid" in target and not re.fullmatch(r"ocid1\.tenancy\.[a-z0-9_-]+\.\.[a-z0-9]+", target["tenancy_ocid"]):
        raise GateRefused("The expected tenancy identifier is invalid.")
    if "auth" in target and target["auth"] not in {"APIKey", "SecurityToken", "InstancePrincipal", "ResourcePrincipal"}:
        raise GateRefused("The declared authentication mode is invalid.")
    if kind == "destroy" and (described["changes"]["create"] or described["changes"]["update"]):
        raise GateRefused("A destroy plan must only delete resources.")
    created_at, epoch = _now()
    summary = {"kind": kind, "stack": stack.name, "stack_path": str(stack), "plan_sha256": sha256_bytes(plan_bytes),
               "created_at": created_at, "created_at_epoch": epoch, "expires_at_epoch": epoch + max_age * 60,
               "terraform": binary, "required_backend": required_backend, **described}
    text = render_summary(summary, stack)
    _write_private(gate / SUMMARY_FILE, json.dumps(summary, indent=2) + "\n")
    _write_private(gate / SUMMARY_MD, text)
    sys.stdout.write(text)
    return 0


def _load_approval(stack: Path, kind: str, approve: str) -> tuple[Path, dict]:
    gate = _gate(stack, create=False)
    plan_path, summary_path = gate / PLAN_FILE, gate / SUMMARY_FILE
    if not gate.exists() or not plan_path.exists() or not summary_path.exists():
        raise GateRefused("There is no approved plan waiting. Run plan (or destroy-plan) first.")
    _no_symlink(plan_path)
    _no_symlink(summary_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["kind"] != kind:
        other = "destroy plan; use destroy" if summary["kind"] == "destroy" else "apply plan; use apply"
        raise GateRefused(f"The pending plan is a {other}.")
    if approve != summary["plan_sha256"]:
        raise GateRefused("The approved hash does not match the pending plan. Show the owner the current plan.")
    now = time.time()
    if summary["created_at_epoch"] > now + CLOCK_SKEW_SECONDS or summary["expires_at_epoch"] > \
            summary["created_at_epoch"] + 24 * 3600:
        raise GateRefused("The plan's timestamps are in the future or too far apart; check the clock and re-plan.")
    if now > summary["expires_at_epoch"]:
        raise GateRefused("The approval has expired. Run plan again and get a fresh approval.")
    if terraform_binary() != summary["terraform"]:
        raise GateRefused("A different Terraform binary is in use than at plan time. Re-plan with this binary.")
    return gate, summary


def cmd_apply(stack: Path, kind: str, approve: str) -> int:
    gate, summary = _load_approval(stack, kind, approve)
    require_backend(stack, summary.get("required_backend"))
    binary = summary["terraform"]
    sha = summary["plan_sha256"]
    applying = gate / f"{PLAN_FILE}.{sha[:12]}.applying"
    _no_symlink(applying).unlink(missing_ok=True)
    os.rename(gate / PLAN_FILE, applying)  # consumes the approval before anything else runs
    for consumed in (gate / SUMMARY_FILE, gate / SUMMARY_MD):
        consumed.unlink(missing_ok=True)
    try:
        if sha256_bytes(applying.read_bytes()) != sha:
            raise GateRefused("The plan file changed since it was summarised. Run plan again.")
        current = describe_plan(json.loads(run_terraform(binary, ["show", "-json", str(applying)], stack, gate)))
        if any(current[k] != summary[k] for k in ("changes", "resources", "target", "access_changes")):
            raise GateRefused("The summary does not match the plan's contents. Run plan again.")
    except (GateRefused, TerraformError, ValueError):
        applying.unlink(missing_ok=True)
        raise
    receipts = gate / "receipts"
    if receipts.is_symlink():
        raise GateInputError("receipts directory is a symlink")
    receipts.mkdir(mode=0o700, exist_ok=True)
    started, _ = _now()
    receipt_path = receipts / f"{started.replace(':', '').replace('-', '')}-{kind}-{sha[:12]}.json"
    receipt = {"schema": "oci-deploy-receipt/2", "kind": kind, "status": "attempted", "stack": summary["stack"],
               "started_at": started, "plan_sha256": sha, "target": summary["target"],
               "changes": summary["changes"], "planned": summary["resources"]}
    if kind == "destroy":
        try:
            receipt["destroyed_resources"] = _read_state(binary, stack, gate)
        except (TerraformError, ValueError, json.JSONDecodeError):
            receipt["destroyed_resources"] = []
    _write_private(receipt_path, json.dumps(receipt, indent=2) + "\n")
    try:
        run_terraform(binary, ["apply", "-input=false", "-no-color", str(applying)], stack, gate)
    except TerraformError as exc:
        receipt["status"] = "failed"
        try:  # a partial apply leaves resources behind; record whatever state reports
            receipt["resources"] = _read_state(binary, stack, gate)
        except (TerraformError, ValueError, json.JSONDecodeError):
            receipt["resources_unreadable"] = True
        _write_private(receipt_path, json.dumps(receipt, indent=2) + "\n")
        raise TerraformError(f"{exc} Resources may have been created or changed before the failure; "
                             f"see {receipt_path.name} and run plan to see the current state.") from exc
    finally:
        applying.unlink(missing_ok=True)
    try:
        resources = _read_state(binary, stack, gate)
    except (TerraformError, ValueError, json.JSONDecodeError) as exc:
        receipt["status"] = "applied-unrecorded"
        _write_private(receipt_path, json.dumps(receipt, indent=2) + "\n")
        raise AppliedButUnrecorded(f"Terraform applied plan {sha[:12]}, but the result could not be read ({exc}). "
                                   f"Resources exist; see {receipt_path.name}.") from exc
    finished, _ = _now()
    receipt.update({"status": "applied", "finished_at": finished})
    receipt["resources"] = resources
    _write_private(receipt_path, json.dumps(receipt, indent=2) + "\n")
    count = len(receipt.get("destroyed_resources", resources) if kind == "destroy" else resources)
    sys.stdout.write(f"Applied {kind} plan {sha[:12]}: {count} resource(s) recorded in "
                     f"{GATE_DIR}/receipts/{receipt_path.name}.\n")
    return 0


def oci_cli_state(profile: str | None, region: str | None, auth: str | None = None) -> Callable[[str], str | None]:
    """Return a read-only state check; None means not visible, never proof of deletion."""
    auth_modes = {"APIKey": "api_key", "SecurityToken": "security_token",
                  "InstancePrincipal": "instance_principal", "ResourcePrincipal": "resource_principal"}
    if auth is not None and auth not in auth_modes:
        raise GateInputError("The receipt authentication mode is invalid.")
    def check(ocid: str) -> str | None:
        match = OCID.match(ocid)
        ocid_region = match.group(1) if match else ""
        command = ["oci", "search", "resource", "structured-search", "--query-text",
                   f"query all resources where identifier = '{ocid}'", "--output", "json"]
        command += ["--profile", profile] if profile else []
        command += ["--auth", auth_modes[auth]] if auth else []
        use_region = ocid_region if REGION.match(ocid_region) else region
        command += ["--region", use_region] if use_region else []
        try:
            result = subprocess.run(command, capture_output=True, text=True, errors="replace", check=False,
                                    timeout=30, stdin=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise TerraformError("oci search could not complete; check access and connectivity privately.") from exc
        if result.returncode != 0:
            raise TerraformError(f"oci search failed (exit {result.returncode}); "
                                 "check authentication, permissions and network access privately.")
        try:
            payload = json.loads(result.stdout)
        except (ValueError, RecursionError):
            return "UNKNOWN"
        data = payload.get("data") if isinstance(payload, dict) else None
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return "UNKNOWN"
        if not items:
            return None
        if len(items) != 1 or not isinstance(items[0], dict) or items[0].get("identifier") != ocid:
            return "UNKNOWN"
        state = items[0].get("lifecycle-state")
        return state if isinstance(state, str) and re.fullmatch(r"[A-Z_]+", state) else "UNKNOWN"
    return check


def verify_teardown(receipt: dict, check: Callable[[str], str | None]) -> dict:
    resources = receipt.get("destroyed_resources") if receipt.get("kind") == "destroy" else receipt.get("resources")
    remaining, checked, ignored_local = [], 0, 0
    for resource in resources or []:
        ocid = resource.get("id")
        if not ocid:
            type_ = resource.get("type") or ""
            if type_.startswith("random_") or type_ in {"null_resource", "terraform_data"}:
                ignored_local += 1
                continue
            remaining.append({**resource, "state": "UNVERIFIABLE_ID"})
            continue
        checked += 1
        if not isinstance(ocid, str) or not OCID.fullmatch(ocid):
            remaining.append({**resource, "state": "INVALID_OCID"})
            continue
        state = check(ocid)
        if state is None:
            remaining.append({**resource, "state": "NOT_VISIBLE"})
        elif not isinstance(state, str) or state.upper() not in GONE_STATES:
            remaining.append({**resource, "state": state if isinstance(state, str) else "UNKNOWN"})
    return {"clean": checked > 0 and not remaining, "checked": checked, "remaining": remaining,
            "ignored_local": ignored_local}


def cmd_verify(receipt_path: Path, profile: str | None, region: str | None) -> int:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    target = receipt.get("target") or {}
    for field, override in (("profile", profile), ("region", region)):
        if override is not None and target.get(field) is not None and override != target[field]:
            raise GateRefused("Verification must use the receipt's profile and region; a different target cannot verify it.")
    result = verify_teardown(receipt, oci_cli_state(profile or target.get("profile"),
                                                  region or target.get("region"), target.get("auth")))
    if result["checked"] == 0 and not result["remaining"]:
        raise GateInputError("The receipt lists no OCIDs: nothing to verify. Use the apply receipt, or a destroy "
                             "receipt that recorded the destroyed resources.")
    if result["clean"]:
        sys.stdout.write(f"Search reports terminal states for all {result['checked']} checked OCIDs. "
                         "This is a residual-resource check, not proof of account-wide cleanup.\n")
        return 0
    sys.stdout.write(f"Teardown incomplete: {len(result['remaining'])} resource(s) still exist or could not be confirmed. "
                     "An empty Search result can mean missing permissions, an unsupported resource or indexing delay; "
                     "use authorized service-specific checks before declaring cleanup complete.\n")
    for r in result["remaining"]:
        sys.stdout.write(f"  {r['state']}: {r.get('type', 'unknown')} {r.get('address', 'unknown')} "
                         f"{r.get('id') or '[identifier unavailable]'}\n")
    return 4


def cmd_status(stack: Path) -> int:
    gate = _gate(stack, create=False)
    summary_md = _no_symlink(gate / SUMMARY_MD)
    sys.stdout.write(summary_md.read_text(encoding="utf-8") if summary_md.exists()
                     else "No plan is waiting for approval.\n")
    receipts_dir = _no_symlink(gate / "receipts")
    receipts = sorted(receipts_dir.glob("*.json")) if receipts_dir.is_dir() else []
    if receipts:
        sys.stdout.write("Receipts: " + ", ".join(r.name for r in receipts) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approval-gated Terraform and image publication for OCI.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("image-plan", "image-push"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, required=True, help="Registry stack / private gate workspace")
        if name == "image-plan":
            p.add_argument("--registry-receipt", type=Path, required=True)
            p.add_argument("--repository-id", required=True)
            p.add_argument("--image", required=True, help="Local image reference resolved to immutable content ID")
            p.add_argument("--tag", required=True, help="New destination tag")
            p.add_argument("--max-image-bytes", type=int, default=1024 ** 3)
            p.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
        else:
            p.add_argument("--approve", required=True, help="SHA-256 of the exact image plan approved by the owner")
    for name in ("plan", "destroy-plan", "apply", "destroy", "status"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, required=True, help="Terraform stack directory")
        if name in ("plan", "destroy-plan"):
            p.add_argument("--var-file", action="append", default=[])
            p.add_argument("--require-backend", choices=["oci"],
                           help="require initialized OCI state backend at plan and apply time")
            p.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES,
                           help="how long the approval stays valid (fixed at plan time)")
        if name in ("apply", "destroy"):
            p.add_argument("--approve", required=True, help="SHA-256 of the plan the owner approved")
    v = sub.add_parser("verify-teardown")
    v.add_argument("--receipt", type=Path, required=True)
    v.add_argument("--profile")
    v.add_argument("--region")
    args = parser.parse_args(argv)
    if args.command in ("image-plan", "image-push"):
        import image_gate
        return image_gate.dispatch(args)
    try:
        if args.command == "verify-teardown":
            return cmd_verify(args.receipt, args.profile, args.region)
        stack = args.dir.resolve()
        if not stack.is_dir():
            raise GateInputError(f"{args.dir} is not a directory")
        if args.command == "status":
            return cmd_status(stack)
        if args.command in ("plan", "destroy-plan"):
            return cmd_plan(stack, "destroy" if args.command == "destroy-plan" else "apply",
                            args.var_file, args.max_age_minutes, args.require_backend)
        return cmd_apply(stack, "destroy" if args.command == "destroy" else "apply", args.approve)
    except GateRefused as exc:
        sys.stderr.write(f"deploy_gate: refused. {exc}\n")
        return 3
    except AppliedButUnrecorded as exc:
        sys.stderr.write(f"deploy_gate: applied but not recorded. {exc}\n")
        return 5
    except TerraformError as exc:
        sys.stderr.write(f"deploy_gate: {exc}\n")
        return 1
    except (GateInputError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        sys.stderr.write(f"deploy_gate: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
