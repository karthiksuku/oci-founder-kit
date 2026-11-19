"""Private configuration handoff preserves source and exact environment gates."""
import copy
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


def load(name):
    spec = importlib.util.spec_from_file_location("test_config_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


p, e, d = (load(name) for name in ("project", "environments", "deployment_config"))


class DeploymentConfiguration(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = self.root / "application"; self.app.mkdir()
        (self.app / "main.py").write_text("raise RuntimeError('do not execute application')\n")
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "build", "mode": "existing", "agent": "both", "stack": "custom", "blueprint": None,
                "project_identity": p.identity(store.root_fd), "created_at": now, "observed_at": now,
                "source_sha256": p.source_fingerprint(store.root_fd), "kit_sha256": p.kit_fingerprint(), "records": {}})
        self.target = {"region": "us-phoenix-1", "profile": "FOUNDER", "auth": "security_token",
            "compartment_id": "ocid1.compartment.oc1..syntheticapp", "vcn_id": "ocid1.vcn.oc1.phx.syntheticvcn",
            "app_subnet_id": "ocid1.subnet.oc1.phx.syntheticprivate", "lb_subnet_id": "ocid1.subnet.oc1.phx.syntheticpublic",
            "app_private_ip": "10.88.2.10", "certificate_id": "ocid1.certificate.oc1.phx.syntheticcert",
            "registry_id": "ocid1.containerrepo.oc1.phx.syntheticregistry", "availability_domain": "TEST:PHX-AD-1",
            "image_digest": "sha256:" + "a" * 64, "image_architecture": "AMD64", "origin": "https://app.example.test",
            "port": 8080, "health_path": "/healthz", "ocpus": 1, "memory_gbs": 4}
        self.backend = {"region": "us-phoenix-1", "namespace": "syntheticnamespace", "bucket": "synthetic-state",
                        "key": "rehearsal/main.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        e.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal",
                 target=self.target, backend=self.backend)
        self.stack = self.app / "deploy/rehearsal"; self.stack.mkdir(parents=True)
        for source in (ROOT / "blueprints/web-container/terraform").glob("*.tf"):
            shutil.copyfile(source, self.stack / source.name)
        self.private = self.app / ".oci-kit/environments/rehearsal"

    def choices(self):
        return {"variables": {"tenancy_ocid": "ocid1.tenancy.oc1..synthetictenancy", "home_region": "us-ashburn-1",
            "name": "synthetic-app", "app_image": "phx.ocir.io/syntheticnamespace/synthetic-app@" + self.target["image_digest"],
            "registry": {"compartment_ocid": self.target["compartment_id"], "repository_name": "synthetic-app"},
            "allowed_ingress_cidrs": ["203.0.113.10/32"],
            "application_contract": {"evidence_sha256": "b" * 64, "background_work": "absent"}}}

    def propose(self, value=None):
        path = self.root / "choices.json"
        path.write_text(json.dumps(self.choices() if value is None else value)); path.chmod(0o600)
        return d.request(self.app, environment="rehearsal", action="propose", config=path)

    def test_private_generated_inputs_match_existing_gate_without_source_or_cloud_execution(self):
        original = (self.app / "main.py").read_bytes()
        original_env = (self.private / "environment.json").read_bytes()
        proposal = self.propose()
        self.assertEqual(proposal["status"], "review")
        result = d.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["approval_granted"])
        values = json.loads((self.app / result["variables"]).read_bytes())
        backend = json.loads((self.app / result["backend"]).read_bytes())
        self.assertEqual(values["network"]["private_subnet_ocid"], self.target["app_subnet_id"])
        self.assertEqual(values["auth"], "SecurityToken")
        self.assertFalse(values["manage_runtime_iam"])
        self.assertEqual(backend, dict(self.backend, auth="SecurityToken", config_file_profile="FOUNDER"))
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py")
        binding = gate.select(self.stack, project=self.app, environment="rehearsal", backend=backend)
        self.assertEqual(binding["target"], self.target)
        for key in ("variables", "backend"):
            self.assertEqual((self.app / result[key]).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.app / result["variables"]).parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(original, (self.app / "main.py").read_bytes())
        self.assertIn(original_env, [path.read_bytes() for path in self.private.glob("environment-backup-*.json")])
        self.assertNotIn("ocid1.", json.dumps(result))
        self.assertNotIn("example.test", json.dumps(result))

    def test_inspection_batches_missing_choices_and_does_not_write(self):
        before = sorted(path.relative_to(self.app) for path in self.app.rglob("*"))
        result = d.request(self.app, environment="rehearsal")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(set(result["missing"]), d.VARIABLE_REQUIRED)
        self.assertEqual(before, sorted(path.relative_to(self.app) for path in self.app.rglob("*")))

    def test_target_completion_is_additive_and_conflicts_refused(self):
        target = dict(self.target); target.pop("origin")
        e.configure(self.app, name="rehearsal", target=target, backend=self.backend)
        value = self.choices(); value["target"] = {"origin": self.target["origin"]}
        proposal = self.propose(value)
        d.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        actual = json.loads((self.private / "environment.json").read_bytes())
        self.assertEqual(actual["target"], self.target)
        value["target"]["origin"] = "https://different.example.test"
        with self.assertRaises(d.ConfigurationError):
            self.propose(value)

    def test_stale_source_environment_or_expiry_cannot_prepare(self):
        for change in ("source", "environment", "expiry"):
            with self.subTest(change=change):
                proposal = self.propose()
                if change == "source":
                    (self.app / "main.py").write_text("changed = True\n")
                elif change == "environment":
                    e.configure(self.app, name="rehearsal", target=dict(self.target, profile="OTHER"), backend=self.backend)
                with mock.patch.object(d.time, "time", return_value=time.time() + (3601 if change == "expiry" else 0)):
                    with self.assertRaises(d.ConfigurationError):
                        d.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        self.assertFalse(list(self.private.glob("deployment-*/*")))

    def test_wrong_environment_and_replay_cannot_prepare(self):
        proposal = self.propose()
        e.create(self.app, name="production", role="production", infrastructure="deploy/production")
        with self.assertRaises((ValueError, OSError)):
            d.request(self.app, environment="production", action="prepare", approve=proposal["sha256"])
        d.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        with self.assertRaises((ValueError, OSError)):
            d.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])

    def test_unsupported_inputs_credentials_enabled_jobs_and_different_image_refused(self):
        changes = [{"manage_runtime_iam": True}, {"password": "synthetic-private-value"},
            {"public_environment": {"DATABASE_URL": "synthetic-private-value"}},
            {"public_environment": {"API_KEY": "synthetic-private-value"}},
            {"public_environment": {"APIKEY": "synthetic-private-value"}},
            {"public_environment": {"AUTHORIZATION": "synthetic-private-value"}},
            {"app_image": "phx.ocir.io/syntheticnamespace/synthetic-app@sha256:" + "c" * 64},
            {"application_contract": {"evidence_sha256": "b" * 64, "background_work": "enabled"}},
            {"application_contract": {"evidence_sha256": "b" * 64, "background_work": "disabled"}},
            {"allowed_ingress_cidrs": ["203.0.113.10/24"]}]
        for patch in changes:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                value = self.choices(); value["variables"].update(patch); self.propose(value)

    def test_preexisting_inputs_infrastructure_changes_and_symlinks_preserved(self):
        for filename in ("terraform.tfvars.json", "extra.auto.tfvars", "extra.tf"):
            path = self.stack / filename; path.write_text("existing = true")
            with self.assertRaises(ValueError):
                self.propose()
            self.assertEqual(path.read_text(), "existing = true"); path.unlink()
        (self.stack / "backend.tf.json").symlink_to(self.app / "main.py")
        with self.assertRaises((ValueError, OSError)):
            self.propose()

    def test_interruption_keeps_artifacts_private_and_does_not_adopt_them(self):
        proposal = self.propose()
        destination = self.private / ("deployment-" + proposal["sha256"][:16])
        destination.mkdir(mode=0o700)
        marker = destination / "variables.json"; marker.write_text("interrupted"); marker.chmod(0o600)
        before = (self.private / "environment.json").read_bytes()
        with self.assertRaises(FileExistsError):
            d.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        self.assertEqual(marker.read_text(), "interrupted")
        self.assertEqual(before, (self.private / "environment.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
