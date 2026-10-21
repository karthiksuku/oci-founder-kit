"""Contract for the Oracle public price list lookup.

The fixture is a real API response captured from
https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/ and trimmed to
USD and AUD. No network access happens in these tests.
"""

import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "founder-value" / "scripts"))

import price_lookup as pl  # noqa: E402
import value_model as vm  # noqa: E402

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "price_api_sample.json").read_text())
ITEMS = {item["partNumber"]: item for item in FIXTURE["items"]}


def fixture_fetch(part_number):
    return ITEMS.get(part_number), FIXTURE["lastUpdated"]


def usd(part):
    loc = next(c for c in ITEMS[part]["currencyCodeLocalizations"] if c["currencyCode"] == "USD")
    return loc["prices"]


class ParseItem(unittest.TestCase):
    def test_flat_hourly_price(self):
        rec = pl.parse_item(ITEMS["B97384"], "USD")
        self.assertEqual(rec["part_number"], "B97384")
        self.assertEqual(rec["metric"], "OCPU Per Hour")
        self.assertAlmostEqual(rec["unit_price"], usd("B97384")[0]["value"])
        self.assertIsNone(rec["tiers"])

    def test_tiered_egress_has_open_top_tier(self):
        rec = pl.parse_item(ITEMS["B93455"], "USD")
        self.assertIsNone(rec["unit_price"])
        self.assertEqual(rec["tiers"][0], {"from": 0, "to": 10240, "price": 0})
        self.assertEqual(rec["tiers"][-1]["from"], 10240)
        self.assertIsNone(rec["tiers"][-1]["to"])

    def test_tiers_price_correctly_in_value_model(self):
        rec = pl.parse_item(ITEMS["B93455"], "USD")
        paid = usd("B93455")[-1]["value"]
        self.assertAlmostEqual(vm.tiered_cost(11240, rec["tiers"]), 1000 * paid)

    def test_other_currency(self):
        rec = pl.parse_item(ITEMS["B97384"], "AUD")
        loc = next(c for c in ITEMS["B97384"]["currencyCodeLocalizations"] if c["currencyCode"] == "AUD")
        self.assertAlmostEqual(rec["unit_price"], loc["prices"][0]["value"])

    def test_missing_currency_raises(self):
        with self.assertRaises(LookupError):
            pl.parse_item(ITEMS["B97384"], "JPY")

    def test_real_open_top_sentinel_is_open(self):
        # B91628's top tier ends at 999999999 in the live list; that means unbounded.
        rec = pl.parse_item(ITEMS["B91628"], "USD")
        self.assertIsNone(rec["tiers"][-1]["to"])

    def _item(self, prices):
        return {"partNumber": "X1", "displayName": "x", "metricName": "m",
                "currencyCodeLocalizations": [{"currencyCode": "USD", "prices": prices}]}

    def test_ambiguous_or_gapped_tiers_are_refused(self):
        shapes = {
            "gap": [{"model": "PAY_AS_YOU_GO", "value": 1, "rangeMin": 0, "rangeMax": 10},
                    {"model": "PAY_AS_YOU_GO", "value": 2, "rangeMin": 11, "rangeMax": 1e13}],
            "late start": [{"model": "PAY_AS_YOU_GO", "value": 1, "rangeMin": 5, "rangeMax": 1e13}],
            "two prices without ranges": [{"model": "PAY_AS_YOU_GO", "value": 1},
                                          {"model": "PAY_AS_YOU_GO", "value": 2}],
            "missing value": [{"model": "PAY_AS_YOU_GO"}],
        }
        for name, prices in shapes.items():
            with self.subTest(name):
                with self.assertRaises(LookupError):
                    pl.parse_item(self._item(prices), "USD")


