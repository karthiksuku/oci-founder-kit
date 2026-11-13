"""Private local preview configuration and safe Compose command boundaries."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints" / "fullstack-container"
spec = importlib.util.spec_from_file_location("local_preview", BLUEPRINT / "local_preview.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class LocalPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="preview-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copyfile(BLUEPRINT / "compose.local.yaml", self.root / "compose.local.yaml")
        self.calls = []
        self.config = {"services": {
            "app": {"environment": {"APP_MODE": "sandbox", "OCI_BUCKET": "", "OCI_NAMESPACE": ""},
                    "ports": [{"host_ip": "127.0.0.1", "published": "8080", "target": 8080}]},
            "db": {"ports": []}}}

    def fake(self, argv, environment, private, timeout=60):
        self.calls.append((argv, environment.copy()))
        if argv[1:3] == ["context", "inspect"]:
            return '"unix:///var/run/docker.sock"'
        if "info" in argv:
            return '"29.1.3"'
        if argv[-2:] == ["up", "--help"]:
            return "--wait --wait-timeout"
        if argv[-2:] == ["build", "--help"]:
            return "--builder"
        if argv[-3:] == ["config", "--format", "json"]:
            return json.dumps(self.config)
        if "port" in argv:
            return "127.0.0.1:8080\n"
        if "ps" in argv:
            return json.dumps([{"Service": "app", "State": "running", "Health": "healthy"},
                               {"Service": "db", "State": "running", "Health": "healthy"}])
        return ""

    def command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(preview, "BASE", self.root), mock.patch.object(preview, "call", side_effect=self.fake), \
                mock.patch.object(preview.shutil, "which", return_value="/usr/bin/docker"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = preview.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_start_generates_private_stable_password_and_loopback_url(self):
        code, out, err = self.command("start")
        self.assertEqual(code, 0, err)
        self.assertIn("http://127.0.0.1:8080", out)
        self.assertIn("attachments", out.lower())
        folder = self.root / ".local-preview"
        settings = json.loads((folder / "settings.json").read_text())
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder / "settings.json").stat().st_mode), 0o600)
        self.assertNotIn(settings["password"], out + err)
        self.assertTrue(all(settings["password"] not in " ".join(argv) for argv, _ in self.calls))
        self.assertEqual(self.command("start")[0], 0)
        self.assertEqual(json.loads((folder / "settings.json").read_text()), settings)

    def test_stop_preserves_volume_settings_and_scope(self):
        self.assertEqual(self.command("start")[0], 0)
        path = self.root / ".local-preview" / "settings.json"
        original = path.read_bytes()
        code, out, err = self.command("stop")
        self.assertEqual(code, 0, err)
        self.assertIn("retained", out)
        command = self.calls[-1][0]
        self.assertIn("down", command)
        self.assertNotIn("--volumes", command)
        self.assertNotIn("--remove-orphans", command)
        self.assertNotIn("prune", command)
        self.assertIn("--project-name", command)
        self.assertEqual(path.read_bytes(), original)

    def test_empty_status_does_not_claim_data_or_volume_exists(self):
        self.assertEqual(self.command("start")[0], 0)
        original = self.fake
        def no_containers(argv, *args, **kwargs):
            return "[]" if "ps" in argv else original(argv, *args, **kwargs)
        self.fake = no_containers
        code, out, err = self.command("status")
        self.assertEqual(code, 0, err)
        self.assertIn("Database volume has not been checked", out)
        self.assertNotIn("stored tasks", out)

    def test_status_and_stop_before_start_do_not_create_settings(self):
        self.assertEqual(self.command("status")[0], 0)
        self.assertEqual(self.command("stop")[0], 0)
        self.assertFalse((self.root / ".local-preview").exists())
        self.assertEqual(self.calls, [])

    def test_remote_docker_endpoint_and_old_daemon_refuse(self):
        with mock.patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote.invalid:2376"}):
            self.assertNotEqual(self.command("start")[0], 0)
        original = self.fake
        def old(argv, *args, **kwargs):
            return '"27.0.0"' if "info" in argv else original(argv, *args, **kwargs)
        self.fake = old
        self.assertNotEqual(self.command("start")[0], 0)
        self.assertFalse(any("--wait" in argv for argv, _ in self.calls))

    def test_inherited_compose_and_preview_overrides_are_removed(self):
        with mock.patch.dict(os.environ, {"COMPOSE_FILE": "/untrusted.yml", "COMPOSE_PROJECT_NAME": "other-project",
                                          "PREVIEW_DB_PASSWORD": "untrusted-password", "PREVIEW_PORT": "9999"}):
            self.assertEqual(self.command("start")[0], 0)
        for argv, env in self.calls:
            self.assertNotIn("COMPOSE_FILE", env)
            self.assertNotIn("COMPOSE_PROJECT_NAME", env)
            if "up" in argv and "--wait" in argv:
                self.assertNotEqual(env["PREVIEW_DB_PASSWORD"], "untrusted-password")
                self.assertEqual(env["PREVIEW_PORT"], "8080")

    def test_effective_local_context_is_pinned_for_all_later_commands(self):
        # After the first context read, a concurrent context switch must not
        # influence info/build/start/status/stop: they carry the checked host.
        with mock.patch.dict(os.environ, {"DOCKER_CONTEXT": "desktop-linux", "DOCKER_HOST": "tcp://ignored.invalid:2376"}):
            self.assertEqual(self.command("start")[0], 0)
        self.assertEqual(sum(argv[1:3] == ["context", "inspect"] for argv, _ in self.calls), 1)
        for argv, env in self.calls[1:]:
            self.assertEqual(argv[1:3], ["--host", "unix:///var/run/docker.sock"])
            self.assertNotIn("DOCKER_CONTEXT", env)
            self.assertNotIn("DOCKER_HOST", env)

    def test_explicit_local_host_takes_precedence_over_saved_context(self):
        with mock.patch.dict(os.environ, {"DOCKER_CONTEXT": "", "DOCKER_HOST": "unix:///tmp/rootless-preview.sock"}):
            self.assertEqual(self.command("start")[0], 0)
        self.assertFalse(any(argv[1:3] == ["context", "inspect"] for argv, _ in self.calls))
        self.assertTrue(all(argv[1:3] == ["--host", "unix:///tmp/rootless-preview.sock"] for argv, _ in self.calls))

    def test_remote_builder_and_source_policy_overrides_are_removed(self):
        with mock.patch.dict(os.environ, {"BUILDX_BUILDER": "remote", "BUILDX_CONFIG": "/untrusted",
                "BUILDKIT_HOST": "tcp://remote.invalid:1234", "COMPOSE_BAKE": "true",
                "EXPERIMENTAL_BUILDKIT_SOURCE_POLICY": "/untrusted/policy.json"}):
            self.assertEqual(self.command("start")[0], 0)
        builds = [argv for argv, _ in self.calls if "build" in argv and "--help" not in argv]
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0][-3:], ["build", "--builder", "default"])
        for _, env in self.calls:
            self.assertFalse(any(k.startswith(("BUILDX_", "BUILDKIT_", "BAKE_")) for k in env))
            self.assertNotIn("COMPOSE_BAKE", env)
            self.assertNotIn("EXPERIMENTAL_BUILDKIT_SOURCE_POLICY", env)

    def test_unsafe_effective_compose_config_refuses_before_start(self):
        for change in ("public-app", "published-db", "production", "cloud-storage"):
            with self.subTest(change=change):
                old = json.loads(json.dumps(self.config))
                if change == "public-app": self.config["services"]["app"]["ports"][0]["host_ip"] = "0.0.0.0"
                elif change == "published-db": self.config["services"]["db"]["ports"] = [{"target": 5432}]
                elif change == "production": self.config["services"]["app"]["environment"]["APP_MODE"] = "production"
                else: self.config["services"]["app"]["environment"]["OCI_BUCKET"] = "unexpected"
                self.calls.clear()
                self.assertNotEqual(self.command("start")[0], 0)
                self.assertFalse(any("--wait" in argv for argv, _ in self.calls))
                self.config = old

    def test_settings_symlink_hardlink_and_nonprivate_permissions_refuse(self):
        self.assertEqual(self.command("start")[0], 0)
        path = self.root / ".local-preview" / "settings.json"
        target = self.root / "preserve.json"
        target.write_bytes(path.read_bytes()); target.chmod(0o600)
        for kind in ("symlink", "hardlink", "public"):
            path.unlink()
            if kind == "symlink": path.symlink_to(target)
            elif kind == "hardlink": os.link(target, path)
            else: path.write_bytes(target.read_bytes()); path.chmod(0o644)
            self.assertNotEqual(self.command("start")[0], 0)

    def test_private_directory_symlink_refuses(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        (self.root / ".local-preview").symlink_to(elsewhere, target_is_directory=True)
        self.assertNotEqual(self.command("start")[0], 0)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_invalid_ports_subnets_and_tampered_identity_refuse(self):
        for args in (("--port", "80"), ("--port", "65536"), ("--subnet", "0.0.0.0/0"),
                     ("--subnet", "8.8.8.0/24"), ("--subnet", "172.16.0.1/28")):
            self.assertNotEqual(self.command("start", *args)[0], 0)
        self.assertEqual(self.command("start")[0], 0)
        path = self.root / ".local-preview" / "settings.json"
        settings = json.loads(path.read_text()); settings["project"] = "other-unowned-project"
        path.write_text(json.dumps(settings))
        self.assertNotEqual(self.command("stop")[0], 0)

    def test_lost_settings_do_not_regenerate_credentials(self):
        self.assertEqual(self.command("start")[0], 0)
        path = self.root / ".local-preview" / "settings.json"
        path.unlink()
        self.assertNotEqual(self.command("start")[0], 0)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
