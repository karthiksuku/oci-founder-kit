"""Small shared boundaries for the lifecycle facade; no independent project state."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS = {
    "PROJECT_REQUIRED": ("setup", "founder", "Open the intended existing application folder or use start --mode new."),
    "INSTALLATION_REQUIRED": ("setup", "agent", "Inspect this project and initialize it with start --mode existing."),
    "ENVIRONMENT_REQUIRED": ("selection", "founder", "Select --environment explicitly; saved preferences never select production."),
    "ENVIRONMENT_UNKNOWN": ("selection", "founder", "List existing environments or create a separate named environment."),
    "INPUTS_REQUIRED": ("configuration", "founder", "Supply the listed nonsecret choices together in private configuration."),
    "UNSAFE_INPUT": ("validation", "agent", "Review private input format, ownership, symlinks and interrupted operations; preserve existing files."),
    "CAPABILITY_UNAVAILABLE": ("compatibility", "agent", "Review the installed capability registry and update the kit through its supported updater."),
    "EVIDENCE_REQUIRED": ("verification", "agent", "Collect current evidence for the selected source, target and image before continuing."),
    "APPROVAL_REQUIRED": ("approval", "owner", "Review the exact current plan; only its approved hash authorizes the gated operation."),
    "OPERATION_FAILED": ("operation", "agent", "Inspect the private attempt and current state before a new plan or retry."),
}

# Only reviewed codes and fixed instructions cross the public CLI boundary.
# Never forward an exception's free-form recovery/message or arbitrary fields.
for codes, phase, owner, recovery in (
    ("PACKAGE_DESCRIPTOR PACKAGE_DESCRIPTOR_REQUIRED PACKAGE_COMMANDS PACKAGE_DEPENDENCIES PACKAGE_ENTRYPOINT PACKAGE_RUNTIME PACKAGE_INPUT_MISSING", "packaging-configuration", "founder", "Complete the private application descriptor's missing choices, then run package propose with that descriptor."),
    ("PACKAGE_PATH PACKAGE_DESTINATION_EXISTS PACKAGE_NESTED_DOCKERFILE PACKAGE_DOCKERFILE_REQUIRED", "packaging-source", "agent", "Review the existing application paths and Dockerfile. Keep source files intact and choose an unused additive packaging destination."),
    ("PACKAGE_BASE_DIGEST PACKAGE_UNPINNED_FROM PACKAGE_LOCKED_REQUIREMENTS PACKAGE_NEXT_DEPENDENCY PACKAGE_STANDALONE_REQUIRED", "packaging-compatibility", "agent", "Review the recipe prerequisites, locked dependencies and immutable base image, then prepare a fresh packaging proposal."),
    ("PACKAGE_ARCHITECTURE PACKAGE_IMAGE_INPUT PACKAGE_IMAGE_CHANGED PACKAGE_SCAN_LIMIT PACKAGE_HEALTH PACKAGE_INPUT_OR_CHECK_FAILED", "packaging-verification", "agent", "Review the exact local Linux AMD64 image, private v2s2 layout, credential findings and health check, then repeat package verify."),
    ("PACKAGE_CHANGED PACKAGE_STALE_PROPOSAL", "packaging-review", "owner", "Prepare a new packaging proposal after source or input changes and approve only its exact current hash."),
    ("PACKAGE_CLEANUP", "packaging-cleanup", "agent", "Inspect the retained local test container and its evidence before scoped removal or another test."),
    ("PACKAGE_ENVIRONMENT PACKAGE_SOURCE PACKAGE_ACTION FOUNDATION_ENVIRONMENT FOUNDATION_SOURCE FOUNDATION_ACTION", "selection", "founder", "Select an explicit OCI target environment and the documented operation; retained source hosting cannot be selected for OCI deployment work."),
    ("FOUNDATION_CONFIG FOUNDATION_MODE FOUNDATION_CREATE FOUNDATION_REUSE FOUNDATION_CIDR FOUNDATION_REGION FOUNDATION_BACKEND FOUNDATION_CERTIFICATE FOUNDATION_WORKSPACE", "foundation-configuration", "founder", "Complete the private foundation choices, selected region/backend and certificate renewal owner; inspect existing resources before preparing a proposal."),
    ("FOUNDATION_BOUNDARY FOUNDATION_STATE_BOUNDARY", "foundation-isolation", "administrator", "Select dedicated non-root workload and state compartments and obtain authorized review of inherited IAM before continuing."),
    ("FOUNDATION_CHANGED FOUNDATION_STALE_PROPOSAL", "foundation-review", "owner", "Prepare and review a new local foundation proposal; source changes invalidate old hashes and cloud approvals remain separate."),
    ("FOUNDATION_OUTPUTS FOUNDATION_OUTPUT_BINDING FOUNDATION_OUTPUT_FIELDS FOUNDATION_OUTPUT_TARGET FOUNDATION_STALE_OUTPUT FOUNDATION_BACKEND_BINDING FOUNDATION_INPUT_OR_HANDOFF_FAILED", "foundation-handoff", "agent", "Inspect private output from the exact prepared component and its separately approved apply; recheck environment, proposal and backend bindings before importing it."),
):
    for code in codes.split():
        ERRORS[code] = (phase, owner, recovery)


def project_module():
    spec = importlib.util.spec_from_file_location("oci_kit_project", ROOT / "scripts/project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KitError(ValueError):
    def __init__(self, code, *, missing=()):
        self.code = code if code in ERRORS else "UNSAFE_INPUT"
        self.missing = tuple(missing)
        super().__init__(self.code)


def error(code, *, missing=()):
    if code not in ERRORS:
        code = "UNSAFE_INPUT"
    phase, owner, action = ERRORS[code]
    allowed = {"environment", "role", "infrastructure", "recipe", "descriptor", "backend", "receipt",
               "evidence", "approval", "target", "image", "region", "compartment_id", "profile", "auth",
               "image_digest", "origin", "port", "health_path", "resource_map", "ledger", "app_directory", "commands",
               "dependencies", "background_work", "probe_runtime", "workspace", "component", "name", "home_region",
               "tenancy_id", "parent_compartment_id", "state_compartment_id", "vcn_cidr", "namespace", "state_key",
               "workspace_key_prefix", "environment.compartment_id", "certificate_renewal_owner", "domain_ownership",
               "vcn_id", "app_subnet_id", "lb_subnet_id", "certificate_id", "registry_id", "availability_domain"}
    return {"schema": "oci-kit-command/1", "status": "blocked", "error": {"code": code,
            "phase": phase, "owner": owner, "recoverable": True,
            "missing": sorted({name for name in missing if isinstance(name, str)} & allowed), "next_action": action},
            "approval_granted": False}


def configurations(project):
    p = project_module()
    try:
        with p.Store(project) as store:
            store.read()
            return p.helper("environments").list_configs(store, p)
    except FileNotFoundError:
        raise KitError("INSTALLATION_REQUIRED") from None


def select(project, environment, *, required=False):
    configs = configurations(project)
    if environment is None:
        if configs or required:
            raise KitError("ENVIRONMENT_REQUIRED", missing=("environment",))
        return None
    result = next((item for item in configs if item["name"] == environment), None)
    if result is None:
        raise KitError("ENVIRONMENT_UNKNOWN", missing=("environment",))
    return result


def bound(store, p, schema):
    return {"schema": schema, "environment": store.environment,
            "target_sha256": p.digest(p.canonical(store.environment_config)),
            "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint()}


def current(value, store, p, *, age=86400):
    import time
    observed = value.get("observed_at")
    return (all(value.get(key) == wanted for key, wanted in bound(store, p, value.get("schema")).items())
            and type(observed) is int and 0 <= time.time() - observed <= age)


def private_json(path):
    p = project_module()
    path = Path(path).expanduser().absolute()
    _, fd = p.open_project(path.parent)
    try:
        return p.object_at(fd, path.name, private=True)
    finally:
        os.close(fd)
