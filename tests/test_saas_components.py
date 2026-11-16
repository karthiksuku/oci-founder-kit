"""Explicit worker role binding and isolation; no OCI calls or credentials."""
import copy
import json
from pathlib import Path
import shutil
import unittest

import test_environment_gate as fixtures
BACKEND, TARGET = fixtures.BACKEND, fixtures.TARGET
import environment_gate
import named_workload
import image_gate


class SaaSComponents(unittest.TestCase):
    setUp = fixtures.EnvironmentGate.setUp
    tearDown = fixtures.EnvironmentGate.tearDown
    restore_env = fixtures.EnvironmentGate.restore_env
    write_json = fixtures.EnvironmentGate.write_json

    def worker(self):
        self.worker_stack = self.project / "worker"
        self.worker_stack.mkdir()
        for source in (environment_gate.ROOT / "blueprints/saas-essentials/terraform").glob("*.tf"):
            shutil.copyfile(source, self.worker_stack / source.name)
        (self.worker_stack / "backend.tf.json").write_text('{"terraform":{"backend":{"oci":{}}}}')
        self.worker_backend = dict(BACKEND, key="rehearsal/worker.tfstate", workspace_key_prefix="rehearsal/worker-workspaces")
        self.worker_target = {**{key: TARGET[key] for key in ("region", "profile", "auth", "ocpus", "memory_gbs")},
                              "compartment_id": "ocid1.compartment.oc1..worker", "image_digest": "sha256:" + "b" * 64}
        self.components = {"worker": {"blueprint": "saas-essentials", "infrastructure": "worker", "target": self.worker_target,
                           "backend": {key: self.worker_backend[key] for key in environment_gate.BACKEND_FIELDS}}}
        self.env.configure(self.project, name="rehearsal", target=TARGET, components=self.components)
        return environment_gate.select(self.worker_stack, project=self.project, environment="rehearsal", backend=self.worker_backend)

    def test_explicit_worker_binding_and_parent_hash(self):
        selected = self.worker()
        self.assertEqual(selected["component_role"], "worker")
        self.assertEqual(selected["target"], self.worker_target)
        self.assertEqual(selected["web_compartment_id"], TARGET["compartment_id"])
        with self.assertRaises(image_gate.ImageGateError):
            environment_gate.select(self.worker_stack, backend=self.worker_backend)
        with self.assertRaises(image_gate.ImageGateError):
            environment_gate.select(self.worker_stack, project=self.project, environment="production", backend=self.worker_backend)
        self.env.configure(self.project, name="rehearsal", target=dict(TARGET, port=9090))
        with self.assertRaises(image_gate.ImageGateError):
            environment_gate.recheck(self.worker_stack, selected, self.worker_backend)

    def test_compartment_state_and_stack_collisions_refused(self):
        self.worker()
        for field, value in (("target", dict(self.worker_target, compartment_id=TARGET["compartment_id"])),
                             ("backend", {key: BACKEND[key] for key in environment_gate.BACKEND_FIELDS}),
                             ("infrastructure", "rehearsal/nested")):
            candidate = copy.deepcopy(self.components); candidate["worker"][field] = value
            with self.assertRaises(ValueError):
                self.env.configure(self.project, name="rehearsal", target=TARGET, components=candidate)

    def test_function_component_is_not_enabled_by_adding_config(self):
        self.worker()
        candidate = {"function": self.components["worker"]}
        with self.assertRaises(ValueError):
            self.env.configure(self.project, name="rehearsal", target=TARGET, components=candidate)

    def test_modified_worker_infrastructure_is_refused(self):
        self.worker()
        with (self.worker_stack / "container.tf").open("a") as stream:
            stream.write('\nresource "oci_core_instance" "unreviewed" {}\n')
        with self.assertRaises(image_gate.ImageGateError):
            environment_gate.select(self.worker_stack, project=self.project, environment="rehearsal", backend=self.worker_backend)

    def worker_plan(self):
        plan = json.loads((self.tmp / "plan.json").read_text())
        plan["variables"]["name"] = {"value": "rehearsal"}
        plan["variables"]["web_compartment_ocid"] = {"value": TARGET["compartment_id"]}
        resources, config = [], []
        for kind, name in (("oci_container_instances_container_instance", "worker"), ("oci_queue_queue", "jobs"),
                           ("oci_core_network_security_group", "worker")):
            values = {"compartment_id": self.worker_target["compartment_id"]}
            if kind == named_workload.CI:
                values["containers"] = [{"image_url": "fixture.ocir.io/fixture/worker@" + self.worker_target["image_digest"]}]
            item = {"address": kind + "." + name, "type": kind, "name": name, "mode": "managed",
                    "provider_name": named_workload.OCI, "values": values}
            resources.append(item)
            config.append({"address": item["address"], "type": kind, "name": name, "mode": "managed", "provider_config_key": "oci"})
        plan["planned_values"] = {"root_module": {"resources": resources}}
        plan["resource_changes"] = [{**{k: v for k, v in item.items() if k != "values"},
            "change": {"actions": ["create"], "before": None, "after": item["values"], "after_unknown": {}}} for item in resources]
        plan["configuration"]["root_module"]["resources"] = config
        return plan

    def test_evaluated_worker_digest_compartment_and_runtime_environment_are_proven(self):
        selected = self.worker(); plan = self.worker_plan()
        proof = named_workload.verify(plan, self.worker_stack, selected, "apply")
        self.assertEqual(proof["component_role"], "worker")
        self.assertEqual(proof["image_digest"], self.worker_target["image_digest"])
        for mutation in ("image", "compartment", "environment"):
            changed = copy.deepcopy(plan)
            if mutation == "image":
                changed["planned_values"]["root_module"]["resources"][0]["values"]["containers"][0]["image_url"] = "fixture.ocir.io/app@" + TARGET["image_digest"]
            elif mutation == "compartment":
                changed["planned_values"]["root_module"]["resources"][1]["values"]["compartment_id"] = TARGET["compartment_id"]
            else:
                changed["variables"]["name"]["value"] = "production"
            with self.assertRaises(image_gate.ImageGateError):
                named_workload.verify(changed, self.worker_stack, selected, "apply")
