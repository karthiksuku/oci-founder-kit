#!/usr/bin/env python3
"""Prepare isolated foundation stacks and import their private nonsecret outputs.

No OCI requests or Terraform commands run. Each cloud stage requires the existing
gate's fresh exact plan and owner approval.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("compartments", "network", "state", "registry")
INPUTS = {"workspace", "component", "name", "region", "home_region", "profile", "auth", "tenancy_id",
          "parent_compartment_id", "state_compartment_id", "vcn_cidr", "namespace", "state_key", "workspace_key_prefix"}
COMMON = {"workspace", "component", "name", "region", "profile", "auth", "tenancy_id"}
EXTRA = {"compartments": {"parent_compartment_id", "home_region"}, "network": {"vcn_cidr"},
         "state": {"state_compartment_id", "namespace", "state_key", "workspace_key_prefix"}, "registry": set()}


class FoundationError(ValueError):
    def __init__(self, code, recovery):
        self.code, self.recovery = code, recovery
        super().__init__(recovery)


def project_module():
    spec = importlib.util.spec_from_file_location("oci_foundation_project", ROOT / "scripts/project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_private(path, p):
    path = Path(path).expanduser().absolute()
    _, fd = p.open_project(path.parent)
    try:
        return p.object_at(fd, path.name, private=True)
    finally:
        os.close(fd)


def save(store, name, value, p):
    temporary = ".foundation-" + uuid.uuid4().hex
    try:
        store.create_file(temporary, p.canonical(value) + b"\n")
        os.replace(temporary, name, src_dir_fd=store.fd, dst_dir_fd=store.fd)
        os.fsync(store.fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=store.fd)


def optional(store, name, p):
    try:
        return p.object_at(store.fd, name, private=True)
    except FileNotFoundError:
        return {}


def choices(value, env, p):
    if not isinstance(value, dict) or set(value) - (INPUTS | {"mode", "target", "backend", "certificate"}):
        raise FoundationError("FOUNDATION_CONFIG", "Use only documented foundation choices; credentials and policy text are not accepted.")
    if value.get("mode") not in {"reuse", "create"}:
        raise FoundationError("FOUNDATION_MODE", "Inspect approved resources first, then explicitly select reuse or create.")
    if value["mode"] == "reuse":
        target, backend = value.get("target", env["target"]), value.get("backend", env.get("backend"))
        p.helper("environments").validate(dict(env, target=target, backend=backend))
        if set(value) - {"mode", "target", "backend", "certificate"}:
            raise FoundationError("FOUNDATION_REUSE", "Reuse accepts selected target, backend and certificate responsibility only.")
    else:
        if set(value) - INPUTS - {"mode", "certificate"}:
            raise FoundationError("FOUNDATION_CREATE", "Creation uses the selected environment target and explicit component inputs.")
        for key, item in value.items():
            if key in {"mode", "certificate"}:
                continue
            if not isinstance(item, str) or not item or len(item) > 512 or any(ord(c) < 32 for c in item):
                raise FoundationError("FOUNDATION_CONFIG", "Use bounded nonsecret string choices.")
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/deploy_gate.py")
        patterns = {"component": "(?:compartments|network|state|registry)", "name": "[a-z][a-z0-9-]{2,24}",
                    "region": gate.REGION.pattern, "home_region": gate.REGION.pattern,
                    "profile": "[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", "auth": "(?:api_key|security_token)",
                    "namespace": "[a-z0-9]{1,64}"}
        for key, pattern in patterns.items():
            if key in value and not re.fullmatch(pattern, value[key]):
                raise FoundationError("FOUNDATION_CONFIG", "Correct the " + key + " format in private foundation choices; use the deployment gate's supported format (profiles: 1-64 characters).")
        references = [(key, kind, value.get(key)) for key, kind in
                      (("tenancy_id", "tenancy"), ("parent_compartment_id", "compartment"), ("state_compartment_id", "compartment"))]
        if value.get("component") in {"network", "registry"}:
            references.append(("environment.compartment_id", "compartment", env["target"].get("compartment_id")))
        for key, kind, reference in references:
            if reference is None:
                continue
            match = gate.OCID.fullmatch(reference)
            if not match or not reference.startswith("ocid1." + kind + ".") or (kind == "tenancy" and match.group(1)):
                raise FoundationError("FOUNDATION_BOUNDARY", "Correct " + key + " in private configuration; select the expected tenancy or a dedicated non-root compartment.")
        if value.get("state_compartment_id") and value["state_compartment_id"] == env["target"].get("compartment_id"):
            raise FoundationError("FOUNDATION_STATE_BOUNDARY", "Use a separate state compartment; private access does not override inherited IAM.")
        if "vcn_cidr" in value:
            network = ipaddress.ip_network(value["vcn_cidr"], strict=True)
            private = [ipaddress.ip_network(c) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
            if network.version != 4 or network.prefixlen != 16 or not any(network.subnet_of(x) for x in private):
                raise FoundationError("FOUNDATION_CIDR", "Select a reviewed nonoverlapping RFC1918 IPv4 /16.")
        if value.get("region") and env["target"].get("region") and value["region"] != env["target"]["region"]:
            raise FoundationError("FOUNDATION_REGION", "Foundation and selected environment must use the same region.")
        if all(key in value for key in ("namespace", "state_key", "workspace_key_prefix", "region", "name")):
            try:
                p.helper("environments").validate_backend({"region": value["region"], "namespace": value["namespace"],
                    "bucket": value["name"] + "-" + env["name"] + "-tfstate", "key": value["state_key"], "workspace_key_prefix": value["workspace_key_prefix"]})
            except Exception:
                raise FoundationError("FOUNDATION_BACKEND", "Select a valid .tfstate key and separate workspace prefix in the explicit private backend.") from None
    certificate = value.get("certificate")
    if certificate is not None:
        if (not isinstance(certificate, dict) or set(certificate) != {"hostname", "renewal_owner", "ownership"}
                or not isinstance(certificate["hostname"], str)
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", certificate["hostname"])
                or "." not in certificate["hostname"]
                or certificate["ownership"] not in {"unverified", "verified-by-owner"}
                or not isinstance(certificate["renewal_owner"], str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", certificate["renewal_owner"])):
            raise FoundationError("FOUNDATION_CERTIFICATE", "Record the hostname, a nonsecret renewal role and explicit domain-ownership status; never private keys.")
    return value


def workspace(value, project, p):
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise FoundationError("FOUNDATION_WORKSPACE", "Select an existing private absolute workspace outside every application project.")
    path, fd = p.open_project(path)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise FoundationError("FOUNDATION_WORKSPACE", "The bootstrap workspace must be private and owned (0700).")
        project = Path(project).absolute()
        if path == project or project in path.parents or path in project.parents:
            raise FoundationError("FOUNDATION_WORKSPACE", "Keep bootstrap infrastructure outside the application and its ancestors.")
        for parent in (path, *path.parents):
            if (parent / ".oci-kit").exists():
                raise FoundationError("FOUNDATION_WORKSPACE", "Select a workspace outside projects with named environment records.")
        return path, p.identity(fd)
    finally:
        os.close(fd)


def templates(component, p):
    _, fd = p.open_project(ROOT / "blueprints/workload-foundation" / component)
    try:
        return {name: p.read_at(fd, name).decode() for name in ("main.tf", "versions.tf", ".gitignore", ".terraform.lock.hcl")}
    finally:
        os.close(fd)


def tfvars(value, env, sha):
    component = value["component"]
    result = {"region": value["region"], "config_file_profile": value["profile"], "tenancy_ocid": value["tenancy_id"],
              "auth": {"api_key": "APIKey", "security_token": "SecurityToken"}[value["auth"]],
              "environment": env["name"], "name": value["name"], "request_sha256": sha}
    if component == "compartments":
        result.update(home_region=value["home_region"], compartment_ocid=value["parent_compartment_id"])
    else:
        result["compartment_ocid"] = value["state_compartment_id"] if component == "state" else env["target"]["compartment_id"]
    if component == "network":
        result["vcn_cidr"] = value["vcn_cidr"]
    if component == "state":
        result.update(namespace=value["namespace"], state_key=value["state_key"], workspace_key_prefix=value["workspace_key_prefix"])
    return result


def bind(store, target, backend, p):
    """Apply environment.configure's backup/isolation rules under our existing lock."""
    e = p.helper("environments")
    config = dict(store.environment_config, target=target, backend=backend)
    e.validate_isolation(config, e.list_configs(store, p))
    original = p.read_at(store.fd, "environment.json", private=True)
    e.put(store.fd, "environment-backup-" + uuid.uuid4().hex + ".json", original)
    save(store, "environment.json", config, p)
    store.environment_config = config


