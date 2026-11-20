#!/usr/bin/env python3
"""Compose existing access checks with blueprint prerequisites and bounded OCI reads."""

from __future__ import annotations

import importlib.util
import ipaddress
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

PERMISSION_CHECKS = {
    "region_subscription": ("ListRegionSubscriptions", "TENANCY_INSPECT", "selected tenancy"),
    "compartment_access": ("GetCompartment", "COMPARTMENT_INSPECT", "selected compartment"),
    "vcn": ("GetVcn", "VCN_READ", "selected VCN compartment"),
    "app_subnet_id": ("GetSubnet", "SUBNET_READ", "selected application subnet compartment"),
    "lb_subnet_id": ("GetSubnet", "SUBNET_READ", "selected load balancer subnet compartment"),
    "certificate": ("GetCertificate", "CERTIFICATE_READ", "selected certificate compartment"),
    "registry": ("GetContainerRepository", "REPOSITORY_READ", "selected registry compartment"),
    "quota_ocpus": ("GetResourceAvailability", "read resource-availability", "selected workload compartment"),
    "quota_memory_gbs": ("GetResourceAvailability", "read resource-availability", "selected workload compartment"),
}


def load(relative: str):
    path = ROOT / relative
    if path.is_symlink():
        raise ValueError("Unsafe toolkit helper.")
    spec = importlib.util.spec_from_file_location("oci_readiness_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.path[:]
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous
    return module


def safe_runner(argv, **kwargs):
    # Explicit profile/config/region must win over inherited CLI configuration.
    env = {key: value for key, value in os.environ.items() if not key.startswith("OCI_")}
    # OCI enables auto-prompt on presence, including the string "False".
    env["OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING"] = "False"
    return subprocess.run(argv[:1] + ["--cli-rc-file", os.devnull, "--no-retry",
        "--connection-timeout", "5", "--read-timeout", "10"] + argv[1:], env=env, **kwargs)


def diagnose(config: dict, *, config_file: Path = Path("~/.oci/config"), live=False,
             runner=safe_runner, which=shutil.which, store=None, state=None) -> dict:
    p = load("scripts/project.py")
    load("scripts/environments.py").validate(config)
    doctor = load("skills/oci-ready/scripts/oci_doctor.py")
    target = config["target"]
    session_status = None
    if target.get("auth") == "security_token":
        session = load("skills/oci-deploy/scripts/backend_auth.py")
        try:
            session.session_readiness(target.get("profile", "DEFAULT"), config_file=config_file.expanduser().absolute())
            session_status = "passed"
        except (ValueError, OSError, UnicodeError):
            session_status = "blocked"
        original_runner = runner
        def session_runner(argv, **kwargs):
            session.session_readiness(target.get("profile", "DEFAULT"), config_file=config_file.expanduser().absolute())
            return original_runner(argv, **kwargs)
        runner = session_runner
    access = doctor.diagnose(config_file=config_file, profile=target.get("profile", "DEFAULT"),
        auth=target.get("auth", "api_key"), region=target.get("region"),
        compartment=target.get("compartment_id"), live=live and session_status != "blocked", runner=runner, which=which)
    if session_status == "blocked":
        access["status"] = "blocked"
    checks = []

    def add(name, status, message, action=None):
        checks.append({"check": name, "status": status, "message": message,
                       **({"administrator_action": action} if action else {})})

    if session_status:
        add("session_lifetime", session_status,
            "Local session consistency and expiry checked; OCI validates authenticity on a read. Refresh or reauthenticate before preparing a fresh plan if expired or near expiry.")
        add("backend_config_location", "passed" if config_file.expanduser().absolute() == Path("~/.oci/config").expanduser().absolute() else "blocked",
            "The native backend uses the selected profile in ~/.oci/config. An alternate doctor config does not establish backend readiness.")

    if config["role"] == "source":
        add("deployment_target", "blocked", "The source environment retains existing hosting. Select rehearsal or production for OCI checks.")
    add("backend_destination", "passed" if config.get("backend") else "unknown",
        "Private destination selected; named-environment gates recheck state-key isolation and actual backend configuration before execution." if config.get("backend") else
        "Bind a distinct private backend destination before preparing a named-environment cloud operation.")
    required = {"image_digest", "image_architecture", "port", "health_path", "origin", "region", "compartment_id"}
    if config["blueprint"] == "web-container":
        required |= {"vcn_id", "app_subnet_id", "lb_subnet_id", "certificate_id", "registry_id",
                     "availability_domain", "ocpus", "memory_gbs", "app_private_ip"}
    for field in sorted(required):
        add("selection_" + field, "passed" if field in target else "unknown",
            "Private selection present; this is not runtime verification." if field in target else "Supply this prerequisite in the private environment target file.")
    add("image_architecture", "blocked" if target.get("image_architecture") == "ARM64" else "unknown",
        "These deployment blueprints use E4 AMD64. Confirm the uploaded manifest digest and architecture; a supplied label is not verification.")
    query_allowed = live and which("oci") and access["status"] == "passed"
    base = ([which("oci"), "--auth", target.get("auth", "api_key"), "--profile", target.get("profile", "DEFAULT"),
            "--config-file", str(config_file.expanduser().absolute()), "--region", target.get("region", ""), "--output", "json"]
            if which("oci") else [])

    unreadable_operations = set()

    def read(name, field, argv, predicate, action):
        status = "unknown"
        if query_allowed and target.get(field):
            outcome, payload = doctor.run_json(base + argv + [target[field]], runner)
            if outcome != "passed":
                unreadable_operations.add(name)
            data = payload.get("data") if isinstance(payload, dict) else None
            if outcome == "passed" and isinstance(data, dict) and data.get("id") == target[field]:
                verdict = predicate(data)
                status = "passed" if verdict is True else ("blocked" if verdict is False else "unknown")
        add(name, status, "Selected resource metadata satisfies this narrow check." if status == "passed" else
            "Resource readiness could not be established. Denied or unavailable reads remain unknown; no broad IAM grant is inferred.",
            None if status == "passed" else action)

    if config["blueprint"] == "web-container":
        read("vcn", "vcn_id", ["network", "vcn", "get", "--vcn-id"],
             lambda d: d.get("lifecycle-state") == "AVAILABLE", "Allow the selected operator to read the selected VCN metadata in its compartment.")
        for field, private in (("app_subnet_id", True), ("lb_subnet_id", False)):
            def subnet(d, private=private):
                fields = {"lifecycle-state", "vcn-id", "prohibit-public-ip-on-vnic"}
                if not fields.issubset(d):
                    return None
                if private and "app_private_ip" in target:
                    try:
                        if ipaddress.ip_address(target["app_private_ip"]) not in ipaddress.ip_network(d.get("cidr-block", "")):
                            return False
                    except ValueError:
                        return None
                return (d["lifecycle-state"] == "AVAILABLE" and d["vcn-id"] == target.get("vcn_id")
                        and d["prohibit-public-ip-on-vnic"] is private)
            read(field, field, ["network", "subnet", "get", "--subnet-id"], subnet,
                 "Allow reads of the selected subnet. Verify the VCN, private app/public LB roles, routing, security lists and egress separately.")
        read("certificate", "certificate_id", ["certs-mgmt", "certificate", "get", "--certificate-id"],
             lambda d: d.get("lifecycle-state") == "ACTIVE", "Allow metadata reads of the selected certificate; separately verify hostname, validity period and chain. Do not export its private key.")
        read("registry", "registry_id", ["artifacts", "container", "repository", "get", "--repository-id"],
             lambda d: (d.get("is-public") is False) if "is-public" in d else None,
             "Allow metadata reads of the selected private repository. Review digest pull policy and the image receipt separately.")
        for field, limit in (("ocpus", "standard-e4-core-count"), ("memory_gbs", "standard-e4-memory-count")):
            status = "unknown"
            if query_allowed and all(key in target for key in ("compartment_id", "availability_domain", field)):
                outcome, payload = doctor.run_json(base + ["limits", "resource-availability", "get", "--service-name", "compute",
                    "--limit-name", limit, "--compartment-id", target["compartment_id"],
                    "--availability-domain", target["availability_domain"]], runner)
                if outcome != "passed":
                    unreadable_operations.add("quota_" + field)
                data = payload.get("data") if isinstance(payload, dict) else None
                available = data.get("available") if isinstance(data, dict) else None
                if outcome == "passed" and type(available) in {int, float} and math.isfinite(available) and available >= 0:
                    status = "passed" if available >= target[field] else "blocked"
            add("quota_" + field, status, "Availability API check for the selected compartment and availability domain; shared Compute/Container Instances quota, not physical capacity.",
                None if status == "passed" else "Review selected E4 core/memory limits and inherited compartment quotas; allow limits inspection only if needed. Unsupported availability reads remain unknown.")
    else:
        add("managed_postgresql", "unknown", "Review supported database shape/version, private networking, backup policy and restore target in the selected region.")
        add("object_storage", "unknown", "Review bucket access, upload isolation, version retention and recovery evidence.")
    for name, message in (
            ("physical_capacity", "Quota availability never proves physical Container Instances capacity; no resource is created by this doctor."),
            ("backend_iam_isolation", "Distinct state keys do not establish effective bucket access isolation. Review inherited IAM and protected state before credential-bearing application deployment."),
            ("effective_provisioning_iam", "Review narrowly scoped create/update permissions and inherited policies with an authorized administrator; readable resources do not establish deploy authority."),
            ("network_egress", "Verify DNS, routing, security lists and NSGs to the existing database, storage and identity providers from the actual OCI target."),
            ("private_address_availability", "Verify that the selected private IPv4 address is unassigned and outside OCI-reserved subnet addresses before planning."),
            ("external_identity", "Verify hosted sign-in, exact callback/logout origins, cookies and two-user access in the deployed app."),
            ("vault_adapter", "Confirm the application resolves only approved Vault secret references at runtime; the container target does not add an adapter or authentication."),
            ("tls_hostname", "Validate the certificate hostname, chain, expiry and public HTTPS behavior after the reviewed deployment."),
            ("scheduler_ownership", "Prove target schedulers and workers are disabled using the application's own mechanism until ownership transfers.")):
        add(name, "unknown", message)
    status = "blocked" if access["status"] == "blocked" or any(c["status"] == "blocked" for c in checks) else "incomplete"
    # A failed metadata read can also mean a wrong resource, region, network or expired identity.
    # Only name the exact read operation for an actual attempt, never infer a missing grant.
    unresolved = []
    unreadable_operations.update(c["check"] for c in access["checks"] if c.get("api_read") in {"blocked", "unknown"})
    for c in [*access["checks"], *checks]:
        if c["check"] in unreadable_operations and c["check"] in PERMISSION_CHECKS:
            op, permission, where = PERMISSION_CHECKS[c["check"]]
            unresolved.append({"check": c["check"], "operation": op, "permission_to_verify": permission,
                               "scope": where, "outcome": c["status"]})
    value = {"schema": "oci-workload-readiness/1", "environment": config["name"], "blueprint": config["blueprint"],
        "target_sha256": p.digest(p.canonical(config)), "observed_at": int(time.time()),
        "mode": "live-read-only" if live else "offline", "status": status, "access": access, "checks": checks,
        "administrator_handoff": [{"check": c["check"], "action": c["administrator_action"]} for c in checks if "administrator_action" in c],
        "production_ready": False, "scope": "Read-only prerequisite evidence. No credentials, account identifiers, resource payloads or cloud writes. Unknown checks require separate evidence."}
    recheck = ["python3", ".oci-founder-kit/scripts/kit.py", "doctor", "--project", ".",
               "--environment", config["name"], "--live"]
    default_config = config_file.expanduser().absolute() == Path("~/.oci/config").expanduser().absolute()
    if not default_config:
        recheck.extend(["--config-file", "<original-private-config-file>"])
    value["permission_review"] = {"owner": "authorized-tenancy-administrator", "reads_to_verify": unresolved,
                                  "recheck_command": recheck, "uses_default_config": default_config,
                                  "instruction": "Verify the selected identity, resource and region first. Review the listed permission only if the read is denied. Reuse the original private --config-file when one was supplied."}
    if store is not None and config["role"] == "rehearsal":
        value["launch_workflow"] = p.helper("sre_plan").launch_route(store, state, p)
    return value
