"""Pin the minimal foundation's permission boundary and plan target contract."""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "blueprints" / "foundation" / "terraform"
MAIN = (TF / "main.tf").read_text()
VARIABLES = (TF / "variables.tf").read_text()
SOURCE = "\n".join(p.read_text() for p in TF.glob("*.tf"))


def validation_pattern(name):
    body = re.search(rf'variable "{name}" \{{(.*?)(?=\nvariable |\Z)', VARIABLES, re.S).group(1)
    escaped = re.search(r'can\(regex\(("(?:[^"\\]|\\.)*")', body).group(1)
    return re.compile(json.loads(escaped))


class FoundationContract(unittest.TestCase):
    def test_tenancy_identity_is_explicit_and_cannot_be_a_compartment(self):
        pattern = validation_pattern("tenancy_ocid")
        self.assertTrue(pattern.fullmatch("ocid1.tenancy.oc1..exampleaccount"))
        for value in ("ocid1.compartment.oc1..exampleparent", "", "ocid1.tenancy.oc1..account' in tenancy"):
            self.assertIsNone(pattern.fullmatch(value), value)

    def test_provider_binds_expected_account_region_profile_and_authentication(self):
        provider = (TF / "versions.tf").read_text().split('provider "oci" {', 1)[1]
        for field in ("tenancy_ocid", "region", "config_file_profile", "auth"):
            self.assertRegex(provider, rf'\b{field}\s*=\s*var\.{field}\b')

    def test_parent_requires_compartment_and_rejects_root_or_policy_injection(self):
        pattern = validation_pattern("compartment_ocid")
        self.assertTrue(pattern.fullmatch("ocid1.compartment.oc1..exampleparent"))
        self.assertTrue(pattern.fullmatch("ocid1.compartment.oc2..exampleparent"))
        for value in ("ocid1.tenancy.oc1..exampleroot", "", "ocid1.compartment.oc1..parent' in tenancy", "parent"):
            self.assertIsNone(pattern.fullmatch(value), value)

    def test_group_is_an_explicit_ocid_and_cannot_inject_a_policy_subject(self):
        pattern = validation_pattern("developer_group_ocid")
        self.assertTrue(pattern.fullmatch("ocid1.group.oc1..examplegroup"))
        for value in ("Administrators", "ocid1.user.oc1..exampleuser", "ocid1.group.oc1..x, any-user", ""):
            self.assertIsNone(pattern.fullmatch(value), value)

    def test_developer_access_is_inspection_of_new_child_only(self):
        statements = re.findall(r'"(Allow group [^"\n]+)"', MAIN)
        self.assertEqual(statements, [
            "Allow group id ${var.developer_group_ocid} to inspect all-resources in compartment id ${oci_identity_compartment.workload.id}"
        ])
        self.assertNotIn(" in tenancy", MAIN)
        self.assertNotIn(" to manage ", MAIN)
        self.assertNotIn("any-user", MAIN)

    def test_compartment_and_policy_have_different_deliberate_parent_boundaries(self):
        self.assertRegex(MAIN, r'resource "oci_identity_compartment" "workload" \{\s+compartment_id = var.compartment_ocid')
        self.assertRegex(MAIN, r'resource "oci_identity_policy" "developer_inspect" \{\s+compartment_id = oci_identity_compartment.workload.id')

    def test_only_documented_bootstrap_resources_are_created(self):
        types = re.findall(r'resource "([a-z0-9_]+)"', SOURCE)
        self.assertCountEqual(types, ["oci_identity_compartment", "oci_identity_policy"])
        known = json.loads((ROOT / "tests" / "fixtures" / "provider-types" / "oci.json").read_text())["resource_types"]
        self.assertFalse(set(types) - set(known))

    def test_no_keys_tokens_or_secret_values_are_accepted_as_terraform_inputs(self):
        names = set(re.findall(r'variable "([a-z0-9_]+)"', VARIABLES))
        self.assertEqual(names, {"tenancy_ocid", "compartment_ocid", "developer_group_ocid", "workload_name", "region", "config_file_profile", "auth"})
        self.assertNotIn("private_key", SOURCE)

    def test_gate_can_identify_the_selected_parent_profile_and_region(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("foundation_gate", ROOT / "skills" / "oci-deploy" / "scripts" / "deploy_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        values = {"compartment_ocid": "ocid1.compartment.oc1..exampleparent", "config_file_profile": "BOOTSTRAP", "region": "ap-sydney-1"}
        summary = gate.describe_plan({"variables": {key: {"value": value} for key, value in values.items()}})
        self.assertEqual(summary["target"], {"compartment_ocid": values["compartment_ocid"], "profile": "BOOTSTRAP", "region": "ap-sydney-1"})

    @unittest.skipUnless(shutil.which("terraform"), "terraform not installed")
    def test_terraform_format(self):
        result = subprocess.run(["terraform", "fmt", "-check", "-recursive"], cwd=TF, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
