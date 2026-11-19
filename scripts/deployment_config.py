"""Prepare private deployment inputs from one explicitly selected environment.

Local proposals never authorize cloud operations. Credentials, application source
and existing Terraform input files are not changed or copied into the proposal.
"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
TARGET_REQUIRED = {"region", "profile", "auth", "compartment_id", "vcn_id", "app_subnet_id", "lb_subnet_id",
                   "app_private_ip", "certificate_id", "registry_id", "availability_domain", "image_digest",
                   "image_architecture", "origin", "port", "health_path", "ocpus", "memory_gbs"}
VARIABLE_REQUIRED = {"tenancy_ocid", "home_region", "name", "app_image", "registry", "allowed_ingress_cidrs", "application_contract"}
VARIABLE_OPTIONAL = {"public_environment", "secret_references", "dependency_egress"}
BACKEND = {"terraform": {"backend": {"oci": {}}}}


class ConfigurationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code="DEPLOYMENT_CONFIG_INPUT"):
    if not condition:
        raise ConfigurationError(code)


def field(value, pattern, maximum=512):
    return isinstance(value, str) and len(value) <= maximum and re.fullmatch(pattern, value) is not None


def reference(value, kind):
    return field(value, r"ocid1\." + kind + r"\.[a-z0-9_-]+\.[a-z0-9_-]*\.[a-z0-9]+")


def settings(value, env, e):
    require(isinstance(value, dict) and set(value) <= {"target", "variables"})
    patch, variables = value.get("target", {}), value.get("variables", {})
    require(isinstance(patch, dict) and isinstance(variables, dict)
            and set(variables) <= VARIABLE_REQUIRED | VARIABLE_OPTIONAL)
    # This handoff completes a selected target. Retargeting existing resources is
    # a separate backed-up environment operation, never an implicit patch.
    require(all(key not in env["target"] or env["target"][key] == item for key, item in patch.items()),
            "DEPLOYMENT_CONFIG_RETARGET")
    selected = dict(env, target={**env["target"], **patch})
    e.validate(selected)
    target = selected["target"]
    if "image_architecture" in target:
        require(target["image_architecture"] == "AMD64")
    if "tenancy_ocid" in variables:
        require(reference(variables["tenancy_ocid"], "tenancy"))
    if "home_region" in variables:
        require(field(variables["home_region"], r"[a-z]+-[a-z]+-[0-9]+"))
    if "name" in variables:
        require(field(variables["name"], r"[a-z][a-z0-9-]{2,30}"))
    if "registry" in variables:
        registry = variables["registry"]
        require(isinstance(registry, dict) and set(registry) == {"compartment_ocid", "repository_name"}
                and reference(registry["compartment_ocid"], "compartment")
                and field(registry["repository_name"], r"[a-z0-9]+(?:[._/-][a-z0-9]+)*", 255))
        require(registry["compartment_ocid"] == target.get("compartment_id"))
    if "app_image" in variables:
        require(field(variables["app_image"], r"[a-z0-9.-]+\.ocir\.io/[a-z0-9_-]+/[a-z0-9._/-]+@sha256:[0-9a-f]{64}"))
        require(variables["app_image"].rsplit("@", 1)[1] == target.get("image_digest"))
        if "registry" in variables:
            require(variables["app_image"].split("/", 2)[2].rsplit("@", 1)[0] == variables["registry"]["repository_name"])
    if "allowed_ingress_cidrs" in variables:
        cidrs = variables["allowed_ingress_cidrs"]
        require(isinstance(cidrs, list) and 1 <= len(cidrs) <= 32 and len(set(cidrs)) == len(cidrs))
        for cidr in cidrs:
            require(isinstance(cidr, str) and str(ipaddress.IPv4Network(cidr, strict=True)) == cidr)
    public = variables.get("public_environment", {})
    require(isinstance(public, dict) and len(public) <= 64)
    for key, item in public.items():
        require(field(key, r"[A-Z][A-Z0-9_]{0,63}")
                and not re.search(r"SECRET|PASSWORD|TOKEN|CREDENTIAL|KEY|AUTHORIZATION|DATABASE_URL|CONNECTION_STRING|^OCI_|^HOST$|^PORT$|^PUBLIC_ORIGIN$", key)
                and isinstance(item, str) and len(item) <= 2048
                and not re.search(r"[\r\n]|://[^/]*@|-----BEGIN", item))
    secrets = variables.get("secret_references", {})
    require(isinstance(secrets, dict) and len(secrets) <= 16)
    for key, ref in secrets.items():
        require(field(key, r"[A-Z][A-Z0-9_]*_SECRET_OCID") and not key.startswith("OCI_")
                and isinstance(ref, dict) and set(ref) == {"secret_ocid", "compartment_ocid"}
                and reference(ref["secret_ocid"], "vaultsecret") and reference(ref["compartment_ocid"], "compartment"))
    dependencies = variables.get("dependency_egress", {})
    require(isinstance(dependencies, dict) and len(dependencies) <= 16)
    for key, item in dependencies.items():
        require(field(key, r"[a-z][a-z0-9-]{0,40}") and isinstance(item, dict)
                and set(item) == {"destination_cidr", "port"} and type(item["port"]) is int and 1 <= item["port"] <= 65535)
        network = ipaddress.IPv4Network(item["destination_cidr"], strict=True)
        require(network.prefixlen >= 2)
    if "application_contract" in variables:
        contract = variables["application_contract"]
        require(isinstance(contract, dict) and {"evidence_sha256", "background_work"} <= set(contract)
                and set(contract) <= {"evidence_sha256", "background_work", "background_control_environment", "vault_references_implemented"}
                and field(contract["evidence_sha256"], r"[0-9a-f]{64}") and contract["background_work"] in {"absent", "disabled"})
        controls = contract.get("background_control_environment", {})
        require(isinstance(controls, dict) and len(controls) <= 32)
        require((contract["background_work"] == "absent" and not controls) or (contract["background_work"] == "disabled" and bool(controls)))
        for key, item in controls.items():
            require(field(key, r"[A-Z][A-Z0-9_]{0,63}") and not re.search(r"SECRET|PASSWORD|TOKEN|CREDENTIAL|KEY|^OCI_|^HOST$|^PORT$|^PUBLIC_ORIGIN$", key)
                    and item in {"false", "0", "off", "disabled", "web"})
        require(type(contract.get("vault_references_implemented", False)) is bool)
        if secrets:
            require(contract.get("vault_references_implemented") is True)
    return selected, variables


def inputs(env, variables):
    target = env["target"]
    values = dict(variables, compartment_ocid=target["compartment_id"], region=target["region"],
        config_file_profile=target["profile"], auth={"api_key": "APIKey", "security_token": "SecurityToken"}[target["auth"]],
        availability_domain=target["availability_domain"], certificate_ocid=target["certificate_id"],
        public_origin=target["origin"], app_port=target["port"], health_path=target["health_path"],
        app_ocpus=target["ocpus"], app_memory_gbs=target["memory_gbs"], manage_runtime_iam=False,
        network={"vcn_ocid": target["vcn_id"], "private_subnet_ocid": target["app_subnet_id"],
                 "public_subnet_ocid": target["lb_subnet_id"], "app_private_ip": target["app_private_ip"]})
    backend = dict(env["backend"], auth=values["auth"], config_file_profile=values["config_file_profile"])
    return values, backend


def infrastructure(store, p):
    path = store.project / store.environment_config["infrastructure"]
    _, fd = p.open_project(path)
    try:
        expected = {file.name: file.read_bytes() for file in (ROOT / "blueprints/web-container/terraform").glob("*.tf")}
        actual = {name for name in os.listdir(fd) if name.endswith((".tf", ".tf.json"))}
        require(actual in (set(expected), set(expected) | {"backend.tf.json"}), "DEPLOYMENT_CONFIG_SOURCE")
        require(all(p.read_at(fd, name) == raw for name, raw in expected.items()), "DEPLOYMENT_CONFIG_SOURCE")
        if "backend.tf.json" in actual:
            require(p.object_at(fd, "backend.tf.json") == BACKEND, "DEPLOYMENT_CONFIG_SOURCE")
        # Automatic Terraform inputs can override generated input or introduce
        # secrets. Existing files must be reviewed through the manual workflow.
        require(not any(name in {"terraform.tfvars", "terraform.tfvars.json"} or name.endswith((".auto.tfvars", ".auto.tfvars.json"))
                        for name in os.listdir(fd)), "DEPLOYMENT_CONFIG_EXISTING_INPUT")
        return {name: p.digest(raw) for name, raw in expected.items()}
    finally:
        os.close(fd)


def request(project, *, environment, action="inspect", config=None, approve=None):
    import importlib.util
    spec = importlib.util.spec_from_file_location("deployment_project", ROOT / "scripts/project.py")
    p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
    f, e = p.helper("foundation"), p.helper("environments")
    require(environment and action in {"inspect", "propose", "prepare"})
    with p.Store(project, environment=environment, write=action != "inspect") as store:
        state = store.read()
        env = store.environment_config
        require(env["role"] != "source" and env["blueprint"] == "web-container", "DEPLOYMENT_CONFIG_TARGET")
        current = p.digest(p.canonical(env))
        sources = infrastructure(store, p)
        source = p.source_fingerprint(store.root_fd)
        base = {"schema": "oci-kit-deployment-config/1", "environment": environment, "cloud": "not_checked",
                "approval_granted": False, "evidence_scope": "local-configuration-only"}
        if action in {"inspect", "propose"}:
            value = f.read_private(config, p) if config else {}
            selected, variables = settings(value, env, e)
            e.validate_isolation(selected, e.list_configs(store, p))
            missing = sorted((TARGET_REQUIRED - selected["target"].keys()) | (VARIABLE_REQUIRED - variables.keys()))
            if not selected.get("backend"):
                missing.append("backend")
            if action == "inspect":
                return dict(base, status="blocked" if missing else "configured", missing=missing,
                    next="Supply remaining nonsecret choices with release configure --config PRIVATE_JSON. Existing selections are reused.")
            packet = {"schema": "oci-kit-deployment-config-proposal/1", "environment": environment,
                      "binding": current, "project_identity": p.identity(store.root_fd), "created_at": int(time.time()),
                      "source_sha256": source, "kit_sha256": p.kit_fingerprint(), "sources": sources,
                      "configuration": selected, "variables": variables, "missing": missing}
            sha = p.digest(p.canonical(packet))
            f.save(store, "deployment-config-proposal.json", packet, p)
            return dict(base, status="blocked" if missing else "review", sha256=sha, missing=missing,
                private_review=".oci-kit/environments/" + environment + "/deployment-config-proposal.json",
                next="Review this local configuration, then use release configure --approve with its hash. Cloud plans require separate approval.")
        packet = p.object_at(store.fd, "deployment-config-proposal.json", private=True)
        require(isinstance(approve, str) and p.valid_hash(approve) and approve == p.digest(p.canonical(packet))
                and packet["schema"] == "oci-kit-deployment-config-proposal/1" and packet["environment"] == environment
                and packet["binding"] == current and not packet["missing"]
                and packet["project_identity"] == p.identity(store.root_fd) and packet["sources"] == sources
                and packet["source_sha256"] == source and packet["kit_sha256"] == p.kit_fingerprint()
                and type(packet["created_at"]) is int and 0 <= int(time.time()) - packet["created_at"] <= 3600,
                "DEPLOYMENT_CONFIG_STALE")
        selected = packet["configuration"]
        e.validate_isolation(selected, e.list_configs(store, p))
        values, backend = inputs(selected, packet["variables"])
        name = "deployment-" + approve[:16]
        # Keep interrupted artifacts visible and refuse adoption/overwrite. A
        # fresh proposal can be reviewed after inspecting any partial directory.
        os.mkdir(name, 0o700, dir_fd=store.fd)
        fd = os.open(name, p.DIRECTORY, dir_fd=store.fd)
        try:
            e.put(fd, "variables.json", p.canonical(values) + b"\n")
            e.put(fd, "backend.json", p.canonical(backend) + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        _, stack_fd = p.open_project(store.project / env["infrastructure"])
        try:
            try:
                existing = p.object_at(stack_fd, "backend.tf.json")
            except FileNotFoundError:
                e.put(stack_fd, "backend.tf.json", p.canonical(BACKEND) + b"\n")
            else:
                require(existing == BACKEND, "DEPLOYMENT_CONFIG_SOURCE")
            os.fsync(stack_fd)
        finally:
            os.close(stack_fd)
        # Existing backup/isolation rules; this does not copy checkpoint passes.
        f.bind(store, selected["target"], selected.get("backend"), p)
        directory = ".oci-kit/environments/" + environment + "/" + name
        result = dict(base, status="prepared", variables=directory + "/variables.json", backend=directory + "/backend.json",
                      previous_evidence="recheck-required", runtime_iam="separate-administrator-prerequisite",
                      next_command=["python3", str(ROOT / "scripts/kit.py"), "release", "init", "--project", str(store.project),
                                    "--environment", environment, "--backend-config", str(store.project / directory / "backend.json")])
        f.save(store, "deployment-config-result.json", result, p)
        return result
