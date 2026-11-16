#!/usr/bin/env python3
"""Verify downloaded release assets against explicit expected source and provenance.

This is read-only and never extracts or executes the archive. Run a trusted copy
of this verifier, not code extracted from an as-yet-unverified download.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def expected_names(tag):
    return ["oci-founder-kit-" + tag[1:] + ".tar.gz", "release-manifest.json", "BUILD-METADATA.json", "SBOM.spdx.json", "SHA256SUMS"]


def attestation_command(path, repo, workflow, tag, commit):
    return ["gh", "attestation", "verify", str(path), "--repo", repo, "--signer-repo", repo,
            "--signer-workflow", repo + "/" + workflow, "--source-ref", "refs/tags/" + tag,
            "--source-digest", commit, "--signer-digest", commit, "--deny-self-hosted-runners"]


def verify(directory, repo, workflow, tag, commit, archive_digest, runner=None):
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or
            not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_-]+\.ya?ml", workflow) or
            not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) or
            not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{64}", archive_digest)):
        raise ValueError("Expected repository, workflow, tag, commit and digest must be explicit.")
    directory = directory.absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("Symlinked asset directory refused.")
    names = expected_names(tag)
    hashes = {}
    for name in names:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("Unavailable or oversized release asset.")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if hashes[names[0]] != archive_digest:
        raise ValueError("Archive differs from the independently selected digest.")
    checksums = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in checksums:
            raise ValueError("Invalid or duplicate checksum entry.")
        checksums[match[2]] = match[1]
    if checksums != {name: hashes[name] for name in names if name != "SHA256SUMS"}:
        raise ValueError("Checksums must cover exactly the released assets.")
    metadata = json.loads((directory / "BUILD-METADATA.json").read_text())
    if (metadata.get("version") != tag[1:] or metadata.get("archive") != names[0] or
            metadata.get("sha256") != archive_digest or metadata.get("source_manifest_sha256") != hashes["release-manifest.json"]):
        raise ValueError("Build metadata differs from the selected release.")
    runner = runner or subprocess.run
    for name in names:
        result = runner(attestation_command(directory / name, repo, workflow, tag, commit),
                        capture_output=True, timeout=180, check=False)
        if result.returncode:
            raise ValueError("Authenticated provenance is unavailable or does not match expected source.")
    return {"schema": "oci-kit-release-verification/1", "status": "verified", "repository": repo,
            "workflow": workflow, "tag": tag, "commit": commit, "archive_sha256": archive_digest,
            "assets": len(names), "scope": "byte identity and authenticated build provenance; not application or security acceptance"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, type=Path)
    for name in ("repo", "workflow", "tag", "commit", "archive-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.assets, args.repo, args.workflow, args.tag, args.commit, args.archive_sha256), indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Release verification failed; do not extract or install. Recheck expected source and authenticated attestations.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
