"""Credential-free packaging/foundation tests. Synthetic outputs never establish OCI readiness."""

import gzip
import hashlib
import importlib.util
import io
import json
import os
import subprocess
from pathlib import Path
import tarfile
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("test_foundation_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p, env, package, foundation = (load(name) for name in ("project", "environments", "packaging", "foundation"))
COMPARTMENT = "ocid1.compartment.oc1..syntheticapp"
STATE = "ocid1.compartment.oc1..syntheticstate"


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / "application"
        self.app.mkdir()
        (self.app / "main.py").write_text("raise RuntimeError('application must not execute')\n")
        self.bootstrap = self.root / "bootstrap"
        self.bootstrap.mkdir(mode=0o700)
        with p.Store(self.app, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})
        env.create(self.app, name="rehearsal", role="rehearsal", infrastructure="deploy/rehearsal",
                   target={"region": "us-phoenix-1", "compartment_id": COMPARTMENT})
        self.private = self.app / ".oci-kit/environments/rehearsal"

    def private_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return path

    def selected(self):
        return json.loads((self.private / "environment.json").read_text())


class Packaging(Fixture):
    def descriptor(self, recipe="fastapi", **updates):
        value = {"schema": "oci-kit-application/1", "recipe": recipe, "app_directory": ".", "port": 8080,
                 "health_path": "/health", "commands": {"build": ["review-build"], "start": ["review-start"], "test": ["review-test"]},
                 "dependencies": ["DATABASE_URL"], "background_work": "source",
                 "probe_runtime": "python", "base_image": "python@sha256:" + "a" * 64, "entrypoint": "main:app"}
        if recipe == "nextjs":
            value.update(probe_runtime="node", base_image="node@sha256:" + "b" * 64)
            (self.app / "package.json").write_text(json.dumps({"dependencies": {"next": "16.0.0"}}))
            (self.app / "package-lock.json").write_text("{}")
            (self.app / "next.config.mjs").write_text("export default { output: 'standalone' };\n")
        elif recipe == "fastapi":
            (self.app / "requirements.txt").write_text("uvicorn==0.38.0 --hash=sha256:" + "a" * 64 + "\n")
        else:
            value.pop("base_image")
            value.pop("entrypoint")
            (self.app / "Dockerfile").write_text("FROM python@sha256:" + "a" * 64 + "\nCMD [\"python\", \"main.py\"]\n")
        value.update(updates)
        return value

    def propose(self, value):
        return package.request(self.app, environment="rehearsal", action="propose",
                               descriptor=self.private_json("descriptor.json", value))

    def test_all_recipes_only_add_packaging_preserve_source_and_never_execute_commands(self):
        for recipe in package.RECIPES:
            with self.subTest(recipe=recipe):
                for file in self.app.glob("Dockerfile*"):
                    file.unlink()
                value = self.descriptor(recipe)
                before = (self.app / "main.py").read_bytes()
                original = (self.app / "Dockerfile").read_bytes() if recipe == "dockerfile" else None
                proposal = self.propose(value)
                self.assertEqual(proposal["status"], "review")
                report = package.request(self.app, environment="rehearsal", action="apply", approve=proposal["sha256"])
                self.assertEqual(report["status"], "applied")
                self.assertFalse(report["commands_executed"])
                self.assertEqual((self.app / "main.py").read_bytes(), before)
                if original:
                    self.assertEqual((self.app / "Dockerfile").read_bytes(), original)
                else:
                    self.assertIn("USER 65532:65532", (self.app / "Dockerfile.oci").read_text())
                ignore = self.app / ("Dockerfile" if original else "Dockerfile.oci")
                self.assertIn("**/.oci-kit", Path(str(ignore) + ".dockerignore").read_text())

    def test_missing_inputs_and_wrong_recipe_do_not_edit_app(self):
        value = self.descriptor("nextjs")
        (self.app / "next.config.mjs").write_text("export default {};")
        report = self.propose(value)
        self.assertEqual(report["status"], "blocked")
        with self.assertRaises(package.PackagingError):
            package.request(self.app, environment="rehearsal", action="apply", approve=report["sha256"])
        self.assertFalse((self.app / "Dockerfile.oci").exists())

    def test_overwrite_symlink_and_hardlink_refused(self):
        value = self.descriptor()
        destination = self.app / "Dockerfile.oci"
        destination.symlink_to(self.app / "main.py")
        with self.assertRaises(ValueError):
            self.propose(value)
        destination.unlink()
        requirements = self.app / "requirements.txt"
        os.link(requirements, self.root / "other")
        with self.assertRaises(ValueError):
            self.propose(value)

    def test_wrong_environment_source_change_expiry_and_replay_refused(self):
        report = self.propose(self.descriptor())
        env.create(self.app, name="production", role="production", infrastructure="deploy/production")
        with self.assertRaises(FileNotFoundError):
            package.request(self.app, environment="production", action="apply", approve=report["sha256"])
        with mock.patch.object(package.time, "time", return_value=time.time() + 3601), self.assertRaises(package.PackagingError):
            package.request(self.app, environment="rehearsal", action="apply", approve=report["sha256"])
        (self.app / "main.py").write_text("changed = True")
        with self.assertRaises(package.PackagingError):
            package.request(self.app, environment="rehearsal", action="apply", approve=report["sha256"])
        report = self.propose(self.descriptor())
        package.request(self.app, environment="rehearsal", action="apply", approve=report["sha256"])
        with self.assertRaises(package.PackagingError):
            package.request(self.app, environment="rehearsal", action="apply", approve=report["sha256"])

    def test_descriptor_rejects_credentials_unknown_fields_paths_and_enabled_workers(self):
        for change in ({"token": "synthetic"}, {"app_directory": "../outside"}, {"port": True},
                       {"health_path": "/health?token=synthetic"}, {"background_work": "enabled"},
                       {"base_image": "python:latest"}, {"dependencies": ["https://private.invalid"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                package.descriptor_value(self.descriptor(**change))
        with self.assertRaises(ValueError):
            package.request(self.app, environment=None)

    def test_private_descriptor_required_and_nested_symlink_refused(self):
        descriptor = self.private_json("descriptor.json", self.descriptor())
        descriptor.chmod(0o644)
        with self.assertRaises(ValueError):
            package.request(self.app, environment="rehearsal", action="propose", descriptor=descriptor)
        (self.app / "nested").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self.propose(self.descriptor(app_directory="nested"))

    def layout(self, *, content=b"ordinary application bytes", name="app/main.py", arch="amd64", environment=None):
        folder = self.root / ("layout-" + str(time.time_ns()))
        folder.mkdir(mode=0o700)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
        raw = stream.getvalue()
        compressed = gzip.compress(raw, mtime=0)
        config = p.canonical({"os": "linux", "architecture": arch, "config": {"Env": environment or []},
                             "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(raw).hexdigest()]}})
        image = "sha256:" + hashlib.sha256(config).hexdigest()
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "digest": image, "size": len(config)},
                    "layers": [{"mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
                                "digest": "sha256:" + hashlib.sha256(compressed).hexdigest(), "size": len(compressed)}]}
        for payload in (config, compressed):
            path = folder / hashlib.sha256(payload).hexdigest()
            path.write_bytes(payload)
            path.chmod(0o600)
        for key, payload in (("manifest.json", p.canonical(manifest)), ("version", b"Directory Transport Version: 1.1\n")):
            (folder / key).write_bytes(payload)
            (folder / key).chmod(0o600)
        return folder, image

    def test_every_layer_scan_blocks_private_paths_credentials_and_config_without_runtime(self):
        self.propose(self.descriptor())
        for values in ({"name": "app/.env.production"}, {"name": "app/.npmrc"}, {"name": "root/.kube/config"},
                       {"name": "root/.netrc"}, {"name": "root/.git-credentials"},
                       {"content": b"prefix " + b"-----BEGIN " + b"ENCRYPTED PRIVATE KEY-----\nMI" + b"A" * 64},
                       {"content": b"npm_" + b"s" * 36}, {"environment": ["APP_SECRET=synthetic-value"]}):
            with self.subTest(values=values):
                layout, image = self.layout(**values)
                with mock.patch.object(package, "local_health") as runtime:
                    result = package.request(self.app, environment="rehearsal", action="verify", layout=layout, image=image)
                runtime.assert_not_called()
                self.assertEqual(result["status"], "blocked")
                self.assertNotIn("synthetic-value", json.dumps(result))

    def test_public_library_pem_delimiter_alone_is_not_a_private_key(self):
        self.assertIsNone(package.PATTERN.search(b"TLS parser constant " + b"-----BEGIN " + b"PRIVATE KEY-----"))
        self.assertIsNotNone(package.PATTERN.search(b"-----BEGIN " + b"PRIVATE KEY-----\\nMI" + b"A" * 64))
        self.assertIsNone(package.PATTERN.search(b"-----BEGIN " + b"PRIVATE KEY-----\nABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))
        self.assertIsNone(package.PATTERN.search(b"sk_X509_ATTRIBUTE_deep_copy"))

    def test_empty_npm_config_contains_no_credential_but_nonempty_file_is_blocked(self):
        self.propose(self.descriptor())
        folder, image = self.layout(name="usr/local/lib/node_modules/npm/.npmrc", content=b"")
        with mock.patch.object(package, "local_health", return_value=({}, {"status": "passed"})):
            result = package.request(self.app, environment="rehearsal", action="verify", layout=folder, image=image)
        self.assertEqual(result["status"], "passed")

    def test_configuration_credentials_refuse_before_runtime_including_encoded_urls(self):
        self.propose(self.descriptor())
        values = [
            "DATABASE_URL=postgres://user:synthetic-password@database.invalid/app",
            "DATABASE_URL=postgres://%75ser:%70assword@database.invalid/app",
            "DATABASE_URL=postgres://%75%2Fser:%70%40ss%3Aword@database.invalid/app",
            "DATABASE_URL=postgres%3A%2F%2Fuser%3Apassword%40database.invalid%2Fapp",
            r"CONNECTION=postgres:\/\/user:password@database.invalid/app",
            r"CONNECTION=postgres\u003a\u002f\u002fuser\u003apassword\u0040database.invalid/app",
            "OPENAI_API_KEY=synthetic-not-an-actual-key",
            "APP_SIGNING_KEY=synthetic-not-an-actual-key",
            "AWS_ACCESS_KEY_ID=synthetic-not-an-actual-key",
        ]
        for value in values:
            with self.subTest(value=value):
                folder, image = self.layout(environment=[value])
                with mock.patch.object(package, "local_health") as runtime:
                    result = package.request(self.app, environment="rehearsal", action="verify", layout=folder, image=image)
                runtime.assert_not_called()
                self.assertEqual(result["status"], "blocked")
                self.assertIn("credential_environment", result["credential_scan"]["findings"])
                self.assertNotIn("synthetic-password", json.dumps(result))

    def test_public_issuer_and_noncredential_configuration_remain_valid(self):
        for value in ("OIDC_ISSUER=https://identity.example.invalid/realm", "PORT=8080",
                      "DATABASE_URL=postgres://database.invalid/app", "PUBLIC_KEY=public-material",
                      "OPENAI_API_KEY=", "CACHE_KEY_PREFIX=requests"):
            self.assertFalse(package.credential_configuration({"config": {"Env": [value]}}), value)

    def test_deleted_package_credentials_remain_in_prior_layer_and_block(self):
        self.propose(self.descriptor())
        folder, image = self.layout(name="app/.npmrc", content=b"//registry.npmjs.org/:_authToken=synthetic")
        manifest = json.loads((folder / "manifest.json").read_text())
        config = json.loads((folder / image[7:]).read_text())
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            entry = tarfile.TarInfo("app/.wh..npmrc")
            archive.addfile(entry, io.BytesIO())
        raw = stream.getvalue()
        layer = gzip.compress(raw, mtime=0)
        digest = hashlib.sha256(layer).hexdigest()
        (folder / digest).write_bytes(layer)
        (folder / digest).chmod(0o600)
        manifest["layers"].append({"mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
                                   "digest": "sha256:" + digest, "size": len(layer)})
        config["rootfs"]["diff_ids"].append("sha256:" + hashlib.sha256(raw).hexdigest())
        config_raw = p.canonical(config)
        (folder / image[7:]).unlink()
        image = "sha256:" + hashlib.sha256(config_raw).hexdigest()
        (folder / image[7:]).write_bytes(config_raw)
        (folder / image[7:]).chmod(0o600)
        manifest["config"].update(digest=image, size=len(config_raw))
        (folder / "manifest.json").write_bytes(p.canonical(manifest))
        with mock.patch.object(package, "local_health") as runtime:
            result = package.request(self.app, environment="rehearsal", action="verify", layout=folder, image=image)
        runtime.assert_not_called()
        self.assertEqual(result["status"], "blocked")

    def test_verified_layout_is_bound_to_health_and_manifest_not_tag(self):
        self.propose(self.descriptor())
        layout, image = self.layout()
        with mock.patch.object(package, "local_health", return_value=({}, {"status": "passed"})):
            result = package.request(self.app, environment="rehearsal", action="verify", layout=layout, image=image)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["image_config_digest"], image)
        self.assertEqual(result["image_digest"], "sha256:" + p.digest((layout / "manifest.json").read_bytes()))
        self.assertEqual(result["evidence_scope"], "local-tested")
        self.assertEqual(result["cloud"], "not_checked")
        self.assertEqual((self.app / result["evidence"]).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            package.request(self.app, environment="rehearsal", action="verify", layout=layout, image="mutable:latest")
        wrong_layout, wrong_image = self.layout(arch="arm64")
        with self.assertRaises(Exception):
            package.request(self.app, environment="rehearsal", action="verify", layout=wrong_layout, image=wrong_image)

    def test_runtime_failure_does_not_establish_verified_image(self):
        self.propose(self.descriptor())
        layout, image = self.layout()
        with mock.patch.object(package, "local_health", return_value=({}, {"status": "blocked"})):
            result = package.request(self.app, environment="rehearsal", action="verify", layout=layout, image=image)
        self.assertEqual(result["status"], "blocked")


class Foundation(Fixture):
    def config(self, component="network", **updates):
        value = {"mode": "create", "component": component, "workspace": str(self.bootstrap), "name": "founder",
                 "region": "us-phoenix-1", "profile": "DEFAULT", "auth": "security_token",
                 "tenancy_id": "ocid1.tenancy.oc1..synthetictenancy"}
        value.update({"network": {"vcn_cidr": "10.88.0.0/16"}, "registry": {},
                      "compartments": {"parent_compartment_id": "ocid1.compartment.oc1..syntheticparent", "home_region": "us-ashburn-1"},
                      "state": {"state_compartment_id": STATE, "namespace": "syntheticnamespace", "state_key": "rehearsal/main.tfstate",
                                "workspace_key_prefix": "rehearsal/workspaces"},
                      "access": {"state_compartment_id": STATE, "home_region": "us-ashburn-1", "developer_group_id": "ocid1.group.oc1..syntheticgroup",
                                 "access_role": "foundation-provisioner", "registry_name": "synthetic-app", "state_bucket_name": "synthetic-state",
                                 "administrator_profile": "ADMINISTRATOR", "administrator_auth": "security_token"}}[component])
        value.update(updates)
        return value

    def propose(self, value):
        return foundation.request(self.app, environment="rehearsal", action="propose",
                                  config=self.private_json("foundation.json", value))

    def prepare(self, component="network", **updates):
        proposal = self.propose(self.config(component, **updates))
        self.assertEqual(proposal["status"], "review")
        result = foundation.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        return proposal, result

    def output(self, proposal, component="network", **updates):
        target = {"network": {"compartment_id": COMPARTMENT, "vcn_id": "ocid1.vcn.oc1.phx.syntheticvcn",
                              "app_subnet_id": "ocid1.subnet.oc1.phx.syntheticprivate", "lb_subnet_id": "ocid1.subnet.oc1.phx.syntheticpublic",
                              "app_private_ip": "10.88.2.10"}, "registry": {"compartment_id": COMPARTMENT, "registry_id": "ocid1.containerrepo.oc1.phx.syntheticrepo"},
                  "compartments": {"compartment_id": "ocid1.compartment.oc1..newsyntheticapp"}, "state": {}, "access": {}}[component]
        value = {"schema": "oci-kit-foundation-output/1", "environment": "rehearsal", "component": component,
                 "request_sha256": proposal["sha256"], "region": "us-phoenix-1", "target": target,
                 "private": {"state_compartment_id": STATE} if component == "compartments" else {}}
        if component == "state":
            value["backend"] = {"region": "us-phoenix-1", "namespace": "syntheticnamespace", "bucket": "founder-rehearsal-tfstate",
                                "key": "rehearsal/main.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        if component == "access":
            value["region"] = "us-ashburn-1"
        value.update(updates)
        return self.private_json("outputs.json", {"foundation": {"sensitive": False, "type": ["object", {}], "value": value}})

    def test_each_component_is_separate_private_and_cloud_is_never_run(self):
        before = (self.app / "main.py").read_bytes()
        for component in foundation.COMPONENTS:
            proposal, result = self.prepare(component)
            folder = Path(result["directory"])
            self.assertTrue(folder.is_relative_to(self.bootstrap))
            self.assertEqual(result["cloud"], "not_checked")
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
            variables = json.loads((folder / "terraform.tfvars.json").read_text())
            self.assertEqual(variables["request_sha256"], proposal["sha256"])
            self.assertEqual(variables["auth"], "SecurityToken")
            self.assertEqual((folder / "terraform.tfvars.json").stat().st_mode & 0o777, 0o600)
            if component != "access":
                self.assertNotIn("oci_identity_policy", (folder / "main.tf").read_text())
        self.assertEqual((self.app / "main.py").read_bytes(), before)

    def test_generated_commands_bind_each_foundation_target_without_applying(self):
        resource_types = {"compartments": "oci_identity_compartment", "network": "oci_core_vcn",
                          "state": "oci_objectstorage_bucket", "registry": "oci_artifacts_container_repository", "access": "oci_identity_policy"}
        for component in foundation.COMPONENTS:
            with self.subTest(component=component):
                _, result = self.prepare(component)
                folder = Path(result["directory"])
                variables = json.loads((folder / "terraform.tfvars.json").read_text())
                resource = resource_types[component]
                evaluated = {"format_version": "1.2", "terraform_version": "1.16.6",
                             "variables": {key: {"value": value} for key, value in variables.items()},
                             "resource_changes": [{"address": resource + ".synthetic", "type": resource,
                                                   "name": "synthetic", "change": {"actions": ["create"]}}]}
                plan = self.private_json(component + "-plan.json", evaluated)
                log = self.root / (component + "-terraform.log")
                child_env = {"PATH": os.environ["PATH"], "HOME": str(self.root),
                             "TF_BIN": str(ROOT / "tests/fixtures/fake_terraform.py"),
                             "FAKE_TF_PLAN_JSON": str(plan), "FAKE_TF_LOG": str(log)}
                completed = subprocess.run(result["plan_command"], env=child_env, capture_output=True,
                                           text=True, timeout=30, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                summary = json.loads((folder / ".gate/plan-summary.json").read_text())
                expected = {"compartments": self.config(component).get("parent_compartment_id"),
                            "state": STATE}.get(component, COMPARTMENT)
                self.assertEqual(summary["target"]["compartment_ocid"], expected)
                self.assertEqual(summary["target"]["region"], "us-ashburn-1" if component == "access" else "us-phoenix-1")
                self.assertEqual(summary["target"]["profile"], "ADMINISTRATOR" if component == "access" else "DEFAULT")
                self.assertEqual(summary["target"]["auth"], "SecurityToken")
                self.assertIsNone(summary["project_environment"])
                self.assertNotIn("parent_compartment_ocid", variables)
                invocations = log.read_text().splitlines()
                self.assertTrue(any(line.startswith("init ") for line in invocations))
                self.assertTrue(any(line.startswith("plan ") for line in invocations))
                self.assertFalse(any(line.startswith(("apply", "APPLIED")) for line in invocations))
                if component == "compartments":
                    self.assertEqual(summary["target"]["home_region"], "us-ashburn-1")
                    evaluated["variables"]["compartment_ocid"]["value"] = self.config()["tenancy_id"]
                    plan.write_text(json.dumps(evaluated))
                    rejected = subprocess.run(result["plan_command"], env=child_env, capture_output=True,
                                              text=True, timeout=30, check=False)
                    self.assertEqual(rejected.returncode, 3)
                    self.assertIn("dedicated non-root compartment", rejected.stderr)
                    self.assertFalse((folder / ".gate/plan-summary.json").exists())
                    self.assertNotIn("APPLIED", log.read_text())

    def test_invalid_gate_selections_refuse_before_scaffolding(self):
        cases = [("network", {"profile": "p" * 65}, "profile"),
                 ("network", {"region": "us-phoenix-extra-1"}, "region"),
                 ("compartments", {"home_region": "us-ashburn-extra-1"}, "home_region"),
                 ("network", {"tenancy_id": "ocid1.tenancy.oc1.phx.synthetictenancy"}, "tenancy_id"),
                 ("compartments", {"parent_compartment_id": self.config()["tenancy_id"]}, "parent_compartment_id"),
                 ("compartments", {"parent_compartment_id": "ocid1.compartment.oc1.."}, "parent_compartment_id"),
                 ("state", {"state_compartment_id": self.config()["tenancy_id"]}, "state_compartment_id")]
        for component, changes, field in cases:
            with self.subTest(field=field, changes=changes), self.assertRaises(foundation.FoundationError) as caught:
                self.propose(self.config(component, **changes))
            self.assertIn(field, caught.exception.recovery)
            self.assertEqual(list(self.bootstrap.iterdir()), [])
            self.assertFalse((self.private / "foundation-proposal.json").exists())
        proposal = self.propose(self.config(profile="p" * 64))
        self.assertEqual(proposal["status"], "review")
        self.assertEqual(list(self.bootstrap.iterdir()), [])

    def test_environment_compartment_and_bootstrap_roots_cannot_bypass_boundary(self):
        selected = self.selected()
        for reference in ("ocid1.compartment.oc1..", "ocid1.tenancy.oc1..synthetictenancy"):
            with self.subTest(reference=reference), self.assertRaises(foundation.FoundationError):
                foundation.choices(self.config(), dict(selected, target={**selected["target"], "compartment_id": reference}), p)
        other = self.root / "other-project"
        other.mkdir(mode=0o700)
        (other / ".oci-kit").mkdir(mode=0o700)
        nested = other / "bootstrap"
        nested.mkdir(mode=0o700)
        for wrong in (self.app, self.root, other, nested):
            with self.subTest(workspace=wrong), self.assertRaises(foundation.FoundationError):
                self.propose(self.config(workspace=str(wrong)))
        self.assertEqual(list(self.bootstrap.iterdir()), [])

    def test_output_handoff_maps_environment_and_backs_up_without_approvals(self):
        proposal, _ = self.prepare()
        original = (self.private / "environment.json").read_bytes()
        result = foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal))
        self.assertEqual(self.selected()["target"]["app_private_ip"], "10.88.2.10")
        self.assertFalse(result["approvals_imported"])
        self.assertEqual(result["evidence_scope"], "owner-supplied-output")
        self.assertEqual(result["cloud"], "not_checked")
        self.assertIn(original, [path.read_bytes() for path in self.private.glob("environment-backup-*.json")])
        with self.assertRaises(ValueError):
            foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal))

    def test_access_roles_remain_separate_and_do_not_retarget_to_administrator_or_home_region(self):
        original = (self.private / "environment.json").read_bytes()
        for role, extra in (("foundation-provisioner", {}), ("observer", {}),
                            ("app-deployer", {"certificate_id": "ocid1.certificate.oc1.phx.syntheticcert"}),
                            ("image-publisher", {}), ("state-operator", {"state_key": "rehearsal/main.tfstate"})):
            with self.subTest(role=role):
                proposal, prepared = self.prepare("access", access_role=role, **extra)
                variables = json.loads((Path(prepared["directory"]) / "terraform.tfvars.json").read_bytes())
                self.assertEqual(variables["role"], role)
                self.assertEqual(variables["region"], "us-ashburn-1")
                self.assertEqual(variables["config_file_profile"], "ADMINISTRATOR")
                output = self.output(proposal, "access")
                result = foundation.request(self.app, environment="rehearsal", action="handoff", outputs=output)
                self.assertEqual(result["evidence_scope"], "owner-supplied-output")
                self.assertFalse(result["approvals_imported"])
                self.assertEqual((self.private / "environment.json").read_bytes(), original)
        stages = json.loads((self.private / "foundation-stages.json").read_bytes())
        self.assertEqual(len(stages), 5)

    def test_access_role_required_inputs_and_injection_refuse(self):
        for role, required in (("state-operator", "state_key"), ("app-deployer", "certificate_id")):
            result = self.propose(self.config("access", access_role=role))
            self.assertEqual(result["status"], "blocked")
            self.assertIn(required, result["missing"])
        for changes in ({"access_role": "administrator"}, {"developer_group_id": "ocid1.tenancy.oc1..synthetic"},
                        {"registry_name": "wild*"}, {"state_bucket_name": "name'"}, {"administrator_profile": "x" * 65}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.propose(self.config("access", **changes))

    def test_access_roles_cannot_target_another_selected_backend_or_certificate(self):
        selected = self.selected()
        certificate = "ocid1.certificate.oc1.phx.syntheticcert"
        env.configure(self.app, name="rehearsal", target=dict(selected["target"], certificate_id=certificate),
            backend={"region": "us-phoenix-1", "namespace": "syntheticnamespace", "bucket": "synthetic-state",
                     "key": "rehearsal/main.tfstate", "workspace_key_prefix": "rehearsal/workspaces"})
        cases = [{"access_role": "state-operator", "state_key": "production/other.tfstate"},
                 {"state_bucket_name": "other-state"},
                 {"access_role": "app-deployer", "certificate_id": "ocid1.certificate.oc1.phx.othercert"},
                 {"access_role": "state-operator", "state_key": "rehearsal/*"}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.propose(self.config("access", **changes))
        result = self.propose(self.config("access", access_role="state-operator", state_key="rehearsal/main.tfstate"))
        self.assertEqual(result["status"], "review")

    def test_state_output_maps_exact_backend_and_preserves_records(self):
        proposal, _ = self.prepare("state")
        result = foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal, "state"))
        self.assertEqual(self.selected()["backend"]["bucket"], "founder-rehearsal-tfstate")
        self.assertEqual(result["previous_evidence"], "stale")
        self.assertEqual(json.loads((self.private / "state.json").read_text())["records"], {})

    def test_compartment_output_remembers_state_selection_for_next_component(self):
        proposal, _ = self.prepare("compartments")
        foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal, "compartments"))
        next_choice = {"mode": "create", "component": "state", "namespace": "syntheticnamespace",
                       "state_key": "rehearsal/main.tfstate", "workspace_key_prefix": "rehearsal/workspaces"}
        report = self.propose(next_choice)
        self.assertEqual(report["status"], "review")
        self.assertFalse(report["missing"])

    def test_missing_inputs_are_bundled_and_unknowns_remain_unknown(self):
        report = self.propose({"mode": "create", "component": "state"})
        self.assertEqual(report["status"], "blocked")
        self.assertIn("namespace", report["missing"])
        self.assertIn("state_compartment_id", report["missing"])
        report = foundation.request(self.app, environment="rehearsal")
        self.assertEqual(report["checks"]["inherited_iam_isolation"], "unknown")
        self.assertIn("certificate_renewal_owner", report["missing"])
        self.assertIn("authorized-tenancy-administrator", json.dumps(report))

    def test_wrong_environment_stale_output_sensitive_extra_fields_refuse(self):
        proposal, _ = self.prepare()
        for changes in ({"environment": "production"}, {"request_sha256": "f" * 64}, {"region": "us-ashburn-1"},
                        {"target": {"token": "synthetic"}}, {"private": {"credential": "synthetic"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal, **changes))
        env.configure(self.app, name="rehearsal", target={**self.selected()["target"], "profile": "reviewed-profile"})
        with self.assertRaises(ValueError):
            foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal))

    def test_changed_source_cannot_supply_handoff(self):
        proposal, result = self.prepare()
        (Path(result["directory"]) / "main.tf").write_text("resource \"unexpected\" \"resource\" {}")
        with self.assertRaises(ValueError):
            foundation.request(self.app, environment="rehearsal", action="handoff", outputs=self.output(proposal))

    def test_bootstrap_inside_app_symlinks_unsafe_permissions_and_source_role_refuse(self):
        nested = self.app / "bootstrap"
        nested.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            self.propose(self.config(workspace=str(nested)))
        self.bootstrap.chmod(0o755)
        with self.assertRaises(ValueError):
            self.propose(self.config())
        self.bootstrap.chmod(0o700)
        linked = self.root / "linked"
        linked.symlink_to(self.bootstrap, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self.propose(self.config(workspace=str(linked)))
        with self.assertRaises(ValueError):
            foundation.request(self.app, environment=None)
        env.create(self.app, name="source", role="source", infrastructure=None)
        with self.assertRaises(ValueError):
            foundation.request(self.app, environment="source")

    def test_private_state_boundary_backend_overlap_and_secrets_refuse(self):
        for changes in ({"state_compartment_id": COMPARTMENT}, {"state_key": "same.tfstate", "workspace_key_prefix": "same.tfstate/child"},
                        {"token": "synthetic"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.propose(self.config("state", **changes))
        for cidr in ("0.0.0.0/16", "203.0.0.0/16", "10.0.0.0/24"):
            with self.assertRaises(ValueError):
                self.propose(self.config(vcn_cidr=cidr))

    def test_reuse_is_reviewed_and_never_claims_security(self):
        original = self.selected()
        proposal = self.propose({"mode": "reuse", "target": original["target"],
                                "certificate": {"hostname": "app.example.invalid", "renewal_owner": "operator", "ownership": "unverified"}})
        result = foundation.request(self.app, environment="rehearsal", action="prepare", approve=proposal["sha256"])
        self.assertEqual(result["mode"], "reuse")
        self.assertEqual(result["cloud"], "not_checked")
        self.assertFalse(result["approvals_imported"])


if __name__ == "__main__":
    unittest.main()