class FillScenario(unittest.TestCase):
    def scenario(self):
        return {
            "schema": "founder-value-scenario/1", "currency": "USD", "horizon_months": 12,
            "business": {"customers_start": 5, "arpa_monthly": 100, "opex_monthly": 1000,
                         "cash_on_hand": 50000},
            "ai_usage": {"actions_per_customer_monthly": 10, "input_tokens_per_action": 1000,
                         "output_tokens_per_action": 200},
            "options": {
                "current": {"lines": [{"id": "bill", "amount": 900, "evidence": "stated"}],
                            "ai": {"input_per_mtok": 1, "output_per_mtok": 2}},
                "oci": {"lines": [
                    {"id": "ocpu", "part_number": "B97384", "quantity": 2, "hours_per_month": 744},
                    {"id": "egress", "part_number": "B93455", "quantity": 12000},
                    {"id": "locked", "part_number": "B97385", "quantity": 1, "unit_price": 9,
                     "price_locked": True, "evidence": "stated"},
                ], "ai": {"input_part": "B112004", "output_part": "B112005"}},
            },
        }

    def test_fills_prices_and_provenance(self):
        filled, report = pl.fill_scenario(self.scenario(), fixture_fetch, today="2026-10-21")
        ocpu = filled["options"]["oci"]["lines"][0]
        self.assertAlmostEqual(ocpu["unit_price"], usd("B97384")[0]["value"])
        self.assertEqual(ocpu["evidence"], "sourced")
        self.assertEqual(ocpu["price_source"]["checked_at"], "2026-10-21")
        self.assertEqual(ocpu["price_source"]["price_list_updated"], FIXTURE["lastUpdated"])
        self.assertEqual(ocpu["price_source"]["metric"], "OCPU Per Hour")
        egress = filled["options"]["oci"]["lines"][1]
        self.assertTrue(egress["tiers"])
        self.assertTrue(all(item["status"] in ("filled", "kept") for item in report))

    def test_locked_price_is_kept(self):
        filled, report = pl.fill_scenario(self.scenario(), fixture_fetch, today="2026-10-21")
        locked = filled["options"]["oci"]["lines"][2]
        self.assertEqual(locked["unit_price"], 9)
        self.assertEqual(locked["evidence"], "stated")
        self.assertIn({"where": "options.oci.lines.locked", "status": "kept",
                       "detail": "price_locked"}, report)

    def test_ai_token_prices_fill(self):
        filled, _ = pl.fill_scenario(self.scenario(), fixture_fetch, today="2026-10-21")
        ai = filled["options"]["oci"]["ai"]
        self.assertAlmostEqual(ai["input_per_mtok"], usd("B112004")[0]["value"])
        self.assertAlmostEqual(ai["output_per_mtok"], usd("B112005")[0]["value"])
        self.assertEqual(ai["price_source"]["checked_at"], "2026-10-21")

    def test_ai_part_with_non_token_metric_is_refused(self):
        s = self.scenario()
        s["options"]["oci"]["ai"]["input_part"] = "B108080"
        filled, report = pl.fill_scenario(s, fixture_fetch, today="2026-10-21")
        self.assertIsNone(filled["options"]["oci"]["ai"].get("input_per_mtok"))
        refused = [r for r in report if r["status"] == "refused"]
        self.assertTrue(refused and "Tokens" in refused[0]["detail"])

    def test_unknown_part_is_reported_and_left_unpriced(self):
        s = self.scenario()
        s["options"]["oci"]["lines"][0]["part_number"] = "B00000"
        filled, report = pl.fill_scenario(s, fixture_fetch, today="2026-10-21")
        self.assertIsNone(filled["options"]["oci"]["lines"][0].get("unit_price"))
        self.assertTrue(any(r["status"] == "not_found" for r in report))

    def test_does_not_mutate_input(self):
        s = self.scenario()
        before = copy.deepcopy(s)
        pl.fill_scenario(s, fixture_fetch, today="2026-10-21")
        self.assertEqual(s, before)

    def test_non_object_scenario_raises_value_error(self):
        for bad in ([1], {"options": [1]}):
            with self.subTest(repr(bad)):
                with self.assertRaises(ValueError):
                    pl.fill_scenario(bad, fixture_fetch, today="2026-10-21")

    def test_malformed_option_and_lines_are_reported_not_crashed(self):
        s = self.scenario()
        s["options"]["bad"] = 5
        s["options"]["oci"]["lines"].append(5)
        s["options"]["current"]["lines"] = None
        filled, report = pl.fill_scenario(s, fixture_fetch, today="2026-10-21")
        self.assertTrue(any(r["where"] == "options.bad" and r["status"] == "refused" for r in report))
        self.assertEqual(filled["options"]["oci"]["lines"][-1], 5)

    def test_filled_scenario_simulates_complete(self):
        filled, _ = pl.fill_scenario(self.scenario(), fixture_fetch, today="2026-10-21")
        self.assertEqual(vm.simulate(filled)["status"], "COMPLETE")


