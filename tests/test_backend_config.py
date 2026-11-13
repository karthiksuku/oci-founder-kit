"""Offline backend discovery refuses ambiguous source and unsafe cache files."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "oci-deploy" / "scripts"))
import backend_config as config  # noqa: E402


class BackendConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backend-config-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.stack = self.tmp / "stack"
        self.stack.mkdir()
        self.env = mock.patch.dict(os.environ, {"TF_WORKSPACE": "default", "TF_DATA_DIR": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, name, text):
        path = self.stack / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def inspect(self):
        return config.inspect_backend(self.stack)

    def test_empty_stack(self):
        self.assertEqual(self.inspect(), {
            "types": [], "declarations": [], "cloud": False, "metadata": None,
            "metadata_sha256": None, "source_sha256": {}, "workspace": "default",
        })

    def test_literal_and_unquoted_backend_labels_comments_and_override(self):
        self.write("main.tf", 'terraform /* comment */ {\n backend "oci" {}\n}\n')
        self.write("other_override.tf", 'terraform { backend\n s3 { key = "x" } }')
        result = self.inspect()
        self.assertEqual(result["types"], ["oci", "s3"])
        self.assertEqual(result["declarations"], [
            {"file": "main.tf", "type": "oci"}, {"file": "other_override.tf", "type": "s3"},
        ])

    def test_duplicate_declarations_are_preserved(self):
        self.write("main.tf", 'terraform { backend "oci" {} backend oci {} }')
        self.assertEqual(self.inspect()["declarations"], [{"file": "main.tf", "type": "oci"}] * 2)

    def test_escaped_backend_label(self):
        self.write("main.tf", r'terraform { backend "\u006fci" {} }')
        self.assertEqual(self.inspect()["types"], ["oci"])

    def test_strings_comments_heredocs_and_resource_backend_are_not_declarations(self):
        self.write("main.tf", '''# terraform { backend "s3" {} }
// terraform { backend "gcs" {} }
/* terraform { backend "azurerm" {} } */
locals {
  text = "terraform { backend \\"s3\\" {} }"
  nested = "${format("%s", { key = "terraform { backend oci {} }" })}"
  heredoc = <<-END
    terraform { backend "oci" {} }
    END
}
resource "oci_apigateway_deployment" "app" {
  specification { routes { backend { type = "HTTP_BACKEND" } } }
}
''')
        self.assertEqual(self.inspect()["types"], [])

    def test_backend_after_heredoc_is_detected(self):
        self.write("main.tf", 'locals { x = <<END\nignored\nEND\n}\nterraform { backend oci {} }')
        self.assertEqual(self.inspect()["types"], ["oci"])

    def test_cloud_block_detected(self):
        self.write("main.tf", 'terraform { cloud { organization = "synthetic" } }')
        self.assertTrue(self.inspect()["cloud"])

    def test_json_blocks_and_array_forms(self):
        self.write("backend.tf.json", json.dumps({"terraform": [
            {"backend": {"oci": [{}, {}]}}, {"cloud": {}},
        ]}))
        result = self.inspect()
        self.assertEqual(result["types"], ["oci"])
        self.assertEqual(result["declarations"], [{"file": "backend.tf.json", "type": "oci"}] * 2)
        self.assertTrue(result["cloud"])

    def test_json_resource_backend_does_not_count(self):
        self.write("main.tf.json", json.dumps({"resource": {"example": {"a": {"backend": {}}}}}))
        self.assertEqual(self.inspect()["types"], [])

    def test_source_hashes_include_automatic_inputs_and_lock(self):
        names = ["main.tf", "override.tf", "a_override.tf.json", ".terraform.lock.hcl",
                 "terraform.tfvars", "terraform.tfvars.json", "a.auto.tfvars", "a.auto.tfvars.json"]
        for name in names:
            self.write(name, "{}" if name.endswith(".json") else "# synthetic\n")
        self.write("manual.tfvars", "ignored = true")
        self.write("README.md", "ignored")
        result = self.inspect()
        self.assertEqual(set(result["source_sha256"]), set(names))
        for name in names:
            self.assertEqual(result["source_sha256"][name], hashlib.sha256((self.stack / name).read_bytes()).hexdigest())

    def test_stale_remote_metadata_survives_removed_declaration(self):
        backend = {"type": "oci", "config": {"key": "synthetic.tfstate"}, "hash": 123}
        path = self.write(".terraform/terraform.tfstate", json.dumps({"version": 3, "backend": backend}))
        result = self.inspect()
        self.assertEqual(result["types"], [])
        self.assertEqual(result["metadata"], backend)
        self.assertEqual(result["metadata_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_null_backend_metadata_is_still_hashed(self):
        self.write(".terraform/terraform.tfstate", '{"version":3,"backend":null}')
        self.assertIsNone(self.inspect()["metadata"])
        self.assertIsNotNone(self.inspect()["metadata_sha256"])

    def test_malformed_json_and_duplicates_fail_without_content(self):
        for content in ('{"terraform": {}, "terraform": {}}', '{"secret":"do-not-print",',
                        '{"terraform":{"backend":{"oci":{}}},"x":NaN}',
                        '{"terraform": {}, "x": 1e9999}',
                        '{"terraform":null}', '{"terraform":{"backend":[]}}',
                        '{"terraform":{"backend":{"oci":null}}}', '{"terraform":{"cloud":null}}'):
            with self.subTest(content=content):
                self.write("main.tf.json", content)
                with self.assertRaises(config.BackendConfigError) as error:
                    self.inspect()
                self.assertNotIn("do-not-print", str(error.exception))

    def test_invalid_metadata_is_not_treated_as_local(self):
        for data in ([], {"backend": []}, {"backend": {"type": "oci"}},
                     {"backend": {"type": "oci", "config": None}},
                     {"backend": {"type": "bad\nvalue", "config": {}}}):
            with self.subTest(data=data):
                self.write(".terraform/terraform.tfstate", json.dumps({"version": 3, **data} if isinstance(data, dict) else data))
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()
        self.write(".terraform/terraform.tfstate", '{"backend":{},"backend":null}')
        with self.assertRaises(config.BackendConfigError):
            self.inspect()

    def test_metadata_version_unknown_fields_and_case_aliases_refused(self):
        backend = {"type": "oci", "config": {}}
        for data in ({"backend": backend}, {"version": 4, "backend": backend},
                     {"version": 3, "Backend": backend}, {"version": 3, "BACKEND": backend},
                     {"version": 3, "backend": {**backend, "Type": "local"}},
                     {"version": 3, "backend": {**backend, "hash": True}},
                     {"version": 3, "future_backend": {}}, {"version": 3, "remote": {}}):
            with self.subTest(data=data):
                self.write(".terraform/terraform.tfstate", json.dumps(data))
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()

    def test_provider_state_store_is_refused_in_source_and_stale_metadata(self):
        for source in ('terraform { state_store "synthetic" {} }',
                       'terraform { state_store synthetic {} }'):
            self.write("main.tf", source)
            with self.assertRaises(config.BackendConfigError):
                self.inspect()
        (self.stack / "main.tf").unlink()
        self.write("main.tf.json", '{"terraform":{"state_store":{"synthetic":{}}}}')
        with self.assertRaises(config.BackendConfigError):
            self.inspect()
        (self.stack / "main.tf.json").unlink()
        self.write(".terraform/terraform.tfstate", '{"version":3,"state_store":{"type":"synthetic"}}')
        with self.assertRaises(config.BackendConfigError):
            self.inspect()

    def test_source_count_total_size_and_hcl_nesting_limits(self):
        self.write("main.tf", "locals { a = [] }")
        with mock.patch.object(config, "MAX_FILES", 0), self.assertRaises(config.BackendConfigError):
            self.inspect()
        with mock.patch.object(config, "MAX_TOTAL_BYTES", 1), self.assertRaises(config.BackendConfigError):
            self.inspect()
        self.write("main.tf", "locals { a = " + "[" * 130 + "0" + "]" * 130 + " }")
        with self.assertRaises(config.BackendConfigError):
            self.inspect()

    def test_automatic_json_variables_reject_duplicate_fields(self):
        self.write("settings.auto.tfvars.json", '{"a":1,"a":2}')
        with self.assertRaises(config.BackendConfigError):
            self.inspect()

    def test_malformed_hcl_or_backend_headers_are_refused(self):
        for source in ('terraform { backend {} }', 'terraform { backend "oci" = {} }',
                       'terraform { backend "${var.type}" {} }', 'terraform {',
                       'locals { x = "unterminated }', '/* unterminated',
                       'locals { x = <<END\nno terminator', 'terraform "label" {}',
                       'terraform { cloud = {} }', 'terraform { backend "oci" {} ] }'):
            with self.subTest(source=source):
                self.write("main.tf", source)
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()

    def test_nondefault_workspace_environment_and_file_refused(self):
        with mock.patch.dict(os.environ, {"TF_WORKSPACE": "production"}):
            with self.assertRaises(config.BackendConfigError):
                self.inspect()
        self.write(".terraform/environment", "production")
        with self.assertRaises(config.BackendConfigError):
            self.inspect()
        self.write(".terraform/environment", "default\n")
        self.assertEqual(self.inspect()["workspace"], "default")

    def test_data_directory_redirect_refused_but_default_allowed(self):
        for value in ("elsewhere", "../other", str(self.tmp / "other")):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"TF_DATA_DIR": value}):
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()
        for value in ("", ".terraform", str(self.stack / ".terraform")):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"TF_DATA_DIR": value}):
                self.assertEqual(self.inspect()["workspace"], "default")

    def test_symlink_stack_or_parent_refused(self):
        link = self.tmp / "link"
        link.symlink_to(self.stack, target_is_directory=True)
        with self.assertRaises(config.BackendConfigError):
            config.inspect_backend(link)
        sub = self.stack / "child"
        sub.mkdir()
        with self.assertRaises(config.BackendConfigError):
            config.inspect_backend(link / "child")

    def test_symlink_source_cache_or_workspace_refused(self):
        target = self.tmp / "outside"
        target.write_text("{}")
        for name in ("main.tf", ".terraform/terraform.tfstate", ".terraform/environment"):
            with self.subTest(name=name):
                path = self.stack / name
                path.parent.mkdir(exist_ok=True)
                path.symlink_to(target)
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()
                path.unlink()
        (self.stack / ".terraform").rmdir()
        (self.stack / ".terraform").symlink_to(self.tmp, target_is_directory=True)
        with self.assertRaises(config.BackendConfigError):
            self.inspect()

    def test_hardlinks_fifos_and_oversize_files_refused(self):
        for name in ("main.tf", ".terraform/terraform.tfstate"):
            with self.subTest(name=name):
                path = self.stack / name
                path.parent.mkdir(exist_ok=True)
                target = self.tmp / "linked"
                target.write_text("{}")
                os.link(target, path)
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()
                path.unlink()
                os.mkfifo(path)
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()
                path.unlink()
                path.write_bytes(b" " * (config.MAX_FILE_BYTES + 1))
                with self.assertRaises(config.BackendConfigError):
                    self.inspect()
                path.unlink()

    def test_actual_fullstack_terraform_is_local_without_configuration(self):
        result = config.inspect_backend(ROOT / "blueprints" / "fullstack-container" / "terraform")
        self.assertEqual(result["types"], [])
        self.assertFalse(result["cloud"])
        self.assertIn("apigateway.tf", result["source_sha256"])


if __name__ == "__main__":
    unittest.main()
