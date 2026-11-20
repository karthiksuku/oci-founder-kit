"""Conservative evaluated-plan checks for the two flat, reviewed workload blueprints."""

from __future__ import annotations

import os
import json
from pathlib import Path
import re

import backend_config
import image_gate as files

ROOT = Path(__file__).resolve().parents[3]
CI = "oci_container_instances_container_instance"
OCI = "registry.terraform.io/oracle/oci"
WORKLOAD = {CI, "oci_load_balancer_load_balancer", "oci_core_network_security_group", "oci_core_vcn",
            "oci_core_subnet", "oci_core_internet_gateway", "oci_core_nat_gateway", "oci_core_service_gateway",
            "oci_core_route_table", "oci_core_security_list", "oci_psql_db_system", "oci_objectstorage_bucket",
            "oci_health_checks_http_monitor", "oci_ons_notification_topic", "oci_ons_subscription", "oci_monitoring_alarm",
            "oci_apigateway_gateway", "oci_apigateway_deployment", "oci_queue_queue"}
PARENTS = {"oci_load_balancer_backend_set": ("load_balancer_id", "oci_load_balancer_load_balancer"),
           "oci_load_balancer_backend": ("load_balancer_id", "oci_load_balancer_load_balancer"),
           "oci_load_balancer_listener": ("load_balancer_id", "oci_load_balancer_load_balancer"),
           "oci_core_network_security_group_security_rule": ("network_security_group_id", "oci_core_network_security_group")}


def sources(stack, blueprint):
    """Named targets use reviewed Terraform bytes; app code and private variables stay editable."""
    directory = backend_config._open_directory(Path(stack))
    try:
        template = ROOT / "blueprints" / blueprint / "terraform"
        expected = {path.name: path.read_bytes() for path in sorted(template.glob("*.tf"))}
        actual = {name for name in backend_config._sources(directory) if name.endswith((".tf", ".tf.json"))}
        files.require(actual == set(expected) | {"backend.tf.json"},
                      "Named workloads require the reviewed blueprint Terraform files plus the canonical backend. Customized infrastructure needs separate review.")
        for name, raw in expected.items():
            files.require(backend_config._read_at(directory, name) == raw,
                          "Named workload Terraform sources differ from the reviewed blueprint. Customize private variables; review infrastructure edits separately.")
        files.require(backend_config._json(backend_config._read_at(directory, "backend.tf.json")) ==
                      {"terraform": {"backend": {"oci": {}}}}, "Use the canonical empty OCI backend declaration.")
        declarations = {}
        for raw in expected.values():
            for mode, kind, name in re.findall(rb'^(resource|data) "([^"]+)" "([^"]+)"', raw, re.MULTILINE):
                address = ("data." if mode == b"data" else "") + kind.decode() + "." + name.decode()
                declarations[address] = {"mode": "data" if mode == b"data" else "managed", "type": kind.decode()}
        return declarations
    except (OSError, ValueError, backend_config.BackendConfigError, RecursionError):
        raise files.ImageGateError("Named workload Terraform sources are unreadable or unsupported.") from None
    finally:
        os.close(directory)


def resources(section):
    files.require(isinstance(section, dict) and isinstance(section.get("root_module"), dict),
                  "The saved plan lacks evaluated workload values.")
    root = section["root_module"]
    files.require(not root.get("child_modules"), "Named workload verification supports flat blueprints only.")
    result = root.get("resources", [])
    files.require(isinstance(result, list) and len(result) <= 1000, "Invalid evaluated workload resources.")
    return result


def verify(plan, stack, binding, kind):
    try:
        return _verify(plan, stack, binding, kind)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        raise files.ImageGateError("Malformed or incomplete evaluated workload plan; review it privately and prepare a fresh plan.") from None


