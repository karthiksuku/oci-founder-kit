"""OCI auto-prompt is enabled by variable presence, including the value False."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location("test_cli_" + Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CliEnvironment(unittest.TestCase):
    def test_workload_doctor_removes_auto_prompt_and_ambient_overrides(self):
        readiness = load("scripts/readiness.py")
        with mock.patch.dict(os.environ, {"OCI_CLI_AUTO_PROMPT": "False", "OCI_CLI_PROFILE": "unselected"}), \
                mock.patch.object(readiness.subprocess, "run") as run:
            readiness.safe_runner(["oci", "iam", "region-subscription", "list"])
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("OCI_CLI_AUTO_PROMPT", environment)
        self.assertNotIn("OCI_CLI_PROFILE", environment)
        self.assertIn("--no-retry", run.call_args.args[0])

    def test_legacy_doctor_does_not_inherit_interactive_mode(self):
        doctor = load("skills/oci-ready/scripts/oci_doctor.py")
        with mock.patch.dict(os.environ, {"OCI_CLI_AUTO_PROMPT": "False"}), \
                mock.patch.object(doctor.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout='{"data": []}')) as run:
            status, value = doctor.run_json(["oci", "iam", "region-subscription", "list"])
        self.assertEqual(status, "passed")
        self.assertEqual(value, {"data": []})
        self.assertNotIn("OCI_CLI_AUTO_PROMPT", run.call_args.kwargs["env"])

    def test_observation_client_does_not_reintroduce_auto_prompt(self):
        operations = load("scripts/operations.py")
        client = operations.Client.__new__(operations.Client)
        client.check = mock.Mock()
        client.requests, client.deadline = 0, time.monotonic() + 120
        client.binary = {"path": "oci", "sha256": "a" * 64}
        client.target = {"region": "us-phoenix-1", "profile": "selected", "auth": "api_key"}
        client.config_file = Path("/synthetic/private-config")
        run = mock.Mock(return_value=b'{"data": {}}')
        client.files = SimpleNamespace(run=run, parse=json.loads)
        with mock.patch.dict(os.environ, {"OCI_CLI_AUTO_PROMPT": "False", "OCI_CLI_PROFILE": "unselected"}):
            self.assertEqual(client(["iam", "region-subscription", "list"]), {"data": {}})
        environment = run.call_args.kwargs["environment"]
        self.assertNotIn("OCI_CLI_AUTO_PROMPT", environment)
        self.assertNotIn("OCI_CLI_PROFILE", environment)
        self.assertIn("selected", run.call_args.args[1])
        self.assertEqual(client.check.call_count, 2)

    def test_image_gate_default_runner_removes_prompt_for_actual_child(self):
        gate = load("skills/oci-deploy/scripts/image_gate.py")
        with mock.patch.dict(os.environ, {"OCI_CLI_AUTO_PROMPT": "False"}):
            result = gate.run({"path": sys.executable}, ["-c", "import os; print('OCI_CLI_AUTO_PROMPT' in os.environ)"], timeout=5)
        self.assertEqual(result.strip(), b"False")


if __name__ == "__main__":
    unittest.main()
