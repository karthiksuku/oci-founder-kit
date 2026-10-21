"""Behavioural contract for the founder value model.

Run: python3 -m unittest discover -s tests -v
"""

import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "founder-value" / "scripts"))

import value_model as vm  # noqa: E402

EXAMPLE = ROOT / "skills" / "founder-value" / "assets" / "scenario.example.json"


def base_scenario():
    """Small, hand-checkable scenario. Every number here is a test input."""
    return {
        "schema": "founder-value-scenario/1",
        "name": "unit test",
        "currency": "USD",
        "horizon_months": 24,
        "baseline": "current",
        "business": {
            "customers_start": 10,
            "customer_growth_monthly": 0.0,
            "arpa_monthly": 500,
            "other_cogs_per_customer_monthly": 0,
            "opex_monthly": 4000,
            "cash_on_hand": 100000,
        },
        "options": {
            "current": {
                "label": "Current cloud",
                "lines": [
                    {"id": "bill", "label": "Monthly invoice", "amount": 1500, "evidence": "stated"},
                ],
            },
            "oci": {
                "label": "OCI",
                "lines": [
                    {"id": "compute", "label": "Compute", "quantity": 1, "unit_price": 1000,
                     "evidence": "sourced"},
                ],
            },
        },
    }


class TieredCost(unittest.TestCase):
    def test_free_tier_then_paid(self):
        tiers = [{"from": 0, "to": 10240, "price": 0}, {"from": 10240, "to": None, "price": 0.025}]
        self.assertAlmostEqual(vm.tiered_cost(12000, tiers), 44.0)

    def test_inside_free_tier_is_zero(self):
        tiers = [{"from": 0, "to": 10240, "price": 0}, {"from": 10240, "to": None, "price": 0.025}]
        self.assertEqual(vm.tiered_cost(5000, tiers), 0)


class LineCost(unittest.TestCase):
    def test_hourly_quantity(self):
        line = {"id": "c", "quantity": 2, "hours_per_month": 730, "unit_price": 0.03}
        cost, qty = vm.line_monthly_cost(line, customers=40)
        self.assertAlmostEqual(cost, 43.8)
        self.assertEqual(qty, 1460)

    def test_per_customer_amount(self):
        line = {"id": "s", "basis": "per_customer", "amount": 1.5}
        cost, _ = vm.line_monthly_cost(line, customers=40)
        self.assertAlmostEqual(cost, 60.0)

    def test_unpriced_line_is_unknown_not_zero(self):
        line = {"id": "db", "quantity": 1, "unit_price": None}
        cost, _ = vm.line_monthly_cost(line, customers=1)
        self.assertIsNone(cost)


