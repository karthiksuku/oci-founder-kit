"""Local updates preserve app changes and recover interrupted owned-file writes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import shlex
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kit_update_tests", ROOT / "scripts/update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.source = self.parent / "new-kit"
        self.project = self.parent / "app"
        self.project.mkdir()
        for name, value in {
            "skills/example/SKILL.md": "---\nname: example\ndescription: Example\n---\nOld workflow\n",
            ".claude-plugin/plugin.json": '{"version":"0.5.0"}',
            "README.md": "First release\n",
        }.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        self.patch_root = mock.patch.object(update, "ROOT", self.source)
        self.patch_installer = mock.patch.object(update.INSTALL, "ROOT", self.source)
        self.patch_root.start(); self.patch_installer.start()
        self.addCleanup(self.patch_root.stop); self.addCleanup(self.patch_installer.stop)
        self.names = ["skills/example/SKILL.md", ".claude-plugin/plugin.json", "README.md"]
        self.refresh()
        update.INSTALL.install(self.project, "both")
        (self.project / "app.py").write_text("User app edits\n")
        (self.project / ".oci-founder-kit/unowned.txt").write_text("Preserve local notes\n")
        private = self.project / ".oci-kit"
        private.mkdir(mode=0o700)
        (private / "state.json").write_text('{"checkpoint":"synthetic"}')

    def refresh(self):
        update.MANIFEST.write(self.source, update.MANIFEST.build(self.source, self.names, update.INSTALL.distributable))

    def new_release(self):
        (self.source / "README.md").write_text("Second release\n")
        (self.source / ".claude-plugin/plugin.json").write_text('{"version":"0.5.1"}')
        self.refresh()

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def test_preview_writes_nothing_and_apply_preserves_app_and_unowned_state(self):
        self.new_release()
        before = self.snapshot()
        plan = update.update(self.project)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(self.snapshot(), before)
        result = update.update(self.project, apply=True)
        self.assertEqual(result["status"], "updated")
        self.assertEqual((self.project / ".oci-founder-kit/README.md").read_text(), "Second release\n")
        for name in ("app.py", ".oci-founder-kit/unowned.txt", ".oci-kit/state.json"):
            self.assertEqual((self.project / name).read_bytes(), before[name])
        self.assertFalse((self.project / ".oci-kit/update-active").exists())
        self.assertTrue((self.project / result["backup"] / "journal.json").is_file())
        self.assertEqual(update.update(self.project)["status"], "current")

    def test_edited_owned_file_refuses_without_writes(self):
        self.new_release()
        (self.project / ".oci-founder-kit/README.md").write_text("User customized this\n")
        before = self.snapshot()
        with self.assertRaises(update.UpdateError):
            update.update(self.project, apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_unowned_collision_is_preserved(self):
        (self.source / "CONTRIBUTING.md").write_text("New file")
        self.names.append("CONTRIBUTING.md")
        self.refresh()
        destination = self.project / ".oci-founder-kit/CONTRIBUTING.md"
        destination.write_text("Unowned original")
        with self.assertRaises(update.UpdateError):
            update.update(self.project, apply=True)
        self.assertEqual(destination.read_text(), "Unowned original")

    def test_installed_hooks_need_explicit_uninstall_before_update(self):
        folder = self.project / ".oci-founder-kit/.hooks"
        folder.mkdir()
        (folder / "codex.json").write_text("{}")
        with self.assertRaisesRegex(update.UpdateError, "Uninstall registered kit hooks"):
            update.update(self.project)

    def test_interruption_recovers_original_files_and_keeps_app_edits(self):
        self.new_release()
        before = self.snapshot()
        original = update.atomic
        wrote = 0

        def interrupt(project, name, content, mode=0o600):
            nonlocal wrote
            if not name.startswith(".oci-kit/"):
                wrote += 1
                if wrote == 2:
                    raise KeyboardInterrupt("synthetic interruption")
            return original(project, name, content, mode)

        with mock.patch.object(update, "atomic", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                update.update(self.project, apply=True)
        self.assertTrue((self.project / ".oci-kit/update-active").is_file())
        with self.assertRaisesRegex(update.UpdateError, "Interrupted update"):
            update.update(self.project)
        (self.project / "app.py").write_text("More user app edits\n")
        result = update.recover(self.project)
        self.assertEqual(result["status"], "recovered")
        for name, content in before.items():
            if name != "app.py":
                self.assertEqual((self.project / name).read_bytes(), content)
        self.assertEqual((self.project / "app.py").read_text(), "More user app edits\n")
        self.assertFalse((self.project / ".oci-kit/update-active").exists())

    def test_recovery_refuses_changes_after_interruption(self):
        self.new_release()
        original = update.atomic
        wrote = []

        def interrupt(project, name, content, mode=0o600):
            if not name.startswith(".oci-kit/"):
                if wrote:
                    raise KeyboardInterrupt()
                wrote.append(name)
            return original(project, name, content, mode)

        with mock.patch.object(update, "atomic", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                update.update(self.project, apply=True)
        changed = self.project / wrote[0]
        changed.write_text("User edit after interruption")
        with self.assertRaises(update.UpdateError):
            update.recover(self.project)
        self.assertEqual(changed.read_text(), "User edit after interruption")

    def test_runtime_failure_rolls_back(self):
        self.new_release()
        before = self.snapshot()
        original = update.atomic
        triggered = False

        def fail_once(project, name, content, mode=0o600):
            nonlocal triggered
            if name == ".oci-founder-kit/README.md" and not triggered:
                triggered = True
                raise OSError("synthetic write failure")
            return original(project, name, content, mode)

        with mock.patch.object(update, "atomic", side_effect=fail_once):
            with self.assertRaises(OSError):
                update.update(self.project, apply=True)
        for name, content in before.items():
            self.assertEqual((self.project / name).read_bytes(), content)
        self.assertFalse((self.project / ".oci-kit/update-active").exists())

    def test_old_installation_requires_baseline(self):
        file = self.project / update.META
        data = json.loads(file.read_text())
        del data["owned_files"]
        file.write_text(json.dumps(data))
        with self.assertRaisesRegex(update.UpdateError, "baseline"):
            update.update(self.project)

    def test_legacy_upgrade_uses_clean_matching_checkout_without_executing_it(self):
        baseline = self.parent / "baseline"
        import shutil
        shutil.copytree(self.source, baseline)
        subprocess.run(["git", "init", "-q", str(baseline)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(baseline), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(baseline), "-c", "user.name=Synthetic Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "Synthetic baseline"],
                       check=True, capture_output=True)
        marker = baseline / ".git/filter-ran"
        callback = baseline / ".git/filter.py"
        callback.write_text('from pathlib import Path\nimport sys\n'
                            'Path(__file__).with_name("filter-ran").write_text("synthetic")\n'
                            'sys.stdout.buffer.write(sys.stdin.buffer.read())\n')
        (baseline / ".git/info/attributes").write_text("README.md filter=synthetic\n")
        subprocess.run(["git", "-C", str(baseline), "config", "filter.synthetic.clean",
                        shlex.join([sys.executable, str(callback)])], check=True, capture_output=True)
        file = self.project / update.META
        data = json.loads(file.read_text())
        del data["owned_files"]
        file.write_text(json.dumps(data))
        self.new_release()
        result = update.update(self.project, apply=True, baseline=baseline)
        self.assertEqual(result["status"], "updated")
        self.assertFalse(marker.exists(), "Baseline validation executed a repository conversion filter")
        self.assertEqual((self.project / "app.py").read_text(), "User app edits\n")

    def test_legacy_baseline_tree_replacement_cannot_hide_staged_changes(self):
        baseline = self.parent / "baseline"
        import shutil
        shutil.copytree(self.source, baseline)

        def git(*arguments):
            return subprocess.run(["git", "-C", str(baseline), *arguments],
                                  check=True, capture_output=True).stdout

        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "Synthetic baseline")
        data = json.loads((self.project / update.META).read_text())
        original = (baseline / "README.md").read_bytes()
        self.assertEqual(update.legacy_owned(data, baseline)[".oci-founder-kit/README.md"], update.digest(original))
        original_tree = git("rev-parse", "HEAD^{tree}").decode().strip()
        (baseline / "README.md").write_text("Changed baseline\n")
        git("add", "README.md")
        with self.assertRaises(update.UpdateError):
            update.legacy_owned(data, baseline)
        replacement_tree = git("write-tree").decode().strip()
        git("replace", original_tree, replacement_tree)
        self.assertEqual(git("--no-replace-objects", "show", "HEAD:README.md"), original)
        with self.assertRaises(update.UpdateError):
            update.legacy_owned(data, baseline)

    def test_symlinked_owned_target_or_parent_refused(self):
        self.new_release()
        original = self.project / ".oci-founder-kit/README.md"
        original.unlink()
        original.symlink_to(self.project / "app.py")
        with self.assertRaises(update.UpdateError):
            update.update(self.project, apply=True)
        self.assertEqual((self.project / "app.py").read_text(), "User app edits\n")

    def test_active_operation_blocks_concurrent_recovery_and_apply(self):
        self.new_release()
        original = update.atomic
        checked = []

        def probe(project, name, content, mode=0o600):
            if not name.startswith(".oci-kit/") and not checked:
                checked.append(name)
                for operation in (lambda: update.recover(project),
                                  lambda: update.update(project, apply=True)):
                    with self.assertRaisesRegex(update.UpdateError, "Another update"):
                        operation()
            return original(project, name, content, mode)

        with mock.patch.object(update, "atomic", side_effect=probe):
            self.assertEqual(update.update(self.project, apply=True)["status"], "updated")
        self.assertTrue(checked)
        self.assertEqual(update.update(self.project)["status"], "current")

    def test_invalid_version_is_never_echoed(self):
        file = self.project / update.META
        data = json.loads(file.read_text())
        data["kit_version"] = "PRIVATE-SENTINEL"
        file.write_text(json.dumps(data))
        import contextlib
        import io
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = update.main(["check", "--project", str(self.project)])
        self.assertEqual(result, 2)
        self.assertNotIn("PRIVATE-SENTINEL", output.getvalue() + error.getvalue())

    def test_recovery_refuses_broad_backup_permissions(self):
        self.new_release()
        original = update.atomic

        def interrupt(project, name, content, mode=0o600):
            if not name.startswith(".oci-kit/"):
                raise KeyboardInterrupt()
            return original(project, name, content, mode)

        with mock.patch.object(update, "atomic", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                update.update(self.project, apply=True)
        backup = next((self.project / ".oci-kit/updates").iterdir())
        backup.chmod(0o755)
        with self.assertRaisesRegex(update.UpdateError, "owner-only"):
            update.recover(self.project)
        self.assertTrue((self.project / ".oci-kit/update-active").exists())


if __name__ == "__main__":
    unittest.main()
