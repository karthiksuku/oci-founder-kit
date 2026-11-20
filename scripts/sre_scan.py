#!/usr/bin/env python3
"""Produce private, digest-bound scan evidence. Reports alone never authorize release."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.76.2"
# Upstream Linux x86-64 v0.76.2 binary, extracted from the verified release archive.
BINARY = "6a972c69606c7b3ea4c6bdcc6fc9332ea9ad38381624310c1e85cc77345909f3"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REV = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
COUNTS = {"unknown", "high", "critical", "lower", "secrets", "misconfigs", "os_packages", "runtime_packages",
          "production_lock_packages", "development_inventory_packages", "terraform_checks", "dockerfile_checks"}
MAX_REPORT = 96 * 1024**2
DAY = 86400


def load(path):
    spec = importlib.util.spec_from_file_location("sre_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bounded(x):
    return type(x) is int and 0 <= x <= 10000000


def moment(value):
    if not isinstance(value, str) or len(value) > 48:
        raise ValueError("INVALID_TIME")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("INVALID_TIME")
    return int(parsed.timestamp())


def fresh(value, now):
    return type(value) is int and 0 <= now - value <= DAY


def lock_identity(path, content_sha256):
    # Bind the exact tracked relative path as well as bytes; sibling copies are distinct.
    value = json.dumps(["oci-sre-npm-lock/1", path, content_sha256], separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def gate_status(report, *, image_digest, now, source_revision=None, selected_lock_sha256=None):
    """Validate signed projection shape, policy and freshness; signature checked by caller."""
    if not isinstance(report, dict):
        return "unknown"
    count = report.get("counts")
    scoped = report.get("schema") == "oci-sre-scan/3"
    if scoped and not re.fullmatch(r"[a-f0-9]{64}", str(report.get("selected_lock_sha256"))):
        return "unknown"
    if selected_lock_sha256 is not None and (not scoped or selected_lock_sha256 != report["selected_lock_sha256"]):
        return "unknown"
    if (report.get("schema") not in {"oci-sre-scan/2", "oci-sre-scan/3"} or not DIGEST.fullmatch(str(image_digest))
            or report.get("image_digest") != image_digest or not REV.fullmatch(str(report.get("source_revision")))
            or (source_revision is not None and report["source_revision"] != source_revision)
            or report.get("scanner_version") != VERSION or report.get("scanner_sha256") != BINARY
            or not isinstance(count, dict) or set(count) != COUNTS or not all(map(bounded, count.values()))
            or not fresh(report.get("observed_at"), now) or not fresh(report.get("database_updated_at"), now)
            or report.get("database_schema") != 2 or not DIGEST.fullmatch(str(report.get("sbom_digest")))
            or type(report.get("os_eol")) is not bool):
        return "unknown"
    if any(count[k] for k in ("critical", "high", "secrets", "misconfigs")) or report["os_eol"]:
        return "blocked"
    if count["unknown"] or any(not count[k] for k in ("os_packages", "runtime_packages", "production_lock_packages",
                                                       "terraform_checks", "dockerfile_checks")):
        return "unknown"
    return "passed"


def registry_status(report, *, image_digest, now):
    if (not isinstance(report, dict) or report.get("schema") != "oci-sre-registry-scan/1"
            or not DIGEST.fullmatch(str(image_digest)) or report.get("image_digest") != image_digest
            or report.get("digest_verified") is not True or report.get("compartment_repository_verified") is not True
            or not fresh(report.get("observed_at"), now) or not fresh(report.get("finished_at"), now)
            or report["finished_at"] > report["observed_at"] or not bounded(report.get("problem_count"))):
        return "unknown"
    severity, problems = report.get("severity"), report["problem_count"]
    if severity in ("CRITICAL", "HIGH"):
        return "blocked"
    if (problems == 0 and severity == "NONE") or (problems > 0 and severity in ("LOW", "MEDIUM")):
        return "passed"
    return "unknown"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    if path.stat().st_size > MAX_REPORT:
        raise ValueError("OVERSIZED_REPORT")
    return json.loads(path.read_bytes())


def scan_process(binary, args, workspace):
    # Scanner configuration, suppressions and credentials from the caller's shell or
    # source checkout must not influence a release result. No scanner auto-install.
    env = {"HOME": str(workspace), "PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    def limit():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_REPORT, MAX_REPORT))
    completed = subprocess.run([str(binary), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=env, cwd=workspace, timeout=300, preexec_fn=limit)
    if completed.returncode or len(completed.stdout) > MAX_REPORT:
        raise ValueError("SCANNER_UNAVAILABLE")
    return completed.stdout


def snapshot(project, staging):
    """Scan the reviewed revision's tracked, regular bytes only, without Git export filters."""
    env = {"PATH": os.defpath, "HOME": str(staging), "GIT_NO_REPLACE_OBJECTS": "1",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0"}
    def git(*args):
        result = subprocess.run(["git", "-C", str(project), *args], env=env, capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError("GIT_READ_FAILED")
        return result.stdout
    if git("rev-parse", "--show-prefix").strip():
        raise ValueError("EXPECTED_CLEAN_PROJECT_ROOT")
    rev = git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if not REV.fullmatch(rev):
        raise ValueError("MISSING_REVISION")
    entries = git("ls-tree", "-rlz", rev).rstrip(b"\0").split(b"\0")
    if len(entries) > 15000:
        raise ValueError("SOURCE_LIMIT")
    # Batch cat-file avoids running project code, checkout filters or 1 process per file.
    with subprocess.Popen(["git", "-C", str(project), "cat-file", "--batch"], env=env, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        try:
            total = 0
            for entry in entries:
                meta, raw_path = entry.split(b"\t", 1)
                mode, kind, oid, size = meta.split()
                parts = PurePosixPath(os.fsdecode(raw_path)).parts
                if (not parts or parts[0] == "/" or any(p in (".git", "..", ".") for p in parts)
                        or not REV.fullmatch(oid.decode()) or kind != b"blob" or mode not in (b"100644", b"100755")):
                    raise ValueError("UNSUPPORTED_SOURCE_ENTRY")
                n = int(size)
                total += n
                if n > 16 * 1024**2 or total > 256 * 1024**2:
                    raise ValueError("SOURCE_LIMIT")
                proc.stdin.write(oid + b"\n")
                proc.stdin.flush()
                if proc.stdout.readline().split() != [oid, b"blob", str(n).encode()]:
                    raise ValueError("SOURCE_UNREADABLE")
                data = proc.stdout.read(n)
                if len(data) != n or proc.stdout.read(1) != b"\n":
                    raise ValueError("SOURCE_UNREADABLE")
                if re.search(rb"(?:trivy|tfsec):ignore:", data, re.I):
                    raise ValueError("INLINE_SUPPRESSION_REQUIRES_REVIEW")
                dest = staging.joinpath(*parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as stream:
                    stream.write(data)
        finally:
            proc.stdin.close()
    return rev


def image_input(layout, digest, workspace):
    """Copy verified dir: transport and wrap the identical manifest in an OCI index for Trivy."""
    gate = load(ROOT / "skills/oci-deploy/scripts/image_gate.py")
    with gate.directory(layout) as fd:
        raw = gate.read_at(fd, "manifest.json")
        if "sha256:" + gate.sha(raw) != digest:
            raise ValueError("IMAGE_DIGEST_MISMATCH")
        config = gate.parse(raw)["config"]["digest"]
    private = workspace / "copied"
    private.mkdir(mode=0o700)
    with gate.directory(private) as fd:
        artifact = gate.layout_artifact(layout, {"id": config, "os": "linux", "architecture": "amd64", "variant": ""},
                                       gate.DEFAULT_MAX_IMAGE_BYTES, copy_to=fd)
    if artifact["manifest_digest"] != digest:
        raise ValueError("IMAGE_CHANGED")
    image = workspace / "image"
    blob = image / "blobs/sha256"
    blob.mkdir(parents=True)
    for name in [artifact["config"]["digest"], *[x["digest"] for x in artifact["layers"]]]:
        if not (blob / name[7:]).exists():
            os.link(private / name[7:], blob / name[7:])
    os.link(private / "manifest.json", blob / digest[7:])
    (image / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    (image / "index.json").write_text(json.dumps({"schemaVersion": 2, "manifests": [{
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json", "digest": digest, "size": len(raw),
        "platform": {"os": "linux", "architecture": "amd64"}}]}))
    return image, config


def projection(source, image, development, db, sbom, *, source_revision, image_digest, config, sbom_digest, now, selected_lock=None):
    count = dict.fromkeys(COUNTS, 0)
    direct, shipped = set(), set()
    selected_source_rows = 0
    for doc, image_scan in [(source, False), (image, True), (development, False)]:
        if (doc.get("SchemaVersion") != 2 or doc.get("Trivy", {}).get("Version") != VERSION
                or not isinstance(doc.get("Results"), list)):
            raise ValueError("UNSUPPORTED_REPORT")
        for row in doc["Results"]:
            packages = row.get("Packages", [])
            if not isinstance(packages, list):
                raise ValueError("UNSUPPORTED_REPORT")
            if row.get("Class") == "lang-pkgs" and row.get("Type") in ("npm", "node-pkg"):
                key = "runtime_packages" if image_scan else "development_inventory_packages" if doc is development else "production_lock_packages"
                if image_scan:
                    for pkg in packages:
                        path = PurePosixPath(str(pkg.get("FilePath", "")))
                        if (path.name == "package.json" and "node_modules" in path.parts
                                and not {"npm", "corepack", "pnpm", "yarn"}.intersection(path.parts)):
                            if selected_lock is None or (pkg.get("Name") == "next" and path.parts[-3:] == ("node_modules", "next", "package.json")):
                                shipped.add((pkg.get("Name"), pkg.get("Version")))
                elif selected_lock is None or (row.get("Type") == "npm" and row.get("Target") == selected_lock[0]):
                    count[key] += len(packages)
                    if doc is source:
                        selected_source_rows += 1
                        direct.update((pkg.get("Name"), pkg.get("Version")) for pkg in packages
                                      if pkg.get("Relationship") == "direct" and pkg.get("Name") and pkg.get("Version"))
            if doc is development:
                continue
            if image_scan and row.get("Class") == "os-pkgs":
                count["os_packages"] += len(packages)
            # Bundlers may remove runtime package metadata. The production lock is
            # conservative evidence for these dependencies; a missing match must
            # never erase a source finding. The development-inclusive report is separate.
            if image_scan or doc is source:
                for vuln in row.get("Vulnerabilities", []):
                    level = vuln["Severity"]
                    count[level.lower() if level in ("HIGH", "CRITICAL") else "lower" if level in ("LOW", "MEDIUM") else "unknown"] += 1
            count["secrets"] += len(row.get("Secrets", []))
            if row.get("Class") == "config":
                checks = row.get("Misconfigurations", [])
                if not image_scan and row.get("Type") in ("terraform", "dockerfile"):
                    count[row["Type"] + "_checks"] += len(checks)
                for item in checks:
                    if item["Status"] == "FAIL":
                        count["misconfigs"] += 1
                    elif item["Status"] != "PASS":
                        count["unknown"] += 1
    count["runtime_packages"] = len(direct & shipped)
    if selected_lock is not None and selected_source_rows != 1:
        count["unknown"] += 1
    metadata = image.get("Metadata", {})
    if (metadata.get("ImageID") != config or not metadata.get("OS", {}).get("Family")
            or not metadata.get("OS", {}).get("Name") or not sbom.get("packages")
            or sbom.get("spdxVersion") not in ("SPDX-2.2", "SPDX-2.3")
            or db.get("Version") != VERSION):
        raise ValueError("UNSUPPORTED_INVENTORY")
    scope = ({"schema": "oci-sre-scan/3", "selected_lock_sha256": selected_lock[1]} if selected_lock is not None
             else {"schema": "oci-sre-scan/2"})
    return {**scope, "source_revision": source_revision, "image_digest": image_digest,
            "scanner_version": VERSION, "scanner_sha256": BINARY, "observed_at": now,
            "database_schema": db["VulnerabilityDB"]["Version"],
            "database_updated_at": moment(db["VulnerabilityDB"]["UpdatedAt"]), "sbom_digest": sbom_digest,
            "os_eol": metadata["OS"].get("EOSL", False), "counts": count}


def run_scan(args, out):
    if (not DIGEST.fullmatch(args.image_digest) or sha(args.trivy) != BINARY
            or not args.cache_dir.is_dir()):
        raise ValueError("PIN_OR_INPUT_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="oci-sre-") as temp:
        w = Path(temp)
        project = args.project.resolve()
        staged = w / "source"
        staged.mkdir()
        gate = load(ROOT / "scripts/sre_gate.py")
        project_helper = gate.project_module()
        candidate = gate.revision(project, project_helper)
        rev = snapshot(project, staged)
        if rev != candidate:
            raise ValueError("SOURCE_CHANGED")
        selected_lock = None
        app_directory = getattr(args, "app_directory", None)
        if app_directory is not None:
            directory = project_helper.helper("packaging").relative(app_directory, dot=True)
            lock = PurePosixPath(*directory, "package-lock.json").as_posix()
            selected_lock = (lock, lock_identity(lock, sha(staged / lock)))
        image, config = image_input(args.layout, args.image_digest, w)
        version = json.loads(scan_process(args.trivy.resolve(), ["--config", "", "--cache-dir", str(args.cache_dir.resolve()), "version", "--format", "json"], w))
        base = ["--cache-dir", str(args.cache_dir.resolve()), "--config", "", "--ignorefile", "", "--secret-config", "",
                "--disable-telemetry", "--offline-scan", "--skip-db-update", "--skip-check-update", "--skip-java-db-update",
                "--skip-vex-repo-update", "--include-non-failures", "--list-all-pkgs", "--format", "json"]
        def report(name, mode, switches, target):
            path = out / (name + ".json")
            scan_process(args.trivy.resolve(), [mode, *base, "--scanners", switches, "--output", str(path), *target], w)
            return read_json(path)
        source = report("source", "fs", "vuln,secret,misconfig", [str(staged)])
        dev = report("including-development", "fs", "vuln", ["--include-dev-deps", str(staged)])
        runtime = report("runtime", "image", "vuln,secret,misconfig", [
            "--image-config-scanners", "secret,misconfig", "--input", str(image)])
        sbom = out / "runtime.spdx.json"
        scan_process(args.trivy.resolve(), ["convert", "--config", "", "--format", "spdx-json",
                                            "--output", str(sbom), str(out / "runtime.json")], w)
        # Refuse data if scanner/DB identity changes during inspection.
        version_after = json.loads(scan_process(args.trivy.resolve(), ["--config", "", "--cache-dir", str(args.cache_dir.resolve()),
                                                                        "version", "--format", "json"], w))
        if version != version_after or sha(args.trivy) != BINARY or gate.revision(project, project_helper) != rev:
            raise ValueError("SCANNER_CHANGED")
        return projection(source, runtime, dev, version, read_json(sbom), source_revision=rev,
                          image_digest=args.image_digest, config=config, sbom_digest="sha256:" + sha(sbom), now=int(time.time()), selected_lock=selected_lock)


def registry_result(call, target, *, image_id, scan_id=None, now):
    """Read-only VSS+Registry checks. Tag-only VSS responses cannot prove immutable identity."""
    digest = target.get("image_digest")
    report = {"schema": "oci-sre-registry-scan/1", "image_digest": digest, "observed_at": now,
              "digest_verified": False, "compartment_repository_verified": False, "reason": "registry-evidence-unavailable"}
    if (not DIGEST.fullmatch(str(digest)) or not target.get("registry_id")
            or not re.fullmatch(r"ocid1\.containerimage\.[a-zA-Z0-9.-]{12,220}", image_id)
            or (scan_id is not None and not re.fullmatch(r"ocid1\.vsscontainerscanresult\.[a-zA-Z0-9.-]{12,220}", scan_id))):
        return report
    def read(args, *, latest=False):
        raw = call(args)
        rows = raw["data"]
        if isinstance(rows, dict):
            rows = rows.get("items")
        # A two-row head of a DESC timeStarted query suffices only when the
        # newest is strictly newer than the runner-up. Older pages cannot win.
        if raw.get("opc-next-page") and not (latest and isinstance(rows, list) and len(rows) == 2
                and moment(rows[0]["time-started"]) > moment(rows[1]["time-started"])):
            raise ValueError("PAGED")
        return raw["data"]
    compartment, repo_id = target["compartment_id"], target["registry_id"]
    try:
        repo = read(["artifacts", "container", "repository", "get", "--repository-id", repo_id])
        image = read(["artifacts", "container", "image", "get", "--image-id", image_id])
        if scan_id is None:
            # Select only a unique latest match; a tag cannot identify a digest retrospectively.
            choices = set()
            for identity in (digest, image_id):
                listed = read(["vulnerability-scanning", "container", "scan", "result", "list", "--compartment-id", compartment,
                               "--repository", repo["display-name"], "--image", identity,
                               "--sort-by", "timeStarted", "--sort-order", "DESC", "--limit", "2"], latest=True)
                rows = listed["items"] if isinstance(listed, dict) else listed
                if rows:
                    if len(rows) > 1 and moment(rows[1]["time-started"]) >= moment(rows[0]["time-started"]):
                        return report
                    choices.add(rows[0]["id"])
            if len(choices) != 1:
                return report
            scan_id = choices.pop()
        scan = read(["vulnerability-scanning", "container", "scan", "result", "get", "--container-scan-result-id", scan_id])
        if (repo["id"] != repo_id or repo["compartment-id"] != compartment or repo["is-public"] is not False
                or image["id"] != image_id or image["compartment-id"] != compartment or image["repository-id"] != repo_id
                or image["repository-name"] != repo["display-name"] or image["digest"] != digest
                or scan["id"] != scan_id or scan["compartment-id"] != compartment
                or scan["target-compartment-id"] != compartment or scan["repository"] != repo["display-name"]):
            return report
        # The currently documented API calls "image" a name, not a digest. Accept
        # only a directly reported immutable identity, never infer one from a tag.
        if scan["image"] not in (digest, image_id):
            return dict(report, reason="service-did-not-bind-immutable-image")
        listing = read(["vulnerability-scanning", "container", "scan", "result", "list", "--compartment-id", compartment,
                        "--repository", scan["repository"], "--image", scan["image"], "--sort-by", "timeStarted",
                        "--sort-order", "DESC", "--limit", "2"], latest=True)
        rows = listing["items"] if isinstance(listing, dict) else listing
        if (not rows or rows[0]["id"] != scan_id or rows[0]["time-started"] != scan["time-started"]
                or len(rows) > 1 and moment(rows[1]["time-started"]) >= moment(scan["time-started"])):
            return report
        started, finished = moment(scan["time-started"]), moment(scan["time-finished"])
        if not moment(image["time-created"]) <= started <= finished <= now:
            return report
        return dict(report, digest_verified=True, compartment_repository_verified=True, reason="latest-bound-result",
                    finished_at=finished, severity=scan["highest-problem-severity"], problem_count=scan["problem-count"])
    except (OSError, LookupError, TypeError, ValueError, RuntimeError):
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="command", required=True)
    scan = cmds.add_parser("scan", help="scan the tracked revision and the immutable local image")
    registry = cmds.add_parser("registry", help="read the selected registry's latest scan, without changes")
    for command in (scan, registry):
        command.add_argument("--project", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True, help="new private directory outside the project")
    scan.add_argument("--app-directory", help="Own-app Next.js source directory within the reviewed repository; use . for the root")
    scan.add_argument("--layout", type=Path, required=True)
    scan.add_argument("--image-digest", required=True)
    scan.add_argument("--trivy", type=Path, required=True)
    scan.add_argument("--cache-dir", type=Path, required=True)
    registry.add_argument("--image-id", required=True)
    registry.add_argument("--scan-id", help="Optional latest scan result; otherwise search immutable identity only")
    registry.add_argument("--require-deployed", action="store_true", help="Require actual running production digest for day-two monitoring")
    registry.add_argument("--environment", required=True)
    registry.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
    args = parser.parse_args(argv)
    old_mask = os.umask(0o077)
    report = None
    try:
        out = args.output.absolute()
        # Refuse symlink ancestors and never overlay existing results or source.
        if out.parent.resolve(strict=True) != out.parent or out.is_relative_to(args.project.resolve()):
            raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
        out.mkdir(mode=0o700)
        if args.command == "scan":
            report = run_scan(args, out)
            status = gate_status(report, image_digest=args.image_digest, now=int(time.time()))
        else:
            ops = load(ROOT / "scripts/operations.py")
            common, p = ops.modules()
            common.select(args.project, args.environment, required=True)
            with p.Store(args.project, environment=args.environment) as store:
                target = ops.role_config(store, p, "web")["target"]
                if args.require_deployed and store.environment_config["role"] != "production":
                    raise ValueError("DEPLOYED_PRODUCTION_REQUIRED")
                report = registry_result(ops.Client(p, target, args.config_file), target, image_id=args.image_id,
                                         scan_id=args.scan_id, now=int(time.time()))
                status = registry_status(report, image_digest=target["image_digest"], now=int(time.time()))
            if args.require_deployed:
                observation = ops.request(args.project, environment=args.environment, live=True, config_file=args.config_file)
                if (observation.get("mode") != "live-read-only" or not observation.get("image_identity_verified")
                        or observation.get("observed_image_digest") != report["image_digest"]):
                    status = "unknown"
                    report.update(digest_verified=False, reason="currently-deployed-image-unverified")
        with (out / "summary.json").open("x") as stream:
            json.dump(report, stream, allow_nan=False, sort_keys=True)
        print(json.dumps({"status": status, "summary": "summary.json", "uploaded": False}))
        return 0 if status == "passed" else 1 if status == "blocked" else 2
    except (Exception, KeyboardInterrupt):
        # Do not print inherited tool failures, broken file paths, API responses or findings.
        print('{"status":"unknown","code":"SCAN_INCOMPLETE","recovery":"Check the pinned binary, database, commit, private paths, image layout or registry access. Use a new output directory."}')
        return 2
    finally:
        os.umask(old_mask)


if __name__ == "__main__":
    raise SystemExit(main())
