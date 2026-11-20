#!/usr/bin/env python3
"""Adapt protected verifier artifacts to the fixed SRE policy. Does not sign or execute tests."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("oci_sre_verifier", Path(__file__).with_name("sre_gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def junit(raw, control):
    """Each required, uniquely named case must be present once and genuinely executed."""
    if len(raw) > 16 * 1024 * 1024 or b"<!" in raw or b"\0" in raw:
        raise ValueError("Require bounded plain UTF-8 JUnit XML, with no DTD or entity declarations.")
    root = ET.fromstring(raw.decode("utf-8"))
    if root.tag not in {"testsuite","testsuites"}:
        raise ValueError("Expected a JUnit test suite.")
    results = {}
    for case in root.iter("testcase"):
        name = case.get("name")
        if (not name or len(name)>180 or case.get("status", "passed") not in {"passed", "run"}
                or case.get("result", "completed") != "completed"
                or any(child.tag not in {"properties", "system-out", "system-err"} for child in case)):
            raise ValueError("Required suite includes an unexecuted, failed, or unsupported result.")
        if name not in gate.REQUIRED[control]:
            continue
        if name in results:
            raise ValueError("Ambiguous test case.")
        results[name] = True
    if set(results) != set(gate.REQUIRED[control]):
        raise ValueError("One or more required named checks were not executed.")
    for suite in root.iter("testsuite"):
        for attr in ("errors", "failures", "skipped", "disabled"):
            if suite.get(attr, "0") != "0":
                raise ValueError("The protected suite was incomplete.")
    return results


def record(challenge, control, artifact, output, observed_at):
    p = gate.project_module()
    private_json = p.helper("kit_common").private_json
    b = private_json(challenge)["binding"]
    if b["policy"] != gate.POLICY or control not in gate.profile_controls(b["profile"]):
        raise ValueError("Unsupported candidate policy/control.")
    if not gate.fresh(observed_at, gate.time.time()):
        raise ValueError("Required execution timestamp is not current.")
    artifact = Path(artifact).absolute()
    _, fd = p.open_project(artifact.parent)
    try:
        raw = p.read_at(fd, artifact.name, private=True, maximum=16*p.LIMIT)
    finally:
        os.close(fd)
    if control in {"security_scan", "oci_registry_scan"}:
        observations = json.loads(raw, object_pairs_hook=p.unique)
        if observations.get("observed_at") != observed_at:
            raise ValueError("Use the scanner's actual observation time.")
    else:
        observations = junit(raw, control)
        if control == "restore":
            root = ET.fromstring(raw)
            for metric in ("recovery_seconds", "data_age_seconds"):
                items = [prop.get("value") for props in root.iter("properties") for prop in props.findall("property")
                         if prop.get("name") == metric]
                if len(items) != 1:
                    raise ValueError("Missing or ambiguous measured restore duration.")
                value = float(items[0])
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid measured duration.")
                observations[metric] = value
    now = gate.time.time()
    sha = hashlib.sha256(raw).hexdigest()
    if gate.indicator({"artifact_sha256":sha,"observed_at":observed_at,"observations":observations},control,b,now,p) != "passed":
        raise ValueError("Evidence does not meet the policy.")
    row = {"schema":"oci-sre-control/1","id":control,"binding_sha256":p.digest(p.canonical(b)),
           "observed_at":observed_at,"raw_artifact_sha256":sha,"observations":observations}
    _, fd = p.open_project(Path(output).absolute())
    try:
        if os.fstat(fd).st_uid != os.getuid() or os.fstat(fd).st_mode & 0o077:
            raise ValueError("Use a private output directory.")
        put = p.helper("environments").put
        put(fd,control+".artifact",raw)
        put(fd,control+".json",p.canonical(row)+b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--challenge",type=Path,required=True)
    cli.add_argument("--control",choices=[*gate.CONTROLS,*gate.MIGRATION],required=True)
    cli.add_argument("--artifact",type=Path,required=True)
    cli.add_argument("--out-dir",type=Path,required=True)
    cli.add_argument("--observed-at",type=int,required=True,help="UTC epoch seconds from the authenticated test run")
    args=cli.parse_args()
    try:
        record(args.challenge,args.control,args.artifact,args.out_dir,args.observed_at)
    except (*gate.SAFE, ET.ParseError):
        raise SystemExit("Control not recorded: inspect artifact identity, named test outcomes, timestamps and private output.") from None
