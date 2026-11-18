"""First-run onboarding preserves apps and reaches the existing environment workflow."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("test_onboarding_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


kit, onboard, p, env = (load(name) for name in ("kit", "onboarding", "project", "environments"))


class Onboarding(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.parent = Path(tmp.name)
        self.app = self.parent / "application"; self.app.mkdir()
        (self.app / "app.py").write_text("raise RuntimeError('application must never execute during onboarding')\n")
        (self.app / "AGENTS.md").write_text("Preserve my application and services.\n")
        (self.app / ".env").write_text("PRIVATE_SYNTHETIC_APP_VALUE=do-not-export\n")
        self.config = self.parent / "missing-config"

    def command(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = kit.main(["onboard", *args, "--project", str(self.app), "--json", "--non-interactive"])
        return code, json.loads(output.getvalue())

    def snapshot(self):
        return {str(f.relative_to(self.app)): f.read_bytes() for f in self.app.rglob("*") if f.is_file()}

    def prepare(self, *extra):
        code, value = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal", *extra)
        self.assertEqual(code, 0, value)
        return value

    def test_fresh_inspection_without_tools_or_config_writes_nothing(self):
        before = self.snapshot()
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("No executable probes or cloud calls")):
            result = onboard.inspect(self.app, config_file=self.config, which=lambda _: None)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(result["installation"], "absent")
        self.assertEqual(result["authentication"]["status"], "not_selected")
        self.assertEqual(result["tools"]["oci"], "missing")
        self.assertEqual(result["cloud"], "not_checked")
        self.assertFalse(result["approval_granted"])
        self.assertTrue({"environment", "role", "profile", "auth", "region"}.issubset(result["missing"]))
        self.assertNotIn("PRIVATE_SYNTHETIC_APP_VALUE", json.dumps(result))
        self.assertTrue(Path(result["next_action"]["command"][1]).is_file())

    def test_prepare_requires_explicit_environment_and_role_before_writes(self):
        before = self.snapshot()
        for args in (("prepare",), ("prepare", "--environment", "rehearsal")):
            code, value = self.command(*args)
            self.assertEqual(code, 3)
            self.assertEqual(value["error"]["code"], "INPUTS_REQUIRED")
            self.assertEqual(before, self.snapshot())

    def test_dry_run_and_prepare_preserve_application_and_bind_correct_root(self):
        before = self.snapshot()
        result = self.prepare("--dry-run", "--stack", "fastapi")
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(before, self.snapshot())
        self.prepare("--stack", "fastapi")
        for name, raw in before.items():
            self.assertEqual((self.app / name).read_bytes(), raw)
        configs = load("kit_common").configurations(self.app)
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["infrastructure"], "deploy/rehearsal/terraform")
        self.assertEqual(configs[0]["target"], {})
        self.assertTrue((self.app / configs[0]["infrastructure"] / "container.tf").is_file())
        self.assertEqual((self.app / ".oci-kit/environments/rehearsal/environment.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((self.app / ".oci-kit/environments/rehearsal/state.json").read_text())["records"], {})

    def test_repeat_prepare_is_unchanged_and_preserves_saved_choices(self):
        self.prepare("--stack", "nextjs", "--agent", "codex")
        before = self.snapshot()
        result = self.prepare()
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(before, self.snapshot())
        self.assertFalse(result["approval_granted"])

    def test_can_add_rehearsal_without_selecting_existing_production(self):
        code, value = self.command("prepare", "--environment", "production", "--role", "production")
        self.assertEqual(code, 0, value)
        production = (self.app / ".oci-kit/environments/production/environment.json").read_bytes()
        self.prepare()
        self.assertEqual(production, (self.app / ".oci-kit/environments/production/environment.json").read_bytes())
        report = onboard.inspect(self.app, config_file=self.config)
        self.assertIsNone(report["environment"])
        self.assertEqual(report["next_action"]["phase"], "environment")

    def test_existing_source_directory_or_symlink_is_never_adopted(self):
        directory = self.app / "deploy/rehearsal"; directory.mkdir(parents=True)
        (directory / "private.txt").write_text("do not touch")
        before = self.snapshot()
        code, value = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ONBOARD_DESTINATION_EXISTS")
        self.assertEqual(before, self.snapshot())
        (directory / "private.txt").unlink(); directory.rmdir()
        directory.symlink_to(self.parent)
        code, value = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal")
        self.assertEqual(code, 3)
        self.assertFalse((self.app / ".oci-founder-kit").exists())

    def test_interrupted_attachment_does_not_create_environment_or_overwrite(self):
        self.prepare()
        partial = self.app / "deploy/second"; partial.mkdir()
        (partial / "partial.txt").write_text("retained")
        before = self.snapshot()
        code, value = self.command("prepare", "--environment", "second", "--role", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ONBOARD_DESTINATION_EXISTS")
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.app / ".oci-kit/environments/second").exists())

    def test_mismatched_project_or_environment_choices_are_not_overwritten(self):
        self.prepare("--stack", "nextjs")
        before = self.snapshot()
        for extra, expected in [(["--stack", "fastapi"], "ONBOARD_PROJECT_CONFLICT")]:
            code, value = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal", *extra)
            self.assertEqual(value["error"]["code"], expected)
            self.assertEqual(code, 3)
        code, value = self.command("prepare", "--environment", "rehearsal", "--role", "production")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ONBOARD_TARGET_CONFLICT")
        self.assertEqual(before, self.snapshot())

    def test_private_target_is_bound_but_never_echoed(self):
        target = self.parent / "target.json"
        target.write_text(json.dumps({"profile": "FOUNDER", "auth": "security_token", "region": "us-ashburn-1",
                                     "compartment_id": "ocid1.compartment.oc1..syntheticprivate"}))
        target.chmod(0o600)
        result = self.prepare("--target-file", str(target))
        self.assertNotIn("syntheticprivate", json.dumps(result))
        stored = json.loads((self.app / ".oci-kit/environments/rehearsal/environment.json").read_text())
        self.assertEqual(stored["target"], json.loads(target.read_text()))
        report = onboard.inspect(self.app, environment="rehearsal", config_file=self.config)
        self.assertNotIn("syntheticprivate", json.dumps(report))
        code, value = self.command("inspect", "--environment", "rehearsal", "--profile", "WRONG")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ONBOARD_TARGET_CONFLICT")

    def test_profile_metadata_inspection_never_reads_key_or_token(self):
        key, token = self.parent / "key", self.parent / "token"
        for file in (key, token):
            file.write_text("PRIVATE_SYNTHETIC_CREDENTIAL"); file.chmod(0o600)
        self.config.write_text(f"[FOUNDER]\ntenancy=ocid1.tenancy.oc1..synthetic\nuser=ocid1.user.oc1..synthetic\nfingerprint=synthetic\nkey_file={key}\nsecurity_token_file={token}\nregion=us-ashburn-1\n")
        self.config.chmod(0o600)
        original = os.open
        def guarded(path, *args, **kwargs):
            self.assertNotIn(str(path), (str(key), str(token)))
            return original(path, *args, **kwargs)
        with mock.patch.object(os, "open", side_effect=guarded), mock.patch.object(subprocess, "run", side_effect=AssertionError("No commands")):
            report = onboard.inspect(self.app, config_file=self.config, profile="FOUNDER", auth="security_token", region="us-ashburn-1")
        self.assertEqual(report["authentication"]["status"], "configured")
        self.assertEqual(report["authentication"]["session_expiry"], "not_checked")
        for private in ("PRIVATE_SYNTHETIC_CREDENTIAL", "ocid1.", str(key), str(token)):
            self.assertNotIn(private, json.dumps(report))

    def test_unknown_environment_and_unsafe_arguments_never_echo_input(self):
        self.prepare()
        code, value = self.command("inspect", "--environment", "absent")
        self.assertEqual(value["error"]["code"], "ENVIRONMENT_UNKNOWN")
        for extra in (["--profile", "private\nvalue"], ["--target-file", "/private/secret"], ["--live"]):
            code, value = self.command("inspect", *extra)
            self.assertEqual(code, 3)
            self.assertNotIn("private\\nvalue", json.dumps(value))
            self.assertNotIn("/private/secret", json.dumps(value))

    def test_new_app_and_installed_command_work_without_oci_credentials(self):
        self.app = self.parent / "new-app"
        self.prepare("--mode", "new", "--stack", "nextjs")
        result = subprocess.run([sys.executable, str(self.app / ".oci-founder-kit/scripts/kit.py"), "onboard", "inspect",
                                 "--project", str(self.app), "--environment", "rehearsal", "--config-file", str(self.config), "--json"],
                                capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["environment"], "rehearsal")
        self.assertEqual(value["cloud"], "not_checked")
        self.assertFalse(value["application_commands_run"])

    def test_returned_continuations_work_from_an_external_directory(self):
        before = self.snapshot()
        report = onboard.inspect(self.app, config_file=self.config)
        for expected in ("proposed", "prepared", "guidance"):
            argv = report["next_action"]["command"] + ["--json"]
            result = subprocess.run(argv, cwd=self.parent, capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], expected)
            self.assertFalse(report["approval_granted"])
            if expected == "proposed":
                self.assertEqual(before, self.snapshot())
        for name, raw in before.items():
            self.assertEqual((self.app / name).read_bytes(), raw)

    def test_source_environment_is_not_sent_to_cloud_foundation(self):
        self.prepare()
        env.create(self.app, name="source", role="source")
        report = onboard.inspect(self.app, environment="source", config_file=self.config)
        self.assertEqual(report["next_action"]["phase"], "environment")
        self.assertNotIn("foundation", report["next_action"]["command"])
        self.assertEqual(report["environment"], "source")

    def test_existing_custom_infrastructure_does_not_validate_a_hypothetical_new_root(self):
        p.start(self.app)
        env.create(self.app, name="custom", role="rehearsal", infrastructure="infra/custom")
        env.create(self.app, name="another", role="production", infrastructure="deploy/custom/terraform")
        before = self.snapshot()
        code, report = self.command("prepare", "--environment", "custom", "--role", "rehearsal")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "unchanged")
        self.assertEqual(before, self.snapshot())

    def test_existing_agent_installation_is_preserved_and_missing_agents_are_not_claimed(self):
        load("install").install(self.app, "claude")
        before = self.snapshot()
        code, report = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal", "--agent", "both")
        self.assertEqual(code, 3)
        self.assertEqual(report["error"]["code"], "ONBOARD_UPDATE_REQUIRED")
        self.assertEqual(before, self.snapshot())
        self.prepare()
        with p.Store(self.app) as store:
            self.assertEqual(store.read()["agent"], "claude")
        self.assertFalse((self.app / ".agents").exists())

    def test_old_bundle_without_onboard_routes_to_update_instead_of_an_invalid_command(self):
        self.prepare()
        bundle = self.app / ".oci-founder-kit"
        manifest_path = bundle / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["files"]["scripts/onboarding.py"]
        (bundle / "scripts/onboarding.py").unlink()
        manifest_path.write_text(json.dumps(manifest))
        before = self.snapshot()
        report = onboard.inspect(self.app, environment="rehearsal", config_file=self.config)
        self.assertEqual(report["next_action"]["phase"], "installation")
        self.assertNotIn("onboard", report["next_action"]["command"])
        result = subprocess.run(report["next_action"]["command"], cwd=self.parent,
                                capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())
        code, value = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ONBOARD_UPDATE_REQUIRED")

    def test_missing_agent_entry_does_not_return_successful_repeat_preparation(self):
        self.prepare()
        (self.app / ".agents/skills/oci-kit/SKILL.md").unlink()
        code, value = self.command("prepare", "--environment", "rehearsal", "--role", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(value["error"]["code"], "ONBOARD_UPDATE_REQUIRED")
        report = onboard.inspect(self.app, environment="rehearsal", config_file=self.config)
        self.assertEqual(report["next_action"]["phase"], "installation")

    def test_saving_access_choices_preserves_target_and_creates_private_backup(self):
        self.prepare()
        target = {"port": 3000, "health_path": "/health", "image_digest": "sha256:" + "a" * 64}
        env.configure(self.app, name="rehearsal", target=target)
        directory = self.app / ".oci-kit/environments/rehearsal"
        before = (directory / "environment.json").read_bytes()
        code, report = self.command("configure", "--environment", "rehearsal", "--profile", "FOUNDER",
                                    "--region", "us-ashburn-1", "--auth", "security_token", "--config-file", str(self.config))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "configured")
        self.assertEqual(report["previous_evidence"], "stale")
        self.assertFalse(report["approval_granted"])
        stored = json.loads((directory / "environment.json").read_text())["target"]
        self.assertEqual(stored, dict(target, profile="FOUNDER", region="us-ashburn-1", auth="security_token"))
        backups = list(directory.glob("environment-backup-*.json"))
        self.assertTrue(any(f.read_bytes() == before for f in backups))
        self.assertTrue(all(f.stat().st_mode & 0o777 == 0o600 for f in backups))
        self.assertIn(str(self.config), report["next_action"]["command"])

    def test_access_configuration_requires_all_choices_and_never_retargets_bound_resources(self):
        self.prepare()
        before = self.snapshot()
        code, result = self.command("configure", "--environment", "rehearsal")
        self.assertEqual(code, 3)
        self.assertEqual(result["error"]["missing"], ["auth", "profile", "region"])
        self.assertEqual(before, self.snapshot())
        env.configure(self.app, name="rehearsal", target={"profile": "FOUNDER", "region": "us-ashburn-1", "auth": "security_token",
                       "compartment_id": "ocid1.compartment.oc1..synthetic"})
        before = self.snapshot()
        code, result = self.command("configure", "--environment", "rehearsal", "--profile", "ANOTHER",
                                    "--region", "us-phoenix-1", "--auth", "api_key")
        self.assertEqual(code, 3)
        self.assertEqual(result["error"]["code"], "ONBOARD_TARGET_CONFLICT")
        self.assertEqual(before, self.snapshot())

    def test_inspected_access_choices_flow_to_the_returned_configuration_command(self):
        self.prepare()
        for name in ("session-key", "session-token"):
            file = self.parent / name; file.write_text("synthetic-offline-only"); file.chmod(0o600)
        self.config.write_text(f"[FOUNDER]\ntenancy=ocid1.tenancy.oc1..synthetic\nkey_file={self.parent / 'session-key'}\nsecurity_token_file={self.parent / 'session-token'}\n")
        self.config.chmod(0o600)
        before = (self.app / ".oci-kit/environments/rehearsal/environment.json").read_bytes()
        report = onboard.inspect(self.app, environment="rehearsal", profile="FOUNDER", auth="security_token",
                                 region="us-ashburn-1", config_file=self.config, which=lambda _: "/synthetic/tool")
        self.assertEqual(report["next_action"]["phase"], "configuration")
        self.assertEqual(before, (self.app / ".oci-kit/environments/rehearsal/environment.json").read_bytes())
        result = subprocess.run(report["next_action"]["command"] + ["--json"], cwd=self.parent,
                                capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        saved = json.loads((self.app / ".oci-kit/environments/rehearsal/environment.json").read_text())["target"]
        self.assertEqual(saved, {"profile": "FOUNDER", "region": "us-ashburn-1", "auth": "security_token"})
        report = onboard.inspect(self.app, environment="rehearsal", config_file=self.config, which=lambda _: "/synthetic/tool")
        self.assertEqual(report["next_action"]["phase"], "administrator-bootstrap")
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["cloud"], "not_checked")

    def test_access_configuration_preserves_an_edit_after_initial_discovery(self):
        self.prepare()
        env.configure(self.app, name="rehearsal", target={"port": 3000, "health_path": "/health"})
        common = onboard.common_module()
        select = common.select
        def concurrent_edit(*args, **kwargs):
            selected = select(*args, **kwargs)
            env.configure(self.app, name="rehearsal", target={"port": 4000, "health_path": "/new-health"})
            return selected
        with mock.patch.object(common, "select", side_effect=concurrent_edit), mock.patch.object(onboard, "common_module", return_value=common):
            onboard.configure(self.app, environment="rehearsal", profile="FOUNDER", region="us-ashburn-1", auth="security_token")
        stored = load("kit_common").select(self.app, "rehearsal")["target"]
        self.assertEqual(stored["port"], 4000)
        self.assertEqual(stored["health_path"], "/new-health")
        self.assertEqual(stored["profile"], "FOUNDER")

    def test_access_configuration_refuses_an_edit_after_bound_snapshot(self):
        self.prepare()
        common = onboard.common_module(); project = common.project_module()
        helper = project.helper
        native = helper("environments")
        configure = native.configure
        def concurrent_write(*args, **kwargs):
            env.configure(self.app, name="rehearsal", target={"port": 4000, "health_path": "/new-health"})
            return configure(*args, **kwargs)
        def patched_helper(name):
            return native if name == "environments" else helper(name)
        with mock.patch.object(native, "configure", side_effect=concurrent_write), mock.patch.object(project, "helper", side_effect=patched_helper), \
                mock.patch.object(common, "project_module", return_value=project), mock.patch.object(onboard, "common_module", return_value=common):
            with self.assertRaises(ValueError):
                onboard.configure(self.app, environment="rehearsal", profile="FOUNDER", region="us-ashburn-1", auth="security_token")
        stored = load("kit_common").select(self.app, "rehearsal")["target"]
        self.assertEqual(stored, {"port": 4000, "health_path": "/new-health"})

    def test_access_shortcut_cannot_retarget_an_existing_state_backend(self):
        self.prepare()
        backend = {"region": "us-ashburn-1", "namespace": "synthetic", "bucket": "state-fixture",
                   "key": "rehearsal/state.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        env.configure(self.app, name="rehearsal", target={"profile": "FOUNDER", "auth": "security_token", "region": "us-ashburn-1"}, backend=backend)
        before = self.snapshot()
        code, result = self.command("configure", "--environment", "rehearsal", "--profile", "ANOTHER",
                                    "--region", "us-phoenix-1", "--auth", "security_token")
        self.assertEqual(code, 3)
        self.assertEqual(result["error"]["code"], "ONBOARD_TARGET_CONFLICT")
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
