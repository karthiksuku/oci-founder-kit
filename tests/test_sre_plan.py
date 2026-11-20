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

    def test_build_discovers_own_app_routes_in_doctor_journey_and_planner(self):
        from test_foundation_packaging import p
        with p.Store(self.app, environment="rehearsal", write=True) as store:
            state = store.read()
            state["task"] = "build"
            store.save(state)
        manifest = self.app / "package.json"
        manifest.write_text('{"dependencies":{"next":"16.0.0"},"scripts":{"test":"private-test --sensitive"}}')
        expected = "new-app-nextjs"
        _, value = self.cli("plan", "--environment", "rehearsal")
        self.assertEqual(value["profile"], expected)
        self.assertNotIn("private-test", json.dumps(value))
        for route in (p.doctor(self.app, environment="rehearsal")["launch_workflow"],
                      p.helper("journey_acceptance").request(self.app, environment="rehearsal")["launch_workflow"]):
            self.assertEqual(route["profile"], expected)
            self.assertEqual(route["recheck_command"][-2:], ["--environment", "rehearsal"])
        # Neither boilerplate nor a recipe label establishes an own-app Next.js codebase.
        manifest.write_text('{"dependencies":{"express":"5"}}')
        desc = {"schema":"oci-kit-application/1", "recipe":"nextjs", "app_directory":".", "port":8080,
                "health_path":"/health", "commands":{key:["demo"] for key in ("build","start","test")},
                "dependencies":[], "background_work":"absent", "probe_runtime":"node",
                "base_image":"node@sha256:"+"a"*64}
        path=self.private/"application.json"
        path.write_text(json.dumps(desc)); path.chmod(0o600)
        self.assertEqual(self.cli("plan", "--environment","rehearsal")[1]["profile"], "other-container")

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
