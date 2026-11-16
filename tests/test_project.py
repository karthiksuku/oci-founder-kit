"""The local guide preserves projects and never turns saved progress into cloud authority."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kit_project_test", ROOT / "scripts/project.py")
project = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project)


@unittest.skipUnless(os.name == "posix", "Private state uses POSIX directory handles and locking")
class ProjectJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory()
        cls.installed = Path(cls.template.name) / "installed"
        cls.installed.mkdir()
        project.helper("install").install(cls.installed, "both")

    @classmethod
    def tearDownClass(cls):
        cls.template.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.app = self.base / "app"
        shutil.copytree(self.installed, self.app)
        (self.app / "main.py").write_text("print('application must not execute')\n")

    def start(self, **kwargs):
        return project.start(self.app, **kwargs)

    def evidence(self, name="local.txt", raw=b"Local synthetic test result: passed.\n"):
        path = self.app / ".oci-kit/evidence" / name
        path.write_bytes(raw)
        path.chmod(0o600)
        return path.relative_to(self.app).as_posix()

    def record(self, step="local-workflow", outcome="passed", raw=b"Synthetic local test result.\n"):
        return project.record(self.app, step, self.evidence(step + ".txt", raw), outcome)

    def state(self):
        return self.app / ".oci-kit/state.json"

    def gate(self, *, status="applied", kind="apply"):
        directory = self.app / "terraform/.gate/receipts"
        directory.mkdir(parents=True, exist_ok=True)
        receipt = {"schema": "oci-deploy-receipt/2", "kind": kind, "status": status,
                   "started_at": "2026-01-01T12:00:00+00:00", "plan_sha256": "a" * 64,
                   "target": {"compartment_ocid": "PRIVATE_TARGET_SENTINEL"}}
        path = directory / "receipt.json"
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)
        return path

    def test_existing_start_preserves_app_and_instructions_and_runs_no_subprocess(self):
        (self.app / "AGENTS.md").write_text("Keep these app instructions.\n")
        before = {name: (self.app / name).read_bytes() for name in ("main.py", "AGENTS.md")}
        with mock.patch("subprocess.run", side_effect=AssertionError("Must not execute commands")):
            result = self.start(task="build", stack="fastapi")
            resumed = project.resume(self.app, refresh=True)
        self.assertEqual(result["next_action"]["id"], "local-workflow")
        self.assertEqual(resumed["stack"], "fastapi")
        self.assertEqual(before, {name: (self.app / name).read_bytes() for name in before})
        self.assertEqual(len([key for key in result if key == "next_action"]), 1)
        self.assertNotIn(str(self.app), json.dumps(result))

    def test_generic_new_project_does_not_substitute_taskboard_or_run_tools(self):
        target = self.base / "new-app"
        with mock.patch("subprocess.run", side_effect=AssertionError("Must not execute commands")):
            result = project.start(target, mode="new", task="build", stack="nextjs")
        self.assertIsNone(result["blueprint"])
        self.assertTrue((target / ".agents/skills/oci-kit/SKILL.md").is_file())
        self.assertFalse((target / "app").exists())
        self.assertFalse((target / "local_preview.py").exists())
        self.assertEqual(result["next_action"]["id"], "local-workflow")

    def test_taskboard_is_explicit_and_uses_existing_creator(self):
        target = self.base / "taskboard"
        result = project.start(target, mode="new", blueprint="fullstack-container")
        self.assertTrue((target / "app/src/server.js").is_file())
        self.assertEqual(result["next_action"]["command"], ["python3", "local_preview.py", "start"])
        self.assertFalse((target / ".local-preview").exists())

    def test_new_refuses_occupied_directory_and_conflicting_blueprint_selection(self):
        with self.assertRaises(ValueError):
            self.start(mode="new")
        with self.assertRaises(ValueError):
            project.start(self.base / "bad", mode="new", blueprint="fullstack-container", stack="nextjs")
        self.assertFalse((self.base / "bad").exists())

    def test_start_retry_and_continue_preserve_saved_choices_and_records(self):
        first = self.start(task="migrate", stack="nextjs", agent="codex")
        self.record("migration-assessment")
        resumed = project.start(self.app, mode="continue")
        retry = self.start(task="migrate", stack="nextjs", agent="codex")
        self.assertEqual(first["task"], resumed["task"])
        self.assertEqual(resumed["next_action"]["id"], "local-workflow")
        self.assertEqual(retry["steps"], resumed["steps"])
        with self.assertRaises(ValueError):
            self.start(task="setup")

    def test_legacy_install_can_start_existing_but_continue_needs_state(self):
        with self.assertRaises(FileNotFoundError):
            project.start(self.app, mode="continue")
        before = (self.app / ".oci-founder-kit/installation.json").read_bytes()
        self.start()
        self.assertEqual(before, (self.app / ".oci-founder-kit/installation.json").read_bytes())

    def test_setup_starts_at_access_and_migration_starts_at_assessment(self):
        result = self.start(task="setup")
        self.assertEqual(result["next_action"]["id"], "access")
        self.assertNotIn("local-workflow", {step["id"] for step in result["steps"]})
        with self.assertRaises(ValueError):
            self.record("local-workflow")

    def test_private_state_and_read_only_status_do_not_modify_any_file(self):
        self.start()
        for name, expected in ((".oci-kit", 0o700), (".oci-kit/evidence", 0o700),
                               (".oci-kit/state.json", 0o600), (".oci-kit/.gitignore", 0o600)):
            self.assertEqual(stat.S_IMODE((self.app / name).stat().st_mode), expected)
        self.assertEqual((self.app / ".oci-kit/.gitignore").read_bytes(), b"*\n")
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.app / ".oci-kit").rglob("*") if p.is_file()}
        project.resume(self.app)
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
        self.assertEqual(before, after)

    def test_evidence_advances_guidance_as_owner_recorded_not_verified(self):
        self.start()
        result = self.record()
        self.assertEqual(result["steps"][0]["status"], "owner-recorded")
        self.assertEqual(result["next_action"]["id"], "access")
        self.assertIn("never authorize", result["scope"])
        self.assertNotIn("Synthetic local test result", self.state().read_text())

    def test_changed_source_invalidates_evidence_even_after_repeated_resume(self):
        self.start()
        self.record()
        (self.app / "main.py").write_text("print('user edit preserved')\n")
        first = project.resume(self.app, refresh=True)
        second = project.resume(self.app, refresh=True)
        for result in (first, second):
            self.assertEqual(result["steps"][0]["status"], "stale")
            self.assertEqual(result["next_action"]["id"], "local-workflow")
        self.assertTrue(first["inputs_changed"])
        self.assertEqual((self.app / "main.py").read_text(), "print('user edit preserved')\n")

    def test_evidence_change_or_removal_does_not_retain_pass(self):
        self.start()
        self.record()
        path = self.app / ".oci-kit/evidence/local-workflow.txt"
        path.write_text("Changed result")
        self.assertEqual(project.resume(self.app)["steps"][0]["status"], "stale")
        path.unlink()
        self.assertEqual(project.resume(self.app)["steps"][0]["status"], "stale")

    def test_changed_kit_helper_invalidates_owner_evidence(self):
        self.start()
        self.record()
        with mock.patch.object(project, "kit_fingerprint", return_value="f" * 64):
            result = project.resume(self.app)
        self.assertEqual(result["steps"][0]["status"], "stale")

    def test_blocked_record_keeps_same_next_action(self):
        self.start()
        result = self.record(outcome="blocked")
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual(result["next_action"]["id"], "local-workflow")

    def test_offline_readiness_is_not_live_access(self):
        self.start(task="setup")
        for mode, status in (("offline", "passed"), ("live-read-only", "incomplete"), ("offline", "blocked")):
            with self.subTest(mode=mode, status=status), self.assertRaises(ValueError):
                self.record("access", raw=json.dumps({"schema": "oci-readiness/1", "mode": mode, "status": status}).encode())
        report = {"schema": "oci-readiness/1", "mode": "live-read-only", "status": "passed"}
        result = self.record("access", raw=json.dumps(report).encode())
        self.assertEqual(result["next_action"]["id"], "design-cost")
        self.assertEqual(result["steps"][0]["status"], "owner-recorded")

    def test_attempt_receipt_blocks_before_other_steps_and_never_retries(self):
        self.start()
        self.gate(status="failed")
        with mock.patch("subprocess.run", side_effect=AssertionError("No cloud commands")):
            for _ in range(3):
                result = project.resume(self.app, refresh=True)
                self.assertEqual(result["next_action"]["id"], "review-deployment")
                self.assertNotIn("PRIVATE_TARGET_SENTINEL", json.dumps(result))
        self.assertNotIn("PRIVATE_TARGET_SENTINEL", self.state().read_text())

    def test_apply_receipt_never_claims_runtime_or_production_acceptance(self):
        self.start()
        self.gate()
        result = project.resume(self.app)
        steps = {step["id"]: step["status"] for step in result["steps"]}
        self.assertEqual(steps["deployment"], "apply-receipt-observed")
        self.assertEqual(steps["runtime"], "not-recorded")
        self.assertEqual(steps["acceptance"], "not-recorded")
        self.assertEqual(result["next_action"]["id"], "local-workflow")

    def test_receipts_use_utc_time_and_surface_failed_ties_or_invalid_dates(self):
        self.start()
        path = self.gate()
        old = json.loads(path.read_text())
        old["started_at"] = "2026-01-01T12:00:00Z"
        path.write_text(json.dumps(old))
        newer = dict(old, status="failed", started_at="2026-01-01T12:00:00.100+00:00")
        second = path.with_name("newer.json")
        second.write_text(json.dumps(newer))
        second.chmod(0o600)
        for timestamp in ("2026-01-01T12:00:00.100+00:00", "2026-01-01T12:00:00+00:00",
                          "2026-02-30T12:00:00Z"):
            newer["started_at"] = timestamp
            second.write_text(json.dumps(newer))
            result = project.resume(self.app)
            self.assertEqual(result["next_action"]["id"], "review-deployment")

    def test_expired_changed_and_pending_plans_are_not_approval(self):
        self.start(task="setup")
        directory = self.app / "terraform/.gate"
        directory.mkdir(parents=True)
        raw = b"synthetic saved plan"
        (directory / "tfplan").write_bytes(raw)
        (directory / "tfplan").chmod(0o600)
        for expected, expires, plan_hash in (("expired", time.time() - 1, project.digest(raw)),
                                            ("changed", time.time() + 60, "f" * 64),
                                            ("pending-review", time.time() + 60, project.digest(raw))):
            plan = {"kind": "apply", "plan_sha256": plan_hash, "created_at_epoch": time.time() - 120,
                    "expires_at_epoch": expires, "target": "PRIVATE_TARGET_SENTINEL"}
            path = directory / "plan-summary.json"
            path.write_text(json.dumps(plan))
            path.chmod(0o600)
            result = project.resume(self.app)
            self.assertEqual(next(step for step in result["steps"] if step["id"] == "cloud-plan")["status"], expected)
            self.assertNotIn("PRIVATE_TARGET_SENTINEL", json.dumps(result))
            if expected != "pending-review":
                self.assertEqual(result["next_action"]["id"], "review-plan")

    def test_malformed_unknown_and_duplicate_state_refused_without_echo(self):
        self.start()
        for raw in (b'{"schema":"oci-kit-project/99"}', b'{"secret":"DO_NOT_ECHO"}',
                    b'{"schema":"one","schema":"two"}', b"[1,2]", b"not JSON"):
            self.state().write_bytes(raw)
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                self.assertEqual(project.main(["status", "--project", str(self.app)]), 2)
            self.assertNotIn("DO_NOT_ECHO", output.getvalue())

    def test_symlink_or_hardlink_state_and_evidence_are_refused(self):
        self.start()
        original = self.state().read_bytes()
        outside = self.base / "outside.json"
        outside.write_bytes(original)
        outside.chmod(0o600)
        for kind in ("symlink", "hardlink"):
            self.state().unlink()
            if kind == "symlink":
                self.state().symlink_to(outside)
            else:
                os.link(outside, self.state())
            with self.assertRaises((ValueError, OSError)):
                project.resume(self.app, refresh=True)
            self.assertEqual(outside.read_bytes(), original)
        self.state().unlink()
        self.state().write_bytes(original)
        self.state().chmod(0o600)
        evidence = self.app / ".oci-kit/evidence/linked.txt"
        evidence.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)):
            project.record(self.app, "local-workflow", ".oci-kit/evidence/linked.txt", "passed")

    def test_state_directory_or_project_ancestor_symlink_refused(self):
        other = self.base / "private"
        other.mkdir(mode=0o700)
        (self.app / ".oci-kit").symlink_to(other, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self.start()
        self.assertEqual(list(other.iterdir()), [])
        (self.app / ".oci-kit").unlink()
        alias = self.base / "alias"
        alias.symlink_to(self.app, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            project.start(alias)

    def test_permissions_limits_and_unsafe_evidence_paths_are_refused(self):
        self.start()
        for evidence in ("../outside", "/tmp/outside", ".oci-kit/evidence/../state.json", ".oci-kit/evidence/sub/result"):
            with self.assertRaises(ValueError):
                project.record(self.app, "local-workflow", evidence, "passed")
        self.evidence("large.txt", b"x" * (project.LIMIT + 1))
        with self.assertRaises(ValueError):
            project.record(self.app, "local-workflow", ".oci-kit/evidence/large.txt", "passed")
        self.state().chmod(0o644)
        with self.assertRaises(ValueError):
            project.resume(self.app)

    def test_atomic_write_interruption_keeps_previous_progress(self):
        self.start()
        before = self.state().read_bytes()
        evidence = self.evidence()
        with mock.patch.object(os, "replace", side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError):
                project.record(self.app, "local-workflow", evidence, "passed")
        self.assertEqual(self.state().read_bytes(), before)
        self.assertEqual(list((self.app / ".oci-kit").glob(".pending-*")), [])
        self.assertEqual(project.resume(self.app)["next_action"]["id"], "local-workflow")

    def test_copied_state_cannot_claim_other_project_progress(self):
        self.start()
        other = self.base / "copy"
        shutil.copytree(self.app, other)
        with self.assertRaises(ValueError):
            project.resume(other)

    def test_private_credentials_and_caches_do_not_enter_source_fingerprint(self):
        self.start()
        before = json.loads(self.state().read_text())["source_sha256"]
        (self.app / "node_modules").mkdir()
        (self.app / "node_modules/unsafe.py").symlink_to(self.base / "missing")
        (self.app / ".oci").mkdir()
        (self.app / ".oci/config").write_text("PRIVATE_ACCOUNT_SENTINEL")
        result = project.resume(self.app, refresh=True)
        self.assertEqual(before, json.loads(self.state().read_text())["source_sha256"])
        self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_private_runtime_and_target_input_changes_invalidate_without_reading_values(self):
        self.start()
        self.record()
        for name in (".env", "terraform.tfvars", "backend.tfbackend", "tokens.json", "TOKENS.JSON",
                     "file.tfstate.json", "deployment.tfplan.json", ".npmrc.backup.json",
                     ".NeTrC.BaCkUp.JsOn", "crash.log.json", "private-receipts/report.json"):
            with self.subTest(name=name):
                path = self.app / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("PRIVATE_INPUT_SENTINEL")
                original = project.read_at

                def guarded(directory, filename, **kwargs):
                    if filename == path.name:
                        self.fail("Private runtime input contents must not be opened")
                    return original(directory, filename, **kwargs)

                with mock.patch.object(project, "read_at", side_effect=guarded):
                    result = project.resume(self.app)
                self.assertEqual(result["steps"][0]["status"], "stale")
                self.assertNotIn("PRIVATE_INPUT_SENTINEL", json.dumps(result))
                path.unlink()

    def test_installed_cli_status_and_resume_work_in_fresh_process(self):
        self.start()
        cli = self.app / ".oci-founder-kit/scripts/project.py"
        for command in ("status", "resume"):
            result = subprocess.run([sys.executable, str(cli), command, "--project", str(self.app)],
                                    capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["schema"], "oci-kit-project/1")
            self.assertEqual(data["next_action"]["id"], "local-workflow")


if __name__ == "__main__":
    unittest.main()
