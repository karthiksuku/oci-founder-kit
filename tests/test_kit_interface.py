"""The lifecycle facade must preserve explicit selection and redact input errors."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("test_facade_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


p, env, kit = load("project"), load("environments"), load("kit")


class Interface(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.app = Path(temp.name) / "app"; self.app.mkdir()
        (self.app / "main.py").write_text("raise RuntimeError('never execute application during continuation')\n")
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both", "stack": "custom", "blueprint": None,
                "project_identity": p.identity(store.root_fd), "created_at": now, "observed_at": now,
                "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint(), "records": {}})
        env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal")
        env.create(self.app, name="production", role="production", infrastructure="deploy/production")

    def command(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = kit.main([*args, "--project", str(self.app), "--json", "--non-interactive"])
        return code, json.loads(output.getvalue())

    def test_mixed_records_cannot_fall_back_to_legacy(self):
        for command in ("status", "next", "start"):
            code, value = self.command(command)
            self.assertEqual(code, 3)
            self.assertEqual(value["error"]["code"], "ENVIRONMENT_REQUIRED")

    def test_continuation_keeps_selected_environment_and_source(self):
        before = (self.app / "main.py").read_bytes()
        code, value = self.command("next", "--environment", "rehearsal")
        self.assertEqual(code, 0)
        self.assertEqual(value["environment"], "rehearsal")
        self.assertEqual(value["continuation_command"][-2:], ["--environment", "rehearsal"])
        self.assertEqual(before, (self.app / "main.py").read_bytes())

    def test_wrong_environment_is_not_created_or_selected(self):
        code, value = self.command("doctor", "--environment", "missing")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ENVIRONMENT_UNKNOWN")

    def test_missing_nonsecret_choices_are_returned_together(self):
        code, value = self.command("environment", "create")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["missing"], ["environment", "infrastructure", "role"])
        self.assertFalse(value["approval_granted"])

    def test_invalid_input_and_exception_values_are_never_echoed(self):
        code, value = self.command("status", "--accidental-secret", "synthetic-sensitive-marker")
        self.assertEqual(code, 3)
        self.assertNotIn("synthetic-sensitive-marker", json.dumps(value))

    def test_apply_without_exact_hash_does_not_execute_gate(self):
        code, value = self.command("release", "apply", "--environment", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "APPROVAL_REQUIRED")
        self.assertFalse((self.app / "deploy/rehearsal").exists())

    def test_registry_snippets_parse_using_same_interface(self):
        for row in load("capabilities").registry()["capabilities"]:
            with self.subTest(capability=row["id"]):
                parsed = kit.parser().parse_args(row["command"])
                self.assertTrue(parsed.command)

    def test_packaging_requires_environment_and_batches_descriptor_choices(self):
        code, value = self.command("package", "inspect")
        self.assertEqual(value["error"]["code"], "ENVIRONMENT_REQUIRED")
        code, value = self.command("package", "inspect", "--environment", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "PACKAGE_DESCRIPTOR_REQUIRED")
        self.assertTrue({"app_directory", "commands", "dependencies", "background_work", "probe_runtime"}.issubset(value["error"]["missing"]))

    def test_known_error_recovery_is_fixed_not_exception_content(self):
        class UntrustedError(ValueError):
            code = "PACKAGE_STALE_PROPOSAL"
            recovery = "synthetic-private-canary"
        with mock.patch.object(kit, "dispatch", side_effect=UntrustedError("synthetic-private-canary")):
            code, value = self.command("package", "apply", "--environment", "rehearsal")
        self.assertEqual(value["error"]["code"], "PACKAGE_STALE_PROPOSAL")
        self.assertEqual(value["error"]["owner"], "owner")
        self.assertNotIn("synthetic-private-canary", json.dumps(value))

    def test_blocked_findings_are_projected_to_reviewed_codes_only(self):
        with mock.patch.object(kit, "dispatch", return_value={"status": "blocked", "findings": [
                {"code": "PACKAGE_STANDALONE_REQUIRED", "input": "synthetic-private-path"}], "missing": []}):
            code, value = self.command("package", "propose", "--environment", "rehearsal")
        self.assertEqual(value["error"]["code"], "PACKAGE_STANDALONE_REQUIRED")
        self.assertNotIn("synthetic-private-path", json.dumps(value))

    def test_support_export_contains_no_project_or_environment_names(self):
        code, value = self.command("support", "export", "--environment", "rehearsal", "--write")
        self.assertEqual(code, 0)
        raw = (self.app / value["path"]).read_bytes()
        for forbidden in (b"rehearsal", str(self.app).encode(), b"main.py", b"source_sha256", b"ocid1."):
            self.assertNotIn(forbidden, raw)
        self.assertFalse(json.loads(raw)["uploaded"])

    def test_backend_init_cannot_return_a_stale_resource_plan(self):
        common = load("kit_common")
        stack = self.app / "deploy/rehearsal"; gate_dir = stack / ".gate"; gate_dir.mkdir(parents=True)
        (gate_dir / "backend-receipts").mkdir()
        digest = "a" * 64; binding = {"environment": "rehearsal", "component_role": "web"}
        def private(path, value):
            path.write_text(json.dumps(value)); path.chmod(0o600)
        private(gate_dir / "backend-plan.json", {"sha256": digest, "payload": {"operation": "init", "project_environment": binding}})
        private(gate_dir / "plan-summary.json", {"plan_sha256": "b" * 64})
        selected = {"schema": "oci-kit-environment/1", "name": "rehearsal", "role": "rehearsal", "blueprint": "web-container",
                    "infrastructure": "deploy/rehearsal", "backend": {"bucket": "synthetic"},
                    "target": {"profile": "DEFAULT", "auth": "api_key"}}
        def main(arguments):
            private(gate_dir / "backend-receipts" / (digest + ".json"), {
                "schema": "oci-backend-receipt/1", "status": "completed", "operation": "init", "operation_sha256": digest,
                "project_environment": binding, "resource_apply_authorized": False})
            return 0
        readiness = SimpleNamespace(load=lambda path: SimpleNamespace(select=lambda *a, **k: binding) if path.endswith("environment_gate.py") else SimpleNamespace(main=main))
        facade_p = mock.Mock(wraps=p)
        facade_p.helper.side_effect = lambda name: readiness if name == "readiness" else p.helper(name)
        args = kit.parser().parse_args(["release", "run", "--project", str(self.app), "--environment", "rehearsal", "--approve", digest])
        result = kit.gate_request(facade_p, common, args, selected)
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("plan_sha256", result)
        self.assertIn("Initialization completed", result["next_action"])

    def test_release_operation_refuses_cross_environment_backend_approval(self):
        common = load("kit_common")
        stack = self.app / "deploy/rehearsal"; gate_dir = stack / ".gate"; gate_dir.mkdir(parents=True)
        digest = "a" * 64
        path = gate_dir / "backend-plan.json"
        path.write_text(json.dumps({"sha256": digest, "payload": {"operation": "plan", "project_environment": {"environment": "production"}}})); path.chmod(0o600)
        selected = {"schema": "oci-kit-environment/1", "name": "rehearsal", "role": "rehearsal", "blueprint": "web-container",
                    "infrastructure": "deploy/rehearsal", "backend": {"bucket": "synthetic"}, "target": {"profile": "DEFAULT", "auth": "api_key"}}
        gate = SimpleNamespace(select=lambda *a, **k: {"environment": "rehearsal"})
        readiness = mock.Mock(); readiness.load.return_value = gate
        facade_p = mock.Mock(wraps=p); facade_p.helper.side_effect = lambda name: readiness if name == "readiness" else p.helper(name)
        args = kit.parser().parse_args(["release", "run", "--project", str(self.app), "--environment", "rehearsal", "--approve", digest])
        with self.assertRaises(common.KitError):
            kit.gate_request(facade_p, common, args, selected)
        self.assertEqual(readiness.load.call_count, 1)


if __name__ == "__main__":
    unittest.main()