class Simulation(unittest.TestCase):
    def test_customer_growth_compounds(self):
        s = base_scenario()
        s["business"]["customer_growth_monthly"] = 0.1
        r = vm.simulate(s)
        months = r["options"]["current"]["months"]
        self.assertAlmostEqual(months[0]["customers"], 10)
        self.assertAlmostEqual(months[12]["customers"], 10 * 1.1 ** 12)

    def test_credits_exhausted_before_window_ends(self):
        s = base_scenario()
        s["options"]["oci"]["credits"] = {"amount": 10000, "start_month": 1, "valid_months": 12}
        c = vm.simulate(s)["options"]["oci"]["summary"]["credits"]
        self.assertAlmostEqual(c["applied"], 10000)
        self.assertAlmostEqual(c["expired"], 0)
        self.assertEqual(c["cliff_month"], 11)
        self.assertAlmostEqual(c["cloud_cash_before_cliff"], 0)
        self.assertAlmostEqual(c["cloud_cash_after_cliff"], 1000)

    def test_unused_credits_expire_at_window_end(self):
        s = base_scenario()
        s["options"]["oci"]["credits"] = {"amount": 20000, "start_month": 1, "valid_months": 12}
        c = vm.simulate(s)["options"]["oci"]["summary"]["credits"]
        self.assertAlmostEqual(c["applied"], 12000)
        self.assertAlmostEqual(c["expired"], 8000)
        self.assertEqual(c["cliff_month"], 13)

    def test_durable_margin_ignores_credits_cash_margin_uses_them(self):
        s = base_scenario()
        s["options"]["oci"]["credits"] = {"amount": 20000, "start_month": 1, "valid_months": 12}
        m1 = vm.simulate(s)["options"]["oci"]["months"][0]
        self.assertAlmostEqual(m1["gross_margin_durable"], (5000 - 1000) / 5000)
        self.assertAlmostEqual(m1["gross_margin_cash"], 1.0)

    def test_migration_and_dual_running_cost_cash(self):
        s = base_scenario()
        s["options"]["oci"]["migration"] = {"one_time_cost": 5000, "start_month": 1, "dual_run_months": 2}
        months = vm.simulate(s)["options"]["oci"]["months"]
        self.assertAlmostEqual(months[0]["migration_cash"], 5000 + 1500)
        self.assertAlmostEqual(months[1]["migration_cash"], 1500)
        self.assertAlmostEqual(months[2]["migration_cash"], 0)

    def test_dual_running_pays_the_baseline_cash_bill_after_its_credits(self):
        s = base_scenario()
        s["options"]["current"]["credits"] = {"amount": 1500, "start_month": 1, "valid_months": 6}
        s["options"]["oci"]["migration"] = {"one_time_cost": 0, "start_month": 1, "dual_run_months": 2}
        months = vm.simulate(s)["options"]["oci"]["months"]
        # The baseline's credits cover its month-1 bill, so dual running costs 0 cash then.
        self.assertAlmostEqual(months[0]["migration_cash"], 0)
        self.assertAlmostEqual(months[1]["migration_cash"], 1500)

    def test_dual_running_without_credits_uses_the_baseline_list_bill(self):
        s = base_scenario()
        s["options"]["current"]["credits"] = {"amount": 1500, "start_month": 1, "valid_months": 6}
        s["options"]["oci"]["migration"] = {"one_time_cost": 0, "start_month": 1, "dual_run_months": 2}
        cmp = vm.simulate(s)["comparisons"]["oci"]
        # Without credits on either side: dual run costs 1500 x 2 against a 500/month
        # durable saving: cumulative -1000, -2000, then +500/month -> month 6.
        self.assertEqual(cmp["payback_month_without_credits"], 6)

    def test_credits_starting_after_the_horizon_do_not_expire(self):
        s = base_scenario()
        s["horizon_months"] = 6
        s["options"]["oci"]["credits"] = {"amount": 1000, "start_month": 10, "valid_months": 3}
        c = vm.simulate(s)["options"]["oci"]["summary"]["credits"]
        self.assertAlmostEqual(c["applied"], 0)
        self.assertAlmostEqual(c["expired"], 0)
        self.assertIsNone(c["cliff_month"])

    def test_payback_with_and_without_credits(self):
        s = base_scenario()
        s["options"]["oci"]["migration"] = {"one_time_cost": 5000, "start_month": 1, "dual_run_months": 2}
        s["options"]["oci"]["credits"] = {"amount": 6000, "start_month": 1, "valid_months": 12}
        cmp = vm.simulate(s)["comparisons"]["oci"]
        # With credits the OCI bill is 0 for months 1-6. Option cash vs the
        # 1500 baseline: m1 6500 (-5000), m2 1500 (0), m3-m6 0 (+1500 each)
        # -> cumulative -5000, -5000, -3500, -2000, -500, +1000: month 6.
        self.assertEqual(cmp["payback_month"], 6)
        # Without credits: m1 7500 (-6000), m2 2500 (-1000), then +500/month
        # -> cumulative reaches 0 in month 16.
        self.assertEqual(cmp["payback_month_without_credits"], 16)
        self.assertAlmostEqual(cmp["durable_monthly_saving_at_horizon"], 500)

    def test_gross_margin_delta_in_points(self):
        cmp = vm.simulate(base_scenario())["comparisons"]["oci"]
        # Durable GM: current (5000-1500)/5000 = 70%, OCI (5000-1000)/5000 = 80%.
        self.assertAlmostEqual(cmp["durable_gross_margin_delta_points_first"], 10.0)
        self.assertAlmostEqual(cmp["durable_gross_margin_delta_points_last"], 10.0)

    def test_cash_saving_as_months_of_runway(self):
        cmp = vm.simulate(base_scenario())["comparisons"]["oci"]
        # Baseline net burn 4000 + 1500 - 5000 = 500/month; OCI keeps 500/month
        # more for 24 months = 12000, worth 24 months of baseline burn.
        self.assertAlmostEqual(cmp["runway_equivalent_months"], 24.0)

    def test_runway_equivalent_is_none_when_baseline_never_burns(self):
        s = base_scenario()
        s["business"]["opex_monthly"] = 0
        cmp = vm.simulate(s)["comparisons"]["oci"]
        self.assertIsNone(cmp["runway_equivalent_months"])

    def test_margin_bridge_by_group_adds_up(self):
        s = base_scenario()
        s["options"]["current"]["lines"][0]["group"] = "compute"
        s["options"]["oci"]["lines"][0]["group"] = "compute"
        s["options"]["oci"]["lines"].append({"id": "misc", "amount": 100})
        cmp = vm.simulate(s)["comparisons"]["oci"]
        bridge = {step["group"]: step["points"] for step in cmp["margin_bridge"]}
        # compute: (1500 - 1000) / 5000 = +10 points; other: (0 - 100) / 5000 = -2 points
        self.assertAlmostEqual(bridge["compute"], 10.0)
        self.assertAlmostEqual(bridge["other"], -2.0)
        self.assertAlmostEqual(sum(bridge.values()), cmp["durable_gross_margin_delta_points_last"])

    def test_margin_bridge_includes_ai_group(self):
        s = base_scenario()
        s["ai_usage"] = {"actions_per_customer_monthly": 100, "input_tokens_per_action": 1000,
                         "output_tokens_per_action": 0}
        s["options"]["current"]["ai"] = {"input_per_mtok": 2.0, "output_per_mtok": 0}
        s["options"]["oci"]["ai"] = {"input_per_mtok": 1.0, "output_per_mtok": 0}
        cmp = vm.simulate(s)["comparisons"]["oci"]
        bridge = {step["group"]: step["points"] for step in cmp["margin_bridge"]}
        # AI: 1000 actions x (0.002 - 0.001) = 1.0 a month / 5000 revenue = +0.02 points
        self.assertAlmostEqual(bridge["ai"], 0.02)

    def test_runway_months(self):
        s = base_scenario()
        s["business"]["arpa_monthly"] = 0
        s["business"]["cash_on_hand"] = 11000
        # current burn = 4000 opex + 1500 cloud = 5500/month -> funded 2 months.
        r = vm.simulate(s)
        self.assertEqual(r["options"]["current"]["summary"]["runway_months"], 2)
        # oci burn = 5000/month -> funded 2 months (cash 1000 after month 2).
        self.assertEqual(r["options"]["oci"]["summary"]["runway_months"], 2)

    def test_runway_beyond_horizon_is_none(self):
        r = vm.simulate(base_scenario())
        self.assertIsNone(r["options"]["current"]["summary"]["runway_months"])

    def test_incomplete_option_is_flagged_and_listed(self):
        s = base_scenario()
        s["options"]["oci"]["lines"].append({"id": "db", "label": "Database", "quantity": 1, "unit_price": None})
        r = vm.simulate(s)
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(r["options"]["oci"]["summary"]["unpriced"], ["db"])
        self.assertAlmostEqual(r["options"]["oci"]["months"][0]["cloud_list"], 1000)

    def test_complete_status(self):
        self.assertEqual(vm.simulate(base_scenario())["status"], "COMPLETE")

    def test_top_drivers_sorted_by_cost(self):
        s = base_scenario()
        s["options"]["oci"]["lines"].append({"id": "egress", "quantity": 1, "unit_price": 50})
        drivers = vm.simulate(s)["options"]["oci"]["summary"]["top_drivers"]
        self.assertEqual([d["id"] for d in drivers], ["compute", "egress"])

    def test_simulate_does_not_mutate_input(self):
        s = base_scenario()
        s["options"]["oci"]["credits"] = {"amount": 10000, "start_month": 1, "valid_months": 12}
        before = copy.deepcopy(s)
        vm.simulate(s)
        self.assertEqual(s, before)


