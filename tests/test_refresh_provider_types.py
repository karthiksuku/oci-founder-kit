"""Regression tests for the provider type refresher, with the network mocked."""

import gzip
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh_provider_types as rpt  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def registry_payload(titles):
    docs = [{"title": t, "category": "resources", "language": "hcl"} for t in titles]
    docs.append({"title": "ignored_data_source", "category": "data-sources", "language": "hcl"})
    docs.append({"title": "python_only", "category": "resources", "language": "python"})
    return FakeResponse(json.dumps({"version": "9.9.9", "docs": docs}).encode())


class Registry(unittest.TestCase):
    def test_prefix_is_added_once(self):
        # Google titles some pages with the full type name; AWS does not.
        with mock.patch.object(rpt.urllib.request, "urlopen",
                               return_value=registry_payload(["google_service_account", "storage_bucket"])):
            version, types, _ = rpt.from_registry("hashicorp/google", "google_")
        self.assertEqual(version, "9.9.9")
        self.assertEqual(types, ["google_service_account", "google_storage_bucket"])


class CloudFormationSpec(unittest.TestCase):
    def spec(self):
        return json.dumps({"ResourceSpecificationVersion": "1.2.3",
                           "ResourceTypes": {"AWS::S3::Bucket": {}, "AWS::SQS::Queue": {}}}).encode()

    def test_gzipped_and_plain_spec(self):
        for body in (gzip.compress(self.spec()), self.spec()):
            with mock.patch.object(rpt.urllib.request, "urlopen", return_value=FakeResponse(body)):
                version, types, _ = rpt.from_cloudformation_spec()
            self.assertEqual((version, types), ("1.2.3", ["AWS::S3::Bucket", "AWS::SQS::Queue"]))


class Main(unittest.TestCase):
    def test_writes_fixture_files_without_terraform(self):
        tmp = Path(tempfile.mkdtemp(prefix="rpt-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        with mock.patch.object(rpt, "OUT", tmp), \
                mock.patch.object(rpt.shutil, "which", return_value=None), \
                mock.patch.object(rpt.urllib.request, "urlopen",
                                  side_effect=lambda *a, **k: registry_payload(["core_vcn"])), \
                redirect_stdout(io.StringIO()):
            code = rpt.main(["--providers", "oci"])
        self.assertEqual(code, 0)
        record = json.loads((tmp / "oci.json").read_text())
        self.assertEqual(record["resource_types"], ["oci_core_vcn"])
        self.assertIn("Terraform Registry", record["_note"])

    def test_cloudformation_fixture(self):
        tmp = Path(tempfile.mkdtemp(prefix="rpt-cfn-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        body = gzip.compress(CloudFormationSpec().spec())
        with mock.patch.object(rpt, "OUT", tmp), \
                mock.patch.object(rpt.urllib.request, "urlopen", return_value=FakeResponse(body)), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(rpt.main(["--providers", "cloudformation"]), 0)
        record = json.loads((tmp / "cloudformation.json").read_text())
        self.assertEqual(record["version"], "1.2.3")
        self.assertIn("SAM", record["_note"])


class Schema(unittest.TestCase):
    def test_reads_types_and_version_from_terraform(self):
        schema = {"provider_schemas": {"registry.terraform.io/oracle/oci": {
            "resource_schemas": {"oci_core_vcn": {}, "oci_core_subnet": {}}}}}

        def fake_run(cmd, cwd, **kwargs):
            if cmd[1] == "init":
                Path(cwd, ".terraform.lock.hcl").write_text(
                    'provider "registry.terraform.io/oracle/oci" {\n  version     = "9.10.0"\n}\n')
                return mock.Mock(stdout=b"")
            return mock.Mock(stdout=json.dumps(schema).encode())

        with mock.patch.object(rpt.subprocess, "run", side_effect=fake_run):
            version, types, method = rpt.from_schema("oracle/oci")
        self.assertEqual(version, "9.10.0")
        self.assertEqual(types, ["oci_core_subnet", "oci_core_vcn"])
        self.assertIn("schema", method)


if __name__ == "__main__":
    unittest.main()
