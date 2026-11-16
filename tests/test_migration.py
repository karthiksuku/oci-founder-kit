"""Hosting-first contracts, redaction, negative controls and bounded transport."""
from contextlib import contextmanager, redirect_stderr
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


def helper(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = helper("migration", ROOT / "scripts/migration.py")
example = helper("migration_rehearsal", ROOT / "examples/migrate-container/rehearse.py")


def contract():
    value = example.contract("http://127.0.0.1:18081", "http://127.0.0.1:18082")
    value["transport"] = "https"
    value["source"]["origin"] = "https://source.example.test"
    value["target"]["origin"] = "https://target.example.test"
    value["checks"] = [{"id": "health", "method": "GET", "path": "/healthz", "status": 200,
                        "body": {"mode": "json", "pointers": ["/status"], "expected": {"/status": "ok"}}}]
    return value


class Client:
    def __init__(self, response=None, failure=None):
        self.calls = []
        self.response = response or migration.Response(200, [("Cache-Control", "no-store")], b'{"status":"ok"}')
        self.failure = failure

    def request(self, method, path, cookie=None):
        self.calls.append((method, path, cookie))
        if self.failure:
            raise self.failure
        return self.response


class Contracts(unittest.TestCase):
    def test_origins_require_explicit_safe_transports(self):
        self.assertEqual(migration.origin("https://source.example.test:8443"), "https://source.example.test:8443")
        for value in ("http://example.test", "https://a.test/", "https://a.test?secret=canary", "https://u:p@a.test",
                      "https://a.test#", "https://a.test:0", "https://a.test:", "https://A.test", "https://a.test\\b"):
            with self.subTest(value=value), self.assertRaises(migration.MigrationError):
                migration.origin(value)
        self.assertEqual(migration.origin("http://127.0.0.1:80", "local-loopback"), "http://127.0.0.1:80")
        for value in ("http://localhost", "http://169.254.169.254", "http://127.0.0.1.attacker.test"):
            with self.assertRaises(migration.MigrationError):
                migration.origin(value, "local-loopback")

    def test_unknown_fields_mutating_methods_unsafe_paths_and_duplicates_refused(self):
        cases = []
        c = contract(); c["command"] = "must-not-run"; cases.append(c)
        c = contract(); c["checks"][0]["method"] = "POST"; cases.append(c)
        c = contract(); c["checks"] *= 2; cases.append(c)
        c = contract(); c["checks"][0]["headers"] = {"authorization": {"equals": "canary"}}; cases.append(c)
        c = contract(); c["checks"][0]["status"] = True; cases.append(c)
        for path in ("//other.test/", "/x\r\nInjected:1", "/%0d%0aInjected:1", "/x#secret", "/\\other.test"):
            c = contract(); c["checks"][0]["path"] = path; cases.append(c)
        for c in cases:
            with self.assertRaises(migration.MigrationError):
                migration.validate_contract(c)

    def test_stale_future_long_and_same_origin_contracts_refused(self):
        now = datetime.now(timezone.utc)
        for field, value in (("expires_at_utc", now - timedelta(seconds=1)),
                             ("created_at_utc", now + timedelta(hours=1)),
                             ("expires_at_utc", now + timedelta(days=2))):
            c = contract(); c[field] = value.isoformat()
            with self.assertRaises(migration.MigrationError):
                migration.validate_contract(c)
        c = contract(); c["target"]["origin"] = c["source"]["origin"]
        with self.assertRaises(migration.MigrationError):
            migration.validate_contract(c)

    def test_private_file_modes_links_duplicate_keys_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            path.write_text(json.dumps(contract())); path.chmod(0o600)
            self.assertEqual(migration.load_private(path)["schema"], migration.SCHEMA)
            path.chmod(0o644)
            with self.assertRaises(migration.MigrationError):
                migration.load_private(path)
            path.chmod(0o600)
            linked = Path(tmp) / "linked"; linked.symlink_to(path)
            with self.assertRaises(migration.MigrationError):
                migration.load_private(linked)
            hard = Path(tmp) / "hard"; os.link(path, hard)
            with self.assertRaises(migration.MigrationError):
                migration.load_private(hard)
            hard.unlink()
            for data in ('{"a":1,"a":2}', '{"a":NaN}', "x" * (migration.MAX_INPUT + 1)):
                path.write_text(data)
                with self.assertRaises(migration.MigrationError):
                    migration.load_private(path)

    def test_sessions_have_exact_origin_binding_and_never_http(self):
        c = contract(); c["checks"][0]["session"] = "a"
        data = {"schema": "oci-migration-sessions/1", "source": {"origin": c["source"]["origin"], "users": {"a": "session=source-canary"}},
                "target": {"origin": c["target"]["origin"], "users": {"a": "session=target-canary"}}}
        self.assertEqual(migration.validate_sessions(data, c), data)
        for change in ("origin", "injection", "extra-user", "http"):
            candidate, selected = copy.deepcopy(data), copy.deepcopy(c)
            if change == "origin": candidate["target"]["origin"] = candidate["source"]["origin"]
            if change == "injection": candidate["target"]["users"]["a"] = "session=x\r\nInjected:1"
            if change == "extra-user": candidate["target"]["users"]["b"] = "session=another"
            if change == "http": selected["transport"] = "local-loopback"
            with self.assertRaises(migration.MigrationError):
                migration.validate_sessions(candidate, selected)
        with self.assertRaises(migration.MigrationError):
            migration.verify(c, client_factory=lambda _: Client())

    def test_session_file_in_git_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / ".git").mkdir()
            path = root / "sessions.json"; path.write_text("{}"); path.chmod(0o600)
            with self.assertRaises(migration.MigrationError):
                migration.load_private(path, outside_git=True)

    def test_existing_output_and_wrong_environment_stop_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp = root / "contract.json"; output = root / "report.json"
            c = contract(); cp.write_text(json.dumps(c)); cp.chmod(0o600)
            args = ["verify", "--contract", str(cp), "--environment", "rehearsal", "--source", c["source"]["origin"],
                    "--target", c["target"]["origin"], "--out", str(output)]
            output.write_text("unchanged")
            with mock.patch.object(migration, "verify") as run, redirect_stderr(io.StringIO()):
                self.assertEqual(migration.main(args), 2); run.assert_not_called()
            self.assertEqual(output.read_text(), "unchanged")
            output.unlink()
            args[args.index("rehearsal")] = "production"
            with mock.patch.object(migration, "verify") as run, redirect_stderr(io.StringIO()):
                self.assertEqual(migration.main(args), 2); run.assert_not_called()
            self.assertFalse(output.exists())


