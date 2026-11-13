"""Synthetic recipe and approval failure boundaries; no OCI calls."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import test_deploy_gate  # establishes the scripts import path
import backend_rehearsal as recipe


TARGET = {"bucket": "synthetic-bucket", "namespace": "synthetic_namespace", "region": "ap-melbourne-1",
          "bucket_id": "ocid1.bucket.oc1.ap-melbourne-1.synthetic",
          "compartment_id": "ocid1.compartment.oc1..synthetic", "tenancy_id": "ocid1.tenancy.oc1..synthetic"}
IDENTITY = {"home": "/synthetic/home", "profile": "DEFAULT", "identity": {"fingerprint": "synthetic"}}


class Storage:
    def __init__(self):
        self.live, self.history, self.deleted = {}, [], []
        self.counter = 0

    def preflight(self):
        return TARGET

    def add(self, name, raw):
        self.counter += 1
        obj = {"bytes": raw, "version_id": str(self.counter), "etag": recipe.files.sha(raw), "size": len(raw)}
        self.live[name] = obj
        self.history.append({"name": name, "version_id": obj["version_id"], "etag": obj["etag"],
                             "size": len(raw), "is_delete_marker": False, "time_modified": "synthetic", "raw": raw})

    def object(self, name, version_id=None, limit=65536):
        if version_id is None:
            return self.live.get(name)
        for row in self.history:
            if row["name"] == name and row["version_id"] == version_id:
                return {"bytes": row["raw"], "version_id": version_id, "etag": row["etag"], "size": row["size"]}
        return None

    def inventory(self, prefix, names):
        return {"objects": sorted([{"name": n, **{k: v[k] for k in ("version_id", "etag", "size")}}
                                   for n, v in self.live.items()], key=lambda r: r["name"]),
                "versions": sorted([{k: v for k, v in row.items() if k != "raw"} for row in self.history],
                                   key=lambda r: (r["name"], r["version_id"]))}

    def delete_version(self, name, version_id, etag=None):
        self.deleted.append((name, version_id, etag))
        self.history = [r for r in self.history if (r["name"], r["version_id"]) != (name, version_id)]
        if self.live.get(name, {}).get("version_id") == version_id:
            del self.live[name]


class FakeServer:
    active = None
    def __init__(self, raw):
        self.port, self.calls, self.released = 32123, {}, False
        self.holder_seen = SimpleNamespace(wait=lambda _: True)
    def __enter__(self):
        FakeServer.active = self
        return self
    def __exit__(self, *args):
        self.release()
    def release(self):
        self.released = True
    def counts(self):
        return dict(self.calls)


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backend-rehearsal-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "work"
        self.root.mkdir(mode=0o700)
        self.target = self.tmp / "target.json"
        self.target.write_text(json.dumps(TARGET)); self.target.chmod(0o600)
        self.bucket = self.tmp / "bucket.json"
        self.bucket.write_text(json.dumps({"schema": "oci-deploy-receipt/2", "kind": "apply", "status": "applied",
            "target": {"region": TARGET["region"], "tenancy_ocid": TARGET["tenancy_id"],
                       "compartment_ocid": TARGET["compartment_id"], "profile": "DEFAULT", "auth": "APIKey"},
            "resources": [{"type": "oci_objectstorage_bucket", "id": TARGET["bucket_id"],
                           "name": TARGET["bucket"], "compartment_id": TARGET["compartment_id"]}]}))
        self.bucket.chmod(0o600)
        self.args = SimpleNamespace(command="backend-rehearsal-plan", dir=self.root, target=self.target,
                                    bucket_receipt=self.bucket, profile="DEFAULT", max_age_minutes=120)
        patch = mock.patch.object(recipe, "auth", return_value=({"tenancy": TARGET["tenancy_id"]}, IDENTITY))
        patch.start(); self.addCleanup(patch.stop)
        patch = mock.patch.object(recipe.files, "fingerprint", return_value={"path": "/synthetic/terraform", "sha256": "a" * 64})
        patch.start(); self.addCleanup(patch.stop)

    def invoke(self, args=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return recipe.dispatch(args or self.args)

    def prepared(self):
        self.assertEqual(self.invoke(), 0)
        return json.loads((self.root / ".gate" / recipe.PLAN).read_text())

    def execution(self, envelope):
        return SimpleNamespace(command="backend-rehearsal-run", dir=self.root, approve=envelope["sha256"])

    def receipt(self, envelope):
        return self.root / ".gate/rehearsal-receipts" / (envelope["sha256"] + ".json")

    def test_offline_preparation_has_fixed_scope(self):
        with mock.patch.object(recipe.inspect, "Inspector") as client:
            env = self.prepared()
        client.assert_not_called()
        self.assertEqual(len(env["payload"]["names"]), 4)
        self.assertEqual(env["payload"]["target"], TARGET)
        self.assertEqual(set(p.name for p in self.root.iterdir()), {".gate"})

    def test_wrong_approval_identity_source_and_expiry_never_start_client(self):
        for change in ("hash", "identity", "source", "expiry", "extra", "directory"):
            with self.subTest(change=change):
                env = self.prepared()
                args = self.execution(env)
                patches = contextlib.ExitStack()
                if change == "hash": args.approve = "0" * 64
                if change == "identity": patches.enter_context(mock.patch.object(recipe, "auth", return_value=({}, {})))
                if change == "source": patches.enter_context(mock.patch.object(recipe, "sources", return_value={}))
                if change in ("expiry", "extra", "directory"):
                    if change == "expiry": env["payload"]["expires_at"] = time.time() - 1
                    if change == "extra": env["payload"]["unexpected"] = "ignored?"
                    if change == "directory": env["payload"]["directory"] = "/wrong"
                    env["sha256"] = recipe.files.sha(recipe.files.canonical(env["payload"]))
                    args.approve = env["sha256"]
                    (self.root / ".gate" / recipe.PLAN).write_text(json.dumps(env))
                with patches, mock.patch.object(recipe.inspect, "Inspector") as client:
                    self.assertEqual(self.invoke(args), 3)
                client.assert_not_called()

    def test_attempt_is_consumed_before_first_client_and_not_replayable(self):
        env = self.prepared()
        def inspect_after_consumption(*args):
            self.assertFalse((self.root / ".gate" / recipe.PLAN).exists())
            self.assertTrue(self.receipt(env).exists())
            raise ValueError("synthetic private error")
        with mock.patch.object(recipe.inspect, "Inspector", side_effect=inspect_after_consumption) as client:
            self.assertEqual(self.invoke(self.execution(env)), 3)
            self.assertEqual(self.invoke(self.execution(env)), 3)
            self.assertEqual(client.call_count, 1)
        self.assertEqual(json.loads(self.receipt(env).read_text())["status"], "incomplete-outcome-review-required")

    def fake_native(self, storage, fail=None):
        outer = self
        class Native:
            def __init__(self, root, payload, receipt, save):
                self.root, self.p, self.receipt, self.save = root, payload, receipt, save
                self.labels = []
                outer.native = self
            def run(self, label, who, argv, expected=0):
                self.labels.append(label)
                self.receipt["steps"].append({"label": label, "final_exit_code": 0})
                primary, lock, recovery, _ = self.p["names"]
                if label == "version": return b'{"terraform_version":"1.16.6"}'
                if label.startswith("init-"): return b"initialized"
                if label in ("push-v1", "push-v2", "restore-v1"):
                    raw = Path(argv[-1]).read_bytes()
                    if label == "push-v2":
                        state = json.loads(raw); state["serial"] += 1
                        raw = recipe.files.canonical(state)
                    storage.add(recovery if label == "restore-v1" else primary, raw)
                if label == fail: raise ValueError("simulated response loss after mutation")
                if label == "contender-blocked": return b"Error acquiring the state lock: 00000000-0000-0000-0000-000000000001"
                if label == "contender-control": FakeServer.active.calls["/contender"] = 2
                return b"ok"
            def start(self, label, who, argv):
                self.labels.append(label)
                self.receipt["steps"].append({"label": label, "final_exit_code": 0})
                storage.live[self.p["names"][1]] = {"bytes": b'{"Operation":"OperationTypePlan","ID":"00000000-0000-0000-0000-000000000001"}'}
                return SimpleNamespace(poll=lambda: None), {}, None
            def finish(self, entry):
                storage.live.pop(self.p["names"][1], None)
                return b"ok"
            def settle(self):
                self.save()
        return Native

    def simulate(self, env, storage, fail=None):
        def cached(path):
            return {"metadata": {"type": "oci", "config": recipe.backend(env["payload"], env["payload"]["names"][2 if path.name == "recovery" else 0])},
                    "types": ["oci"], "cloud": False, "declarations": [], "metadata_sha256": "fixture",
                    "source_sha256": {}, "workspace": "default"}
        with mock.patch.object(recipe.inspect, "Inspector", return_value=storage), \
             mock.patch.object(recipe, "Native", self.fake_native(storage, fail)), \
             mock.patch.object(recipe.fixture, "LoopbackFixture", FakeServer), \
             mock.patch.object(recipe.backend_config, "inspect_backend", side_effect=cached):
            return self.invoke(self.execution(env))

    def test_fixed_recipe_tests_contention_overwrite_and_separate_recovery(self):
        env, storage = self.prepared(), Storage()
        self.assertEqual(self.simulate(env, storage), 0)
        receipt = json.loads(self.receipt(env).read_text())
        self.assertEqual(receipt["status"], "verified-synthetic-only")
        self.assertTrue(receipt["lock_contention_verified"])
        self.assertFalse(receipt["iam_isolation_verified"])
        self.assertEqual(len(self.native.labels), 10)
        self.assertTrue(FakeServer.active.released)
        self.assertEqual(json.loads(storage.live[env["payload"]["names"][0]]["bytes"])["outputs"]["generation"]["value"], 2)

    def test_mutation_response_loss_stops_all_downstream_steps(self):
        env, storage = self.prepared(), Storage()
        self.assertEqual(self.simulate(env, storage, fail="push-v2"), 3)
        self.assertNotIn("restore-v1", self.native.labels)
        self.assertTrue(FakeServer.active.released)
        self.assertEqual(len(storage.live), 1)
        self.assertEqual(self.invoke(self.execution(env)), 3)

    def test_native_timeout_never_kills_or_retries_and_records_pid(self):
        env = self.prepared()
        (self.root / "holder").mkdir()
        result = {"steps": []}
        native = recipe.Native(self.root, env["payload"], result, lambda: None)
        proc = mock.Mock(pid=1234)
        proc.wait.side_effect = subprocess.TimeoutExpired("synthetic", 1)
        proc.poll.return_value = None
        drain = mock.Mock(pid=5678)
        drain.poll.return_value = None
        with mock.patch.object(recipe.subprocess, "Popen", side_effect=[drain, proc]) as launch:
            entry = native.start("holder-plan", "holder", ["plan"])
            with self.assertRaises(recipe.files.ImageGateError): native.finish(entry, timeout=0.01)
            native.settle()
        self.assertEqual(launch.call_count, 2)
        proc.kill.assert_not_called(); proc.terminate.assert_not_called(); proc.send_signal.assert_not_called()
        self.assertEqual(result["steps"][0]["pid"], 1234)
        self.assertEqual(result["steps"][0]["status"], "still-running-outcome-unknown")
        self.assertEqual(set(launch.call_args.kwargs["env"]), {"HOME", "PATH", "LANG", "TF_INPUT", "TF_IN_AUTOMATION", "TF_CLI_CONFIG_FILE", "CHECKPOINT_DISABLE"})

    def test_cleanup_deletes_exact_versions_once_and_checks_both_inventories(self):
        env, storage = self.prepared(), Storage()
        self.assertEqual(self.simulate(env, storage), 0)
        args = SimpleNamespace(command="backend-cleanup-plan", dir=self.root, receipt=self.receipt(env), max_age_minutes=120)
        with mock.patch.object(recipe.inspect, "Inspector", return_value=storage):
            self.assertEqual(self.invoke(args), 0)
            cleanup = json.loads((self.root / ".gate" / recipe.CLEANUP).read_text())
            args = SimpleNamespace(command="backend-cleanup-run", dir=self.root, approve=cleanup["sha256"])
            self.assertEqual(self.invoke(args), 0)
            self.assertEqual(self.invoke(args), 3)
        self.assertEqual(len(storage.deleted), 3)
        self.assertEqual(storage.inventory("unused", []), {"objects": [], "versions": []})

    def test_stale_cleanup_manifest_is_consumed_without_deletion(self):
        env, storage = self.prepared(), Storage()
        self.assertEqual(self.simulate(env, storage), 0)
        args = SimpleNamespace(command="backend-cleanup-plan", dir=self.root, receipt=self.receipt(env), max_age_minutes=120)
        with mock.patch.object(recipe.inspect, "Inspector", return_value=storage):
            self.assertEqual(self.invoke(args), 0)
            cleanup = json.loads((self.root / ".gate" / recipe.CLEANUP).read_text())
            storage.add(env["payload"]["names"][0], storage.live[env["payload"]["names"][0]]["bytes"])
            args = SimpleNamespace(command="backend-cleanup-run", dir=self.root, approve=cleanup["sha256"])
            self.assertEqual(self.invoke(args), 3)
            self.assertEqual(self.invoke(args), 3)
        self.assertEqual(storage.deleted, [])

    def test_cleanup_keeps_all_markers_until_historical_data_is_gone(self):
        rows = [{"name": "a.lock", "version_id": "marker", "is_delete_marker": True},
                {"name": "a.lock", "version_id": "old-lock", "is_delete_marker": False},
                {"name": "b.state", "version_id": "current", "is_delete_marker": False}]
        ordered = recipe.cleanup_order({"versions": rows, "objects": [{"name": "b.state", "version_id": "current"}]})
        self.assertEqual([r["version_id"] for r in ordered], ["old-lock", "marker", "current"])

    def test_unresolved_process_status_blocks_cleanup_preparation(self):
        env = self.prepared()
        path = self.tmp / "unresolved.json"
        path.write_text(json.dumps({"schema": "oci-backend-rehearsal-receipt/1", "status": "incomplete-outcome-review-required",
                                   "finished_at": time.time(), "payload": env["payload"], "steps": [{"pid": 1234}]}))
        path.chmod(0o600)
        with self.assertRaises(recipe.files.ImageGateError): recipe.cleanup_origin(path, self.root)


class NativeProcessTests(unittest.TestCase):
    """Real harmless writers exercise the production drainer without OCI auth."""

    def setUp(self):
        import hashlib
        import sys

        self.tmp = tempfile.TemporaryDirectory(prefix="native-process-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "client").mkdir()
        (self.root / "terraform.rc").write_text("disable_checkpoint = true\n")
        identity = {"home": str(Path.home()), "profile": "SYNTHETIC", "identity": {"synthetic": True}}
        binary = Path(sys.executable).resolve()
        fingerprint = {"path": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
        self.payload = {"identity": identity, "terraform": fingerprint,
                        "sources": {"synthetic": "binding"}, "expires_at": time.time() + 60}
        for patch in (mock.patch.object(recipe, "auth", return_value=({}, identity)),
                      mock.patch.object(recipe, "sources", return_value=self.payload["sources"]),
                      mock.patch.object(recipe.files, "fingerprint", return_value=fingerprint)):
            patch.start()
            self.addCleanup(patch.stop)
        self.receipt = {"steps": []}
        self.saved = []
        self.native = recipe.Native(self.root, self.payload, self.receipt,
                                    lambda: self.saved.append(copy.deepcopy(self.receipt)))
        self.addCleanup(self.native.settle)

    def test_real_success_captures_stdout_stderr_and_reconciles_drainer(self):
        raw = self.native.run("success", "client", ["-c",
            "import sys; print('synthetic-output', flush=True); sys.stderr.write('synthetic-error-stream\\n')"])
        self.assertIn(b"synthetic-output\n", raw)
        self.assertIn(b"synthetic-error-stream\n", raw)
        self.native.settle()
        step = self.receipt["steps"][0]
        self.assertEqual(step["status"], "completed")
        self.assertEqual(step["final_exit_code"], 0)
        self.assertEqual(step["drain_exit_code"], 0)
        self.assertTrue(self.saved)

    def test_real_overflow_drains_writer_caps_log_and_blocks_next_launch(self):
        marker = self.root / "writer-finished"
        script = ("import pathlib, sys; "
                  "sys.stdout.buffer.write(b'x' * (2 * 1024 * 1024)); sys.stdout.flush(); "
                  f"pathlib.Path({str(marker)!r}).write_text('finished')")
        entry = self.native.start("overflow", "client", ["-c", script])
        with self.assertRaises(recipe.files.ImageGateError):
            self.native.finish(entry, timeout=10)
        self.assertEqual(entry[0].returncode, 0)
        self.assertEqual(marker.read_text(), "finished")
        self.assertEqual(entry[2].stat().st_size, 256 * 1024)
        self.assertEqual(self.native.drainers[entry[0].pid].returncode, 2)
        count = len(self.receipt["steps"])
        with mock.patch.object(recipe.subprocess, "Popen", wraps=subprocess.Popen) as launch:
            with self.assertRaises(recipe.files.ImageGateError):
                self.native.start("after-overflow", "client", ["-c", "print('must-not-run')"])
            launch.assert_not_called()
        self.assertEqual(len(self.receipt["steps"]), count)

    def test_real_timeout_preserves_writer_until_normal_exit_then_blocks_next_step(self):
        entry = self.native.start("slow", "client", ["-c",
            "import time; time.sleep(0.25); print('finished-normally')"])
        proc = entry[0]
        with mock.patch.object(proc, "kill", wraps=proc.kill) as kill, \
             mock.patch.object(proc, "terminate", wraps=proc.terminate) as terminate, \
             mock.patch.object(proc, "send_signal", wraps=proc.send_signal) as signal:
            with self.assertRaises(recipe.files.ImageGateError):
                self.native.finish(entry, timeout=0.01)
            self.assertEqual(entry[1]["status"], "still-running-outcome-unknown")
            self.assertEqual(entry[1]["pid"], proc.pid)
            self.assertIsNone(proc.poll())
            self.assertEqual(proc.wait(timeout=3), 0)
            self.native.settle()
            kill.assert_not_called()
            terminate.assert_not_called()
            signal.assert_not_called()
        self.assertEqual(entry[2].read_bytes(), b"finished-normally\n")
        self.assertEqual(entry[1]["final_exit_code"], 0)
        self.assertEqual(entry[1]["drain_exit_code"], 0)
        with mock.patch.object(recipe.subprocess, "Popen", wraps=subprocess.Popen) as launch:
            with self.assertRaises(recipe.files.ImageGateError):
                self.native.start("after-timeout", "client", ["-c", "print('must-not-run')"])
            launch.assert_not_called()

    def test_real_expiry_refuses_before_any_child_or_log_is_created(self):
        self.payload["expires_at"] = time.time() - 1
        with mock.patch.object(recipe.subprocess, "Popen", wraps=subprocess.Popen) as launch:
            with self.assertRaises(recipe.files.ImageGateError):
                self.native.start("expired", "client", ["-c", "print('must-not-run')"])
            launch.assert_not_called()
        self.assertEqual(self.receipt["steps"], [])
        self.assertFalse((self.root / "expired.log").exists())


class SpawnInterruptionTests(unittest.TestCase):
    """Real harmless children regress interrupted launch bookkeeping."""

    setUp = NativeProcessTests.setUp

    def origin(self):
        path = self.root / "interrupted-receipt.json"
        path.write_text(json.dumps({"schema": "oci-backend-rehearsal-receipt/1",
            "status": "incomplete-outcome-review-required", "payload": {"directory": str(self.root)},
            "finished_at": time.time(), "steps": self.receipt["steps"]}))
        path.chmod(0o600)
        return path

    def test_interrupt_after_returned_child_registers_it_and_refuses_cleanup(self):
        original = subprocess.Popen
        children = []

        class InterruptedClose:
            def __init__(self, pipe):
                self.pipe = pipe

            def fileno(self):
                return self.pipe.fileno()

            def close(self):
                self.pipe.close()
                raise KeyboardInterrupt()

        def spawn(*args, **kwargs):
            proc = original(*args, **kwargs)
            children.append(proc)
            if len(children) == 1:
                proc.stdin = InterruptedClose(proc.stdin)
            return proc

        with mock.patch.object(recipe.subprocess, "Popen", side_effect=spawn):
            with self.assertRaises(KeyboardInterrupt):
                self.native.start("interrupted-close", "client", ["-c", "import time; time.sleep(0.25)"])
        self.assertEqual(len(children), 2)
        self.assertIs(self.native.running[0][0], children[1])
        self.assertEqual(self.receipt["steps"][0]["status"], "launch-outcome-unknown")
        self.assertEqual(self.receipt["steps"][0]["pid"], children[1].pid)
        with self.assertRaises(recipe.files.ImageGateError):
            recipe.cleanup_origin(self.origin(), self.root)
        self.native.settle()
        self.assertEqual(children[1].returncode, 0)
        self.assertEqual(children[0].returncode, 0)
        with self.assertRaises(recipe.files.ImageGateError):
            recipe.cleanup_origin(self.origin(), self.root)
        with mock.patch.object(recipe.subprocess, "Popen") as forbidden:
            with self.assertRaises(recipe.files.ImageGateError):
                self.native.start("after-interruption", "client", ["-c", "pass"])
            forbidden.assert_not_called()

    def test_interrupt_before_popen_returns_never_claims_failed_exec(self):
        original = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            proc = original(*args, **kwargs)
            children.append(proc)
            if len(children) == 2:
                raise KeyboardInterrupt()
            return proc

        try:
            with mock.patch.object(recipe.subprocess, "Popen", side_effect=spawn):
                with self.assertRaises(KeyboardInterrupt):
                    self.native.start("interrupted-return", "client", ["-c", "import time; time.sleep(0.1)"])
            self.assertEqual(self.receipt["steps"][0]["status"], "launch-outcome-unknown")
            with self.assertRaises(recipe.files.ImageGateError):
                recipe.cleanup_origin(self.origin(), self.root)
        finally:
            for proc in reversed(children):
                proc.wait(timeout=5)
        self.assertTrue(all(proc.returncode == 0 for proc in children))

    def test_proven_exec_failure_reaps_drainer_without_native_process(self):
        original = subprocess.Popen
        readers = []

        def spawn(*args, **kwargs):
            if readers:
                raise FileNotFoundError("synthetic unavailable executable")
            proc = original(*args, **kwargs)
            readers.append(proc)
            return proc

        with mock.patch.object(recipe.subprocess, "Popen", side_effect=spawn):
            with self.assertRaises(FileNotFoundError):
                self.native.start("failed-exec", "client", ["-c", "pass"])
        self.assertEqual(self.receipt["steps"][0]["status"], "launch-failed")
        self.assertEqual(self.receipt["steps"][0]["drain_exit_code"], 0)
        self.assertEqual(readers[0].returncode, 0)
        self.assertEqual(self.native.running, [])


if __name__ == "__main__":
    unittest.main()
