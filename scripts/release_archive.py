#!/usr/bin/env python3
"""Build deterministic release assets from verified manifest entries only.

No Git enumeration, network, credentials or publisher identity is used. A
checksum proves matching bytes; trusted CI attestation is a separate operation.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def helpers(root: Path):
    # Only trusted kit code is executable; application contents are never loaded.
    spec = importlib.util.spec_from_file_location("archive_install", ROOT / "scripts/install.py")
    installer = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(installer)
    finally:
        sys.dont_write_bytecode = previous
    installer.ROOT = root
    return installer, installer.manifest_module()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path) -> tuple[dict[str, bytes], dict, str]:
    installer, manifest = helpers(root)
    entries = manifest.verified(root, installer.distributable)
    required = {".claude-plugin/plugin.json", "scripts/install.py", "scripts/release_manifest.py", "LICENSE"}
    if not required.issubset(entries):
        raise ValueError("The release is missing required installation metadata.")
    content = {}
    for name, entry in sorted(entries.items()):
        data = manifest.read_file(root, name)
        if digest(data) != entry["sha256"]:
            raise ValueError("Source changed during archiving.")
        content[name] = data
    metadata = json.loads(content[".claude-plugin/plugin.json"])
    version = metadata.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", version):
        raise ValueError("Invalid release version.")
    return content, entries, version


def archive_bytes(content: dict[str, bytes], entries: dict, prefix: str) -> bytes:
    output = io.BytesIO()
    # Empty gzip filename, fixed timestamp and normalized tar ownership/modes
    # prevent local filesystem paths, usernames and mtimes entering the artifact.
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, data in sorted(content.items()):
                info = tarfile.TarInfo(f"{prefix}/{name}")
                info.size = len(data)
                info.mode = 0o755 if entries[name]["executable"] else 0o644
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def build(root: Path, output: Path) -> dict:
    root = root.expanduser().resolve(strict=True)
    output = output.expanduser().absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("Symlinked output paths are refused.")
    output = Path(os.path.normpath(output))
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("Write release assets outside the source tree.")
    content, entries, version = snapshot(root)
    basename = f"oci-founder-kit-{version}"
    archive = archive_bytes(content, entries, basename)
    record = {"schema": "oci-kit-release-archive/1", "version": version,
              "files": len(content), "archive": basename + ".tar.gz", "sha256": digest(archive),
              "source_manifest_sha256": digest(content["release-manifest.json"]),
              "scope": "Verified manifest bytes only; publisher authentication requires separate trusted CI attestation."}
    assets = {record["archive"]: archive, "release-manifest.json": content["release-manifest.json"],
              "BUILD-METADATA.json": (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()}
    assets["SHA256SUMS"] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(assets.items())).encode()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd:
        raise ValueError("Release creation requires supported POSIX filesystem operations.")
    # Pin every parent component. A new destination is required; partial outputs
    # are retained on interruption and never overwrite earlier release assets.
    parent_fd = os.open(output.anchor, flags)
    try:
        for part in output.parts[1:-1]:
            next_fd = os.open(part, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        os.mkdir(output.name, mode=0o755, dir_fd=parent_fd)
        target_fd = os.open(output.name, flags, dir_fd=parent_fd)
        try:
            for name, data in sorted(assets.items()):
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=target_fd)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        finally:
            os.close(target_fd)
    finally:
        os.close(parent_fd)
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory outside the source tree, with an existing parent.")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(args.root, args.output_dir), sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, tarfile.TarError):
        sys.stderr.write("Release archive refused: invalid or changed manifest, unsafe path or unavailable source. "
                         "No source content is shown. Preserve any partial destination for review.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
