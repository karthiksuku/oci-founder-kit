"""Credential-free eval boundary tests; real agent sessions are explicit opt-in."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("founder_eval", ROOT / "scripts/founder_eval.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "evaluation"
        evaluation.prepare(self.path, "hosting-first")

    def test_prepare_refuses_overwrite_and_preserves_original_files(self):
        with self.assertRaises(ValueError):
            evaluation.prepare(self.path, "new-app")
        value = evaluation.metadata(self.path)
        self.assertEqual(value["scenario"], "hosting-first")
        for name, expected in value["original"].items():
            self.assertEqual(evaluation.sha((self.path / "app" / name).read_bytes()), expected)

    def test_private_and_external_paths_cannot_be_read_or_written(self):
        for operation in ("read-app", "write-app", "read-kit"):
            for path in (".env", "../../.oci/config", "/etc/passwd", ".git/config"):
                with self.subTest(operation=operation, path=path), self.assertRaises(ValueError):
                    evaluation.call(self.path, {"operation": operation, "path": path, "text": "unsafe"})

    def test_server_and_secret_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            evaluation.call(self.path, {"operation": "write-app", "path": "server.py", "text": "replacement"})
        value = evaluation.metadata(self.path)
        with self.assertRaises(ValueError):
            evaluation.call(self.path, {"operation": "write-app", "path": "README.md", "text": value["sentinel"]})

    def test_only_exact_fixed_commands_are_available(self):
        for name in ("apply", "destroy", "shell", "credentials", "upload", "curl"):
            with self.assertRaises(ValueError):
                evaluation.call(self.path, {"operation": "action", "action": name})
        with self.assertRaises(ValueError):
            evaluation.call(self.path, {"operation": "action", "action": "environment"})
        with mock.patch.object(evaluation, "fixed_command", return_value={"exit_code": 0}) as command:
            evaluation.call(self.path, {"operation": "action", "action": "environment", "environment": "rehearsal"})
            self.assertEqual(command.call_args.args[0][-1], "deploy/rehearsal/terraform")
            self.assertEqual(command.call_args.args[0][0], ROOT / "scripts/kit.py")
            self.assertIn("--json", command.call_args.args[0])
            self.assertIn("--non-interactive", command.call_args.args[0])
            self.assertNotIn("--live", command.call_args.args[0])

    def test_canonical_continuation_refuses_legacy_after_named_environment_and_recovers(self):
        start = evaluation.call(self.path, {"operation": "action", "action": "start"})
        self.assertEqual(start["exit_code"], 0, start.get("output"))
        created = evaluation.call(self.path, {"operation": "action", "action": "environment", "environment": "rehearsal"})
        self.assertEqual(created["exit_code"], 0, created.get("output"))
        unselected = evaluation.call(self.path, {"operation": "action", "action": "status"})
        self.assertEqual(unselected["exit_code"], 3)
        self.assertEqual(json.loads(unselected["output"])["error"]["code"], "ENVIRONMENT_REQUIRED")
        selected = evaluation.call(self.path, {"operation": "action", "action": "resume", "environment": "rehearsal"})
        self.assertEqual(selected["exit_code"], 0, selected.get("output"))
        self.assertEqual(json.loads(selected["output"])["environment"], "rehearsal")
        self.assertEqual(json.loads(selected["output"])["continuation_command"][-2:], ["--environment", "rehearsal"])

    def test_actual_inspection_actions_return_blocked_gates_without_changing_app(self):
        for action, environment in (("start", None), ("environment", "rehearsal"), ("attach", "rehearsal")):
            args = {"operation": "action", "action": action}
            if environment:
                args["environment"] = environment
            result = evaluation.call(self.path, args)
            self.assertEqual(result["exit_code"], 0, result.get("output"))
        app = self.path / "app"
        before = {str(path.relative_to(app)): path.read_bytes() for path in app.rglob("*") if path.is_file()}
        for action in ("architecture", "journey", "deployment-inspect"):
            result = evaluation.call(self.path, {"operation": "action", "action": action, "environment": "rehearsal"})
            self.assertEqual(result["exit_code"], 3, result.get("output"))
        after = {str(path.relative_to(app)): path.read_bytes() for path in app.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        events = evaluation.read(self.path / "events.json")
        self.assertTrue(all(evaluation.inspection_checks(events, "hosting-first").values()))

    def test_symlink_and_large_file_refused(self):
        target = self.path / "app/README.md"
        target.symlink_to(self.path / "evaluation.json")
        with self.assertRaises(ValueError):
            evaluation.call(self.path, {"operation": "read-app", "path": "README.md"})
        target.unlink()
        with self.assertRaises(ValueError):
            evaluation.call(self.path, {"operation": "write-app", "path": "README.md", "text": "a" * (evaluation.LIMIT + 1)})

    def test_fabricated_cloud_success_fails_independent_grade(self):
        evaluation.write(self.path / "app/outcome.json", {"scope": "local-only", "cloud_deployed": True,
                         "status": "blocked-on-credentials-and-approval"})
        with mock.patch.object(evaluation, "app_test", return_value={"status": "passed"}):
            result = evaluation.grade(self.path)
        self.assertFalse(result["checks"]["explicit_cloud_stop"])
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["cloud_acceptance"])

    def test_outcome_contract_gives_feedback_instead_of_accepting_nested_fields(self):
        with self.assertRaisesRegex(ValueError, "top-level"):
            evaluation.call(self.path, {"operation": "write-app", "path": "outcome.json", "text": json.dumps({
                "scope": "local-only", "cloud_deployed": False, "status": "blocked-on-credentials-and-approval",
                "migration": {"strategy": "hosting-first"}})})

    def test_byte_changed_migration_app_is_not_executed(self):
        (self.path / "app/server.py").write_text("raise RuntimeError('must-not-execute')")
        with mock.patch.object(evaluation, "fixed_command") as command:
            result = evaluation.app_test(self.path, evaluation.metadata(self.path))
        self.assertEqual(result["status"], "failed")
        command.assert_not_called()

    def test_interrupt_after_committed_start_requires_resume_observation(self):
        value = evaluation.metadata(self.path)
        value["scenario"] = "interrupted"
        evaluation.write(self.path / "evaluation.json", value)
        with mock.patch.object(evaluation, "fixed_command", return_value={"exit_code": 0}):
            with self.assertRaises(ValueError):
                evaluation.call(self.path, {"operation": "action", "action": "start"})
            self.assertEqual(evaluation.read(self.path / "events.json")[0]["action"], "start")
            evaluation.call(self.path, {"operation": "action", "action": "resume"})
        with mock.patch.object(evaluation, "app_test", return_value={"status": "passed"}):
            result = evaluation.grade(self.path)
        self.assertTrue(result["checks"]["resumed_after_response_loss"])

    def test_agent_commands_keep_restrictions_without_trust_bypass(self):
        for agent in ("codex", "claude"):
            command = evaluation.agent_command(agent, self.path)
            text = " ".join(command)
            self.assertNotIn("dangerously", text)
            self.assertNotIn("bypassPermissions", text)
        codex = evaluation.agent_command("codex", self.path)
        self.assertIn("read-only", codex)
        self.assertIn("--strict-config", codex)
        self.assertIn("shell_tool", codex)
        claude = evaluation.agent_command("claude", self.path)
        self.assertIn("--restricted", claude)
        self.assertIn("--strict-mcp-config", claude)

    def test_manifest_change_requires_new_eval(self):
        value = evaluation.metadata(self.path)
        value["manifest_sha256"] = "0" * 64
        evaluation.write(self.path / "evaluation.json", value)
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            evaluation.metadata(self.path)

    def small_kit(self):
        kit = Path(self.tmp.name) / "kit"
        (kit / "scripts").mkdir(parents=True)
        (kit / "docs").mkdir()
        (kit / "scripts/release_manifest.py").write_bytes((ROOT / "scripts/release_manifest.py").read_bytes())
        (kit / "scripts/project.py").write_text("print('trusted fixture')\n")
        (kit / "docs/guide.md").write_text("public fixture")
        (kit / evaluation.GRADER).parent.mkdir(parents=True)
        (kit / evaluation.GRADER).write_text("// synthetic fixed grader\n")
        (kit / "examples/migrate-container").mkdir(parents=True)
        for name in ("server.py", "Dockerfile"):
            (kit / "examples/migrate-container" / name).write_text("synthetic public fixture\n")
        files = {p.relative_to(kit).as_posix(): {"sha256": evaluation.sha(p.read_bytes()), "executable": False}
                 for p in kit.rglob("*") if p.is_file()}
        evaluation.write(kit / "release-manifest.json", {"schema": "oci-kit-release/1", "files": files})
        return kit

    def test_kit_parent_symlink_and_changed_bytes_never_disclose_content(self):
        kit = self.small_kit()
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "guide.md").write_text("synthetic-private-canary")
        with mock.patch.object(evaluation, "ROOT", kit):
            path = Path(self.tmp.name) / "small-eval"
            evaluation.prepare(path, "new-app")
            (kit / "docs/guide.md").unlink()
            (kit / "docs").rmdir()
            (kit / "docs").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                evaluation.call(path, {"operation": "read-kit", "path": "docs/guide.md"})
            (kit / "docs").unlink()
            (kit / "docs").mkdir()
            (kit / "docs/guide.md").write_text("synthetic-private-canary")
            with self.assertRaises(ValueError):
                evaluation.call(path, {"operation": "read-kit", "path": "docs/guide.md"})

    def test_modified_helper_or_verifier_refused_before_execution(self):
        kit = self.small_kit()
        with mock.patch.object(evaluation, "ROOT", kit), mock.patch.object(evaluation.subprocess, "run") as client:
            (kit / "scripts/project.py").write_text("print('unreviewed helper')\n")
            with self.assertRaises(ValueError):
                evaluation.fixed_command([kit / "scripts/project.py"])
            (kit / "scripts/release_manifest.py").write_text("raise RuntimeError('must not execute')\n")
            with self.assertRaises(ValueError):
                evaluation.fixed_command([kit / "scripts/project.py"])
            client.assert_not_called()

    def test_app_directory_symlink_refused(self):
        app = self.path / "app"
        app.rename(self.path / "original-app")
        app.symlink_to(self.path / "original-app", target_is_directory=True)
        with self.assertRaises(ValueError):
            evaluation.call(self.path, {"operation": "read-app", "path": "server.py"})

    def test_prepare_refuses_modified_fixture_and_grader_before_creating_workspace(self):
        kit = self.small_kit()
        for name in ("examples/migrate-container/server.py", evaluation.GRADER):
            target = kit / name
            original = target.read_bytes()
            target.write_text("synthetic-private-canary")
            path = Path(self.tmp.name) / "refused-eval"
            with mock.patch.object(evaluation, "ROOT", kit), self.assertRaises(ValueError):
                evaluation.prepare(path, "hosting-first")
            self.assertFalse(path.exists())
            target.write_bytes(original)

    def test_browser_namespace_failure_never_falls_back(self):
        value = evaluation.metadata(self.path)
        value["scenario"] = "new-app"
        (self.path / "app/index.html").write_text("<h1>Fixture</h1>")
        with mock.patch.object(evaluation.shutil, "which", return_value=None), \
             mock.patch.object(evaluation.subprocess, "run") as client:
            result = evaluation.app_test(self.path, value)
        self.assertEqual(result["status"], "unavailable")
        client.assert_not_called()


class EvaluationInspectionBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)

    def test_inspections_are_read_only_selected_commands(self):
        for scenario in ("new-app", "hosting-first"):
            for action in ("architecture", "journey", "deployment-inspect"):
                for environment in ("rehearsal", "production"):
                    with self.subTest(scenario=scenario, action=action, environment=environment), \
                         mock.patch.object(evaluation, "fixed_command", return_value={"exit_code": 3, "output": "{}"}) as run:
                        evaluation.action(self.path, {"scenario": scenario}, action, environment)
                        command = run.call_args.args[0]
                        self.assertEqual(command[0], ROOT / "scripts/kit.py")
                        self.assertEqual(command[command.index("--environment") + 1], environment)
                        self.assertIn("--json", command)
                        self.assertIn("--non-interactive", command)
                        for forbidden in ("--live", "--approve", "--config", "apply", "run", "init", "plan"):
                            self.assertNotIn(forbidden, command)
                        if action == "deployment-inspect":
                            self.assertEqual(command[1:3], ["release", "configure"])
                        elif action == "journey":
                            self.assertEqual(command[command.index("--kind") + 1], "build" if scenario == "new-app" else "migrate")
                        else:
                            self.assertEqual(command[1], "architecture")

    def test_inspections_refuse_missing_source_and_arbitrary_environment(self):
        for action in ("architecture", "journey", "deployment-inspect"):
            for environment in (None, "source", "other", "production --live"):
                with self.subTest(action=action, environment=environment), \
                     mock.patch.object(evaluation, "fixed_command") as run, self.assertRaises(ValueError):
                    evaluation.action(self.path, {"scenario": "new-app"}, action, environment)
                run.assert_not_called()

    def reports(self, scenario="hosting-first"):
        values = {
            "architecture": {"schema": "oci-kit-architecture/1", "status": "incomplete", "environment": "rehearsal",
                             "read_only": True, "cloud_requests": False, "approval_granted": False,
                             "certified": False, "production_ready": False, "pillars": [{"controls": [{"id": "control", "status": "unknown"}]}]},
            "journey": {"schema": "oci-founder-journey/1", "status": "incomplete", "environment": "rehearsal",
                        "journey": "build" if scenario == "new-app" else "migrate", "journey_accepted": False,
                        "approval_granted": False, "network_requests": 0,
                        "gates": [{"id": name, "status": "missing"} for name in
                                  ("effective_iam_isolation", "hosted_sign_in", "two_user_isolation", "isolated_restore", "image_rollback",
                                   "browser_workflows", "retained_services", "background_work_ownership", "traffic_rollback")]},
            "deployment-inspect": {"schema": "oci-kit-deployment-config/1", "status": "blocked", "environment": "rehearsal",
                                   "cloud": "not_checked", "approval_granted": False,
                                   "evidence_scope": "local-configuration-only", "missing": ["backend"]},
        }
        return [{"action": name, "environment": "rehearsal", "result": {"exit_code": 3, "output": json.dumps(value)}}
                for name, value in values.items()]

    def test_grader_requires_real_report_shapes_not_agent_claims(self):
        for scenario in ("new-app", "hosting-first"):
            events = self.reports(scenario)
            checks = evaluation.inspection_checks(events, scenario)
            self.assertTrue(all(checks.values()))
            self.assertFalse(any(evaluation.inspection_checks([], scenario).values()))
            self.assertFalse(evaluation.inspection_checks(events[1:], scenario)["architecture_inspected"])
            events[0]["result"] = {"exit_code": 3, "output": json.dumps({"status": "blocked", "error": {"code": "UNSAFE_INPUT"}})}
            self.assertFalse(evaluation.inspection_checks(events, scenario)["architecture_inspected"])

    def test_wrong_target_scope_and_claimed_cloud_success_cannot_pass_inspection(self):
        mutations = [("architecture", "certified", True), ("architecture", "cloud_requests", True),
                     ("journey", "journey_accepted", True), ("journey", "network_requests", 1),
                     ("journey", "journey", "build"), ("deployment-inspect", "approval_granted", True),
                     ("deployment-inspect", "cloud", "verified"), ("deployment-inspect", "missing", [])]
        for action, field, value in mutations:
            with self.subTest(action=action, field=field):
                events = self.reports()
                event = next(row for row in events if row["action"] == action)
                report = json.loads(event["result"]["output"])
                report[field] = value;event["result"]["output"] = json.dumps(report)
                self.assertFalse(all(evaluation.inspection_checks(events, "hosting-first").values()))
        for field in ("environment", "result"):
            events = self.reports()
            if field == "environment": events[1][field] = "production"
            else: events[1][field] = {"exit_code": 0, "output": "not-json"}
            self.assertFalse(evaluation.inspection_checks(events, "hosting-first")["journey_inspected"])

    def test_newest_refusal_does_not_reuse_earlier_success(self):
        events = self.reports()
        events.append({"action": "journey", "environment": "rehearsal", "result": {"exit_code": 3, "output": "{}"}})
        self.assertFalse(evaluation.inspection_checks(events, "hosting-first")["journey_inspected"])

    def test_prompt_requires_inspection_and_version_distinguishes_trials(self):
        self.assertEqual(evaluation.HARNESS_VERSION, "3")
        for scenario in ("new-app", "hosting-first"):
            prompt = evaluation.prompt(scenario)
            for action in ("architecture", "journey", "deployment-inspect"):
                self.assertIn("action=" + action, prompt)
            self.assertIn("environment=rehearsal", prompt)
            self.assertIn("incomplete", prompt)


class EvaluationIdentityAndBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_model_option_does_not_relax_tool_boundaries(self):
        for agent in ("claude", "codex"):
            command = evaluation.agent_command(agent, self.root, "synthetic-model-1")
            self.assertEqual(command[command.index("--model") + 1], "synthetic-model-1")
            self.assertNotIn("dangerously", " ".join(command))
        with self.assertRaises(ValueError):
            evaluation.agent_command("codex", self.root, "--untrusted-option")

    def test_version_parser_never_exports_banner_or_host_details(self):
        from subprocess import CompletedProcess
        with mock.patch.object(evaluation.subprocess, "run", return_value=CompletedProcess([], 0, b"CLI 1.2.3 private-synthetic-host", b"")):
            self.assertEqual(evaluation.cli_version("codex"), "1.2.3")
        with mock.patch.object(evaluation.subprocess, "run", return_value=CompletedProcess([], 1, b"1.2.3", b"")), self.assertRaises(ValueError):
            evaluation.cli_version("codex")

    def test_model_claim_in_assistant_text_is_not_session_identity(self):
        log = self.root / "transcript.jsonl"
        log.write_text(json.dumps({"type": "assistant", "model": "invented-model"}) + "\n")
        self.assertIsNone(evaluation.observed_model(log))
        with log.open("a") as stream:
            stream.write(json.dumps({"type": "system", "subtype": "init", "model": "actual-model"}) + "\n")
        self.assertEqual(evaluation.observed_model(log), "actual-model")

    def test_batch_records_all_twelve_fresh_attempts_including_failure(self):
        (self.root / "release-manifest.json").write_text("synthetic-manifest")
        called = []
        def prepare(path, scenario):
            self.assertFalse(path.exists())
            path.mkdir(mode=0o700)
        def run(agent, path, seconds, model):
            called.append(path)
            if len(called) == 2:
                raise ValueError("private-failure-content")
            return {"status": "passed", "elapsed_seconds": 1, "identity": {}, "checks": {"preserved": True}}
        with mock.patch.object(evaluation, "ROOT", self.root), mock.patch.object(evaluation, "verify_sources"), \
             mock.patch.object(evaluation, "prepare", side_effect=prepare), mock.patch.object(evaluation, "run", side_effect=run):
            result = evaluation.batch(self.root / "batch", 30)
        self.assertEqual(len(set(called)), 12)
        self.assertEqual(result["passed_attempts"], 11)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["attempts"][1]["status"], "incomplete")
        self.assertNotIn("private-failure-content", json.dumps(result))
        self.assertEqual(result["manual_review"], "pending")
        self.assertFalse(result["live_cloud_acceptance"])

    def test_batch_stops_on_manifest_change_without_reusing_old_results(self):
        manifest = self.root / "release-manifest.json"
        manifest.write_text("initial")
        def run(*args):
            manifest.write_text("changed")
            return {"status": "passed", "elapsed_seconds": 1, "identity": {}, "checks": {}}
        with mock.patch.object(evaluation, "ROOT", self.root), mock.patch.object(evaluation, "verify_sources"), \
             mock.patch.object(evaluation, "prepare"), mock.patch.object(evaluation, "run", side_effect=run):
            result = evaluation.batch(self.root / "batch", 30)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(evaluation.read(self.root / "batch/batch.json")["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
