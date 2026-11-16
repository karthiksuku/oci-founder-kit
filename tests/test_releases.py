"""Release observations bind exact local evidence; rollback never executes cloud writes."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("test_release_" + name, ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


releases = load("releases")
p = load("project")
env = load("environments")
common = load("kit_common")


class ReleaseLedger(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.app = self.base / "app"; self.app.mkdir()
        (self.app / "deploy/rehearsal").mkdir(parents=True)
        (self.app / "app.py").write_text("raise RuntimeError('must not execute')\n")
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "build", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})
        self.image = "sha256:" + "a" * 64
        env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal",
                   target={"image_digest": self.image})
        self.operations = mock.Mock()
        self.receipt = "1" * 64
        self.operations.receipt_at.side_effect = lambda *args: ({}, self.receipt)
        self.patch = mock.patch.object(releases, "modules", return_value=(common, p, env, self.operations))
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.variables = self.base / "private-variables.json"
        self.refresh()

    def refresh(self, **changes):
        with p.Store(self.app, environment="rehearsal", write=True) as store:
            # Older reports remain in production; make fixture times distinguishable.
            for filename in os.listdir(store.evidence_fd):
                if filename.startswith("observe-"):
                    value = p.object_at(store.evidence_fd, filename, private=True)
                    value["observed_at"] -= 10
                    path = self.app / ".oci-kit/environments/rehearsal/evidence" / filename
                    path.write_bytes(p.canonical(value)); path.chmod(0o600)
            value = {**common.bound(store, p, "oci-operating-observation/1"), "observed_at": int(time.time()),
                     "mode": "live-read-only", "component_role": "web", "image_identity_verified": True,
                     "observed_image_digest": self.image, "receipt_sha256": self.receipt, "status": "unknown", **changes}
            self.observation = p.save_report(store, value, "observe")
            behavior = {**common.bound(store, p, "oci-runtime-probe/1"), "observed_at": int(time.time()),
                        "selected_image_digest": self.image, "status": "passed", "scope": "selected-https-origin"}
            self.evidence = p.save_report(store, behavior, "verify")

    def request(self, action="record", **kwargs):
        return releases.request(self.app, environment="rehearsal", action=action, **kwargs)

    def accept_two(self):
        self.request(evidence=self.evidence)
        self.image = "sha256:" + "b" * 64; self.receipt = "2" * 64
        env.configure(self.app, name="rehearsal", target={"image_digest": self.image})
        self.refresh(); self.request(evidence=self.evidence)
        values = {"app_image": "example.ocir.io/example/web@" + self.image, "port": 8080,
                  "external_service": "retain-original", "synthetic_private_setting": "private-sentinel"}
        self.variables.write_text(json.dumps(values)); self.variables.chmod(0o600)
        return values

    def test_record_is_append_only_and_limited_acceptance(self):
        result = self.request(evidence=self.evidence)
        self.assertEqual(result["acceptance_scope"], "anonymous-https-health")
        self.assertFalse(result["production_ready"])
        with self.assertRaises(ValueError):
            self.request(evidence=self.evidence)
        listing = self.request("list")
        self.assertEqual(len(listing["records"]), 1)
        self.assertNotIn("receipt", json.dumps(listing))

    def test_injected_unknown_wrong_image_or_failed_observation_cannot_record(self):
        for changes in ({"mode": "injected-test-client"}, {"image_identity_verified": False},
                        {"observed_image_digest": "sha256:" + "c" * 64}, {"status": "failed"},
                        {"receipt_sha256": "3" * 64}, {"component_role": "worker"},
                        {"observed_at": int(time.time()) - 90000}):
            self.refresh(**changes)
            # Select only this report for the freshness failure case.
            with mock.patch.object(releases, "latest_observation", return_value=json.loads((self.app / self.observation).read_text())):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.request(evidence=self.evidence)

    def test_wrong_environment_or_stale_behavior_refused(self):
        path = self.app / self.evidence
        value = json.loads(path.read_text()); value["environment"] = "production"
        path.write_text(json.dumps(value)); path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.request(evidence=self.evidence)
        with self.assertRaises(ValueError):
            self.request(evidence="../../outside.json")

    def test_digest_only_rollback_preserves_app_variables_and_needs_new_cloud_plan(self):
        values = self.accept_two(); app_before = (self.app / "app.py").read_bytes()
        proposal = self.request("rollback", variables=self.variables)
        self.assertFalse(proposal["cloud_write"])
        modified = json.loads((self.app / proposal["variables"]).read_text())
        self.assertEqual(modified, dict(values, app_image="example.ocir.io/example/web@sha256:" + "a" * 64))
        self.assertNotIn("private-sentinel", json.dumps(proposal))
        result = self.request("rollback", approve=proposal["proposal_sha256"])
        self.assertFalse(result["cloud_write"]); self.assertFalse(result["approval_granted"])
        self.assertEqual(json.loads((self.app / result["stack_variables"]).read_text()), modified)
        self.assertTrue(result["var_file"].endswith(".tfvars.json"))
        self.assertEqual((self.app / "app.py").read_bytes(), app_before)
        with p.Store(self.app, environment="rehearsal") as store:
            self.assertEqual(store.environment_config["target"]["image_digest"], "sha256:" + "a" * 64)
            self.assertTrue(any(n.startswith("environment-backup-") for n in os.listdir(store.fd)))
        with self.assertRaises(ValueError):
            self.request("rollback", approve=proposal["proposal_sha256"])

    def test_changed_variables_source_refused(self):
        self.accept_two(); proposal = self.request("rollback", variables=self.variables)
        self.variables.write_text(json.dumps({"app_image": "changed"})); self.variables.chmod(0o600)
        with self.assertRaises(ValueError):
            self.request("rollback", approve=proposal["proposal_sha256"])
        self.assertEqual(len(self.request("list")["records"]), 2)

    def test_expired_proposal_and_interrupted_deployment_refused(self):
        self.accept_two(); proposal = self.request("rollback", variables=self.variables)
        with mock.patch("time.time", return_value=proposal["expires_at"] + 1), self.assertRaises(ValueError):
            self.request("rollback", approve=proposal["proposal_sha256"])
        self.operations.receipt_at.side_effect = ValueError("latest deployment interrupted")
        with self.assertRaises(ValueError):
            self.request("rollback", variables=self.variables)

    def test_source_drift_and_locked_configuration_race_refused(self):
        self.accept_two(); proposal = self.request("rollback", variables=self.variables)
        (self.app / "app.py").write_text("changed application")
        with self.assertRaises(ValueError):
            self.request("rollback", approve=proposal["proposal_sha256"])
        with p.Store(self.app, environment="rehearsal") as store:
            expected = {k: v for k, v in common.bound(store, p, "ignored").items() if k.endswith("sha256")}
        (self.app / "app.py").write_text("raced application")
        with self.assertRaises(ValueError):
            env.configure(self.app, name="rehearsal", target={"image_digest": "sha256:" + "a" * 64}, expected_binding=expected)

    def test_replacement_ledger_and_unsafe_variable_permissions_refused(self):
        self.accept_two()
        self.variables.chmod(0o644)
        with self.assertRaises(ValueError):
            self.request("rollback", variables=self.variables)
        folder = self.app / ".oci-kit/environments/rehearsal/releases"
        entry = next(folder.glob("release-000001-*"))
        entry.write_text("{}"); entry.chmod(0o600)
        with self.assertRaises(ValueError):
            self.request("list")


if __name__ == "__main__":
    unittest.main()
