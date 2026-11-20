"""Founder-facing rehearsal planning and the actual emitted Python health command."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import shlex
import subprocess
import sys
import threading

from test_foundation_packaging import Fixture, load, package

kit = load("kit")


class RehearsalPlan(Fixture):
    def cli(self, *args):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = kit.main(["sre", *args, "--project", str(self.app), "--json"])
        return code, json.loads(capture.getvalue())

    def test_preserves_existing_workflow_and_only_shows_known_script_names(self):
        (self.app / "package.json").write_text(json.dumps({"dependencies": {"next": "test"},
            "scripts": {"test": "never execute this private string", "start": "private-command"}}))
        folder = self.app / ".github/workflows"
        folder.mkdir(parents=True)
        (folder / "company.yaml").write_text("unchanged")
        path = self.private / "sre-journey.json"
        path.write_text(json.dumps({"schema":"oci-sre-journey/1", "journey":"customer-record",
                                    "assertions":["private acceptance description"]}))
        path.chmod(0o600)
        code, value = self.cli("plan", "--environment", "rehearsal")
        self.assertEqual((code, value["profile"], value["existing_workflow_count"]), (0, "hosting-first-nextjs", 1))
        self.assertEqual((value["assertion_count"], value["discovered_scripts"]), (1, ["test"]))
        self.assertNotIn("private acceptance", json.dumps(value))
        self.assertNotIn("private string", json.dumps(value))
        self.assertFalse(value["approval_granted"])
        self.assertEqual((folder / "company.yaml").read_text(), "unchanged")

    def test_wrong_role_and_missing_environment_stay_blocked(self):
        self.assertEqual(self.cli("check", "--environment", "rehearsal")[0], 3)
        self.assertEqual(self.cli("plan")[0], 3)
        self.assertEqual(self.cli("plan", "--environment", "rehearsal", "--live")[0], 3)


class Probes(Fixture):
    def test_generated_python_probe_uses_first_response_even_when_optimized(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                status = {"/ok": 200, "/login": 200, "/redirect": 302, "/down": 503, "/empty": 204}[self.path]
                self.send_response(status)
                if status == 302:
                    self.send_header("Location", "/login")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        for path, result in (("/ok", 0), ("/redirect", 1), ("/empty", 1), ("/down", 1)):
            cmd = package.health_command({"probe_runtime": "python", "port": server.server_port, "health_path": path})
            self.assertEqual(subprocess.run([sys.executable, "-O", *shlex.split(cmd)[1:]], timeout=5).returncode, result)
        self.assertNotIn("/login", seen)
        measure = load("sre_latency_drill").measure
        for route, good in (("/ok", 4), ("/redirect", 0)):
            result = measure(port=server.server_port, route=route, attempts=4, clients=2, latency_ms=2000, good_percent=100)
            self.assertEqual((result["within_threshold"], result["status"]), (good, "passed" if good else "failed"))
        self.assertNotIn("/login", seen)