class Comparisons(unittest.TestCase):
    def test_pass_is_selected_scope_not_image_identity_or_production_readiness(self):
        clients = {side: Client() for side in ("source", "target")}
        report = migration.verify(contract(), client_factory=clients.get)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["production_readiness_established"])
        self.assertFalse(report["image_identity_verified"])
        self.assertEqual(report["environment"], "rehearsal")
        self.assertIn("browser-hydration-and-navigation", report["not_covered"])
        for client in clients.values():
            self.assertEqual(client.calls, [("GET", "/healthz", None)])

    def test_body_mismatch_and_failed_source_baseline_are_distinct(self):
        c = contract(); del c["checks"][0]["body"]["expected"]
        clients = {"source": Client(), "target": Client(migration.Response(200, [], b'{"status":"different"}'))}
        result = migration.verify(c, client_factory=clients.get)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checks"][0], {"id": "health", "source": "passed", "target": "passed", "parity": "failed"})
        result = migration.verify(contract(), client_factory=lambda _: clients["target"])
        self.assertEqual(result["checks"][0]["source"], "failed")

    def test_unavailable_and_interrupted_requests_are_unknown(self):
        for failure in (migration.MigrationError("private-canary"), KeyboardInterrupt()):
            result = migration.verify(contract(), client_factory=lambda _: Client(failure=failure))
            self.assertEqual(result["status"], "unknown")
            self.assertNotIn("private-canary", json.dumps(result))

    def test_expiry_during_run_never_passes(self):
        c = contract()
        class Expiring(Client):
            def request(self, *args):
                c["expires_at_utc"] = datetime.now(timezone.utc).isoformat()
                return super().request(*args)
        report = migration.verify(c, client_factory=lambda _: Expiring())
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(report["contract_expired_during_run"])

    def test_cookies_body_headers_and_origins_are_not_in_report(self):
        c = contract(); c["checks"][0]["session"] = "a"
        data = {"schema": "oci-migration-sessions/1"}
        clients = {}
        for side in ("source", "target"):
            data[side] = {"origin": c[side]["origin"], "users": {"a": "session=" + side + "-canary"}}
            clients[side] = Client(migration.Response(200, [("Set-Cookie", "canary-header=hidden")],
                                                       b'{"status":"ok","secret":"canary-body"}'))
        report = migration.verify(c, sessions=data, client_factory=clients.get)
        text = json.dumps(report)
        for forbidden in ("source-canary", "target-canary", "canary-header", "canary-body", c["source"]["origin"], c["target"]["origin"]):
            self.assertNotIn(forbidden, text)
        self.assertEqual(clients["target"].calls[0][2], "session=target-canary")

    def test_fixed_predicates_detect_redirect_cache_stream_and_cookie_failures(self):
        c = {"id": "selected", "method": "GET", "path": "/", "status": 307, "body": {"mode": "none"}, "location": "/ok"}
        with self.assertRaises(migration.MigrationError):
            migration.projection(c, migration.Response(307, [("Location", "https://other.test/ok")], b""), "https://selected.test")
        c.update(status=200, headers={"cache-control": {"equals": "no-store"}}); del c["location"]
        with self.assertRaises(migration.MigrationError):
            migration.projection(c, migration.Response(200, [("Cache-Control", "public")], b""), "https://selected.test")
        del c["headers"]; c["streaming"] = {"first_byte_ms_max": 100, "span_ms_min": 50, "completion_ms_max": 1000}
        with self.assertRaises(migration.MigrationError):
            migration.projection(c, migration.Response(200, [], b"buffered", 80, 80), "https://selected.test")
        migration.projection(c, migration.Response(200, [], b"stream", 20, 120), "https://selected.test")
        del c["streaming"]; c["cookies"] = {"present": True, "secure": True, "httponly": True, "samesite": "Lax"}
        with self.assertRaises(migration.MigrationError):
            migration.projection(c, migration.Response(200, [("Set-Cookie", "session=canary; SameSite=Lax")], b""), "https://selected.test")
        migration.projection(c, migration.Response(200, [("Set-Cookie", "session=canary; Secure; HttpOnly; SameSite=Lax")], b""), "https://selected.test")

    def test_repeated_cache_read_changed_data_fails(self):
        c = contract(); c["checks"][0]["repeat"] = 2; del c["checks"][0]["body"]["expected"]
        class Changing(Client):
            def request(self, *args):
                response = super().request(*args)
                return response if len(self.calls) == 1 else migration.Response(200, [], b'{"status":"changed"}')
        self.assertEqual(migration.verify(c, client_factory=lambda _: Changing())["status"], "failed")

    def test_dns_bound_does_not_send_request(self):
        client = migration.HTTPClient("https://example.test", deadline=time.monotonic() + .02)
        def slow(*args, **kwargs):
            time.sleep(.1)
            return []
        with mock.patch.object(migration.socket, "getaddrinfo", side_effect=slow), \
                mock.patch.object(migration.http.client.HTTPSConnection, "request") as send:
            with self.assertRaises(migration.MigrationError):
                client.request("GET", "/")
            send.assert_not_called()


