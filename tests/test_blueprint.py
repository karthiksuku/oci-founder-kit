"""Blueprint inspection checks local metadata without executing its commands."""

import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


blueprint = module("kit_blueprint", ROOT / "scripts/blueprint.py")
installer = module("blueprint_install", ROOT / "scripts/install.py")
CONTRACT = json.loads((ROOT / "blueprints/fullstack-container/blueprint.json").read_text())


class BlueprintInspection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / "blueprints/fullstack-container"
        (self.base / "app/test").mkdir(parents=True)
        (self.base / "terraform").mkdir()
        (self.base / "app/package.json").write_text("{}")
        (self.base / "local_preview.py").write_text("raise RuntimeError('must not run')\n")
        self.path = self.base / "blueprint.json"
        self.write(CONTRACT)

    def write(self, value):
        self.path.write_text(json.dumps(value))

    def test_catalog_checks_metadata_without_running_commands_or_changing_files(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with mock.patch("subprocess.run", side_effect=AssertionError("must not execute")):
            data = blueprint.load("fullstack-container", self.root)
            found = blueprint.catalog(self.root)
        after = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(data["schema"], "oci-kit-blueprint/1")
        self.assertEqual([item["id"] for item in found], ["fullstack-container"])

    def test_rejects_unknown_fields_at_each_contract_level(self):
        paths = [(), ("runtime",), ("paths",), ("tools", 0), ("commands",),
                 ("commands", "preview"), ("operating_modes", 0), ("acceptance", 0)]
        for path in paths:
            with self.subTest(path=path):
                data = copy.deepcopy(CONTRACT)
                part = data
                for key in path:
                    part = part[key]
                part["unexpected"] = "PRIVATE_SENTINEL"
                self.write(data)
                with self.assertRaises(ValueError):
                    blueprint.load("fullstack-container", self.root)

    def test_rejects_missing_fields_invalid_schema_id_and_types(self):
        cases = [("schema", "oci-kit-blueprint/99"), ("id", "other"), ("tools", []),
                 ("commands", []), ("outputs", ["https://app.example.test"]),
                 ("acceptance", [{"id": "local", "description": 1}])]
        for key, value in cases:
            with self.subTest(key=key):
                data = copy.deepcopy(CONTRACT)
                data[key] = value
                self.write(data)
                with self.assertRaises(ValueError):
                    blueprint.load("fullstack-container", self.root)
        data = copy.deepcopy(CONTRACT)
        del data["runtime"]
        self.write(data)
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)

    def test_rejects_path_escape_absolute_and_platform_ambiguous_paths(self):
        for value in ("../outside", "/tmp", "app/../../outside", "C:\\private", "app//test", "app/./test"):
            with self.subTest(path=value):
                data = copy.deepcopy(CONTRACT)
                data["paths"]["app"] = value
                self.write(data)
                with self.assertRaises(ValueError):
                    blueprint.load("fullstack-container", self.root)
        with self.assertRaises(ValueError):
            blueprint.load("../outside", self.root)

    def test_runtime_source_and_command_directory_cannot_escape(self):
        for section in ("runtime", "command"):
            data = copy.deepcopy(CONTRACT)
            if section == "runtime":
                data["runtime"]["source"] = "../../private.txt"
            else:
                data["commands"]["preview"]["cwd"] = "../outside"
            self.write(data)
            with self.assertRaises(ValueError):
                blueprint.load("fullstack-container", self.root)

    def test_missing_paths_and_wrong_types_are_rejected(self):
        (self.base / "local_preview.py").unlink()
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)
        (self.base / "local_preview.py").mkdir()
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)

    @unittest.skipIf(os.name == "nt", "POSIX symlink fixtures")
    def test_symlinked_paths_and_metadata_are_not_followed(self):
        private = self.root / "private.txt"
        private.write_text("PRIVATE_SENTINEL")
        preview = self.base / "local_preview.py"
        preview.unlink()
        preview.symlink_to(private)
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)
        preview.unlink()
        preview.write_text("# fixture\n")
        self.path.unlink()
        self.path.symlink_to(private)
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)
        with self.assertRaises(ValueError):
            blueprint.catalog(self.root)

    @unittest.skipIf(os.name == "nt", "POSIX symlink fixtures")
    def test_symlinked_parent_is_rejected(self):
        (self.base / "app/test").rmdir()
        (self.base / "app/package.json").unlink()
        (self.base / "app").rmdir()
        (self.base / "app").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)

    def test_duplicate_json_fields_and_oversized_metadata_are_rejected(self):
        self.path.write_text('{"schema":"oci-kit-blueprint/1","schema":"other"}')
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)
        self.path.write_text(" " * (blueprint.LIMIT + 1))
        with self.assertRaises(ValueError):
            blueprint.load("fullstack-container", self.root)

    def test_duplicate_ids_undeclared_tools_and_control_text_are_rejected(self):
        changes = [lambda d: d["tools"].append(d["tools"][0]),
                   lambda d: d["acceptance"].append(d["acceptance"][0]),
                   lambda d: d["outputs"].append(d["outputs"][0]),
                   lambda d: d["commands"]["preview"].update(argv=["undeclared", "start"]),
                   lambda d: d.update(summary="unsafe\ntext")]
        for change in changes:
            data = copy.deepcopy(CONTRACT)
            change(data)
            self.write(data)
            with self.assertRaises(ValueError):
                blueprint.load("fullstack-container", self.root)

    def test_invalid_contract_diagnostic_does_not_echo_contents(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(blueprint, "load", side_effect=ValueError("PRIVATE_SENTINEL")):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                result = blueprint.main(["inspect", "fullstack-container"])
        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("PRIVATE_SENTINEL", errors.getvalue())

    def test_installed_bundle_preserves_inspection_command_and_contract(self):
        with tempfile.TemporaryDirectory() as app:
            project = Path(app)
            installer.install(project, "codex")
            bundle = project / ".oci-founder-kit"
            result = subprocess.run([sys.executable, str(bundle / "scripts/blueprint.py"),
                                     "inspect", "fullstack-container"],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["metadata"], "valid")
            self.assertEqual(data["commands"], "not_run")
            self.assertEqual(data["cloud"], "not_checked")
            self.assertIn("never executed", data["scope"])


if __name__ == "__main__":
    unittest.main()
