#!/usr/bin/env python3
"""Read-only OCI readiness checks. Credentials and raw CLI output never enter reports.

Offline checks are the default; --live explicitly enables two IAM read calls.
Exit codes: 0 checks passed, 1 blocked, 2 invalid arguments, 3 incomplete/unknown.
A passing report establishes read access, not deployment permissions or capacity.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable

AUTH_MODES = ("api_key", "security_token", "instance_principal", "resource_principal")
PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
REGION = re.compile(r"^[a-z][a-z0-9-]*-[0-9]+$")
TENANCY = re.compile(r"^ocid1\.tenancy\.[a-z0-9-]+\.\.[a-z0-9]+$")
COMPARTMENT = re.compile(r"^ocid1\.compartment\.[a-z0-9-]+\.\.[a-z0-9]+$")


def check(name: str, status: str, message: str) -> dict:
    return {"check": name, "status": status, "message": message}


def private_file(path: Path) -> bool:
    """Inspect metadata only, including for keys and tokens. Never read key contents."""
    try:
        if any(part.is_symlink() for part in (path, *path.parents)):
            return False
        info = path.stat()
        return (stat.S_ISREG(info.st_mode)
                and (os.name == "nt" or (info.st_mode & 0o077 == 0
                     and info.st_uid == os.getuid())))
    except OSError:
        return False


def read_profile(path: Path, profile: str, auth: str) -> tuple[dict, list[dict]]:
    if not private_file(path):
        return {}, [check("credentials", "blocked", "Use an owned, non-symlink config file with mode 600 or 400; never paste its contents.")]
    parser = configparser.ConfigParser(interpolation=None)
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("oversized config")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), encoding="utf-8") as handle:
            parser.read_file(handle)
        if profile != "DEFAULT" and not parser.has_section(profile):
            raise ValueError("missing profile")
        values = dict(parser[profile])
    except (OSError, ValueError, configparser.Error, UnicodeError):
        return {}, [check("credentials", "blocked", "Select an existing valid OCI config profile; no config values are included in this report.")]
    required = {"tenancy", "key_file"}
    required |= {"user", "fingerprint"} if auth == "api_key" else {"security_token_file"}
    if any(not values.get(key, "").strip() for key in required):
        return {}, [check("credentials", "blocked", "The selected profile is incomplete for this authentication mode; follow the credentials guide.")]
    for key in ("key_file", "security_token_file"):
        if key not in required:
            continue
        candidate = Path(values[key]).expanduser()
        if not candidate.is_absolute():
            return {}, [check("credentials", "blocked", "Use absolute paths for key and token files so OCI CLI and the doctor inspect the same files.")]
        if not private_file(candidate):
            return {}, [check("credentials", "blocked", "Use owned, non-symlink key/token files with mode 600 or 400. Key and token contents are never inspected.")]
    if values.get("pass_phrase"):
        return {}, [check("credentials", "blocked", "Remove stored passphrases through an owner-reviewed credential update; prefer a session or an approved runtime secret source.")]
    return values, [check("credentials", "passed", "Required profile fields and credential file metadata checked; no credential contents reported.")]


def run_json(argv: list[str], runner: Callable = subprocess.run) -> tuple[str, object]:
    try:
        result = runner(argv, capture_output=True, text=True, timeout=30, check=False,
                        stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            return "blocked", None
        return "passed", json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError, UnicodeError):
        return "unknown", None


def diagnose(*, config_file: Path, profile: str = "DEFAULT", auth: str = "api_key",
             region: str | None = None, compartment: str | None = None,
             tenancy: str | None = None, live: bool = False,
             which: Callable = shutil.which, runner: Callable = subprocess.run) -> dict:
    if auth not in AUTH_MODES or not PROFILE.fullmatch(profile):
        raise ValueError("Invalid authentication mode or profile name.")
    checks = []
    checks.append(check("python", "passed" if sys.version_info >= (3, 11) else "blocked",
                        "Python 3.11 or newer is required by the kit."))
    for executable in ("oci", "terraform"):
        checks.append(check(executable, "passed" if which(executable) else "blocked",
                            "Tool available." if which(executable) else "Install the required tool from its official documentation."))
    values = {}
    if auth in {"api_key", "security_token"}:
        values, credential_checks = read_profile(config_file.expanduser().absolute(), profile, auth)
        checks.extend(credential_checks)
    else:
        checks.append(check("credentials", "unknown" if not live else "passed",
                            "Principal credentials are runtime supplied; only a live request can validate access."))
    selected_region = region or values.get("region")
    selected_tenancy = tenancy or values.get("tenancy")
    if selected_region and not REGION.fullmatch(selected_region):
        raise ValueError("Invalid region format.")
    if selected_tenancy and not TENANCY.fullmatch(selected_tenancy):
        raise ValueError("Invalid tenancy OCID format.")
    if compartment and not COMPARTMENT.fullmatch(compartment):
        raise ValueError("Use a non-root compartment OCID; the tenancy root is not a deployment target.")
    checks.append(check("region", "passed" if selected_region else "unknown",
                        "Region selected." if selected_region else "Select the target OCI region; none was inferred."))
    checks.append(check("compartment", "passed" if compartment else "unknown",
                        "Non-root compartment selected." if compartment else "Select or plan a dedicated non-root application compartment."))
    checks.append(check("tenancy", "passed" if selected_tenancy else "unknown",
                        "Tenancy selected." if selected_tenancy else "Specify the tenancy OCID privately for subscription checks."))
    can_query = (which("oci") and selected_region and selected_tenancy and compartment
                 and not any(c["status"] == "blocked" and c["check"] == "credentials" for c in checks))
    if live and can_query:
        base = [which("oci"), "--auth", auth, "--region", selected_region,
                "--output", "json"]
        if auth in {"api_key", "security_token"}:
            base += ["--config-file", str(config_file.expanduser().absolute()), "--profile", profile]
        status, payload = run_json(base + ["iam", "region-subscription", "list",
                                          "--tenancy-id", selected_tenancy, "--all"], runner)
        if status == "passed":
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                status = "unknown"
            elif not any(isinstance(item, dict) and item.get("region-name") == selected_region
                         and item.get("status") == "READY" for item in data):
                status = "blocked"
        checks.append(check("region_subscription", status,
                            "Target region subscription checked." if status == "passed" else
                            "Could not confirm a READY subscription. Check the region, IAM access and authentication; raw CLI output is withheld."))
        status, payload = run_json(base + ["iam", "compartment", "get", "--compartment-id", compartment], runner)
        if status == "passed":
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or data.get("id") != compartment:
                status = "unknown"
            elif data.get("lifecycle-state") != "ACTIVE":
                status = "blocked"
        checks.append(check("compartment_access", status,
                            "Target compartment is readable and ACTIVE." if status == "passed" else
                            "Could not confirm the target compartment. Check IAM permissions, authentication and compartment state; raw CLI output is withheld."))
    else:
        checks.append(check("live_access", "unknown", "Live access was not checked. Rerun with --live after resolving required inputs and local blockers."))
    checks.append(check("deployment_permissions_and_capacity", "unknown",
                        "IAM read access does not prove resource creation permissions, available capacity or service quotas. Review the exact Terraform plan and service limits before deployment."))
    actionable = [c for c in checks if c["check"] != "deployment_permissions_and_capacity"]
    status = "blocked" if any(c["status"] == "blocked" for c in actionable) else (
        "incomplete" if any(c["status"] == "unknown" for c in actionable) else "passed")
    return {"schema": "oci-readiness/1", "mode": "live-read-only" if live else "offline",
            "status": status, "checks": checks,
            "scope": "Readiness diagnosis only. No cloud writes. No credentials or account identifiers in output."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--auth", choices=AUTH_MODES, default="api_key")
    parser.add_argument("--region")
    parser.add_argument("--compartment-id")
    parser.add_argument("--tenancy-id")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args(argv)
    try:
        report = diagnose(config_file=args.config_file, profile=args.profile, auth=args.auth,
                          region=args.region, compartment=args.compartment_id,
                          tenancy=args.tenancy_id, live=args.live)
    except ValueError as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(f"OCI readiness: {report['status']} ({report['mode']})")
        for item in report["checks"]:
            print(f"- {item['check']}: {item['status']} — {item['message']}")
        print(report["scope"])
    return {"passed": 0, "blocked": 1, "incomplete": 3}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
