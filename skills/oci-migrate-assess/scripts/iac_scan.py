#!/usr/bin/env python3
"""Discover what an application runs on today and map it to OCI.

Reads a repository (read-only) and inventories cloud resources and
cloud-specific dependencies from:

  - Terraform resources and registry modules (AWS, Azure, Google Cloud)
  - CloudFormation and SAM templates (YAML or JSON)
  - Azure Resource Manager templates and Bicep files
  - Google Cloud Deployment Manager configurations
  - Docker Compose files and Kubernetes manifests (self-hosted services and
    annotations that tie a cluster to its cloud)
  - SDK dependencies in package.json, requirements*.txt, pyproject.toml,
    go.mod, pom.xml, build.gradle and .csproj files

Each finding is mapped to an OCI service through assets/service-map.json,
with the fit (equivalent, partial, gap), what differs and how to migrate.
Unrecognised cloud resources are reported, never silently dropped.

Safety: skips credential filenames, hidden/dependency/build trees and symlinks;
bounds enumeration and reads; omits source attribute values and uses relative
paths. Exit 0 means a report was produced: inspect its coverage, not just the
exit status. Standard library only. Exit 2: invalid input or refused output.

Usage:
  python3 iac_scan.py PATH [--format md|json] [--out FILE] [--map FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "oci-migration-inventory/1"
DEFAULT_MAP = Path(__file__).resolve().parents[1] / "assets" / "service-map.json"
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".terraform", "vendor", "venv", ".venv", "env",
             "__pycache__", "dist", "build", "target", ".next", ".nuxt", "bin", "obj", ".idea", ".vscode",
             "credentials", "keys", "secrets", "private", "certificates", "coverage", "out"}
MAX_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 24 * 1024 * 1024
MAX_FILES = 3000
MAX_ENTRIES = 20000
MAX_DEPTH = 30
SAFE_LABEL = re.compile(r"^[A-Za-z0-9_./@()\[\]+ :,-]{1,240}$")
FIT_ORDER = {"gap": 0, "partial": 1, "equivalent": 2}
WEIGHTS = {"low": 1, "medium": 3, "high": 8}
SIZES = ((12, "S"), (35, "M"), (80, "L"))

TF_BLOCK = re.compile(r'^[ \t]*(resource|module)[ \t]+"([^"]+)"(?:[ \t]+"([^"]+)")?[ \t]*\{', re.M)
TF_ATTR = re.compile(r'^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*"([^"$]*)"[ \t]*$')
CFN_TYPE = re.compile(r'^([ \t]*)Type:[ \t]*["\']?(AWS::[A-Za-z0-9]+::[A-Za-z0-9]+)["\']?[ \t]*$', re.M)
CFN_LOGICAL = re.compile(r'^[ \t]*([A-Za-z0-9]+):[ \t]*$')
CFN_PROP = re.compile(r'^[ \t]*(Engine|Type):[ \t]*["\']?([A-Za-z0-9_.-]+)["\']?[ \t]*$')
BICEP_RES = re.compile(r"^[ \t]*resource[ \t]+(\w+)[ \t]+'([^'@]+)@[^']*'[ \t]*(existing)?", re.M)
BICEP_KIND = re.compile(r"^[ \t]*kind:[ \t]*'([^']*)'", re.M)
DM_TYPE = re.compile(r'^[ \t-]*type:[ \t]*([a-z]+\.v[0-9a-z]+\.[A-Za-z]+)[ \t]*$', re.M)
IMAGE = re.compile(r'^[ \t-]*image:[ \t]*["\']?([^\s"\']+)["\']?[ \t]*$', re.M)
GO_REQ = re.compile(r'^[ \t]*(?:require[ \t]+)?([a-zA-Z0-9.\-]+\.[a-z]{2,}/[^\s]+)[ \t]+v[0-9]', re.M)
POM_DEP = re.compile(r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>", re.S)
GRADLE_DEP = re.compile(r'''(?:implementation|api|compileOnly|runtimeOnly)\s*\(?\s*["']([^:"']+):([^:"']+)''')
NUGET_DEP = re.compile(r'<PackageReference\s+Include="([^"]+)"')
REQ_LINE = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)')

COUPLING = (
    ("aws", "aws-load-balancer-annotation", r"service\.beta\.kubernetes\.io/aws-load-balancer"),
    ("aws", "aws-alb-ingress", r"(alb\.ingress\.kubernetes\.io|ingress\.class:\s*[\"']?alb\b|ingressClassName:\s*[\"']?alb\b)"),
    ("aws", "aws-storage-class", r"(storageClassName:\s*[\"']?(gp2|gp3|io1|io2|st1|sc1)\b|ebs\.csi\.aws\.com|efs\.csi\.aws\.com)"),
    ("aws", "aws-pod-iam-role", r"eks\.amazonaws\.com/role-arn"),
    ("azure", "azure-load-balancer-annotation", r"service\.beta\.kubernetes\.io/azure-"),
    ("azure", "azure-app-gateway-ingress", r"(azure/application-gateway|appgw\.ingress)"),
    ("azure", "azure-storage-class", r"(storageClassName:\s*[\"']?(managed-csi|managed-csi-premium|managed-premium|azurefile|azurefile-csi)\b|disk\.csi\.azure\.com|file\.csi\.azure\.com)"),
    ("azure", "azure-workload-identity", r"azure\.workload\.identity"),
    ("gcp", "gcp-load-balancer-annotation", r"(cloud\.google\.com/load-balancer-type|cloud\.google\.com/neg|networking\.gke\.io)"),
    ("gcp", "gcp-ingress", r"ingress\.class:\s*[\"']?gce"),
    ("gcp", "gcp-storage-class", r"(storageClassName:\s*[\"']?(standard-rwo|premium-rwo|standard-rwx)\b|pd\.csi\.storage\.gke\.io)"),
    ("gcp", "gcp-workload-identity", r"iam\.gke\.io/gcp-service-account"),
)
TF_PREFIX = {"aws_": "aws", "azurerm_": "azure", "google_": "gcp"}


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def load_map(path: Path = DEFAULT_MAP) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _match_when(when: dict, attributes: dict) -> bool:
    return all(re.search(pattern, str(attributes.get(key, "")), re.I) for key, pattern in when.items())


def classify(smap: dict, cloud: str, kind: str, type_: str, attributes: dict | None = None) -> dict | None:
    """Return the matching rule entry ({service, opportunity?}) or None."""
    attributes = attributes or {}
    rules = smap["rules"].get(cloud, {}).get(kind)
    if rules is None:
        return None
    if isinstance(rules, dict):
        value = rules.get(type_.lower() if kind == "arm" else type_)
        if value is None:
            return None
        entries = value if isinstance(value, list) else [{"service": value}]
        return next((e for e in entries if _match_when(e.get("when", {}), attributes)), None)
    for entry in rules:
        if re.search(entry["pattern"], type_) and _match_when(entry.get("when", {}), attributes):
            return entry
    return None


def classify_sdk(smap: dict, ecosystem: str, package: str) -> tuple[str, dict] | None:
    for cloud, kinds in smap["rules"].items():
        for entry in kinds.get("sdk", []):
            if entry["ecosystem"] == ecosystem and re.search(entry["pattern"], package):
                return cloud, entry
    return None


# --------------------------------------------------------------------------
# Parsers: each yields raw items {cloud, kind, type, name, line, attributes}
# --------------------------------------------------------------------------

def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _block_body(text: str, start: int) -> str:
    """Text between the brace at `start` and its matching close, ignoring braces in strings."""
    depth, i, in_string = 0, start, False
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "#" or text.startswith("//", i):
            nl = text.find("\n", i)
            i = len(text) if nl < 0 else nl
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return text[start + 1:]


def _top_level_attributes(body: str) -> dict:
    attributes, depth = {}, 0
    for line in body.splitlines():
        if depth == 0:
            match = TF_ATTR.match(line)
            if match:
                attributes.setdefault(match.group(1), match.group(2))
        stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        depth += stripped.count("{") + stripped.count("[") - stripped.count("}") - stripped.count("]")
        depth = max(depth, 0)
    return attributes


def parse_terraform(text: str) -> Iterator[dict]:
    for match in TF_BLOCK.finditer(text):
        block, first, second = match.groups()
        attributes = _top_level_attributes(_block_body(text, match.end() - 1))
        line = _line_of(text, match.start())
        if block == "module":
            source = attributes.get("source", "")
            for prefix, cloud in (("/aws", "aws"), ("/azurerm", "azure"), ("/google", "gcp")):
                if re.search(re.escape(prefix) + r"(//|$)", source):
                    # URLs can embed access tokens. Only emit public-registry-shaped identifiers.
                    public_source = source if re.fullmatch(
                        r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/(?:aws|azurerm|google)(?://[A-Za-z0-9_/.-]+)?", source
                    ) else "non-registry-module"
                    yield {"cloud": cloud, "kind": "terraform-module", "type": public_source, "name": first,
                           "line": line, "attributes": attributes}
            continue
        cloud = next((c for p, c in TF_PREFIX.items() if first.startswith(p)), None)
        if cloud:
            yield {"cloud": cloud, "kind": "terraform", "type": first, "name": second or "",
                   "line": line, "attributes": attributes}


def is_cloudformation(text: str) -> bool:
    return "AWSTemplateFormatVersion" in text or "AWS::Serverless" in text or bool(CFN_TYPE.search(text))


def parse_cloudformation_yaml(text: str) -> Iterator[dict]:
    matches = list(CFN_TYPE.finditer(text))
    lines = text.splitlines()
    for i, match in enumerate(matches):
        line = _line_of(text, match.start())
        name = ""
        for back in range(line - 2, -1, -1):
            logical = CFN_LOGICAL.match(lines[back])
            if logical and len(lines[back]) - len(lines[back].lstrip()) < len(match.group(1)):
                name = logical.group(1)
                break
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        attributes = {}
        for prop in text[match.end():end].splitlines():
            found = CFN_PROP.match(prop)
            if found:
                attributes.setdefault(found.group(1), found.group(2))
        yield {"cloud": "aws", "kind": "cloudformation", "type": match.group(2), "name": name,
               "line": line, "attributes": attributes}


def parse_cloudformation_json(data: dict, text: str) -> Iterator[dict]:
    for logical, resource in (data.get("Resources") or {}).items():
        if not isinstance(resource, dict) or not str(resource.get("Type", "")).startswith("AWS::"):
            continue
        props = resource.get("Properties") or {}
        attributes = {k: v for k, v in props.items() if isinstance(v, str)} if isinstance(props, dict) else {}
        index = text.find(f'"{logical}"')
        yield {"cloud": "aws", "kind": "cloudformation", "type": resource["Type"], "name": logical,
               "line": _line_of(text, max(index, 0)), "attributes": attributes}


def parse_arm(data: dict, text: str) -> Iterator[dict]:
    def walk(resources: Any, parent: str) -> Iterator[dict]:
        for resource in resources if isinstance(resources, list) else []:
            if not isinstance(resource, dict) or not isinstance(resource.get("type"), str):
                continue
            rtype = resource["type"]
            full = f"{parent}/{rtype}" if parent and "/" not in rtype and "." not in rtype else rtype
            index = text.find(f'"{rtype}"')
            attributes = {"kind": resource["kind"]} if isinstance(resource.get("kind"), str) else {}
            yield {"cloud": "azure", "kind": "arm", "type": full, "name": str(resource.get("name", "")),
                   "line": _line_of(text, max(index, 0)), "attributes": attributes}
            yield from walk(resource.get("resources"), full)
    yield from walk(data.get("resources"), "")


def parse_bicep(text: str) -> Iterator[dict]:
    matches = list(BICEP_RES.finditer(text))
    for i, match in enumerate(matches):
        name, rtype, existing = match.groups()
        if existing or "/" not in rtype:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        kind = BICEP_KIND.search(text, match.end(), end)
        yield {"cloud": "azure", "kind": "arm", "type": rtype, "name": name, "line": _line_of(text, match.start()),
               "attributes": {"kind": kind.group(1)} if kind else {}}


def parse_deployment_manager(text: str) -> Iterator[dict]:
    for match in DM_TYPE.finditer(text):
        yield {"cloud": "gcp", "kind": "deployment-manager", "type": match.group(1), "name": "",
               "line": _line_of(text, match.start()), "attributes": {}}


def normalise_image(image: str) -> str:
    name = image.split("@", 1)[0]
    last = name.rsplit("/", 1)
    if ":" in last[-1]:
        name = name[: len(name) - len(last[-1])] + last[-1].split(":", 1)[0]
    return name[len("library/"):] if name.startswith("library/") else name.removeprefix("docker.io/library/")


def parse_images(text: str) -> Iterator[tuple[str, int]]:
    for match in IMAGE.finditer(text):
        yield normalise_image(match.group(1)), _line_of(text, match.start())


def parse_coupling(text: str) -> Iterator[dict]:
    for cloud, signal, pattern in COUPLING:
        for match in re.finditer(pattern, text):
            yield {"cloud": cloud, "signal": signal, "line": _line_of(text, match.start())}


def parse_dependencies(name: str, text: str) -> Iterator[tuple[str, str]]:
    """Yield (ecosystem, package) pairs from a dependency manifest."""
    if name == "package.json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Expected a package object")
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            group = data.get(section, {})
            if not isinstance(group, dict) or not all(isinstance(value, str) for value in group.values()):
                raise ValueError("Expected dependency name/version pairs")
            for package in sorted(group):
                yield "npm", package
    elif name.startswith("requirements") and name.endswith(".txt"):
        for line in text.splitlines():
            if line.strip() and not line.lstrip().startswith(("#", "-")):
                match = REQ_LINE.match(line)
                if match:
                    yield "pypi", match.group(1).lower()
    elif name == "pyproject.toml":
        data = tomllib.loads(text)
        project = data.get("project", {})
        tool = data.get("tool", {})
        if not isinstance(project, dict) or not isinstance(tool, dict):
            raise ValueError("Expected project/tool tables")
        dependencies = project.get("dependencies", [])
        poetry = tool.get("poetry", {})
        if (not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies)
                or not isinstance(poetry, dict) or not isinstance(poetry.get("dependencies", {}), dict)):
            raise ValueError("Expected dependency list/table")
        for dep in dependencies:
            match = REQ_LINE.match(dep)
            if match:
                yield "pypi", match.group(1).lower()
        for package in poetry.get("dependencies", {}):
            yield "pypi", package.lower()
    elif name == "go.mod":
        for match in GO_REQ.finditer(text):
            yield "go", match.group(1)
    elif name == "pom.xml":
        for group, artifact in POM_DEP.findall(text):
            yield "maven", f"{group.strip()}:{artifact.strip()}"
    elif name in ("build.gradle", "build.gradle.kts"):
        for group, artifact in GRADLE_DEP.findall(text):
            yield "maven", f"{group}:{artifact}"
    elif name.endswith(".csproj"):
        for package in NUGET_DEP.findall(text):
            yield "nuget", package


DEPENDENCY_FILES = re.compile(r"^(package\.json|requirements[\w.-]*\.txt|pyproject\.toml|go\.mod|pom\.xml|"
                              r"build\.gradle(\.kts)?|.+\.csproj)$")


# --------------------------------------------------------------------------
# Walking the tree
# --------------------------------------------------------------------------

def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (name.startswith(".") or name.endswith((".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".tfvars",
                                                  ".tfvars.json", ".tfplan", ".tfplan.json", ".plan.json"))
            or ".tfstate" in name or name.startswith("tfplan") or name == "crash.log"
            or name in {"plan.json", "terraform-plan.json"}
            or any(word in name for word in ("credential", "secret", "private", "certificate"))
            or name in ("id_rsa", "id_ed25519"))


def display_label(value: str) -> str:
    """Keep source metadata from injecting markup or control characters into reports."""
    return (value if not value or (SAFE_LABEL.fullmatch(value) and "](" not in value and "://" not in value)
            else "[unsupported source label omitted]")


def _warn(coverage: dict, message: str) -> None:
    coverage["warnings"].add(message)


def _candidate(path: Path) -> bool:
    return bool(not _is_sensitive(path) and
            (path.suffix.lower() in {".tf", ".bicep", ".json", ".template", ".yaml", ".yml"}
             or DEPENDENCY_FILES.fullmatch(path.name) or _dockerfile(path)))


def _dockerfile(path: Path) -> bool:
    return path.name == "Dockerfile" or path.name.endswith(".Dockerfile") or path.name.startswith("Dockerfile.")


def iter_files(root: Path, coverage: dict | None = None, *, max_entries: int = MAX_ENTRIES,
               max_depth: int = MAX_DEPTH) -> Iterator[Path]:
    """Prune excluded trees before entering them and bound enumeration itself."""
    coverage = coverage if coverage is not None else {"entries_seen": 0, "warnings": set()}
    pending = [(root, 0)]
    exhausted = False
    while pending and not exhausted:
        directory, depth = pending.pop()
        children = []
        try:
            if directory.is_symlink():
                _warn(coverage, "A directory became a symlink; discovery is incomplete.")
                continue
            with os.scandir(directory) as entries:
                for entry in entries:
                    if coverage["entries_seen"] >= max_entries:
                        _warn(coverage, "Entry limit reached; discovery is incomplete.")
                        exhausted = True
                        break
                    coverage["entries_seen"] += 1
                    children.append(entry)
            directories = []
            for entry in sorted(children, key=lambda item: item.name):
                if entry.is_symlink():
                    continue
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() in SKIP_DIRS or _is_sensitive(path):
                        continue
                    if depth >= max_depth:
                        _warn(coverage, "Directory depth limit reached; discovery is incomplete.")
                    else:
                        directories.append((path, depth + 1))
                elif entry.is_file(follow_symlinks=False) and _candidate(path):
                    yield path
            pending.extend(reversed(directories))
        except OSError:
            _warn(coverage, "Unreadable directory skipped; discovery is incomplete.")


def _read(path: Path, coverage: dict, remaining_bytes: int) -> str | None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                _warn(coverage, "Oversized or nonregular candidate skipped; discovery is incomplete.")
                return None
            if info.st_size > remaining_bytes:
                _warn(coverage, "Byte limit reached; discovery is incomplete.")
                return None
            # The descriptor can grow after fstat; never read beyond the remaining budget.
            raw = handle.read(min(MAX_BYTES + 1, remaining_bytes))
            coverage["bytes_read"] += len(raw)
            if len(raw) > MAX_BYTES or len(raw) != info.st_size:
                _warn(coverage, "Changing or oversized candidate skipped; discovery is incomplete.")
                return None
        return raw.decode("utf-8")
    except (OSError, UnicodeError):
        _warn(coverage, "Unreadable candidate skipped; discovery is incomplete.")
        return None


def _scan_file(path: Path, rel: str, smap: dict, inv: dict, text: str) -> None:
    name = path.name
    if _dockerfile(path):
        inv["dockerfiles"].append(rel)
        return
    suffix = path.suffix.lower()
    raw: list[dict] = []
    if suffix == ".tf":
        raw = list(parse_terraform(text))
    elif suffix == ".bicep":
        raw = list(parse_bicep(text))
    elif DEPENDENCY_FILES.match(name):
        _scan_dependencies(name, text, rel, smap, inv)
        return
    elif suffix in (".json", ".template"):
        raw = _scan_json(text)
    elif suffix in (".yaml", ".yml"):
        raw = _scan_yaml(text, rel, smap, inv)
    for item in raw:
        _record(item, rel, smap, inv)


def _scan_json(text: str) -> list[dict]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a configuration object")
    if "deploymentTemplate" in str(data.get("$schema", "")):
        return list(parse_arm(data, text))
    if isinstance(data.get("Resources"), dict):
        return list(parse_cloudformation_json(data, text))
    return []


def _scan_yaml(text: str, rel: str, smap: dict, inv: dict) -> list[dict]:
    if is_cloudformation(text):
        return list(parse_cloudformation_yaml(text))
    is_k8s = bool(re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:", text, re.M))
    is_compose = Path(rel).name.startswith(("docker-compose", "compose")) or bool(re.search(r"^services:", text, re.M))
    if is_k8s or is_compose:
        for image, line in parse_images(text):
            _record_image(image, line, rel, smap, inv)
        if is_k8s:
            for signal in parse_coupling(text):
                inv["coupling"].append({**signal, "file": rel})
        return []
    if re.search(r"^resources:", text, re.M):
        return list(parse_deployment_manager(text))
    return []


def _scan_dependencies(name: str, text: str, rel: str, smap: dict, inv: dict) -> None:
    pairs = list(parse_dependencies(name, text))
    for ecosystem, package in pairs:
        hit = classify_sdk(smap, ecosystem, package)
        if hit:
            cloud, entry = hit
            inv["findings"].append({"cloud": cloud, "kind": "sdk", "type": display_label(package), "name": ecosystem,
                                    "file": rel, "line": _line_of(text, max(text.find(package), 0)),
                                    "attributes": {}, "service": entry["service"]})


def _record(item: dict, rel: str, smap: dict, inv: dict) -> None:
    entry = classify(smap, item["cloud"], item["kind"], item["type"], item["attributes"])
    # Classification can inspect configuration values; the report must never retain them.
    base = {**item, "attributes": {}, "file": rel,
            "type": display_label(item["type"]), "name": display_label(item["name"])}
    if entry is None:
        inv["unmapped"].append({k: base[k] for k in ("cloud", "kind", "type", "file", "line")})
        return
    finding = {**base, "service": entry["service"]}
    if "opportunity" in entry:
        finding["opportunity"] = entry["opportunity"]
    inv["findings"].append(finding)


def _record_image(image: str, line: int, rel: str, smap: dict, inv: dict) -> None:
    for entry in smap["rules"].get("any", {}).get("image", []):
        if re.search(entry["pattern"], image):
            shown = image.rsplit("/", 1)[-1] if image.startswith(("bitnami/", "docker.elastic.co/")) else image
            inv["findings"].append({"cloud": "any", "kind": "image", "type": display_label(shown),
                                    "name": "", "file": rel, "line": line, "attributes": {},
                                    "service": entry["service"], "opportunity": entry.get("opportunity")})
            return


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

def _summarise(inv: dict, smap: dict) -> None:
    clouds: dict[str, int] = {}
    for f in inv["findings"] + inv["unmapped"]:
        if f["cloud"] != "any":
            clouds[f["cloud"]] = clouds.get(f["cloud"], 0) + 1
    inv["source_clouds"] = dict(sorted(clouds.items()))
    grouped: dict[str, dict] = {}
    for f in inv["findings"]:
        sid = f["service"]
        entry = grouped.setdefault(sid, {"id": sid, "count": 0, "found": set()})
        entry["count"] += 1
        entry["found"].add(f["type"])
    services = []
    for sid, entry in grouped.items():
        svc = smap["services"][sid]
        services.append({"id": sid, "count": entry["count"], "found": sorted(entry["found"]),
                         "category": svc["category"], "oci": svc["oci"], "fit": svc["fit"],
                         "complexity": svc["complexity"], "differences": svc["differences"],
                         "migration": svc["migration"], "alternatives": svc.get("alternatives", []),
                         "upstream_skill": svc.get("upstream_skill")})
    services.sort(key=lambda s: (FIT_ORDER[s["fit"]], -WEIGHTS[s["complexity"]], s["category"], s["id"]))
    inv["services"] = services
    score = sum(WEIGHTS[s["complexity"]] for s in services if s["id"] != "self-hosted")
    score += len(inv["coupling"]) + 2 * len(inv["unmapped"])
    size = next((label for limit, label in SIZES if score < limit), "XL")
    inv["effort"] = {"score": score, "size": size,
                     "method": "Heuristic: low 1, medium 3, high 8 per distinct OCI service; +1 per Kubernetes "
                               "coupling; +2 per unrecognised resource. S < 12, M < 35, L < 80, XL above."}


def scan_path(root: Path | str, smap: dict | None = None, *, max_files: int = MAX_FILES,
              max_bytes: int = MAX_TOTAL_BYTES, max_entries: int = MAX_ENTRIES,
              max_depth: int = MAX_DEPTH) -> dict:
    """Scan a directory tree and return the migration inventory."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose a real repository directory")
    if min(max_files, max_bytes, max_entries) < 1 or max_depth < 0:
        raise ValueError("Invalid scan limits")
    root = root.resolve()
    smap = smap or load_map()
    coverage = {"entries_seen": 0, "bytes_read": 0, "warnings": set(),
                "limits": {"files": max_files, "total_bytes": max_bytes, "file_bytes": MAX_BYTES,
                           "entries": max_entries, "depth": max_depth}}
    inv: dict = {"schema": SCHEMA, "root": display_label(root.name), "coverage": coverage,
                 "service_map": {"checked_at": smap.get("checked_at"), "oci_provider": smap.get("oci_provider")},
                 "files_scanned": 0, "findings": [], "unmapped": [], "coupling": [], "dockerfiles": []}
    for path in iter_files(root, coverage, max_entries=max_entries, max_depth=max_depth):
        if inv["files_scanned"] >= max_files:
            _warn(coverage, "File limit reached; discovery is incomplete.")
            break
        if coverage["bytes_read"] >= max_bytes:
            _warn(coverage, "Byte limit reached; discovery is incomplete.")
            break
        text = _read(path, coverage, max_bytes - coverage["bytes_read"])
        if text is None:
            continue
        inv["files_scanned"] += 1
        try:
            _scan_file(path, display_label(path.relative_to(root).as_posix()), smap, inv, text)
        except (ValueError, TypeError, AttributeError, RecursionError):
            _warn(coverage, "Malformed source candidate skipped; discovery is incomplete.")
    for key in ("findings", "unmapped", "coupling"):
        inv[key].sort(key=lambda f: (f["file"], f["line"], f.get("type", f.get("signal", ""))))
    inv["container_ready"] = bool(inv["dockerfiles"])
    _summarise(inv, smap)
    coverage["status"] = "incomplete" if coverage["warnings"] else "bounded-static-scan"
    coverage["warnings"] = sorted(coverage["warnings"])
    coverage["limitations"] = ["Heuristic discovery only; comments can match and dynamic configuration can be missed.",
                               "No source execution, credential files, hidden directories or provider APIs are inspected.",
                               "A bounded scan cannot establish a complete inventory or workload compatibility."]
    return inv


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _cell(text: str) -> str:
    return str(text).replace("|", "\\|")


