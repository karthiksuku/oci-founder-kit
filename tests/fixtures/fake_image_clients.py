#!/usr/bin/env python3
"""Local fake Docker/OCI clients for image publication tests; no network calls."""

import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_IMAGE_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
client = Path(sys.argv[0]).name
with Path(os.environ["FAKE_IMAGE_LOG"]).open("a") as log:
    log.write(json.dumps({"client": client, "args": args,
                          "endpoint_override": os.environ.get("OCI_CLI_ENDPOINT")}) + "\n")


def output(value):
    print(json.dumps(value))


def fail():
    print("SYNTHETIC-CLIENT-SECRET")
    print("SYNTHETIC-CLIENT-SECRET", file=sys.stderr)
    raise SystemExit(1)


if state.get("fail") and args[:len(state["fail"])] == state["fail"]:
    fail()
if state.get("oversized") and args[:len(state["oversized"])] == state["oversized"]:
    print("X" * 2_100_000)
    raise SystemExit(0)

if client == "docker":
    if args[:2] == ["image", "inspect"]:
        data = dict(state["image"])
        if state.get("tag_swapped") and args[-1].endswith(":" + state["tag"]):
            data["id"] = "sha256:" + "f" * 64
        output(data)
    elif args[:2] == ["image", "tag"]:
        state["tagged"] = args[-1]
        if state.get("race"):
            state["existing"] = True
        if state.get("swap_on_tag"):
            state["tag_swapped"] = True
        state_path.write_text(json.dumps(state))
    elif args[:2] == ["image", "push"]:
        state["pushed"] = True
        state_path.write_text(json.dumps(state))
        if state.get("push_partial_failure"):
            fail()
        if not state.get("no_push_digest"):
            print(state["tag"] + ": digest: " + state["digest"] + " size: 1234")
    elif args[:3] == ["manifest", "inspect", "--verbose"]:
        data = {"Descriptor": {"digest": state["digest"], "platform": {
            "os": state["image"]["os"], "architecture": state["image"]["architecture"],
            "variant": state["image"]["variant"]}},
            "SchemaV2Manifest": {"schemaVersion": 2, "config": {"digest": state["image"]["id"]}}}
        if state.get("wrong_manifest"):
            data["SchemaV2Manifest"]["config"]["digest"] = "sha256:" + "e" * 64
        if state.get("wrong_platform"):
            data["Descriptor"]["platform"]["architecture"] = "arm64"
        if state.get("manifest_list"):
            data = [data]
        if state.get("oci_manifest"):
            data["OCIManifest"] = data.pop("SchemaV2Manifest")
        output(data)
    else:
        fail()
elif client == "oci":
    if args[:4] == ["artifacts", "container", "repository", "get"]:
        output({"data": state["repository"]})
    elif args[:3] == ["os", "ns", "get"]:
        output({"data": state.get("namespace", "syntheticnamespace")})
    elif args[:3] == ["iam", "region", "list"]:
        output({"data": state.get("regions", [{"name": "ap-melbourne-1", "key": "MEL"}])})
    elif args[:4] == ["artifacts", "container", "image", "list"]:
        if state.get("bad_list"):
            output({"data": None})
        else:
            output({"data": {"items": [{}] if state.get("existing") or state.get("pushed") else []}})
    elif args[:4] == ["artifacts", "container", "image", "lookup"]:
        if not state.get("pushed"):
            fail()
        repo = state["repository"]
        data = {"id": "ocid1.containerimage.oc1.ap-melbourne-1.syntheticimage",
                "repository-id": repo["id"], "repository-name": repo["display-name"],
                "compartment-id": repo["compartment-id"], "lifecycle-state": "AVAILABLE",
                "digest": "sha256:" + "d" * 64 if state.get("wrong_remote") else state["digest"]}
        if state.get("lookup_identity_mismatch") and "@sha256:" in args[args.index("--image-uri") + 1]:
            data["id"] = "ocid1.containerimage.oc1.ap-melbourne-1.otherimage"
        output({"data": data})
    else:
        fail()
else:
    fail()
