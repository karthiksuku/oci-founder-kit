"""Exact-image publication for deploy_gate; no login, token creation or shell commands.

Only existing, immutable, private commercial-realm OCIR repositories are supported.
The receipt and CLI are trusted local inputs, not proof of human approval. The
owner must approve the displayed hash in the conversation. Same-user tampering,
changes to Docker's daemon or installed libraries, and external IAM changes are
outside this local gate's isolation boundary. Raw client output is never saved.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

PLAN = "image-plan.json"
MAX_JSON = 1_000_000
MAX_OUTPUT = 2_000_000
DEFAULT_MAX_IMAGE_BYTES = 1024 ** 3
MAX_IMAGE_BYTES = 10 * 1024 ** 3
AUTH = {"APIKey": "api_key", "SecurityToken": "security_token",
        "InstancePrincipal": "instance_principal", "ResourcePrincipal": "resource_principal"}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
REPOSITORY = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*")


class ImageGateError(Exception):
    def __init__(self, message: str, code: int = 3):
        super().__init__(message)
        self.code = code


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImageGateError(message)


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON fields are not accepted.")
        result[key] = value
    return result


def parse(raw: bytes):
    require(len(raw) <= MAX_JSON, "JSON exceeds the permitted size.")
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


@contextlib.contextmanager
def directory(path: Path):
    """Open every directory component without following symlinks; pin the fd."""
    path = path.absolute()
    require(".." not in path.parts, "Parent traversal is not accepted.")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def private_directory(parent: int, name: str):
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        meta = os.fstat(fd)
        require(meta.st_uid == os.getuid() and not meta.st_mode & 0o077,
                "Gate directories must be owned by this user and private (0700).")
        yield fd
    finally:
        os.close(fd)


def regular(fd: int, private: bool = True) -> None:
    meta = os.fstat(fd)
    require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1,
            "Gate inputs must be regular files with a single link.")
    if private:
        require(meta.st_uid == os.getuid() and not meta.st_mode & 0o077,
                "Gate inputs must be owned by this user and private (0600).")


def read_at(parent: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, "rb") as handle:
        regular(handle.fileno())
        raw = handle.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, "Gate file exceeds the permitted size.")
    return raw


def read_private(path: Path) -> bytes:
    with directory(path.parent) as fd:
        return read_at(fd, path.name)


def write_at(parent: int, name: str, value: dict, exclusive: bool = False) -> None:
    raw = canonical(value) + b"\n"
    require(len(raw) <= MAX_JSON, "Gate output exceeds the permitted size.")
    try:
        meta = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        meta = None
    if meta:
        require(not exclusive, "This approval already has an attempt receipt; re-plan.")
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid == os.getuid(),
                "Refusing an unsafe gate output file.")
    temporary = name if exclusive else ".image-" + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if not exclusive:
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        if not exclusive:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent)


@contextlib.contextmanager
def workspace(stack: Path):
    with directory(stack) as root, private_directory(root, ".gate") as gate:
        fd = os.open("image.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=gate)
        try:
            regular(fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ImageGateError("Another image gate operation is running.") from None
            yield gate
        finally:
            os.close(fd)


def fingerprint(name: str) -> dict:
    value = os.environ.get(name.upper() + "_BIN", name)
    require(bool(value) and not any(c.isspace() for c in value), "Client must be a single executable path.")
    found = shutil.which(value)
    require(found is not None, "A required local client is unavailable.")
    path = Path(found).resolve(strict=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    digest, size = hashlib.sha256(), 0
    with os.fdopen(fd, "rb") as handle:
        regular(handle.fileno(), private=False)
        while block := handle.read(1024 * 1024):
            size += len(block)
            require(size <= 256 * 1024 * 1024, "Client executable exceeds the permitted size.")
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest()}


def run(binary: dict, arguments: list[str], timeout: int = 45) -> bytes:
    """Bound output and time; discard stderr and never interpolate shell text."""
    env = {k: v for k, v in os.environ.items() if k not in {
        "OCI_CLI_ENDPOINT", "OCI_CLI_DEFAULTS_FILE", "OCI_CLI_RC_FILE", "OCI_CLI_QUERY",
        "OCI_CLI_DEBUG", "OCI_CLI_AUTO_PROMPT", "OCI_CLI_FEDERATION_ENDPOINT",
        "OCI_CLI_REALM_SPECIFIC_ENDPOINT", "OCI_REGION_METADATA"}}
    output = bytearray()
    process = subprocess.Popen([binary["path"], *arguments], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=env, start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            while selector.get_map():
                require(time.monotonic() < deadline, "Client timed out; inspect the private receipt before retrying.")
                for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(block)
                        require(len(output) <= MAX_OUTPUT, "Client output exceeded the permitted size.")
            remaining = max(0.001, deadline - time.monotonic())
            code = process.wait(timeout=remaining)
        if code:
            raise ImageGateError("Client failed; check existing credentials, permissions and connectivity privately.", 1)
        return bytes(output)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        process.stdout.close()


def oci(binary: dict, target: dict, arguments: list[str]):
    # Disable CLI defaults so they cannot add endpoint overrides or a query.
    raw = run(binary, [*arguments, "--region", target["region"], "--profile", target["profile"],
                       "--auth", AUTH[target["auth"]], "--output", "json", "--cli-rc-file", os.devnull,
                       "--no-retry", "--connection-timeout", "10", "--read-timeout", "30"])
    payload = parse(raw)
    require(isinstance(payload, dict) and "data" in payload, "OCI returned an unrecognized response.")
    return payload["data"]


def ocid(value, kind: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"ocid1\." + kind + r"\.oc1\.[a-z0-9-]*\.[a-z0-9]+", value) is not None


def registry_receipt(path: Path, repository_id: str) -> tuple[dict, str]:
    raw = read_private(path)
    receipt = parse(raw)
    require(isinstance(receipt, dict) and receipt.get("schema") == "oci-deploy-receipt/2"
            and receipt.get("kind") == "apply" and receipt.get("status") == "applied",
            "Use a successful registry apply receipt from this deploy tool.")
    source = receipt.get("target")
    require(isinstance(source, dict), "The registry receipt has no target.")
    target = {key: source.get(key) for key in ("region", "profile", "auth", "compartment_ocid", "tenancy_ocid")}
    require(ocid(target["tenancy_ocid"], "tenancy") and ocid(target["compartment_ocid"], "compartment")
            and ocid(repository_id, "containerrepo"), "A commercial-realm tenancy, compartment and repository are required.")
    require(isinstance(target["region"], str) and re.fullmatch(r"[a-z]+-[a-z]+-\d+", target["region"])
            and isinstance(target["profile"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", target["profile"])
            and target["auth"] in AUTH, "The receipt must declare region, profile and authentication mode.")
    resources = receipt.get("resources")
    require(isinstance(resources, list), "The registry receipt has no resources.")
    found = [r for r in resources if isinstance(r, dict) and r.get("id") == repository_id
             and r.get("type") == "oci_artifacts_container_repository"]
    require(len(found) == 1 and found[0].get("compartment_id") == target["compartment_ocid"],
            "The receipt does not identify exactly one repository in the target compartment.")
    planned = receipt.get("planned")
    require(isinstance(planned, list) and any(isinstance(r, dict) and r.get("address") == found[0].get("address")
            and r.get("type") == "oci_artifacts_container_repository" and r.get("action") == "create" for r in planned),
            "The receipt must record creation of this repository.")
    name = found[0].get("name")
    require(isinstance(name, str) and len(name) <= 255 and REPOSITORY.fullmatch(name), "Unsupported repository name.")
    target.update(repository_id=repository_id, repository_name=name)
    return target, sha(raw)


def verify_registry(binary: dict, target: dict) -> dict:
    repository = oci(binary, target, ["artifacts", "container", "repository", "get", "--repository-id", target["repository_id"]])
    require(isinstance(repository, dict) and repository.get("id") == target["repository_id"]
            and repository.get("compartment-id") == target["compartment_ocid"]
            and repository.get("display-name") == target["repository_name"]
            and repository.get("is-public") is False and repository.get("is-immutable") is True
            and repository.get("lifecycle-state") == "AVAILABLE"
            and repository.get("repository-type") in (None, "STANDARD")
            and repository.get("is-top-level") in (None, False),
            "Cannot confirm the exact available, private, immutable standard repository.")
    namespace = oci(binary, target, ["os", "ns", "get", "--compartment-id", target["tenancy_ocid"]])
    require(isinstance(namespace, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", namespace)
            and repository.get("namespace") == namespace, "The repository namespace does not match the expected tenancy.")
    regions = oci(binary, target, ["iam", "region", "list", "--all"])
    require(isinstance(regions, list), "Cannot confirm the registry region.")
    matches = [r for r in regions if isinstance(r, dict) and r.get("name") == target["region"]]
    require(len(matches) == 1 and isinstance(matches[0].get("key"), str)
            and re.fullmatch(r"[A-Z]{3}", matches[0]["key"]), "Cannot confirm the official registry endpoint.")
    return {**target, "namespace": namespace, "registry_host": matches[0]["key"].lower() + ".ocir.io"}


def image(binary: dict, reference: str) -> dict:
    require(isinstance(reference, str) and 1 <= len(reference) <= 512 and not reference.startswith("-")
            and re.fullmatch(r"[A-Za-z0-9_./:@-]+", reference), "Unsupported local image reference.")
    # Do not request Config.Env, labels or other potentially secret-bearing fields.
    template = ('{"id":{{json .Id}},"size":{{json .Size}},"os":{{json .Os}},'
                '"architecture":{{json .Architecture}},"variant":{{json (index . "Variant")}}}')
    data = parse(run(binary, ["image", "inspect", "--format", template, reference]))
    if isinstance(data, dict) and data.get("variant") is None:
        data["variant"] = ""
    require(isinstance(data, dict) and isinstance(data.get("id"), str) and DIGEST.fullmatch(data["id"])
            and type(data.get("size")) is int and data["size"] > 0
            and data.get("os") == "linux" and data.get("architecture") in ("amd64", "arm64")
            and isinstance(data.get("variant"), str) and re.fullmatch(r"[a-z0-9]*", data["variant"]),
            "Cannot identify a supported immutable Linux image and platform.")
    return {key: data[key] for key in ("id", "size", "os", "architecture", "variant")}


def absent(binary: dict, target: dict, tag: str) -> None:
    # An exact version filter plus a successful complete result distinguishes
    # absence from an authentication/NotAuthorizedOrNotFound failure.
    data = oci(binary, target, ["artifacts", "container", "image", "list", "--compartment-id", target["compartment_ocid"],
                               "--repository-id", target["repository_id"], "--image-version", tag, "--all"])
    require(isinstance(data, dict) and isinstance(data.get("items"), list), "Cannot confirm destination tag absence.")
    require(not data["items"], "Destination tag exists or cannot be confirmed absent; choose a new tag and re-plan.")


def destination(target: dict, tag: str) -> str:
    return f"{target['registry_host']}/{target['namespace']}/{target['repository_name']}:{tag}"


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def plan(args, gate: int) -> int:
    require(1 <= args.max_age_minutes <= 1440, "Approval expiry must be between 1 and 1440 minutes.")
    require(1 <= args.max_image_bytes <= MAX_IMAGE_BYTES, "Image limit must be positive and at most 10 GiB.")
    require(TAG.fullmatch(args.tag) is not None, "Unsupported destination tag.")
    target, receipt_hash = registry_receipt(args.registry_receipt, args.repository_id)
    binaries = {name: fingerprint(name) for name in ("docker", "oci")}
    source = image(binaries["docker"], args.image)
    require(source["size"] <= args.max_image_bytes, "Local image exceeds the approved size limit.")
    target = verify_registry(binaries["oci"], target)
    absent(binaries["oci"], target, args.tag)
    now = time.time()
    value = {"schema": "oci-image-plan/1", "stack_path": str(args.dir.absolute()),
             "source_receipt": {"path": str(args.registry_receipt.absolute()), "sha256": receipt_hash},
             "source_image": source, "target": target, "tag": args.tag, "destination": destination(target, args.tag),
             "binaries": binaries, "max_image_bytes": args.max_image_bytes,
             "created_at_epoch": now, "expires_at_epoch": now + args.max_age_minutes * 60}
    digest = sha(canonical(value))
    write_at(gate, PLAN, {"plan": value, "plan_sha256": digest})
    sys.stdout.write(f"Image publication plan (one new tag, no repository or credential creation)\n"
                     f"Destination: {value['destination']}\nRegion: {target['region']}\n"
                     f"Tenancy: {target['tenancy_ocid']}\nCompartment: {target['compartment_ocid']}\n"
                     f"Repository: {target['repository_id']}\nProfile/auth: {target['profile']} / {target['auth']}\n"
                     f"Local image: {source['id']}\nUncompressed bytes: {source['size']} (limit {args.max_image_bytes})\n"
                     f"Platform: {source['os']}/{source['architecture']} {source['variant']}\n"
                     f"Approval expires: {dt.datetime.fromtimestamp(value['expires_at_epoch'], dt.timezone.utc).isoformat()}\n"
                     f"Plan SHA-256: {digest}\nReview storage/transfer cost and approve this exact hash before image-push.\n")
    return 0


def validate_time(value: dict) -> None:
    created, expires = value["created_at_epoch"], value["expires_at_epoch"]
    require(all(type(v) in (int, float) and math.isfinite(v) for v in (created, expires))
            and 0 < expires - created <= 86400 and created <= time.time() + 300 and time.time() < expires,
            "The image approval expired or has invalid timestamps; re-plan.")


def verify_remote(binary: dict, target: dict, tag: str, digest: str) -> dict:
    base = target["namespace"] + "/" + target["repository_name"]
    result = None
    # Look up both the tag and immutable digest; a successful push alone is not verification.
    for uri in (base + ":" + tag, base + "@" + digest):
        data = oci(binary, target, ["artifacts", "container", "image", "lookup", "--image-uri", uri])
        require(isinstance(data, dict) and ocid(data.get("id"), "containerimage")
                and data.get("repository-id") == target["repository_id"]
                and data.get("repository-name") == target["repository_name"]
                and data.get("compartment-id") == target["compartment_ocid"]
                and data.get("lifecycle-state") == "AVAILABLE" and data.get("digest") == digest,
                "Published image identity could not be verified.")
        if result is not None:
            require(data["id"] == result["id"], "Tag and immutable image lookups disagree.")
        result = data
    return {"id": result["id"], "digest": digest,
            "immutable_uri": target["registry_host"] + "/" + base + "@" + digest}


def verify_manifest(binary: dict, remote: dict, source: dict) -> None:
    data = parse(run(binary, ["manifest", "inspect", "--verbose", remote["immutable_uri"]]))
    require(isinstance(data, dict), "Only a single-platform image manifest can be verified.")
    descriptor = data.get("Descriptor")
    manifest = data.get("SchemaV2Manifest") or data.get("OCIManifest")
    require(isinstance(descriptor, dict) and descriptor.get("digest") == remote["digest"]
            and isinstance(manifest, dict) and manifest.get("schemaVersion") == 2
            and isinstance(manifest.get("config"), dict) and manifest["config"].get("digest") == source["id"],
            "Published manifest does not bind the approved local image configuration.")
    platform = descriptor.get("platform")
    require(isinstance(platform, dict) and platform.get("os") == source["os"]
            and platform.get("architecture") == source["architecture"]
            and platform.get("variant", "") == source["variant"], "Published image platform differs from the approval.")


def push(args, gate: int) -> int:
    require(re.fullmatch(r"[0-9a-f]{64}", args.approve) is not None, "Approval must be the exact plan SHA-256.")
    envelope = parse(read_at(gate, PLAN))
    value = envelope["plan"]
    require(value.get("schema") == "oci-image-plan/1" and sha(canonical(value)) == args.approve
            and envelope.get("plan_sha256") == args.approve, "The image plan does not match the approved hash.")
    require(value["stack_path"] == str(args.dir.absolute()), "Use the original image gate workspace.")
    validate_time(value)
    binaries = {name: fingerprint(name) for name in ("docker", "oci")}
    require(binaries == value["binaries"], "A publication client changed; re-plan.")
    target, receipt_hash = registry_receipt(Path(value["source_receipt"]["path"]), value["target"]["repository_id"])
    require(receipt_hash == value["source_receipt"]["sha256"], "The registry apply receipt changed; re-plan.")
    require(verify_registry(binaries["oci"], target) == value["target"], "Registry identity changed; re-plan.")
    target = value["target"]
    source = image(binaries["docker"], value["source_image"]["id"])
    require(source == value["source_image"] and source["size"] <= value["max_image_bytes"], "Local image changed; re-plan.")
    require(TAG.fullmatch(value["tag"]) is not None and value["destination"] == destination(target, value["tag"]),
            "The destination does not match the reviewed target.")
    absent(binaries["oci"], target, value["tag"])
    receipt = {"schema": "oci-image-push-receipt/1", "status": "attempted", "plan_sha256": args.approve,
               "target": target, "source_image": source, "destination": value["destination"],
               "started_at": timestamp(), "write_may_have_occurred": False}
    with private_directory(gate, "image-receipts") as receipts:
        name = args.approve + ".json"
        write_at(receipts, name, receipt, exclusive=True)
        os.unlink(PLAN, dir_fd=gate)  # one approval permits one attempt, including failed attempts
        os.fsync(gate)
        stage = "local-tag"
        try:
            run(binaries["docker"], ["image", "tag", source["id"], value["destination"]])
            require(image(binaries["docker"], value["destination"]) == source, "Local destination tag changed.")
            stage = "final-check"
            validate_time(value)
            require(all(fingerprint(n) == binaries[n] for n in binaries), "A publication client changed.")
            require(verify_registry(binaries["oci"], target) == target, "Registry identity changed.")
            absent(binaries["oci"], target, value["tag"])
            require(image(binaries["docker"], value["destination"]) == source, "Local destination tag changed.")
            validate_time(value)
            stage = "push"
            receipt["write_may_have_occurred"] = True
            write_at(receipts, name, receipt)
            validate_time(value)  # final reads or durable receipt writes may cross expiry
            output = run(binaries["docker"], ["image", "push", value["destination"]], timeout=600)
            stage = "remote-verification"
            matches = re.findall(rb"(?:^|[\r\n])" + re.escape(value["tag"].encode())
                                 + rb": digest: (sha256:[0-9a-f]{64}) size: [0-9]+(?:[\r\n]|$)", output)
            require(len(set(matches)) == 1, "Push completed but its immutable digest could not be confirmed.")
            receipt["remote_image"] = verify_remote(binaries["oci"], target, value["tag"], matches[0].decode())
            verify_manifest(binaries["docker"], receipt["remote_image"], source)
            receipt.update(status="verified", finished_at=timestamp())
            write_at(receipts, name, receipt)
        except (ImageGateError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            receipt.update(status="unverified" if receipt["write_may_have_occurred"] else "failed",
                           failure_stage=stage, finished_at=timestamp())
            try:
                write_at(receipts, name, receipt)
            except (ImageGateError, OSError, ValueError):
                raise ImageGateError("Attempt may have written remote data; receipt update failed. Inspect privately; do not retry.", 5) from None
            raise ImageGateError("Publication attempt did not verify. Approval is consumed; inspect its private receipt before re-planning.",
                                 5 if receipt["write_may_have_occurred"] else 1) from None
    sys.stdout.write(f"Verified image: {receipt['remote_image']['immutable_uri']}\n"
                     f"Private receipt: .gate/image-receipts/{name}\n")
    return 0


def dispatch(args) -> int:
    try:
        with workspace(args.dir) as gate:
            return plan(args, gate) if args.command == "image-plan" else push(args, gate)
    except ImageGateError as exc:
        sys.stderr.write(f"image gate: {exc}\n")
        return exc.code
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, subprocess.SubprocessError):
        sys.stderr.write("image gate: invalid or unavailable private input/client response; no raw output is disclosed.\n")
        return 2
