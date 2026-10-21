"""Static guarantees of the fullstack-container golden path.

These pin the security properties of the Terraform so a later edit cannot
quietly open the app to the internet or widen IAM. Optional checks run
`terraform fmt` and `node --test` when those tools are installed.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints" / "fullstack-container"
TF = BLUEPRINT / "terraform"
OCI_TYPES = set(json.loads((ROOT / "tests" / "fixtures" / "provider-types" / "oci.json").read_text())["resource_types"])
SOURCE = "\n".join(p.read_text() for p in sorted(TF.glob("*.tf")))


def blocks(kind, rtype):
    """Bodies of `kind "rtype" "name" { ... }` blocks, brace-matched."""
    found = {}
    for match in re.finditer(rf'{kind}\s+"{rtype}"\s+"([^"]+)"\s*\{{', SOURCE):
        depth, i = 0, match.end() - 1
        while i < len(SOURCE):
            depth += {"{": 1, "}": -1}.get(SOURCE[i], 0)
            if depth == 0:
                break
            i += 1
        found[match.group(1)] = SOURCE[match.end():i]
    return found


class Resources(unittest.TestCase):
    def test_every_oci_resource_type_exists_in_the_provider(self):
        types = set(re.findall(r'resource\s+"(oci_[a-z0-9_]+)"', SOURCE))
        self.assertTrue(types)
        self.assertEqual(types - OCI_TYPES, set())

    def test_provider_is_pinned_and_lock_file_is_committed(self):
        self.assertIn('version = "~> 9.10"', SOURCE)
        self.assertTrue((TF / ".terraform.lock.hcl").exists())


class Network(unittest.TestCase):
    def test_ingress_has_no_default(self):
        var = re.search(r'variable\s+"allowed_ingress_cidrs"\s*\{(.*?)\n\}', SOURCE, re.S).group(1)
        self.assertIsNone(re.search(r"^\s*default\s*=", var, re.M))

    def test_only_the_load_balancer_accepts_client_ranges(self):
        rules = blocks("resource", "oci_core_network_security_group_security_rule")
        for name, body in rules.items():
            if 'direction                 = "INGRESS"' in body and "CIDR_BLOCK" in body:
                self.assertIn("oci_core_network_security_group.lb.id", body, name)
                self.assertIn("var.allowed_ingress_cidrs", SOURCE)
                self.assertNotIn('"0.0.0.0/0"', body, name)

    def test_app_and_database_accept_traffic_only_from_their_neighbour(self):
        rules = blocks("resource", "oci_core_network_security_group_security_rule")
        self.assertIn("oci_core_network_security_group.lb.id", rules["app_in_lb"])
        self.assertIn("oci_core_network_security_group.app.id", rules["db_in_app"])

    def test_default_security_list_is_replaced_and_private_subnet_has_no_public_ips(self):
        subnets = blocks("resource", "oci_core_subnet")
        for body in subnets.values():
            self.assertIn("oci_core_security_list.none.id", body)
        self.assertIn("prohibit_public_ip_on_vnic = true", subnets["private"])
        self.assertNotIn("ingress_security_rules", blocks("resource", "oci_core_security_list")["none"])

    def test_container_has_no_public_ip(self):
        body = blocks("resource", "oci_container_instances_container_instance")["app"]
        self.assertIn("is_public_ip_assigned = false", body)


class Access(unittest.TestCase):
    def test_policy_is_scoped_to_the_bucket(self):
        policy = blocks("resource", "oci_identity_policy")["app"]
        statements = re.findall(r'"(Allow [^"]+)"', policy)
        self.assertEqual(len(statements), 2)
        for statement in statements:
            self.assertIn("target.bucket.name", statement)
            self.assertNotIn("all-resources", statement)

    def test_dynamic_group_matches_container_instances_in_the_compartment(self):
        group = blocks("resource", "oci_identity_dynamic_group")["app"]
        self.assertIn("resource.type = 'computecontainerinstance'", group)
        self.assertIn("resource.compartment.id = '${var.compartment_ocid}'", group)

    def test_compartment_cannot_be_the_root(self):
        self.assertIn('regex("^ocid1\\\\.compartment\\\\."', SOURCE)


class App(unittest.TestCase):
    def test_database_tls_is_never_disabled_in_code(self):
        code = "\n".join(p.read_text() for p in (BLUEPRINT / "app" / "src").rglob("*.js"))
        self.assertNotIn("rejectUnauthorized: false", code)

    def test_image_runs_as_non_root(self):
        self.assertIn("USER node", (BLUEPRINT / "app" / "Dockerfile").read_text())


class Tools(unittest.TestCase):
    @unittest.skipUnless(shutil.which("terraform"), "terraform not installed")
    def test_terraform_fmt(self):
        result = subprocess.run(["terraform", "fmt", "-check", "-recursive"], cwd=TF, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node") and (BLUEPRINT / "app" / "node_modules").exists(),
                         "node or app dependencies not installed")
    def test_app_unit_tests(self):
        result = subprocess.run(["node", "--test"], cwd=BLUEPRINT / "app", capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
