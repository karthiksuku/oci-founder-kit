"""Independent regressions for environment binding and private verification inputs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load("environment_security_project", ROOT / "scripts/project.py")
env = load("environment_security_config", ROOT / "scripts/environments.py")
migration = load("environment_security_migration", ROOT / "scripts/migration.py")
example = load("environment_security_example", ROOT / "examples/migrate-container/rehearse.py")


class EnvironmentSecurity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / "app"
        self.app.mkdir()
        (self.app / "app.py").write_text("# Existing application; never executed.\n")
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})
        env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal",
                   target={"origin": "https://target.example.test", "image_digest": "sha256:" + "a" * 64})

    def put(self, relative, data):
        path = self.app / relative
        path.write_text(json.dumps(data)); path.chmod(0o600)
        return path

    def bound_runtime(self):
        with p.Store(self.app, environment="rehearsal", write=True) as store:
            value = {"schema": "oci-runtime-probe/1", "environment": "rehearsal", "status": "passed",
                     "target_sha256": p.digest(p.canonical(store.environment_config)),
                     "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint(),
                     "observed_at": int(time.time()), "checks": [{"id": "https_health", "status": "passed"}]}
            return p.save_report(store, value, "verify")

    def test_unbound_legacy_doctor_cannot_advance_environment_access(self):
        report = {"schema": "oci-readiness/1", "mode": "live-read-only", "status": "passed", "checks": []}
        evidence = self.put(".oci-kit/environments/rehearsal/evidence/unbound.json", report)
        with self.assertRaises(ValueError):
            p.record(self.app, "access", evidence.relative_to(self.app).as_posix(), "passed", environment="rehearsal")
        # The existing non-environment command remains backward compatible.
        evidence = self.put(".oci-kit/evidence/legacy.json", report)
        result = p.record(self.app, "access", evidence.relative_to(self.app).as_posix(), "passed")
        self.assertEqual(next(row["status"] for row in result["steps"] if row["id"] == "access"), "owner-recorded")

    def bound_readiness(self, status, check_status):
        with p.Store(self.app, environment="rehearsal", write=True) as store:
            value = {"schema": "oci-workload-readiness/1", "environment": "rehearsal", "status": status,
                     "target_sha256": p.digest(p.canonical(store.environment_config)),
                     "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint(),
                     "observed_at": int(time.time()),
                     "access": {"schema": "oci-readiness/1", "mode": "live-read-only", "status": "passed"},
                     "checks": [{"check": "app_subnet_id", "status": check_status}]}
            return p.save_report(store, value, "doctor")

    def test_known_workload_blocker_cannot_advance_access_despite_valid_credentials(self):
        state = self.app / ".oci-kit/environments/rehearsal/state.json"
        before = state.read_bytes()
        for status in ("blocked", "failed", "unknown", None):
            with self.subTest(status=status):
                evidence = self.bound_readiness(status, "blocked")
                with self.assertRaises(ValueError):
                    p.record(self.app, "access", evidence, "passed", environment="rehearsal")
                self.assertEqual(state.read_bytes(), before)

    def test_incomplete_workload_can_record_proven_access_without_resolving_unknowns(self):
        evidence = self.bound_readiness("incomplete", "unknown")
        result = p.record(self.app, "access", evidence, "passed", environment="rehearsal")
        self.assertEqual(next(row["status"] for row in result["steps"] if row["id"] == "access"), "owner-recorded")
        report = json.loads((self.app / evidence).read_text())
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["checks"][0]["status"], "unknown")

    def test_machine_evidence_expires_on_resume(self):
        evidence = self.bound_runtime()
        p.record(self.app, "runtime", evidence, "passed", environment="rehearsal")
        future = time.time() + 90000
        with mock.patch.object(p.time, "time", return_value=future):
            result = p.resume(self.app, environment="rehearsal")
        self.assertEqual(next(row["status"] for row in result["steps"] if row["id"] == "runtime"), "stale")

    def test_plain_owner_notes_keep_the_original_freshness_model(self):
        path = self.app / ".oci-kit/environments/rehearsal/evidence/notes.txt"
        path.write_text("Synthetic reviewed local workflow evidence."); path.chmod(0o600)
        p.record(self.app, "local-workflow", path.relative_to(self.app).as_posix(), "passed", environment="rehearsal")
        with mock.patch.object(p.time, "time", return_value=time.time() + 90000):
            result = p.resume(self.app, environment="rehearsal")
        self.assertEqual(next(row["status"] for row in result["steps"] if row["id"] == "local-workflow"), "owner-recorded")

    def test_all_accepted_origins_work_with_runtime_validator(self):
        for origin in ("https://EXAMPLE.com/", "https://example.com?", "https://example.com#", "https://example.com/", "https://example.com:0", "https://example.com:8443"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                env.configure(self.app, name="rehearsal", target={"origin": origin})
        env.configure(self.app, name="rehearsal", target={"origin": "https://example.com:443"})
        self.assertEqual(migration.origin("https://example.com:443"), "https://example.com:443")

    def test_kit_fingerprint_includes_executed_helper_dependencies(self):
        baseline = p.kit_fingerprint()
        original = p.read_at
        for changed in ("oci_doctor.py", "backend_auth.py", "production_check.py"):
            def altered(directory, name, **kwargs):
                raw = original(directory, name, **kwargs)
                return raw + b"\n# changed fixture\n" if name == changed else raw
            with self.subTest(helper=changed), mock.patch.object(p, "read_at", side_effect=altered):
                self.assertNotEqual(p.kit_fingerprint(), baseline)

    def test_integrated_verifier_refuses_sessions_inside_git_before_requests(self):
        (self.app / ".git").mkdir()
        value = example.contract("http://127.0.0.1:18081", "http://127.0.0.1:18082")
        value["transport"] = "https"
        value["source"]["origin"] = "https://source.example.test"
        value["target"] = {"origin": "https://target.example.test", "image_digest": "sha256:" + "a" * 64}
        value["checks"] = value["checks"][:1]
        value["checks"][0]["session"] = "a"
        with p.Store(self.app, environment="rehearsal") as store:
            value["source"]["revision_sha256"] = p.source_fingerprint(store.root_fd)
        selected = self.put(".oci-kit/environments/rehearsal/contract.json", value)
        sessions = self.put(".oci-kit/environments/rehearsal/sessions.json", {"schema": "oci-migration-sessions/1",
            **{side: {"origin": value[side]["origin"], "users": {"a": "session=" + side + "-synthetic"}} for side in ("source", "target")}})
        original = p.helper
        with mock.patch.object(p, "helper", side_effect=lambda name: migration if name == "migration" else original(name)), \
                mock.patch.object(migration, "verify") as verify:
            with self.assertRaises(ValueError):
                p.verify(self.app, environment="rehearsal", kind="migration", contract=selected, sessions_file=sessions)
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