class Search(unittest.TestCase):
    def test_search_matches_display_name_case_insensitively(self):
        rows = pl.search(FIXTURE["items"], "e5 - ocpu", "USD")
        self.assertEqual([r["part_number"] for r in rows], ["B97384"])


class Network(unittest.TestCase):
    def test_fetch_part_picks_the_exact_part_and_last_updated(self):
        with mock.patch.object(pl, "_get_json", return_value=FIXTURE) as get:
            item, updated = pl.fetch_part("B97385", "USD", 5)
        self.assertEqual(item["partNumber"], "B97385")
        self.assertEqual(updated, FIXTURE["lastUpdated"])
        self.assertIn("partNumber=B97385", get.call_args[0][0])

    def test_fetch_all_returns_items(self):
        with mock.patch.object(pl, "_get_json", return_value=FIXTURE):
            items, updated = pl.fetch_all("USD", 5)
        self.assertEqual(len(items), len(FIXTURE["items"]))


class Cli(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pl.main(argv)
        return code, out.getvalue(), err.getvalue()

    def tmp(self):
        d = tempfile.mkdtemp(prefix="fvk-pl-")
        self.addCleanup(shutil.rmtree, d, True)
        return Path(d)

    def test_search_prints_matches(self):
        with mock.patch.object(pl, "fetch_all", return_value=(FIXTURE["items"], FIXTURE["lastUpdated"])):
            code, out, _ = self.run_main(["search", "Outbound Data Transfer"])
        self.assertEqual(code, 0)
        self.assertIn("B93455", out)
        self.assertIn("tiers", out)

    def test_search_without_matches_exits_4(self):
        with mock.patch.object(pl, "fetch_all", return_value=(FIXTURE["items"], FIXTURE["lastUpdated"])):
            code, _, _ = self.run_main(["search", "no such service"])
        self.assertEqual(code, 4)

    def test_part_found_and_not_found(self):
        with mock.patch.object(pl, "fetch_part", side_effect=lambda p, c, t: fixture_fetch(p)):
            self.assertEqual(self.run_main(["part", "B97384"])[0], 0)
            self.assertEqual(self.run_main(["part", "B00000"])[0], 4)

    def test_fill_writes_priced_scenario(self):
        d = self.tmp()
        src, dst = d / "s.json", d / "out.json"
        src.write_text(json.dumps(FillScenario().scenario()))
        with mock.patch.object(pl, "fetch_part", side_effect=lambda p, c, t: fixture_fetch(p)):
            code, out, _ = self.run_main(["fill", str(src), "--out", str(dst)])
        self.assertEqual(code, 0)
        self.assertIn("filled", out)
        self.assertEqual(json.loads(dst.read_text())["options"]["oci"]["lines"][0]["evidence"], "sourced")

    def test_fill_with_unknown_part_exits_4(self):
        d = self.tmp()
        s = FillScenario().scenario()
        s["options"]["oci"]["lines"][0]["part_number"] = "B00000"
        (d / "s.json").write_text(json.dumps(s))
        with mock.patch.object(pl, "fetch_part", side_effect=lambda p, c, t: fixture_fetch(p)):
            code, _, _ = self.run_main(["fill", str(d / "s.json"), "--out", str(d / "o.json")])
        self.assertEqual(code, 4)

    def test_fill_rejects_unreadable_and_non_object_input(self):
        d = self.tmp()
        (d / "bad.json").write_text("{not json")
        (d / "list.json").write_text("[1]")
        self.assertEqual(self.run_main(["fill", str(d / "bad.json"), "--out", str(d / "o.json")])[0], 2)
        self.assertEqual(self.run_main(["fill", str(d / "list.json"), "--out", str(d / "o.json")])[0], 2)

    def test_network_failure_exits_1_and_says_not_to_guess(self):
        with mock.patch.object(pl, "fetch_all", side_effect=urllib.error.URLError("offline")):
            code, _, err = self.run_main(["search", "E5"])
        self.assertEqual(code, 1)
        self.assertIn("do not substitute remembered prices", err)


if __name__ == "__main__":
    unittest.main()