class AiEconomics(unittest.TestCase):
    USAGE = {"actions_per_customer_monthly": 100, "input_tokens_per_action": 2000,
             "cached_input_share": 0.3, "output_tokens_per_action": 500}

    def test_cost_per_action_with_cache(self):
        prices = {"input_per_mtok": 0.15, "cached_input_per_mtok": 0.05, "output_per_mtok": 0.6}
        expected = (1400 * 0.15 + 600 * 0.05 + 500 * 0.6) / 1_000_000
        self.assertAlmostEqual(vm.ai_cost_per_action(self.USAGE, prices), expected)

    def test_cached_price_defaults_to_input_price(self):
        prices = {"input_per_mtok": 0.15, "output_per_mtok": 0.6}
        expected = (2000 * 0.15 + 500 * 0.6) / 1_000_000
        self.assertAlmostEqual(vm.ai_cost_per_action(self.USAGE, prices), expected)

    def test_missing_ai_price_is_unpriced(self):
        self.assertIsNone(vm.ai_cost_per_action(self.USAGE, {"input_per_mtok": 0.15}))

    def test_ai_cost_enters_cloud_bill(self):
        s = base_scenario()
        s["ai_usage"] = dict(self.USAGE)
        s["options"]["oci"]["ai"] = {"input_per_mtok": 1.0, "output_per_mtok": 2.0}
        s["options"]["current"]["ai"] = {"input_per_mtok": 3.0, "output_per_mtok": 6.0}
        r = vm.simulate(s)
        per_action = (2000 * 1.0 + 500 * 2.0) / 1_000_000
        m1 = r["options"]["oci"]["months"][0]
        self.assertAlmostEqual(m1["ai_cost"], per_action * 100 * 10)
        self.assertAlmostEqual(m1["cloud_list"], 1000 + per_action * 1000)
        self.assertAlmostEqual(r["options"]["oci"]["summary"]["ai_cost_per_action"], per_action)

    def test_ai_usage_without_option_prices_marks_incomplete(self):
        s = base_scenario()
        s["ai_usage"] = dict(self.USAGE)
        s["options"]["oci"]["ai"] = {"input_per_mtok": 1.0, "output_per_mtok": 2.0}
        r = vm.simulate(s)
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertIn("ai", r["options"]["current"]["summary"]["unpriced"])


