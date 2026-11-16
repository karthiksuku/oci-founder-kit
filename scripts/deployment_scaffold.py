"""Attach reviewed deployment sources without replacing an application's files.

Uses the existing manifest reader and exclusive, descriptor-relative publisher.
No application command, dependency installer, credential read or cloud call runs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def source_helper(root: Path):
    path = root / "scripts/scaffold.py"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Required source helper is unavailable.")
    spec = importlib.util.spec_from_file_location("oci_attach_scaffold", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def destination_parts(directory: str) -> tuple[str, ...]:
    path = PurePosixPath(directory)
    if (not directory or not path.parts or path.is_absolute() or directory != path.as_posix()
            or len(directory) > 180 or len(path.parts) > 6
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", part) for part in path.parts)):
        raise ValueError("Choose a new canonical relative deployment directory.")
    return path.parts


def identity(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def check_project(helper, project: Path, project_fd: int) -> None:
    current = helper.open_directory(project)
    try:
        if identity(current) != identity(project_fd):
            raise ValueError("Project changed during attachment.")
    finally:
        os.close(current)


def check_destination(helper, project_fd: int, parts: tuple[str, ...]) -> None:
    """Read every existing component without following links; final must be absent."""
    fd = os.dup(project_fd)
    try:
        for index, part in enumerate(parts):
            try:
                os.stat(part, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            if index == len(parts) - 1:
                raise ValueError("The selected deployment directory already exists.")
            next_fd = os.open(part, helper.DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    finally:
        os.close(fd)


def prepare(root: Path, name: str, helper, stage: Path) -> dict:
    contract = helper.sibling(root, "blueprint").load(name, root)
    if name != "web-container" or contract.get("kind") != "deployment":
        raise ValueError("Only reviewed deployment blueprints can be attached.")
    installer = helper.sibling(root, "install")
    manifest = installer.manifest_module()
    release = manifest.verified(root, installer.distributable)
    prefix = f"blueprints/{name}/"
    selected = {key: value for key, value in release.items() if key.startswith(prefix) or key == "LICENSE"}
    required = {prefix + value for value in ("README.md", ".gitignore", "blueprint.json",
                                             "terraform/versions.tf", "terraform/container.tf")}
    if not required.issubset(selected) or "LICENSE" not in selected:
        raise ValueError("Required deployment sources are missing from the release.")
    for key, record in selected.items():
        data = manifest.read_file(root, key)
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Source changed during attachment.")
        relative = key.removeprefix(prefix)
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(0o755 if record["executable"] else 0o644)
    return {"files": len(selected), "source_manifest_sha256": hashlib.sha256(
        manifest.read_file(root, "release-manifest.json")).hexdigest()}


def attach(name: str, project: Path, directory: str, dry_run: bool = False, *, root: Path = ROOT) -> dict:
    parts = destination_parts(directory)
    root = root.resolve(strict=True)
    project = project.expanduser().absolute()
    if any(path.is_symlink() for path in (project, *project.parents)):
        raise ValueError("Symlinked project paths are refused.")
    project = Path(os.path.normpath(project))
    destination = project.joinpath(*parts)
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError("Attach outside the toolkit source.")
    if (os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd
            or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")):
        raise ValueError("Attachment requires Linux, macOS or WSL2 filesystem operations.")
    helper = source_helper(root)
    project_fd = helper.open_directory(project)
    try:
        check_destination(helper, project_fd, parts)
        # Validate identical source bytes for dry-run and actual attachment.
        with tempfile.TemporaryDirectory(prefix=".oci-kit-attach-") as temporary:
            stage = Path(temporary)
            source = prepare(root, name, helper, stage)
            report = {"schema": "oci-kit-blueprint-attachment/1", "blueprint": name,
                      "directory": directory, "status": "dry_run" if dry_run else "attached",
                      **source, "application": "unchanged", "agent_installation": "unchanged",
                      "checks": {"application": "not_run", "cloud": "not_checked", "recovery": "not_run"}}
            if dry_run:
                return report
            check_project(helper, project, project_fd)
            parent_fd = os.dup(project_fd)
            try:
                for part in parts[:-1]:
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=parent_fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(part, helper.DIRECTORY_FLAGS, dir_fd=parent_fd)
                    os.close(parent_fd)
                    parent_fd = next_fd
                current_parent = helper.open_parent(project_fd, parts[:-1])
                try:
                    if identity(current_parent) != identity(parent_fd):
                        raise ValueError("Deployment parent changed during attachment.")
                finally:
                    os.close(current_parent)
                os.mkdir(parts[-1], mode=0o755, dir_fd=parent_fd)
                target_fd = os.open(parts[-1], helper.DIRECTORY_FLAGS, dir_fd=parent_fd)
                try:
                    helper.publish(stage, target_fd)
                    check_project(helper, project, project_fd)
                    current = helper.open_parent(project_fd, parts)
                    try:
                        if identity(current) != identity(target_fd):
                            raise ValueError("Deployment destination changed during attachment.")
                    finally:
                        os.close(current)
                finally:
                    os.close(target_fd)
            finally:
                os.close(parent_fd)
            return report
    finally:
        os.close(project_fd)