def _verify(plan, stack, binding, kind):
    if binding is None:
        return None
    declarations = sources(stack, binding["blueprint"])
    target = binding["target"]
    digest = target.get("image_digest")
    files.require(isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest),
                  "Select an immutable image digest before preparing a named workload resource plan.")
    configuration = plan.get("configuration") or {}
    providers = configuration.get("provider_config")
    root = configuration.get("root_module")
    allowed = {"oci", "oci.home"} | ({"random"} if binding["blueprint"] == "fullstack-container" else set())
    files.require(isinstance(providers, dict) and {"oci", "oci.home"}.issubset(providers)
                  and set(providers).issubset(allowed) and isinstance(root, dict)
                  and not root.get("module_calls"), "Unsupported provider or module configuration in the named workload plan.")
    for key in ("oci", "oci.home"):
        provider = providers[key]
        expected = {"region": {"references": ["var.home_region" if key == "oci.home" else "var.region"]},
                    "config_file_profile": {"references": ["var.config_file_profile"]},
                    "tenancy_ocid": {"references": ["var.tenancy_ocid"]}, "auth": {"references": ["var.auth"]}}
        files.require(isinstance(provider, dict) and provider.get("full_name") == OCI
                      and not provider.get("module_address") and provider.get("expressions") == expected
                      and provider.get("alias") == ("home" if key == "oci.home" else None),
                      "The saved provider configuration does not match the reviewed workload definition.")
    if "random" in providers:
        provider = providers["random"]
        files.require(isinstance(provider, dict) and provider.get("full_name") == "registry.terraform.io/hashicorp/random"
                      and not provider.get("module_address") and not provider.get("alias") and not provider.get("expressions"),
                      "Unexpected random-provider configuration.")
    configured = {}
    for resource in root.get("resources", []):
        files.require(isinstance(resource, dict) and isinstance(resource.get("address"), str)
                      and not resource.get("provisioners"), "Invalid configured resource in the named plan.")
        files.require(resource["address"] not in configured, "Duplicate configured resource address.")
        declared = declarations.get(resource["address"])
        files.require(isinstance(declared, dict) and declared["type"] == resource.get("type")
                      and declared["mode"] == resource.get("mode", "managed"),
                      "A configured resource is outside the reviewed blueprint inventory.")
        kind_name, provider_key = resource.get("type", ""), resource.get("provider_config_key")
        files.require(isinstance(kind_name, str) and (
            kind_name.startswith("oci_") and (provider_key == "oci" or provider_key == "oci.home" and kind_name.startswith("oci_identity_"))
            or kind_name == "random_password" and binding["blueprint"] == "fullstack-container" and provider_key == "random"),
            "The configured resource uses an unsupported provider or region alias.")
        configured[resource["address"]] = resource
    changes = plan.get("resource_changes")
    files.require(isinstance(changes, list), "The saved plan lacks explicit resource changes.")
    changes_by_address = {resource.get("address"): resource.get("change") or {} for resource in changes}
    planned = resources(plan.get("planned_values"))
    previous_section = (plan.get("prior_state") or {}).get("values")
    previous = resources(previous_section) if previous_section else []
    parent_ids = {"before": {}, "after": {}}

    def add_parent(resource, values, phase):
        kind_name = resource.get("type")
        if kind_name in {parent[1] for parent in PARENTS.values()} and isinstance(values, dict):
            if values.get("compartment_id") == target["compartment_id"] and isinstance(values.get("id"), str):
                parent_ids[phase].setdefault(kind_name, set()).add(values["id"])

    for resource in previous:
        add_parent(resource, resource.get("values"), "before")
    for resource in planned:
        add_parent(resource, resource.get("values"), "after")
    for resource in changes:
        for phase in ("before", "after"):
            add_parent(resource, (resource.get("change") or {}).get(phase), phase)
    checked, images, iam_scopes = set(), [], {}

    def variable(name):
        entry = (plan.get("variables") or {}).get(name)
        return entry.get("value") if isinstance(entry, dict) else None

    if binding.get("component_role") == "worker":
        files.require(binding["blueprint"] == "saas-essentials" and variable("name") == binding["environment"]
                      and variable("web_compartment_ocid") == binding.get("web_compartment_id")
                      and target["compartment_id"] != binding.get("web_compartment_id"),
                      "Worker runtime identity and database environment must match the explicit component binding.")

    def iam_scope(address):
        base = address.split("[", 1)[0]
        if base in {"oci_identity_dynamic_group.runtime", "oci_identity_dynamic_group.app"}:
            compartment = variable("tenancy_ocid")
        elif binding["blueprint"] == "fullstack-container" and base == "oci_identity_policy.app":
            compartment = target["compartment_id"]
        elif binding["blueprint"] == "fullstack-container" and base == "oci_identity_policy.runtime_secrets":
            compartment = (variable("production") or {}).get("security_compartment_ocid")
        elif binding["blueprint"] in {"web-container", "saas-essentials"} and base == "oci_identity_policy.registry":
            compartment = (variable("registry") or {}).get("compartment_ocid")
        elif binding["blueprint"] in {"web-container", "saas-essentials"} and base == "oci_identity_policy.secrets":
            matched = re.fullmatch(r"oci_identity_policy\.secrets\[(.+)\]", address)
            key = json.loads(matched[1]) if matched else None
            references = variable("secret_references")
            files.require(isinstance(key, str) and isinstance(references, dict) and isinstance(references.get(key), dict),
                          "The secret policy lacks an explicit reviewed scope.")
            compartment = references[key].get("compartment_ocid")
        elif binding["blueprint"] == "saas-essentials" and base == "oci_identity_policy.queue":
            compartment = target["compartment_id"]
        else:
            raise files.ImageGateError("This IAM resource is outside the known workload blueprint; review it separately.")
        region = variable("home_region")
        files.require(isinstance(compartment, str) and re.fullmatch(r"ocid1\.(?:compartment|tenancy)\.[a-z0-9.-]+", compartment)
                      and isinstance(region, str) and re.fullmatch(r"[a-z]+-[a-z]+-\d+", region),
                      "The IAM home region and compartment must be explicit reviewed values.")
        iam_scopes[address] = {"address": address, "compartment_id": compartment, "region": region}
        return compartment

    def check(resource, values, *, image_required, phase):
        files.require(isinstance(resource, dict), "Invalid evaluated resource.")
        if resource.get("mode", "managed") != "managed":
            return
        kind_name = resource.get("type", "")
        if not isinstance(kind_name, str) or not kind_name.startswith("oci_"):
            return
        address = resource.get("address", "")
        files.require(isinstance(address, str) and not address.startswith("module."),
                      "Nested resource addresses require separately reviewed support.")
        config = configured.get(address.split("[", 1)[0])
        files.require(isinstance(config, dict) and config.get("type") == kind_name,
                      "The evaluated resource has no matching reviewed root configuration.")
        provider = config.get("provider_config_key")
        files.require(provider == "oci" or kind_name.startswith("oci_identity_") and provider == "oci.home",
                      "A workload resource uses an unexpected OCI provider or region alias.")
        files.require(resource.get("provider_name") == OCI, "The evaluated resource uses an unexpected provider.")
        files.require(isinstance(values, dict), "Evaluated workload identity is unknown.")
        if kind_name in WORKLOAD:
            files.require(values.get("compartment_id") == target["compartment_id"],
                          "An evaluated workload resource targets another or unknown compartment.")
        elif kind_name.startswith("oci_identity_"):
            files.require(provider == "oci.home" and values.get("compartment_id") == iam_scope(address),
                          "An evaluated IAM resource differs from its explicit reviewed shared scope.")
        if kind_name in PARENTS:
            field, parent_kind = PARENTS[kind_name]
            parent = values.get(field)
            if phase == "after" and parent is None:
                unknown = changes_by_address.get(address, {}).get("after_unknown") or {}
                files.require(unknown.get(field) is True,
                              "The future workload parent must be explicitly computed by the reviewed blueprint.")
            else:
                files.require(isinstance(parent, str) and parent in parent_ids[phase].get(parent_kind, set()),
                              "An existing workload child targets an unverified or different environment parent.")
        if kind_name == CI and image_required:
            containers = values.get("containers")
            files.require(isinstance(containers, list) and len(containers) == 1 and isinstance(containers[0], dict),
                          "The reviewed workload requires exactly one evaluated app container.")
            image = containers[0].get("image_url")
            files.require(isinstance(image, str) and re.fullmatch(r"[^@\s]+@" + re.escape(digest), image),
                          "The evaluated app container image differs from the selected immutable digest.")
            images.append(digest)
        checked.add(address)

    if kind == "destroy":
        files.require(bool(previous_section), "Destroy requires evaluated prior state for this environment.")
        evaluated = previous
    else:
        evaluated = planned
    for resource in evaluated:
        check(resource, resource.get("values"), image_required=True, phase="before" if kind == "destroy" else "after")
    for resource in changes:
        change = resource.get("change") or {}
        actions = change.get("actions")
        files.require(isinstance(actions, list), "Invalid resource actions.")
        if change.get("before") is not None:
            check(resource, change["before"], image_required=kind == "destroy", phase="before")
        if change.get("after") is not None:
            check(resource, change["after"], image_required=True, phase="after")
        if resource.get("mode", "managed") == "managed" and resource.get("type") in WORKLOAD:
            files.require(change.get("before") is not None or change.get("after") is not None,
                          "The changed workload identity is unknown.")
    files.require(bool(images), "The plan does not establish the actual app container and selected image.")
    return {"schema": "oci-named-workload-proof/1", "scope": "reviewed-flat-blueprint",
            "resources_checked": len(checked), "image_digest": digest,
            "compartment_id": target["compartment_id"], "component_role": binding.get("component_role", "web"), "provider_definition": "reviewed-exact-source",
            "shared_iam_scopes": [iam_scopes[key] for key in sorted(iam_scopes)],
            "iam_authorization": "separate-owner-review-required"}
