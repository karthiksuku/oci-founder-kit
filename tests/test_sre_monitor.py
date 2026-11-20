"""Reliability checks use synthetic bounded observations only; no OCI calls."""

import importlib.util
import json
from pathlib import Path
import time
import unittest

import test_operations as fixtures
from test_operations import INSTANCE, COMPARTMENT

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kit_sre_monitor_test", ROOT / "scripts/sre_monitor.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

C = {
    "schema": "oci-sre-monitor-input/1",
    "environment": "rehearsal",
    "journey": "customer-create",
    "availability_bps": 9990,
    "latency_bps": 9900,
    "latency_ms": 450,
    "runbook_sha256": "a" * 64,
    "primary_role": "owner",
    "backup_role": "backup",
}


def rows(end, count, n=100, ok=100, fast=100):
    return [dict(end=end - i * 3600, minutes=60, eligible=n, successful=ok, within=fast) for i in range(count)]


class Signals(unittest.TestCase):
    def setUp(self):
        self.end = int(time.time()) // 3600 * 3600

    def test_real_success_and_user_latency_have_separate_denominators_from_probe(self):
        r = s.summarize(rows(self.end, s.HOURS, 100, 100, 95), C, self.end)
        self.assertEqual(
            (r["status"], r["observed_availability_percent"], r["observed_within_target_percent"]), ("missed", 100, 95)
        )
        self.assertEqual(s.summarize(rows(self.end, s.HOURS), C, self.end)["status"], "met")
        with self.assertRaises(ValueError):
            s.summarize([dict(rows(self.end, 1)[0], synthetic=1)], C, self.end)

    def test_first_run_sparse_or_missing_history_never_establish_objective(self):
        short = rows(self.end, 2)
        self.assertEqual(s.summarize(short, C, self.end)["status"], "collecting-history")
        self.assertEqual(s.summarize([], C, self.end)["status"], "no-data")
        zero = rows(self.end, s.HOURS, 0, 0, 0)
        self.assertIsNone(s.summarize(zero, C, self.end)["observed_availability_percent"])
        zero[0].update(eligible=1, successful=1, within=1)
        self.assertEqual(s.summarize(zero, C, self.end)["status"], "low-traffic")
        zero[1]["minutes"] = 59
        self.assertEqual(s.summarize(zero, C, self.end)["status"], "incomplete-telemetry")
        with self.assertRaises(ValueError):
            s.summarize(short + short, C, self.end)

    def test_private_drill_not_promotion_or_shared_between_roles(self):
        c = s.policy(C, "rehearsal")
        record = dict(
            environment="rehearsal",
            primary_role="owner",
            runbook_sha256="a" * 64,
            evidence_sha256="b" * 64,
            fired_at=self.end - 100,
            received_at=self.end - 90,
            recovered_at=self.end - 50,
            cleared_at=self.end - 40,
        )
        self.assertFalse(s.drill(record, c, self.end)["receipt_authenticated"])
        self.assertEqual(s.drill(dict(record, environment="other"), c, self.end)["status"], "stale-or-unbound")
        self.assertEqual(s.drill(record, c, self.end + 31 * 86400)["status"], "stale-or-unbound")
        with self.assertRaises(ValueError):
            s.policy(dict(C, backup_role="owner"), "rehearsal")
        with self.assertRaises(ValueError):
            s.drill(dict(record, received_at=self.end + 1), c, self.end)

    def test_oci_mql_missing_duplicate_or_unbound_intervals(self):
        dims = {"resourceId": INSTANCE, "journey": C["journey"], "latencyMs": str(C["latency_ms"])}
        response = dict(
            name="EligibleRequests",
            namespace="founder_app",
            dimensions=dims,
            **{
                "compartment-id": COMPARTMENT,
                "aggregated-datapoints": [{"timestamp": s.iso(self.end), "value": 12.0}],
            },
        )

        def result(row=response, paged=False):
            return s.points(
                lambda args: {"data": [row], "opc-next-page": paged},
                COMPARTMENT,
                "founder_app",
                "EligibleRequests",
                dims,
                self.end - 3600,
                self.end,
                "1h",
                "sum",
            )

        self.assertEqual(result(), {self.end: 12})
        self.assertEqual(result(dict(response, dimensions=dict(dims, resourceId="other"))), {})
        self.assertEqual(
            result(dict(response, **{"aggregated-datapoints": response["aggregated-datapoints"] * 2})), {}
        )
        self.assertEqual(result(paged=True), {})

    def test_cloud_request_counts_require_all_four_metric_streams(self):
        def client(args):
            query = args[args.index("--query-text") + 1]
            name = query.split("[")[0]
            dims = {"resourceId": INSTANCE, "journey": C["journey"]}
            if name != "Heartbeat":
                dims.update(latencyMs=str(C["latency_ms"]))
            total = {"EligibleRequests": 12, "SuccessfulRequests": 10, "WithinLatencyTarget": 8, "Heartbeat": 60}
            value = 60 if query.endswith(".count()") else total[name]
            if lose and query.startswith("WithinLatencyTarget") and query.endswith(".count()"):
                value = 59
            return {
                "data": [
                    {
                        "compartment-id": COMPARTMENT,
                        "namespace": "founder_app",
                        "name": name,
                        "dimensions": dims,
                        "aggregated-datapoints": [{"timestamp": s.iso(self.end), "value": value}],
                    }
                ]
            }

        lose = False

        def result():
            return s.summarize(
                s.user_hours(client, {"compartment_id": COMPARTMENT}, INSTANCE, C, self.end), C, self.end
            )

        self.assertEqual(result()["eligible"], 12)
        self.assertEqual(result()["within_latency_target"], 8)
        lose = True
        self.assertEqual(result()["status"], "incomplete-telemetry")
        self.assertIsNone(result()["observed_availability_percent"])

    def test_consecutive_probe_errors_are_separate_from_user_traffic(self):
        identifier = "ocid1.httpmonitor.oc1..syntheticcheck"
        host = "rehearsal.example.test"
        m = dict(
            id=identifier,
            targets=[host],
            path="/health",
            protocol="HTTPS",
            port=443,
            method="GET",
            **{
                "compartment-id": COMPARTMENT,
                "is-enabled": True,
                "interval-in-seconds": 60,
                "vantage-point-names": ["test-east"],
            },
        )
        receipt = {
            "resources": [dict(type="oci_health_checks_http_monitor", id=identifier, compartment_id=COMPARTMENT)]
        }
        records = [
            dict(
                target=host,
                **{
                    "probe-configuration-id": identifier,
                    "vantage-point-name": "test-east",
                    "is-healthy": False,
                    "status-code": 503,
                    "start-time": (self.end - i * 60 - 1) * 1000,
                },
            )
            for i in range(3)
        ]

        def observe():
            def client(args):
                return {"data": m if args[1] == "http-monitor" else records}

            return s.probe(
                client,
                {"origin": "https://" + host, "health_path": "/health", "compartment_id": COMPARTMENT},
                receipt,
                self.end,
            )

        self.assertEqual(observe()["status"], "failed")
        records[0].update({"is-healthy": True, "status-code": 200})
        self.assertEqual(observe()["status"], "passing")
        records[0]["status-code"] = 302
        self.assertEqual(observe()["status"], "failed")
        m["path"] = "/wrong"
        self.assertEqual(observe()["status"], "unknown")

    def test_injected_client_reports_never_become_cloud_acceptance(self):
        fixture = fixtures.BoundObservation(
            methodName="test_bound_receipt_can_be_read_under_write_lock_without_nested_store"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        private = fixture.app.parent / "monitor.json"
        fixture.write(private, C)
        r = s.request(
            fixture.app,
            environment="rehearsal",
            input_file=private,
            live=True,
            write=True,
            client=fixture.fixture.client,
        )
        self.assertEqual(
            (r["mode"], r["production_ready"], r["users"]["status"]), ("injected-test-client", False, "no-data")
        )
        self.assertEqual(r["heartbeat"]["status"], "unknown")
        saved = fixture.app / r["evidence"]
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        val = json.loads(saved.read_text())
        val["extra_private"] = "synthetic-private-marker"
        fixture.write(saved, val)
        with fixture.p.Store(fixture.app, environment="rehearsal") as store:
            d = fixture.p.helper("dashboard")
            page = d.page(d.view(store, fixture.p)).decode()
        self.assertIn("injected-test-client · real-user objective: no-data", page)
        self.assertNotIn("synthetic-private-marker", page)
        wrong = dict(C, hours=[])
        fixture.write(private, wrong)
        with self.assertRaises(ValueError):
            s.request(
                fixture.app, environment="rehearsal", input_file=private, live=True, client=fixture.fixture.client
            )
