"""Separate targets preserve app bytes, stale evidence and never transfer approvals."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("test_environment_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load("project")
env = load("environments")
dashboard = load("dashboard")


class Environments(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / "app"
        self.app.mkdir()
        (self.app / "app.py").write_text("raise RuntimeError('application must not execute')\n")
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})

    def create(self, name="rehearsal", **kwargs):
        return env.create(self.app, name=name, role=kwargs.pop("role", "rehearsal"),
                          infrastructure=kwargs.pop("infrastructure", "deploy/" + name), **kwargs)

    def evidence(self, name="rehearsal", raw=b"Synthetic local workflow result"):
        path = self.app / ".oci-kit/environments" / name / "evidence/local.txt"
        path.write_bytes(raw)
        path.chmod(0o600)
        return path.relative_to(self.app).as_posix()

    def test_environment_state_is_separate_and_legacy_unchanged(self):
        before = (self.app / ".oci-kit/state.json").read_bytes()
        app_before = (self.app / "app.py").read_bytes()
        self.create()
        self.create("production", role="production")
        evidence = self.evidence()
        p.record(self.app, "local-workflow", evidence, "passed", environment="rehearsal")
        statuses = {row["id"]: row["status"] for row in p.resume(self.app, environment="production")["steps"]}
        self.assertEqual(statuses["local-workflow"], "not-recorded")
        self.assertEqual(before, (self.app / ".oci-kit/state.json").read_bytes())
        self.assertEqual(app_before, (self.app / "app.py").read_bytes())
        self.assertEqual(p.resume(self.app)["schema"], "oci-kit-project/1")

    def test_target_change_makes_old_records_stale(self):
        self.create()
        p.record(self.app, "local-workflow", self.evidence(), "passed", environment="rehearsal")
        env.configure(self.app, name="rehearsal", target={"region": "us-phoenix-1"})
        report = p.resume(self.app, environment="rehearsal")
        self.assertTrue(report["inputs_changed"])
        self.assertEqual(next(row["status"] for row in report["steps"] if row["id"] == "local-workflow"), "stale")
        self.assertTrue(list((self.app / ".oci-kit/environments/rehearsal").glob("environment-backup-*.json")))

    def test_conversion_backs_up_legacy_evidence_without_importing_success(self):
        old = self.app / ".oci-kit/evidence/old.txt"
        old.write_bytes(b"old verified evidence")
        old.chmod(0o600)
        p.record(self.app, "local-workflow", ".oci-kit/evidence/old.txt", "passed")
        raw = (self.app / ".oci-kit/state.json").read_bytes()
        result = self.create(convert_legacy=True)
        backups = list((self.app / ".oci-kit/environment-backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "state.json").read_bytes(), raw)
        self.assertEqual((backups[0] / "evidence/old.txt").read_bytes(), old.read_bytes())
        self.assertFalse(result["approvals_imported"])
        self.assertFalse(result["records_imported"])
        with p.Store(self.app, environment="rehearsal") as store:
            self.assertEqual(store.read()["records"], {})

    def test_rejects_shared_or_nested_infrastructure_and_wrong_evidence(self):
        self.create()
        for path in ("deploy/rehearsal", "deploy/rehearsal/nested", "deploy"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.create("production", role="production", infrastructure=path)
        self.create("production", role="production")
        with self.assertRaises(ValueError):
            p.record(self.app, "local-workflow", self.evidence(), "passed", environment="production")

    def test_symlink_unsafe_owner_permissions_and_interruption_fail_closed(self):
        self.create()
        parent = self.app / ".oci-kit/environments"
        (parent / "production").symlink_to(parent / "rehearsal", target_is_directory=True)
        with self.assertRaises(OSError):
            p.resume(self.app, environment="production")
        (parent / "production").unlink()
        (parent / ".pending-interrupted").mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            self.create("production", role="production")
        (parent / ".pending-interrupted").rmdir()
        (parent / "rehearsal").chmod(0o755)
        with self.assertRaises(ValueError):
            p.resume(self.app, environment="rehearsal")

    def test_config_rejects_secrets_unapproved_keys_and_credential_urls(self):
        for target in ({"token": "not-a-real-token"}, {"origin": "https://name:secret@example.invalid"},
                       {"origin": "http://example.invalid"}, {"image_digest": "latest"}, {"port": True}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.create(target=target)
        for name in ("../outside", "default/production", "Production"):
            with self.assertRaises(ValueError):
                self.create(name)

    def test_receipts_from_another_environment_do_not_advance_this_one(self):
        self.create()
        self.create("production", role="production")
        receipt_dir = self.app / "deploy/rehearsal/.gate/receipts"
        receipt_dir.mkdir(parents=True)
        receipt = receipt_dir / "receipt.json"
        receipt.write_text(json.dumps({"schema": "oci-deploy-receipt/2", "kind": "apply", "status": "failed",
            "started_at": "2026-01-01T12:00:00+00:00", "plan_sha256": "a" * 64}))
        receipt.chmod(0o600)
        rehearsal = p.resume(self.app, environment="rehearsal")
        production = p.resume(self.app, environment="production")
        self.assertEqual(next(r["status"] for r in rehearsal["steps"] if r["id"] == "deployment"), "attempt-needs-review")
        self.assertEqual(next(r["status"] for r in production["steps"] if r["id"] == "deployment"), "unobserved")
        data = json.loads(receipt.read_text())
        data["status"] = "applied"
        receipt.write_text(json.dumps(data))
        rehearsal = p.resume(self.app, environment="rehearsal")
        self.assertEqual(next(r["status"] for r in rehearsal["steps"] if r["id"] == "deployment"), "attempt-needs-review")

    def test_bound_receipt_becomes_untrusted_after_environment_changes(self):
        backend = {"region": "us-phoenix-1", "namespace": "synthetic", "bucket": "state-fixture",
                   "key": "rehearsal/state.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        target = {"region": "us-phoenix-1", "compartment_id": "ocid1.compartment.oc1..rehearsal",
                  "profile": "DEFAULT", "auth": "api_key"}
        self.create(target=target, backend=backend)
        stack = self.app / "deploy/rehearsal"
        receipt_dir = stack / ".gate/receipts"
        receipt_dir.mkdir(parents=True)
        for source in (ROOT / "blueprints/web-container/terraform").glob("*.tf"):
            shutil.copyfile(source, stack / source.name)
        shutil.copyfile(ROOT / "blueprints/web-container/terraform/backend.tf.json.example",
                        stack / "backend.tf.json")
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py")
        binding = gate.select(stack, project=self.app, environment="rehearsal",
                              backend=dict(backend, auth="APIKey", config_file_profile="DEFAULT"))
        path = receipt_dir / "receipt.json"
        path.write_text(json.dumps({"schema": "oci-deploy-receipt/2", "kind": "apply", "status": "applied",
            "started_at": "2026-01-01T12:00:00+00:00", "plan_sha256": "a" * 64, "project_environment": binding}))
        path.chmod(0o600)
        result = p.resume(self.app, environment="rehearsal")
        self.assertEqual(next(row["status"] for row in result["steps"] if row["id"] == "deployment"), "apply-receipt-observed")
        env.configure(self.app, name="rehearsal", target=dict(target, region="us-ashburn-1"))
        result = p.resume(self.app, environment="rehearsal")
        self.assertEqual(next(row["status"] for row in result["steps"] if row["id"] == "deployment"), "attempt-needs-review")

    def test_dashboard_uses_bound_fresh_projections_and_never_raw_evidence(self):
        self.create(target={"image_digest": "sha256:" + "a" * 64})
        with p.Store(self.app, environment="rehearsal", write=True) as store:
            current = {"schema": "oci-runtime-probe/1", "environment": "rehearsal", "status": "failed",
                "target_sha256": p.digest(p.canonical(store.environment_config)),
                "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint(),
                "observed_at": int(time.time()), "checks": [{"status": "failed", "message": "SECRET_SENTINEL<script>alert(1)</script>"}]}
            p.save_report(store, current, "current")
            p.save_report(store, dict(current, observed_at=int(time.time()) - 90000), "stale")
            p.save_report(store, dict(current, environment="production"), "wrong")
        with mock.patch("subprocess.run", side_effect=AssertionError("No network/command for dashboard")):
            result = dashboard.render(self.app, environment="rehearsal")
        path = self.app / result["path"]
        raw = path.read_text()
        self.assertNotIn("SECRET_SENTINEL", raw)
        self.assertNotIn("<script", raw)
        self.assertIn("2 stale", raw)
        self.assertIn("Unknown", raw)
        self.assertIn("default-src 'none'", raw)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_source_role_has_no_oci_infrastructure(self):
        result = self.create("source", role="source", infrastructure=None)
        self.assertEqual(result["role"], "source")
        report = p.resume(self.app, environment="source")
        self.assertEqual([step["id"] for step in report["steps"]], ["migration-assessment", "local-workflow", "source-handoff"])
        with self.assertRaises(ValueError):
            p.verify(self.app, environment="source")

    def test_distinct_environment_backend_and_compartment_bindings(self):
        backend = {"region": "us-phoenix-1", "namespace": "synthetic", "bucket": "state-fixture",
                   "key": "rehearsal/state.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        target = {"compartment_id": "ocid1.compartment.oc1..rehearsal"}
        self.create(target=target, backend=backend)
        self.create("production", role="production")
        before = (self.app / ".oci-kit/environments/production/environment.json").read_bytes()
        with self.assertRaises(ValueError):
            env.configure(self.app, name="production", target=target)
        production = {"compartment_id": "ocid1.compartment.oc1..production"}
        for collision in (backend, dict(backend, workspace_key_prefix="other/workspaces"),
                          dict(backend, key="production/state.tfstate"),
                          dict(backend, key="rehearsal/workspaces/nested.tfstate", workspace_key_prefix="elsewhere")):
            with self.subTest(backend=collision), self.assertRaises(ValueError):
                env.configure(self.app, name="production", target=production, backend=collision)
        self.assertEqual(before, (self.app / ".oci-kit/environments/production/environment.json").read_bytes())
        distinct = dict(backend, key="production/state.tfstate", workspace_key_prefix="production/workspaces")
        self.assertTrue(env.configure(self.app, name="production", target=production, backend=distinct)["backend_configured"])
        env.configure(self.app, name="production", target=dict(production, region="us-phoenix-1"))
        with p.Store(self.app, environment="production") as store:
            self.assertEqual(store.environment_config["backend"], distinct)

    def test_backend_import_keeps_only_destination_and_legacy_config_remains_readable(self):
        backend = {"region": "us-phoenix-1", "namespace": "synthetic", "bucket": "state-fixture",
                   "key": "rehearsal/state.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        path = self.app / ".oci-kit/backend.json"
        path.write_text(json.dumps(dict(backend, auth="SecurityToken", config_file_profile="example-session")))
        path.chmod(0o600)
        self.assertEqual(env.read_backend(path), backend)
        self.create()
        with p.Store(self.app, environment="rehearsal") as store:
            legacy = dict(store.environment_config)
            legacy.pop("backend")
            env.validate(legacy)
        with self.assertRaises(ValueError):
            self.create("source", role="source", infrastructure=None, backend=backend)

    def test_infrastructure_alias_and_internal_backend_overlap_refused(self):
        self.create()
        with self.assertRaises(ValueError):
            self.create("production", infrastructure="Deploy/Rehearsal")
        with self.assertRaises(ValueError):
            self.create("production", backend={"region": "us-phoenix-1", "namespace": "synthetic", "bucket": "state-fixture",
                                              "key": "workspaces/state.tfstate", "workspace_key_prefix": "workspaces"})


if __name__ == "__main__":
    unittest.main()
