"""Small shared boundaries for the lifecycle facade; no independent project state."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS = {
    "SRE_CHECK_INPUT": ("promotion", "release-owner", "Select a production environment, --rehearsal NAME and the saved --plan-sha256."),
    "SRE_PLAN_INPUT": ("testing", "app-owner", "Select a named rehearsal environment to inspect the application and create a test plan."),
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
    "ONBOARD_TARGET_CONFLICT": ("onboarding-selection", "founder", "Inspect the selected environment's existing infrastructure and role. Reuse the intended target or explicitly choose a separate environment; do not overwrite its bindings."),
    "ONBOARD_PROJECT_CONFLICT": ("onboarding-project", "founder", "Inspect the existing project choices and continue its saved task. Preserve source and progress; do not recreate the application to change onboarding selections."),
    "ONBOARD_UPDATE_REQUIRED": ("onboarding-installation", "agent", "Review the installed kit and use the documented update workflow from a separate reviewed release source. Preserve application files and existing records before retrying onboarding."),
    "ONBOARD_DESTINATION_EXISTS": ("onboarding-infrastructure", "agent", "Inspect the occupied infrastructure destination and any interrupted setup. Reuse only verified existing bindings or choose an unused directory; never delete or overwrite application files to make onboarding succeed."),
}
FOUNDATION_CHECKS = {"inherited_iam_isolation": "unknown", "certificate_keys": "not_read",
                     "dns_change": "separate-reviewed-operation", "network_overlap": "unknown",
                     "actual_capacity": "unknown"}
FOUNDATION_ADMIN_CHECKS = (
    "Verify operator authorization and inherited allow/deny policies; do not switch identity to bypass a deny.",
    "Review the exact component scope and separate runtime IAM before approving cloud changes.",
    "Verify inherited state access, bucket isolation, locking and recovery before uploading real Terraform state.",
    "Review VCN overlap, routes, subnet exposure, certificate ownership and scoped registry access; denied reads remain unknown.",
)

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
    ("DEPLOYMENT_CONFIG_INPUT", "deployment-configuration", "founder", "Review the missing nonsecret target and application choices in docs/DEPLOYMENT-CONFIGURATION.md. Credentials stay outside all Terraform inputs."),
    ("DEPLOYMENT_CONFIG_TARGET DEPLOYMENT_CONFIG_RETARGET", "deployment-selection", "owner", "Select an explicit web-container target. Preserve existing resource selections; a retarget requires the separate backed-up environment configuration workflow."),
    ("DEPLOYMENT_CONFIG_SOURCE DEPLOYMENT_CONFIG_EXISTING_INPUT", "deployment-source", "agent", "Inspect the existing infrastructure and Terraform inputs without replacing them. Automatic preparation requires reviewed blueprint sources and no automatic variable files; use the manual workflow for existing inputs."),
    ("DEPLOYMENT_CONFIG_STALE", "deployment-review", "owner", "Prepare and review a fresh local deployment configuration proposal after source, environment, kit or expiry changes. Its hash authorizes no cloud operation."),
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
               "vcn_id", "app_subnet_id", "lb_subnet_id", "app_private_ip", "certificate_id", "registry_id", "availability_domain",
               "developer_group_id", "access_role", "registry_name", "state_bucket_name", "administrator_profile", "administrator_auth"}
    return {"schema": "oci-kit-command/1", "status": "blocked", "error": {"code": code,
            "phase": phase, "owner": owner, "recoverable": True,
            "missing": sorted({name for name in missing if isinstance(name, str)} & allowed), "next_action": action},
            "approval_granted": False}


def project_blocked(value, *, code, command, action, environment):
    """Keep actionable foundation diagnostics without forwarding private helper data."""
    result = error(code, missing=value.get("missing", ()))
    if (command != "foundation" or action != "inspect"
            or value.get("schema") != "oci-kit-foundation/1"
            or value.get("status") != "blocked" or value.get("cloud") != "not_checked"
            or not isinstance(environment, str)
            or not project_module().helper("environments").NAME.fullmatch(environment)
            or value.get("environment") != environment):
        return result
    # Foundation inspection performs no cloud reads. Preserve only its fixed
    # narrow states, never a helper-supplied success claim or arbitrary message.
    observed = value.get("checks")
    if not isinstance(observed, dict):
        return result
    checks = {name: state for name, state in FOUNDATION_CHECKS.items() if observed.get(name) == state}
    result.update(environment=environment, cloud="not_checked", checks=checks,
                  guide="blueprints/workload-foundation/README.md")
    result["error"]["next_action"] = (
        "Review the missing private choices and existing approved resources using "
        "blueprints/workload-foundation/README.md. Ask the authorized administrator "
        "to resolve access and isolation checks before preparing separate component plans.")
    result["error"]["recheck_command"] = ["python3", ".oci-founder-kit/scripts/kit.py", "foundation", "inspect",
                                            "--project", ".", "--environment", environment]
    # Reconstruct the reviewed handoff. Input checks, paths, identifiers and
    # commands can contain private data and are never copied to this projection.
    result["administrator_handoff"] = {
        "owner": "authorized-tenancy-administrator",
        "checks": list(FOUNDATION_ADMIN_CHECKS),
        "recheck_command": ["python3", ".oci-founder-kit/scripts/kit.py", "doctor", "--project", ".",
                            "--environment", environment],
    }
    return result


def render_blocked_details(value):
    """Render only reviewed diagnostic vocabulary in the readable CLI mode."""
    if value.get("cloud") != "not_checked" or value.get("guide") != "blueprints/workload-foundation/README.md":
        return
    checks = value.get("checks")
    if isinstance(checks, dict):
        for name, state in FOUNDATION_CHECKS.items():
            if checks.get(name) == state:
                print(f"{name}: {state}")
    handoff = value.get("administrator_handoff")
    if isinstance(handoff, dict) and handoff.get("owner") == "authorized-tenancy-administrator":
        instructions = handoff.get("checks")
        if isinstance(instructions, list):
            print("Administrator review:")
            for instruction in FOUNDATION_ADMIN_CHECKS:
                if instruction in instructions:
                    print("- " + instruction)


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
