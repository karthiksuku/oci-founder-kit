"""Named environments cannot reuse state or silently change an approved target.

Only the existing fake Terraform client runs; no credentials or OCI requests.
"""

import copy
import json
import shutil
import time
import unittest
from unittest import mock

import test_deploy_gate as fixtures
import backend_ops as ops
import environment_gate as binding


BACKEND = {"region": "ap-melbourne-1", "namespace": "fixture_namespace", "bucket": "fixture-state",
           "key": "rehearsal/app.tfstate", "workspace_key_prefix": "rehearsal/workspaces",
           "auth": "APIKey", "config_file_profile": "DEFAULT"}
TARGET = {"region": "ap-melbourne-1", "compartment_id": "ocid1.compartment.oc1..sandbox",
          "profile": "DEFAULT", "auth": "api_key", "image_digest": "sha256:" + "a" * 64,
          "port": 8080, "health_path": "/healthz", "origin": "https://rehearsal.example.invalid",
          "ocpus": 1, "memory_gbs": 4}


class EnvironmentGate(unittest.TestCase):
    run_gate = fixtures.GateTestCase.run_gate
    restore_env = fixtures.GateTestCase.restore_env
    write_json = fixtures.GateTestCase.write_json
    gate_dir = fixtures.GateTestCase.gate_dir
    applied = fixtures.GateTestCase.applied
    apply = fixtures.GateTestCase.apply
    receipts = fixtures.GateTestCase.receipts

    def setUp(self):
        fixtures.GateTestCase.setUp(self)
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.stack.rename(self.project / "rehearsal")
        self.stack = self.project / "rehearsal"
        (self.stack / "main.tf").unlink()
        for source in (fixtures.ROOT / "blueprints/web-container/terraform").glob("*.tf"):
            shutil.copyfile(source, self.stack / source.name)
        (self.stack / "backend.tf.json").write_text(json.dumps(ops.DECLARATION))
        self.config = self.tmp / "backend.json"
        self.config.write_text(json.dumps(BACKEND))
        self.config.chmod(0o600)
        self.env, p = binding.modules()
        with p.Store(self.project, create=True, write=True) as store:
            now = int(time.time())
            store.save({"schema": p.SCHEMA, "task": "migrate", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})
        self.env.create(self.project, name="rehearsal", role="rehearsal", infrastructure="rehearsal",
                        target=TARGET, backend={key: BACKEND[key] for key in binding.BACKEND_FIELDS})
        plan = copy.deepcopy(fixtures.PLAN)
        plan["variables"].update({"auth": {"value": "APIKey"},
            "app_image": {"value": "fixture.ocir.io/fixture/app@" + TARGET["image_digest"]},
            "app_port": {"value": TARGET["port"]}, "health_path": {"value": TARGET["health_path"]},
            "public_origin": {"value": TARGET["origin"]}, "app_ocpus": {"value": 1},
            "app_memory_gbs": {"value": 4}})
        provider = {"name": "oci", "full_name": "registry.terraform.io/oracle/oci",
            "expressions": {name: {"references": ["var." + name]} for name in
                            ("region", "config_file_profile", "tenancy_ocid", "auth")}}
        home = copy.deepcopy(provider)
        home.update(alias="home")
        home["expressions"]["region"] = {"references": ["var.home_region"]}
        evaluated = []
        configured = []
        for kind, name in (("oci_container_instances_container_instance", "app"),
                           ("oci_load_balancer_load_balancer", "web"), ("oci_core_network_security_group", "app")):
            values = {"compartment_id": TARGET["compartment_id"]}
            if kind == "oci_container_instances_container_instance":
                values["containers"] = [{"image_url": "fixture.ocir.io/fixture/app@" + TARGET["image_digest"]}]
            evaluated.append({"address": kind + "." + name, "type": kind, "name": name,
                "mode": "managed", "provider_name": "registry.terraform.io/oracle/oci", "values": values})
            configured.append({"address": kind + "." + name, "type": kind, "name": name,
                "mode": "managed", "provider_config_key": "oci"})
        plan["resource_changes"] = [{**{key: value for key, value in resource.items() if key != "values"},
            "change": {"actions": ["create"], "before": None, "after": resource["values"], "after_unknown": {}}}
            for resource in evaluated]
        plan["planned_values"] = {"root_module": {"resources": evaluated}}
        plan["configuration"] = {"provider_config": {"oci": provider, "oci.home": home},
                                  "root_module": {"resources": configured}}
        self.write_json("plan.json", plan)

    def prepare(self, operation="init", *, selected=True):
        args = ["backend-plan", "--dir", str(self.stack), "--operation", operation]
        if selected:
            args += ["--project", str(self.project), "--environment", "rehearsal"]
        if operation == "init":
            args += ["--backend-config", str(self.config)]
        return self.run_gate(*args)

    def pending(self):
        return json.loads((self.gate_dir / ops.PLAN).read_text())

    def execute(self):
        return self.run_gate("backend-run", "--dir", str(self.stack), "--approve", self.pending()["sha256"])

    def initialize(self):
        self.assertEqual(self.prepare()[0], 0)
        code, _, err = self.execute()
        self.assertEqual(code, 0, err)

    def resource_plan(self):
        self.initialize()
        self.assertEqual(self.prepare("plan")[0], 0)
        code, _, err = self.execute()
        self.assertEqual(code, 0, err)
        return json.loads((self.gate_dir / "plan-summary.json").read_text())

    def config_path(self, name="rehearsal"):
        return self.project / ".oci-kit/environments" / name / "environment.json"

    def test_named_backend_requires_explicit_pair_before_credentials_or_subprocess(self):
        with mock.patch.object(ops.backend_auth, "inspect", side_effect=AssertionError("No credential read")):
            code, _, err = self.prepare(selected=False)
        self.assertEqual(code, 3, err)
        self.assertFalse(self.log.exists())
        code, _, _ = self.run_gate("backend-plan", "--dir", str(self.stack), "--operation", "init",
            "--backend-config", str(self.config), "--project", str(self.project))
        self.assertEqual(code, 3)
        self.assertFalse(self.log.exists())

    def test_local_state_cannot_bypass_named_environment(self):
        (self.stack / "backend.tf.json").unlink()
        for args in ([], ["--project", str(self.project), "--environment", "rehearsal"]):
            code, _, _ = self.run_gate("plan", "--dir", str(self.stack), *args)
            self.assertEqual(code, 3)
        self.assertFalse(self.log.exists())

    def test_unregistered_copy_inside_named_project_cannot_use_legacy_gate(self):
        copied = self.project / "copied-stack"
        copied.mkdir()
        with self.assertRaises(ops.files.ImageGateError):
            binding.select(copied, backend=BACKEND)
        with self.assertRaises(ops.files.ImageGateError):
            binding.select(copied, project=self.project, environment="rehearsal", backend=BACKEND)

    def test_exact_backend_plan_and_resource_receipts_bind_environment(self):
        summary = self.resource_plan()
        selected = summary["project_environment"]
        self.assertEqual(selected["environment"], "rehearsal")
        self.assertEqual(selected["backend"]["key"], BACKEND["key"])
        self.assertEqual(summary["target"]["image_digest"], TARGET["image_digest"])
        code, _, err = self.apply(summary["plan_sha256"])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.applied()), 1)
        self.assertEqual(json.loads(self.receipts()[0].read_text())["project_environment"], selected)
        for receipt in (self.gate_dir / "backend-receipts").glob("*.json"):
            self.assertEqual(json.loads(receipt.read_text())["project_environment"], selected)

    def test_wrong_selected_name_or_root_refused(self):
        for name in ("production", "source"):
            with self.assertRaises(ops.files.ImageGateError):
                binding.select(self.stack, project=self.project, environment=name, backend=BACKEND)
        child = self.stack / "nested"
        child.mkdir()
        with self.assertRaises(ops.files.ImageGateError):
            binding.select(child, project=self.project, environment="rehearsal", backend=BACKEND)
        with self.assertRaises(ops.files.ImageGateError):
            binding.select(child, backend=BACKEND)

    def test_changed_backend_destination_or_auth_refused_offline(self):
        for key, value in (("key", "production/app.tfstate"), ("workspace_key_prefix", "production/workspaces"),
                           ("bucket", "other-state"), ("config_file_profile", "OTHER"), ("auth", "SecurityToken")):
            with self.subTest(key=key), self.assertRaises(ops.files.ImageGateError):
                binding.select(self.stack, project=self.project, environment="rehearsal", backend={**BACKEND, key: value})
        self.assertFalse(self.log.exists())

    def test_changed_configuration_refuses_pending_backend_operation(self):
        self.assertEqual(self.prepare()[0], 0)
        self.env.configure(self.project, name="rehearsal", target={**TARGET, "image_digest": "sha256:" + "b" * 64})
        self.assertEqual(self.execute()[0], 3)
        self.assertFalse(self.log.exists())

    def test_old_unbound_backend_packet_cannot_transfer_to_named_environment(self):
        self.assertEqual(self.prepare()[0], 0)
        packet = self.pending()
        packet["payload"].pop("project_environment")
        packet["sha256"] = ops.files.sha(ops.files.canonical(packet["payload"]))
        (self.gate_dir / ops.PLAN).write_text(json.dumps(packet))
        self.assertEqual(self.execute()[0], 3)
        self.assertFalse(self.log.exists())

    def test_stale_or_unbound_resource_plan_refused_before_apply(self):
        summary = self.resource_plan()
        before = self.log.read_text()
        self.env.configure(self.project, name="rehearsal", target={**TARGET, "origin": "https://changed.example.invalid"})
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        self.assertEqual(self.log.read_text(), before)
        self.env.configure(self.project, name="rehearsal", target=TARGET)
        summary.pop("project_environment")
        (self.gate_dir / "plan-summary.json").write_text(json.dumps(summary))
        self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        self.assertEqual(self.applied(), [])

    def test_actual_plan_target_and_promoted_digest_must_match(self):
        self.initialize()
        original = json.loads((self.tmp / "plan.json").read_text())
        for key, value in (("compartment_ocid", "ocid1.compartment.oc1..other"), ("region", "us-phoenix-1"),
                           ("config_file_profile", "OTHER"), ("auth", "SecurityToken"),
                           ("app_image", "fixture.ocir.io/fixture/app@sha256:" + "b" * 64),
                           ("app_image", "fixture.ocir.io/fixture/app:latest"), ("app_port", 8081),
                           ("public_origin", "https://other.example.invalid")):
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(original)
                changed["variables"][key] = {"value": value}
                self.write_json("plan.json", changed)
                self.assertEqual(self.prepare("plan")[0], 0)
                self.assertEqual(self.execute()[0], 3)
                self.assertFalse((self.gate_dir / "plan-summary.json").exists())
        self.assertEqual(self.applied(), [])

    def test_manual_sibling_collisions_rechecked_at_execution(self):
        self.env.create(self.project, name="production", role="production", infrastructure="production",
            target={**TARGET, "compartment_id": "ocid1.compartment.oc1..production"},
            backend={key: ("production/app.tfstate" if key == "key" else "production/workspaces"
                          if key == "workspace_key_prefix" else BACKEND[key]) for key in binding.BACKEND_FIELDS})
        self.assertEqual(self.prepare()[0], 0)
        path = self.config_path("production")
        original = json.loads(path.read_text())
        for corruption in ("backend", "compartment"):
            changed = copy.deepcopy(original)
            if corruption == "backend":
                changed["backend"]["key"] = BACKEND["key"]
            else:
                changed["target"]["compartment_id"] = TARGET["compartment_id"]
            path.write_text(json.dumps(changed))
            self.assertEqual(self.execute()[0], 3)
            self.assertFalse(self.log.exists())
        path.write_text(json.dumps(original))

    def test_symlink_and_unsafe_private_environment_fail_closed(self):
        path = self.config_path()
        path.chmod(0o644)
        self.assertEqual(self.prepare()[0], 3)
        path.chmod(0o600)
        saved = path.with_suffix(".saved")
        path.rename(saved)
        path.symlink_to(saved)
        self.assertEqual(self.prepare()[0], 3)
        self.assertFalse(self.log.exists())

    def test_per_subprocess_recheck_stops_after_environment_changes(self):
        selected = binding.select(self.stack, project=self.project, environment="rehearsal", backend=BACKEND)
        self.env.configure(self.project, name="rehearsal", target={**TARGET, "port": 8081})
        with mock.patch.object(fixtures.gate.subprocess, "run", side_effect=AssertionError("Must refuse first")):
            with self.assertRaises(fixtures.gate.GateRefused):
                fixtures.gate.run_terraform({"path": "/unused"}, ["apply"], self.stack, self.gate_dir,
                                           backend=BACKEND, project_environment=selected)

    def test_change_after_saved_plan_check_records_refused_apply(self):
        summary = self.resource_plan()
        original = fixtures.gate.run_terraform

        def change_after_show(binary, args, stack, gate, **kwargs):
            output = original(binary, args, stack, gate, **kwargs)
            if args[0] == "show":
                self.env.configure(self.project, name="rehearsal", target={**TARGET, "port": 8081})
            return output

        with mock.patch.object(fixtures.gate, "run_terraform", side_effect=change_after_show):
            self.assertEqual(self.apply(summary["plan_sha256"])[0], 3)
        receipt = json.loads(self.receipts()[0].read_text())
        self.assertEqual(receipt["status"], "refused")
        self.assertFalse(receipt["apply_started"])
        self.assertEqual(self.applied(), [])

    def test_legacy_environment_without_selected_backend_cannot_deploy(self):
        path = self.config_path()
        config = json.loads(path.read_text())
        config.pop("backend")
        path.write_text(json.dumps(config))
        self.assertEqual(self.prepare()[0], 3)
        self.assertFalse(self.log.exists())

    def selected(self):
        return binding.select(self.stack, project=self.project, environment="rehearsal", backend=BACKEND)

    def evaluated_plan(self):
        return json.loads((self.tmp / "plan.json").read_text())

    def proof(self, plan, kind="apply", selected=None):
        return binding.named_workload.verify(plan, self.stack, selected or self.selected(), kind)

    def test_evaluated_resources_cannot_contradict_matching_variables(self):
        self.initialize()
        plan = self.evaluated_plan()
        plan["resource_changes"][0]["change"]["after"]["compartment_id"] = "ocid1.compartment.oc1..unexpected"
        plan["resource_changes"][0]["change"]["after"]["containers"][0]["image_url"] = "fixture/app@sha256:" + "b" * 64
        self.write_json("plan.json", plan)
        self.assertEqual(self.prepare("plan")[0], 0)
        self.assertEqual(self.execute()[0], 3)
        self.assertFalse((self.gate_dir / "plan-summary.json").exists())
        self.assertEqual(self.applied(), [])

    def test_each_evaluated_workload_compartment_and_image_is_required(self):
        original = self.evaluated_plan()
        for index in range(3):
            with self.subTest(resource=index):
                plan = copy.deepcopy(original)
                plan["planned_values"]["root_module"]["resources"][index]["values"]["compartment_id"] = None
                with self.assertRaises(ops.files.ImageGateError):
                    self.proof(plan)
        for image in (None, "fixture/app:latest", "fixture/app@sha256:" + "b" * 64):
            plan = copy.deepcopy(original)
            plan["planned_values"]["root_module"]["resources"][0]["values"]["containers"][0]["image_url"] = image
            with self.subTest(image=image), self.assertRaises(ops.files.ImageGateError):
                self.proof(plan)

    def test_empty_noop_plan_needs_evaluated_container_and_selected_image(self):
        plan = self.evaluated_plan()
        plan["resource_changes"] = []
        self.assertEqual(self.proof(plan)["image_digest"], TARGET["image_digest"])
        without_image = self.selected()
        without_image["target"].pop("image_digest")
        with self.assertRaises(ops.files.ImageGateError):
            self.proof(plan, selected=without_image)
        plan["planned_values"]["root_module"]["resources"] = []
        with self.assertRaises(ops.files.ImageGateError):
            self.proof(plan)

    def test_missing_image_is_refused_before_resource_plan_client(self):
        self.initialize()
        target = dict(TARGET)
        target.pop("image_digest")
        self.env.configure(self.project, name="rehearsal", target=target)
        before = self.log.read_text()
        self.assertEqual(self.prepare("plan")[0], 3)
        self.assertEqual(self.log.read_text(), before)

    def test_provider_sources_refused_before_backend_client_even_with_same_json_references(self):
        path = self.stack / "versions.tf"
        original = path.read_text()
        path.write_text(original.replace("= var.region", '= var.region == "us-ashburn-1" ? "us-phoenix-1" : "us-sanjose-1"'))
        self.assertEqual(self.prepare()[0], 3)
        path.write_text(original)
        for filename, body in (("override.tf", 'provider "oci" { region = "us-phoenix-1" }'),
                               ("custom_override.tf.json", '{"provider":{"oci":{"region":"us-phoenix-1"}}}'),
                               ("extra.tf", 'provider "oci" { alias = "unreviewed" }'),
                               ("module.tf", 'module "other" { source = "./other" }'),
                               ("provisioner.tf", 'resource "terraform_data" "x" { provisioner "local-exec" { command = "false" } }')):
            with self.subTest(filename=filename):
                added = self.stack / filename
                added.write_text(body)
                self.assertEqual(self.prepare()[0], 3)
                added.unlink()
        self.assertFalse(self.log.exists())

    def test_provider_aliases_opaque_expressions_and_unreviewed_resources_are_refused(self):
        original = self.evaluated_plan()
        changes = [lambda p: p["configuration"]["provider_config"]["oci"]["expressions"].update(region={"constant_value": "us-phoenix-1"}),
                   lambda p: p["configuration"]["root_module"]["resources"][0].update(provider_config_key="oci.home"),
                   lambda p: p["configuration"]["provider_config"].update(unreviewed={"full_name": "fixture/foreign"}),
                   lambda p: p["configuration"]["root_module"].update(module_calls={"unreviewed": {}}),
                   lambda p: p["configuration"]["root_module"]["resources"].append({"address": "terraform_data.run", "type": "terraform_data", "provider_config_key": "terraform"})]
        for mutate in changes:
            plan = copy.deepcopy(original)
            mutate(plan)
            with self.assertRaises(ops.files.ImageGateError):
                self.proof(plan)

    def test_unreviewed_oci_resource_cannot_hide_beside_valid_workload(self):
        plan = self.evaluated_plan()
        extra = {"address": "oci_core_instance.extra", "type": "oci_core_instance", "name": "extra", "mode": "managed",
                 "provider_name": "registry.terraform.io/oracle/oci", "values": {"compartment_id": "ocid1.compartment.oc1..unexpected"}}
        plan["planned_values"]["root_module"]["resources"].append(extra)
        plan["configuration"]["root_module"]["resources"].append({"address": extra["address"], "type": extra["type"],
            "name": "extra", "mode": "managed", "provider_config_key": "oci"})
        plan["resource_changes"].append({**{key: value for key, value in extra.items() if key != "values"},
            "change": {"actions": ["create"], "before": None, "after": extra["values"]}})
        with self.assertRaises(ops.files.ImageGateError):
            self.proof(plan)

    def test_changed_infrastructure_source_is_refused_before_client(self):
        source = self.stack / "loadbalancer.tf"
        source.write_text(source.read_text().replace("var.compartment_ocid", '"ocid1.compartment.oc1..unexpected"'))
        self.assertEqual(self.prepare()[0], 3)
        self.assertFalse(self.log.exists())

    def test_existing_child_parent_must_belong_to_verified_environment(self):
        for child_type, name, parent_type, parent_field in (
            ("oci_load_balancer_listener", "https", "oci_load_balancer_load_balancer", "load_balancer_id"),
            ("oci_core_network_security_group_security_rule", "lb_in_https", "oci_core_network_security_group", "network_security_group_id")):
            with self.subTest(child=child_type):
                plan = self.evaluated_plan()
                parent = next(r for r in plan["planned_values"]["root_module"]["resources"] if r["type"] == parent_type)
                parent["values"]["id"] = "ocid1.fixture.oc1..expected"
                parent_change = next(r["change"] for r in plan["resource_changes"] if r["type"] == parent_type)
                parent_change.update(actions=["no-op"], before=copy.deepcopy(parent["values"]), after=copy.deepcopy(parent["values"]))
                child = {"address": child_type + "." + name, "type": child_type, "name": name, "mode": "managed",
                         "provider_name": "registry.terraform.io/oracle/oci", "values": {parent_field: parent["values"]["id"]}}
                plan["planned_values"]["root_module"]["resources"].append(child)
                plan["configuration"]["root_module"]["resources"].append({"address": child["address"], "type": child_type,
                    "name": name, "mode": "managed", "provider_config_key": "oci"})
                change = {"actions": ["update"], "before": copy.deepcopy(child["values"]), "after": copy.deepcopy(child["values"])}
                plan["resource_changes"].append({**{key: value for key, value in child.items() if key != "values"}, "change": change})
                self.assertEqual(self.proof(plan)["resources_checked"], 4)
                change["before"][parent_field] = "ocid1.fixture.oc1..foreign"
                with self.assertRaises(ops.files.ImageGateError):
                    self.proof(plan)
                change["before"] = copy.deepcopy(child["values"])
                change["after"][parent_field] = "ocid1.fixture.oc1..foreign"
                with self.assertRaises(ops.files.ImageGateError):
                    self.proof(plan)
                change["after"][parent_field] = None
                with self.assertRaises(ops.files.ImageGateError):
                    self.proof(plan)
                change["after_unknown"] = {parent_field: True}
                self.assertEqual(self.proof(plan)["resources_checked"], 4)

    def test_update_allows_previous_image_but_never_previous_wrong_compartment(self):
        plan = self.evaluated_plan()
        change = plan["resource_changes"][0]["change"]
        change["actions"] = ["update"]
        change["before"] = copy.deepcopy(change["after"])
        change["before"]["containers"][0]["image_url"] = "fixture/app@sha256:" + "b" * 64
        self.assertEqual(self.proof(plan)["image_digest"], TARGET["image_digest"])
        change["before"]["compartment_id"] = "ocid1.compartment.oc1..other"
        with self.assertRaises(ops.files.ImageGateError):
            self.proof(plan)

    def test_destroy_verifies_actual_prior_state_and_before_values(self):
        plan = self.evaluated_plan()
        plan["prior_state"] = {"values": plan.pop("planned_values")}
        plan["planned_values"] = {"root_module": {}}
        for resource in plan["resource_changes"]:
            change = resource["change"]
            change.update(actions=["delete"], before=change["after"], after=None)
        self.assertEqual(self.proof(plan, "destroy")["image_digest"], TARGET["image_digest"])
        plan["resource_changes"][0]["change"]["before"]["containers"][0]["image_url"] = "fixture/app@sha256:" + "b" * 64
        with self.assertRaises(ops.files.ImageGateError):
            self.proof(plan, "destroy")

    def test_fullstack_home_iam_keeps_explicit_shared_scope(self):
        path = self.config_path()
        config = json.loads(path.read_text())
        config["blueprint"] = "fullstack-container"
        path.write_text(json.dumps(config))
        for source in self.stack.glob("*.tf"):
            source.unlink()
        for source in (fixtures.ROOT / "blueprints/fullstack-container/terraform").glob("*.tf"):
            shutil.copyfile(source, self.stack / source.name)
        plan = self.evaluated_plan()
        plan["variables"].update(tenancy_ocid={"value": "ocid1.tenancy.oc1..fixture"}, home_region={"value": "us-phoenix-1"})
        for kind, name, compartment in (("oci_identity_dynamic_group", "app", "ocid1.tenancy.oc1..fixture"),
                                         ("oci_identity_policy", "app", TARGET["compartment_id"])):
            resource = {"address": kind + "." + name, "type": kind, "name": name, "mode": "managed",
                        "provider_name": "registry.terraform.io/oracle/oci", "values": {"compartment_id": compartment}}
            plan["planned_values"]["root_module"]["resources"].append(resource)
            plan["configuration"]["root_module"]["resources"].append({"address": resource["address"], "type": kind,
                "name": name, "mode": "managed", "provider_config_key": "oci.home"})
            plan["resource_changes"].append({**{key: value for key, value in resource.items() if key != "values"},
                "change": {"actions": ["create"], "before": None, "after": resource["values"]}})
        proof = self.proof(plan)
        self.assertEqual(len(proof["shared_iam_scopes"]), 2)
        self.assertEqual(proof["shared_iam_scopes"][0]["compartment_id"], "ocid1.tenancy.oc1..fixture")
        self.assertEqual(proof["iam_authorization"], "separate-owner-review-required")
        plan["planned_values"]["root_module"]["resources"][-1]["values"]["compartment_id"] = "ocid1.compartment.oc1..unexpected"
        with self.assertRaises(ops.files.ImageGateError):
            self.proof(plan)


if __name__ == "__main__":
    unittest.main()