def inspect(store, p):
    config = store.environment_config
    required = {"region", "compartment_id", "vcn_id", "app_subnet_id", "lb_subnet_id", "app_private_ip", "registry_id", "certificate_id"}
    missing = sorted(required - config["target"].keys())
    if not config.get("backend"):
        missing.append("backend")
    settings = optional(store, "foundation-settings.json", p)
    certificate = settings.get("certificate", {})
    if not certificate.get("renewal_owner"):
        missing.append("certificate_renewal_owner")
    if certificate.get("ownership") != "verified-by-owner":
        missing.append("domain_ownership")
    return {"schema": "oci-kit-foundation/1", "status": "blocked" if missing else "configured", "environment": store.environment,
            "missing": missing, "next": "inspect-existing-resources-then-propose", "cloud": "not_checked",
            "checks": {"inherited_iam_isolation": "unknown", "certificate_keys": "not_read", "dns_change": "separate-reviewed-operation",
                       "network_overlap": "unknown", "actual_capacity": "unknown"},
            "administrator_handoff": {"owner": "authorized-tenancy-administrator", "checks": [
                "Verify selected operator authorization and inherited allow/deny policies; never switch identity to bypass a deny.",
                "Authorize only the selected component plan in its dedicated compartment; runtime IAM is a separate reviewed operation.",
                "Review state compartment inherited access, bucket isolation, lock behavior and recovery before any real Terraform state upload.",
                "Inspect VCN routes, subnet exposure, nonoverlap, certificate metadata and scoped OCIR access; denied reads remain unknown."],
                "recheck": ".oci-founder-kit/scripts/oci-kit doctor --environment " + store.environment}}


