"""Contract for the approval-gated deploy tool.

Terraform is replaced by tests/fixtures/fake_terraform.py; nothing here
touches a cloud account. Several tests come from an adversarial review: each
one pins a way an apply could escape the approved plan.
"""

import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "oci-deploy" / "scripts"))

import deploy_gate as gate  # noqa: E402

FAKE_TF = ROOT / "tests" / "fixtures" / "fake_terraform.py"
REGION_OCID = "ocid1.vcn.oc1.ap-melbourne-1.aaa"
DB_OCID = "ocid1.postgresqldbsystem.oc1.ap-melbourne-1.bbb"

PLAN = {
    "format_version": "1.2",
    "terraform_version": "1.16.6",
    "variables": {"region": {"value": "ap-melbourne-1"}, "compartment_ocid": {"value": "ocid1.compartment.oc1..sandbox"},
                  "config_file_profile": {"value": "DEFAULT"}, "db_admin_password": {"value": "do-not-print-me"}},
    "resource_changes": [
        {"address": "oci_core_vcn.main", "type": "oci_core_vcn", "name": "main", "change": {"actions": ["create"]}},
        {"address": "oci_psql_db_system.db", "type": "oci_psql_db_system", "name": "db", "change": {"actions": ["create"]}},
        {"address": "oci_objectstorage_bucket.uploads", "type": "oci_objectstorage_bucket", "name": "uploads",
         "change": {"actions": ["update"]}},
        {"address": "oci_identity_policy.app", "type": "oci_identity_policy", "name": "app",
         "change": {"actions": ["create"]}},
        {"address": "data.oci_identity_availability_domains.ads", "type": "oci_identity_availability_domains",
         "mode": "data", "name": "ads", "change": {"actions": ["read"]}},
    ],
    "output_changes": {"lb_ip": {"actions": ["create"]}},
}
DESTROY_PLAN = {**PLAN, "resource_changes": [
    {"address": "oci_core_vcn.main", "type": "oci_core_vcn", "name": "main", "change": {"actions": ["delete"]}}]}
