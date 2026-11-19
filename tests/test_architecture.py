"""Architecture claims stay within fresh, selected and explicitly typed evidence."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location("test_architecture_" + Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


architecture = load("scripts/architecture.py")


class Architecture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / "app"
        self.app.mkdir()
        (self.app / "app.py").write_text("raise RuntimeError('application must not execute')\n")
        self.common, self.p = architecture.modules()
        self.env = self.p.helper("environments")
        with self.p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": self.p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": self.p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": self.p.source_fingerprint(store.root_fd),
                        "kit_sha256": self.p.kit_fingerprint(), "records": {}})
        self.env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal",
                        target={"region": "us-phoenix-1", "profile": "DEFAULT", "auth": "api_key",
                                "origin": "https://private.example.invalid", "image_digest": "sha256:" + "a" * 64,
                                "ocpus": 1, "memory_gbs": 2})
        self.evidence = self.app / ".oci-kit/environments/rehearsal/evidence"

    def report(self):
        return architecture.request(self.app, environment="rehearsal")

    def control(self, name, value=None):
        return next(control for pillar in (value or self.report())["pillars"] for control in pillar["controls"] if control["id"] == name)

    def save(self, name, value):
        path = self.evidence / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return path

    def doctor(self, **changes):
        with self.p.Store(self.app, environment="rehearsal") as store:
            value = {**self.common.bound(store, self.p, architecture.READINESS), "observed_at": int(time.time()),
                     "mode": "live-read-only", "status": "incomplete", "checks": [
                         {"check": "app_subnet_id", "status": "passed"}, {"check": "registry", "status": "passed"}]}
        value.update(changes)
        return value

    def test_empty_report_is_read_only_and_keeps_unknowns(self):
        before = {str(path.relative_to(self.app)): path.read_bytes() for path in self.app.rglob("*") if path.is_file()}
        with mock.patch("subprocess.run", side_effect=AssertionError("No command execution")):
            value = self.report()
        after = {str(path.relative_to(self.app)): path.read_bytes() for path in self.app.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(value["status"], "incomplete")
        self.assertEqual(len(value["pillars"]), 5)
        self.assertEqual(self.control("compute_sizing", value)["status"], "configured")
        for name in ("effective_iam_and_state_isolation", "hosted_identity_and_two_user_isolation", "reported_usage_cost", "isolated_restore_and_rollback"):
            self.assertEqual(self.control(name, value)["status"], "unknown")
        self.assertFalse(value["certified"])
        self.assertFalse(value["production_ready"])
        self.assertFalse(value["approval_granted"])

    def test_environment_is_explicit_and_source_is_not_an_oci_target(self):
        with self.assertRaises(ValueError):
            architecture.request(self.app, environment=None)
        self.env.create(self.app, name="source", role="source", infrastructure=None)
        with self.assertRaises(ValueError):
            architecture.request(self.app, environment="source")

    def test_live_metadata_is_narrowly_observed_without_private_fields(self):
        value = self.doctor(raw_error="synthetic-private-canary", domain="private.example.invalid")
        self.save("doctor.json", value)
        result = self.report()
        control = self.control("private_application_subnet", result)
        self.assertEqual(control["status"], "observed")
        self.assertEqual(control["evidence"][0]["sha256"], self.p.digest(self.p.canonical(value)))
        raw = json.dumps(result)
        for forbidden in ("synthetic-private-canary", "private.example.invalid", str(self.app), "ocid1."):
            self.assertNotIn(forbidden, raw)
        self.assertIn("--environment", control["recheck_command"])
        self.assertEqual(control["recheck_command"][-1], "rehearsal")

    def test_offline_report_never_establishes_observed_resources(self):
        self.save("doctor.json", self.doctor(mode="offline"))
        self.assertEqual(self.control("private_application_subnet")["status"], "unknown")

    def test_public_subnet_fails_but_denied_read_remains_unknown(self):
        self.save("doctor.json", self.doctor(checks=[{"check": "app_subnet_id", "status": "blocked"}, {"check": "registry", "status": "unknown"}]))
        value = self.report()
        self.assertEqual(self.control("private_application_subnet", value)["status"], "failed")
        self.assertEqual(self.control("private_registry", value)["status"], "unknown")
        self.assertEqual(value["status"], "failed")

    def test_old_wrong_environment_source_and_kit_evidence_is_stale(self):
        for change in ({"observed_at": int(time.time()) - 86410}, {"environment": "production"},
                       {"source_sha256": "0" * 64}, {"kit_sha256": "0" * 64}, {"target_sha256": "0" * 64}):
            with self.subTest(change=change):
                self.save("doctor.json", self.doctor(**change))
                self.assertEqual(self.control("private_application_subnet")["status"], "stale")

    def test_newer_invalid_report_does_not_revive_an_older_pass(self):
        self.save("old.json", self.doctor(observed_at=int(time.time()) - 10))
        self.save("latest.json", self.doctor(checks=[{"check": "app_subnet_id", "status": "passed"}] * 2))
        self.assertEqual(self.control("private_application_subnet")["status"], "unknown")

    def test_all_three_same_timestamp_reports_are_ambiguous(self):
        value = self.doctor()
        for name in ("one.json", "two.json", "three.json"):
            self.save(name, value)
        result = self.report()
        self.assertEqual(self.control("private_application_subnet", result)["status"], "unknown")
        self.assertEqual(result["evidence_review"]["ambiguous"], 3)

    def test_future_and_undated_evidence_do_not_revive_an_older_pass(self):
        self.save("old.json", self.doctor(observed_at=int(time.time()) - 10))
        for timestamp, expected in ((int(time.time()) + 100, "stale"), (None, "unknown"), (True, "unknown")):
            self.save("latest.json", self.doctor(observed_at=timestamp))
            self.assertEqual(self.control("private_application_subnet")["status"], expected)

    def test_unrecognized_shapes_and_symlink_reports_do_not_expose_or_pass(self):
        self.save("odd.json", {"schema": ["unhashable"]})
        secret = self.app / "private.txt"
        secret.write_text("synthetic-private-canary")
        (self.evidence / "linked.json").symlink_to(secret)
        result = self.report()
        self.assertEqual(self.control("private_application_subnet", result)["status"], "unknown")
        self.assertGreater(result["evidence_review"]["unreadable"], 0)
        self.assertNotIn("synthetic-private-canary", json.dumps(result))

    def test_recovery_record_remains_owner_recorded(self):
        path = self.evidence / "recovery.txt"
        path.write_text("Owner says restore was completed")
        path.chmod(0o600)
        self.p.record(self.app, "recovery", path.relative_to(self.app).as_posix(), "passed", environment="rehearsal")
        self.assertEqual(self.control("isolated_restore_and_rollback")["status"], "owner-recorded")

    def parity(self):
        now = dt.datetime.now(dt.timezone.utc)
        with self.p.Store(self.app, environment="rehearsal") as store:
            value = {**self.common.bound(store, self.p, "oci-migration-parity/1"), "observed_at": int(time.time()),
                     "scope": "selected-https-origins", "status": "passed", "read_only": True,
                     "selected_image_digest": "sha256:" + "a" * 64, "target_image_digest": "sha256:" + "a" * 64,
                     "target_origin_sha256": self.p.digest(b"https://private.example.invalid"), "source_origin_sha256": "b" * 64,
                     "runner_sha256": self.p.digest((ROOT / "scripts/migration.py").read_bytes()), "contract_sha256": "c" * 64,
                     "run_id": "d" * 24, "interrupted": False, "contract_expired_during_run": False,
                     "started_at_utc": (now - dt.timedelta(seconds=1)).isoformat(), "finished_at_utc": now.isoformat(),
                     "checks": [{"id": "home", "source": "passed", "target": "passed", "parity": "passed"}]}
            value["source_revision_sha256"] = value["source_sha256"]
        return value

    def test_selected_parity_never_claims_cloud_or_browser_acceptance(self):
        value = self.parity()
        self.save("parity.json", value)
        control = self.control("hosting_migration_parity")
        self.assertEqual(control["status"], "tested")
        self.assertEqual(control["evidence"][0]["mode"], "selected-https-origins")
        self.assertEqual(self.control("hosted_identity_and_two_user_isolation")["status"], "unknown")
        value["checks"] *= 2
        self.save("parity.json", value)
        self.assertEqual(self.control("hosting_migration_parity")["status"], "unknown")

    def test_interrupted_expired_or_incomplete_parity_is_never_tested(self):
        for patch in ({"interrupted": True}, {"contract_expired_during_run": True}, {"runner_sha256": "0" * 64},
                      {"read_only": False}, {"contract_sha256": None}, {"selected_image_digest": "sha256:" + "0" * 64},
                      {"target_image_digest": "sha256:" + "0" * 64}, {"target_origin_sha256": "0" * 64},
                      {"source_revision_sha256": "0" * 64}, {"finished_at_utc": "2000-01-01T00:00:00Z"},
                      {"scope": "local-loopback-http"}, {"status": "failed"}):
            with self.subTest(patch=patch):
                value = self.parity(); value.update(patch)
                self.save("parity.json", value)
                self.assertEqual(self.control("hosting_migration_parity")["status"], "unknown")

    def test_source_changes_during_review_refuse_the_result(self):
        original = architecture.review
        def changed(store, p, common):
            value = original(store, p, common)
            (self.app / "app.py").write_text("changed = True\n")
            return value
        with mock.patch.object(architecture, "review", side_effect=changed), self.assertRaises(ValueError):
            self.report()


class OperatingArchitecture(unittest.TestCase):
    def setUp(self):
        module = load("tests/test_operations.py")
        self.fixture = module.BoundObservation()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app = self.fixture.app

    def control(self, name):
        value = architecture.request(self.app, environment="rehearsal")
        return next(c for pillar in value["pillars"] for c in pillar["controls"] if c["id"] == name)

    def observe(self, mode):
        result = self.fixture.observe()
        path = self.app / result["evidence"]
        value = json.loads(path.read_text())
        value["mode"] = mode
        self.fixture.write(path, value)
        return path, value

    def test_injected_client_is_never_live_evidence(self):
        self.observe("injected-test-client")
        self.assertEqual(self.control("deployed_image_identity")["status"], "unknown")
        self.assertEqual(self.control("container_health")["status"], "unknown")

    def test_recorded_live_readback_is_narrowly_observed_and_receipt_bound(self):
        self.observe("live-read-only")
        self.assertEqual(self.control("deployed_image_identity")["status"], "observed")
        self.fixture.write(self.fixture.path, dict(self.fixture.receipt, status="failed"))
        self.assertEqual(self.control("deployed_image_identity")["status"], "stale")

    def test_unknown_billing_is_not_zero_and_expired_certificate_is_failed(self):
        path, value = self.observe("live-read-only")
        value["costs"] = {"status": "unknown", "reported_amount": None}
        next(c for c in value["checks"] if c["id"] == "certificate_expiry")["status"] = "failed"
        self.fixture.write(path, value)
        self.assertEqual(self.control("reported_usage_cost")["status"], "unknown")
        self.assertEqual(self.control("certificate_validity")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