class Validation(unittest.TestCase):
    def errors(self, mutate):
        s = base_scenario()
        mutate(s)
        return vm.validate_scenario(s)

    def test_valid(self):
        self.assertEqual(vm.validate_scenario(base_scenario()), [])

    def test_missing_currency(self):
        self.assertTrue(self.errors(lambda s: s.pop("currency")))

    def test_bad_horizon(self):
        self.assertTrue(self.errors(lambda s: s.update(horizon_months=0)))

    def test_unknown_baseline(self):
        self.assertTrue(self.errors(lambda s: s.update(baseline="nope")))

    def test_amount_and_quantity_conflict(self):
        def m(s):
            s["options"]["oci"]["lines"][0]["amount"] = 10
        self.assertTrue(self.errors(m))

    def test_negative_value(self):
        def m(s):
            s["business"]["cash_on_hand"] = -1
        self.assertTrue(self.errors(m))

    def test_duplicate_line_ids(self):
        def m(s):
            s["options"]["oci"]["lines"].append({"id": "compute", "quantity": 1, "unit_price": 1})
        self.assertTrue(self.errors(m))

    def test_unknown_evidence_class(self):
        def m(s):
            s["options"]["oci"]["lines"][0]["evidence"] = "vibes"
        self.assertTrue(self.errors(m))

    def test_simulate_rejects_invalid(self):
        s = base_scenario()
        s.pop("currency")
        with self.assertRaises(vm.ScenarioError):
            vm.simulate(s)

    def test_malformed_nested_blocks_raise_scenario_error_not_crash(self):
        def oci(field, value):
            return lambda s: s["options"]["oci"].__setitem__(field, value)

        def line(field, value):
            return lambda s: s["options"]["oci"]["lines"][0].__setitem__(field, value)

        cases = {
            "credits without amount": oci("credits", {"start_month": 1, "valid_months": 3}),
            "credits amount null": oci("credits", {"amount": None, "start_month": 1, "valid_months": 3}),
            "credits not an object": oci("credits", 5),
            "credits a string": oci("credits", "x"),
            "migration not an object": oci("migration", 5),
            "ai not an object": oci("ai", 5),
            "ai_usage not an object": lambda s: s.__setitem__("ai_usage", [1]),
            "tiers not a list": line("tiers", 5),
            "tier to not numeric": line("tiers", [{"from": 0, "to": "x", "price": 1}]),
            "line id a list": line("id", ["a"]),
            "baseline a list": lambda s: s.__setitem__("baseline", ["x"]),
            "option not an object": lambda s: s["options"].__setitem__("oci", 5),
            "lines contain a non-object": lambda s: s["options"]["oci"]["lines"].append(5),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                s = base_scenario()
                if name.startswith("tier"):
                    s["options"]["oci"]["lines"][0].pop("unit_price")
                mutate(s)
                self.assertTrue(vm.validate_scenario(s), name)
                with self.assertRaises(vm.ScenarioError):
                    vm.simulate(s)

    def test_tiers_must_start_at_zero_and_be_contiguous(self):
        bad = {
            "gap": [{"from": 0, "to": 10, "price": 1}, {"from": 20, "to": None, "price": 2}],
            "overlap": [{"from": 0, "to": 20, "price": 1}, {"from": 10, "to": None, "price": 2}],
            "late start": [{"from": 10, "to": None, "price": 2}],
            "open middle": [{"from": 0, "to": None, "price": 1}, {"from": 10, "to": None, "price": 2}],
        }
        for name, tiers in bad.items():
            with self.subTest(name):
                s = base_scenario()
                line = s["options"]["oci"]["lines"][0]
                line.pop("unit_price")
                line["tiers"] = tiers
                self.assertTrue(vm.validate_scenario(s), name)

    def test_contiguous_tiers_are_valid(self):
        s = base_scenario()
        line = s["options"]["oci"]["lines"][0]
        line.pop("unit_price")
        line["tiers"] = [{"from": 0, "to": 10, "price": 0}, {"from": 10, "to": None, "price": 2}]
        self.assertEqual(vm.validate_scenario(s), [])


class Rendering(unittest.TestCase):
    def test_incomplete_banner(self):
        s = base_scenario()
        s["options"]["oci"]["lines"].append({"id": "db", "quantity": 1, "unit_price": None})
        md = vm.render_markdown(vm.simulate(s))
        self.assertIn("INCOMPLETE", md)
        self.assertIn("db", md)

    def test_credit_cliff_is_reported(self):
        s = base_scenario()
        s["options"]["oci"]["credits"] = {"amount": 20000, "start_month": 1, "valid_months": 12}
        md = vm.render_markdown(vm.simulate(s))
        self.assertIn("Credit cliff", md)
        self.assertIn("month 13", md)

    def test_output_is_deterministic(self):
        s = base_scenario()
        self.assertEqual(vm.render_markdown(vm.simulate(s)), vm.render_markdown(vm.simulate(s)))


class Cli(unittest.TestCase):
    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = vm.main(argv)
        return code, buf.getvalue()

    def test_example_scenario_runs(self):
        code, out = self.run_cli([str(EXAMPLE), "--format", "json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("comparisons", data)

    def test_strict_fails_when_incomplete(self):
        s = base_scenario()
        s["options"]["oci"]["lines"].append({"id": "db", "quantity": 1, "unit_price": None})
        path = Path(self._tmp()) / "s.json"
        path.write_text(json.dumps(s))
        code, _ = self.run_cli([str(path), "--strict"])
        self.assertEqual(code, 3)

    def test_invalid_input_exit_code(self):
        path = Path(self._tmp()) / "bad.json"
        path.write_text(json.dumps({"schema": "founder-value-scenario/1"}))
        buf = io.StringIO()
        with redirect_stdout(buf), _quiet_stderr():
            code = vm.main([str(path)])
        self.assertEqual(code, 2)

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="fvk-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d


class _quiet_stderr:
    def __enter__(self):
        self._old = sys.stderr
        sys.stderr = io.StringIO()

    def __exit__(self, *exc):
        sys.stderr = self._old


if __name__ == "__main__":
    unittest.main()
