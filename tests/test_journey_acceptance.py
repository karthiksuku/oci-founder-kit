"""Journey coverage cannot promote claims, stale evidence or local tests to OCI acceptance."""

import importlib.util
import datetime as dt
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("test_journey_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p, env, common, journey = [load(name) for name in ("project", "environments", "kit_common", "journey_acceptance")]


class FounderJourney(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / "app"
        self.app.mkdir()
        (self.app / "app.py").write_text("raise RuntimeError('application execution is forbidden during a report')\n")
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})
        self.target = {"region": "us-phoenix-1", "origin": "https://private-marker.example.invalid",
                       "image_digest": "sha256:" + "a" * 64, "port": 8080,
                       "compartment_id": "ocid1.compartment.oc1..syntheticjourney"}
        env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal", target=self.target)
        env.create(self.app, name="production", role="production", infrastructure="deploy/production")
        env.create(self.app, name="source", role="source")
        self.serial = 0

    def report(self, schema, *, changes=None, **values):
        with p.Store(self.app, environment="rehearsal") as store:
            value = {**common.bound(store, p, schema), "observed_at": int(time.time()), **values}
            if changes:
                value.update(changes)
            self.serial += 1
            p.helper("environments").put(store.evidence_fd, "synthetic-" + str(self.serial) + ".json", p.canonical(value))
        return value

    def runtime(self, **changes):
        return self.report("oci-runtime-probe/1", changes=changes, status="passed", scope="selected-https-origin",
                           read_only=True, selected_image_digest=self.target["image_digest"],
                           checks=[{"id": "https_health", "status": "passed"}])

    def run_report(self, kind="build"):
        return journey.request(self.app, environment="rehearsal", journey=kind)

    def gate(self, value, name):
        return next(row for row in value["gates"] if row["id"] == name)

    def snapshot(self):
        return {str(path.relative_to(self.app)): path.read_bytes() for path in self.app.rglob("*") if path.is_file()}

    def test_explicit_target_required_and_source_refused(self):
        for environment in (None, "missing", "source"):
            with self.subTest(environment=environment), self.assertRaises((ValueError, OSError)):
                journey.request(self.app, environment=environment)
        self.assertEqual(self.run_report()["environment"], "rehearsal")

    def test_report_is_read_only_and_does_not_expose_private_values(self):
        before = self.snapshot()
        with mock.patch("subprocess.run", side_effect=AssertionError("No child process")):
            value = self.run_report()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(value["network_requests"], 0)
        self.assertFalse(value["journey_accepted"])
        self.assertFalse(value["approval_granted"])
        raw = json.dumps(value)
        for private in (str(self.app), "private-marker", "ocid1.", self.target["image_digest"]):
            self.assertNotIn(private, raw)

    def test_bound_https_report_is_narrow_and_never_completes_journey(self):
        self.runtime()
        value = self.run_report()
        self.assertEqual(self.gate(value, "https_application")["status"], "reported")
        for name in ("hosted_sign_in", "two_user_isolation", "durable_persistence", "isolated_restore", "image_rollback"):
            self.assertEqual(self.gate(value, name)["status"], "missing")
        self.assertEqual(value["status"], "incomplete")
        self.assertFalse(value["journey_accepted"])

    def test_wrong_environment_source_kit_target_age_and_future_reports_never_advance(self):
        mutations = [{"environment": "production"}, {"source_sha256": "b" * 64}, {"kit_sha256": "b" * 64},
                     {"target_sha256": "b" * 64}, {"observed_at": int(time.time()) - 90000},
                     {"observed_at": int(time.time()) + 100}]
        for change in mutations:
            with self.subTest(change=change):
                self.runtime(**change)
                self.assertNotEqual(self.gate(self.run_report(), "https_application")["status"], "reported")
                for path in (self.app / ".oci-kit/environments/rehearsal/evidence").iterdir():
                    path.unlink()

    def test_three_tied_reports_remain_ambiguous(self):
        observed = int(time.time()) - 2
        for _ in range(3):
            self.runtime(observed_at=observed)
        self.assertEqual(self.gate(self.run_report(), "https_application")["status"], "ambiguous")

    def test_newer_failed_or_malformed_report_never_falls_back_to_pass(self):
        self.runtime(observed_at=int(time.time()) - 10)
        self.runtime(status="failed", checks=[{"id": "https_health", "status": "failed"}])
        value = self.run_report()
        self.assertEqual(self.gate(value, "https_application")["status"], "failed")
        self.assertEqual(value["status"], "failed")

    def test_boolean_claim_and_wrong_scope_do_not_establish_https(self):
        self.runtime(scope="local-loopback-http", checks=[], journey_accepted=True)
        value = self.run_report()
        self.assertEqual(self.gate(value, "https_application")["status"], "invalid")
        self.assertFalse(value["journey_accepted"])

    def test_malformed_dashboard_input_preserves_journey_coverage(self):
        self.report(["unrecognized-schema"], status="passed", sensitive="private-canary")
        self.runtime()
        value = self.run_report()
        self.assertEqual(value["status"], "incomplete")
        self.assertEqual(self.gate(value, "https_application")["status"], "reported")
        self.assertEqual(self.gate(value, "deployed_image")["status"], "missing")
        self.assertEqual(self.gate(value, "isolated_restore")["status"], "missing")
        self.assertGreater(value["evidence_counts"]["unreadable"], 0)
        self.assertNotIn("private-canary", json.dumps(value))

    def test_access_checks_require_live_narrow_results(self):
        access = {"schema": "oci-readiness/1", "mode": "live-read-only", "status": "passed",
                  "checks": [{"check": "region_subscription", "status": "passed"},
                             {"check": "compartment_access", "status": "passed"}]}
        self.report("oci-workload-readiness/1", mode="live-read-only", status="incomplete", access=access, checks=[])
        value = self.run_report()
        self.assertEqual(self.gate(value, "operator_read_access")["status"], "reported")
        self.assertEqual(self.gate(value, "effective_iam_isolation")["status"], "missing")

    def test_denied_access_stays_unknown_and_owner_claims_do_not_override(self):
        self.report("oci-workload-readiness/1", mode="live-read-only", status="incomplete",
                    access={"schema": "oci-readiness/1", "mode": "live-read-only", "status": "incomplete",
                            "checks": [{"check": "region_subscription", "status": "unknown"},
                                       {"check": "compartment_access", "status": "unknown"}]}, checks=[])
        with p.Store(self.app, environment="rehearsal", write=True) as store:
            path = p.save_report(store, {"approved": True, "restored": True, "journey_accepted": True}, "owner")
        p.record(self.app, "recovery", path, "passed", environment="rehearsal")
        value = self.run_report()
        self.assertEqual(self.gate(value, "operator_read_access")["status"], "unknown")
        self.assertEqual(self.gate(value, "isolated_restore")["status"], "missing")

    def test_local_migration_parity_does_not_establish_hosting_acceptance(self):
        self.report("oci-migration-parity/1", scope="local-loopback-http", status="passed", read_only=True,
                    selected_image_digest=self.target["image_digest"], contract_sha256="b" * 64,
                    runner_sha256=p.digest((ROOT / "scripts/migration.py").read_bytes()),
                    checks=[{"id": "health", "source": "passed", "target": "passed", "parity": "passed"}],
                    interrupted=False, contract_expired_during_run=False)
        value = self.run_report("migrate")
        self.assertEqual(self.gate(value, "hosting_parity")["status"], "invalid")
        for name in ("browser_workflows", "retained_services", "background_work_ownership", "traffic_rollback"):
            self.assertEqual(self.gate(value, name)["status"], "missing")

    def test_failed_and_interrupted_parity_are_not_reported_as_passed(self):
        with p.Store(self.app, environment="rehearsal") as store:
            source = p.source_fingerprint(store.root_fd)
        moment = dt.datetime.fromtimestamp(time.time() - 1, dt.timezone.utc).isoformat()
        self.report("oci-migration-parity/1", scope="selected-https-origins", status="passed", read_only=True,
                    selected_image_digest=self.target["image_digest"], contract_sha256="b" * 64,
                    target_image_digest=self.target["image_digest"], target_origin_sha256=p.digest(self.target["origin"].encode()),
                    source_origin_sha256="b" * 64, source_revision_sha256=source, run_id="c" * 24,
                    started_at_utc=moment, finished_at_utc=moment,
                    runner_sha256=p.digest((ROOT / "scripts/migration.py").read_bytes()),
                    checks=[{"id": "health", "source": "passed", "target": "passed", "parity": "passed"}],
                    interrupted=True, contract_expired_during_run=False)
        self.assertEqual(self.gate(self.run_report("migrate"), "hosting_parity")["status"], "unknown")

    def test_commands_preserve_named_environment_and_never_apply(self):
        value = self.run_report("migrate")
        for row in value["gates"]:
            command = row["recheck_command"]
            if command:
                self.assertEqual(command[-2:], ["--environment", "rehearsal"])
                self.assertNotIn("apply", command)
                self.assertNotIn("destroy", command)


if __name__ == "__main__":
    unittest.main()
