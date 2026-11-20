"""A launch cost forecast keeps incomplete pricing and observed use distinct."""
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("launch_cost", ROOT / "scripts/launch_cost.py")
cost = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost)


class LaunchCost(unittest.TestCase):
    def setUp(self):
        self.rates = json.loads((ROOT / "recipes/launch-cost/rates.json").read_text())
        self.today = max(date.fromisoformat(row["price_source"]["checked_at"])
                         for row in self.rates["options"]["oci"]["lines"])
        self.env = {"name": "rehearsal", "role": "rehearsal", "blueprint": "web-container",
                    "target": {"ocpus": 1, "memory_gbs": 2}}
        self.binding = "a" * 64

    def forecast(self, assumptions=None, cleanup=None, attached=True):
        return cost.forecast(self.env, self.binding, self.rates, assumptions, cleanup,
                             attached=attached, today=self.today)

    def test_default_uses_dated_fixed_units_without_free_tier_or_invented_bill(self):
        result = self.forecast()
        rates = result["infrastructure"]
        expected = sum(row["quantity"] * row["unit_usd"] for row in rates)
        self.assertEqual(result["demo_24h"]["known_usd"], round(expected * 24, 4))
        self.assertEqual(result["run_30d"]["known_usd"], round(expected * 720, 4))
        self.assertGreater(rates[2]["unit_usd"], 0)
        self.assertIsNone(result["demo_24h"]["estimate_usd"])
        self.assertIsNone(result["retained_30d"]["estimate_usd"])
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["approval_granted"])

    def test_missing_shape_modified_blueprint_and_stale_rates_cannot_produce_known_amounts(self):
        self.env["target"].pop("memory_gbs")
        self.assertIn("container_memory", self.forecast()["demo_24h"]["unknown"])
        self.assertIsNone(self.forecast(attached=False)["demo_24h"]["known_usd"])
        self.today += timedelta(days=31)
        self.assertIsNone(self.forecast()["run_30d"]["known_usd"])

    def test_wrong_sku_or_unit_is_unknown_instead_of_a_price_for_the_wrong_resource(self):
        self.rates["options"]["oci"]["lines"][0]["price_source"]["metric"] = "GB per month"
        self.rates["options"]["oci"]["lines"][1]["price_source"]["part_number"] = "B93030"
        self.assertEqual(self.forecast()["demo_24h"]["unknown"][:2], ["container_cpu", "container_memory"])

    def test_reviewed_extras_and_post_cleanup_inventory_are_bound_and_compared(self):
        inputs = self.forecast()["assumptions_template"]
        for row in inputs["items"].values():
            for key in row:
                row[key] = 0
        inputs["items"]["registry"].update(demo_24h_usd=1, run_30d_usd=3, kept_count=1, kept_30d_usd=3)
        report = self.forecast(inputs)
        self.assertEqual(report["status"], "estimated")
        self.assertEqual(report["retained_30d"]["estimate_usd"], 3)
        after = report["cleanup_template"]
        after["inventory_evidence_sha256"] = "b" * 64
        for row in after["items"].values():
            row.update(count=0, usd_30d=0)
        after["items"]["registry"].update(count=2, usd_30d=5)
        comparison = self.forecast(inputs, after)["after_cleanup"]
        self.assertEqual(comparison["estimated_delta_30d_usd"], 2)
        self.assertEqual(comparison["items"]["registry"]["count_delta"], 1)
        self.assertEqual(comparison["basis"], "owner-reviewed inventory and repricing")
        original_day = self.today
        self.today += timedelta(days=90)
        after["as_of"] = self.today.isoformat()
        later = self.forecast(inputs, after)
        self.assertTrue(later["historical_comparison"])
        self.assertEqual(later["estimate_sha256"], report["estimate_sha256"])
        self.assertEqual(later["after_cleanup"]["estimated_delta_30d_usd"], 2)
        self.today = original_day
        after["as_of"] = self.today.isoformat()
        del after["items"]["object_storage"]
        incomplete = self.forecast(inputs, after)
        self.assertIsNone(incomplete["after_cleanup"]["estimated_delta_30d_usd"])
        self.assertEqual(incomplete["status"], "incomplete")
        inputs["items"]["registry"]["kept_30d_usd"] = 4
        with self.assertRaises(ValueError):
            self.forecast(inputs, after)

    def test_wrong_environment_stale_or_invalid_owner_inputs_do_not_count(self):
        inputs = self.forecast()["assumptions_template"]
        inputs["environment"] = "production"
        with self.assertRaises(ValueError):
            self.forecast(inputs)

        inputs["environment"] = "rehearsal"
        inputs["items"]["registry"]["run_30d_usd"] = True
        with self.assertRaises(ValueError):
            self.forecast(inputs)
        inputs["items"]["registry"]["run_30d_usd"] = 5
        inputs["as_of"] = (self.today - timedelta(days=60)).isoformat()
        with self.assertRaises(ValueError):
            self.forecast(inputs)

    def test_cli_binds_private_inputs_to_real_environment_and_refuses_world_readable_data(self):
        project_spec = importlib.util.spec_from_file_location("cost_project", ROOT / "scripts/project.py")
        p = importlib.util.module_from_spec(project_spec)
        project_spec.loader.exec_module(p)
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "app"
            infra = project / "deploy"
            infra.mkdir(parents=True)
            for item in (ROOT / "blueprints/web-container/terraform").glob("*.tf"):
                (infra / item.name).write_bytes(item.read_bytes())
            with p.Store(project, create=True, write=True) as store:
                now = int(time.time())
                store.save({"schema": p.SCHEMA, "task": "build", "mode": "existing", "agent": "both",
                            "stack": "nextjs", "blueprint": None, "project_identity": p.identity(store.root_fd),
                            "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                            "kit_sha256": p.kit_fingerprint(), "records": {}})
            p.helper("environments").create(project, name="rehearsal", role="rehearsal", infrastructure="deploy",
                                            target={"ocpus": 1, "memory_gbs": 2})
            # Refresh the synthetic rate dates so future offline test runs exercise the priced path.
            for row in self.rates["options"]["oci"]["lines"]:
                row["price_source"]["checked_at"] = datetime.now(timezone.utc).date().isoformat()
            rates = Path(temporary) / "rates.json"
            rates.write_text(json.dumps(self.rates))
            rates.chmod(0o600)
            cmd = [sys.executable, str(ROOT / "scripts/kit.py"), "cost", "preview", "--project", str(project),
                   "--environment", "rehearsal", "--rates", str(rates), "--json"]
            result = subprocess.run(cmd, capture_output=True, check=False)
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 3)
            self.assertTrue(payload["blueprint_source_verified"])
            self.assertFalse(payload["terraform_plan_priced"])
            self.assertGreater(payload["run_30d"]["known_usd"], 0)
            self.assertEqual(payload["reported_usage"], {"status": "unknown"})
            private = Path(temporary) / "assumptions.json"
            value = payload["assumptions_template"]
            for row in value["items"].values():
                for key in row:
                    row[key] = 0
            private.write_text(json.dumps(value))
            private.chmod(0o644)
            command = cmd + ["--assumptions", str(private)]
            self.assertEqual(json.loads(subprocess.run(command, capture_output=True).stdout)["status"], "blocked")
            private.chmod(0o600)
            full = json.loads(subprocess.run(command, capture_output=True, check=True).stdout)
            self.assertEqual(full["status"], "estimated")
            self.assertTrue(full["run_30d"]["estimate_usd"])
