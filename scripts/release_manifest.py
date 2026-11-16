#!/usr/bin/env python3
"""Build or verify an explicit, offline distribution manifest.

Hashes detect changed bytes; they are not a publisher signature. Obtain releases
from the reviewed project source. Creation selects Git-indexed paths only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile

NAME = "release-manifest.json"
SCHEMA = "oci-kit-release/1"
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 96 * 1024 * 1024
MAX_FILES = 2048


def read_file(root: Path, name: str, limit: int = MAX_FILE) -> bytes:
    relative = PurePosixPath(name)
    if (not isinstance(name, str) or not name or relative.is_absolute()
            or relative.as_posix() != name or ".." in relative.parts or "\\" in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError("Invalid distribution path.")
    root = root.resolve(strict=True)
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinked distribution path.")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Distribution entry is not a regular file.")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Distribution entry exceeds its limit.")
    return data


def unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate manifest field.")
        data[key] = value
    return data


def load(root: Path, eligible) -> dict:
    raw = read_file(root, NAME, 1024 * 1024)
    data = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(data, dict) or set(data) != {"schema", "files"}
            or data["schema"] != SCHEMA or not isinstance(data["files"], dict)
            or len(data["files"]) > MAX_FILES):
        raise ValueError("Invalid release manifest.")
    for name, entry in data["files"].items():
        if (name == NAME or not eligible(root / name) or not isinstance(entry, dict)
                or set(entry) != {"sha256", "executable"}
                or not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in entry["sha256"])
                or not isinstance(entry["executable"], bool)):
            raise ValueError("Invalid release entry.")
        # Validate names even when the caller only needs ownership metadata.
        relative = PurePosixPath(name)
        if (relative.is_absolute() or relative.as_posix() != name or ".." in relative.parts
                or "\\" in name or any(ord(c) < 32 for c in name)):
            raise ValueError("Invalid release path.")
    return data


def verified(root: Path, eligible) -> dict[str, dict]:
    manifest = load(root, eligible)
    total = 0
    entries = dict(manifest["files"])
    for name, entry in entries.items():
        data = read_file(root, name)
        total += len(data)
        if total > MAX_TOTAL or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("Release integrity check failed.")
    raw = read_file(root, NAME, 1024 * 1024)
    entries[NAME] = {"sha256": hashlib.sha256(raw).hexdigest(), "executable": False}
    return entries


def build(root: Path, names: list[str], eligible) -> dict:
    files = {}
    total = 0
    for name in sorted(set(names)):
        if name == NAME or not eligible(root / name):
            continue
        data = read_file(root, name)
        total += len(data)
        if len(files) >= MAX_FILES or total > MAX_TOTAL:
            raise ValueError("Release exceeds its limit.")
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(),
                       "executable": bool((root / name).stat().st_mode & 0o111)}
    return {"schema": SCHEMA, "files": files}


def indexed_paths(root: Path) -> list[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
               GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root),
                             "ls-files", "--cached", "-z"], env=env, timeout=15,
                            capture_output=True, check=True)
    if len(result.stdout) > 1024 * 1024:
        raise ValueError("Index exceeds its limit.")
    return [os.fsdecode(name) for name in result.stdout.split(b"\0") if name]


def write(root: Path, data: dict) -> None:
    target = root / NAME
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("Unsafe manifest destination.")
    fd, temporary = tempfile.mkstemp(prefix=".release-manifest-", dir=root)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o644)
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "check"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        spec = importlib.util.spec_from_file_location("kit_manifest_install", Path(__file__).with_name("install.py"))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.ROOT = root
        if args.operation == "create":
            data = build(root, indexed_paths(root), installer.distributable)
            write(root, data)
        entries = verified(root, installer.distributable)
        print(json.dumps({"schema": SCHEMA, "status": "verified", "files": len(entries),
                          "scope": "Listed file bytes only; no publisher signature or secret-safety guarantee."}))
        return 0
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError):
        sys.stderr.write("Release verification refused: missing, changed or unsafe manifest/file. No source content is shown.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
