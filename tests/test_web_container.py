"""Deployment attachment preserves existing app source and fails closed at filesystem boundaries."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


blueprint = module("web_blueprint", ROOT / "scripts/blueprint.py")
attach_module = module("web_attach", ROOT / "scripts/deployment_scaffold.py")
manifest = module("web_manifest", ROOT / "scripts/release_manifest.py")


def snapshot(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file() and not p.is_symlink()}


class WebContainerAttachment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="oci-kit-attach-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "kit"
        self.project = self.base / "existing app"
        (self.project / "src").mkdir(parents=True)
        (self.project / "src/app.py").write_text("# Existing owner application\n")
        (self.project / ".env").write_text("EXAMPLE=PRIVATE_TEST_SENTINEL\n")
        (self.project / "AGENTS.md").write_text("Owner rules remain unchanged.\n")
        # A coherent, minimal release fixture exercises the real integrity reader;
        # production attachment never bypasses a stale distribution manifest.
        names = ["LICENSE"] + ["scripts/" + name + ".py" for name in
                                  ("blueprint", "scaffold", "deployment_scaffold", "install", "release_manifest")]
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT / "blueprints/web-container").rglob("*")
                  if p.is_file() and ".terraform" not in p.parts and "__pycache__" not in p.parts]
        for name in names:
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        installer = module("web_fixture_install", self.source / "scripts/install.py")
        manifest.write(self.source, manifest.build(self.source, names, installer.distributable))

    def attach(self, directory="deploy/oci", dry_run=False):
        return attach_module.attach("web-container", self.project, directory, dry_run, root=self.source)

    def test_exports_deployment_only_preserving_app_and_agent_installation(self):
        before = snapshot(self.project)
        with mock.patch("subprocess.run", side_effect=AssertionError("No tools may run")):
            report = self.attach()
        after = snapshot(self.project)
        self.assertTrue(all(after[name] == value for name, value in before.items()))
        self.assertEqual(report["application"], "unchanged")
        self.assertEqual(report["agent_installation"], "unchanged")
        self.assertEqual(report["checks"]["cloud"], "not_checked")
        exported = self.project / "deploy/oci"
        self.assertTrue((exported / "terraform/container.tf").is_file())
        self.assertTrue((exported / "LICENSE").is_file())
        self.assertFalse((exported / "app").exists())
        self.assertFalse((self.project / ".oci-founder-kit").exists())
        self.assertFalse((self.project / ".agents").exists())
        self.assertNotIn("PRIVATE_TEST_SENTINEL", json.dumps(report))
        self.assertNotIn("PRIVATE_TEST_SENTINEL", (exported / "README.md").read_text())

    def test_dry_run_validates_same_sources_without_creating_any_destination(self):
        before = snapshot(self.project)
        report = self.attach(dry_run=True)
        self.assertEqual(report["status"], "dry_run")
        self.assertFalse((self.project / "deploy").exists())
        self.assertEqual(before, snapshot(self.project))

    def test_existing_empty_or_populated_destination_is_never_overwritten(self):
        for populated in (False, True):
            with self.subTest(populated=populated):
                destination = self.project / ("populated" if populated else "empty")
                destination.mkdir()
                if populated:
                    (destination / "main.tf").write_text("owner source")
                before = snapshot(self.project)
                with self.assertRaises(ValueError):
                    self.attach(destination.name)
                self.assertEqual(before, snapshot(self.project))

    def test_unsafe_directories_and_source_overlap_are_refused(self):
        for value in ("", ".", "../outside", "/tmp/outside", "deploy/../../app", "deploy//oci",
                      "deploy/./oci", "deploy/", "C:\\private", ".git/oci", "deploy/.oci"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.attach(value)
        with self.assertRaises(ValueError):
            attach_module.attach("web-container", self.source, "blueprints/other", root=self.source)
        with self.assertRaises(ValueError):
            attach_module.attach("web-container", self.project / ".." / "kit", "unexpected", root=self.source)

    def test_symlinked_parent_and_final_destination_are_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "marker").write_text("unchanged")
        (self.project / "deploy").symlink_to(outside, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self.attach()
        self.assertEqual(list(outside.iterdir()), [outside / "marker"])
        (self.project / "deploy").unlink()
        (self.project / "deploy").mkdir()
        (self.project / "deploy/oci").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.attach()
        self.assertEqual(list(outside.iterdir()), [outside / "marker"])

    def test_symlinked_project_and_source_file_are_refused(self):
        alias = self.base / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(ValueError):
            attach_module.attach("web-container", alias, "deploy/oci", root=self.source)
        target = self.source / "blueprints/web-container/terraform/container.tf"
        target.unlink()
        target.symlink_to(self.project / ".env")
        with self.assertRaises(ValueError):
            self.attach()
        self.assertFalse((self.project / "deploy").exists())

    def test_changed_or_unlisted_sources_refuse_before_touching_app(self):
        target = self.source / "blueprints/web-container/terraform/container.tf"
        target.write_text(target.read_text() + "\n# Modified after review\n")
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), self.assertRaises(ValueError):
                self.attach(dry_run=dry_run)
        self.assertFalse((self.project / "deploy").exists())

    def test_interrupted_copy_leaves_partial_target_and_preserves_existing_app(self):
        helper = attach_module.source_helper(self.source)
        before = snapshot(self.project)

        def interrupted(stage, directory_fd, relative=()):
            fd = os.open("partial", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
            os.close(fd)
            raise OSError("Synthetic interruption")

        with mock.patch.object(helper, "publish", side_effect=interrupted), mock.patch.object(attach_module, "source_helper", return_value=helper):
            with self.assertRaises(OSError):
                self.attach()
        self.assertTrue((self.project / "deploy/oci/partial").exists())
        after = snapshot(self.project)
        self.assertTrue(all(after[name] == value for name, value in before.items()))
        with self.assertRaises(ValueError):
            self.attach()

    def test_cli_from_fixture_release_and_installed_source_subdirectory(self):
        # A kit installed inside an app must be usable without reinstalling it.
        installed = self.project / ".oci-founder-kit"
        shutil.copytree(self.source, installed)
        result = subprocess.run([sys.executable, str(installed / "scripts/blueprint.py"), "attach", "web-container",
                                 "--project", str(self.project), "--directory", "deploy/oci"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "attached")
        self.assertTrue((self.project / "deploy/oci/terraform/versions.tf").is_file())

    def test_v2_metadata_is_deployment_only_and_v1_remains_supported(self):
        contract = blueprint.load("web-container", self.source)
        self.assertEqual(contract["kind"], "deployment")
        self.assertNotIn("app", contract["paths"])
        self.assertNotIn("preview", contract["commands"])
        self.assertEqual(blueprint.load("fullstack-container")["schema"], "oci-kit-blueprint/1")
        metadata = self.source / "blueprints/web-container/blueprint.json"
        contract["application_contract"]["execute"] = "not permitted"
        metadata.write_text(json.dumps(contract))
        with self.assertRaises(ValueError):
            blueprint.load("web-container", self.source)

    def test_sensitive_local_configuration_is_ignored_within_attached_directory(self):
        self.attach()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        private = ["deploy/oci/terraform/terraform.tfvars", "deploy/oci/terraform/backend.tfbackend.json",
                   "deploy/oci/terraform/terraform.tfstate", "deploy/oci/.gate/private.json",
                   "deploy/oci/.ENV", "deploy/oci/credentials.KEY", "deploy/oci/terraform/tfplan.saved"]
        result = subprocess.run(["git", "-C", str(self.project), "check-ignore", "--stdin"],
                                input="\n".join(private) + "\n", capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), set(private))


if __name__ == "__main__":
    unittest.main()
