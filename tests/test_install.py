"""Project-local installation preserves source paths and existing app files."""

import importlib.util
import json
import os
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kit_install", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class Installation(unittest.TestCase):
    def test_both_agents_load_workflows_with_supporting_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "AGENTS.md").write_text("Existing app instructions\n")
            result = installer.install(project, "both")
            self.assertIn("oci-kit", result["skills"])
            self.assertRegex(result["kit_version"], r"^\d+\.\d+\.\d+")
            self.assertEqual((project / "AGENTS.md").read_text(), "Existing app instructions\n")
            for directory in [".agents", ".claude"]:
                entry = project / directory / "skills/oci-kit/SKILL.md"
                reference = entry.read_text().split("](", 1)[1].split(")", 1)[0]
                self.assertTrue((entry.parent / reference).is_file())
            self.assertTrue((project / ".oci-founder-kit/blueprints/fullstack-container/app/package.json").is_file())
            self.assertFalse((project / ".oci-founder-kit/.git").exists())
            validation = subprocess.run(
                [sys.executable, str(project / ".oci-founder-kit/scripts/validate.py")],
                capture_output=True, text=True, check=False)
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer.install(Path(tmp), "codex", True)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_status_is_read_only_and_reports_missing_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            installer.install(project, "codex")
            entry = project / ".agents/skills/oci-kit/SKILL.md"
            entry.unlink()
            before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
            result = installer.status(project)
            after = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertIn("codex:oci-kit", result["missing_entries"])
            self.assertTrue(result["installed"])

    def test_status_refuses_symlinked_metadata_and_arbitrary_skill_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / ".oci-founder-kit"
            bundle.mkdir()
            metadata = bundle / "installation.json"
            metadata.write_text(json.dumps({"agents": ["codex"], "skills": ["../../private"]}))
            with self.assertRaises(ValueError):
                installer.status(project)
            metadata.unlink()
            outside = project / "private.txt"
            outside.write_text("PRIVATE_SENTINEL")
            metadata.symlink_to(outside)
            with self.assertRaises(ValueError):
                installer.status(project)

    @unittest.skipIf(os.name == "nt", "POSIX executable mode contract")
    def test_installed_deploy_gate_fixture_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            installer.install(project, "codex")
            fixture = project / ".oci-founder-kit/tests/fixtures/fake_terraform.py"
            result = subprocess.run([str(fixture), "version"],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("terraform_version", result.stdout)

    def test_existing_skill_refuses_before_bundle_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            existing = project / ".agents/skills/oci-kit"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("Keep me")
            with self.assertRaises(ValueError):
                installer.install(project, "codex")
            self.assertEqual((existing / "SKILL.md").read_text(), "Keep me")
            self.assertFalse((project / ".oci-founder-kit").exists())

    def test_symlinked_discovery_directory_refused(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            project = Path(tmp)
            (project / ".agents").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                installer.install(project, "codex")
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_install_cannot_clobber_existing_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".oci-founder-kit").mkdir()
            with self.assertRaises(ValueError):
                installer.install(project, "both")

    def test_distribution_excludes_keys_state_and_env(self):
        for name in ["skills/x/.env", "skills/x/.env.local", "blueprints/x/a.tfstate",
                     "blueprints/x/a.tfvars", "blueprints/x/private.auto.tfvars.json", "blueprints/x/private.tfbackend", "blueprints/x/private.tfbackend.json",
                     "blueprints/x/crash.log", "skills/x/credentials/config.json",
                     "blueprints/x/.local-preview/settings.json",
                     "skills/x/key.pem", "skills/x/.gate/report.json"]:
            self.assertFalse(installer.distributable(ROOT / name), name)
        self.assertTrue(installer.distributable(ROOT / "blueprints/x/terraform.tfvars.example"))

    def test_symlinked_metadata_is_not_copied_into_entries(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as app:
            fake_root = Path(tmp) / "kit"
            skill = fake_root / "skills/example"
            (skill / "agents").mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: example\ndescription: Example\n---\nWorkflow\n")
            outside = Path(tmp) / "private"
            outside.write_text("PRIVATE_SENTINEL")
            (skill / "agents/openai.yaml").symlink_to(outside)
            with mock.patch.object(installer, "ROOT", fake_root):
                installer.install(Path(app), "codex")
            self.assertFalse((Path(app) / ".agents/skills/example/agents/openai.yaml").exists())
            for file in Path(app).rglob("*"):
                if file.is_file():
                    self.assertNotIn("PRIVATE_SENTINEL", file.read_text())

    def test_symlinked_skill_instructions_are_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as app:
            fake_root = Path(tmp) / "kit"
            skill = fake_root / "skills/example"
            skill.mkdir(parents=True)
            outside = Path(tmp) / "private"
            outside.write_text("---\nname: example\n---\nPRIVATE_SENTINEL")
            (skill / "SKILL.md").symlink_to(outside)
            with mock.patch.object(installer, "ROOT", fake_root):
                result = installer.install(Path(app), "codex")
            self.assertEqual(result["skills"], [])

    def test_private_terraform_inputs_and_crash_log_not_distributed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as app:
            fake_root = Path(tmp) / "kit"
            (fake_root / "skills").mkdir(parents=True)
            private = fake_root / "blueprints/test"
            private.mkdir(parents=True)
            for name in ["private.auto.tfvars.json", "private.tfbackend.json", "crash.log"]:
                (private / name).write_text("PRIVATE_SENTINEL")
            with mock.patch.object(installer, "ROOT", fake_root):
                installer.install(Path(app), "codex")
            for name in ["private.auto.tfvars.json", "private.tfbackend.json", "crash.log"]:
                self.assertFalse((Path(app) / ".oci-founder-kit/blueprints/test" / name).exists())

    def test_private_local_preview_is_not_distributed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as app:
            fake_root = Path(tmp) / "kit"
            (fake_root / "skills").mkdir(parents=True)
            private = fake_root / "blueprints/test/.local-preview"
            private.mkdir(parents=True)
            (private / "settings.json").write_text("PRIVATE_PREVIEW_SENTINEL")
            with mock.patch.object(installer, "ROOT", fake_root):
                installer.install(Path(app), "codex")
            self.assertFalse((Path(app) / ".oci-founder-kit/blueprints/test/.local-preview").exists())


if __name__ == "__main__":
    unittest.main()