def render_markdown(inv: dict) -> str:
    services = inv["services"]
    fits = {fit: sum(1 for s in services if s["fit"] == fit) for fit in ("equivalent", "partial", "gap")}
    clouds = ", ".join(f"{c} ({n})" for c, n in inv["source_clouds"].items()) or "none detected"
    out = [f"# Migration assessment: {inv['root']}", "",
           f"Coverage: {inv['coverage']['status']}. Inspect the limitations below.", "",
           f"Source clouds: {clouds}. Files scanned: {inv['files_scanned']}. "
           f"Findings: {len(inv['findings'])}, mapped to {len(services)} OCI services "
           f"({fits['equivalent']} equivalent, {fits['partial']} partial, {fits['gap']} gap). "
           f"Unrecognised: {len(inv['unmapped'])}.", "",
           f"Effort signal: **{inv['effort']['size']}** (score {inv['effort']['score']}). {inv['effort']['method']}",
           "", f"Container-ready: {'yes, ' + ', '.join(inv['dockerfiles']) if inv['container_ready'] else 'no Dockerfile found'}.",
           "", "## What maps to OCI", "",
           "| Fit | Complexity | Found | Count | OCI target |", "|---|---|---|---:|---|"]
    for s in services:
        found = ", ".join(f"`{t}`" for t in s["found"][:4]) + (" and more" if len(s["found"]) > 4 else "")
        out.append(f"| {s['fit']} | {s['complexity']} | {_cell(found)} | {s['count']} | "
                   f"[{_cell(s['oci']['name'])}]({s['oci']['docs']}) |")
    hard = [s for s in services if s["fit"] != "equivalent"]
    if hard:
        out += ["", "## Partial fits and gaps", ""]
        for s in hard:
            out.append(f"**{s['oci']['name']}** ({s['fit']}, {s['complexity']}): replaces {', '.join(s['found'][:3])}.")
            out += [f"- {d}" for d in s["differences"]]
            out.append(f"- Migration: {s['migration']}")
            out += [f"- Alternative: `{a['service']}` when {a['when'][0].lower() + a['when'][1:]}"
                    for a in s["alternatives"]]
            out.append("")
    sdk = [f for f in inv["findings"] if f["kind"] == "sdk"]
    if sdk:
        out += ["## Application code that calls cloud SDKs", "",
                "These need code changes, or a compatible API, before the app runs on OCI.", "",
                "| Package | Ecosystem | Used for | File |", "|---|---|---|---|"]
        out += [f"| `{f['type']}` | {f['name']} | {f['service']} | {f['file']}:{f['line']} |" for f in sdk]
        out.append("")
    images = [f for f in inv["findings"] if f["kind"] == "image"]
    if images:
        out += ["## Self-hosted services", "",
                "They run unchanged in containers on OCI; a managed service is optional.", ""]
        out += [f"- `{f['type']}` in {f['file']}:{f['line']}: could move to `{f['opportunity']}`" for f in images]
        out.append("")
    if inv["coupling"]:
        out += ["## Kubernetes settings tied to the source cloud", ""]
        out += [f"- {c['signal']} in {c['file']}:{c['line']}" for c in inv["coupling"]]
        out.append("")
    out += ["## Not recognised", ""]
    if inv["unmapped"]:
        out += ["Cloud resources the service map does not cover yet. Review each by hand.", ""]
        out += [f"- `{u['type']}` ({u['kind']}) in {u['file']}:{u['line']}" for u in inv["unmapped"]]
    else:
        out.append("Every cloud resource found was mapped.")
    out += ["", "## Coverage limitations", ""]
    out += [f"- {item}" for item in inv["coverage"]["warnings"] + inv["coverage"]["limitations"]]
    out += ["", "## Next steps", "",
            "1. Confirm the inventory with the team: anything created by hand in a console will not appear here.",
            "2. Settle every partial fit and gap above before choosing dates.",
            "3. Continue with `oci-migrate-assess`'s staged assessment, and price both sides with `founder-value`.",
            "", f"Service map checked {inv['service_map']['checked_at']} against {inv['service_map']['oci_provider']}. "
            "A planning aid, not a guarantee of compatibility."]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory a repository's cloud footprint and map it to OCI.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--out", type=Path, help="Create a new report; existing files are never overwritten.")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args(argv)
    if not args.path.is_dir():
        sys.stderr.write("iac_scan: input is not a directory\n")
        return 2
    try:
        if args.out and (args.out.exists() or args.out.is_symlink()):
            raise ValueError("Output already exists")
        inventory = scan_path(args.path, load_map(args.map))
        text = json.dumps(inventory, indent=2) + "\n" if args.format == "json" else render_markdown(inventory)
        if args.out:
            fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
        else:
            sys.stdout.write(text)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        sys.stderr.write("iac_scan: cannot scan or create report; use a readable source/map and a new output path.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
