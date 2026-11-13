#!/usr/bin/env python3
"""A stand-in for the terraform binary, for deploy gate tests.

Behaviour is driven by environment variables so each test controls it:
  FAKE_TF_LOG          file that receives one line per invocation
  FAKE_TF_PLAN_BYTES   content written to the plan file (default "plan-1")
  FAKE_TF_PLAN_JSON    file whose content `show -json <plan>` prints
  FAKE_TF_STATE_JSON   file whose content `show -json` (no plan) prints
  FAKE_TF_FAIL         a subcommand name that should exit 1
  FAKE_TF_FAIL_STATE   when set, `show -json` without a plan exits 1
  FAKE_TF_LEAK         when set, a failing command prints this to stdout only
It never contacts a cloud.
"""

import hashlib
import json
import os
import sys
from pathlib import Path


def log(line):
    path = os.environ.get("FAKE_TF_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def fail(command):
    leak = os.environ.get("FAKE_TF_LEAK")
    if leak:
        sys.stdout.write(f"  + password = {leak}\n")
    else:
        sys.stderr.write(f"Error: {command} failed on purpose\nmore detail\n")
    return 1


def main(argv):
    log(" ".join(argv))
    if any(k.startswith("TF_CLI_ARGS") for k in os.environ):
        log("ENV TF_CLI_ARGS present")
    command = argv[0] if argv else ""
    if command == os.environ.get("FAKE_TF_FAIL"):
        return fail(command)
    if command == "version":
        print(json.dumps({"terraform_version": "1.16.6"}))
        return 0
    if command == "init":
        config_file = next((a.split("=", 1)[1] for a in argv if a.startswith("-backend-config=")), None)
        if config_file:
            config = json.loads(Path(config_file).read_text())
            if os.environ.get("FAKE_TF_WRONG_BACKEND"):
                config["bucket"] = "different-fixture-bucket"
            folder = Path(".terraform")
            folder.mkdir(exist_ok=True)
            (folder / "terraform.tfstate").write_text(json.dumps({"version": 3, "backend": {"type": "oci", "config": config}}))
        return 0
    if command == "plan":
        out = next(a.split("=", 1)[1] for a in argv if a.startswith("-out="))
        Path(out).write_text(os.environ.get("FAKE_TF_PLAN_BYTES", "plan-1"))
        return 0
    if command == "show":
        files = [a for a in argv[1:] if not a.startswith("-")]
        if not files and os.environ.get("FAKE_TF_FAIL_STATE"):
            return fail("show")
        source = os.environ["FAKE_TF_PLAN_JSON"] if files else os.environ["FAKE_TF_STATE_JSON"]
        sys.stdout.write(Path(source).read_text())
        return 0
    if command == "apply":
        plan = Path(argv[-1])
        log("APPLIED " + plan.name + " " + hashlib.sha256(plan.read_bytes()).hexdigest())
        return 0
    sys.stderr.write(f"fake terraform: unsupported {argv}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
