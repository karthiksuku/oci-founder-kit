"""Integrity of the migration service map.

The OCI side is checked against the real OCI Terraform provider schema
(tests/fixtures/provider-types/oci.json), so a renamed or invented resource
type fails here rather than in a user's plan.
"""

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SMAP = json.loads((ROOT / "skills" / "oci-migrate-assess" / "assets" / "service-map.json").read_text())
OCI_TYPES = set(json.loads((ROOT / "tests" / "fixtures" / "provider-types" / "oci.json").read_text())["resource_types"])
CLOUDS = ("aws", "azure", "gcp")


def iter_rules():
    """Yield (cloud, kind, key_or_pattern, entry) for every rule."""
    for cloud, kinds in SMAP["rules"].items():
        for kind, rules in kinds.items():
            if isinstance(rules, dict):
                for key, value in rules.items():
                    for entry in value if isinstance(value, list) else [{"service": value}]:
                        yield cloud, kind, key, entry
            else:
                for entry in rules:
                    yield cloud, kind, entry["pattern"], entry


class Services(unittest.TestCase):
    def test_every_service_is_complete(self):
        for sid, svc in SMAP["services"].items():
            with self.subTest(sid):
                self.assertIn(svc["fit"], ("equivalent", "partial", "gap"))
                self.assertIn(svc["complexity"], ("low", "medium", "high"))
                self.assertTrue(svc["oci"]["name"])
                self.assertEqual(urlparse(svc["oci"]["docs"]).scheme, "https")
                self.assertEqual(set(svc["sources"]), set(CLOUDS))
                self.assertIsInstance(svc["differences"], list)
                self.assertTrue(svc["migration"])
                if svc["fit"] != "equivalent":
                    self.assertTrue(svc["differences"], f"{sid} is {svc['fit']} but names no differences")

    def test_oci_terraform_types_exist_in_the_provider(self):
        for sid, svc in SMAP["services"].items():
            for tf_type in svc["oci"]["terraform"]:
                with self.subTest(service=sid, type=tf_type):
                    self.assertIn(tf_type, OCI_TYPES)

    def test_alternatives_point_at_real_services(self):
        for sid, svc in SMAP["services"].items():
            for alt in svc.get("alternatives", []):
                with self.subTest(sid):
                    self.assertIn(alt["service"], SMAP["services"])


class Rules(unittest.TestCase):
    def test_every_rule_points_at_a_service(self):
        for cloud, kind, key, entry in iter_rules():
            with self.subTest(cloud=cloud, kind=kind, key=key):
                self.assertIn(entry["service"], SMAP["services"])
                if "opportunity" in entry:
                    self.assertIn(entry["opportunity"], SMAP["services"])

    def test_patterns_and_conditions_compile(self):
        for cloud, kind, key, entry in iter_rules():
            with self.subTest(cloud=cloud, kind=kind, key=key):
                if "pattern" in entry:
                    re.compile(entry["pattern"])
                for regex in entry.get("when", {}).values():
                    re.compile(regex)

    def test_conditional_lists_end_with_a_fallback_or_are_exhaustive(self):
        for cloud, kinds in SMAP["rules"].items():
            for kind, rules in kinds.items():
                if not isinstance(rules, dict):
                    continue
                for key, value in rules.items():
                    if isinstance(value, list):
                        with self.subTest(cloud=cloud, key=key):
                            self.assertNotIn("when", value[-1], "the last entry must be an unconditional fallback")

    def test_arm_types_are_lowercase(self):
        for key in SMAP["rules"]["azure"]["arm"]:
            self.assertEqual(key, key.lower())

    def test_source_terraform_types_exist_or_are_noted(self):
        notes = SMAP["source_type_notes"]
        for cloud, provider in (("aws", "aws"), ("azure", "azurerm"), ("gcp", "google")):
            known = set(json.loads((ROOT / "tests" / "fixtures" / "provider-types" / f"{provider}.json")
                                   .read_text())["resource_types"])
            for key in SMAP["rules"][cloud]["terraform"]:
                with self.subTest(key):
                    self.assertTrue(key in known or key in notes,
                                    f"{key} is not in {provider}'s current resource list and has no note")

    def test_cloudformation_types_exist_in_the_spec(self):
        spec = set(json.loads((ROOT / "tests" / "fixtures" / "provider-types" / "cloudformation.json")
                              .read_text())["resource_types"])
        for key in SMAP["rules"]["aws"]["cloudformation"]:
            with self.subTest(key):
                self.assertTrue(key in spec or key.startswith("AWS::Serverless::"))

    def test_noted_types_are_still_needed(self):
        used = {key for cloud in CLOUDS for key in SMAP["rules"][cloud]["terraform"]}
        self.assertEqual(set(SMAP["source_type_notes"]) - used, set())

    def test_terraform_types_carry_their_provider_prefix(self):
        prefixes = {"aws": "aws_", "azure": "azurerm_", "gcp": "google_"}
        for cloud in CLOUDS:
            for key in SMAP["rules"][cloud]["terraform"]:
                with self.subTest(key):
                    self.assertTrue(key.startswith(prefixes[cloud]))

    def test_every_service_is_reachable_from_a_rule(self):
        used = {entry["service"] for *_, entry in iter_rules()}
        used |= {entry["opportunity"] for *_, entry in iter_rules() if "opportunity" in entry}
        self.assertEqual(set(SMAP["services"]) - used, set())

    def test_each_cloud_covers_the_core_categories(self):
        core = {"compute-vm", "container-service", "kubernetes", "serverless-functions", "managed-postgres",
                "object-storage", "vpc-network", "load-balancer-l7", "message-queue", "secrets", "dns"}
        for cloud in CLOUDS:
            with self.subTest(cloud):
                services = {entry["service"] for c, kind, _, entry in iter_rules() if c == cloud and kind == "terraform"}
                self.assertEqual(core - services, set())


if __name__ == "__main__":
    unittest.main()
