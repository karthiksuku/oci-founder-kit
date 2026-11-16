"""One public capability registry, shared by installed help and the website."""
from pathlib import Path
import importlib.util
import json
import re
import argparse

ROOT = Path(__file__).resolve().parents[1]
LEVELS = {"preview", "unverified", "local-tested", "oci-verified"}


def registry():
    spec = importlib.util.spec_from_file_location("oci_capability_project", ROOT / "scripts/project.py")
    p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
    _, fd = p.open_project(ROOT / "docs")
    try:
        value = p.object_at(fd, "capabilities.json")
    finally:
        import os
        os.close(fd)
    if set(value) != {"schema", "checked_on", "entrypoint", "platforms", "capabilities", "versions"} or value["schema"] != "oci-kit-capabilities/1":
        raise ValueError("Invalid public registry.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["checked_on"]):
        raise ValueError("Missing dated evidence.")
    if set(value["versions"]) != {"python_required", "terraform_tested", "oci_provider_tested", "compatibility"}:
        raise ValueError("Missing runtime compatibility scope.")
    seen = set()
    for row in value["capabilities"]:
        if (set(row) != {"id", "title", "summary", "command", "guide", "evidence", "prerequisites", "limitations"}
                or not re.fullmatch(r"[a-z][a-z-]{0,39}", row["id"]) or row["id"] in seen or row["evidence"] not in LEVELS
                or not isinstance(row["command"], list) or not 1 <= len(row["command"]) <= 20
                or any(not isinstance(s, str) or not s or len(s) > 300 or any(ord(c) < 32 for c in s) for s in row["command"])
                or Path(row["guide"]).is_absolute() or ".." in Path(row["guide"]).parts):
            raise ValueError("Invalid capability entry.")
        for key in ("title", "summary", "guide", "evidence"):
            if not isinstance(row[key], str) or not row[key] or len(row[key]) > 500 or any(ord(c) < 32 or c in "|<>" for c in row[key]):
                raise ValueError("Invalid capability text.")
        for key in ("prerequisites", "limitations"):
            if (not isinstance(row[key], list) or not 1 <= len(row[key]) <= 12
                    or any(not isinstance(s, str) or not s or len(s) > 500 or any(ord(c) < 32 or c in "|<>" for c in s) for s in row[key])):
                raise ValueError("Invalid capability guidance.")
        seen.add(row["id"])
    for row in value["platforms"]:
        if row["id"] not in {"linux", "macos", "wsl2"} or row["evidence"] not in LEVELS:
            raise ValueError("Invalid platform evidence.")
    return value


def table(value):
    lines = ["# Capability and platform support", "", "Generated from [capabilities.json](capabilities.json). Evidence checked " + value["checked_on"] + ".", "",
             "An evidence label applies only to the scope described. Local tests do not establish OCI deployment, effective IAM or recovery.", "",
             "| Capability | Evidence | Prerequisites | Limitations |", "|---|---|---|---|"]
    for row in value["capabilities"]:
        lines.append(f"| [{row['title']}](../{row['guide']}) | {row['evidence']} | {'; '.join(row['prerequisites'])} | {'; '.join(row['limitations'])} |")
    lines.extend(["", "| Platform | Evidence | Scope |", "|---|---|---|"])
    for row in value["platforms"]:
        lines.append(f"| {row['id']} | {row['evidence']} | {row['scope']} |")
    lines.extend(["", "| Runtime or compatibility | Reviewed scope |", "|---|---|"])
    for name, version in value["versions"].items():
        lines.append(f"| {name} | {version} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-table", action="store_true")
    args = parser.parse_args()
    value = registry()
    if args.write_table:
        (ROOT / "docs/CAPABILITIES.md").write_text(table(value))
    else:
        print(json.dumps(value, indent=2))
