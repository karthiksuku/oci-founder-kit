"""Synthetic session profiles and fake Terraform only; no OCI requests or real keys."""
import base64
import json
import os
import time
from unittest import mock

import test_deploy_gate as fixtures
from test_backend_ops import CONFIG
import backend_auth as auth
import backend_ops as ops


class SessionBackend(fixtures.GateTestCase):
    def setUp(self):
        super().setUp()
        self.session_home = self.tmp / "synthetic-home"
        self.credentials = self.session_home / ".oci"
        self.credentials.mkdir(parents=True, mode=0o700)
        home = mock.patch.object(auth.Path, "home", return_value=self.session_home)
        home.start()
        self.addCleanup(home.stop)
        self.identity = {"user": "ocid1.user.oc1..syntheticuser", "tenancy": "ocid1.tenancy.oc1..synthetictenancy"}
        self.key = self.credentials / "key.pem"
        self.key.write_text("-----BEGIN " + "PRIVATE KEY-----\nSYNTHETIC-NOT-A-KEY\n-----END " + "PRIVATE KEY-----\n")
        self.key.chmod(0o600)
        self.token = self.credentials / "token"
        self.write_token()
        self.profile = self.credentials / "config"
        self.write_profile()
        self.settings = {**CONFIG, "auth": "SecurityToken", "config_file_profile": "FOUNDER"}
        self.config = self.tmp / "session-backend.json"
        self.config.write_text(json.dumps(self.settings))
        self.config.chmod(0o600)
        (self.stack / "backend.tf.json").write_text(json.dumps(ops.DECLARATION))
        self.write_json("plan.json", {**fixtures.PLAN, "variables": {**fixtures.PLAN["variables"],
                        "auth": {"value": "SecurityToken"}, "config_file_profile": {"value": "FOUNDER"}}})

    def write_profile(self, **overrides):
        values = {**self.identity, "region": CONFIG["region"], "key_file": str(self.key),
                  "security_token_file": str(self.token), **overrides}
        self.profile.write_text("[FOUNDER]\n" + "".join(f"{k}={v}\n" for k, v in values.items()))
        self.profile.chmod(0o600)

    def write_token(self, **overrides):
        now = int(time.time())
        claims = {"sub": self.identity["user"], "tenant": self.identity["tenancy"],
                  "exp": now + 3600, "iat": now - 1, **overrides}
        encode = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
        self.token.write_text(encode({"alg": "RS256"}) + "." + encode(claims) + ".c3ludGhldGlj")
        self.token.chmod(0o600)

    def prepare(self, kind="init", *extra):
        args = ["backend-plan", "--dir", str(self.stack), "--operation", kind]
        if kind == "init":
            args += ["--backend-config", str(self.config)]
        return self.run_gate(*args, *extra)

    def packet(self):
        return json.loads((self.gate_dir / ops.PLAN).read_text())

    def run_packet(self):
        return self.run_gate("backend-run", "--dir", str(self.stack), "--approve", self.packet()["sha256"])

    def initialize(self):
        self.assertEqual(self.prepare()[0], 0)
        result = self.run_packet()
        self.assertEqual(result[0], 0, result[2])

    def remote_plan(self):
        self.initialize()
        self.assertEqual(self.prepare("plan")[0], 0)
        result = self.run_packet()
        self.assertEqual(result[0], 0, result[2])
        return json.loads((self.gate_dir / "plan-summary.json").read_text())

    def test_session_init_plan_apply_and_private_receipts(self):
        summary = self.remote_plan()
        self.assertEqual(summary["backend_authentication"]["auth"], "SecurityToken")
        self.assertLessEqual(summary["expires_at_epoch"], auth.inspect(self.settings)["expires_at_epoch"] - 600)
        result = self.apply(summary["plan_sha256"])
        self.assertEqual(result[0], 0, result[2])
        self.assertEqual(len(self.applied()), 1)
        receipt = json.loads(self.receipts()[0].read_text())
        self.assertEqual(receipt["backend_authentication"], summary["backend_authentication"])

    def test_preparation_is_offline_and_contains_hashes_only(self):
        code, out, err = self.prepare()
        self.assertEqual(code, 0, err)
        self.assertFalse(self.log.exists())
        public = out + err + json.dumps(self.packet())
        for secret in (self.token.read_text(), self.key.read_text(), *self.identity.values()):
            self.assertNotIn(secret, public)
        self.assertIn("SecurityToken", out)

    def test_expired_nearly_expired_and_invalid_expiry_stop_before_client(self):
        for expiry in (int(time.time()) - 1, int(time.time()) + 599, True, "9999999999", None):
            with self.subTest(expiry=expiry):
                self.write_token(exp=expiry)
                code, _, err = self.prepare()
                self.assertEqual(code, 3)
                self.assertIn("session", err.lower())
                self.assertFalse(self.log.exists())

    def test_malformed_and_future_token_redacted(self):
        for token in ("synthetic-token-do-not-print", "e30.e30.c2ln", "x.y.z", "x" * 65537):
            with self.subTest(length=len(token)):
                self.token.write_text(token)
                code, out, err = self.prepare()
                self.assertEqual(code, 3)
                self.assertNotIn(token, out + err)
                self.assertFalse(self.log.exists())
        for name in ("iat", "nbf"):
            self.write_token(**{name: int(time.time()) + 300})
            self.assertEqual(self.prepare()[0], 3)

    def test_identity_mismatch_and_profile_override_refused(self):
        self.write_token(sub="ocid1.user.oc1..anotheruser")
        self.assertEqual(self.prepare()[0], 3)
        self.write_token()
        self.write_profile(pass_phrase="synthetic-secret-not-printed")
        code, out, err = self.prepare()
        self.assertEqual(code, 3)
        self.assertNotIn("synthetic-secret-not-printed", out + err)
        self.assertFalse(self.log.exists())

    def test_token_refresh_requires_new_exact_packet(self):
        self.assertEqual(self.prepare()[0], 0)
        old = self.packet()["sha256"]
        self.write_token(exp=int(time.time()) + 4000)
        code, _, err = self.run_packet()
        self.assertEqual(code, 3)
        self.assertIn("fresh plan", err)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.prepare()[0], 0)
        self.assertNotEqual(old, self.packet()["sha256"])
        self.assertEqual(self.run_packet()[0], 0)

    def test_refreshed_token_rejects_saved_resource_plan_without_starting_client(self):
        summary = self.remote_plan()
        before = self.log.read_text()
        self.write_token(exp=int(time.time()) + 4000)
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)
        self.assertEqual(self.applied(), [])

    def test_identity_rotation_rejects_pending_packet_even_when_profile_matches_new_token(self):
        self.assertEqual(self.prepare()[0], 0)
        self.identity["user"] = "ocid1.user.oc1..changedidentity"
        self.write_token()
        self.write_profile()
        self.assertEqual(self.run_packet()[0], 3)
        self.assertFalse(self.log.exists())

    def test_key_rotation_and_profile_path_change_reject_pending_packet(self):
        self.assertEqual(self.prepare()[0], 0)
        self.key.write_text(self.key.read_text().replace("NOT-A-KEY", "ANOTHER-FAKE-KEY"))
        self.assertEqual(self.run_packet()[0], 3)
        self.assertFalse(self.log.exists())

    def test_unsafe_files_directories_and_symlinks_refused(self):
        for path in (self.profile, self.key, self.token):
            with self.subTest(path=path.name):
                path.chmod(0o644)
                self.assertEqual(self.prepare()[0], 3)
                path.chmod(0o600)
        self.credentials.chmod(0o755)
        self.assertEqual(self.prepare()[0], 3)
        self.credentials.chmod(0o700)
        link = self.credentials / "key-link"
        link.symlink_to(self.key)
        self.write_profile(key_file=str(link))
        self.assertEqual(self.prepare()[0], 3)
        self.assertFalse(self.log.exists())

    def test_denied_local_read_has_actionable_redacted_error(self):
        with mock.patch.object(auth, "_read", side_effect=PermissionError("synthetic-sensitive-path")):
            code, out, err = self.prepare()
        self.assertEqual(code, 3)
        self.assertNotIn("synthetic-sensitive-path", out + err)
        self.assertIn("private session configuration", err)
        self.assertFalse(self.log.exists())

    def test_parent_symlink_and_hardlinked_credentials_refused(self):
        link = self.session_home / "linked-dir"
        link.symlink_to(self.credentials, target_is_directory=True)
        self.write_profile(key_file=str(link / "key.pem"))
        self.assertEqual(self.prepare()[0], 3)
        self.write_profile()
        os.link(self.key, self.credentials / "second-key-name")
        self.assertEqual(self.prepare()[0], 3)
        self.assertFalse(self.log.exists())

    def test_selected_profile_must_not_inherit_credentials(self):
        self.profile.write_text(self.profile.read_text().replace("[FOUNDER]", "[DEFAULT]") + "\n[FOUNDER]\n")
        self.assertEqual(self.prepare()[0], 3)
        self.assertFalse(self.log.exists())

    def test_failure_consumes_attempt_and_discards_client_token_echo(self):
        self.assertEqual(self.prepare()[0], 0)
        digest = self.packet()["sha256"]
        with mock.patch.dict(os.environ, {"FAKE_TF_FAIL": "init", "FAKE_TF_LEAK": self.token.read_text()}):
            code, out, err = self.run_packet()
        self.assertEqual(code, 1)
        self.assertNotIn(self.token.read_text(), out + err)
        self.assertIn("reauthenticate", err)
        self.assertFalse((self.gate_dir / ops.PLAN).exists())
        for path in self.gate_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.token.read_bytes(), path.read_bytes())
        receipt = json.loads((self.gate_dir / "backend-receipts" / (digest + ".json")).read_text())
        self.assertEqual(receipt["status"], "failed")
        before = self.log.read_text()
        self.assertEqual(self.run_gate("backend-run", "--dir", str(self.stack), "--approve", digest)[0], 3)
        self.assertEqual(self.log.read_text(), before)

    def test_expiry_before_apply_stops_before_any_client(self):
        summary = self.remote_plan()
        before = self.log.read_text()
        expiry = summary["backend_authentication"]["expires_at_epoch"]
        with mock.patch.object(auth.time, "time", return_value=expiry + 1):
            self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)

    def test_late_token_change_after_show_stops_apply_and_consumes_plan(self):
        summary = self.remote_plan()
        original = fixtures.gate._write_private
        def writing(path, value):
            original(path, value)
            if path.parent.name == "receipts":
                self.write_token(exp=int(time.time()) + 4000)
        with mock.patch.object(fixtures.gate, "_write_private", side_effect=writing):
            code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 3, err)
        self.assertEqual(self.applied(), [])
        self.assertFalse((self.gate_dir / "tfplan").exists())
        receipt = json.loads(self.receipts()[0].read_text())
        self.assertEqual(receipt["status"], "refused")
        self.assertFalse(receipt["apply_started"])

    def test_interruption_keeps_attempt_consumed(self):
        self.assertEqual(self.prepare()[0], 0)
        digest = self.packet()["sha256"]
        with mock.patch.object(fixtures.gate, "run_terraform", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_packet()
        self.assertFalse((self.gate_dir / ops.PLAN).exists())
        self.assertEqual(self.run_gate("backend-run", "--dir", str(self.stack), "--approve", digest)[0], 3)

    def test_provider_target_must_explicitly_use_selected_session(self):
        self.initialize()
        self.write_json("plan.json", fixtures.PLAN)
        self.assertEqual(self.prepare("plan")[0], 0)
        self.assertEqual(self.run_packet()[0], 3)
        self.assertFalse((self.gate_dir / "plan-summary.json").exists())

    def test_api_key_never_reads_session_credentials(self):
        with mock.patch.object(auth, "_read", side_effect=AssertionError("unexpected credential read")):
            self.assertEqual(auth.inspect(CONFIG), {"auth": "APIKey", "profile": "DEFAULT"})

    def test_backend_environment_cannot_switch_identity_endpoint_or_tls(self):
        for name in ("auth", "private_key", "accept_local_certs", "CLIENT_HOST_OVERRIDES", "obo_token", "use_obo_token"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: "synthetic-override-secret"}):
                code, out, err = self.prepare()
                self.assertEqual(code, 3)
                self.assertNotIn("synthetic-override-secret", out + err)
                self.assertFalse(self.log.exists())

    def test_doctor_interface_supports_explicit_path_without_disclosing_identity(self):
        observed = auth.session_readiness("FOUNDER", config_file=self.profile)
        self.assertEqual(observed["verification"], "local-consistency-only")
        self.assertEqual(observed["minimum_remaining_seconds"], 600)
        self.assertNotIn("identity_sha256", observed)
        self.write_token(exp=int(time.time()) - 1)
        with self.assertRaisesRegex(ValueError, "expired"):
            auth.session_readiness("FOUNDER", config_file=self.profile)

    def test_explicit_resource_targets_are_passed_and_recorded(self):
        self.initialize()
        self.assertEqual(self.prepare("plan", "--target", "oci_core_vcn.main")[0], 0)
        self.assertEqual(self.run_packet()[0], 0)
        summary = json.loads((self.gate_dir / "plan-summary.json").read_text())
        self.assertEqual(summary["resource_targets"], ["oci_core_vcn.main"])
        self.assertIn("-target=oci_core_vcn.main", self.log.read_text())

    def test_targeted_destroy_and_invalid_target_syntax(self):
        self.initialize()
        current = json.loads((self.tmp / "plan.json").read_text())
        self.write_json("plan.json", {**current, "resource_changes": fixtures.DESTROY_PLAN["resource_changes"]})
        self.assertEqual(self.prepare("destroy-plan", "--target", "oci_core_vcn.main")[0], 0)
        self.assertEqual(self.run_packet()[0], 0)
        summary = json.loads((self.gate_dir / "plan-summary.json").read_text())
        self.assertEqual(self.apply(summary["plan_sha256"], command="destroy")[0], 0)
        before = self.log.read_text()
        self.assertEqual(self.prepare("destroy-plan", "--target", "module.whole")[0], 3)
        self.assertEqual(self.log.read_text(), before)
