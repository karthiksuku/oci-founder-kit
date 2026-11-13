#!/usr/bin/env python3
"""List, check or inspect bundled blueprint metadata without running commands.

Python 3.11+. This checks the declarative contract and referenced local paths,
not installed tools, application behavior, OCI access or deployment readiness.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-kit-blueprint/1"
NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
LIMIT = 32768
SCOPE = ("Metadata and paths only. Commands are displayed, never executed. "
         "Tools, application behavior, OCI access and deployment readiness are not checked.")


def fields(value: object, expected: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Missing or unknown contract fields.")
    return value


def text(value: object, maximum: int = 500) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("Invalid contract text.")
    return value


def named(value: object) -> str:
    if not NAME.fullmatch(text(value, 64)):
        raise ValueError("Invalid contract name.")
    return value


def items(value: object) -> list:
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise ValueError("Contract lists must contain 1 to 32 items.")
    return value


def local_path(base: Path, value: object, *, directory: bool) -> Path:
    value = text(value, 200)
    relative = PurePosixPath(value)
    if (relative.is_absolute() or "\\" in value or ":" in value
            or ".." in relative.parts or value != relative.as_posix()):
        raise ValueError("Paths must stay within the blueprint.")
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlinked blueprint paths are refused.")
    if current.is_symlink() or (not current.is_dir() if directory else not current.is_file()):
        raise ValueError("A required blueprint path is missing or has the wrong type.")
    return current


def no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON fields are refused.")
        result[key] = value
    return result


def read_contract(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Blueprint metadata must be a regular file.")
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Blueprint metadata exceeds its size limit.")
    return json.loads(raw, object_pairs_hook=no_duplicate_keys)


def load(name: str, root: Path = ROOT) -> dict:
    named(name)
    catalog = local_path(root, "blueprints", directory=True)
    base = local_path(catalog, name, directory=True)
    path = local_path(base, "blueprint.json", directory=False)
    data = fields(read_contract(path), {"schema", "id", "name", "summary", "runtime", "paths",
                                      "tools", "commands", "operating_modes", "outputs", "acceptance"})
    if data["schema"] != SCHEMA or data["id"] != name:
        raise ValueError("Unsupported blueprint schema or mismatched ID.")
    text(data["name"], 100)
    text(data["summary"])
    runtime = fields(data["runtime"], {"name", "requirement", "source"})
    text(runtime["name"], 64)
    text(runtime["requirement"], 100)
    local_path(base, runtime["source"], directory=False)
    paths = fields(data["paths"], {"app", "infrastructure", "tests", "local_preview"})
    for key, value in paths.items():
        local_path(base, value, directory=key != "local_preview")
    seen = set()
    for tool in items(data["tools"]):
        fields(tool, {"name", "requirement", "purpose"})
        key = named(tool["name"])
        if key in seen:
            raise ValueError("Duplicate tool names are refused.")
        seen.add(key)
        text(tool["requirement"], 150)
        text(tool["purpose"])
    commands = fields(data["commands"], {"preview", "application_tests", "infrastructure_validate"})
    for command in commands.values():
        fields(command, {"cwd", "argv"})
        local_path(base, command["cwd"], directory=True)
        for argument in items(command["argv"]):
            text(argument, 200)
        if command["argv"][0] not in seen:
            raise ValueError("Command tools must be declared in the contract.")
    for section in ("operating_modes", "acceptance"):
        seen = set()
        for entry in items(data[section]):
            fields(entry, {"id", "description"})
            key = named(entry["id"])
            if key in seen:
                raise ValueError("Duplicate section IDs are refused.")
            seen.add(key)
            text(entry["description"])
    outputs = items(data["outputs"])
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)
           for value in outputs) or len(set(outputs)) != len(outputs):
        raise ValueError("Outputs must be unique Terraform output names, never values.")
    return data


def catalog(root: Path = ROOT) -> list[dict]:
    directory = local_path(root, "blueprints", directory=True)
    result = []
    for child in sorted(directory.iterdir()):
        if child.is_symlink():
            raise ValueError("Symlinked blueprint directories are refused.")
        metadata = child / "blueprint.json"
        if child.is_dir() and (metadata.exists() or metadata.is_symlink()):
            data = load(child.name, root)
            result.append({key: data[key] for key in ("id", "name", "summary")})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List blueprints with validated metadata.")
    for name in ("check", "inspect"):
        command = commands.add_parser(name, help="Validate metadata and local paths without executing anything.")
        command.add_argument("blueprint")
    args = parser.parse_args(argv)
    try:
        result = {"schema": "oci-kit-blueprint-inspection/1", "scope": SCOPE}
        if args.command == "list":
            result["blueprints"] = catalog()
        else:
            data = load(args.blueprint)
            result.update(blueprint=data["id"], metadata="valid", commands="not_run",
                          tools="not_checked", cloud="not_checked")
            if args.command == "inspect":
                result["contract"] = data
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, UnicodeError, RecursionError):
        # Do not echo malformed metadata, account values or private filesystem paths.
        sys.stderr.write("Blueprint check refused: invalid contract, unsafe path or missing required file.\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
