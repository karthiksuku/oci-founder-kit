"""Backend approvals exercise fake clients only; never initialize OCI state."""
import json
import os
from pathlib import Path
from unittest import mock

import test_deploy_gate as fixtures
import backend_ops as ops


CONFIG = {"bucket": "fixture-state-bucket", "namespace": "fixture_namespace", "region": "ap-melbourne-1",
          "key": "fixture/app.tfstate", "workspace_key_prefix": "fixture/unused-workspaces",
          "auth": "APIKey", "config_file_profile": "DEFAULT"}


class BackendOperations(fixtures.GateTestCase):
    def setUp(self):
        super().setUp()
        (self.stack / "backend.tf.json").write_text(json.dumps(ops.DECLARATION))
        self.config = self.tmp / "backend.tfbackend.json"
        self.config.write_text(json.dumps(CONFIG))
        self.config.chmod(0o600)

    def operation(self, kind="init", *extra):
        args = ["backend-plan", "--dir", str(self.stack), "--operation", kind]
        if kind == "init":
            args += ["--backend-config", str(self.config)]
        code, out, err = self.run_gate(*args, *extra)
        self.assertEqual(code, 0, err)
        return json.loads((self.gate_dir / ops.PLAN).read_text()), out

    def execute(self, digest):
        return self.run_gate("backend-run", "--dir", str(self.stack), "--approve", digest)

    def initialize(self):
        envelope, _ = self.operation()
        code, _, err = self.execute(envelope["sha256"])
        self.assertEqual(code, 0, err)
        return envelope

    def remote_plan(self, kind="plan", *extra):
        self.initialize()
        envelope, _ = self.operation(kind, *extra)
        code, _, err = self.execute(envelope["sha256"])
        self.assertEqual(code, 0, err)
        return json.loads((self.gate_dir / "plan-summary.json").read_text()), envelope

    def receipt(self, digest):
        return json.loads((self.gate_dir / "backend-receipts" / (digest + ".json")).read_text())

    def test_preparation_is_offline_and_describes_exact_object_scope(self):
        envelope, out = self.operation()
        self.assertFalse(self.log.exists())
        self.assertFalse((self.stack / ".terraform").exists())
        self.assertEqual(envelope["payload"]["backend"], CONFIG)
        self.assertIn(CONFIG["key"] + ".lock", out)
        self.assertIn("No resource apply", out)

    def test_initialization_consumes_approval_and_checks_destination(self):
        envelope = self.initialize()
        self.assertFalse((self.gate_dir / ops.PLAN).exists())
        receipt = self.receipt(envelope["sha256"])
        self.assertEqual(receipt["status"], "completed")
        self.assertFalse(receipt["resource_apply_authorized"])
        before = self.log.read_text()
        self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)

    def test_failed_init_is_consumed_and_records_uncertainty(self):
        envelope, _ = self.operation()
        with mock.patch.dict(os.environ, {"FAKE_TF_FAIL": "init"}):
            code, _, err = self.execute(envelope["sha256"])
        self.assertEqual(code, 1, err)
        self.assertFalse((self.gate_dir / ops.PLAN).exists())
        receipt = self.receipt(envelope["sha256"])
        self.assertEqual(receipt["status"], "failed")
        self.assertTrue(receipt["remote_objects_may_have_changed"])

    def test_wrong_initialized_destination_is_failure_not_success(self):
        envelope, _ = self.operation()
        with mock.patch.dict(os.environ, {"FAKE_TF_WRONG_BACKEND": "1"}):
            self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertEqual(self.receipt(envelope["sha256"])["status"], "failed")

    def test_wrong_hash_and_expiry_refuse_before_any_client(self):
        envelope, _ = self.operation()
        self.assertEqual(self.execute("0" * 64)[0], 3)
        self.assertFalse(self.log.exists())
        envelope["payload"]["created_at_epoch"] -= 10000
        envelope["payload"]["expires_at_epoch"] -= 10000
        envelope["sha256"] = ops.files.sha(ops.files.canonical(envelope["payload"]))
        (self.gate_dir / ops.PLAN).write_text(json.dumps(envelope))
        self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertFalse(self.log.exists())

    def test_source_and_config_changes_refuse_before_any_client(self):
        envelope, _ = self.operation()
        (self.stack / "main.tf").write_text("# changed after review\n")
        self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertFalse(self.log.exists())
        envelope, _ = self.operation()
        self.config.write_text(json.dumps({**CONFIG, "key": "other/state.tfstate"}))
        self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertFalse(self.log.exists())

    def test_gate_source_or_binary_change_requires_new_approval(self):
        envelope, _ = self.operation()
        with mock.patch.object(ops, "source_binding", return_value={"changed": "fixture"}):
            self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertFalse(self.log.exists())

    def test_no_implicit_migration_or_reconfiguration(self):
        (self.stack / "terraform.tfstate").write_text('{"resources":[]}')
        code, _, _ = self.run_gate("backend-plan", "--dir", str(self.stack), "--operation", "init",
                                    "--backend-config", str(self.config))
        self.assertEqual(code, 3)
        self.assertFalse(self.log.exists())
        (self.stack / "terraform.tfstate").unlink()
        self.initialize()
        self.config.write_text(json.dumps({**CONFIG, "bucket": "other-bucket"}))
        code, _, _ = self.run_gate("backend-plan", "--dir", str(self.stack), "--operation", "init",
                                    "--backend-config", str(self.config))
        self.assertEqual(code, 3)

    def test_inline_settings_and_extra_declarations_are_rejected(self):
        for source in ("terraform { backend oci {} }", 'terraform { backend "http" {} }'):
            with self.subTest(source=source):
                (self.stack / "override.tf").write_text(source)
                code, _, _ = self.run_gate("backend-plan", "--dir", str(self.stack), "--operation", "init",
                                            "--backend-config", str(self.config))
                self.assertEqual(code, 3)
                self.assertFalse(self.log.exists())

    def test_backend_credentials_and_environment_overrides_are_not_printed(self):
        sensitive = "synthetic-sensitive-value"
        self.config.write_text(json.dumps({**CONFIG, "private_key": sensitive}))
        code, out, err = self.run_gate("backend-plan", "--dir", str(self.stack), "--operation", "init",
                                        "--backend-config", str(self.config))
        self.assertEqual(code, 3)
        self.assertNotIn(sensitive, out + err)
        self.config.write_text(json.dumps(CONFIG))
        with mock.patch.dict(os.environ, {"OCI_AUTH": sensitive}):
            code, out, err = self.run_gate("backend-plan", "--dir", str(self.stack), "--operation", "init",
                                            "--backend-config", str(self.config))
        self.assertEqual(code, 3)
        self.assertNotIn(sensitive, out + err)
        self.assertFalse(self.log.exists())

    def test_remote_plan_needs_its_own_operation_approval_and_apply_approval(self):
        summary, envelope = self.remote_plan()
        self.assertEqual(summary["backend"], CONFIG)
        self.assertEqual(summary["backend_operation_sha256"], envelope["sha256"])
        self.assertEqual(self.applied(), [])
        # Approved planning does not repeat init and does not approve apply.
        lines = self.log.read_text().splitlines()
        self.assertEqual(len([line for line in lines if line.startswith("init ")]), 1)
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.applied()), 1)

    def test_changed_metadata_cannot_redirect_resource_apply(self):
        summary, _ = self.remote_plan()
        path = self.stack / ".terraform/terraform.tfstate"
        metadata = json.loads(path.read_text())
        metadata["backend"]["config"]["key"] = "other/app.tfstate"
        path.write_text(json.dumps(metadata))
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        self.assertEqual(self.applied(), [])

    def test_apply_rechecks_environment_and_does_not_log_secrets(self):
        summary, _ = self.remote_plan()
        for name in ("TF_LOG", "TF_LOG_CORE", "TF_LOG_PROVIDER", "OCI_CONFIG_FILE", "TF_CLI_CONFIG_FILE", "TF_VAR_new"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: "synthetic-private-value"}):
                code, out, err = self.apply(summary["plan_sha256"])
                self.assertEqual(code, 3)
                self.assertNotIn("synthetic-private-value", out + err)
                self.assertEqual(self.applied(), [])

    def test_private_variable_files_are_bound_to_operation(self):
        self.initialize()
        var_file = self.stack / "production.tfvars"
        var_file.write_text('name = "fixture"\n')
        var_file.chmod(0o600)
        envelope, _ = self.operation("plan", "--var-file", var_file.name, "--target", "oci_core_vcn.main")
        before = self.log.read_text()
        var_file.write_text('name = "changed"\n')
        self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)

    def test_destroy_plan_is_separate_and_retains_no_apply_permission(self):
        self.write_json("plan.json", fixtures.DESTROY_PLAN)
        summary, envelope = self.remote_plan("destroy-plan")
        self.assertEqual(summary["kind"], "destroy")
        self.assertEqual(self.receipt(envelope["sha256"])["status"], "completed")
        self.assertEqual(self.applied(), [])

    def test_explicit_resource_targets_are_passed_and_recorded(self):
        summary, _ = self.remote_plan("plan", "--target", "oci_core_vcn.main")
        self.assertEqual(summary["resource_targets"], ["oci_core_vcn.main"])
        self.assertIn("-target=oci_core_vcn.main", self.log.read_text())

    def test_targeted_destroy_and_invalid_target_syntax(self):
        self.initialize()
        before = self.log.read_text()
        for target in ("module.whole", "-destroy", "oci_core_vcn.*", "data.oci_core_vcn.main"):
            with self.subTest(target=target):
                code, _, _ = self.run_gate("backend-plan", "--dir", str(self.stack),
                                            "--operation", "destroy-plan", "--target=" + target)
                self.assertEqual(code, 3)
        self.assertEqual(self.log.read_text(), before)

    def test_legacy_resource_plan_is_refused_even_after_remote_source_removed(self):
        summary, _ = self.remote_plan()
        summary.pop("backend_binding")
        summary.pop("backend_environment_sha256")
        (self.gate_dir / "plan-summary.json").write_text(json.dumps(summary))
        (self.stack / "backend.tf.json").unlink()
        (self.stack / ".terraform/terraform.tfstate").unlink()
        before = self.log.read_text()
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)

    def test_expiry_during_backend_validation_prevents_client_start(self):
        envelope, _ = self.operation()
        now = envelope["payload"]["created_at_epoch"]
        source = ops.source_binding
        with mock.patch.object(ops.time, "time", return_value=now) as clock:
            def delayed_source():
                clock.return_value = envelope["payload"]["expires_at_epoch"] + 1
                return source()
            with mock.patch.object(ops, "source_binding", side_effect=delayed_source):
                self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertFalse(self.log.exists())

    def test_expiry_during_resource_plan_setup_prevents_backend_lock(self):
        self.initialize()
        envelope, _ = self.operation("plan")
        before = self.log.read_text()
        now = envelope["payload"]["created_at_epoch"]
        with mock.patch.object(ops.time, "time", return_value=now) as clock:
            def delayed_check(*args):
                clock.return_value = envelope["payload"]["expires_at_epoch"] + 1
            with mock.patch.object(fixtures.gate, "require_backend", side_effect=delayed_check):
                self.assertEqual(self.execute(envelope["sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)
        self.assertEqual(self.receipt(envelope["sha256"])["status"], "failed")
