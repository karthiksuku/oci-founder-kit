"""Behavioural contract for the migration discovery scanner.

Fixtures in tests/fixtures/sources describe one small app the way each source
cloud would define it. Nothing here touches a network or a cloud account.
"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "oci-migrate-assess" / "scripts"))

import iac_scan as scan  # noqa: E402

SOURCES = ROOT / "tests" / "fixtures" / "sources"


def services(inv):
    return {f["service"] for f in inv["findings"]}


def by_type(inv, type_):
    return [f for f in inv["findings"] if f["type"] == type_]


class Terraform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = scan.scan_path(SOURCES / "aws-terraform")

    def test_detects_aws_as_the_source(self):
        self.assertEqual(set(self.inv["source_clouds"]), {"aws"})

    def test_maps_the_full_stack(self):
        expected = {"vpc-network", "firewall-rules", "container-registry", "container-service",
                    "load-balancer-l7", "managed-postgres", "object-storage", "cache-redis",
                    "message-queue", "identity-users", "secrets", "dns", "cdn", "logging"}
        self.assertEqual(expected - services(self.inv), set())

    def test_engine_comes_from_the_top_level_attribute_not_a_nested_block(self):
        [db] = by_type(self.inv, "aws_db_instance")
        self.assertEqual(db["attributes"]["engine"], "postgres")
        self.assertEqual(db["service"], "managed-postgres")

    def test_registry_module_is_recognised(self):
        [vpc] = [f for f in self.inv["findings"] if f["kind"] == "terraform-module"]
        self.assertEqual(vpc["service"], "vpc-network")
        self.assertTrue(vpc["type"].startswith("terraform-aws-modules/vpc/aws"))

    def test_findings_carry_file_and_line(self):
        [bucket] = by_type(self.inv, "aws_s3_bucket")
        self.assertEqual(bucket["file"], "main.tf")
        lines = (SOURCES / "aws-terraform" / "main.tf").read_text().splitlines()
        self.assertIn('resource "aws_s3_bucket" "uploads"', lines[bucket["line"] - 1])

    def test_unknown_cloud_resource_is_reported_not_dropped(self):
        self.assertIn("aws_appconfig_application", {u["type"] for u in self.inv["unmapped"]})
        self.assertEqual(by_type(self.inv, "aws_xray_sampling_rule")[0]["service"], "apm-tracing")

    def test_data_sources_are_ignored(self):
        self.assertFalse(by_type(self.inv, "aws_caller_identity"))

    def test_sdk_calls_in_application_code(self):
        sdk = {f["type"]: f["service"] for f in self.inv["findings"] if f["kind"] == "sdk"}
        self.assertEqual(sdk, {"@aws-sdk/client-s3": "object-storage", "@aws-sdk/client-sqs": "message-queue"})

    def test_dockerfile_means_container_ready(self):
        self.assertTrue(self.inv["container_ready"])
        self.assertEqual(self.inv["dockerfiles"], ["app/Dockerfile"])


class CloudFormation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = scan.scan_path(SOURCES / "aws-sam")

    def test_sam_and_cloudformation_types(self):
        got = {f["type"]: f["service"] for f in self.inv["findings"] if f["kind"] == "cloudformation"}
        self.assertEqual(got["AWS::Serverless::Function"], "serverless-functions")
        self.assertEqual(got["AWS::DynamoDB::Table"], "key-value-nosql")
        self.assertEqual(got["AWS::S3::Bucket"], "object-storage")
        self.assertEqual(got["AWS::Serverless::Api"], "api-gateway")

    def test_property_conditions(self):
        got = {f["type"]: f["service"] for f in self.inv["findings"] if f["kind"] == "cloudformation"}
        self.assertEqual(got["AWS::RDS::DBInstance"], "managed-mysql")
        self.assertEqual(got["AWS::ElasticLoadBalancingV2::LoadBalancer"], "load-balancer-l4")

    def test_event_types_inside_a_function_are_not_resources(self):
        self.assertFalse(by_type(self.inv, "Api"))

    def test_unmapped_and_python_sdk(self):
        self.assertIn("AWS::AppConfig::Application", {u["type"] for u in self.inv["unmapped"]})
        self.assertEqual(by_type(self.inv, "AWS::XRay::Group")[0]["service"], "apm-tracing")
        self.assertIn(("boto3", "cloud-sdk"), {(f["type"], f["service"]) for f in self.inv["findings"]})
        self.assertNotIn("requests", {f["type"] for f in self.inv["findings"]})


class Azure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = scan.scan_path(SOURCES / "azure")

    def test_bicep_resources_and_kinds(self):
        sites = {f["name"]: f["service"] for f in by_type(self.inv, "Microsoft.Web/sites")}
        self.assertEqual(sites, {"web": "container-service", "worker": "serverless-functions"})
        expected = {"managed-postgres", "object-storage", "secrets", "cache-redis", "message-queue", "apm-tracing"}
        self.assertEqual(expected - services(self.inv), set())

    def test_existing_bicep_references_are_skipped(self):
        self.assertFalse(by_type(self.inv, "Microsoft.Network/virtualNetworks"))

    def test_arm_child_types_are_qualified(self):
        types = {f["type"] for f in self.inv["findings"] if f["kind"] == "arm"}
        self.assertIn("Microsoft.Sql/servers/databases", types)
        self.assertIn("kubernetes", services(self.inv))
        self.assertIn("managed-sqlserver", services(self.inv))

    def test_azurerm_terraform_and_nuget(self):
        self.assertIn(("azurerm_cosmosdb_account", "document-db"),
                      {(f["type"], f["service"]) for f in self.inv["findings"]})
        nuget = {f["type"]: f["service"] for f in self.inv["findings"] if f["kind"] == "sdk"}
        self.assertEqual(nuget, {"Azure.Storage.Blobs": "object-storage", "Microsoft.Azure.Cosmos": "document-db"})


class GoogleCloud(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = scan.scan_path(SOURCES / "gcp")

    def test_database_version_selects_the_engine(self):
        [sql] = by_type(self.inv, "google_sql_database_instance")
        self.assertEqual(sql["service"], "managed-postgres")

    def test_module_subpath_selects_mysql(self):
        [mod] = [f for f in self.inv["findings"] if f["kind"] == "terraform-module"]
        self.assertEqual(mod["service"], "managed-mysql")

    def test_deployment_manager_and_go_modules(self):
        self.assertIn(("compute.v1.instance", "compute-vm"), {(f["type"], f["service"]) for f in self.inv["findings"]})
        go = {f["type"]: f["service"] for f in self.inv["findings"] if f["kind"] == "sdk"}
        self.assertEqual(go, {"cloud.google.com/go/storage": "object-storage", "cloud.google.com/go/pubsub": "cloud-sdk"})


class ContainersAndKubernetes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = scan.scan_path(SOURCES / "k8s-compose")

    def test_self_hosted_services_show_managed_opportunities(self):
        images = {f["type"]: f.get("opportunity") for f in self.inv["findings"] if f["kind"] == "image"}
        self.assertEqual(images, {"postgres": "managed-postgres", "redis": "cache-redis", "rabbitmq": "message-queue"})

    def test_kubernetes_cloud_coupling(self):
        signals = {c["signal"] for c in self.inv["coupling"]}
        self.assertEqual(signals, {"aws-load-balancer-annotation", "aws-alb-ingress", "aws-storage-class",
                                   "aws-pod-iam-role"})
        self.assertTrue(all(c["cloud"] == "aws" for c in self.inv["coupling"]))

    def test_maven_dependency(self):
        maven = {f["type"]: f["service"] for f in self.inv["findings"] if f["kind"] == "sdk"}
        self.assertEqual(maven, {"software.amazon.awssdk:s3": "object-storage"})


class MoreFormats(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="iac-formats-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_json_cloudformation_pyproject_and_gradle(self):
        (self.tmp / "stack.json").write_text(json.dumps({
            "AWSTemplateFormatVersion": "2010-09-09",
            "Resources": {"Db": {"Type": "AWS::RDS::DBInstance", "Properties": {"Engine": "postgres"}},
                          "Topic": {"Type": "AWS::SNS::Topic"}}}, indent=2))
        (self.tmp / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = ["google-cloud-storage>=2.0", "fastapi"]\n')
        (self.tmp / "build.gradle").write_text("dependencies {\n  implementation 'software.amazon.awssdk:dynamodb:2.28.0'\n}\n")
        inv = scan.scan_path(self.tmp)
        got = {(f["type"], f["service"]) for f in inv["findings"]}
        self.assertIn(("AWS::RDS::DBInstance", "managed-postgres"), got)
        self.assertIn(("AWS::SNS::Topic", "pub-sub-topic"), got)
        self.assertIn(("google-cloud-storage", "object-storage"), got)
        self.assertIn(("software.amazon.awssdk:dynamodb", "key-value-nosql"), got)
        self.assertNotIn("fastapi", {f["type"] for f in inv["findings"]})

    def test_malformed_files_are_skipped_not_fatal(self):
        (self.tmp / "broken.json").write_text("{not json")
        (self.tmp / "package.json").write_text("{also not json")
        (self.tmp / "pyproject.toml").write_text("not = [toml")
        (self.tmp / "main.tf").write_text('resource "aws_sqs_queue" "q" {\n  name = "q"\n}\n')
        inv = scan.scan_path(self.tmp)
        self.assertEqual([f["type"] for f in inv["findings"]], ["aws_sqs_queue"])

    def test_cli_writes_report_file(self):
        out = self.tmp / "report.md"
        code = scan.main([str(SOURCES / "gcp"), "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertIn("Migration assessment: gcp", out.read_text())


class Safety(unittest.TestCase):
    def test_skips_dependency_folders_and_never_reads_env_files(self):
        tmp = Path(tempfile.mkdtemp(prefix="iac-scan-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        block = 'resource "aws_s3_bucket" "x" {\n  bucket = "x"\n}\n'
        for rel in ("node_modules/pkg/main.tf", ".terraform/modules/m/main.tf", "vendor/x.tf", ".env",
                    ".env.production"):
            path = tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(block)
        (tmp / "main.tf").write_text(block)
        inv = scan.scan_path(tmp)
        self.assertEqual([f["file"] for f in inv["findings"]], ["main.tf"])

    def test_paths_in_output_are_relative(self):
        inv = scan.scan_path(SOURCES / "gcp")
        self.assertTrue(all(not f["file"].startswith("/") for f in inv["findings"]))
        self.assertEqual(inv["root"], "gcp")


class Summary(unittest.TestCase):
    def test_services_summary_and_effort(self):
        inv = scan.scan_path(SOURCES)
        self.assertEqual(set(inv["source_clouds"]), {"aws", "azure", "gcp"})
        summary = {s["id"]: s for s in inv["services"]}
        self.assertEqual(summary["managed-postgres"]["oci"]["terraform"], ["oci_psql_db_system"])
        self.assertGreaterEqual(summary["object-storage"]["count"], 4)
        self.assertIn(inv["effort"]["size"], ("S", "M", "L", "XL"))
        self.assertGreater(inv["effort"]["score"], 0)

    def test_services_are_ordered_hardest_first(self):
        inv = scan.scan_path(SOURCES)
        order = {"gap": 0, "partial": 1, "equivalent": 2}
        fits = [order[s["fit"]] for s in inv["services"]]
        self.assertEqual(fits, sorted(fits))

    def test_markdown_report(self):
        md = scan.render_markdown(scan.scan_path(SOURCES / "aws-terraform"))
        for text in ("Migration assessment", "OCI Database with PostgreSQL", "Partial fits and gaps",
                     "Not recognised", "aws_appconfig_application", "@aws-sdk/client-s3"):
            self.assertIn(text, md)

    def test_output_is_deterministic(self):
        a = json.dumps(scan.scan_path(SOURCES), sort_keys=True)
        b = json.dumps(scan.scan_path(SOURCES), sort_keys=True)
        self.assertEqual(a, b)


class Cli(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = scan.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_json_output(self):
        code, out, _ = self.run_main([str(SOURCES / "gcp"), "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["schema"], "oci-migration-inventory/1")

    def test_missing_path_exits_2(self):
        code, _, err = self.run_main([str(SOURCES / "does-not-exist")])
        self.assertEqual(code, 2)
        self.assertIn("not a directory", err)


if __name__ == "__main__":
    unittest.main()
