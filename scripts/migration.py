#!/usr/bin/env python3
"""Review hosting compatibility and compare selected read-only HTTP behavior.

No app code, shell commands, cloud APIs, redirects or traffic changes are run.
Private contracts select exact origins; reports never include bodies or cookies.
Python 3.11+, Linux/macOS/WSL2. Local HTTP requires explicit loopback scope.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import ssl
import stat
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

SCHEMA = "oci-hosting-migration/1"
REPORT_SCHEMA = "oci-migration-parity/1"
MAX_INPUT = 65536
MAX_RESPONSE = 262144
MAX_CHECKS = 16
MAX_REQUESTS = 64
HASH = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
COOKIE = re.compile(r"[!#$%&'*+.^_`|~A-Za-z0-9-]+=[!#-:<-\[\]-~]{1,4096}(?:; [!#$%&'*+.^_`|~A-Za-z0-9-]+=[!#-:<-\[\]-~]{1,4096})*")
FEATURES = {"hosting-config", "server-routes", "routing", "scheduled-jobs", "blob-storage",
            "kv-store", "postgres", "edge-config", "edge-runtime", "platform-functions",
            "analytics", "external-backend", "middleware", "image-optimization",
            "cache-revalidation", "deployment-env", "next-runtime"}
OUTCOMES = {"supported", "adaptation-required", "unsupported", "unknown"}
HEADERS = {"content-type", "cache-control", "vary", "x-content-type-options",
           "strict-transport-security", "content-encoding"}
NOT_COVERED = ["browser-hydration-and-navigation", "hosted-sign-in-and-callback",
               "uploads-and-other-writes", "data-migration", "cloud-iam-and-network-isolation",
               "deployed-image-identity", "restart-and-isolated-restore", "traffic-switch-and-rollback",
               "scheduler-runtime-ownership", "shared-cache-invalidation", "production-load"]


class MigrationError(ValueError):
    """Sanitized failures only; never add response or private input excerpts."""


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise MigrationError("Duplicate JSON fields are refused.")
        value[key] = item
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise MigrationError("Missing or unsupported contract fields.")


def parent_directory(path):
    """Open every directory without following links, including during renames."""
    if os.name != "posix" or ".." in path.parts:
        raise MigrationError("Private files require a supported filesystem and no parent traversal.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:-1]:
            following = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except Exception:
        os.close(fd)
        raise


def private_read(path, *, outside_git=False):
    path = Path(path).expanduser().absolute()
    if os.name != "posix" or ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise MigrationError("Private input requires a supported filesystem and no symlinks.")
    if outside_git and any((p / ".git").exists() for p in path.parents):
        raise MigrationError("Keep session files outside Git repositories.")
    directory = None
    try:
        directory = parent_directory(path)
        with os.fdopen(os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory), "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_mode & 0o077 or before.st_nlink != 1):
                raise MigrationError("Private input must be an owned regular file with mode 600 or 400.")
            raw = stream.read(MAX_INPUT + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_INPUT or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise MigrationError("Private input exceeded limits or changed during inspection.")
        return raw
    except OSError:
        raise MigrationError("Private input is unavailable.") from None
    finally:
        if directory is not None:
            os.close(directory)


def load_private(path, *, outside_git=False):
    try:
        return json.loads(private_read(path, outside_git=outside_git), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise MigrationError("Private JSON input is unavailable or invalid.") from None


def origin(value, transport="https"):
    try:
        parsed = urlsplit(value)
        if (not isinstance(value, str) or len(value) > 512 or not value.isascii()
                or any(c.isspace() for c in value) or any(c in value for c in "\\?#")
                or parsed.username or parsed.password or not parsed.hostname or parsed.path
                or parsed.netloc.endswith(":") or parsed.hostname.endswith(".")
                or not 1 <= (parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)) <= 65535):
            raise ValueError
        if transport == "local-loopback":
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}:
                raise ValueError
        elif transport != "https" or parsed.scheme != "https" or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.hostname):
            raise ValueError
        if value != parsed.scheme + "://" + parsed.netloc.lower():
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise MigrationError("Select exact lowercase HTTPS origins, or explicit numeric loopback HTTP origins.") from None


def request_path(value):
    if (not isinstance(value, str) or len(value) > 2048 or not value.startswith("/")
            or value.startswith("//") or not value.isascii() or "#" in value
            or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in value + unquote(value))):
        raise MigrationError("Checks require bounded origin-relative request paths.")
    return value


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise MigrationError("Use explicit UTC contract timestamps.") from None


def optional_hash(value):
    return value is None or isinstance(value, str) and HASH.fullmatch(value)


def validate_contract(value, *, now=None):
    fields(value, {"schema", "environment", "created_at_utc", "expires_at_utc", "transport", "source", "target",
                   "retained_services", "jobs", "rollback", "checks"})
    if value["schema"] != SCHEMA or not isinstance(value["environment"], str) or not NAME.fullmatch(value["environment"]):
        raise MigrationError("Unsupported schema or environment selection.")
    created, expires = timestamp(value["created_at_utc"]), timestamp(value["expires_at_utc"])
    now = now or datetime.now(timezone.utc)
    if not created <= now < expires or not 0 < (expires - created).total_seconds() <= 86400:
        raise MigrationError("Contract is expired, future-dated or exceeds a 24-hour review window.")
    if value["transport"] not in {"https", "local-loopback"}:
        raise MigrationError("Unsupported transport selection.")
    fields(value["source"], {"origin", "revision_sha256"})
    fields(value["target"], {"origin", "image_digest"})
    for side in ("source", "target"):
        origin(value[side]["origin"], value["transport"])
    if value["source"]["origin"] == value["target"]["origin"]:
        raise MigrationError("Source and target must be distinct origins.")
    if (not isinstance(value["source"]["revision_sha256"], str) or not HASH.fullmatch(value["source"]["revision_sha256"])
            or not isinstance(value["target"]["image_digest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", value["target"]["image_digest"])):
        raise MigrationError("Bind the source revision hash and target image digest.")
    fields(value["retained_services"], {"database", "authentication", "storage"})
    if any(v not in {"retained", "not-used", "unknown"} for v in value["retained_services"].values()):
        raise MigrationError("Hosting-first service choices must be retained, not-used or unknown.")
    jobs = value["jobs"]
    fields(jobs, {"inventory", "owner", "source_enabled", "target_enabled", "evidence_sha256"})
    if (jobs["inventory"] not in {"attested", "unknown"} or jobs["owner"] not in {"source", "target", "none", "unknown"}
            or any(v is not None and type(v) is not bool for v in (jobs["source_enabled"], jobs["target_enabled"]))
            or not optional_hash(jobs["evidence_sha256"])):
        raise MigrationError("Invalid scheduler ownership attestation.")
    rollback = value["rollback"]
    fields(rollback, {"source_preserved", "restore_traffic_reviewed", "evidence_sha256"})
    if (any(v is not None and type(v) is not bool for v in (rollback["source_preserved"], rollback["restore_traffic_reviewed"]))
            or not optional_hash(rollback["evidence_sha256"])):
        raise MigrationError("Invalid rollback attestation.")
    checks = value["checks"]
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
        raise MigrationError("Select one to sixteen bounded read-only checks.")
    names = set()
    for check in checks:
        fields(check, {"id", "method", "path", "status", "body"}, {"session", "headers", "location", "cookies", "streaming", "repeat"})
        name = check["id"]
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in names:
            raise MigrationError("Check identifiers must be unique short lowercase names.")
        names.add(name)
        if (check["method"] not in {"GET", "HEAD"} or type(check["status"]) is not int
                or not 100 <= check["status"] <= 599 or check.get("session", "anonymous") not in {"anonymous", "a", "b"}
                or type(check.get("repeat", 1)) is not int or check.get("repeat", 1) not in {1, 2}):
            raise MigrationError("Only bounded GET/HEAD checks with fixed status and optional test sessions are supported.")
        request_path(check["path"])
        headers = check.get("headers", {})
        if not isinstance(headers, dict) or set(headers) - HEADERS:
            raise MigrationError("Unsupported response header assertion.")
        for assertion in headers.values():
            if not isinstance(assertion, dict) or len(assertion) != 1 or not set(assertion) <= {"equals", "contains"}:
                raise MigrationError("Header assertions use equals or contains.")
            expected = next(iter(assertion.values()))
            if not isinstance(expected, str) or not 1 <= len(expected) <= 256 or any(ord(c) < 32 for c in expected):
                raise MigrationError("Invalid response header assertion.")
        if "location" in check:
            request_path(check["location"])
        if "cookies" in check:
            cookies = check["cookies"]
            fields(cookies, {"present", "secure", "httponly", "samesite"})
            if (any(type(cookies[k]) is not bool for k in ("present", "secure", "httponly"))
                    or cookies["samesite"] not in {"Lax", "Strict", "None"}):
                raise MigrationError("Invalid cookie-flag assertion.")
        body = check["body"]
        fields(body, {"mode"}, {"pointers", "expected", "expected_sha256"})
        mode = body["mode"]
        if mode == "none":
            fields(body, {"mode"})
        elif mode == "sha256":
            fields(body, {"mode"}, {"expected_sha256"})
            if "expected_sha256" in body and not (isinstance(body["expected_sha256"], str) and HASH.fullmatch(body["expected_sha256"])):
                raise MigrationError("Invalid expected response hash.")
        elif mode == "json":
            fields(body, {"mode", "pointers"}, {"expected"})
            pointers = body["pointers"]
            if (not isinstance(pointers, list) or not 1 <= len(pointers) <= 16
                    or any(not isinstance(p, str) or not re.fullmatch(r"(?:/[A-Za-z0-9_~-]{1,64}){1,8}", p) for p in pointers)
                    or len(set(pointers)) != len(pointers)):
                raise MigrationError("JSON checks require bounded explicit field pointers.")
            expected = body.get("expected", {})
            if not isinstance(expected, dict) or set(expected) - set(pointers) or len(canonical(expected)) > 8192:
                raise MigrationError("Expected JSON must match selected pointers and size bounds.")
        else:
            raise MigrationError("Unsupported body assertion mode.")
        if check["method"] == "HEAD" and mode != "none":
            raise MigrationError("HEAD checks cannot assert response bodies.")
        if "streaming" in check:
            stream = check["streaming"]
            fields(stream, {"first_byte_ms_max", "span_ms_min", "completion_ms_max"})
            if (check["method"] != "GET" or any(type(v) is not int or not 1 <= v <= 9000 for v in stream.values())
                    or stream["span_ms_min"] >= stream["completion_ms_max"]):
                raise MigrationError("Streaming requires bounded first-byte, span and completion assertions.")
    if len(canonical(value)) > MAX_INPUT:
        raise MigrationError("Contract exceeded its size limit.")
    return value


def validate_sessions(data, contract):
    fields(data, {"schema", "source", "target"})
    if data["schema"] != "oci-migration-sessions/1" or contract["transport"] != "https":
        raise MigrationError("Sessions require exact HTTPS origins.")
    for side in ("source", "target"):
        item = data[side]
        fields(item, {"origin", "users"})
        if item["origin"] != contract[side]["origin"] or not isinstance(item["users"], dict) or not set(item["users"]) <= {"a", "b"}:
            raise MigrationError("Sessions must match the exact reviewed source and target origins.")
        users = item["users"]
        if any(not isinstance(v, str) or len(v) > 8192 or not COOKIE.fullmatch(v) for v in users.values()):
            raise MigrationError("Invalid private test-session cookie.")
        if len(set(users.values())) != len(users):
            raise MigrationError("Distinct user checks require distinct sessions.")
        needed = {c.get("session", "anonymous") for c in contract["checks"]} - {"anonymous"}
        if set(users) != needed:
            raise MigrationError("Provide exactly the sessions selected by the checks.")
    return data


class Response:
    def __init__(self, status, headers, body, first_byte_ms=0, duration_ms=0):
        self.status, self.headers, self.body = status, headers, body
        self.first_byte_ms, self.duration_ms = first_byte_ms, duration_ms


class HTTPClient:
    """Pinned origin, TLS verification, bounded DNS/bytes/time, no proxies or redirects."""
    def __init__(self, selected_origin, *, transport="https", ca_file=None, deadline=None):
        target = urlsplit(origin(selected_origin, transport))
        self.host, self.port = target.hostname, target.port or (443 if transport == "https" else 80)
        self.tls = transport == "https"
        self.context = ssl.create_default_context() if self.tls else None
        if ca_file is not None:
            if not self.tls:
                raise MigrationError("A CA file requires HTTPS.")
            self.context.load_verify_locations(cadata=private_read(ca_file).decode("ascii"))
        self.deadline = deadline or time.monotonic() + 90
        self.calls = 0
        self.addresses = None

    def connect(self, address, timeout, source_address=None):
        if address != (self.host, self.port) or source_address is not None:
            raise MigrationError("Unexpected connection target.")
        if self.addresses is None:
            resolved = queue.Queue(maxsize=1)
            def lookup():
                try:
                    resolved.put(socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM))
                except OSError:
                    resolved.put([])
            threading.Thread(target=lookup, daemon=True).start()
            try:
                self.addresses = resolved.get(timeout=max(.01, min(5, self.deadline - time.monotonic())))[:4]
            except queue.Empty:
                raise MigrationError("Name resolution exceeded its deadline.") from None
        for family, kind, protocol, _, endpoint in self.addresses:
            if time.monotonic() >= self.deadline:
                break
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(min(timeout, self.deadline - time.monotonic()))
                sock.connect(endpoint)
                return sock
            except (OSError, ValueError):
                sock.close()
        raise MigrationError("Selected origin is unavailable.")

    def request(self, method, path, cookie=None):
        if method not in {"GET", "HEAD"} or self.calls >= MAX_REQUESTS or time.monotonic() >= self.deadline:
            raise MigrationError("Request bounds were reached.")
        request_path(path)
        if cookie is not None and (not self.tls or not COOKIE.fullmatch(cookie)):
            raise MigrationError("Invalid private session request.")
        self.calls += 1
        started = time.monotonic()
        timeout = min(5, self.deadline - started)
        if self.tls:
            conn = http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=self.context)
        else:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        conn._create_connection = self.connect
        timer = None
        try:
            conn.connect()
            sock = conn.sock
            def expire():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            timer = threading.Timer(max(.01, min(10, self.deadline - time.monotonic())), expire)
            timer.daemon = True
            timer.start()
            headers = {"Accept-Encoding": "identity", "User-Agent": "oci-founder-kit-migration-check"}
            if cookie is not None:
                headers["Cookie"] = cookie
            conn.request(method, path, headers=headers)
            response = conn.getresponse()
            body, first = bytearray(), None
            while True:
                if time.monotonic() >= self.deadline:
                    raise MigrationError("Request deadline reached.")
                chunk = response.read1(min(8192, MAX_RESPONSE + 1 - len(body)))
                if not chunk:
                    break
                if first is None:
                    first = (time.monotonic() - started) * 1000
                body.extend(chunk)
                if len(body) > MAX_RESPONSE:
                    raise MigrationError("Response exceeded its size limit.")
            duration = (time.monotonic() - started) * 1000
            return Response(response.status, response.getheaders(), bytes(body), first if first is not None else duration, duration)
        except (OSError, http.client.HTTPException, ValueError):
            raise MigrationError("Selected request was unavailable or exceeded bounds.") from None
        finally:
            if timer:
                timer.cancel()
            conn.close()


def projection(check, response, selected_origin):
    """Validate fixed predicates; projected values stay in memory, never in reports."""
    if response.status != check["status"]:
        raise MigrationError("Response assertion failed.")
    headers = {}
    for name, value in response.headers:
        headers.setdefault(name.lower(), []).append(value)
    result = {"status": response.status}
    for name, assertion in check.get("headers", {}).items():
        values = headers.get(name, [])
        if len(values) != 1:
            raise MigrationError("Response assertion failed.")
        actual = values[0]
        if ("equals" in assertion and actual != assertion["equals"]
                or "contains" in assertion and assertion["contains"] not in actual):
            raise MigrationError("Response assertion failed.")
        # Only selected predicates are compared; volatile header values stay private.
        result[name] = True
    if "location" in check:
        values = headers.get("location", [])
        if len(values) != 1 or values[0] not in {check["location"], selected_origin + check["location"]}:
            raise MigrationError("Response assertion failed.")
        result["location"] = True
    if "cookies" in check:
        required, raw = check["cookies"], headers.get("set-cookie", [])
        if bool(raw) != required["present"]:
            raise MigrationError("Response assertion failed.")
        for text in raw:
            cookies = SimpleCookie()
            try:
                cookies.load(text)
            except Exception:
                raise MigrationError("Response assertion failed.") from None
            if not cookies or any(bool(c["secure"]) != required["secure"] or bool(c["httponly"]) != required["httponly"]
                                  or c["samesite"].lower() != required["samesite"].lower() for c in cookies.values()):
                raise MigrationError("Response assertion failed.")
        result["cookie-flags"] = True
    mode = check["body"]["mode"]
    if mode == "sha256":
        result["body"] = digest(response.body)
        if "expected_sha256" in check["body"] and result["body"] != check["body"]["expected_sha256"]:
            raise MigrationError("Response assertion failed.")
    elif mode == "json":
        try:
            data = json.loads(response.body, object_pairs_hook=unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            result["body"] = {}
            for pointer in check["body"]["pointers"]:
                current = data
                for part in pointer.split("/")[1:]:
                    part = part.replace("~1", "/").replace("~0", "~")
                    current = current[int(part)] if isinstance(current, list) and part.isdigit() else current[part]
                result["body"][pointer] = current
            for pointer, expected in check["body"].get("expected", {}).items():
                if canonical(result["body"][pointer]) != canonical(expected):
                    raise ValueError
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError, RecursionError):
            raise MigrationError("Response assertion failed.") from None
    if "streaming" in check:
        limits = check["streaming"]
        if (not response.body or response.first_byte_ms > limits["first_byte_ms_max"]
                or response.duration_ms > limits["completion_ms_max"]
                or response.duration_ms - response.first_byte_ms < limits["span_ms_min"]):
            raise MigrationError("Response assertion failed.")
        result["streaming-observed"] = True
    return canonical(result)


def bindings(contract):
    return {"contract_sha256": digest(canonical(contract)), "environment": contract["environment"],
            "source_origin_sha256": digest(contract["source"]["origin"].encode()),
            "target_origin_sha256": digest(contract["target"]["origin"].encode()),
            "source_revision_sha256": contract["source"]["revision_sha256"],
            "target_image_digest": contract["target"]["image_digest"]}


def verify(contract, *, sessions=None, ca_file=None, client_factory=None):
    validate_contract(contract)
    if sessions is not None:
        validate_sessions(sessions, contract)
    if any(c.get("session", "anonymous") != "anonymous" for c in contract["checks"]) and sessions is None:
        raise MigrationError("Selected authenticated checks require a private session file.")
    deadline = time.monotonic() + 90
    clients = {side: client_factory(side) if client_factory else HTTPClient(contract[side]["origin"],
               transport=contract["transport"], ca_file=ca_file, deadline=deadline) for side in ("source", "target")}
    report = {"schema": REPORT_SCHEMA, **bindings(contract), "run_id": secrets.token_hex(12),
              "runner_sha256": digest(Path(__file__).read_bytes()), "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "local-loopback-http" if contract["transport"] == "local-loopback" else "selected-https-origins",
              "read_only": True, "image_identity_verified": False, "production_readiness_established": False,
              "status": "unknown", "checks": [], "not_covered": list(NOT_COVERED)}
    interrupted = False
    try:
        for check in contract["checks"]:
            row = {"id": check["id"], "source": "unknown", "target": "unknown", "parity": "unknown"}
            report["checks"].append(row)
            projected = {}
            for side in ("source", "target"):
                try:
                    values = []
                    for _ in range(check.get("repeat", 1)):
                        session = check.get("session", "anonymous")
                        cookie = None if session == "anonymous" else sessions[side]["users"][session]
                        response = clients[side].request(check["method"], check["path"], cookie)
                        try:
                            values.append(projection(check, response, contract[side]["origin"]))
                        except MigrationError:
                            row[side] = "failed"
                            break
                    else:
                        row[side] = "passed" if all(v == values[0] for v in values) else "failed"
                        if row[side] == "passed":
                            projected[side] = values[0]
                except (MigrationError, OSError):
                    row[side] = "unknown"
            if "failed" in (row["source"], row["target"]):
                row["parity"] = "failed"
            elif len(projected) == 2:
                row["parity"] = "passed" if projected["source"] == projected["target"] else "failed"
    except KeyboardInterrupt:
        interrupted = True
    statuses = [row["parity"] for row in report["checks"]]
    expired = datetime.now(timezone.utc) >= timestamp(contract["expires_at_utc"])
    report["status"] = ("unknown" if interrupted or expired else "failed" if "failed" in statuses else
                        "passed" if len(statuses) == len(contract["checks"]) and all(s == "passed" for s in statuses) else "unknown")
    report["interrupted"] = interrupted
    report["contract_expired_during_run"] = expired
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def assess(scan, reviews=None):
    """Attach explicit owner reviews to a bounded scan; defaults never imply portability."""
    if (not isinstance(scan, dict) or scan.get("schema") != "oci-web-migration/1"
            or not isinstance(scan.get("findings"), list) or len(scan["findings"]) > 3000
            or not isinstance(scan.get("coverage"), dict)
            or scan["coverage"].get("status") not in {"bounded-static-scan", "incomplete"}):
        raise MigrationError("Expected a bounded web migration scan.")
    codes = set()
    for finding in scan["findings"]:
        if not isinstance(finding, dict) or finding.get("code") not in FEATURES:
            raise MigrationError("Unsupported discovered feature.")
        codes.add(finding["code"])
    scan_hash = digest(canonical(scan))
    indexed = {}
    if reviews is not None:
        fields(reviews, {"schema", "scan_sha256", "features"})
        if (reviews["schema"] != "oci-migration-reviews/1" or reviews["scan_sha256"] != scan_hash
                or not isinstance(reviews["features"], list) or len(reviews["features"]) > len(FEATURES)):
            raise MigrationError("Reviews must bind this exact scan.")
        for item in reviews["features"]:
            fields(item, {"feature", "outcome", "evidence_sha256"})
            if (item["feature"] not in codes or item["feature"] in indexed or item["outcome"] not in OUTCOMES
                    or not optional_hash(item["evidence_sha256"])
                    or item["outcome"] != "unknown" and item["evidence_sha256"] is None):
                raise MigrationError("Feature reviews require known features, explicit outcomes and evidence hashes.")
            indexed[item["feature"]] = dict(item)
    outcomes = [indexed.get(code, {"feature": code, "outcome": "unknown", "evidence_sha256": None}) for code in sorted(codes)]
    return {"schema": "oci-migration-compatibility/1", "scan_sha256": scan_hash, "features": outcomes,
            "coverage": scan["coverage"]["status"], "review_basis": "owner-attestation-not-independent-proof",
            "unreviewed_features": sum(f["outcome"] == "unknown" for f in outcomes),
            "portability_established": False, "hosting_first": True,
            "inventory_complete": False, "status": "review-required" if not outcomes or scan["coverage"]["status"] == "incomplete"
            or any(f["outcome"] != "supported" for f in outcomes) else "selected-features-reviewed",
            "not_covered": ["provider-dashboard-settings", "undiscovered-or-dynamic-dependencies", "runtime-behavior",
                            "database-authentication-and-storage-connectivity", "framework-version-support"]}


def job_ownership(jobs):
    """A consistent attestation is not observation of a running scheduler."""
    if jobs["source_enabled"] is True and jobs["target_enabled"] is True:
        return "conflict"
    if jobs["inventory"] != "attested" or jobs["evidence_sha256"] is None:
        return "unknown"
    states = {"source": (True, False), "target": (False, True), "none": (False, False)}
    if jobs["owner"] not in states or None in (jobs["source_enabled"], jobs["target_enabled"]):
        return "unknown"
    return "attested" if (jobs["source_enabled"], jobs["target_enabled"]) == states[jobs["owner"]] else "conflict"


def review(contract, parity_report=None):
    validate_contract(contract)
    parity = "unknown"
    if parity_report is not None:
        if (not isinstance(parity_report, dict) or parity_report.get("schema") != REPORT_SCHEMA
                or any(parity_report.get(key) != val for key, val in bindings(contract).items())
                or parity_report.get("runner_sha256") != digest(Path(__file__).read_bytes())
                or not timestamp(contract["created_at_utc"]) <= timestamp(parity_report.get("started_at_utc"))
                <= timestamp(parity_report.get("finished_at_utc")) <= datetime.now(timezone.utc)
                or parity_report.get("scope") != ("local-loopback-http" if contract["transport"] == "local-loopback" else "selected-https-origins")
                or parity_report.get("read_only") is not True):
            raise MigrationError("Parity evidence is stale or belongs to another contract, environment or runner.")
        parity = parity_report.get("status", "unknown")
        if parity not in {"passed", "failed", "unknown"}:
            raise MigrationError("Invalid parity evidence.")
        expected = [check["id"] for check in contract["checks"]]
        rows = parity_report.get("checks", [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise MigrationError("Invalid parity evidence.")
        if parity == "passed" and ([r.get("id") for r in rows] != expected or parity_report.get("interrupted") is not False
                or parity_report.get("contract_expired_during_run") is not False
                or timestamp(parity_report["finished_at_utc"]) >= timestamp(contract["expires_at_utc"])
                or any(any(r.get(k) != "passed" for k in ("source", "target", "parity")) for r in rows)):
            raise MigrationError("Incomplete parity evidence cannot pass.")
    jobs = job_ownership(contract["jobs"])
    rollback = contract["rollback"]
    retained = all(v != "unknown" for v in contract["retained_services"].values())
    rollback_status = "attested" if all(rollback[k] is True for k in ("source_preserved", "restore_traffic_reviewed")) and rollback["evidence_sha256"] else "unknown"
    return {"schema": "oci-migration-cutover-review/1", **bindings(contract),
            "status": "review-required", "parity": parity, "parity_evidence_authenticated": False,
            "retained_services": dict(contract["retained_services"]), "retained_services_decided": retained,
            "job_ownership": jobs, "job_ownership_basis": "owner-attestation-not-runtime-proof",
            "rollback": rollback_status, "rehearsal_keeps_target_jobs_disabled": contract["jobs"]["target_enabled"] is False,
            "cutover_authorized": False, "rollback_authorized": False, "data_migration_authorized": False,
            "required_operations": ["Review source and target dependency connectivity, TLS, callbacks and latency.",
                                    "Verify hosted browser workflows, image identity and isolated recovery separately.",
                                    "Approve an exact traffic-change plan and a separate rollback plan before execution.",
                                    "Transfer scheduled jobs and workers once; verify the previous owner is disabled.",
                                    "Keep source hosting and external data providers until hosting acceptance.",
                                    "Report overlap costs and retained resources; cleanup requires separate approval."]}


def reserve_output(path):
    path = Path(path).expanduser().absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise MigrationError("Output must be a new private regular file without symlinks.")
    directory = None
    try:
        directory = parent_directory(path)
        return os.fdopen(os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                                dir_fd=directory), "w")
    except OSError:
        raise MigrationError("Output must be a new private file in an existing directory.") from None
    finally:
        if directory is not None:
            os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    assessment = sub.add_parser("assess")
    assessment.add_argument("--scan", required=True, type=Path)
    assessment.add_argument("--reviews", type=Path)
    for command in ("verify", "review"):
        selected = sub.add_parser(command)
        selected.add_argument("--contract", required=True, type=Path)
        selected.add_argument("--environment", required=True)
        if command == "verify":
            selected.add_argument("--source", required=True, help="Confirm the exact source origin.")
            selected.add_argument("--target", required=True, help="Confirm the exact target origin.")
            selected.add_argument("--sessions-file", type=Path)
            selected.add_argument("--ca-file", type=Path)
        else:
            selected.add_argument("--parity", type=Path)
    for selected in (assessment, *[sub.choices[c] for c in ("verify", "review")]):
        selected.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    output = None
    try:
        if args.command == "assess":
            report = assess(load_private(args.scan), load_private(args.reviews) if args.reviews else None)
            output = reserve_output(args.out)
        else:
            contract = validate_contract(load_private(args.contract))
            if args.environment != contract["environment"]:
                raise MigrationError("Explicit environment does not match the contract.")
            if args.command == "verify":
                if args.source != contract["source"]["origin"] or args.target != contract["target"]["origin"]:
                    raise MigrationError("Explicit origins do not match the contract.")
                sessions = load_private(args.sessions_file, outside_git=True) if args.sessions_file else None
                if sessions is not None:
                    validate_sessions(sessions, contract)
                output = reserve_output(args.out)
                report = verify(contract, sessions=sessions, ca_file=args.ca_file)
            else:
                report = review(contract, load_private(args.parity) if args.parity else None)
                output = reserve_output(args.out)
        output.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
        output.close()
        return 0 if args.command != "verify" or report["status"] == "passed" else 1
    except (MigrationError, OSError, ValueError, TypeError, RecursionError):
        if output:
            output.close()
        print("Migration check could not complete: review private inputs, bindings and bounds.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
