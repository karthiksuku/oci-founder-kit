"""Image approval boundary: fake Docker and OCI clients only, never real pushes."""

import contextlib
import fcntl
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "oci-deploy" / "scripts"))
import deploy_gate as gate  # noqa: E402
import image_gate as image_gate  # noqa: E402

REPO = "ocid1.containerrepo.oc1.ap-melbourne-1.syntheticrepo"
COMPARTMENT = "ocid1.compartment.oc1..syntheticcompartment"
TENANCY = "ocid1.tenancy.oc1..synthetictenancy"
TAG = "rehearsal-001"
IMAGE = {"id": "sha256:" + "a" * 64, "size": 12345678,
         "os": "linux", "architecture": "amd64", "variant": ""}


class ImageGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="image-gate-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stack = self.root / "stack"
        self.stack.mkdir()
        self.state_file = self.root / "fake-state.json"
        self.log_file = self.root / "fake-log.jsonl"
        self.receipt_file = self.root / "registry-receipt.json"
        self.clients = {}
        for name in ("docker", "oci"):
            destination = self.root / name
            shutil.copyfile(ROOT / "tests" / "fixtures" / "fake_image_clients.py", destination)
            destination.chmod(0o700)
            self.clients[name] = str(destination)
        self.env = mock.patch.dict(os.environ, {
            "DOCKER_BIN": self.clients["docker"], "OCI_BIN": self.clients["oci"],
            "FAKE_IMAGE_STATE": str(self.state_file), "FAKE_IMAGE_LOG": str(self.log_file),
            "OCI_CLI_ENDPOINT": "https://untrusted.invalid", "OCI_CLI_QUERY": "untrusted"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = {"image": IMAGE, "tag": TAG, "digest": "sha256:" + "b" * 64,
                      "repository": {"id": REPO, "compartment-id": COMPARTMENT,
                                     "display-name": "taskboard", "namespace": "syntheticnamespace",
                                     "is-public": False, "is-immutable": True,
                                     "repository-type": "STANDARD", "is-top-level": False,
                                     "lifecycle-state": "AVAILABLE"}}
        self.receipt = {"schema": "oci-deploy-receipt/2", "kind": "apply", "status": "applied",
                        "target": {"region": "ap-melbourne-1", "profile": "DEFAULT", "auth": "SecurityToken",
                                   "tenancy_ocid": TENANCY, "compartment_ocid": COMPARTMENT},
                        "planned": [{"address": "oci_artifacts_container_repository.app",
                                     "type": "oci_artifacts_container_repository", "action": "create"}],
                        "resources": [{"address": "oci_artifacts_container_repository.app",
                                       "type": "oci_artifacts_container_repository", "id": REPO,
                                       "name": "taskboard", "compartment_id": COMPARTMENT}]}
        self.save_state()
        self.save_receipt()

    def save_state(self):
        self.state_file.write_text(json.dumps(self.state))

    def save_receipt(self):
        self.receipt_file.write_text(json.dumps(self.receipt))
        self.receipt_file.chmod(0o600)

    def command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate.main(list(args))
        self.assertNotIn("SYNTHETIC-CLIENT-SECRET", out.getvalue() + err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def prepare(self, *extra):
        return self.command("image-plan", "--dir", str(self.stack), "--registry-receipt", str(self.receipt_file),
                            "--repository-id", REPO, "--image", "taskboard:local", "--tag", TAG, *extra)

    @property
    def plan_file(self):
        return self.stack / ".gate" / "image-plan.json"

    def plan(self):
        code, out, err = self.prepare()
        self.assertEqual(code, 0, err)
        envelope = json.loads(self.plan_file.read_text())
        self.assertIn(envelope["plan_sha256"], out)
        return envelope

    def push(self, digest):
        return self.command("image-push", "--dir", str(self.stack), "--approve", digest)

    def calls(self):
        return [json.loads(line) for line in self.log_file.read_text().splitlines()] if self.log_file.exists() else []

    def pushed(self):
        return [r for r in self.calls() if r["client"] == "docker" and r["args"][:2] == ["image", "push"]]

    def attempted(self, digest):
        return json.loads((self.stack / ".gate" / "image-receipts" / (digest + ".json")).read_text())

    def test_plan_binds_image_identity_target_binary_expiry_and_receipt(self):
        envelope = self.plan()
        plan = envelope["plan"]
        self.assertEqual(envelope["plan_sha256"], image_gate.sha(image_gate.canonical(plan)))
        self.assertEqual(plan["source_image"], IMAGE)
        self.assertEqual(plan["destination"], "mel.ocir.io/syntheticnamespace/taskboard:" + TAG)
        self.assertEqual(plan["target"]["compartment_ocid"], COMPARTMENT)
        self.assertEqual(plan["target"]["tenancy_ocid"], TENANCY)
        self.assertEqual(plan["binaries"]["docker"], image_gate.fingerprint("docker"))
        self.assertEqual(plan["expires_at_epoch"] - plan["created_at_epoch"], 7200)
        self.assertEqual(plan["source_receipt"]["sha256"], image_gate.sha(self.receipt_file.read_bytes()))
        self.assertEqual(stat.S_IMODE(self.plan_file.stat().st_mode), 0o600)
        self.assertEqual(self.pushed(), [])
        self.assertTrue(all(call["endpoint_override"] is None for call in self.calls()))
        for call in self.calls():
            if call["client"] == "oci":
                self.assertIn("--cli-rc-file", call["args"])
                self.assertNotIn("--endpoint", call["args"])

    def test_success_verifies_remote_digest_manifest_and_platform(self):
        envelope = self.plan()
        code, out, err = self.push(envelope["plan_sha256"])
        self.assertEqual(code, 0, err)
        receipt = self.attempted(envelope["plan_sha256"])
        self.assertEqual(receipt["status"], "verified")
        self.assertEqual(receipt["remote_image"]["digest"], self.state["digest"])
        self.assertIn("@" + self.state["digest"], out)
        self.assertFalse(self.plan_file.exists())
        self.assertEqual(len(self.pushed()), 1)
        lookups = [c for c in self.calls() if c["args"][:4] == ["artifacts", "container", "image", "lookup"]]
        self.assertEqual(len(lookups), 2)
        self.assertTrue(any(c["args"][:3] == ["manifest", "inspect", "--verbose"] for c in self.calls()))
        self.assertNotEqual(self.push(envelope["plan_sha256"])[0], 0)
        self.assertEqual(len(self.pushed()), 1)

    def test_existing_tag_is_refused_at_plan_and_again_before_push(self):
        self.state["existing"] = True
        self.save_state()
        self.assertEqual(self.prepare()[0], 3)
        self.state.pop("existing")
        self.save_state()
        plan = self.plan()
        self.state["existing"] = True
        self.save_state()
        self.assertEqual(self.push(plan["plan_sha256"])[0], 3)
        self.assertEqual(self.pushed(), [])

    def test_public_mutable_wrong_scope_and_unsafe_registry_are_refused(self):
        for field, value in [("is-public", True), ("is-immutable", False), ("is-immutable", None),
                             ("compartment-id", "ocid1.compartment.oc1..different"), ("namespace", "other"),
                             ("display-name", "taskboard.evil"), ("is-top-level", True),
                             ("repository-type", "PULL_THROUGH"), ("lifecycle-state", "DELETING")]:
            with self.subTest(field=field, value=value):
                old = self.state["repository"][field]
                self.state["repository"][field] = value
                self.save_state()
                self.assertEqual(self.prepare()[0], 3)
                self.state["repository"][field] = old
        self.assertEqual(self.pushed(), [])

    def test_failed_or_wrong_registry_receipt_is_refused(self):
        for field, value in [("status", "failed"), ("kind", "destroy"), ("schema", "unknown")]:
            with self.subTest(field=field):
                old = self.receipt[field]
                self.receipt[field] = value
                self.save_receipt()
                self.assertEqual(self.prepare()[0], 3)
                self.receipt[field] = old
        self.receipt["target"]["tenancy_ocid"] = TENANCY.replace(".oc1.", ".oc2.")
        self.save_receipt()
        self.assertEqual(self.prepare()[0], 3)
        self.assertEqual(self.calls(), [])

    def test_tag_cli_reference_size_and_expiry_bounds(self):
        for flags in [("--tag", "../../evil"), ("--tag", "x*"), ("--image=--help",),
                      ("--max-image-bytes", "1"), ("--max-age-minutes", "0"),
                      ("--max-age-minutes", "1441"), ("--max-image-bytes", str(11 * 1024 ** 3))]:
            with self.subTest(flags=flags):
                self.assertNotEqual(self.prepare(*flags)[0], 0)
        self.assertEqual(self.pushed(), [])

    def test_plan_hash_mismatch_and_content_tamper_refuse(self):
        envelope = self.plan()
        self.assertEqual(self.push("0" * 64)[0], 3)
        envelope["plan"]["target"]["registry_host"] = "untrusted.invalid"
        self.plan_file.write_text(json.dumps(envelope))
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        self.assertEqual(self.pushed(), [])

    def test_expired_plan_and_future_clock_refuse(self):
        envelope = self.plan()
        with mock.patch.object(image_gate.time, "time", return_value=envelope["plan"]["expires_at_epoch"] + 1):
            self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        with mock.patch.object(image_gate.time, "time", return_value=envelope["plan"]["created_at_epoch"] - 301):
            self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        self.assertEqual(self.pushed(), [])

    def test_expiry_during_final_read_checks_cannot_start_push(self):
        envelope = self.plan()
        original_absent = image_gate.absent
        calls = 0
        with mock.patch.object(image_gate.time, "time", return_value=envelope["plan"]["created_at_epoch"]) as clock:
            def slow_absent(*args):
                nonlocal calls
                original_absent(*args)
                calls += 1
                if calls == 2:
                    clock.return_value = envelope["plan"]["expires_at_epoch"] + 1
            with mock.patch.object(image_gate, "absent", side_effect=slow_absent):
                self.assertEqual(self.push(envelope["plan_sha256"])[0], 1)
        self.assertEqual(self.pushed(), [])
        self.assertEqual(self.attempted(envelope["plan_sha256"])["status"], "failed")

    def test_changed_client_and_receipt_refuse(self):
        envelope = self.plan()
        with Path(self.clients["docker"]).open("a") as handle:
            handle.write("\n# modified client\n")
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        envelope = self.plan()
        self.receipt["note"] = "changed"
        self.save_receipt()
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        self.assertEqual(self.pushed(), [])

    def test_changed_image_or_repository_refuse(self):
        envelope = self.plan()
        self.state["image"] = {**IMAGE, "id": "sha256:" + "c" * 64}
        self.save_state()
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        self.state["image"] = IMAGE
        self.state["repository"]["is-public"] = True
        self.save_state()
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        self.assertEqual(self.pushed(), [])

    def test_last_moment_tag_race_or_local_swap_consumes_without_push(self):
        for fault in ("race", "swap_on_tag"):
            with self.subTest(fault=fault):
                self.state = {k: v for k, v in self.state.items() if k not in ("race", "swap_on_tag", "existing", "tag_swapped")}
                self.save_state()
                envelope = self.plan()
                self.state[fault] = True
                self.save_state()
                self.assertEqual(self.push(envelope["plan_sha256"])[0], 1)
                receipt = self.attempted(envelope["plan_sha256"])
                self.assertEqual(receipt["status"], "failed")
                self.assertFalse(receipt["write_may_have_occurred"])
                self.assertFalse(self.plan_file.exists())
        self.assertEqual(self.pushed(), [])

    def test_partial_push_failure_keeps_private_unverified_receipt_and_no_replay(self):
        envelope = self.plan()
        original = self.plan_file.read_bytes()
        self.state["push_partial_failure"] = True
        self.save_state()
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 5)
        receipt = self.attempted(envelope["plan_sha256"])
        self.assertEqual(receipt["status"], "unverified")
        self.assertEqual(receipt["failure_stage"], "push")
        self.assertTrue(receipt["write_may_have_occurred"])
        self.state.pop("push_partial_failure")
        self.save_state()
        self.plan_file.write_bytes(original)
        self.plan_file.chmod(0o600)
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 3)
        self.assertEqual(len(self.pushed()), 1)
        for file in (self.stack / ".gate").rglob("*.json"):
            self.assertNotIn("SYNTHETIC-CLIENT-SECRET", file.read_text())

    def test_remote_metadata_manifest_and_platform_must_all_verify(self):
        for fault in ("wrong_remote", "wrong_manifest", "wrong_platform", "manifest_list", "no_push_digest", "lookup_identity_mismatch"):
            with self.subTest(fault=fault):
                self.state = {k: v for k, v in self.state.items() if k not in (
                    "wrong_remote", "wrong_manifest", "wrong_platform", "manifest_list", "no_push_digest", "lookup_identity_mismatch", "pushed")}
                self.save_state()
                envelope = self.plan()
                self.state[fault] = True
                self.save_state()
                self.assertEqual(self.push(envelope["plan_sha256"])[0], 5)
                receipt = self.attempted(envelope["plan_sha256"])
                self.assertEqual(receipt["status"], "unverified")
                self.assertEqual(receipt["failure_stage"], "remote-verification")

    def test_oci_manifest_shape_is_supported(self):
        self.state["oci_manifest"] = True
        self.save_state()
        envelope = self.plan()
        self.assertEqual(self.push(envelope["plan_sha256"])[0], 0)

    def test_omitted_or_null_docker_variant_is_normalized(self):
        for variant in (None, "omitted"):
            self.state["image"] = dict(IMAGE)
            if variant == "omitted":
                self.state["image"].pop("variant")
            else:
                self.state["image"]["variant"] = variant
            self.save_state()
            envelope = self.plan()
            self.assertEqual(envelope["plan"]["source_image"]["variant"], "")

    def test_unknown_or_failed_tag_absence_is_not_success(self):
        self.state["bad_list"] = True
        self.save_state()
        self.assertEqual(self.prepare()[0], 3)
        self.state.pop("bad_list")
        self.state["fail"] = ["artifacts", "container", "image", "list"]
        self.save_state()
        self.assertEqual(self.prepare()[0], 1)
        self.assertEqual(self.pushed(), [])

    def test_unsafe_region_key_cannot_choose_arbitrary_host(self):
        self.state["regions"] = [{"name": "ap-melbourne-1", "key": "EVIL.invalid/"}]
        self.save_state()
        self.assertEqual(self.prepare()[0], 3)

    def test_symlink_hardlink_fifo_oversized_or_nonprivate_receipt_refused(self):
        original = self.receipt_file.read_bytes()
        target = self.root / "target.json"
        target.write_bytes(original)
        target.chmod(0o600)
        for kind in ("symlink", "hardlink", "fifo", "oversized", "public"):
            with self.subTest(kind=kind):
                self.receipt_file.unlink()
                if kind == "symlink":
                    self.receipt_file.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, self.receipt_file)
                elif kind == "fifo":
                    os.mkfifo(self.receipt_file, 0o600)
                else:
                    self.receipt_file.write_bytes(b"X" * (image_gate.MAX_JSON + 1) if kind == "oversized" else original)
                    self.receipt_file.chmod(0o644 if kind == "public" else 0o600)
                self.assertNotEqual(self.prepare()[0], 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual(target.read_bytes(), original)

    def test_gate_and_plan_symlinks_are_not_followed(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        (self.stack / ".gate").symlink_to(elsewhere)
        self.assertNotEqual(self.prepare()[0], 0)
        self.assertEqual(list(elsewhere.iterdir()), [])
        (self.stack / ".gate").unlink()
        self.plan()
        original = self.receipt_file.read_bytes()
        self.plan_file.unlink()
        self.plan_file.symlink_to(self.receipt_file)
        self.assertNotEqual(self.prepare()[0], 0)
        self.assertEqual(self.receipt_file.read_bytes(), original)

    def test_parent_directory_symlink_is_refused(self):
        alternate = self.root / "alternate"
        alternate.symlink_to(self.root, target_is_directory=True)
        self.receipt_file = alternate / self.receipt_file.name
        self.assertNotEqual(self.prepare()[0], 0)
        self.assertEqual(self.calls(), [])

    def test_concurrent_operation_is_refused(self):
        self.plan()
        with (self.stack / ".gate" / "image.lock").open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.prepare()[0], 3)

    def test_client_output_is_bounded(self):
        self.state["oversized"] = ["image", "inspect"]
        self.save_state()
        self.assertEqual(self.prepare()[0], 3)
        self.assertEqual(self.pushed(), [])

    def test_duplicate_or_malformed_json_does_not_disclose_raw_values(self):
        for raw in (b'{"schema":"SYNTHETIC-CLIENT-SECRET","schema":"x"}', b'{"SYNTHETIC-CLIENT-SECRET":'):
            self.receipt_file.write_bytes(raw)
            self.assertNotEqual(self.prepare()[0], 0)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
