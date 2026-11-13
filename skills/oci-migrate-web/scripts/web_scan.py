#!/usr/bin/env python3
"""Bounded, read-only discovery of web-hosting dependencies. Never runs source code.

Python 3.11+. Exit 0: report produced (inspect coverage); 2: invalid request.
Dependency/configuration values, source excerpts and credential files are not output.
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

SCHEMA = "oci-web-migration/1"
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 24 * MAX_FILE_BYTES
MAX_FILES = 3000
MAX_ENTRIES = 20000
MAX_DEPTH = 30
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", "coverage", "out", "target",
             "venv", "env", "__pycache__", "bin", "obj"}
SOURCE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
FRAMEWORKS = {"next": "Next.js", "react": "React", "vite": "Vite", "astro": "Astro",
              "@sveltejs/kit": "SvelteKit", "nuxt": "Nuxt"}
DEPENDENCIES = {
    "@vercel/blob": "blob-storage", "@vercel/kv": "kv-store", "@vercel/postgres": "postgres",
    "@vercel/edge-config": "edge-config", "@vercel/functions": "platform-functions",
    "@vercel/analytics": "analytics", "@vercel/speed-insights": "analytics",
    "@netlify/blobs": "blob-storage", "@netlify/functions": "platform-functions",
    "@netlify/edge-functions": "edge-runtime", "@neondatabase/serverless": "postgres",
    "@supabase/supabase-js": "external-backend",
}
ACTIONS = {
    "hosting-config": "Review build/runtime settings and deployment environments; recreate only required settings on OCI.",
    "server-routes": "Keep request handlers server-side; test methods, cookies, uploads, streaming and request limits on the chosen runtime.",
    "routing": "Reproduce redirects, rewrites, headers and fallback semantics at the app or edge; test deep links and status codes.",
    "scheduled-jobs": "Move schedules to a reviewed scheduler; preserve authentication, time zones, retries and duplicate-execution handling.",
    "blob-storage": "Inventory objects and permissions; adapt storage calls to OCI Object Storage, rehearse copy and validate checksums before cutover.",
    "kv-store": "Choose a compatible data service after checking TTL, commands, consistency and atomicity; test and rehearse data transfer.",
    "postgres": "Inventory extensions, TLS, pooling and backups; test the selected OCI database or retain the existing provider deliberately.",
    "edge-config": "Replace edge-distributed configuration with a reviewed configuration/cache design; verify propagation and latency.",
    "edge-runtime": "Review edge runtime APIs and placement; adapt to a Node server or separately validated edge target and test latency.",
    "platform-functions": "Adapt provider helpers and function lifecycle behavior to the selected OCI runtime; verify background work completes.",
    "analytics": "Choose telemetry deliberately; update consent and external destinations and verify events without leaking personal data.",
    "external-backend": "Inventory external authentication, data and storage separately; do not assume changing hosting migrates them.",
    "middleware": "Preserve middleware/proxy ordering, authentication, cookies and redirects; test bypass and deep-link cases.",
    "image-optimization": "Validate self-hosted image optimization, allowed origins, dependencies and cache behavior; account for resource use.",
    "cache-revalidation": "Design shared cache and revalidation behavior for the number of replicas; test invalidation and stale responses.",
    "deployment-env": "Replace provider deployment metadata with explicit runtime configuration; review build-time public variables separately.",
    "next-runtime": "Inspect the installed Next.js version and self-hosting guide; use a Node/container runtime where server features are required.",
}
PATTERNS = (
    ("edge-runtime", r"\bruntime\s*[:=]\s*['\"](?:edge|experimental-edge)['\"]"),
    ("middleware", r"\bNextResponse\b|\bNextRequest\b"),
    ("image-optimization", r"['\"]next/image['\"]"),
    ("cache-revalidation", r"\brevalidatePath\b|\brevalidateTag\b|\bgetStaticProps\b|\bunstable_cache\b|\brevalidate\s*[:=]"),
    ("deployment-env", r"\b(?:VERCEL|NETLIFY)(?:_[A-Z0-9_]+)?\b"),
)
ENV = re.compile(r"\b(?:process\.env|import\.meta\.env)(?:\.([A-Z][A-Z0-9_]{0,127})\b|\[\s*['\"]([A-Z][A-Z0-9_]{0,127})['\"]\s*\])")
SAFE_PATH = re.compile(r"^[A-Za-z0-9_./@()\[\]+ -]{1,240}$")


def display_path(path: Path) -> str:
    """Do not reflect control characters or markup from untrusted filenames."""
    value = path.as_posix()
    return value if SAFE_PATH.fullmatch(value) else "[path omitted: unsupported characters or length]"


def candidate(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith(".") or any(word in name for word in ("secret", "credential", "private", "certificate")):
        return False
    return path.suffix in SOURCE_SUFFIXES or name in {"package.json", "vercel.json", "netlify.toml", "_redirects", "_headers"}


def scan(root: Path, *, max_files: int = MAX_FILES, max_bytes: int = MAX_TOTAL_BYTES) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose an existing repository directory, not a symlink.")
    if max_files < 1 or max_bytes < 1:
        raise ValueError("Scan limits must be positive.")
    root = root.resolve()
    findings: dict[tuple[str, str], dict] = {}
    frameworks: set[str] = set()
    env_names: set[str] = set()
    warnings: set[str] = set()
    counts = {"files_read": 0, "bytes_read": 0, "entries_seen": 0, "files_skipped": 0}
    exhausted = False

    def add(code: str, path: Path):
        shown = display_path(path)
        findings[(code, shown)] = {"code": code, "path": shown, "fit": "review-required", "action": ACTIONS[code]}

    pending = [(root, 0)]
    while pending and not exhausted:
        directory, depth = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    counts["entries_seen"] += 1
                    if counts["entries_seen"] > MAX_ENTRIES:
                        warnings.add("Entry limit reached; discovery is incomplete.")
                        exhausted = True
                        break
                    if entry.is_symlink():
                        counts["files_skipped"] += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                            continue
                        if depth >= MAX_DEPTH:
                            warnings.add("Directory depth limit reached; discovery is incomplete.")
                        else:
                            pending.append((Path(entry.path), depth + 1))
                        continue
                    path = Path(entry.path)
                    if not entry.is_file(follow_symlinks=False) or not candidate(path):
                        continue
                    rel = path.relative_to(root)
                    if counts["files_read"] >= max_files:
                        warnings.add("File limit reached; discovery is incomplete.")
                        exhausted = True
                        break
                    try:
                        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                        with os.fdopen(fd, "rb") as handle:
                            info = os.fstat(handle.fileno())
                            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                                counts["files_skipped"] += 1
                                warnings.add("Oversized or nonregular candidate skipped; discovery is incomplete.")
                                continue
                            if counts["bytes_read"] + info.st_size > max_bytes:
                                warnings.add("Byte limit reached; discovery is incomplete.")
                                exhausted = True
                                break
                            raw = handle.read(MAX_FILE_BYTES + 1)
                        if len(raw) > MAX_FILE_BYTES:
                            warnings.add("Growing or oversized candidate skipped; discovery is incomplete.")
                            counts["files_skipped"] += 1
                            continue
                        text = raw.decode("utf-8")
                    except (OSError, UnicodeError):
                        warnings.add("Unreadable candidate skipped; discovery is incomplete.")
                        counts["files_skipped"] += 1
                        continue
                    counts["files_read"] += 1
                    counts["bytes_read"] += len(raw)
                    if path.name == "package.json":
                        try:
                            data = json.loads(text)
                            if not isinstance(data, dict):
                                raise ValueError
                            deps = set()
                            for key in ("dependencies", "devDependencies", "optionalDependencies"):
                                group = data.get(key, {})
                                if isinstance(group, dict):
                                    deps.update(group)
                            frameworks.update(FRAMEWORKS[key] for key in deps & FRAMEWORKS.keys())
                            for key in deps & DEPENDENCIES.keys():
                                add(DEPENDENCIES[key], rel)
                            if "next" in deps:
                                add("next-runtime", rel)
                        except (ValueError, TypeError, RecursionError):
                            warnings.add("Malformed package manifest; dependency discovery is incomplete.")
                    elif path.name == "vercel.json":
                        add("hosting-config", rel)
                        try:
                            data = json.loads(text)
                            if not isinstance(data, dict):
                                raise ValueError
                            for key, code in (("functions", "server-routes"), ("crons", "scheduled-jobs"),
                                              ("rewrites", "routing"), ("redirects", "routing"), ("headers", "routing"), ("routes", "routing")):
                                if key in data:
                                    add(code, rel)
                        except (ValueError, TypeError, RecursionError):
                            warnings.add("Malformed Vercel configuration; configuration discovery is incomplete.")
                    elif path.name == "netlify.toml":
                        add("hosting-config", rel)
                        try:
                            data = tomllib.loads(text)
                            for key, code in (("functions", "platform-functions"), ("edge_functions", "edge-runtime"),
                                              ("redirects", "routing"), ("headers", "routing")):
                                if key in data:
                                    add(code, rel)
                        except (ValueError, RecursionError):
                            warnings.add("Malformed Netlify configuration; configuration discovery is incomplete.")
                    elif path.name in {"_redirects", "_headers"}:
                        add("routing", rel)
                    else:
                        for code, pattern in PATTERNS:
                            if re.search(pattern, text):
                                add(code, rel)
                        if path.stem in {"middleware", "proxy"}:
                            add("middleware", rel)
                        if "api" in rel.parts or (path.stem == "route" and "app" in rel.parts):
                            add("server-routes", rel)
                        for match in ENV.finditer(text):
                            env_names.add(match.group(1) or match.group(2))
        except OSError:
            warnings.add("Unreadable directory skipped; discovery is incomplete.")

    return {"schema": SCHEMA, "frameworks": sorted(frameworks), "findings": [findings[key] for key in sorted(findings)],
            "environment_variable_names": sorted(env_names),
            "coverage": {**counts, "status": "incomplete" if warnings else "bounded-static-scan",
                         "warnings": sorted(warnings), "limits": {"files": max_files, "total_bytes": max_bytes,
                         "file_bytes": MAX_FILE_BYTES, "entries": MAX_ENTRIES, "depth": MAX_DEPTH},
                         "limitations": ["Heuristic discovery only; comments can match and dynamic configuration can be missed.",
                                         "No source execution, package installation, environment files, provider APIs or hidden directories are inspected.",
                                         "Monorepos are scanned within limits; provider dashboard settings, data, domains and secrets require a separate inventory."]},
            "next_steps": ["Review findings and capture source behavior before adapting code.",
                           "Use oci-ready and oci-foundation, then oci-build and oci-deploy for the selected target.",
                           "Rehearse data transfer and rollback; switch traffic only after explicit approval and functional checks."]}


def markdown(report: dict) -> str:
    lines = ["# Web workload migration discovery", "", "Frameworks: " + (", ".join(report["frameworks"]) or "not identified"),
             "", "Coverage: " + report["coverage"]["status"], "", "Every finding requires review; this report is not a migration or deployment receipt.", ""]
    for finding in report["findings"]:
        lines.extend([f"- **{finding['code']}** — {finding['path']}: {finding['action']}"])
    if not report["findings"]:
        lines.append("No recognized hosting dependencies found; absence of findings does not establish portability.")
    lines.extend(["", "Environment variable names (values are never collected):", ""])
    lines.extend("- " + name for name in report["environment_variable_names"])
    lines.extend(["", "Coverage limitations:", ""])
    lines.extend("- " + item for item in report["coverage"]["warnings"] + report["coverage"]["limitations"])
    lines.extend(["", "Next steps:", ""])
    lines.extend("- " + step for step in report["next_steps"])
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--out", type=Path, help="Create a new report; existing files are never overwritten.")
    args = parser.parse_args(argv)
    try:
        if args.out and (args.out.exists() or args.out.is_symlink()):
            raise ValueError("Report output already exists; choose a new path.")
        report = scan(args.root)
        output = json.dumps(report, indent=2) + "\n" if args.format == "json" else markdown(report)
        if args.out:
            # Exclusive creation also rejects a symlink created between checking and opening.
            fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(output)
        else:
            sys.stdout.write(output)
        return 0
    except (ValueError, OSError):
        sys.stderr.write("Cannot scan or create report. Choose a readable directory and a new output path.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
