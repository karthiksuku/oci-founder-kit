"""Distribution follows reviewed file identities, not directory contents."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manifest_test_install", ROOT / "scripts/install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)
manifest = install.manifest_module()


class ReleaseManifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "kit"
        self.app = Path(self.tmp.name) / "app"
        self.app.mkdir()
        path = self.root / "skills/example/SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text("---\nname: example\ndescription: Example workflow\n---\nUse this workflow.\n")
        self.names = ["skills/example/SKILL.md"]
        self.patch = mock.patch.object(install, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.refresh()

    def refresh(self):
        manifest.write(self.root, manifest.build(self.root, self.names, install.distributable))

    def test_unlisted_content_and_skills_do_not_enter_installation(self):
        (self.root / "skills/example/unrelated.json").write_text("PRIVATE_SYNTHETIC_CONTENT")
        extra = self.root / "skills/unreviewed/SKILL.md"
        extra.parent.mkdir()
        extra.write_text("---\nname: unreviewed\ndescription: Not included\n---\n")
        report = install.install(self.app, "both")
        self.assertEqual(report["skills"], ["example"])
        self.assertFalse((self.app / ".oci-founder-kit/skills/example/unrelated.json").exists())
        self.assertFalse((self.app / ".agents/skills/unreviewed").exists())
        for name, digest in report["owned_files"].items():
            self.assertEqual(hashlib.sha256((self.app / name).read_bytes()).hexdigest(), digest)

    def test_changed_or_missing_listed_file_refuses_without_partial_install(self):
        path = self.root / self.names[0]
        path.write_text("Changed after release review")
        for dry in (True, False):
            with self.assertRaises(ValueError):
                install.install(self.app, "codex", dry)
            self.assertEqual(list(self.app.iterdir()), [])
        path.unlink()
        with self.assertRaises(OSError):
            install.install(self.app, "codex")

    def test_listed_symlink_is_refused(self):
        path = self.root / self.names[0]
        outside = Path(self.tmp.name) / "outside"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            install.install(self.app, "codex")
        self.assertEqual(list(self.app.iterdir()), [])

    def test_missing_manifest_does_not_fall_back_to_directory_copy(self):
        (self.root / manifest.NAME).unlink()
        with self.assertRaises(OSError):
            install.install(self.app, "codex")
        self.assertEqual(list(self.app.iterdir()), [])

    def test_private_and_escaping_manifest_entries_are_refused(self):
        for name in ("skills/example/.env", "../outside", "/absolute", "skills/../outside",
                     "skills/example/.oci-kit/state.json"):
            with self.subTest(name=name):
                data = {"schema": manifest.SCHEMA, "files": {name: {"sha256": "a" * 64, "executable": False}}}
                manifest.write(self.root, data)
                with self.assertRaises(ValueError):
                    manifest.verified(self.root, install.distributable)

    def test_duplicate_manifest_fields_are_refused(self):
        (self.root / manifest.NAME).write_text('{"schema":"oci-kit-release/1","files":{},"files":{}}')
        with self.assertRaises(ValueError):
            manifest.verified(self.root, install.distributable)

    def test_creation_uses_indexed_paths_not_untracked_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "add", "--", self.names[0]], check=True, capture_output=True)
        unknown = self.root / "skills/example/untracked.json"
        unknown.write_text("SYNTHETIC_PRIVATE_DATA")
        listed = manifest.indexed_paths(self.root)
        self.assertEqual(listed, self.names)
        manifest.write(self.root, manifest.build(self.root, listed, install.distributable))
        install.install(self.app, "codex")
        self.assertFalse((self.app / ".oci-founder-kit/skills/example/untracked.json").exists())


if __name__ == "__main__":
    unittest.main()
