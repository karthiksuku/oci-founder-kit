"""Allowlisted support bundle. No account, application, hostname or log export."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def request(project, *, environment, write=False):
    spec = importlib.util.spec_from_file_location("oci_support_common", ROOT / "scripts/kit_common.py")
    common = importlib.util.module_from_spec(spec); spec.loader.exec_module(common)
    p = common.project_module()
    common.select(project, environment, required=True)
    registry = p.helper("capabilities").registry()
    version = p.helper("install").release_metadata(ROOT)["kit_version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.]+)?", version):
        raise ValueError("Invalid kit version.")
    with p.Store(project, environment=environment, write=write) as store:
        view = p.helper("dashboard").view(store, p)
        now = int(time.time())
        report = {"schema": "oci-kit-support/1", "kit_version": version,
                  "python_version": ".".join(map(str, sys.version_info[:3])),
                  "platform": "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "unverified",
                  "capabilities": [{"id": row["id"], "evidence": row["evidence"]} for row in registry["capabilities"]],
                  "error_codes": [], "observations": [], "uploaded": False}
        for schema, item in view["observations"].items():
            report["observations"].append({"schema": schema, "status": item.get("status", "owner-recorded"),
                                          "evidence_class": item.get("mode") if item.get("mode") in {"live-read-only", "injected-test-client"} else "private-local-report",
                                          "age_seconds": max(0, now - item["observed_at"])})
        if view["stale_reports"]:
            report["error_codes"].append("EVIDENCE_REQUIRED")
        if view["unreadable_reports"]:
            report["error_codes"].append("UNSAFE_INPUT")
        result = {"schema": "oci-kit-support-result/1", "status": "ready", "preview": report, "uploaded": False}
        if write:
            name = "support-" + uuid.uuid4().hex + ".json"
            p.helper("environments").put(store.fd, name, p.canonical(report) + b"\n")
            os.fsync(store.fd)
            result["path"] = f".oci-kit/environments/{environment}/{name}"
        return result
