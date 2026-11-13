#!/usr/bin/env python3
"""Start a loopback-only Taskboard preview; stop retains its database and settings.

Uses a local Docker daemon and Compose. No OCI credentials or cloud operations.
Private development settings must stay with the persistent volume they unlock.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parent
LIMIT = 2 * 1024 * 1024


class PreviewError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise PreviewError(message)


def regular(fd):
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
            and not info.st_mode & 0o077, "Preview settings must be owned regular private files (0600), without links.")


@contextlib.contextmanager
def private_settings(create):
    folder = BASE / ".local-preview"
    created = False
    try:
        if create:
            try:
                folder.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                pass
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        yield None, False
        return
    try:
        info = os.fstat(fd)
        require(info.st_uid == os.getuid() and not info.st_mode & 0o077, "Preview directory must be owned and private (0700).")
        lock = os.open("lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
        try:
            regular(lock)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PreviewError("Another local preview command is running.") from None
            yield fd, created
        finally:
            os.close(lock)
    finally:
        os.close(fd)


def write_private(folder, name, content):
    try:
        existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    except FileNotFoundError:
        pass
    else:
        try:
            regular(existing)
        finally:
            os.close(existing)
    temporary = ".writing-" + secrets.token_hex(12)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, name, src_dir_fd=folder, dst_dir_fd=folder)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=folder)


def subnet(value):
    if value is None:
        return None
    try:
        network = ipaddress.IPv4Network(value, strict=True)
    except (ValueError, TypeError):
        raise PreviewError("Use an unused private IPv4 subnet with prefix /24 through /28.") from None
    require(24 <= network.prefixlen <= 28 and any(network.subnet_of(ipaddress.IPv4Network(block))
            for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")),
            "Use an unused RFC1918 subnet with prefix /24 through /28.")
    return str(network)


def settings(folder, created, port, network):
    if created:
        value = {"schema": "oci-local-preview/1", "project": "ocifk-preview-" + secrets.token_hex(6),
                 "password": secrets.token_hex(32), "port": 8080, "subnet": None}
    else:
        try:
            fd = os.open("settings.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        except FileNotFoundError:
            raise PreviewError("Existing preview settings are missing. Restore them; do not regenerate credentials for retained data.") from None
        with os.fdopen(fd, "rb") as handle:
            regular(handle.fileno())
            raw = handle.read(4097)
        require(len(raw) <= 4096, "Preview settings are oversized.")
        value = json.loads(raw)
    require(isinstance(value, dict) and set(value) == {"schema", "project", "password", "port", "subnet"}
            and value["schema"] == "oci-local-preview/1"
            and isinstance(value["project"], str) and re.fullmatch(r"ocifk-preview-[0-9a-f]{12}", value["project"])
            and isinstance(value["password"], str) and re.fullmatch(r"[0-9a-f]{64}", value["password"]),
            "Private preview settings are invalid; restore the original settings.")
    if port is not None:
        value["port"] = port
    if network is not None:
        value["subnet"] = network
    require(type(value["port"]) is int and 1024 <= value["port"] <= 65535, "Choose a local port from 1024 to 65535.")
    value["subnet"] = subnet(value["subnet"])
    if created or port is not None or network is not None:
        write_private(folder, "settings.json", (json.dumps(value, sort_keys=True) + "\n").encode())
    return value


def clean_environment():
    # An explicit file/project and cleared Compose overrides keep this operation
    # scoped to the preview. Docker's existing local context/auth remain usable.
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("COMPOSE_", "PREVIEW_", "BUILDX_", "BUILDKIT_", "BAKE_"))
            and key not in {"DOCKER_BUILDKIT", "DOCKER_DEFAULT_PLATFORM", "EXPERIMENTAL_BUILDKIT_SOURCE_POLICY"}}


def call(argv, environment, private, timeout=60):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            result = subprocess.run(argv, env=environment, cwd=BASE, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise PreviewError("Local Docker operation timed out. Run status; stop retains the database.") from None
        out.seek(0); err.seek(0)
        stdout, stderr = out.read(LIMIT + 1), err.read(LIMIT + 1)
    require(len(stdout) <= LIMIT and len(stderr) <= LIMIT, "Local client output was too large; inspect the Docker operation privately.")
    if result.returncode:
        if private is not None:
            write_private(private, "last-error.log", stdout + b"\n" + stderr)
        if b"address pools" in stderr or b"Pool overlaps" in stderr:
            raise PreviewError("Docker has no available subnet. Choose an unused private subnet with start --subnet; see LOCAL.md.")
        raise PreviewError("Local Docker operation failed. Check Docker/Compose; private details are in .local-preview/last-error.log when initialized.")
    return stdout.decode("utf-8", errors="strict")


def prerequisites(binary, environment):
    # Docker's explicit context environment takes precedence over DOCKER_HOST.
    # Capture the effective endpoint once, then pin every subsequent invocation.
    if environment.get("DOCKER_HOST") and not environment.get("DOCKER_CONTEXT"):
        endpoint = environment["DOCKER_HOST"]
    else:
        endpoint = json.loads(call([binary, "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"], environment, None))
    require(isinstance(endpoint, str) and endpoint.startswith("unix://"), "Local preview requires a local Unix Docker endpoint.")
    environment.pop("DOCKER_CONTEXT", None)
    environment.pop("DOCKER_HOST", None)
    pinned = [binary, "--host", endpoint]
    version = json.loads(call([*pinned, "info", "--format", "{{json .ServerVersion}}"], environment, None))
    require(isinstance(version, str) and re.match(r"^\d+\.", version) and int(version.split(".")[0]) >= 28,
            "Use Docker Engine 28+ (or current Docker Desktop) for the documented loopback isolation.")
    help_text = call([*pinned, "compose", "up", "--help"], environment, None)
    require("--wait" in help_text and "--wait-timeout" in help_text, "Update Docker Compose to a version supporting up --wait and --wait-timeout.")
    build_help = call([*pinned, "compose", "build", "--help"], environment, None)
    require("--builder" in build_help, "Update Docker Compose to a version supporting build --builder.")
    return pinned


def validate_compose(data, value):
    services = data.get("services")
    require(isinstance(services, dict) and set(services) == {"app", "db"}, "Preview must contain only its app and database.")
    app, db = services["app"], services["db"]
    ports = app.get("ports", [])
    require(len(ports) == 1 and ports[0].get("host_ip") == "127.0.0.1"
            and str(ports[0].get("published")) == str(value["port"]) and ports[0].get("target") == 8080
            and not db.get("ports"), "Only the app's selected loopback port may be published; database ports must stay private.")
    env = app.get("environment", {})
    require(env.get("APP_MODE") == "sandbox" and not env.get("OCI_BUCKET") and not env.get("OCI_NAMESPACE"),
            "Local preview requires sandbox mode with OCI attachments disabled.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Build/start preview; preserve existing tasks")
    start.add_argument("--port", type=int, help="Loopback port (initial default 8080)")
    start.add_argument("--subnet", help="Optional unused private /24 through /28 for exhausted Docker pools")
    sub.add_parser("status", help="Show this preview's service state")
    sub.add_parser("stop", help="Remove this preview's containers/network; retain data and settings")
    args = parser.parse_args(argv)
    try:
        require(os.name == "posix" and sys.version_info >= (3, 11), "Use Python 3.11+ on Linux/macOS or WSL2 with local Docker.")
        if args.command != "start" and not (BASE / ".local-preview").exists():
            print("Local preview has not been initialized.")
            return 0
        if args.command == "start":
            require(args.port is None or 1024 <= args.port <= 65535, "Choose a local port from 1024 to 65535.")
            subnet(args.subnet)
        binary = shutil.which("docker")
        require(binary is not None, "Install Docker and its Compose plugin before starting the preview.")
        environment = clean_environment()
        pinned = prerequisites(binary, environment)
        with private_settings(args.command == "start") as (private, created):
            require(private is not None, "Local preview settings are unavailable.")
            value = settings(private, created, getattr(args, "port", None), getattr(args, "subnet", None))
            environment.update(PREVIEW_PORT=str(value["port"]), PREVIEW_PROJECT=value["project"], PREVIEW_DB_PASSWORD=value["password"])
            with tempfile.TemporaryDirectory(prefix="ocifk-preview-") as temporary:
                override = Path(temporary) / "network.json"
                network = {"ipam": {"config": [{"subnet": value["subnet"]}]}} if value["subnet"] else {}
                override.write_text(json.dumps({"networks": {"default": network}}))
                command = [*pinned, "compose", "--project-directory", str(BASE), "--project-name", value["project"],
                           "--env-file", os.devnull, "--file", str(BASE / "compose.local.yaml"), "--file", str(override)]
                validate_compose(json.loads(call([*command, "config", "--format", "json"], environment, private)), value)
                if args.command == "start":
                    print("Building and starting the local app and database; first use may download public images.", flush=True)
                    call([*command, "build", "--builder", "default"], environment, private, timeout=900)
                    call([*command, "up", "--no-build", "--wait", "--wait-timeout", "120"], environment, private, timeout=180)
                    address = call([*command, "port", "app", "8080"], environment, private).strip()
                    require(address == f"127.0.0.1:{value['port']}", "Could not confirm loopback publication. Run stop and inspect privately.")
                    print(f"Taskboard: http://{address}\nLocal sandbox: no sign-in; OCI attachments are unavailable.\n"
                          "Tasks persist when stopped. Run local_preview.py stop when finished.")
                elif args.command == "stop":
                    call([*command, "down", "--timeout", "20"], environment, private, timeout=90)
                    print("Preview containers and network stopped; private settings retained.\n"
                          "No database-volume deletion was requested. Volume presence has not been checked.")
                else:
                    raw = call([*command, "ps", "--all", "--format", "json"], environment, private)
                    rows = json.loads(raw) if raw.strip().startswith("[") else [json.loads(line) for line in raw.splitlines() if line.strip()]
                    require(isinstance(rows, list), "Could not read preview service status.")
                    for row in rows:
                        require(row.get("Service") in {"app", "db"}, "Unexpected service in preview status.")
                        print(f"{row['Service']}: {row.get('State', 'unknown')} / {row.get('Health') or 'no health result'}")
                    if not rows:
                        print("No preview containers found; private settings retained. Database volume has not been checked.")
        return 0
    except (PreviewError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, PreviewError) else "Invalid private settings or unavailable local client; raw values are withheld."
        print("local preview: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