def request(project: Path, *, environment: str, action="inspect", config=None, approve=None, outputs=None):
    if not environment:
        raise FoundationError("FOUNDATION_ENVIRONMENT", "Select a named environment explicitly; legacy progress is never selected.")
    if action not in {"inspect", "propose", "prepare", "handoff"}:
        raise FoundationError("FOUNDATION_ACTION", "Select inspect, propose, prepare or handoff.")
    p = project_module()
    with p.Store(project, environment=environment, write=action != "inspect") as store:
        store.read()
        env = store.environment_config
        if env["role"] == "source":
            raise FoundationError("FOUNDATION_SOURCE", "Select an explicit OCI rehearsal or production environment.")
        binding = p.digest(p.canonical(env))
        if action == "inspect":
            return inspect(store, p)
        if action == "propose":
            saved = optional(store, "foundation-settings.json", p)
            incoming = read_private(config, p) if config else saved
            if incoming.get("mode") == "create":
                # Reuse validated private choices and prior component outputs. Explicit input wins.
                previous = saved if saved.get("mode") == "create" else {}
                selected = {key: env["target"][key] for key in ("region", "profile", "auth") if key in env["target"]}
                incoming = {**previous, **selected, **incoming}
            value = choices(incoming, env, p)
            missing, source, workspace_identity = [], {}, None
            if value["mode"] == "create":
                missing = sorted((COMMON | EXTRA.get(value.get("component"), set())) - value.keys())
                if value.get("component") in {"network", "registry"} and not env["target"].get("compartment_id"):
                    missing.append("environment.compartment_id")
                if not missing:
                    _, workspace_identity = workspace(value["workspace"], project, p)
                    source = templates(value["component"], p)
                    tfvars(value, env, "0" * 64)
            packet = {"schema": "oci-kit-foundation-proposal/1", "environment": environment, "binding": binding,
                      "project_identity": p.identity(store.root_fd), "created_at": int(time.time()), "config": value,
                      "workspace_identity": workspace_identity, "sources": source, "missing": missing}
            sha = p.digest(p.canonical(packet))
            save(store, "foundation-proposal.json", packet, p)
            save(store, "foundation-settings.json", value, p)
            return {"schema": "oci-kit-foundation/1", "status": "blocked" if missing else "review", "environment": environment,
                    "mode": value["mode"], "component": value.get("component"), "sha256": sha, "missing": missing,
                    "files": sorted(source), "next": "prepare", "cloud": "not_checked", "costs": "unknown; obtain dated estimate for the exact cloud plan",
                    "scope": "Review local scaffold/configuration only. This hash never authorizes Terraform or OCI changes."}
        if action == "prepare":
            packet = p.object_at(store.fd, "foundation-proposal.json", private=True)
            if (not isinstance(approve, str) or approve != p.digest(p.canonical(packet)) or packet["binding"] != binding
                    or packet["environment"] != environment or packet["missing"]
                    or packet["project_identity"] != p.identity(store.root_fd)
                    or not 0 <= int(time.time()) - packet["created_at"] <= 3600):
                raise FoundationError("FOUNDATION_STALE_PROPOSAL", "Prepare and review a fresh foundation proposal for the selected environment.")
            value = choices(packet["config"], env, p)
            if value["mode"] == "reuse":
                bind(store, value.get("target", env["target"]), value.get("backend", env.get("backend")), p)
                return {"schema": "oci-kit-foundation/1", "status": "configured", "environment": environment,
                        "mode": "reuse", "previous_evidence": "stale", "approvals_imported": False, "cloud": "not_checked", "next": "doctor"}
            destination, identity = workspace(value["workspace"], project, p)
            if identity != packet["workspace_identity"] or templates(value["component"], p) != packet["sources"]:
                raise FoundationError("FOUNDATION_CHANGED", "Workspace or source templates changed; prepare a fresh proposal.")
            variables = tfvars(value, env, approve)
            _, parent = p.open_project(destination)
            name = environment + "-" + value["component"] + "-" + approve[:12]
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
                fd = os.open(name, p.DIRECTORY, dir_fd=parent)
                try:
                    for filename, content in packet["sources"].items():
                        p.helper("environments").put(fd, filename, content.encode())
                    p.helper("environments").put(fd, "terraform.tfvars.json", p.canonical(variables) + b"\n")
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                os.close(parent)
            stages = optional(store, "foundation-stages.json", p)
            stages[value["component"]] = {"sha256": approve, "binding": binding, "directory": str(destination / name),
                "region": value["region"], "variables": variables, "sources": packet["sources"], "handed_off": False}
            save(store, "foundation-stages.json", stages, p)
            gate = str(ROOT / "skills/oci-deploy/scripts/deploy_gate.py")
            return {"schema": "oci-kit-foundation/1", "status": "prepared", "environment": environment, "component": value["component"],
                    "directory": str(destination / name), "cloud": "not_checked", "next": "review-exact-cloud-plan",
                    "plan_command": ["python3", gate, "plan", "--dir", str(destination / name)],
                    "scope": "Local source and private variables only. No IAM policy, certificate private key, cloud operation or approval is created."}
        return handoff(store, outputs, binding, p)


