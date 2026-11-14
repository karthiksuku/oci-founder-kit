#!/usr/bin/env python3
"""Exercise one HTTP contract against next start and the standalone artifact.

No dependency installation, build, credentials or cloud calls. Both owned servers
bind loopback and stop afterward. Run npm ci and npm run build first.
"""

from __future__ import annotations

import contextlib
import html.parser
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

ROOT = Path(__file__).resolve().parent
LIMIT = 1024 * 1024


class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.visible = []
        self.tags = []
        self.styles = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag in {"script", "style"}:
            self.hidden += 1
        data = dict(attrs)
        if tag == "link" and data.get("rel") == "stylesheet":
            self.styles.append(data.get("href", ""))

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.visible.append(data)


def request(port, path, method="GET"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, headers={"Accept": "text/html,application/json"})
        response = connection.getresponse()
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT:
            raise AssertionError("Response exceeded the test bound.")
        return response.status, {key.lower(): value for key, value in response.getheaders()}, body
    finally:
        connection.close()


def free_port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


@contextlib.contextmanager
def serve(mode, temporary):
    port = free_port()
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required.")
    command = ([node, str(ROOT / "node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", str(port)]
               if mode == "next-start" else [node, str(ROOT / ".next/standalone/server.js")])
    env = {"PATH": os.environ.get("PATH", ""), "NODE_ENV": "production",
           "NEXT_TELEMETRY_DISABLED": "1", "HOSTNAME": "127.0.0.1", "PORT": str(port)}
    if mode == "next-start":
        env["OCI_KIT_REFERENCE"] = "1"
    log = temporary / (mode + ".log")
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"{mode} exited before becoming ready.")
                try:
                    if request(port, "/healthz")[0] == 200:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError(f"{mode} did not become ready within 40 seconds.")
            yield port
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def contract(port):
    observations = {}

    def check(name, path, status, *, expected=None, text=None, method="GET", cache=False):
        actual, headers, body = request(port, path, method)
        assert actual == status, f"{name}: expected HTTP {status}, got {actual}"
        observation = {"status": actual}
        if expected is not None:
            assert "application/json" in headers.get("content-type", ""), name
            assert json.loads(body) == expected, name
            observation["json"] = expected
        if text is not None:
            page = Page()
            page.feed(body.decode())
            visible = " ".join(page.visible)
            for snippet in text:
                assert snippet in visible, f"{name}: missing server-rendered content"
            observation["visible_contract"] = text
        if cache:
            assert "no-store" in headers.get("cache-control", ""), name
            observation["no_store"] = True
        observations[name] = observation
        return headers, body

    check("health", "/healthz", 200, expected={"status": "ok", "example": "nextjs-standalone"}, cache=True)
    check("home", "/", 200, text=["Your next app.", "One clear step.", "Shape the idea", "Build a useful prototype"])
    query = urllib.parse.urlencode({"project": "Orbit & Co"})
    headers, body = check("deep_link_ssr_query", "/checklist/prototype?" + query, 200,
                         text=["Orbit & Co", "Build the smallest useful flow", "Try it with a potential user"], cache=True)
    page = Page()
    page.feed(body.decode())
    assert page.tags.count("li") == 3 and "label" in page.tags and "input" in page.tags
    assert page.styles, "Standalone page must include its CSS"
    asset = page.styles[0]
    assert asset.startswith("/_next/static/") and not urllib.parse.urlsplit(asset).netloc
    css_status, css_headers, css = request(port, asset)
    assert css_status == 200 and "text/css" in css_headers.get("content-type", "") and b".checklist" in css
    observations["bundled_stylesheet"] = {"bytes": len(css)}
    check("different_query", "/checklist/prototype?project=Second+idea", 200, text=["Second idea"], cache=True)
    # Next streams the dynamic notFound UI through its client payload; status is
    # the stable HTTP contract here. The static missing-page UI is checked below.
    check("unknown_stage", "/checklist/missing", 404)
    check("missing_page", "/no-such-page", 404, text=["Choose another step."])
    payload = '<img src=x onerror="alert(1)">'
    _, escaped = check("escaped_query", "/checklist/idea?" + urllib.parse.urlencode({"project": payload}), 200,
                       text=[payload], cache=True)
    safe_page = Page()
    safe_page.feed(escaped.decode())
    assert "img" not in safe_page.tags, "Query text must not become HTML elements"
    check("api", "/api/checklist?stage=prototype&" + query, 200, cache=True, expected={
        "stage": "prototype", "project": "Orbit & Co", "title": "Build a useful prototype",
        "tasks": ["Build the smallest useful flow", "Try it with a potential user", "Record what needs to change"],
    })
    error = {"error": "Use one valid stage and one project name of up to 64 characters."}
    check("api_unknown_stage", "/api/checklist?stage=missing", 400, expected=error, cache=True)
    check("api_long_query", "/api/checklist?project=" + "x" * 65, 400, expected=error, cache=True)
    check("api_repeated_query", "/api/checklist?project=a&project=b", 400, expected=error, cache=True)
    check("api_control_query", "/api/checklist?project=%00", 400, expected=error, cache=True)
    check("api_method", "/api/checklist", 405, method="POST")
    redirect_headers, _ = check("redirect", "/start?project=Orbit", 307)
    location = urllib.parse.urlsplit(redirect_headers.get("location", ""))
    assert location.path == "/checklist/idea" and location.query == "project=Orbit", "Redirect must preserve query"
    observations["redirect"]["location"] = location.path + "?" + location.query
    _, asset_body = check("public_asset", "/example.txt", 200)
    assert asset_body == b"Launch Notes static asset\n"
    _, head_body = check("head", "/healthz", 200, method="HEAD")
    assert head_body == b""
    return observations


def main():
    required = ["node_modules/next/dist/bin/next", ".next/reference/BUILD_ID", ".next/standalone/server.js",
                ".next/standalone/public/example.txt", ".next/standalone/.next/static"]
    if not all((ROOT / name).exists() for name in required):
        print("Run npm ci --ignore-scripts, then NEXT_TELEMETRY_DISABLED=1 npm run build first.", file=sys.stderr)
        return 2
    if list(ROOT.glob(".env*")) or list((ROOT / ".next/standalone").glob(".env*")):
        print("Use a clean example without .env files; this synthetic test needs no credentials.", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="oci-kit-nextjs-parity-") as directory:
            results = {}
            for mode in ("next-start", "standalone"):
                with serve(mode, Path(directory)) as port:
                    results[mode] = contract(port)
            assert results["next-start"] == results["standalone"], "HTTP contracts differ"
            print(json.dumps({"result": "passed", "checks_per_runtime": len(results["next-start"]),
                              "runtimes": ["next-start", "standalone"], "cloud": "not_tested",
                              "scope": "stateless local HTTP parity", "checks": list(results["next-start"])}))
        return 0
    except (AssertionError, RuntimeError, OSError, ValueError, http.client.HTTPException) as error:
        reason = str(error) if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__
        print(f"Parity failed: {reason}. No cloud was tested.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
