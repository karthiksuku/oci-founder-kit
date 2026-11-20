"""Workload checks distinguish denied reads, quota, capacity and local selections."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("readiness_test", ROOT / "scripts/readiness.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class Readiness(unittest.TestCase):
    def setUp(self):
        self.config = {"schema": "oci-kit-environment/1", "name": "rehearsal", "role": "rehearsal",
                       "blueprint": "web-container", "infrastructure": "deploy/rehearsal", "target": {
            "region": "us-phoenix-1", "compartment_id": "ocid1.compartment.oc1..synthetic",
            "vcn_id": "ocid1.vcn.oc1.test.synthetic", "app_subnet_id": "ocid1.subnet.oc1.test.private",
            "lb_subnet_id": "ocid1.subnet.oc1.test.public", "registry_id": "ocid1.containerrepo.oc1.test.synthetic",
            "certificate_id": "ocid1.certificate.oc1.test.synthetic", "availability_domain": "TEST:AD-1",
            "ocpus": 1, "memory_gbs": 4, "image_architecture": "AMD64", "image_digest": "sha256:" + "b" * 64,
            "port": 8080, "health_path": "/healthz", "origin": "https://app.example.invalid"}}
        self.original_load = r.load
        self.doctor = r.load("skills/oci-ready/scripts/oci_doctor.py")
        self.doctor.diagnose = lambda **kwargs: {"schema": "oci-readiness/1", "status": "passed", "checks": [], "mode": "live-read-only"}
        def load(path):
            return self.doctor if path.endswith("oci_doctor.py") else self.original_load(path)
        self.loader = mock.patch.object(r, "load", side_effect=load)
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def run_with(self, runner, live=True):
        return r.diagnose(self.config, live=live, which=lambda _: "/synthetic/tool", runner=runner)

    def test_denied_reads_remain_unknown_and_handoff_has_no_resource_payload(self):
        calls = []
        def denied(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=1, stdout="PRIVATE_PROVIDER_ERROR", stderr="PRIVATE_PROVIDER_ERROR")
        result = self.run_with(denied)
        self.assertEqual(len(calls), 7)
        checks = {c["check"]: c["status"] for c in result["checks"]}
        self.assertEqual(checks["quota_ocpus"], "unknown")
        self.assertEqual(checks["vcn"], "unknown")
        self.assertEqual(checks["physical_capacity"], "unknown")
        self.assertTrue(result["administrator_handoff"])
        packet = result["permission_review"]
        permissions = {row["check"]:row["permission_to_verify"] for row in packet["reads_to_verify"]}
        self.assertEqual(permissions["vcn"], "VCN_READ")
        self.assertEqual(permissions["certificate"], "CERTIFICATE_READ")
        self.assertEqual(permissions["quota_ocpus"], "read resource-availability")
        self.assertEqual(packet["recheck_command"][-3:], ["--environment", self.config["name"], "--live"])
        self.assertNotIn("PRIVATE_PROVIDER_ERROR", json.dumps(result))
        self.assertNotIn("ocid1", json.dumps(result))

    def test_successful_reads_do_not_prove_capacity_or_runtime(self):
        def successful(argv, **kwargs):
            if "limits" in argv:
                data = {"available": 20}
            else:
                data = {"id": argv[-1], "lifecycle-state": "ACTIVE" if "certs-mgmt" in argv else "AVAILABLE",
                        "is-public": False, "vcn-id": self.config["target"]["vcn_id"],
                        "prohibit-public-ip-on-vnic": argv[-1] == self.config["target"]["app_subnet_id"]}
            return SimpleNamespace(returncode=0, stdout=json.dumps({"data": data}))
        result = self.run_with(successful)
        checks = {c["check"]: c["status"] for c in result["checks"]}
        for name in ("vcn", "app_subnet_id", "lb_subnet_id", "registry", "certificate", "quota_ocpus", "quota_memory_gbs"):
            self.assertEqual(checks[name], "passed", name)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["permission_review"]["reads_to_verify"])
        self.assertFalse(result["production_ready"])
        self.assertEqual(checks["physical_capacity"], "unknown")
        self.assertEqual(checks["image_architecture"], "unknown")

    def test_insufficient_quota_and_inactive_resources_do_not_request_more_access(self):
        def readable(argv, **kwargs):
            if "limits" in argv:
                data = {"available": 0}
            else:
                data = {"id": argv[-1], "lifecycle-state": "UNAVAILABLE"}
            return SimpleNamespace(returncode=0, stdout=json.dumps({"data": data}))
        self.doctor.diagnose = lambda **kwargs: {"status":"passed", "checks":[
            {"check":"region_subscription","status":"blocked","api_read":"passed"}]}
        result = self.run_with(readable)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["permission_review"]["reads_to_verify"], [])

    def test_offline_makes_no_requests_and_wrong_architecture_blocks(self):
        self.config["target"]["image_architecture"] = "ARM64"
        with mock.patch("subprocess.run", side_effect=AssertionError("Offline must make no requests")):
            result = self.run_with(lambda *_a, **_k: self.fail("offline runner called"), live=False)
        self.assertEqual(result["status"], "blocked")

    def test_expired_session_blocks_before_any_remote_operation(self):
        self.config["target"]["auth"] = "security_token"
        session = SimpleNamespace(session_readiness=mock.Mock(side_effect=ValueError("expired")))
        original = r.load.side_effect
        r.load.side_effect = lambda path: session if path.endswith("backend_auth.py") else original(path)
        def diagnose(**kwargs):
            self.assertFalse(kwargs["live"])
            return {"status": "incomplete", "checks": []}
        self.doctor.diagnose = diagnose
        result = self.run_with(lambda *_a, **_k: self.fail("expired session must not invoke OCI"))
        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
