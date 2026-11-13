#!/usr/bin/env python3
"""End-to-end smoke test for a deployed Taskboard: health, database, tasks, uploads.

Usage: python3 smoke_test.py http://<load-balancer-ip> [--wait-seconds 600]

Read-and-write against the app only: it creates one task and one small file,
then deletes the task. It never calls OCI APIs directly. Prints one line per
check and exits 0 only when every check passes. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def call(method: str, url: str, body: bytes | None = None, headers: dict | None = None,
         follow: bool = True, timeout: float = 30) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read()


def api(method: str, base: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    status, _, raw = call(method, base + path, body, {"content-type": "application/json"} if body else {})
    return status, (json.loads(raw) if raw else {})


def wait_ready(base: str, seconds: int) -> tuple[bool, str]:
    deadline = time.time() + seconds
    last = "no response"
    while time.time() < deadline:
        try:
            status, _, raw = call("GET", base + "/readyz", timeout=10)
            last = f"{status} {raw[:80]!r}"
            if status == 200:
                return True, last
        except (urllib.error.URLError, OSError) as exc:
            last = str(exc)[:80]
        time.sleep(15)
    return False, last


def run(base: str, wait_seconds: int) -> list[tuple[str, bool, str]]:
    results = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        results.append((name, ok, detail))
        return ok

    ready, detail = wait_ready(base, wait_seconds)
    if not check("readiness (database connected)", ready, detail):
        return results
    status, body = api("GET", base, "/healthz")
    check("liveness", status == 200 and body.get("status") == "ok", str(status))

    title = f"Live proof {time.strftime('%Y-%m-%d %H:%M:%S')}"
    status, task = api("POST", base, "/api/tasks", {"title": title})
    if not check("create task", status == 201 and task.get("title") == title, str(status)):
        return results
    task_id = task["id"]

    content = f"OCI Founder Kit smoke test {time.time()}\n".encode()
    status, upload = api("POST", base, f"/api/tasks/{task_id}/attachments/upload-url",
                         {"filename": "smoke-test.txt", "size": len(content), "contentType": "text/plain"})
    if check("pre-authenticated upload URL", status == 201 and upload.get("uploadUrl", "").startswith("https://"),
             str(status)):
        put_status, _, _ = call("PUT", upload["uploadUrl"], content, {"content-type": "text/plain"})
        check("direct upload to Object Storage", put_status == 200, str(put_status))
        status, attachment = api("POST", base, f"/api/tasks/{task_id}/attachments",
                                 {"objectName": upload["objectName"], "filename": "smoke-test.txt",
                                  "size": len(content)})
        if check("record attachment", status == 201, str(status)):
            redirect, headers, _ = call("GET", f"{base}/api/attachments/{attachment['id']}/download", follow=False)
            location = headers.get("Location") or headers.get("location") or ""
            if check("download redirects to a short-lived URL", redirect == 302 and location.startswith("https://"),
                     str(redirect)):
                got_status, _, got = call("GET", location)
                check("downloaded bytes match", got_status == 200 and hashlib.sha256(got).digest()
                      == hashlib.sha256(content).digest(), str(got_status))

    status, updated = api("PATCH", base, f"/api/tasks/{task_id}", {"done": True})
    check("update task", status == 200 and updated.get("done") is True, str(status))
    status, _ = api("DELETE", base, f"/api/tasks/{task_id}")
    check("delete task", status == 204, str(status))
    status, _ = api("GET", base, f"/api/tasks/{task_id}")
    check("task is gone", status == 404, str(status))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url")
    parser.add_argument("--wait-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    results = run(args.base_url.rstrip("/"), args.wait_seconds)
    for name, ok, detail in results:
        sys.stdout.write(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else "") + "\n")
    passed = sum(1 for _, ok, _ in results if ok)
    sys.stdout.write(f"{passed}/{len(results)} checks passed\n")
    return 0 if results and passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
