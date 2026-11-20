#!/usr/bin/env python3
"""Explicit private environments. No active/default environment or transferred approvals."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9-]{0,39}")
ROLES = ("source", "rehearsal", "production")
BLUEPRINTS = ("web-container", "fullstack-container")
BACKEND_FIELDS = {"region", "namespace", "bucket", "key", "workspace_key_prefix"}
TARGET_FIELDS = {"region", "compartment_id", "profile", "auth", "image_digest", "image_architecture",
                 "port", "health_path", "origin", "vcn_id", "app_subnet_id", "lb_subnet_id",
                 "certificate_id", "registry_id", "availability_domain", "ocpus", "memory_gbs", "app_private_ip"}


def project_module():
    spec = importlib.util.spec_from_file_location("oci_environment_project", ROOT / "scripts/project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(config: dict, *, component: bool = False):
    fields = {"schema", "name", "role", "blueprint", "infrastructure", "target"}
    if (not isinstance(config, dict) or not fields.issubset(config) or not set(config).issubset(fields | {"backend", "components"})
            or config["schema"] != "oci-kit-environment/1"
            or not isinstance(config["name"], str) or not NAME.fullmatch(config["name"])
            or config["role"] not in ROLES or config["blueprint"] not in ((*BLUEPRINTS, "saas-essentials") if component else BLUEPRINTS)
            or not isinstance(config["target"], dict) or not set(config["target"]).issubset(TARGET_FIELDS)):
        raise ValueError("Invalid environment selection.")
    if "components" in config:
        components = config["components"]
        if (component or config["role"] == "source" or not isinstance(components, dict)
                or not set(components).issubset({"worker"})):
            raise ValueError("Only an explicit worker component is supported for an OCI target.")
        for role, selected in components.items():
            if (not isinstance(selected, dict) or set(selected) != {"blueprint", "infrastructure", "target", "backend"}
                    or selected["blueprint"] != "saas-essentials"):
                raise ValueError("Worker components require the reviewed SaaS blueprint and independent bindings.")
            validate({"schema": config["schema"], "name": config["name"], "role": config["role"], **selected}, component=True)
            for field in ("region", "profile", "auth"):
                if selected["target"].get(field) != config["target"].get(field):
                    raise ValueError("Components must explicitly share their environment region and operator context.")
            if not selected["target"].get("compartment_id") or not config["target"].get("compartment_id"):
                raise ValueError("Bind distinct dedicated web and worker compartments before adding a component.")
    if config.get("backend") is not None:
        validate_backend(config["backend"])
        if config["role"] == "source":
            raise ValueError("The retained source cannot select an OCI backend.")
    path = config["infrastructure"]
    if config["role"] == "source":
        if path is not None:
            raise ValueError("The retained source has no OCI deployment directory.")
    elif (not isinstance(path, str) or not path or len(path) > 240
          or PurePosixPath(path).as_posix() != path or path.startswith("/")
          or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", part) for part in path.split("/"))):
        raise ValueError("Choose a normal project-relative infrastructure directory.")
    target = config["target"]
    for field, value in target.items():
        if field in {"port", "ocpus", "memory_gbs"}:
            maximum = {"port": 65535, "ocpus": 64, "memory_gbs": 1024}[field]
            minimum = 1024 if field == "port" and config["blueprint"] == "web-container" else 1
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError("Invalid application sizing.")
            continue
        if not isinstance(value, str) or not value or len(value) > 512 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid target selection.")
        patterns = {"region": r"[a-z][a-z0-9-]*-[0-9]+", "profile": r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}",
                    "image_digest": r"sha256:[0-9a-f]{64}", "health_path": r"/[A-Za-z0-9/_.-]{0,199}",
                    "availability_domain": r"[A-Za-z0-9][A-Za-z0-9:_.-]{0,127}"}
        if field in patterns and not re.fullmatch(patterns[field], value):
            raise ValueError("Invalid target selection.")
        if field.endswith("_id"):
            kinds = {"compartment_id": "compartment", "vcn_id": "vcn", "app_subnet_id": "subnet",
                     "lb_subnet_id": "subnet", "certificate_id": "certificate", "registry_id": "containerrepo"}
            if not re.fullmatch(r"ocid1\." + kinds[field] + r"\.[a-z0-9.-]+", value):
                raise ValueError("Invalid resource reference.")
        if field == "auth" and value not in {"api_key", "security_token"}:
            raise ValueError("Use an explicit supported local authentication mode.")
        if field == "image_architecture" and value not in {"AMD64", "ARM64", "unknown"}:
            raise ValueError("Invalid image architecture selection.")
        if field == "origin":
            project_module().helper("migration").origin(value, "https")
            if config["role"] != "source" and urlsplit(value).port not in {None, 443}:
                raise ValueError("These OCI ingress blueprints use HTTPS port 443.")
        if field == "app_private_ip":
            ipaddress.IPv4Address(value)
    if "ocpus" in target and "memory_gbs" in target and not target["ocpus"] <= target["memory_gbs"] <= target["ocpus"] * 64:
        raise ValueError("E4 memory must be within the configured OCPU ratio.")


def validate_backend(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != BACKEND_FIELDS:
        raise ValueError("Select exactly the five nonsecret backend destination fields.")
    # Reuse the native gate's format rules without loading credentials or running a client.
    module = project_module().helper("readiness").load("skills/oci-deploy/scripts/backend_ops.py")
    module.configuration({**value, "auth": "APIKey", "config_file_profile": "DEFAULT"})
    if overlap(value["key"], value["workspace_key_prefix"]):
        raise ValueError("The state key must be separate from the workspace prefix.")
    return value


def overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def component_configs(config: dict) -> list[dict]:
    """Expand explicit role bindings without selecting a default deployment target."""
    main = {key: value for key, value in config.items() if key != "components"}
    return [dict(main, component_role="web"), *[
        {"schema": config["schema"], "name": config["name"], "role": config["role"],
         **selected, "component_role": role} for role, selected in config.get("components", {}).items()]]


def validate_isolation(config: dict, configs: list[dict]):
    """Refuse known component/environment target and state collisions."""
    validate(config)
    all_configs = [config, *[item for item in configs if item["name"] != config["name"]]]
    for item in all_configs:
        validate(item)
    expanded = [item for parent in all_configs for item in component_configs(parent)]
    for index, selected in enumerate(expanded):
        for other in expanded[index + 1:]:
            if selected["infrastructure"] and other["infrastructure"] and overlap(
                    selected["infrastructure"].casefold(), other["infrastructure"].casefold()):
                raise ValueError("Environments and components need distinct non-overlapping infrastructure roots.")
            if selected["role"] == "source" or other["role"] == "source":
                continue
            compartment = selected["target"].get("compartment_id")
            if compartment and compartment == other["target"].get("compartment_id"):
                raise ValueError("Environments and runtime components need distinct dedicated compartments.")
            left, right = selected.get("backend"), other.get("backend")
            if left and right and all(left[key] == right[key] for key in ("region", "namespace", "bucket")):
                if any(overlap(left[a], right[b]) for a in ("key", "workspace_key_prefix")
                       for b in ("key", "workspace_key_prefix")):
                    raise ValueError("Environment or component state destinations overlap in the same bucket.")


def private_directory(parent: int, name: str, p, *, create: bool = False) -> int:
    if create:
        with contextlib.suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent)
    fd = os.open(name, p.DIRECTORY, dir_fd=parent)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError("Expected a private owned directory.")
    return fd


def put(fd: int, name: str, raw: bytes):
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(handle, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def list_configs(store, p) -> list[dict]:
    try:
        directory = private_directory(store.base_fd, "environments", p)
    except FileNotFoundError:
        return []
    try:
        names = os.listdir(directory)
        if len(names) > 50:
            raise ValueError("Too many environments or incomplete operations.")
        result = []
        for name in sorted(names):
            if not NAME.fullmatch(name):
                raise ValueError("Review incomplete environment operations before continuing.")
            child = private_directory(directory, name, p)
            try:
                config = p.object_at(child, "environment.json", private=True)
                validate(config)
                if config["name"] != name:
                    raise ValueError("Environment binding changed.")
                result.append(config)
            finally:
                os.close(child)
        return result
    finally:
        os.close(directory)


def summary(config, p) -> dict:
    return {"name": config["name"], "role": config["role"], "blueprint": config["blueprint"],
            "target_sha256": p.digest(p.canonical(config)), "target_configured": bool(config["target"]),
            "backend_configured": config.get("backend") is not None}


def create(project: Path, *, name: str, role: str, blueprint: str = "web-container",
           infrastructure: str | None = None, target: dict | None = None,
           convert_legacy: bool = False, backend: dict | None = None) -> dict:
    p = project_module()
    config = {"schema": "oci-kit-environment/1", "name": name, "role": role,
              "blueprint": blueprint, "infrastructure": infrastructure, "target": target or {}, "backend": backend}
    validate(config)
    with p.Store(project, write=True) as store:
        legacy = store.read()
        configs = list_configs(store, p)
        if any(item["name"] == name for item in configs):
            raise ValueError("Environment already exists; inspect it instead of replacing it.")
        validate_isolation(config, configs)
        # A conversion is an observation backup, never a copy of receipts, approval or passing checkpoints.
        backup = None
        if convert_legacy:
            backups = private_directory(store.base_fd, "environment-backups", p, create=True)
            try:
                backup = uuid.uuid4().hex
                saved = private_directory(backups, backup, p, create=True)
                try:
                    put(saved, "state.json", p.read_at(store.fd, "state.json", private=True))
                    evidence = private_directory(saved, "evidence", p, create=True)
                    try:
                        names = os.listdir(store.evidence_fd)
                        if len(names) > 200:
                            raise ValueError("Legacy evidence exceeds the backup bound.")
                        for filename in names:
                            if not p.NAME.fullmatch(filename):
                                raise ValueError("Invalid legacy evidence filename.")
                            put(evidence, filename, p.read_at(store.evidence_fd, filename, private=True))
                    finally:
                        os.close(evidence)
                    put(saved, "conversion.json", p.canonical({"environment": name, "records_imported": False,
                        "approvals_imported": False, "created_at": int(time.time())}) + b"\n")
                    os.fsync(saved)
                finally:
                    os.close(saved)
            finally:
                os.close(backups)
        environments = private_directory(store.base_fd, "environments", p, create=True)
        pending_name = ".pending-" + uuid.uuid4().hex
        try:
            os.mkdir(pending_name, 0o700, dir_fd=environments)
            pending = private_directory(environments, pending_name, p)
            try:
                put(pending, "environment.json", p.canonical(config) + b"\n")
                os.mkdir("evidence", 0o700, dir_fd=pending)
                now = int(time.time())
                data = dict(legacy, schema="oci-kit-project/2", environment=name, blueprint=blueprint,
                            records={}, created_at=now, observed_at=now,
                            source_sha256=p.source_fingerprint(store.root_fd),
                            kit_sha256=p.digest(p.canonical([p.kit_fingerprint(), config])))
                p.validate_state(data)
                put(pending, "state.json", p.canonical(data) + b"\n")
                os.fsync(pending)
            finally:
                os.close(pending)
            os.rename(pending_name, name, src_dir_fd=environments, dst_dir_fd=environments)
            os.fsync(environments)
        finally:
            os.close(environments)
        return {"schema": "oci-kit-environment-result/1", **summary(config, p), "created": True,
                "legacy_backup": backup is not None, "records_imported": False, "approvals_imported": False,
                "scope": "Local configuration only. Select this environment explicitly on every operation. Use distinct backend keys and reviewed plans."}


def configure(project: Path, *, name: str, target: dict, backend: dict | None = None, components: dict | None = None,
              expected_binding: dict | None = None) -> dict:
    p = project_module()
    with p.Store(project, environment=name, write=True) as store:
        return configure_locked(store, p, target, backend, components, expected_binding)


def configure_locked(store, p, target, backend=None, components=None, expected_binding=None):
    """Replace selection only while the caller holds the private store's write lock."""
    if not store.write:
        raise ValueError("An exclusive environment store is required.")
    if expected_binding is not None:
        actual = {"target_sha256": p.digest(p.canonical(store.environment_config)),
                  "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint()}
        if expected_binding != actual:
            raise ValueError("Source, kit or environment changed after local review; prepare a new proposal.")
    config = dict(store.environment_config, target=target)
    if components is not None:
        config["components"] = components
    if backend is not None:
        config["backend"] = backend
    validate_isolation(config, list_configs(store, p))
    original = p.read_at(store.fd, "environment.json", private=True)
    if original == p.canonical(config) + b"\n":
        return {**summary(config, p), "changed": False}
    # Keep a private backup before replacing target selection. Existing records become stale.
    put(store.fd, "environment-backup-" + uuid.uuid4().hex + ".json", original)
    pending = ".config-" + uuid.uuid4().hex
    put(store.fd, pending, p.canonical(config) + b"\n")
    os.replace(pending, "environment.json", src_dir_fd=store.fd, dst_dir_fd=store.fd)
    os.fsync(store.fd)
    return {**summary(config, p), "changed": True, "previous_evidence": "stale",
            "approvals_imported": False}


def read_target(path: Path) -> dict:
    p = project_module()
    _, fd = p.open_project(path.expanduser().absolute().parent)
    try:
        target = p.object_at(fd, path.name, private=True)
    finally:
        os.close(fd)
    return target


def read_backend(path: Path) -> dict:
    value = read_target(path)
    if set(value) == BACKEND_FIELDS | {"auth", "config_file_profile"}:
        module = project_module().helper("readiness").load("skills/oci-deploy/scripts/backend_ops.py")
        module.configuration(value)
        value = {key: value[key] for key in BACKEND_FIELDS}
    return validate_backend(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "list", "configure"):
        child = commands.add_parser(command)
        child.add_argument("--project", type=Path, required=True)
        if command != "list":
            child.add_argument("--name", required=True)
            child.add_argument("--target-file", type=Path, required=command == "configure")
            if command == "configure":
                child.add_argument("--components-file", type=Path)
            child.add_argument("--backend-config", type=Path,
                               help="Private native backend JSON; store only its five nonsecret destination fields.")
        if command == "create":
            child.add_argument("--role", choices=ROLES, required=True)
            child.add_argument("--blueprint", choices=BLUEPRINTS, default="web-container")
            child.add_argument("--infrastructure")
            child.add_argument("--convert-legacy", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            p = project_module()
            with p.Store(args.project) as store:
                result = {"environments": [summary(item, p) for item in list_configs(store, p)], "active_environment": None}
        else:
            target = read_target(args.target_file) if args.target_file else {}
            backend = read_backend(args.backend_config) if args.backend_config else None
            if args.command == "configure":
                result = configure(args.project, name=args.name, target=target, backend=backend,
                                   components=read_target(args.components_file) if args.components_file else None)
            else:
                result = create(args.project, name=args.name, role=args.role, blueprint=args.blueprint,
                                infrastructure=args.infrastructure, target=target, convert_legacy=args.convert_legacy,
                                backend=backend)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, RecursionError):
        sys.stderr.write("Environment operation refused: review private configuration, directory ownership, unique target roots and any interrupted operation. No cloud operation ran.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