STATE = {"values": {"root_module": {"resources": [
    {"address": "oci_core_vcn.main", "type": "oci_core_vcn", "name": "main", "mode": "managed",
     "values": {"id": REGION_OCID, "display_name": "founder-vcn", "compartment_id": "ocid1.compartment.oc1..sandbox"},
     "sensitive_values": {}},
    {"address": "oci_psql_db_system.db", "type": "oci_psql_db_system", "name": "db", "mode": "managed",
     "values": {"id": DB_OCID, "display_name": "SENSITIVE-DISPLAY", "compartment_id": "ocid1.compartment.oc1..sandbox",
                "credentials": [{"password_details": [{"password": "do-not-print-me"}]}]},
     "sensitive_values": {"display_name": True}},
    {"address": "random_password.db", "type": "random_password", "name": "db", "mode": "managed",
     "values": {"id": "none", "result": "do-not-print-me"}, "sensitive_values": {"result": True}},
]}}}


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.stack = self.tmp / "stack"
        self.stack.mkdir()
        (self.stack / "main.tf").write_text("# stack\n")
        self.log = self.tmp / "tf.log"
        self.write_json("plan.json", PLAN)
        self.write_json("state.json", STATE)
        keys = ["TF_BIN", "FAKE_TF_LOG", "FAKE_TF_PLAN_JSON", "FAKE_TF_STATE_JSON", "FAKE_TF_PLAN_BYTES",
                "FAKE_TF_FAIL", "FAKE_TF_FAIL_STATE", "FAKE_TF_LEAK", "TF_CLI_ARGS", "TF_CLI_ARGS_apply"]
        self._old = {k: os.environ.get(k) for k in keys}
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update({"TF_BIN": str(FAKE_TF), "FAKE_TF_LOG": str(self.log),
                           "FAKE_TF_PLAN_JSON": str(self.tmp / "plan.json"),
                           "FAKE_TF_STATE_JSON": str(self.tmp / "state.json")})
        self.addCleanup(self.restore_env)

    def restore_env(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write_json(self, name, data):
        (self.tmp / name).write_text(json.dumps(data))

    @property
    def gate_dir(self):
        return self.stack / ".gate"

    def run_gate(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gate.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def plan(self, *extra):
        code, out, err = self.run_gate("plan", "--dir", str(self.stack), *extra)
        self.assertEqual(code, 0, err)
        return json.loads((self.gate_dir / "plan-summary.json").read_text()), out

    def apply(self, sha, command="apply"):
        return self.run_gate(command, "--dir", str(self.stack), "--approve", sha)

    def applied(self):
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines() if line.startswith("APPLIED")]

    def receipts(self, kind="apply"):
        folder = self.gate_dir / "receipts"
        return sorted(folder.glob(f"*-{kind}-*.json")) if folder.exists() else []


class Plan(GateTestCase):
    def test_summary_binds_the_exact_plan_bytes(self):
        summary, out = self.plan()
        plan_bytes = (self.gate_dir / "tfplan").read_bytes()
        self.assertEqual(summary["plan_sha256"], hashlib.sha256(plan_bytes).hexdigest())
        self.assertIn(summary["plan_sha256"], out)
        self.assertIn("--approve", out)

    def test_counts_resources_and_skips_data_sources(self):
        summary, _ = self.plan()
        self.assertEqual(summary["changes"], {"create": 3, "update": 1, "delete": 0, "replace": 0})
        self.assertEqual(len(summary["resources"]), 4)
        self.assertFalse(summary["destructive"])
        self.assertEqual(summary["kind"], "apply")

    def test_access_changes_are_called_out(self):
        summary, out = self.plan()
        self.assertEqual(summary["access_changes"], ["oci_identity_policy.app"])
        self.assertIn("ACCESS", out)

    def test_target_comes_from_variables_and_secrets_never_appear(self):
        summary, out = self.plan()
        self.assertEqual(summary["target"], {"region": "ap-melbourne-1", "compartment_ocid": "ocid1.compartment.oc1..sandbox",
                                             "profile": "DEFAULT"})
        for path in self.gate_dir.rglob("*"):
            if path.is_file() and path.name != "tfplan":
                self.assertNotIn("do-not-print-me", path.read_text())
        self.assertNotIn("do-not-print-me", out)

    def test_records_the_terraform_binary_and_expiry(self):
        summary, _ = self.plan("--max-age-minutes", "30")
        self.assertEqual(summary["terraform"]["path"], str(FAKE_TF))
        self.assertEqual(summary["terraform"]["sha256"], hashlib.sha256(FAKE_TF.read_bytes()).hexdigest())
        self.assertAlmostEqual(summary["expires_at_epoch"] - summary["created_at_epoch"], 1800, delta=1)

    def test_machine_readable_plan_is_not_kept_and_files_are_private(self):
        self.plan()
        self.assertFalse((self.gate_dir / "plan.json").exists())
        self.assertEqual(stat.S_IMODE(self.gate_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.gate_dir / "tfplan").stat().st_mode), 0o600)

    def test_bad_max_age_and_bad_tf_bin_are_input_errors(self):
        self.assertEqual(self.run_gate("plan", "--dir", str(self.stack), "--max-age-minutes", "0")[0], 2)
        os.environ["TF_BIN"] = f"{sys.executable} {FAKE_TF}"
        code, _, err = self.run_gate("plan", "--dir", str(self.stack))
        self.assertEqual(code, 2)
        self.assertIn("TF_BIN", err)

    def test_terraform_failure_never_echoes_stdout(self):
        os.environ["FAKE_TF_FAIL"] = "plan"
        os.environ["FAKE_TF_LEAK"] = "hunter2-from-plan-diff"
        code, out, err = self.run_gate("plan", "--dir", str(self.stack))
        self.assertEqual(code, 1)
        self.assertIn("terraform plan failed", err)
        self.assertNotIn("hunter2", err + out)
        log = self.gate_dir / "last-error.log"
        self.assertIn("hunter2", log.read_text())
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)

    def test_tf_cli_args_are_not_passed_to_terraform(self):
        os.environ["TF_CLI_ARGS_apply"] = "-auto-approve"
        self.plan()
        self.assertNotIn("TF_CLI_ARGS", self.log.read_text())

    def test_symlinked_gate_directory_is_refused(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir(mode=0o755)
        (self.stack / ".gate").symlink_to(elsewhere)
        code, _, err = self.run_gate("plan", "--dir", str(self.stack))
        self.assertEqual(code, 2)
        self.assertIn("symlink", err)
        self.assertEqual(stat.S_IMODE(elsewhere.stat().st_mode), 0o755)

    def test_destroy_plan_is_marked_destructive(self):
        self.write_json("plan.json", DESTROY_PLAN)
        code, out, _ = self.run_gate("destroy-plan", "--dir", str(self.stack))
        self.assertEqual(code, 0)
        summary = json.loads((self.gate_dir / "plan-summary.json").read_text())
        self.assertEqual(summary["kind"], "destroy")
        self.assertTrue(summary["destructive"])
        self.assertIn("DESTROYS", out)
        self.assertIn("-destroy", self.log.read_text())


class Apply(GateTestCase):
    def test_wrong_hash_is_refused_and_the_plan_survives(self):
        self.plan()
        code, _, err = self.apply("0" * 64)
        self.assertEqual(code, 3)
        self.assertIn("does not match", err)
        self.assertEqual(self.applied(), [])
        self.assertTrue((self.gate_dir / "tfplan").exists())

    def test_right_hash_applies_the_approved_bytes_once(self):
        summary, _ = self.plan()
        code, out, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 0, err)
        [line] = self.applied()
        self.assertTrue(line.endswith(summary["plan_sha256"]))
        self.assertIn(".applying", line)
        [receipt_path] = self.receipts()
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(receipt["plan_sha256"], summary["plan_sha256"])
        self.assertIn(receipt_path.name, out)

    def test_receipts_drop_sensitive_values_and_non_ocid_ids(self):
        summary, _ = self.plan()
        self.apply(summary["plan_sha256"])
        text = self.receipts()[0].read_text()
        self.assertNotIn("do-not-print-me", text)
        self.assertNotIn("SENSITIVE-DISPLAY", text)
        resources = {r["address"]: r for r in json.loads(text)["resources"]}
        self.assertEqual(resources["oci_core_vcn.main"]["name"], "founder-vcn")
        self.assertIsNone(resources["oci_psql_db_system.db"]["name"])
        self.assertIsNone(resources["random_password.db"]["id"])

    def test_a_plan_cannot_be_applied_twice(self):
        summary, _ = self.plan()
        self.apply(summary["plan_sha256"])
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("no approved plan", err.lower())
        self.assertEqual(len(self.applied()), 1)

    def test_tampered_plan_is_refused(self):
        summary, _ = self.plan()
        (self.gate_dir / "tfplan").write_text("a different plan")
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("changed since", err)
        self.assertEqual(self.applied(), [])

    def test_summary_that_does_not_match_the_plan_contents_is_refused(self):
        summary, _ = self.plan()
        path = self.gate_dir / "plan-summary.json"
        data = json.loads(path.read_text())
        data["resources"] = data["resources"][:1]
        data["changes"] = {"create": 1, "update": 0, "delete": 0, "replace": 0}
        path.write_text(json.dumps(data))
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("does not match the plan's contents", err)
        self.assertEqual(self.applied(), [])

    def test_expiry_is_fixed_at_plan_time(self):
        summary, _ = self.plan()
        path = self.gate_dir / "plan-summary.json"
        data = json.loads(path.read_text())
        data["expires_at_epoch"] = time.time() - 1
        path.write_text(json.dumps(data))
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("expired", err)
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                gate.main(["apply", "--dir", str(self.stack), "--approve", summary["plan_sha256"],
                           "--max-age-minutes", "99999"])

    def test_future_timestamps_are_refused(self):
        summary, _ = self.plan()
        path = self.gate_dir / "plan-summary.json"
        data = json.loads(path.read_text())
        data["created_at_epoch"] = 1e12
        path.write_text(json.dumps(data))
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("clock", err)

    def test_a_different_terraform_binary_is_refused(self):
        summary, _ = self.plan()
        other = self.tmp / "terraform-other"
        other.write_text(FAKE_TF.read_text() + "\n# different\n")
        other.chmod(0o755)
        os.environ["TF_BIN"] = str(other)
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("binary", err)
        self.assertEqual(self.applied(), [])

    def test_destroy_plan_cannot_be_used_by_apply_and_vice_versa(self):
        self.write_json("plan.json", DESTROY_PLAN)
        self.run_gate("destroy-plan", "--dir", str(self.stack))
        summary = json.loads((self.gate_dir / "plan-summary.json").read_text())
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("destroy plan", err)
        code, _, err = self.apply(summary["plan_sha256"], command="destroy")
        self.assertEqual(code, 0, err)
        [receipt] = self.receipts("destroy")
        destroyed = json.loads(receipt.read_text())["destroyed_resources"]
        self.assertIn(REGION_OCID, {r["id"] for r in destroyed})

    def test_failed_apply_consumes_the_approval_and_records_the_attempt(self):
        summary, _ = self.plan()
        os.environ["FAKE_TF_FAIL"] = "apply"
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 1)
        self.assertIn("terraform apply failed", err)
        self.assertIn("may have been created", err)
        self.assertEqual(json.loads(self.receipts()[0].read_text())["status"], "failed")
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)

    def test_apply_that_cannot_be_recorded_exits_5(self):
        summary, _ = self.plan()
        os.environ["FAKE_TF_FAIL_STATE"] = "1"
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 5)
        self.assertIn("applied but not recorded", err)
        self.assertEqual(json.loads(self.receipts()[0].read_text())["status"], "applied-unrecorded")
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)

    def test_empty_state_output_is_not_success(self):
        summary, _ = self.plan()
        (self.tmp / "state.json").write_text("")
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 5)

    def test_symlinked_plan_file_is_refused(self):
        summary, _ = self.plan()
        plan = self.gate_dir / "tfplan"
        real = self.tmp / "real-plan"
        real.write_bytes(plan.read_bytes())
        plan.unlink()
        plan.symlink_to(real)
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3)
        self.assertIn("symlink", err)