class Review(unittest.TestCase):
    def scan(self, codes=("next-runtime",)):
        return {"schema": "oci-web-migration/1", "findings": [{"code": code} for code in codes],
                "coverage": {"status": "bounded-static-scan"}}

    def test_no_findings_or_unreviewed_features_never_mean_portable(self):
        for scan in (self.scan(()), self.scan()):
            report = migration.assess(scan)
            self.assertFalse(report["portability_established"])
            self.assertFalse(report["inventory_complete"])
            self.assertEqual(report["status"], "review-required")
        self.assertEqual(migration.assess(self.scan())["features"][0]["outcome"], "unknown")

    def test_reviewed_outcomes_need_current_scan_and_evidence(self):
        scan = self.scan()
        reviews = {"schema": "oci-migration-reviews/1", "scan_sha256": migration.digest(migration.canonical(scan)),
                   "features": [{"feature": "next-runtime", "outcome": "supported", "evidence_sha256": "a" * 64}]}
        self.assertEqual(migration.assess(scan, reviews)["status"], "selected-features-reviewed")
        for outcome in ("adaptation-required", "unsupported", "unknown"):
            reviews["features"][0]["outcome"] = outcome
            self.assertEqual(migration.assess(scan, reviews)["status"], "review-required")
        reviews["features"][0].update(outcome="supported", evidence_sha256=None)
        with self.assertRaises(migration.MigrationError):
            migration.assess(scan, reviews)
        reviews["scan_sha256"] = "b" * 64
        with self.assertRaises(migration.MigrationError):
            migration.assess(scan, reviews)

    def test_incomplete_scan_and_unknown_codes_remain_unresolved(self):
        scan = self.scan(); scan["coverage"]["status"] = "incomplete"
        reviews = {"schema": "oci-migration-reviews/1", "scan_sha256": migration.digest(migration.canonical(scan)),
                   "features": [{"feature": "next-runtime", "outcome": "supported", "evidence_sha256": "a" * 64}]}
        self.assertEqual(migration.assess(scan, reviews)["status"], "review-required")
        with self.assertRaises(migration.MigrationError):
            migration.assess(self.scan(("made-up-feature",)))

    def test_jobs_require_consistent_single_owner_attestation(self):
        c = contract(); self.assertEqual(migration.review(c)["job_ownership"], "unknown")
        c["jobs"] = {"inventory": "attested", "owner": "source", "source_enabled": True,
                     "target_enabled": False, "evidence_sha256": "a" * 64}
        review = migration.review(c)
        self.assertEqual(review["job_ownership"], "attested")
        self.assertFalse(review["cutover_authorized"])
        self.assertFalse(review["data_migration_authorized"])
        c["jobs"]["target_enabled"] = True
        self.assertEqual(migration.review(c)["job_ownership"], "conflict")
        c["jobs"]["source_enabled"] = False
        self.assertEqual(migration.review(c)["job_ownership"], "conflict")

    def test_wrong_environment_digest_runner_and_incomplete_evidence_are_rejected(self):
        c = contract(); report = migration.verify(c, client_factory=lambda _: Client())
        self.assertEqual(migration.review(c, report)["parity"], "passed")
        for field, value in (("environment", "production"), ("target_image_digest", "sha256:" + "b" * 64),
                             ("runner_sha256", "a" * 64), ("checks", []), ("scope", "local-loopback-http")):
            candidate = copy.deepcopy(report); candidate[field] = value
            with self.assertRaises(migration.MigrationError):
                migration.review(c, candidate)


