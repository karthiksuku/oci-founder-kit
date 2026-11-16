"""Service-level failures stay distinct from verified image and billing evidence."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_operating_helper", ROOT / "scripts/operations.py")
ops = importlib.util.module_from_spec(spec); spec.loader.exec_module(ops)
INSTANCE = "ocid1.computecontainerinstance.oc1.test.syntheticinstance"
CONTAINER = "ocid1.computecontainer.oc1.test.syntheticcontainer"
COMPARTMENT = "ocid1.compartment.oc1..syntheticenvironment"
LB = "ocid1.loadbalancer.oc1.test.syntheticbalancer"
CERT = "ocid1.certificate.oc1.test.syntheticcertificate"
DIGEST = "sha256:" + "a" * 64


class Operations(unittest.TestCase):
    def setUp(self):
        self.config = {"target": {"compartment_id": COMPARTMENT, "image_digest": DIGEST, "certificate_id": CERT,
                                  "region": "us-phoenix-1"}}
        self.receipt = {"resources": [{"type": "oci_container_instances_container_instance", "id": INSTANCE},
                                      {"type": "oci_load_balancer_load_balancer", "id": LB}]}
        self.responses = {
            "container-instance": {"id": INSTANCE, "compartment-id": COMPARTMENT, "lifecycle-state": "ACTIVE", "containers": [{"container-id": CONTAINER}]},
            "container": {"id": CONTAINER, "container-instance-id": INSTANCE, "compartment-id": COMPARTMENT,
                          "image-url": "phx.ocir.io/syntheticnamespace/app@" + DIGEST},
            "load-balancer": {"id": LB, "compartment-id": COMPARTMENT},
            "load-balancer-health": {"status": "OK"},
            "certificate": {"id": CERT, "lifecycle-state": "ACTIVE", "current-version": {"validity": {"time-not-after": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=60)).isoformat()}}},
            "work-request": {"items": [{"status": "SUCCEEDED", "compartment-id": COMPARTMENT, "resources": [{"identifier": INSTANCE}]}]},
            "metric-data": [{"namespace": "oci_computecontainerinstance", "name": "CpuUtilization", "compartment-id": COMPARTMENT, "dimensions": {"resourceId": INSTANCE},
                "aggregated-datapoints": [{"timestamp": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat(), "value": 14.5}]}]}
        self.calls = []

    def client(self, arguments):
        self.calls.append(arguments)
        return {"data": copy.deepcopy(self.responses[arguments[1]])}

    def collect(self):
        return ops.collect(self.config, self.receipt, self.client)

    def status(self, value, key):
        return next(c["status"] for c in value["checks"] if c["id"] == key)

    def test_actual_digest_and_target_are_checked(self):
        value = self.collect()
        self.assertEqual(value["status"], "passed")
        self.assertTrue(value["image_identity_verified"])
        self.assertEqual(value["metrics"]["cpu_mean_percent"], 14.5)
        self.assertLessEqual(len(self.calls), 8)

    def test_wrong_instance_never_allows_container_read(self):
        self.responses["container-instance"]["compartment-id"] += "other"
        value = self.collect()
        self.assertFalse(value["image_identity_verified"])
        self.assertFalse(any(c[1] == "container" for c in self.calls))

    def test_matching_tag_is_not_digest_verification(self):
        self.responses["container"]["image-url"] = "phx.ocir.io/syntheticnamespace/app:latest"
        value = self.collect()
        self.assertEqual(self.status(value, "image_identity"), "failed")

    def test_denied_read_is_unknown_and_error_is_not_reported(self):
        def denied(arguments):
            raise RuntimeError("synthetic-sensitive-request")
        value = ops.collect(self.config, self.receipt, denied)
        self.assertEqual(value["status"], "unknown")
        self.assertIsNone(value["metrics"])
        self.assertNotIn("synthetic-sensitive-request", str(value))

    def test_expired_cert_unhealthy_lb_and_failed_work_are_actionable(self):
        self.responses["certificate"]["current-version"]["validity"]["time-not-after"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
        self.responses["load-balancer-health"]["status"] = "CRITICAL"
        self.responses["work-request"]["items"][0]["status"] = "FAILED"
        value = self.collect()
        for name in ("certificate_expiry", "load_balancer", "recent_work_requests"):
            self.assertEqual(self.status(value, name), "failed")
        self.assertTrue(all(c["recovery"] for c in value["checks"]))

    def test_missing_metrics_do_not_mean_zero(self):
        self.responses["metric-data"] = []
        value = self.collect()
        self.assertIsNone(value["metrics"])
        self.assertEqual(self.status(value, "metrics"), "unknown")

    def test_wrong_metric_scope_is_unknown(self):
        self.responses["metric-data"][0]["dimensions"]["resourceId"] = "different"
        self.assertIsNone(self.collect()["metrics"])

    def test_malformed_dimensions_duplicate_points_and_unknown_work_stay_unknown(self):
        original = copy.deepcopy(self.responses)
        for change in ("dimensions", "duplicate", "compartment"):
            self.responses = copy.deepcopy(original)
            metric = self.responses["metric-data"][0]
            if change == "dimensions":
                metric["dimensions"] = None
            elif change == "duplicate":
                metric["aggregated-datapoints"] *= 2
            else:
                metric["compartment-id"] = "wrong"
            self.assertIsNone(self.collect()["metrics"])
        self.responses = original
        for status in ("IN_PROGRESS", "UNRECOGNIZED"):
            self.responses["work-request"]["items"][0]["status"] = status
            self.assertEqual(self.status(self.collect(), "recent_work_requests"), "unknown")

    def test_unexpected_topology_is_not_partially_verified(self):
        self.receipt["resources"].append(copy.deepcopy(self.receipt["resources"][0]))
        with self.assertRaises(ValueError):
            self.collect()

    def billing(self, items, *, paged=False):
        now = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = (now - dt.timedelta(days=2)).isoformat(), (now - dt.timedelta(days=1)).isoformat()
        private = {"tenant_id": "ocid1.tenancy.oc1..syntheticbilling", "period_start_utc": start, "period_end_utc": end}
        rows = [{"computed-amount": amount, "currency": currency, "compartment-id": COMPARTMENT, "region": "us-phoenix-1",
                 "resource-id": resource, "time-usage-started": start, "time-usage-ended": end} for amount, currency, resource in items]
        calls = []
        def client(arguments):
            calls.append(arguments)
            return {"data": {"items": rows}, "opc-next-page": "more" if paged else None}
        result = ops.costs(self.config, private, client, [INSTANCE, LB])
        self.assertIn("--filter", calls[0]); self.assertIn("--group-by", calls[0])
        return result

    def test_reported_costs_are_scoped_and_currency_explicit(self):
        value = self.billing([(2.25, "USD", INSTANCE), (1.75, "USD", LB)])
        self.assertEqual(value["reported_amount"], 4)
        self.assertEqual(value["currency"], "USD")

    def test_empty_partial_mixed_or_wrong_scope_costs_remain_unknown(self):
        for rows in ([], [(1, "USD", INSTANCE)], [(1, "USD", INSTANCE), (1, "AUD", LB)], [(1, "USD", "other")],
                     [(1, "USD", INSTANCE), (1, "USD", INSTANCE), (1, "USD", LB)]):
            with self.subTest(rows=rows):
                self.assertIsNone(self.billing(rows)["reported_amount"])
        self.assertIsNone(self.billing([(1, "USD", INSTANCE)], paged=True)["reported_amount"])


class BoundObservation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / "app"; self.app.mkdir()
        self.common, self.p = ops.modules()
        self.env = self.p.helper("environments")
        self.fixture = Operations(); self.fixture.setUp()
        self.stack = self.app / "deploy/rehearsal"
        self.stack.mkdir(parents=True)
        for path in (ROOT / "blueprints/web-container/terraform").glob("*.tf"):
            shutil.copyfile(path, self.stack / path.name)
        (self.stack / "backend.tf.json").write_text('{"terraform":{"backend":{"oci":{}}}}')
        with self.p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": self.p.SCHEMA, "task": "build", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": self.p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": self.p.source_fingerprint(store.root_fd),
                        "kit_sha256": self.p.kit_fingerprint(), "records": {}})
        self.target = dict(self.fixture.config["target"], profile="DEFAULT", auth="api_key")
        backend = {"region": "us-phoenix-1", "namespace": "syntheticnamespace", "bucket": "synthetic-state",
                   "key": "rehearsal/state.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        self.env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal",
                        target=self.target, backend=backend)
        gate = self.p.helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py")
        binding = gate.select(self.stack, project=self.app, environment="rehearsal", backend=dict(backend, config_file_profile="DEFAULT", auth="APIKey"))
        directory = self.stack / ".gate/receipts"; directory.mkdir(parents=True, mode=0o700)
        resources = [dict(row, compartment_id=COMPARTMENT) for row in self.fixture.receipt["resources"]]
        self.receipt = {"schema": "oci-deploy-receipt/2", "kind": "apply", "status": "applied", "plan_sha256": "1" * 64,
                        "started_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)).isoformat(),
                        "project_environment": binding, "resources": resources}
        self.path = directory / "initial.json"; self.write(self.path, self.receipt)

    def write(self, path, value):
        path.write_text(json.dumps(value)); path.chmod(0o600)

    def observe(self):
        return ops.request(self.app, environment="rehearsal", live=True, client=self.fixture.client)

    def test_bound_receipt_can_be_read_under_write_lock_without_nested_store(self):
        with self.p.Store(self.app, environment="rehearsal", write=True) as store:
            value, digest = ops.receipt_at(store, self.p)
            self.assertEqual(digest, self.p.digest(self.p.canonical(self.receipt)))
            self.assertEqual(value["status"], "applied")

    def test_injected_client_stays_test_evidence_and_support_is_allowlisted(self):
        result = self.observe()
        self.assertEqual(result["mode"], "injected-test-client")
        path = self.app / result["evidence"]
        record = json.loads(path.read_text()); record["raw_logs"] = "synthetic-sensitive-canary"
        record["domain"] = "private.example.invalid"; self.write(path, record)
        with self.p.Store(self.app, environment="rehearsal") as store:
            view = self.p.helper("dashboard").view(store, self.p)
        self.assertEqual(view["deployed_image_identity"], "not-independently-verified")
        export = self.p.helper("support").request(self.app, environment="rehearsal", write=True)
        raw = (self.app / export["path"]).read_text()
        for forbidden in ("synthetic-sensitive-canary", "private.example.invalid", "ocid1.", "rehearsal", str(self.app)):
            self.assertNotIn(forbidden, raw)
        self.assertIn("injected-test-client", raw)

    def test_latest_failed_or_wrong_binding_receipt_blocks_and_invalidates_dashboard(self):
        result = self.observe()
        for changed in (dict(self.receipt, status="failed"),
                        dict(self.receipt, project_environment=dict(self.receipt["project_environment"], environment="production"))):
            changed["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            self.write(self.path.parent / "latest.json", changed)
            with self.p.Store(self.app, environment="rehearsal", write=True) as store:
                with self.assertRaises(ValueError):
                    ops.receipt_at(store, self.p, self.path)
                view = self.p.helper("dashboard").view(store, self.p)
            self.assertNotIn("oci-operating-observation/1/web", view["observations"])
            self.assertGreater(view["stale_reports"], 0)

    def test_changed_receipt_during_collection_does_not_save_a_report(self):
        def client(arguments):
            self.write(self.path, dict(self.receipt, status="failed"))
            return self.fixture.client(arguments)
        with self.assertRaises(ValueError):
            ops.request(self.app, environment="rehearsal", live=True, client=client)
        self.assertFalse(list((self.app / ".oci-kit/environments/rehearsal/evidence").glob("observe-*")))

    def test_tied_reports_do_not_select_a_convenient_success(self):
        result = self.observe()
        path = self.app / result["evidence"]; record = json.loads(path.read_text())
        self.write(path.parent / "observe-tied.json", dict(record, status="failed"))
        with self.p.Store(self.app, environment="rehearsal") as store:
            view = self.p.helper("dashboard").view(store, self.p)
        self.assertNotIn("oci-operating-observation/1/web", view["observations"])

    def test_changed_session_stops_before_another_read(self):
        files = mock.Mock(); auth = mock.Mock()
        files.fingerprint.return_value = "reviewed-cli"
        files.sha.return_value = "config-hash"; auth._read.return_value = b"synthetic-config"
        auth.inspect.side_effect = [{"identity": "initial"}, {"identity": "changed"}]
        readiness = mock.Mock(); readiness.load.side_effect = [files, auth]
        p = mock.Mock(); p.helper.return_value = readiness
        client = ops.Client(p, self.target, Path("/synthetic/config"))
        with self.assertRaises(ValueError):
            client(["container-instances", "container-instance", "get"])
        files.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
