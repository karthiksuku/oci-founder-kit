"""Creating a project exports editable sources without running tools or touching an existing app."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/blueprint.py"


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def scaffold_module():
    spec = importlib.util.spec_from_file_location("create_scaffold_test", ROOT / "scripts/scaffold.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlueprintCreate(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="oci-kit-create-test-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)

    def run_create(self, project, agent="both", *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "create", "fullstack-container",
                               "--project", str(project), "--agent", agent, *extra],
                              capture_output=True, text=True, check=False)

    def fixture_source(self):
        module = scaffold_module()
        installer = module.sibling(ROOT, "install")
        fake_root = self.parent / "source"
        for source in installer.source_files():
            target = fake_root / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return fake_root

    def test_new_project_has_independent_editable_sources_and_installed_skills(self):
        project = self.parent / "my app"
        result = self.run_create(project)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "created")
        self.assertTrue(all(value == "not_run" for value in report["checks"].values()))
        self.assertTrue((project / "app/src/server.js").is_file())
        self.assertTrue((project / "terraform/main.tf").is_file() or (project / "terraform/versions.tf").is_file())
        self.assertTrue((project / "registry/main.tf").is_file())
        self.assertTrue((project / ".agents/skills/oci-kit/SKILL.md").is_file())
        self.assertTrue((project / ".claude/skills/oci-kit/SKILL.md").is_file())
        source = ROOT / "blueprints/fullstack-container/app/src/server.js"
        original = source.read_bytes()
        edited = project / "app/src/server.js"
        self.assertEqual(edited.read_bytes(), original)
        edited.write_text("// editable project copy\n")
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((project / ".oci-founder-kit/blueprints/fullstack-container/app/src/server.js").read_bytes(), original)
        for command in report["commands"].values():
            self.assertEqual(command["cwd"], str(project))
            self.assertIsInstance(command["argv"], list)
        preview = report["commands"]["preview"]["argv"]
        self.assertEqual(preview, ["python3", "local_preview.py", "start"])
        help_result = subprocess.run([sys.executable, str(project / "local_preview.py"), "--help"],
                                     capture_output=True, text=True, check=False)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertFalse((project / ".local-preview").exists())

    def test_empty_existing_project_and_one_agent(self):
        project = self.parent / "app"
        project.mkdir()
        result = self.run_create(project, "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / ".agents/skills/oci-kit/SKILL.md").is_file())
        self.assertFalse((project / ".claude").exists())

    def test_dry_run_creates_no_project_or_staging_files(self):
        project = self.parent / "app"
        before = snapshot(self.parent)
        result = self.run_create(project, "both", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "dry_run")
        self.assertFalse(project.exists())
        self.assertEqual(snapshot(self.parent), before)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_dry_run_does_not_write_helper_bytecode_into_source(self):
        source = self.fixture_source()
        before = snapshot(source)
        environment = os.environ.copy()
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        result = subprocess.run(
            [sys.executable, str(source / "scripts/blueprint.py"), "create", "fullstack-container",
             "--project", str(self.parent / "app"), "--dry-run"],
            capture_output=True, text=True, env=environment, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(source), before)
        self.assertFalse((self.parent / "app").exists())

    def test_existing_app_is_refused_without_modification(self):
        project = self.parent / "existing"
        project.mkdir()
        (project / "README.md").write_text("Existing user work\n")
        before = snapshot(self.parent)
        result = self.run_create(project)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Preserve and review the destination", result.stderr)
        self.assertEqual(snapshot(self.parent), before)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink fixture")
    def test_symlink_target_and_parent_are_refused(self):
        outside = self.parent / "outside"
        outside.mkdir()
        link = self.parent / "link"
        link.symlink_to(outside, target_is_directory=True)
        for target in [link, link / "app"]:
            result = self.run_create(target)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(outside.iterdir()), [])

    def test_missing_parent_is_not_created_implicitly(self):
        project = self.parent / "missing/app"
        result = self.run_create(project)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.parent / "missing").exists())

    def test_generated_guidance_and_git_rules_keep_local_state_private(self):
        project = self.parent / "app"
        result = self.run_create(project)
        self.assertEqual(result.returncode, 0, result.stderr)
        readme = (project / "README.md").read_text()
        self.assertIn("local_preview.py start", readme)
        self.assertIn("app/", readme)
        self.assertIn(".oci-founder-kit", (project / "AGENTS.md").read_text())
        progress = (project / "docs/PROGRESS.md").read_text()
        self.assertIn("Not started", progress)
        self.assertNotIn("| Passed |", progress)
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        for path in [".local-preview/settings.json", ".env", "terraform/private.tfvars",
                     "terraform/state.tfstate", ".next/cache/data", ".vercel/project.json",
                     ".netlify/state.json", "app/node_modules/a.js", ".oci-founder-kit/README.md"]:
            ignored = subprocess.run(["git", "-C", str(project), "check-ignore", "-q", path])
            self.assertEqual(ignored.returncode, 0, path)

    def test_staging_failure_leaves_existing_empty_project_and_no_artifacts(self):
        module = scaffold_module()
        project = self.parent / "app"
        project.mkdir()
        with mock.patch.object(module, "prepare", side_effect=OSError("PRIVATE_FAILURE")):
            with self.assertRaises(OSError):
                module.create("fullstack-container", project, "both", root=ROOT)
        self.assertEqual(list(project.iterdir()), [])
        self.assertEqual(list(self.parent.iterdir()), [project])

    def test_creation_does_not_start_external_tools(self):
        module = scaffold_module()
        project = self.parent / "app"
        with mock.patch("subprocess.Popen", side_effect=AssertionError("must not run a tool")), \
                mock.patch("os.system", side_effect=AssertionError("must not invoke a shell")), \
                mock.patch("socket.socket", side_effect=AssertionError("must not use the network")):
            result = module.create("fullstack-container", project, "claude", root=ROOT)
        self.assertEqual(result["status"], "created")
        self.assertFalse((project / ".local-preview").exists())
        self.assertFalse((project / ".agents").exists())

    def test_generated_production_pointer_uses_this_project_and_installed_guides(self):
        project = self.parent / "app"
        result = self.run_create(project)
        self.assertEqual(result.returncode, 0, result.stderr)
        guide = (project / "PRODUCTION.md").read_text()
        self.assertIn(".oci-founder-kit/blueprints/fullstack-container/PRODUCTION.md", guide)
        self.assertIn("python3 .oci-founder-kit/skills/oci-deploy/scripts/deploy_gate.py", guide)
        self.assertIn("--dir terraform", guide)
        self.assertNotIn("../../", guide)
        self.assertIn("../PRODUCTION.md", (project / "terraform/production.tf").read_text())

    def test_exports_exclude_private_files_and_generated_caches(self):
        module = scaffold_module()
        fake_root = self.fixture_source()
        canary = secrets.token_hex(24)
        base = fake_root / "blueprints/fullstack-container"
        for relative in ["app/.env", "app/.next/cache/private", "app/.vercel/project.json",
                         "app/.netlify/state.json", "terraform/private.auto.tfvars.json",
                         "terraform/private.tfstate", ".local-preview/settings.json"]:
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(canary)
        outside = self.parent / "private"
        outside.write_text(canary)
        (base / "app/external.txt").symlink_to(outside)
        project = self.parent / "created"
        module.create("fullstack-container", project, "both", root=fake_root)
        for path in project.rglob("*"):
            if path.is_file():
                self.assertNotIn(canary.encode(), path.read_bytes(), str(path))
            self.assertFalse(path.is_symlink(), str(path))
        self.assertFalse((project / "app/.env").exists())
        self.assertFalse((project / "terraform/private.auto.tfvars.json").exists())

    def test_dry_run_refuses_missing_required_export_without_writing(self):
        module = scaffold_module()
        fake_root = self.fixture_source()
        (fake_root / "blueprints/fullstack-container/compose.local.yaml").unlink()
        project = self.parent / "app"
        with self.assertRaises(ValueError):
            module.create("fullstack-container", project, "both", True, root=fake_root)
        self.assertFalse(project.exists())
        self.assertEqual(list(self.parent.iterdir()), [fake_root])

    def test_publication_failure_retains_partial_output_and_foreign_file(self):
        module = scaffold_module()
        project = self.parent / "app"
        project.mkdir()
        original = module.publish_file
        count = 0

        def prepare(root, name, stage, agent):
            (stage / "first.txt").write_text("Generated source\n")
            (stage / "second.txt").write_text("More generated source\n")
            return {"kit_version": "0.4.0"}

        def collide(source, directory_fd, name):
            nonlocal count
            count += 1
            if count == 2:
                (project / "foreign.txt").write_text("Preserve user work\n")
                raise FileExistsError("Publication collision")
            return original(source, directory_fd, name)

        with mock.patch.object(module, "prepare", side_effect=prepare), \
                mock.patch.object(module, "publish_file", side_effect=collide):
            with self.assertRaises(OSError):
                module.create("fullstack-container", project, "both", root=ROOT)
        self.assertEqual((project / "foreign.txt").read_text(), "Preserve user work\n")
        self.assertEqual((project / "first.txt").read_text(), "Generated source\n")
        self.assertEqual({p.name for p in project.iterdir()}, {"foreign.txt", "first.txt"})

    def test_parent_replacement_after_validation_cannot_redirect_creation(self):
        module = scaffold_module()
        parent = self.parent / "target-parent"
        parent.mkdir()
        moved = self.parent / "original-parent"
        outside = self.parent / "outside"
        outside.mkdir()
        temporary = tempfile.TemporaryDirectory
        swapped = False

        def swap_parent(*args, **kwargs):
            nonlocal swapped
            if not swapped:
                parent.rename(moved)
                parent.symlink_to(outside, target_is_directory=True)
                swapped = True
            return temporary(*args, **kwargs)

        with mock.patch.object(module.tempfile, "TemporaryDirectory", side_effect=swap_parent):
            with self.assertRaises((ValueError, OSError)):
                module.create("fullstack-container", parent / "app", "both", root=ROOT)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list(moved.iterdir()), [])

    def test_user_replacement_survives_failed_publication(self):
        module = scaffold_module()
        project = self.parent / "app"
        original = module.publish_file

        def prepare(root, name, stage, agent):
            (stage / "first.txt").write_text("Generated source\n")
            (stage / "second.txt").write_text("More source\n")
            return {"kit_version": "0.4.0"}

        def fail_after_user_replacement(source, directory_fd, name):
            if name == "second.txt":
                replacement = project / "replacement.tmp"
                replacement.write_text("Concurrent user work\n")
                replacement.replace(project / "first.txt")
                raise OSError("Synthetic publication failure")
            return original(source, directory_fd, name)

        with mock.patch.object(module, "prepare", side_effect=prepare), \
                mock.patch.object(module, "publish_file", side_effect=fail_after_user_replacement):
            with self.assertRaises(OSError):
                module.create("fullstack-container", project, "both", root=ROOT)
        self.assertEqual((project / "first.txt").read_text(), "Concurrent user work\n")
        self.assertEqual(list(project.iterdir()), [project / "first.txt"])

    def test_parent_replacement_during_publication_retains_partial_original(self):
        module = scaffold_module()
        parent = self.parent / "target-parent"
        parent.mkdir()
        moved = self.parent / "original-parent"
        outside = self.parent / "outside"
        outside.mkdir()
        original = module.publish_file

        def prepare(root, name, stage, agent):
            (stage / "first.txt").write_text("Generated source\n")
            return {"kit_version": "0.4.0"}

        def move_parent_after_write(source, directory_fd, name):
            original(source, directory_fd, name)
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)

        with mock.patch.object(module, "prepare", side_effect=prepare), \
                mock.patch.object(module, "publish_file", side_effect=move_parent_after_write):
            with self.assertRaises((OSError, ValueError)):
                module.create("fullstack-container", parent / "app", "both", root=ROOT)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual((moved / "app/first.txt").read_text(), "Generated source\n")


if __name__ == "__main__":
    unittest.main()
