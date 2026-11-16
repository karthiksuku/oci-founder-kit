#!/usr/bin/env python3
"""Additive packaging proposals and bounded, explicitly requested local image checks.

Build commands are displayed for review, never executed. Verification runs only
the selected immutable image, without a network, mounted files or credentials.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import string
import tarfile
import tempfile
import time
import uuid
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ("nextjs", "fastapi", "dockerfile")
LIMIT = 512 * 1024 * 1024
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE = re.compile(r"[a-z0-9][a-z0-9./:_-]{0,180}@sha256:[0-9a-f]{64}")
# A PEM delimiter alone occurs in public TLS libraries and npm documentation.
# Require base64 DER-sequence/OpenSSH material, including escaped JSON newlines.
# Public TLS binaries contain a PEM delimiter beside their base64 alphabet table.
# OpenSSL's sk_* C function identifiers also are not API-token prefixes.
PATTERN = re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----(?:\r?\n|\\r\\n|\\n)(?:M[A-P][A-Za-z0-9+/=]{30,}|b3BlbnNzaC1rZXktdjE[A-Za-z0-9+/=]{16,})|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{24,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b|\bnpm_[A-Za-z0-9]{30,}\b|(?<![A-Za-z0-9_])(?:sk-proj-[A-Za-z0-9_-]{40,}|(?:sk|xai)-[A-Za-z0-9]{32,})\b")
PRIVATE_NAMES = {".oci", ".aws", ".ssh", ".oci-kit", ".oci-founder-kit", ".docker", ".azure", ".kube",
                 ".npmrc", ".pypirc", ".netrc", ".git-credentials", ".gate", ".env", "id_rsa", "id_ed25519",
                 "credentials", "tokens.json", "application_default_credentials.json"}


def credential_configuration(value):
    """Inspect image environment values only, never generic library source text."""
    for entry in value.get("config", {}).get("Env", []):
        key, separator, content = entry.partition("=")
        if not separator or not content:
            continue
        secret_name = re.search(r"PASSWORD|PASSWD|TOKEN|SECRET|PRIVATE_KEY|CREDENTIAL", key, re.I)
        key_name = re.search(r"(?:^|_)(?:API|ACCESS|AUTH|SIGNING|ENCRYPTION|SESSION|MASTER|CLIENT|APP|JWT)_?KEY(?:$|_)", key, re.I)
        if secret_name or key_name:
            return True
        # OCI/Docker JSON escapes are decoded by json.loads. Also recognize
        # userinfo in percent-encoded and literal JSON-escaped connection URLs.
        normalized = content
        for _ in range(4):
            # Inspect before decoding, too: encoded "/" inside a valid password
            # must not become a path delimiter that hides the original userinfo.
            if re.search(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#]*:[^/\s?#]*@", normalized):
                return True
            normalized = unquote(normalized).replace(r"\/", "/")
            normalized = re.sub(r"\\u00(?:2[fF]|3[aA]|40)", lambda match: chr(int(match[0][-2:], 16)), normalized)
    return False


class PackagingError(ValueError):
    def __init__(self, code, recovery):
        self.code, self.recovery = code, recovery
        super().__init__(recovery)


def project_module():
    spec = importlib.util.spec_from_file_location("oci_packaging_project", ROOT / "scripts/project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def relative(value, *, dot=False):
    if dot and value == ".":
        return ()
    if (not isinstance(value, str) or len(value) > 180 or PurePosixPath(value).as_posix() != value
            or value.startswith("/") or len(value.split("/")) > 8
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", x) for x in value.split("/"))):
        raise PackagingError("PACKAGE_PATH", "Choose an ordinary relative application path without links or traversal.")
    return tuple(value.split("/"))


def descriptor_value(value):
    required = {"schema", "recipe", "app_directory", "port", "health_path", "commands", "dependencies", "background_work", "probe_runtime"}
    optional = {"base_image", "entrypoint", "dockerfile"}
    if (not isinstance(value, dict) or not required.issubset(value) or not set(value).issubset(required | optional)
            or value["schema"] != "oci-kit-application/1" or value["recipe"] not in RECIPES
            or type(value["port"]) is not int or not 1024 <= value["port"] <= 65535
            or not isinstance(value["health_path"], str) or not re.fullmatch(r"/[A-Za-z0-9/_-]{0,120}", value["health_path"])
            or value["probe_runtime"] not in {"node", "python"}
            or value["background_work"] not in {"absent", "disabled", "source"}):
        raise PackagingError("PACKAGE_DESCRIPTOR", "Use the application descriptor schema; keep background processing absent, disabled or retained at source.")
    relative(value["app_directory"], dot=True)
    commands = value["commands"]
    if not isinstance(commands, dict) or set(commands) != {"build", "start", "test"}:
        raise PackagingError("PACKAGE_COMMANDS", "Describe build, start and test as argument lists; they are never automatically executed.")
    for command in commands.values():
        if (not isinstance(command, list) or not 1 <= len(command) <= 32
                or any(not isinstance(x, str) or not x or len(x) > 240 or any(ord(c) < 32 for c in x) for x in command)):
            raise PackagingError("PACKAGE_COMMANDS", "Use bounded command argument lists without control characters or secret values.")
    if (not isinstance(value["dependencies"], list) or len(value["dependencies"]) > 30
            or any(not isinstance(x, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", x) for x in value["dependencies"])
            or len(set(value["dependencies"])) != len(value["dependencies"])):
        raise PackagingError("PACKAGE_DEPENDENCIES", "List dependency names only; keep endpoints, keys and account identifiers private.")
    if value["recipe"] != "dockerfile":
        if not isinstance(value.get("base_image"), str) or not IMAGE.fullmatch(value["base_image"]):
            raise PackagingError("PACKAGE_BASE_DIGEST", "Select and review a compatible base image by immutable repository@sha256 digest.")
        if value["probe_runtime"] != {"nextjs": "node", "fastapi": "python"}[value["recipe"]]:
            raise PackagingError("PACKAGE_RUNTIME", "Select the runtime matching the recipe.")
    if value["recipe"] == "fastapi" and (not isinstance(value.get("entrypoint"), str) or
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*", value["entrypoint"])):
        raise PackagingError("PACKAGE_ENTRYPOINT", "Select the existing ASGI module and callable, for example app.main:app.")
    if value["recipe"] == "dockerfile":
        relative(value.get("dockerfile", "Dockerfile"))
    return value


def read_private(path, p):
    path = Path(path).expanduser().absolute()
    _, fd = p.open_project(path.parent)
    try:
        return p.object_at(fd, path.name, private=True)
    finally:
        os.close(fd)


def app_fd(store, descriptor, p):
    fd = os.dup(store.root_fd)
    try:
        for part in relative(descriptor["app_directory"], dot=True):
            following = os.open(part, p.DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except Exception:
        os.close(fd)
        raise


def read_relative(fd, path, p):
    parts = (path,) if path == ".dockerignore" else relative(path)
    folder = os.dup(fd)
    try:
        for name in parts[:-1]:
            following = os.open(name, p.DIRECTORY, dir_fd=folder)
            os.close(folder)
            folder = following
        return p.read_at(folder, parts[-1], maximum=4 * p.LIMIT)
    finally:
        os.close(folder)


def health_command(value):
    url = f"http://127.0.0.1:{value['port']}{value['health_path']}"
    if value["probe_runtime"] == "node":
        program = "require('http').get(" + json.dumps(url) + ",r=>{r.resume();process.exit(r.statusCode===200?0:1)}).on('error',()=>process.exit(1)).setTimeout(2000,()=>process.exit(1))"
        return "node -e " + shlex.quote(program)
    program = "import urllib.request; r=urllib.request.urlopen(" + repr(url) + ",timeout=2); assert r.status==200"
    return "python -c " + shlex.quote(program)


def prepare_files(fd, value, p):
    findings, inputs, files = [], {}, {}

    def read(path):
        try:
            raw = read_relative(fd, path, p)
        except FileNotFoundError:
            findings.append({"code": "PACKAGE_INPUT_MISSING", "input": path})
            return b""
        inputs[path] = p.digest(raw)
        return raw

    recipe = value["recipe"]
    if recipe == "nextjs":
        raw = read("package.json")
        if raw:
            package = json.loads(raw, object_pairs_hook=p.unique)
            if not isinstance(package, dict) or "next" not in {**package.get("dependencies", {}), **package.get("devDependencies", {})}:
                findings.append({"code": "PACKAGE_NEXT_DEPENDENCY"})
        read("package-lock.json")
        configs = []
        for name in ("next.config.js", "next.config.mjs", "next.config.ts"):
            try:
                raw = read_relative(fd, name, p)
                inputs[name] = p.digest(raw)
                configs.append(raw)
            except FileNotFoundError:
                pass
        # This is a static prerequisite, not execution of arbitrary config code.
        if len(configs) != 1 or not re.search(rb"\boutput\s*:\s*['\"]standalone['\"]", configs[0]):
            findings.append({"code": "PACKAGE_STANDALONE_REQUIRED", "recovery": "Review existing Next config and select standalone output; the kit will not rewrite it."})
    elif recipe == "fastapi":
        raw = read("requirements.txt")
        if raw and (b"--hash=sha256:" not in raw or b"uvicorn" not in raw.lower()):
            findings.append({"code": "PACKAGE_LOCKED_REQUIREMENTS", "recovery": "Provide hash-locked requirements including uvicorn; dependency resolution stays in your existing tooling."})
    else:
        dockerfile = value.get("dockerfile", "Dockerfile")
        raw = read(dockerfile)
        stages = set()
        for line in raw.decode("utf-8").splitlines():
            if not re.match(r"\s*FROM\s", line, re.I):
                continue
            parts = line.split()
            source = parts[1] if len(parts) > 1 else ""
            if not IMAGE.fullmatch(source) and source not in stages and source != "scratch":
                findings.append({"code": "PACKAGE_UNPINNED_FROM", "recovery": "Review and pin each external FROM image; dynamic FROM/platform directives need manual adaptation."})
            if len(parts) == 4 and parts[2].lower() == "as":
                stages.add(parts[3])
        if not raw or not re.search(rb"(?im)^\s*FROM\s", raw):
            findings.append({"code": "PACKAGE_DOCKERFILE_REQUIRED"})
    if recipe != "dockerfile":
        template = ROOT / "recipes" / recipe / "Dockerfile.template"
        _, folder = p.open_project(template.parent)
        try:
            content = p.read_at(folder, template.name).decode()
        finally:
            os.close(folder)
        rendered = string.Template(content).substitute(value)
        rendered += "HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD " + health_command(value) + "\n"
        files["Dockerfile.oci"] = rendered
        dockerfile = "Dockerfile.oci"
    # Dockerfile-specific ignore takes precedence without replacing an existing .dockerignore.
    ignore = dockerfile + ".dockerignore"
    try:
        previous = read_relative(fd, ".dockerignore", p)
        inputs[".dockerignore"] = p.digest(previous)
    except FileNotFoundError:
        previous = b""
    files[ignore] = previous.decode("utf-8") + "\n# OCI Founder Kit private-input exclusions (keep last)\n" + "\n".join(
        "**/" + item for item in (".git", *sorted(PRIVATE_NAMES), ".npmrc.*", ".pypirc.*", ".netrc.*", ".git-credentials.*",
                                  ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.tfstate*", "*.tfvars*", "*.tfbackend*",
                                  "*.tfplan", "node_modules", ".next", "__pycache__", ".venv")) + "\n"
    for name in files:
        if len(relative(name)) != 1:
            findings.append({"code": "PACKAGE_NESTED_DOCKERFILE", "recovery": "Select a Dockerfile in the application directory for this preview."})
            continue
        try:
            os.stat(name, dir_fd=fd, follow_symlinks=False)
            findings.append({"code": "PACKAGE_DESTINATION_EXISTS", "input": name})
        except FileNotFoundError:
            pass
    return files, inputs, findings, dockerfile


def save_named(store, name, value, p):
    temporary = ".package-" + uuid.uuid4().hex
    try:
        store.create_file(temporary, p.canonical(value) + b"\n")
        os.replace(temporary, name, src_dir_fd=store.fd, dst_dir_fd=store.fd)
        os.fsync(store.fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=store.fd)


def scan_layout(path, artifact, gate):
    """Inspect every archived layer, including files deleted in later layers; never extract."""
    findings, entries, scanned = set(), 0, 0
    with gate.directory(path) as folder:
        raw = gate.read_at(folder, artifact["config"]["digest"][7:])
        config = json.loads(raw)
        if PATTERN.search(raw):
            findings.add("credential_pattern")
        if credential_configuration(config):
            findings.add("credential_environment")
        for layer in artifact["layers"]:
            fd = os.open(layer["digest"][7:], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
            with os.fdopen(fd, "rb") as raw_layer, gzip.GzipFile(fileobj=raw_layer) as compressed, tarfile.open(fileobj=compressed, mode="r|") as archive:
                for member in archive:
                    entries += 1
                    if entries > 100000:
                        raise PackagingError("PACKAGE_SCAN_LIMIT", "Image archive exceeds the inspection bound; use a smaller image.")
                    parts = PurePosixPath(member.name).parts
                    # Public Node images include an empty builtin .npmrc. A zero-
                    # byte regular file cannot embed credentials; nonempty files
                    # and any earlier layer containing them still fail.
                    empty_npmrc = member.isfile() and member.size == 0 and parts[-1:] == (".npmrc",)
                    if not empty_npmrc and any(part.lower() in PRIVATE_NAMES or re.match(r"^\.(?:env|npmrc|pypirc|netrc|git-credentials)[.~]", part.lower()) for part in parts):
                        findings.add("private_input_path")
                    if member.isfile():
                        stream, tail = archive.extractfile(member), b""
                        while block := stream.read(65536):
                            scanned += len(block)
                            if scanned > LIMIT:
                                raise PackagingError("PACKAGE_SCAN_LIMIT", "Image archive exceeds the inspection bound.")
                            if PATTERN.search(tail + block):
                                findings.add("credential_pattern")
                            tail = block[-256:]
    return {"status": "blocked" if findings else "passed", "findings": sorted(findings), "entries": entries,
            "bytes_scanned": scanned, "scope": "Known credential patterns and private paths in every image layer and image configuration; not proof that arbitrary secrets are absent."}


def local_health(value, image, gate):
    docker = gate.fingerprint("docker")
    # Deliberately ignore Docker contexts, credential helpers and endpoint overrides.
    with tempfile.TemporaryDirectory(prefix="oci-package-docker-") as config:
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": config, "DOCKER_CONFIG": config, "DOCKER_HOST": "unix:///var/run/docker.sock"}
        def run(args):
            return gate.run(docker, args, timeout=10, environment=environment)
        source = json.loads(run(["image", "inspect", "--format", '{"id":{{json .Id}},"size":{{json .Size}},"os":{{json .Os}},"architecture":{{json .Architecture}},"variant":{{json (index . "Variant")}}}', image]))
        if source.get("id") != image or source.get("os") != "linux" or source.get("architecture") != "amd64":
            raise PackagingError("PACKAGE_ARCHITECTURE", "Use a local immutable Linux AMD64 image for the current E4 blueprint.")
        name = "oci-kit-check-" + uuid.uuid4().hex
        started = False
        try:
            run(["run", "--detach", "--name", name, "--pull", "never", "--network", "none", "--read-only",
                 "--user", "65532:65532", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128",
                 "--memory", "512m", "--cpus", "1", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--log-driver", "none",
                 "--health-cmd", health_command(value), "--health-interval", "1s", "--health-timeout", "3s",
                 "--health-retries", "2", "--health-start-period", "1s", image])
            started = True
            for _ in range(20):
                payload = json.loads(run(["inspect", "--format", '{"running":{{json .State.Running}},"health":{{json .State.Health.Status}},"image":{{json .Image}}}', name]))
                if payload.get("image") != image:
                    raise PackagingError("PACKAGE_IMAGE_CHANGED", "Recheck the local immutable image identity.")
                if payload.get("health") == "healthy":
                    return source, {"status": "passed", "scope": "HTTP 200 at the descriptor health route inside an isolated local image. External dependencies and meaningful workflows are not checked."}
                if not payload.get("running") or payload.get("health") == "unhealthy":
                    break
                time.sleep(1)
            return source, {"status": "blocked", "code": "PACKAGE_HEALTH", "recovery": "Check the health route, non-root/read-only runtime and dependency-free liveness behavior locally; no raw logs were collected."}
        finally:
            # A failed Docker response can still have created a container.
            try:
                run(["rm", "--force", "--volumes", name])
            except Exception:
                if started:
                    raise PackagingError("PACKAGE_CLEANUP", "Inspect and remove the retained local oci-kit-check container before retrying.")


def request(project: Path, *, environment: str, action="inspect", descriptor=None, approve=None, image=None, layout=None):
    if not environment:
        raise PackagingError("PACKAGE_ENVIRONMENT", "Select a named environment explicitly; legacy progress is never selected.")
    p = project_module()
    if action not in {"inspect", "propose", "apply", "verify"}:
        raise PackagingError("PACKAGE_ACTION", "Select inspect, propose, apply or verify.")
    with p.Store(project, environment=environment, write=action != "inspect") as store:
        store.read()
        if store.environment_config["role"] == "source":
            raise PackagingError("PACKAGE_SOURCE", "Select the explicit OCI rehearsal or production environment.")
        binding = p.digest(p.canonical(store.environment_config))
        source = p.source_fingerprint(store.root_fd)
        if action == "inspect":
            try:
                saved = p.object_at(store.fd, "application.json", private=True)
                return {"schema": "oci-kit-package/1", "status": "configured", "recipe": descriptor_value(saved)["recipe"], "environment": environment,
                        "next": "propose", "cloud": "not_checked"}
            except FileNotFoundError:
                return {"schema": "oci-kit-package/1", "status": "blocked", "code": "PACKAGE_DESCRIPTOR_REQUIRED", "environment": environment,
                        "missing": ["recipe", "app_directory", "commands", "port", "health_path", "dependencies", "background_work", "probe_runtime"], "next": "propose"}
        if action == "propose":
            value = descriptor_value(read_private(descriptor, p) if descriptor else p.object_at(store.fd, "application.json", private=True))
            fd = app_fd(store, value, p)
            try:
                files, inputs, findings, dockerfile = prepare_files(fd, value, p)
                application_identity = p.identity(fd)
            finally:
                os.close(fd)
            proposal = {"schema": "oci-kit-package-proposal/1", "environment": environment, "binding": binding,
                        "project_identity": p.identity(store.root_fd), "app_identity": application_identity, "source_sha256": source,
                        "descriptor": value, "inputs": inputs, "files": files, "created_at": int(time.time()), "findings": findings}
            sha = p.digest(p.canonical(proposal))
            save_named(store, "package-proposal.json", proposal, p)
            save_named(store, "application.json", value, p)
            return {"schema": "oci-kit-package/1", "status": "blocked" if findings else "review", "environment": environment,
                    "sha256": sha, "findings": findings, "proposed_files": [{"path": key, "content": content} for key, content in files.items()],
                    "build_command": ["docker", "buildx", "build", "--load", "--platform", "linux/amd64", "--file", dockerfile, "."],
                    "build_directory": value["app_directory"], "next": "apply", "scope": "Only additive packaging files. Review build scripts separately; no commands run and no cloud approval is created."}
        if action == "apply":
            proposal = p.object_at(store.fd, "package-proposal.json", private=True)
            value = descriptor_value(proposal["descriptor"])
            if (not isinstance(approve, str) or approve != p.digest(p.canonical(proposal)) or proposal["environment"] != environment
                    or proposal["binding"] != binding or proposal["source_sha256"] != source or proposal["findings"]
                    or proposal["project_identity"] != p.identity(store.root_fd)
                    or not 0 <= int(time.time()) - proposal["created_at"] <= 3600):
                raise PackagingError("PACKAGE_STALE_PROPOSAL", "Prepare and review a fresh packaging proposal for this environment; use its exact SHA-256.")
            fd = app_fd(store, value, p)
            try:
                files, inputs, findings, _ = prepare_files(fd, value, p)
                if findings or files != proposal["files"] or inputs != proposal["inputs"] or p.identity(fd) != proposal["app_identity"]:
                    raise PackagingError("PACKAGE_CHANGED", "Application, recipe or destination changed; prepare a fresh proposal.")
                for name, content in files.items():
                    p.helper("environments").put(fd, name, content.encode())
                os.fsync(fd)
            finally:
                os.close(fd)
            return {"schema": "oci-kit-package/1", "status": "applied", "environment": environment, "files_added": list(files),
                    "application_source": "preserved", "commands_executed": False, "next": "review-build-and-test", "cloud": "not_checked"}
        value = descriptor_value(p.object_at(store.fd, "application.json", private=True))
        if not isinstance(image, str) or not DIGEST.fullmatch(image) or layout is None:
            raise PackagingError("PACKAGE_IMAGE_INPUT", "Supply a tested local sha256 image ID and private single-platform skopeo dir v2s2 layout.")
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/image_gate.py")
        # Bind and scan the exact image bytes before executing the selected image.
        expected = {"id": image, "os": "linux", "architecture": "amd64", "variant": ""}
        artifact = gate.layout_artifact(Path(layout), expected, LIMIT)
        scan = scan_layout(Path(layout), artifact, gate)
        health = {"status": "not_run"}
        if scan["status"] == "passed":
            _, health = local_health(value, image, gate)
        final = gate.layout_artifact(Path(layout), expected, LIMIT)
        if final != artifact or p.source_fingerprint(store.root_fd) != source:
            raise PackagingError("PACKAGE_CHANGED", "Application or image bytes changed during inspection; repeat verification.")
        report = {"schema": "oci-kit-package-verification/1", "environment": environment, "environment_sha256": binding,
                  "source_sha256": source, "observed_at": int(time.time()), "image_config_digest": image,
                  "image_digest": artifact["manifest_digest"], "image_architecture": "AMD64", "credential_scan": scan,
                  "health": health, "status": "passed" if scan["status"] == health["status"] == "passed" else "blocked",
                  "evidence_scope": "local-tested", "cloud": "not_checked", "publication": "separate exact image-gate plan required"}
        report["evidence"] = p.save_report(store, report, "package")
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "propose", "apply", "verify"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--environment", required=True)
    for name in ("descriptor", "layout"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--approve")
    parser.add_argument("--image")
    args = parser.parse_args(argv)
    try:
        value = request(**vars(args))
        print(json.dumps(value, indent=2))
        return 2 if value["status"] == "blocked" else 0
    except Exception:
        print(json.dumps({"status": "blocked", "code": "PACKAGE_INPUT_OR_CHECK_FAILED", "recovery": "Review private inputs, local Docker access and the packaging guide; no raw client output is disclosed."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