def handoff(store, outputs, binding, p):
    if outputs is None:
        raise FoundationError("FOUNDATION_OUTPUTS", "Provide private Terraform output JSON from the prepared component after its separately approved apply.")
    raw = read_private(outputs, p)
    if set(raw) != {"foundation"} or not isinstance(raw["foundation"], dict) or raw["foundation"].get("sensitive") is not False:
        raise FoundationError("FOUNDATION_OUTPUTS", "Use bounded terraform output -json from the prepared stage; secret outputs are refused.")
    output, env, environment = raw["foundation"].get("value"), store.environment_config, store.environment
    required = {"schema", "component", "environment", "request_sha256", "region", "target", "private"}
    if (not isinstance(output, dict) or not required.issubset(output) or set(output) - required - {"backend"}
            or output["schema"] != "oci-kit-foundation-output/1" or output["environment"] != environment
            or output["component"] not in COMPONENTS):
        raise FoundationError("FOUNDATION_OUTPUT_BINDING", "Output must belong to the selected environment and prepared component.")
    stages = optional(store, "foundation-stages.json", p)
    stage = stages.get(output["component"])
    if (not stage or stage["handed_off"] or output["request_sha256"] != stage["sha256"] or stage["binding"] != binding
            or output["region"] != stage["region"]):
        raise FoundationError("FOUNDATION_STALE_OUTPUT", "Output is stale, already imported or belongs to another proposal; inspect the current component and environment.")
    _, fd = p.open_project(Path(stage["directory"]))
    try:
        if any(p.read_at(fd, key).decode() != content for key, content in stage["sources"].items()) or p.object_at(fd, "terraform.tfvars.json", private=True) != stage["variables"]:
            raise FoundationError("FOUNDATION_CHANGED", "Prepared infrastructure or private variables changed; review before importing outputs.")
    finally:
        os.close(fd)
    expected = {"compartments": {"compartment_id"}, "network": {"compartment_id", "vcn_id", "app_subnet_id", "lb_subnet_id", "app_private_ip"},
                "state": set(), "registry": {"compartment_id", "registry_id"}}
    if not isinstance(output["target"], dict) or set(output["target"]) != expected[output["component"]]:
        raise FoundationError("FOUNDATION_OUTPUT_FIELDS", "Only the prepared component's allowlisted outputs can be imported.")
    if output["component"] != "compartments" and output["target"].get("compartment_id", env["target"].get("compartment_id")) != env["target"].get("compartment_id"):
        raise FoundationError("FOUNDATION_OUTPUT_TARGET", "Component output cannot switch the selected application compartment.")
    private = output["private"]
    if not isinstance(private, dict) or set(private) != ({"state_compartment_id"} if output["component"] == "compartments" else set()):
        raise FoundationError("FOUNDATION_OUTPUT_FIELDS", "Unexpected private output fields are refused.")
    settings = optional(store, "foundation-settings.json", p)
    if private:
        choices({"mode": "create", "state_compartment_id": private["state_compartment_id"]}, dict(env, target=output["target"]), p)
        settings.update(private)
    backend, variables = env.get("backend"), stage["variables"]
    if output["component"] == "state":
        expected_backend = {"region": stage["region"], "namespace": variables["namespace"],
            "bucket": variables["name"] + "-" + environment + "-tfstate", "key": variables["state_key"], "workspace_key_prefix": variables["workspace_key_prefix"]}
        if output.get("backend") != expected_backend:
            raise FoundationError("FOUNDATION_BACKEND_BINDING", "State outputs differ from the exact prepared destination.")
        backend = output["backend"]
    elif "backend" in output:
        raise FoundationError("FOUNDATION_OUTPUT_FIELDS", "Only the state component can bind a backend.")
    target = dict(env["target"], **output["target"], region=output["region"])
    target.update(profile=variables["config_file_profile"], auth={"APIKey": "api_key", "SecurityToken": "security_token"}[variables["auth"]])
    bind(store, target, backend, p)
    stage["handed_off"] = True
    save(store, "foundation-stages.json", stages, p)
    save(store, "foundation-settings.json", settings, p)
    return {"schema": "oci-kit-foundation/1", "status": "configured", "environment": environment,
            "component": output["component"], "previous_evidence": "stale", "approvals_imported": False,
            "evidence_scope": "owner-supplied-output", "cloud": "not_checked", "next": "doctor",
            "scope": "Private outputs mapped without manual identifier copying. This is configuration, not evidence of live security or successful deployment."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "propose", "prepare", "handoff"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--approve")
    parser.add_argument("--outputs", type=Path)
    args = parser.parse_args(argv)
    try:
        result = request(**vars(args))
        print(json.dumps(result, indent=2))
        return 2 if result["status"] == "blocked" else 0
    except Exception:
        print(json.dumps({"status": "blocked", "code": "FOUNDATION_INPUT_OR_HANDOFF_FAILED", "recovery": "Review private inputs, selected environment and foundation guide. No cloud operation ran."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
