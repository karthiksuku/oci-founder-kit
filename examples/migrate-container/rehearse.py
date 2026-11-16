#!/usr/bin/env python3
"""Run bounded HTTP checks against two owned loopback catalogue servers.

This executes only the reviewed example. No dependency installation, container
build, image upload, credentials, OCI APIs or changes to an existing app.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent


def helper(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = helper("migration_catalogue", ROOT / "server.py")
migration = helper("migration_runner", ROOT.parents[1] / "scripts/migration.py")


@contextmanager
def serve(handler=app.Handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield "http://127.0.0.1:" + str(server.server_port)
        finally:
            server.shutdown()
            thread.join(timeout=3)


def contract(source, target):
    now = datetime.now(timezone.utc)
    checks = [
        {"id": "health", "path": "/healthz", "method": "GET", "status": 200,
         "body": {"mode": "json", "pointers": ["/status"], "expected": {"/status": "ok"}}},
        {"id": "catalogue", "path": "/catalogue", "method": "GET", "status": 200,
         "body": {"mode": "sha256", "expected_sha256": hashlib.sha256(app.PAGE).hexdigest()}},
        {"id": "filtered-items", "path": "/api/items?category=work", "method": "GET", "status": 200,
         "repeat": 2, "headers": {"cache-control": {"equals": "no-store"}},
         "body": {"mode": "json", "pointers": ["/items"], "expected": {"/items": [app.ITEMS[0]]}}},
        {"id": "invalid-category", "path": "/api/items?category=other", "method": "GET", "status": 400,
         "body": {"mode": "json", "pointers": ["/error"]}},
        {"id": "redirect", "path": "/start", "method": "GET", "status": 307,
         "location": "/catalogue", "body": {"mode": "none"}},
        {"id": "anonymous-denied", "path": "/private", "method": "GET", "status": 401,
         "body": {"mode": "json", "pointers": ["/error"]}},
        {"id": "head", "path": "/healthz", "method": "HEAD", "status": 200, "body": {"mode": "none"}},
        {"id": "stream", "path": "/stream", "method": "GET", "status": 200,
         "headers": {"content-type": {"equals": "text/event-stream"}, "cache-control": {"equals": "no-store"}},
         "streaming": {"first_byte_ms_max": 2000, "span_ms_min": 80, "completion_ms_max": 4000},
         "body": {"mode": "sha256"}},
    ]
    # The local packaging candidate has no image: all-zero digest is an explicit
    # synthetic selection. It must never be used as a deployed-image receipt.
    return {"schema": migration.SCHEMA, "environment": "rehearsal", "transport": "local-loopback",
            "created_at_utc": now.isoformat(), "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
            "source": {"origin": source, "revision_sha256": hashlib.sha256((ROOT / "server.py").read_bytes()).hexdigest()},
            "target": {"origin": target, "image_digest": "sha256:" + "0" * 64},
            "retained_services": {"database": "not-used", "authentication": "not-used", "storage": "not-used"},
            "jobs": {"inventory": "unknown", "owner": "unknown", "source_enabled": None, "target_enabled": None, "evidence_sha256": None},
            "rollback": {"source_preserved": None, "restore_traffic_reviewed": None, "evidence_sha256": None},
            "checks": checks}


class WrongBody(app.Handler):
    def reply(self, status, body=b"", content_type="application/json", *, location=None):
        if self.path.startswith("/api/items?category=work"):
            body = b'{"items":[]}'
        super().reply(status, body, content_type, location=location)


class WrongCache(app.Handler):
    def send_header(self, key, value):
        super().send_header(key, "public, max-age=3600" if key.lower() == "cache-control" else value)


def run():
    before = (ROOT / "server.py").read_bytes()
    results = {}
    with serve() as source:
        for name, handler in (("baseline", app.Handler), ("changed-body", WrongBody), ("changed-cache", WrongCache)):
            with serve(handler) as target:
                result = migration.verify(contract(source, target))
                results[name] = result["status"]
    preserved = before == (ROOT / "server.py").read_bytes()
    passed = results == {"baseline": "passed", "changed-body": "failed", "changed-cache": "failed"} and preserved
    return {"schema": "oci-container-example-rehearsal/1", "status": "passed" if passed else "failed",
            "scope": "local-python-http-not-container-or-oci", "checks": results, "source_preserved": preserved,
            "cloud_calls": False, "browser_workflows_verified": False}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
