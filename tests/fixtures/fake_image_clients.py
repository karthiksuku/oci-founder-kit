#!/usr/bin/env python3
"""Local fake Docker/OCI clients for image publication tests; no network calls."""

import json
import hashlib
import os
import sys
from pathlib import Path

state_path = Path(os.environ.get("FAKE_IMAGE_STATE", str(Path(sys.argv[0]).parent / "fake-state.json")))
state = json.loads(state_path.read_text())
args = sys.argv[1:]
client = Path(sys.argv[0]).name
with Path(os.environ.get("FAKE_IMAGE_LOG", str(Path(sys.argv[0]).parent / "fake-log.jsonl"))).open("a") as log:
    log.write(json.dumps({"client": client, "args": args,
                          "endpoint_override": os.environ.get("OCI_CLI_ENDPOINT"),
                          "registry_override": os.environ.get("CONTAINERS_REGISTRIES_CONF")}) + "\n")


def output(value):
    print(json.dumps(value))


def fail():
    print("SYNTHETIC-CLIENT-SECRET")
    print("SYNTHETIC-CLIENT-SECRET", file=sys.stderr)
    raise SystemExit(1)


def remote_image():
    repo = state["repository"]
    tagged = state.get("publication_mode") != "digest-only"
    return {"id": "ocid1.containerimage.oc1.ap-melbourne-1.0.syntheticns1." + "i" * 60,
            "repository-id": repo["id"], "repository-name": repo["display-name"],
            "compartment-id": repo["compartment-id"], "lifecycle-state": "AVAILABLE",
            "digest": "sha256:" + "d" * 64 if state.get("wrong_remote") else state["digest"],
            "display-name": repo["display-name"], "time-created": "2026-01-01T00:00:00Z",
            "freeform-tags": {}, "defined-tags": {}, "system-tags": {},
            "version": state["tag"] if tagged else None,
            "versions": [{"version": state["tag"]}] if tagged else []}


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
elif client == "skopeo":
    if "copy" in args:
        assert args[-1].startswith("docker://") and "@sha256:" in args[-1]
        assert "--preserve-digests" in args and "--dest-tls-verify=true" in args
        raw = (Path(args[-2].removeprefix("dir:")) / "manifest.json").read_bytes()
        assert args[-1].endswith("@sha256:" + hashlib.sha256(raw).hexdigest())
        state["remote_manifest"] = raw.decode()
        state["pushed"] = True
        state["publication_mode"] = "digest-only"
        state_path.write_text(json.dumps(state))
        if state.get("push_partial_failure"):
            fail()
    elif "inspect" in args and "--raw" in args:
        sys.stdout.write("wrong" if state.get("wrong_manifest") else state["remote_manifest"])
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
        if "--image-digest" in args or "--all" not in args:
            fail()
        repo = state["repository"]
        assert args[args.index("--repository-id") + 1] == repo["id"]
        assert args[args.index("--compartment-id") + 1] == repo["compartment-id"]
        if state.get("paging_failure"):
            output({"data": {"items": []}, "opc-next-page": "synthetic-next-page"})
            fail()
        if state.get("bad_list"):
            output({"data": None})
        else:
            summary = remote_image()
            summary.pop("versions")
            data = {"items": state.get("list_items", [summary] if state.get("existing") or state.get("pushed") else [])}
            if state.get("remaining_items"):
                data["remaining-items-count"] = state["remaining_items"]
            result = {"data": data}
            if state.get("next_page"):
                result["opc-next-page"] = "synthetic-next-page"
            output(result)
    elif args[:4] == ["artifacts", "container", "image", "get"]:
        if not state.get("pushed"):
            fail()
        data = remote_image()
        assert args[args.index("--image-id") + 1] == data["id"]
        if state.get("lookup_identity_mismatch"):
            data["id"] = "ocid1.containerimage.oc1.ap-melbourne-1.otherimage"
        if state.get("wrong_remote_tag"):
            data["versions"] = [{"version": "different-tag"}]
        output({"data": data})
    else:
        fail()
else:
    fail()