@unittest.skipUnless(os.environ.get("FOUNDER_KIT_MIGRATION_LOCAL") == "1", "Opt-in owned local HTTP/TLS application checks.")
class LocalApplication(unittest.TestCase):
    def test_real_container_example_rehearsal_and_negative_controls(self):
        result = example.run()
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["source_preserved"])
        self.assertFalse(result["browser_workflows_verified"])

    def test_actual_redirect_never_followed_and_oversize_is_unknown(self):
        visits = []
        class Redirect(example.app.Handler):
            def do_GET(self):
                visits.append(self.path)
                self.reply(302, location="http://127.0.0.1:1/forbidden")
        class Oversize(example.app.Handler):
            def do_GET(self):
                self.reply(200, b"x" * (migration.MAX_RESPONSE + 1))
        with example.serve() as source:
            for handler, expected in ((Redirect, "failed"), (Oversize, "unknown")):
                with example.serve(handler) as target:
                    c = example.contract(source, target); c["checks"] = c["checks"][:1]
                    self.assertEqual(migration.verify(c)["status"], expected)
        self.assertEqual(visits, ["/healthz"])

    def test_actual_https_session_isolation_ca_and_redaction(self):
        self.assertIsNotNone(shutil.which("openssl"))
        class Auth(example.app.Handler):
            def do_GET(self):
                session = self.headers.get("Cookie", "")
                status = "a" if session == "session=a-private-canary" else "b" if session == "session=b-private-canary" else "anonymous"
                self.reply(200, json.dumps({"status": status}).encode())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); key, cert = root / "key.pem", root / "ca.pem"
            proc = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                                   "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
                                   "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 0); cert.chmod(0o600); key.chmod(0o600)
            @contextmanager
            def serve():
                with ThreadingHTTPServer(("127.0.0.1", 0), Auth) as server:
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    context.load_cert_chain(cert, key)
                    server.socket = context.wrap_socket(server.socket, server_side=True)
                    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                    try:
                        yield "https://127.0.0.1:" + str(server.server_port)
                    finally:
                        server.shutdown(); thread.join(timeout=3)
            with serve() as source, serve() as target:
                c = contract(); c["source"]["origin"] = source; c["target"]["origin"] = target
                c["checks"] = [{"id": "session-" + user, "path": "/session", "method": "GET", "status": 200,
                                "session": user, "body": {"mode": "json", "pointers": ["/status"], "expected": {"/status": user}}} for user in ("a", "b")]
                sessions = {"schema": "oci-migration-sessions/1"}
                for side in ("source", "target"):
                    sessions[side] = {"origin": c[side]["origin"], "users": {user: "session=" + user + "-private-canary" for user in ("a", "b")}}
                result = migration.verify(c, sessions=sessions, ca_file=cert)
                self.assertEqual(result["status"], "passed", result["checks"])
                self.assertNotIn("private-canary", json.dumps(result))
                self.assertEqual(migration.verify(c, sessions=sessions)["status"], "unknown")

    @unittest.skipUnless(os.environ.get("FOUNDER_KIT_NEXTJS_PARITY") == "1", "Opt-in previously built Next.js application.")
    def test_generic_checks_against_real_nextjs_server_and_standalone(self):
        nextjs = helper("migration_nextjs_parity", ROOT / "examples/migrate-nextjs/parity.py")
        preserved = {path: path.read_bytes() for path in (ROOT / "examples/migrate-nextjs/app").rglob("*.js")}
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            with nextjs.serve("next-start", temporary) as source, nextjs.serve("standalone", temporary) as target:
                c = example.contract("http://127.0.0.1:" + str(source), "http://127.0.0.1:" + str(target))
                c["checks"] = [
                    {"id": "health", "method": "GET", "path": "/healthz", "status": 200,
                     "body": {"mode": "json", "pointers": ["/status", "/example"], "expected": {"/status": "ok", "/example": "nextjs-standalone"}}},
                    {"id": "query-workflow", "method": "GET", "path": "/api/checklist?stage=prototype&project=Orbit", "status": 200,
                     "headers": {"cache-control": {"contains": "no-store"}}, "repeat": 2,
                     "body": {"mode": "json", "pointers": ["/stage", "/project", "/tasks"], "expected": {"/stage": "prototype", "/project": "Orbit"}}},
                    {"id": "redirect", "method": "GET", "path": "/start?project=Orbit", "status": 307,
                     "location": "/checklist/idea?project=Orbit", "body": {"mode": "none"}},
                    {"id": "static-asset", "method": "GET", "path": "/example.txt", "status": 200,
                     "body": {"mode": "sha256", "expected_sha256": migration.digest(b"Launch Notes static asset\n")}},
                    {"id": "head", "method": "HEAD", "path": "/healthz", "status": 200, "body": {"mode": "none"}},
                ]
                result = migration.verify(c)
                self.assertEqual(result["status"], "passed", result["checks"])
                # A bad acceptance expectation must fail both real runtimes.
                c["checks"][1]["body"]["expected"]["/project"] = "wrong-project"
                result = migration.verify(c)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["checks"][1]["source"], "failed")
                self.assertEqual(result["checks"][1]["target"], "failed")
        self.assertTrue(all(path.read_bytes() == before for path, before in preserved.items()))


if __name__ == "__main__":
    unittest.main()
