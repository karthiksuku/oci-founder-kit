"""Offline boundary checks for the reviewed human-operator IAM templates.

Native Terraform mocks separately test evaluated statements and invalid inputs.
These checks guard the source surface and verify the unchanged deploy gate flags
both policies for review without exposing the private statements in its summary.
"""

import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "blueprints" / "workload-access" / "terraform"
spec = importlib.util.spec_from_file_location("workload_access_gate", ROOT / "skills/oci-deploy/scripts/deploy_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class WorkloadAccess(unittest.TestCase):
    def setUp(self):
        self.main = (STACK / "main.tf").read_text()
        self.variables = (STACK / "variables.tf").read_text()
        self.versions = (STACK / "versions.tf").read_text()

    def test_only_two_compartment_attached_policies_and_no_execution_hooks(self):
        resources = re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', self.main)
        self.assertEqual(resources, [("oci_identity_policy", "application"), ("oci_identity_policy", "state")])
        self.assertIn("compartment_id = var.compartment_ocid", self.main)
        self.assertIn("compartment_id = var.state_compartment_ocid", self.main)
        for source in STACK.glob("*.tf"):
            self.assertNotRegex(source.read_text(), r'(?m)^\s*(?:provisioner\s+"|data\s+"external")')

    def test_selected_group_and_targets_cannot_be_substituted_by_arbitrary_policy_input(self):
        declared = set(re.findall(r'variable\s+"([^"]+)"', self.variables))
        self.assertEqual(declared, {"tenancy_ocid", "compartment_ocid", "state_compartment_ocid",
                                   "developer_group_ocid", "role", "name", "registry_name", "state_bucket_name",
                                   "region", "home_region", "config_file_profile", "auth"})
        self.assertIn('subject = "Allow group id ${var.developer_group_ocid}"', self.main)
        self.assertNotRegex(self.variables, r'\bdefault\s*=')
        self.assertEqual(self.main.count("var.compartment_ocid != var.state_compartment_ocid"), 2)
        self.assertEqual(self.main.count("var.region == var.home_region"), 2)

    def test_no_tenancy_wide_data_or_identity_grants(self):
        for forbidden in ("in tenancy", "all-resources", "manage policies", "manage groups", "manage users",
                          "manage compartments", "manage dynamic-groups", "object-family", " to read objects",
                          " to manage objects", "secret-bundles", "PAR_MANAGE", "BUCKET_DELETE", "BUCKET_UPDATE",
                          "OBJECT_READ", "OBJECT_CREATE", "OBJECT_DELETE", "RETENTION_RULE_", "REPOSITORY_DELETE",
                          "REPOSITORY_UPDATE", "REPOSITORY_MANAGE", "virtual-network-family"):
            self.assertNotIn(forbidden, self.main)
        self.assertIn("target.repo.name = '${var.registry_name}'", self.main)
        self.assertIn("target.bucket.name = '${var.state_bucket_name}'", self.main)
        self.assertIn("request.permission = '${permission}'", self.main)

    def test_pinned_provider_is_same_reviewed_lock_as_foundation(self):
        self.assertIn('source  = "oracle/oci"', self.versions)
        self.assertIn('version = "= 9.10.0"', self.versions)
        self.assertEqual((STACK / ".terraform.lock.hcl").read_bytes(),
                         (ROOT / "blueprints/workload-foundation/registry/.terraform.lock.hcl").read_bytes())
        self.assertNotRegex(self.versions, r'\b(?:private_key|private_key_path|pass_phrase|security_token)\s*=')

    def test_existing_gate_marks_both_attachments_as_access_changes(self):
        private_marker = "PRIVATE-POLICY-CONTENT-MUST-NOT-APPEAR"
        plan = {
            "terraform_version": "1.16.6",
            "variables": {name: {"value": value} for name, value in {
                "region": "us-phoenix-1", "home_region": "us-phoenix-1",
                "compartment_ocid": "ocid1.compartment.oc1..syntheticapp",
                "state_compartment_ocid": "ocid1.compartment.oc1..syntheticstate",
                "tenancy_ocid": "ocid1.tenancy.oc1..synthetictenancy",
                "config_file_profile": "SYNTHETIC", "auth": "SecurityToken"}.items()},
            "resource_changes": [
                {"address": f"oci_identity_policy.{name}", "type": "oci_identity_policy", "mode": "managed",
                 "change": {"actions": ["create"], "after": {"compartment_id": compartment,
                            "statements": [private_marker]}}}
                for name, compartment in (("application", "ocid1.compartment.oc1..syntheticapp"),
                                          ("state", "ocid1.compartment.oc1..syntheticstate"))],
        }
        result = gate.describe_plan(plan)
        self.assertEqual(result["access_changes"], ["oci_identity_policy.application", "oci_identity_policy.state"])
        self.assertEqual(result["changes"], {"create": 2, "update": 0, "delete": 0, "replace": 0})
        self.assertEqual(result["target"]["home_region"], "us-phoenix-1")
        self.assertNotIn(private_marker, json.dumps(result))
        # The gate headline names the canonical app target. The full plan is
        # additionally required to review the separate state policy attachment.
        self.assertEqual(result["target"]["compartment_ocid"], "ocid1.compartment.oc1..syntheticapp")

    def test_native_mock_cases_cover_rejected_target_and_policy_inputs(self):
        source = (STACK / "tests/access.tftest.hcl").read_text()
        self.assertIn('mock_provider "oci" {}', source)
        cases = set(re.findall(r'run\s+"([^"]+)"', source))
        self.assertEqual(cases, {"foundation_grants_are_bounded", "observer_has_no_mutation_grants",
                               "reject_tenancy_as_application", "reject_tenancy_as_state", "reject_shared_app_state",
                               "reject_wrong_home_region", "reject_user_as_group", "reject_wildcard_repository",
                               "reject_bucket_policy_injection", "reject_unsupported_role", "reject_implicit_auth"})
        self.assertNotRegex(source, r'\bcommand\s*=\s*apply\b')

    def test_documented_boundary_and_examples_do_not_claim_oci_acceptance(self):
        document = (STACK.parent / "README.md").read_text()
        self.assertIn("No live policy apply or denial", document)
        self.assertIn("inherited", document.lower())
        self.assertIn("full private Terraform plan", document)
        self.assertIn("no credential inputs", document)
        self.assertNotIn("ocid1.", (STACK / "terraform.tfvars.example").read_text())


if __name__ == "__main__":
    unittest.main()
