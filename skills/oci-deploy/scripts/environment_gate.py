"""Bind named project environments to the existing approval gates, without cloud I/O."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

import image_gate as files
import named_workload

ROOT = Path(__file__).resolve().parents[3]
BACKEND_FIELDS = {"region", "namespace", "bucket", "key", "workspace_key_prefix"}
TARGET_FIELDS = {"region", "compartment_id", "profile", "auth"}


def source_binding():
    names = ("skills/oci-deploy/scripts/environment_gate.py", "scripts/project.py",
             "scripts/environments.py", "scripts/migration.py", "scripts/readiness.py",
             "skills/oci-deploy/scripts/named_workload.py")
    templates = [path.relative_to(ROOT).as_posix() for blueprint in ("web-container", "fullstack-container", "saas-essentials")
                 for path in sorted((ROOT / "blueprints" / blueprint / "terraform").glob("*.tf"))]
    return {name: files.sha((ROOT / name).read_bytes()) for name in (*names, *templates)}


def modules():
    path = ROOT / "scripts/environments.py"
    files.require(not path.is_symlink(), "The environment helper must be a reviewed regular file.")
    spec = importlib.util.spec_from_file_location("oci_gate_environments", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        return module, module.project_module()
    finally:
        sys.dont_write_bytecode = previous


def inspect_project(project, env, p):
    with p.Store(project) as store:
        state = store.read()
        return state["project_identity"], env.list_configs(store, p)


def candidates(stack, env, p):
    """Inspect bounded ancestors, including outer projects; never select a default."""
    parents = (stack, *stack.parents)
    files.require(len(parents) <= 64, "Project ancestry exceeds the inspection bound.")
    matches, projects = [], []
    for project in parents:
        marker = project / ".oci-kit"
        if not os.path.lexists(marker):
            continue
        # Opening Store validates every path component, ownership, lock and private files.
        identity, configs = inspect_project(project, env, p)
        if configs:
            projects.append(project)
        for parent_config in configs:
            for config in env.component_configs(parent_config):
                if config["infrastructure"] is None:
                    continue
                infrastructure = project / config["infrastructure"]
                if stack == infrastructure or infrastructure in stack.parents:
                    matches.append((project, identity, config, configs))
    return matches, projects


def select(stack, *, project=None, environment=None, backend=None):
    """Require an explicit project/name for mapped stacks; legacy stacks remain unchanged."""
    try:
        files.require((project is None) == (environment is None),
                      "Select both --project and --environment for a named deployment.")
        stack = Path(stack).absolute()
        env, p = modules()
        # Reject symlink ancestors before inspecting or comparing configured roots.
        _, descriptor = p.open_project(stack)
        os.close(descriptor)
        matches, projects = candidates(stack, env, p)
        files.require(len(matches) <= 1 and len(projects) <= 1,
                      "The stack belongs to ambiguous nested environment projects.")
        if project is None:
            files.require(not projects,
                          "This named environment requires explicit --project and --environment selection.")
            return None
        project = Path(project).expanduser().absolute()
        identity, configs = inspect_project(project, env, p)
        chosen = [config for config in configs if config["name"] == environment]
        files.require(len(chosen) == 1, "The selected environment does not exist in this project.")
        parent_config = chosen[0]
        env.validate_isolation(parent_config, configs)
        roles = [item for item in env.component_configs(parent_config)
                 if item["infrastructure"] is not None and stack == project / item["infrastructure"]]
        files.require(len(roles) == 1, "Select the exact reviewed infrastructure root for this environment component.")
        config = roles[0]
        files.require(config["role"] != "source" and config["infrastructure"] is not None,
                      "The retained source cannot be used as an OCI deployment target.")
        files.require(stack == project / config["infrastructure"] and len(matches) == 1
                      and matches[0][0] == project and matches[0][2]["name"] == environment,
                      "The selected environment does not match this exact infrastructure root.")
        target = config["target"]
        files.require(TARGET_FIELDS.issubset(target),
                      "Configure the environment region, compartment, profile and authentication before cloud operations.")
        selected_backend = config.get("backend")
        files.require(isinstance(selected_backend, dict) and set(selected_backend) == BACKEND_FIELDS,
                      "Configure a distinct reviewed OCI backend for this named environment first.")
        files.require(isinstance(backend, dict)
                      and {key: backend.get(key) for key in BACKEND_FIELDS} == selected_backend,
                      "The backend destination does not match the selected environment; local state is not supported here.")
        files.require(backend.get("config_file_profile") == target["profile"]
                      and backend.get("auth") == {"api_key": "APIKey", "security_token": "SecurityToken"}[target["auth"]],
                      "The backend profile and authentication must match the selected environment.")
        named_workload.sources(stack, config["blueprint"])
        return {"schema": "oci-deploy-environment-binding/1", "project_path": str(project),
                "project_identity": identity, "environment": environment, "role": config["role"],
                "blueprint": config["blueprint"],
                "infrastructure": config["infrastructure"], "configuration_sha256": p.digest(p.canonical(parent_config)),
                "component_role": config["component_role"],
                **({"web_compartment_id": parent_config["target"]["compartment_id"]} if config["component_role"] == "worker" else {}),
                "backend": selected_backend, "target": dict(target),
                "sources": source_binding()}
    except files.ImageGateError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise files.ImageGateError("Unsafe or incomplete environment configuration; review it privately before planning.") from None


def recheck(stack, binding, backend=None, target=None):
    """Re-read bindings on execution; old/unbound plans cannot enter a mapped root."""
    if binding is None:
        return select(stack, backend=backend)
    files.require(isinstance(binding, dict) and binding.get("schema") == "oci-deploy-environment-binding/1",
                  "Invalid environment binding; prepare and approve a fresh plan.")
    current = select(stack, project=binding.get("project_path"), environment=binding.get("environment"), backend=backend)
    files.require(current == binding, "Environment configuration or target changed; prepare and approve a fresh plan.")
    if target is not None:
        expected = binding["target"]
        files.require(isinstance(target, dict) and target.get("region") == expected["region"]
                      and target.get("compartment_ocid") == expected["compartment_id"]
                      and target.get("profile") == expected["profile"]
                      and target.get("auth") == {"api_key": "APIKey", "security_token": "SecurityToken"}[expected["auth"]],
                      "The actual Terraform target differs from the selected environment; no resource apply is authorized.")
        comparable = {"image_digest", "ocpus", "memory_gbs"}
        if binding["blueprint"] == "web-container":
            comparable |= {"port", "health_path", "origin", "availability_domain", "certificate_id",
                           "vcn_id", "app_subnet_id", "lb_subnet_id", "app_private_ip"}
        if binding.get("component_role") == "worker":
            comparable |= {"availability_domain", "vcn_id", "app_subnet_id", "app_private_ip"}
        files.require(all(target.get(key) == expected[key] for key in comparable & expected.keys()),
                      "The planned image or selected workload settings differ from this environment.")
    return current
