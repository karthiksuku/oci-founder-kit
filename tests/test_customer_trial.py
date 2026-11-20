"""A customer trial is private evidence about a single named rehearsal."""
import json
import time
from unittest import mock

from test_foundation_packaging import Fixture, load, p

trial = load("customer_trial")


class CustomerTrial(Fixture):
    def setUp(self):
        super().setUp()
        self.now = int(time.time())
        config = self.selected()
        config["target"]["origin"] = "https://pilot.example.invalid"
        p.helper("environments").configure(self.app, name="rehearsal", target=config["target"])
        self.binding = {"environment": "rehearsal", "receipt_sha256": "1" * 64,
                        "image_digest": "sha256:" + "a" * 64}
        self.review = {"candidate_sha256": p.digest(p.canonical(self.binding)), "task": "Find a synthetic task",
                       "observed_at": self.now, "expires_at": self.now + 3600,
                       "checks": dict.fromkeys(trial.PREPARE_CHECKS, True)}

    def run_action(self, action, data=None, trial_id=None, environment="rehearsal"):
        path = self.private_json("input.json", data) if data is not None else None
        return trial.request(self.app, p=p, action=action, environment=environment,
                             trial_id=trial_id, input_file=path)

    def test_missing_deployment_and_wrong_environment_cannot_generate_invitation(self):
        self.assertEqual(self.run_action("inspect")["status"], "incomplete")
        self.assertEqual(self.run_action("prepare", self.review)["status"], "incomplete")
        p.helper("environments").create(self.app, name="prod", role="production", infrastructure="deploy/prod", target={})
        with self.assertRaises(ValueError):
            self.run_action("prepare", self.review, environment="prod")
        self.assertFalse(list(self.private.glob("trial-*.json")))

    def test_requires_recent_checks_and_current_receipt_and_enforced_expiry(self):
        with mock.patch.object(trial, "candidate", return_value=self.binding):
            for changed in ({"expires_at": self.now}, {"expires_at": self.now + 8*86400},
                            {"observed_at": self.now-90000}, {"candidate_sha256": "f"*64},
                            {"checks": {**self.review["checks"], "uninvited_account_denied": False}}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    self.run_action("prepare", {**self.review, **changed})
        self.assertFalse(list(self.private.glob("trial-*.json")))

    def test_feedback_retries_privacy_and_revocation(self):
        with mock.patch.object(trial, "candidate", return_value=self.binding):
            prepared = self.run_action("prepare", self.review)
            identifier = prepared["trial_id"]
            self.assertEqual(self.run_action("prepare", self.review), prepared)
            receipt = self.app / prepared["private_brief"]
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("pilot.example.invalid", json.dumps(prepared))
            feedback = {"trial_id": identifier, "outcome": "blocked", "observed": "private-marker",
                        "expected": "Task survives reload", "observed_at": self.now}
            with mock.patch.object(trial, "candidate", return_value={**self.binding, "receipt_sha256": "2"*64}):
                recorded = self.run_action("feedback", feedback, identifier)
            self.assertEqual(recorded["readback_at_recording"], "current-target-changed")
            self.assertEqual(recorded["image_during_tester_action"], "unverified")
            self.assertEqual(self.run_action("feedback", feedback, identifier), recorded)
            self.assertNotIn("private-marker", json.dumps(recorded))
            self.assertEqual(json.loads((self.app / recorded["private_regression"]).read_bytes())["test_status"], "not-run")
            with self.assertRaises(ValueError):
                self.run_action("feedback", {**feedback, "observed_at": self.now+4000}, identifier)
            close = {"checks": dict.fromkeys(trial.CLOSE_CHECKS, True), "observed_at": self.now,
                     "trial_id": identifier}
            with self.assertRaises(ValueError):
                self.run_action("close", {**close, "checks": {}}, identifier)
            self.assertEqual(self.run_action("close", close, identifier)["status"], "closed")
            self.assertEqual(self.run_action("prepare", self.review)["status"], "closed")
            with self.assertRaises(ValueError):
                self.run_action("feedback", {**feedback, "trial_id": "f"*64}, identifier)

    def test_cli_binds_real_receipt_and_observation_parser_through_trial_closure(self):
        # Only the OCI metadata transport is replaced. Exercise the real receipt parser,
        # observation writer, evidence selectors, CLI entry point and private records.
        import subprocess
        import sys
        from test_operations import BoundObservation, ROOT, ops

        fixture = BoundObservation()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.target["origin"] = "https://pilot.example.invalid"
        fixture.env.configure(fixture.app, name="rehearsal", target=fixture.target)
        with p.Store(fixture.app, environment="rehearsal") as store:
            backend = dict(store.environment_config["backend"], config_file_profile="DEFAULT", auth="APIKey")
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py")
        fixture.receipt["project_environment"] = gate.select(fixture.stack, project=fixture.app,
                                                              environment="rehearsal", backend=backend)
        fixture.write(fixture.path, fixture.receipt)

        def cli(action, data=None, trial_id=None, expected=0):
            command = [sys.executable, str(ROOT / "scripts/kit.py"), "trial", action,
                       "--project", str(fixture.app), "--environment", "rehearsal", "--json", "--non-interactive"]
            if data is not None:
                command.extend(["--input", str(self.private_json("trial-cli-input.json", data))])
            if trial_id is not None:
                command.extend(["--trial-id", trial_id])
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
            return json.loads(proc.stdout)

        injected = fixture.observe()
        self.assertEqual(cli("inspect", expected=3)["status"], "incomplete")
        # Simulate a later instant without sleeping or relabeling test-client evidence.
        record = json.loads((fixture.app / injected["evidence"]).read_bytes())
        record["observed_at"] -= 30
        fixture.write(fixture.app / injected["evidence"], record)
        with mock.patch.object(ops.Client, "__init__", return_value=None), \
                mock.patch.object(ops.Client, "__call__", side_effect=fixture.fixture.client), \
                mock.patch.object(ops.Client, "check", return_value=None):
            observation = ops.request(fixture.app, environment="rehearsal", live=True)
        self.assertTrue(observation["image_identity_verified"])
        first = cli("inspect")
        self.assertEqual(first["status"], "needs-access-review")
        review = dict(self.review, candidate_sha256=first["candidate_sha256"])
        prepared = cli("prepare", review)
        identifier = prepared["trial_id"]
        brief = json.loads((fixture.app / prepared["private_brief"]).read_bytes())
        self.assertEqual(brief["binding"]["receipt_sha256"], observation["receipt_sha256"])
        self.assertEqual(brief["binding"]["image_digest"], fixture.target["image_digest"])
        self.assertEqual(brief["origin"], fixture.target["origin"])
        feedback = {"trial_id": identifier, "outcome": "blocked", "observed_at": self.now,
                    "observed": "Example text was hard to read", "expected": "Readable example text"}
        recorded = cli("feedback", feedback, identifier)
        self.assertEqual(recorded["readback_at_recording"], "current-match")
        closed = cli("close", {"trial_id": identifier, "observed_at": self.now,
                               "checks": dict.fromkeys(trial.CLOSE_CHECKS, True)}, identifier)
        self.assertEqual(closed["revocation_evidence"], "owner-recorded")
        self.assertEqual(cli("prepare", review)["status"], "closed")
        # Superseding the receipt invalidates the old observation and prevents reuse.
        fixture.receipt["plan_sha256"] = "5" * 64
        fixture.write(fixture.path, fixture.receipt)
        self.assertEqual(cli("prepare", review, expected=3)["status"], "incomplete")
