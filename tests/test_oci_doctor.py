"""Readiness behavior: offline, live read-only calls, unsafe files and non-disclosure."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "skills/oci-ready/scripts/oci_doctor.py"
SPEC = importlib.util.spec_from_file_location("oci_doctor", SCRIPT)
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)

TENANCY = "ocid1.tenancy.oc1..fixture"
COMPARTMENT = "ocid1.compartment.oc1..fixture"
REGION = "ap-melbourne-1"


class Doctor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = self.root / "key.pem"
        self.key.write_text("key content must never be read or reported")
        self.key.chmod(0o600)
        self.config = self.root / "config"
        self.config.write_text(f"[DEFAULT]\ntenancy={TENANCY}\nuser=fixture\nfingerprint=fixture\nkey_file={self.key}\nregion={REGION}\n")
        self.config.chmod(0o600)

    def diagnose(self, **options):
        options.setdefault("config_file", self.config)
        options.setdefault("compartment", COMPARTMENT)
        options.setdefault("which", lambda name: f"/tools/{name}")
        return doctor.diagnose(**options)

    @staticmethod
    def successful_runner(argv, **kwargs):
        if "region-subscription" in argv:
            data = [{"region-name": REGION, "status": "READY"}]
        else:
            data = {"id": COMPARTMENT, "lifecycle-state": "ACTIVE"}
        return SimpleNamespace(returncode=0, stdout=json.dumps({"data": data}), stderr="")

    def test_offline_never_calls_cli(self):
        def forbidden(*args, **kwargs):
            self.fail("offline mode must not execute the CLI")
        result = self.diagnose(runner=forbidden)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["mode"], "offline")

    def test_live_checks_only_read_commands_with_timeout_and_no_shell(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            self.assertEqual(kwargs["timeout"], 30)
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            return self.successful_runner(argv, **kwargs)
        result = self.diagnose(live=True, runner=runner)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(calls), 2)
        self.assertIn("region-subscription", calls[0])
        self.assertIn("get", calls[1])
        self.assertNotIn(TENANCY, json.dumps(result))
        self.assertNotIn(COMPARTMENT, json.dumps(result))

    def test_nonzero_cli_result_blocks_without_leaking_stderr(self):
        raw = "DO_NOT_DISCLOSE_CREDENTIAL_MATERIAL"
        result = self.diagnose(live=True, runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout=raw, stderr=raw))
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn(raw, json.dumps(result))

    def test_malformed_cli_output_is_unknown_not_success(self):
        result = self.diagnose(live=True, runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="not json", stderr=""))
        self.assertEqual(result["status"], "incomplete")

    def test_timeout_is_unknown_without_leaking_command(self):
        def runner(*args, **kwargs):
            raise subprocess.TimeoutExpired("sensitive command", 30)
        result = self.diagnose(live=True, runner=runner)
        self.assertEqual(result["status"], "incomplete")
        self.assertNotIn("sensitive command", json.dumps(result))

    def test_pending_region_is_blocked(self):
        def runner(argv, **kwargs):
            if "region-subscription" in argv:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"data": [{"region-name": REGION, "status": "IN_PROGRESS"}]}))
            return self.successful_runner(argv)
        self.assertEqual(self.diagnose(live=True, runner=runner)["status"], "blocked")

    def test_wrong_compartment_response_is_unknown(self):
        def runner(argv, **kwargs):
            if "compartment" in argv:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"data": {"id": "other", "lifecycle-state": "ACTIVE"}}))
            return self.successful_runner(argv)
        self.assertEqual(self.diagnose(live=True, runner=runner)["status"], "incomplete")

    def test_root_compartment_is_rejected(self):
        with self.assertRaises(ValueError):
            self.diagnose(compartment=TENANCY)

    def test_injection_profile_is_rejected_before_cli(self):
        for value in ("DEFAULT; touch /tmp/should-not-exist", "--debug", "a\nvalue"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.diagnose(profile=value)

    def test_injection_region_is_rejected(self):
        with self.assertRaises(ValueError):
            self.diagnose(region="x; echo private")

    def test_missing_tools_block_but_do_not_hide_auth_diagnosis(self):
        result = self.diagnose(which=lambda name: None)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(c["check"] == "credentials" for c in result["checks"]))

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_broad_config_permissions_block_without_live_call(self):
        self.config.chmod(0o644)
        result = self.diagnose(live=True, runner=lambda *a, **k: self.fail("unsafe credentials must prevent live requests"))
        self.assertEqual(result["status"], "blocked")

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_broad_key_permissions_are_rejected(self):
        self.key.chmod(0o644)
        self.assertEqual(self.diagnose()["status"], "blocked")

    def test_key_and_config_symlinks_are_rejected(self):
        link = self.root / "key-link.pem"
        link.symlink_to(self.key)
        self.config.write_text(self.config.read_text().replace(str(self.key), str(link)))
        self.assertEqual(self.diagnose()["status"], "blocked")
        config_link = self.root / "config-link"
        config_link.symlink_to(self.config)
        self.assertEqual(self.diagnose(config_file=config_link)["status"], "blocked")

    def test_key_contents_never_opened(self):
        from unittest.mock import patch
        real_open = os.open
        def guarded_open(path, *args, **kwargs):
            if Path(path) == self.key:
                self.fail("doctor must never open a private key")
            return real_open(path, *args, **kwargs)
        with patch.object(doctor.os, "open", side_effect=guarded_open):
            result = self.diagnose()
        self.assertNotIn("key content", json.dumps(result))

    def test_session_token_checks_metadata_without_reading_token(self):
        token = self.root / "token"
        token.write_text("TOKEN_MUST_NOT_BE_REPORTED")
        token.chmod(0o600)
        self.config.write_text(f"[DEFAULT]\ntenancy={TENANCY}\nkey_file={self.key}\nsecurity_token_file={token}\nregion={REGION}\n")
        result = self.diagnose(auth="security_token", live=True, runner=self.successful_runner)
        self.assertEqual(result["status"], "passed")
        self.assertNotIn("TOKEN_MUST_NOT_BE_REPORTED", json.dumps(result))

    def test_principal_auth_needs_no_config_and_passes_explicit_auth(self):
        for auth in ("instance_principal", "resource_principal"):
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                return self.successful_runner(argv)
            result = self.diagnose(config_file=self.root / "missing", auth=auth, tenancy=TENANCY,
                                   region=REGION, live=True, runner=runner)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(calls[0][calls[0].index("--auth") + 1], auth)
            self.assertNotIn("--config-file", calls[0])


if __name__ == "__main__":
    unittest.main()