class Teardown(GateTestCase):
    def receipt(self):
        summary, _ = self.plan()
        self.apply(summary["plan_sha256"])
        return self.receipts()[0]

    def test_all_gone(self):
        result = gate.verify_teardown(json.loads(self.receipt().read_text()), lambda ocid: "TERMINATED")
        self.assertTrue(result["clean"])
        self.assertEqual(result["checked"], 2)

    def test_reports_what_is_still_alive_or_unknown(self):
        states = {REGION_OCID: "UNKNOWN", DB_OCID: "ACTIVE"}
        result = gate.verify_teardown(json.loads(self.receipt().read_text()), states.get)
        self.assertFalse(result["clean"])
        self.assertEqual({r["id"] for r in result["remaining"]}, {REGION_OCID, DB_OCID})

    def test_malformed_ocid_is_never_queried(self):
        receipt = {"kind": "apply", "status": "applied", "resources": [
            {"address": "x", "type": "oci_core_vcn", "id": "ocid1.a.b' || identifier != 'zzz"}]}
        calls = []
        result = gate.verify_teardown(receipt, lambda ocid: calls.append(ocid))
        self.assertEqual(calls, [])
        self.assertFalse(result["clean"])
        self.assertEqual(result["remaining"][0]["state"], "INVALID_OCID")

    def test_oci_cli_checker(self):
        found = mock.Mock(returncode=0, stdout=json.dumps({"data": {"items": [{"lifecycle-state": "ACTIVE"}]}}))
        stateless = mock.Mock(returncode=0, stdout=json.dumps({"data": {"items": [{}]}}))
        empty = mock.Mock(returncode=0, stdout=json.dumps({"data": {"items": []}}))
        with mock.patch.object(gate.subprocess, "run", side_effect=[found, stateless, empty]) as run:
            check = gate.oci_cli_state("DEFAULT", "us-ashburn-1")
            self.assertEqual(check(REGION_OCID), "ACTIVE")
            self.assertEqual(check(DB_OCID), "UNKNOWN")
            self.assertIsNone(check("ocid1.compartment.oc1..x"))
        first, last = run.call_args_list[0][0][0], run.call_args_list[2][0][0]
        self.assertEqual(first[:4], ["oci", "search", "resource", "structured-search"])
        self.assertEqual(first[first.index("--region") + 1], "ap-melbourne-1")
        self.assertEqual(last[last.index("--region") + 1], "us-ashburn-1")

    def test_verify_command_exit_codes(self):
        receipt = self.receipt()
        with mock.patch.object(gate, "oci_cli_state", return_value=lambda ocid: None):
            code, out, _ = self.run_gate("verify-teardown", "--receipt", str(receipt))
        self.assertEqual((code, "Teardown verified" in out), (0, True))
        with mock.patch.object(gate, "oci_cli_state", return_value=lambda ocid: "AVAILABLE"):
            code, out, _ = self.run_gate("verify-teardown", "--receipt", str(receipt))
        self.assertEqual((code, "Teardown incomplete" in out), (4, True))

    def test_nothing_to_verify_is_not_success(self):
        empty = self.tmp / "empty-receipt.json"
        empty.write_text(json.dumps({"kind": "apply", "status": "applied", "resources": []}))
        code, _, err = self.run_gate("verify-teardown", "--receipt", str(empty))
        self.assertEqual(code, 2)
        self.assertIn("nothing to verify", err)

    def test_cli_failure_is_reported_briefly_not_treated_as_gone(self):
        receipt = self.receipt()
        failing = mock.Mock(returncode=1, stdout="", stderr="ServiceError: NotAuthenticated\nsecret-ish detail\n")
        with mock.patch.object(gate.subprocess, "run", return_value=failing):
            code, _, err = self.run_gate("verify-teardown", "--receipt", str(receipt))
        self.assertEqual(code, 1)
        self.assertIn("oci search failed", err)
        self.assertNotIn("secret-ish", err)


class Status(GateTestCase):
    def test_status_without_and_with_a_plan(self):
        code, out, _ = self.run_gate("status", "--dir", str(self.stack))
        self.assertEqual((code, "No plan" in out), (0, True))
        summary, _ = self.plan()
        code, out, _ = self.run_gate("status", "--dir", str(self.stack))
        self.assertIn(summary["plan_sha256"], out)

    def test_missing_stack_dir(self):
        code, _, _ = self.run_gate("plan", "--dir", str(self.tmp / "nope"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
