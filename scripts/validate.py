#!/usr/bin/env python3
"""Dependency-free repository checks for the Founder Value Kit.

Checks skill frontmatter, portable frontmatter keys, relative Markdown links,
manifest JSON and version consistency, the example scenario, and obvious
secret patterns. Prints one line per problem and exits 1 if there are any.

Usage: python3 scripts/validate.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MANIFESTS = ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json")
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SECRET_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"ocid1\.(user|tenancy|credential)\.oc1\.\.[a-z0-9]{20,}"),
    re.compile(r"\b(sk|xai|ghp)[-_][A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(password|secret|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
)
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500
SKIP_DIRS = {".git", "__pycache__"}


def parse_frontmatter(text: str) -> tuple[dict, str] | None:
    """Parse the small YAML subset used in SKILL.md frontmatter."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0 and text.endswith("\n---"):
        end = len(text) - 4
    if end < 0:
        return None
    data: dict = {}
    parent = None
    for raw in text[4:end].splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, value = raw.strip().partition(":")
        value = value.strip().strip('"')
        if indent and parent:
            data[parent][key] = value
        elif value:
            data[key], parent = value, None
        else:
            data[key], parent = {}, key
    return data, text[end + 5:]


def check_skill(skill_dir: Path, root: Path = ROOT, versions: dict | None = None) -> list[str]:
    """Check one skill directory; record its metadata.version in `versions` when given."""
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    rel = skill_md.relative_to(root)
    if not skill_md.is_file():
        return [f"{skill_dir.relative_to(root)}: missing SKILL.md"]
    parsed = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if parsed is None:
        return [f"{rel}: missing or malformed frontmatter"]
    meta, body = parsed
    extra = set(meta) - PORTABLE_KEYS
    if extra:
        problems.append(f"{rel}: non-portable frontmatter keys {sorted(extra)}")
    name = meta.get("name") if isinstance(meta.get("name"), str) else ""
    if name != skill_dir.name:
        problems.append(f"{rel}: name '{meta.get('name')}' does not match directory")
    if not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"{rel}: name must be lowercase kebab-case, 64 characters or fewer")
    description = meta.get("description") if isinstance(meta.get("description"), str) else ""
    if not description or len(description) > MAX_DESCRIPTION:
        problems.append(f"{rel}: description must be 1 to {MAX_DESCRIPTION} characters "
                        f"(is {len(description)})")
    if body.count("\n") > MAX_BODY_LINES:
        problems.append(f"{rel}: body is longer than {MAX_BODY_LINES} lines")
    metadata = meta.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("version"):
        problems.append(f"{rel}: metadata must be a mapping with a version")
    elif versions is not None:
        versions[str(rel)] = metadata["version"]
    if not (skill_dir / "agents" / "openai.yaml").is_file():
        problems.append(f"{skill_dir.relative_to(root)}: missing agents/openai.yaml")
    return problems


def check_skills(problems: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        problems.extend(check_skill(skill_dir, ROOT, versions))
    return versions


def check_manifests(problems: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in MANIFESTS + (".claude-plugin/marketplace.json",):
        path = ROOT / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{name}: {exc}")
            continue
        if name.endswith("marketplace.json"):
            for entry in data.get("plugins", []):
                versions[f"{name}:{entry.get('name')}"] = entry.get("version")
        else:
            versions[name] = data.get("version")
            if data.get("name") != "oci-founder-kit":
                problems.append(f"{name}: name must be oci-founder-kit")
    return versions


def check_links(problems: list[str]) -> None:
    for md in iter_files(".md"):
        text = md.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if path and not (md.parent / path).resolve().exists():
                problems.append(f"{md.relative_to(ROOT)}: broken link {target}")


def check_secrets(problems: list[str]) -> None:
    for path in iter_files(".md", ".py", ".json", ".yaml", ".yml", ".txt"):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_RES:
            if pattern.search(text):
                problems.append(f"{path.relative_to(ROOT)}: matches secret pattern {pattern.pattern[:30]}")


def check_example(problems: list[str]) -> None:
    sys.path.insert(0, str(SKILLS / "founder-value" / "scripts"))
    import value_model  # noqa: PLC0415

    assets = SKILLS / "founder-value" / "assets"
    for name, must_be_complete in (("scenario.example.json", True), ("scenario.template.json", False)):
        scenario = json.loads((assets / name).read_text(encoding="utf-8"))
        errors = value_model.validate_scenario(scenario)
        if errors:
            problems.append(f"assets/{name}: {errors[0]}")
            continue
        status = value_model.simulate(scenario)["status"]
        if must_be_complete and status != "COMPLETE":
            problems.append(f"assets/{name}: expected a COMPLETE result, got {status}")


def iter_files(*suffixes: str):
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in suffixes and not SKIP_DIRS & set(path.parts):
            yield path


def main() -> int:
    problems: list[str] = []
    versions = check_skills(problems)
    versions.update(check_manifests(problems))
    if len(set(versions.values())) != 1:
        problems.append(f"versions differ: {versions}")
    check_links(problems)
    check_secrets(problems)
    check_example(problems)
    for problem in problems:
        sys.stdout.write(problem + "\n")
    sys.stdout.write(f"{'FAIL' if problems else 'OK'}: {len(problems)} problem(s)\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
