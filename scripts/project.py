#!/usr/bin/env python3
"""Guide private project progress and explicit read-only environment checks.

Python 3.11+, Linux/macOS/WSL2. Records are owner-supplied evidence references,
not proof of runtime behavior or authorization. Only reviewed kit helpers are
loaded. Application code, Git configuration, recognized credential stores and receipts'
commands are never executed. Only explicit doctor/verify operations perform bounded
read requests; status/resume/record remain local.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "oci-kit-project/1"
TASKS = ("build", "migrate", "setup")
AGENTS = ("codex", "claude", "both")
STACKS = ("auto", "nextjs", "fastapi", "custom")
RECORD_STEPS = ("migration-assessment", "local-workflow", "access", "design-cost",
                "runtime", "recovery", "cutover")
BOUND_REPORT_SCHEMAS = {"oci-workload-readiness/1", "oci-runtime-probe/1", "oci-migration-parity/1", "oci-production-check/1"}
LIMIT = 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
DIRECTORY = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
SKIP = {".git", ".oci-kit", ".oci-founder-kit", ".agents", ".claude", ".codex",
        ".gate", ".terraform", "node_modules", "__pycache__", ".venv", "venv",
        "dist", "build", "coverage", ".next", ".vercel", ".netlify", ".local-preview",
        ".oci", ".docker", ".aws", ".ssh", ".azure", ".kube", "credentials", "keys"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json",
                   ".tf", ".hcl", ".yaml", ".yml", ".toml", ".html", ".css", ".sql",
                   ".md", ".go", ".rs", ".java", ".sh", ".lock"}
SCOPE = ("Local guidance only. Evidence is owner-recorded, not independently verified. "
         "No application commands or cloud requests run. Recognized private input contents "
         "are not read; source files are hashed, not retained. Saved progress "
         "and receipts never authorize writes; exact-plan approval remains in the deploy gate.")


def helper(name: str):
    """Load a fixed helper from this reviewed kit, never from application input."""
    path = ROOT / "scripts" / f"{name}.py"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Required kit helper is unavailable.")
    spec = importlib.util.spec_from_file_location(f"oci_project_{name}", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_at(directory: int, name: str, *, private: bool = False, maximum: int = LIMIT) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or (private and (before.st_uid != os.getuid() or before.st_mode & 0o077))):
            raise ValueError("Expected a bounded regular file with safe ownership.")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        if len(raw) > maximum or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("File is oversized or changed during inspection.")
    return raw


def object_at(directory: int, name: str, *, private: bool = False) -> dict:
    value = json.loads(read_at(directory, name, private=private), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object.")
    return value


def open_project(project: Path) -> tuple[Path, int]:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("Supported local filesystem operations are required.")
    path = project.expanduser().absolute()
    if ".." in path.parts:
        raise ValueError("Use a project path without parent traversal.")
    fd = os.open(path.anchor, DIRECTORY)
    try:
        for part in path.parts[1:]:
            following = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = following
        return path, fd
    except Exception:
        os.close(fd)
        raise


def identity(directory: int) -> str:
    info = os.fstat(directory)
    return digest(canonical([info.st_dev, info.st_ino]))


class Store:
    """Private, locked state with atomic replacement; no app files are rewritten."""

    def __init__(self, project: Path, create: bool = False, write: bool = False,
                 environment: str | None = None):
        self.project = project
        self.create = create
        self.write = write
        self.environment = environment
        if environment is not None and not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", environment):
            raise ValueError("Invalid environment name.")

    def __enter__(self):
        import fcntl
        self.handles = []
        try:
            self.project, self.root_fd = open_project(self.project)
            self.handles.append(self.root_fd)
            if self.create:
                try:
                    os.mkdir(".oci-kit", 0o700, dir_fd=self.root_fd)
                except FileExistsError:
                    pass
            self.fd = os.open(".oci-kit", DIRECTORY, dir_fd=self.root_fd)
            self.base_fd = self.fd
            self.handles.append(self.fd)
            info = os.fstat(self.fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Project state directory must be private and owned.")
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
            if self.create:
                flags |= os.O_CREAT
            lock = os.open(".lock", flags, 0o600, dir_fd=self.fd)
            self.handles.append(lock)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Unsafe state lock.")
            fcntl.flock(lock, fcntl.LOCK_EX if self.write else fcntl.LOCK_SH)
            if self.create:
                self.create_file(".gitignore", b"*\n")
            if read_at(self.base_fd, ".gitignore", private=True) != b"*\n":
                raise ValueError("Private state ignore file changed.")
            if self.environment is not None:
                for name in ("environments", self.environment):
                    self.fd = os.open(name, DIRECTORY, dir_fd=self.fd)
                    self.handles.append(self.fd)
                    info = os.fstat(self.fd)
                    if info.st_uid != os.getuid() or info.st_mode & 0o077:
                        raise ValueError("Environment directory must be private and owned.")
                self.environment_config = object_at(self.fd, "environment.json", private=True)
                helper("environments").validate(self.environment_config)
                if self.environment_config["name"] != self.environment:
                    raise ValueError("Environment binding changed.")
            if self.create:
                try:
                    os.mkdir("evidence", 0o700, dir_fd=self.fd)
                except FileExistsError:
                    pass
            evidence = os.open("evidence", DIRECTORY, dir_fd=self.fd)
            self.handles.append(evidence)
            info = os.fstat(evidence)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Evidence directory must be private and owned.")
            self.evidence_fd = evidence
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for fd in reversed(self.handles):
            os.close(fd)

    def create_file(self, name: str, raw: bytes):
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        except FileExistsError:
            return
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def read(self) -> dict:
        data = object_at(self.fd, "state.json", private=True)
        validate_state(data)
        if data["project_identity"] != identity(self.root_fd):
            raise ValueError("State belongs to another directory; review before starting there.")
        if data.get("environment") != self.environment:
            raise ValueError("State belongs to another environment.")
        return data

    def save(self, data: dict):
        validate_state(data)
        # Refuse an unexpected target before replacing a known regular state file.
        try:
            read_at(self.fd, "state.json", private=True)
        except FileNotFoundError:
            pass
        name = f".pending-{uuid.uuid4().hex}"
        try:
            self.create_file(name, canonical(data) + b"\n")
            os.replace(name, "state.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(name, dir_fd=self.fd)


def valid_hash(value) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def validate_state(data: dict):
    fields = {"schema", "task", "mode", "agent", "stack", "blueprint", "project_identity",
              "created_at", "observed_at", "source_sha256", "kit_sha256", "records"}
    if data.get("schema") == "oci-kit-project/2":
        fields |= {"environment"}
        if not isinstance(data.get("environment"), str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", data["environment"]):
            raise ValueError("Invalid state environment.")
    if (set(data) != fields or data["schema"] not in {SCHEMA, "oci-kit-project/2"} or data["task"] not in TASKS
            or data["mode"] not in {"new", "existing"} or data["agent"] not in AGENTS
            or data["stack"] not in STACKS or data["blueprint"] not in {None, "fullstack-container", "web-container"}
            or not all(valid_hash(data[key]) for key in ("project_identity", "source_sha256", "kit_sha256"))
            or any(type(data[key]) is not int or data[key] < 0 for key in ("created_at", "observed_at"))
            or not isinstance(data["records"], dict) or not set(data["records"]).issubset(RECORD_STEPS)):
        raise ValueError("Invalid project state.")
    for item in data["records"].values():
        if (not isinstance(item, dict) or set(item) != {"outcome", "evidence", "evidence_sha256", "source_sha256", "kit_sha256", "recorded_at"}
                or item["outcome"] not in {"passed", "blocked"}
                or not isinstance(item["evidence"], str) or not NAME.fullmatch(item["evidence"])
                or any(not valid_hash(item[key]) for key in ("evidence_sha256", "source_sha256", "kit_sha256"))
                or type(item["recorded_at"]) is not int or item["recorded_at"] < 0):
            raise ValueError("Invalid evidence record.")


def source_fingerprint(root_fd: int) -> str:
    """Hash bounded regular source inputs. Never save contents, filenames or secrets."""
    fingerprints = []
    total = 0
    entries = 0
    private_path = helper("hooks").private_path

    def walk(fd: int, prefix: str, depth: int):
        nonlocal total, entries
        if depth > 30:
            raise ValueError("Source nesting exceeds inspection limit.")
        names = os.listdir(fd)
        entries += len(names)
        if entries > 10000:
            raise ValueError("Source directory exceeds inspection limit.")
        for name in sorted(names):
            lower = name.lower()
            if lower in SKIP or lower.startswith("tfplan"):
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            relative = prefix + name
            private_input = (private_path(relative) or lower.startswith(".env")
                             or re.search(r"\.(?:tfvars|tfbackend|tfstate|tfplan)(?:[.~]|$)", lower))
            if private_input:
                # Configuration changes invalidate evidence without opening secrets.
                # This metadata check cannot detect deliberate same-user timestamp forgery.
                fingerprints.append([relative, "metadata-only", info.st_mode, info.st_ino,
                                     info.st_size, info.st_mtime_ns, info.st_ctime_ns])
            elif stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY, dir_fd=fd)
                try:
                    walk(child, relative + "/", depth + 1)
                finally:
                    os.close(child)
            elif Path(lower).suffix in SOURCE_SUFFIXES or lower in {"dockerfile", "makefile"}:
                raw = read_at(fd, name, maximum=4 * LIMIT)
                total += len(raw)
                fingerprints.append([relative, digest(raw)])
            elif stat.S_ISLNK(info.st_mode):
                # An unknown link might be a source directory: do not silently omit it.
                raise ValueError("Source symlinks need review.")
            if len(fingerprints) > 5000 or total > 64 * LIMIT:
                raise ValueError("Source inspection exceeds bounded limits.")
    walk(root_fd, "", 0)
    return digest(canonical(fingerprints))


def kit_fingerprint() -> str:
    values = []
    # Include executed transitive helpers, not only the top-level dispatcher.
    for relative in ("scripts", "skills/oci-ready/scripts", "skills/oci-deploy/scripts",
                     "blueprints/fullstack-container"):
        _, fd = open_project(ROOT / relative)
        try:
            names = os.listdir(fd)
            if len(names) > 200:
                raise ValueError("Toolkit helper inventory exceeds its bound.")
            for name in sorted(names):
                if name.endswith(".py") and NAME.fullmatch(name):
                    values.append([relative + "/" + name, digest(read_at(fd, name))])
        finally:
            os.close(fd)
    return digest(canonical(values))


def gate_observation(root_fd: int, infrastructure: str = "terraform", *, environment_config=None,
                     project_path: str | None = None) -> dict:
    """Observe only the conventional editable terraform/.gate, never execute it."""
    result = {"plan": "absent", "deployment": "unobserved"}
    handles = []
    try:
        expected_sources = (helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py").source_binding()
                            if environment_config else None)
        def binding_matches(value):
            if environment_config is None:
                return True
            binding = value.get("project_environment")
            return (environment_config.get("backend") is not None and isinstance(binding, dict)
                    and binding.get("schema") == "oci-deploy-environment-binding/1"
                    and binding.get("project_identity") == identity(root_fd)
                    and binding.get("project_path") == project_path
                    and binding.get("environment") == environment_config["name"]
                    and binding.get("configuration_sha256") == digest(canonical(environment_config))
                    and binding.get("infrastructure") == infrastructure
                    and binding.get("sources") == expected_sources)
        fd = root_fd
        for name in (*Path(infrastructure).parts, ".gate"):
            fd = os.open(name, DIRECTORY, dir_fd=fd)
            handles.append(fd)
        try:
            plan = object_at(fd, "plan-summary.json", private=True)
            created, expires = plan.get("created_at_epoch"), plan.get("expires_at_epoch")
            if (plan.get("kind") not in {"apply", "destroy"} or not valid_hash(plan.get("plan_sha256"))
                    or type(created) not in {int, float} or type(expires) not in {int, float}
                    or not 0 < expires - created <= 86400 or created > time.time() + 300):
                raise ValueError("Invalid gate plan metadata.")
            raw = read_at(fd, "tfplan", private=True, maximum=16 * LIMIT)
            result["plan"] = "changed" if digest(raw) != plan["plan_sha256"] or not binding_matches(plan) else (
                "expired" if time.time() > expires else "pending-review")
        except FileNotFoundError:
            pass
        try:
            receipts = os.open("receipts", DIRECTORY, dir_fd=fd)
            handles.append(receipts)
        except FileNotFoundError:
            return result
        names = os.listdir(receipts)
        if len(names) > 200:
            raise ValueError("Receipt inspection exceeds its bound.")
        latest = None
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            receipt = object_at(receipts, name, private=True)
            if receipt.get("schema") != "oci-deploy-receipt/2":
                continue
            if (receipt.get("kind") not in {"apply", "destroy"} or receipt.get("status") not in
                    {"attempted", "refused", "failed", "applied-unrecorded", "applied"}
                    or not valid_hash(receipt.get("plan_sha256"))):
                raise ValueError("Invalid deployment receipt.")
            started = receipt.get("started_at")
            if not isinstance(started, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:\+00:00|Z)", started):
                raise ValueError("Invalid receipt timestamp.")
            timestamp = dt.datetime.fromisoformat(started.replace("Z", "+00:00"))
            # With equal timestamps the order is unknown; surface an unsafe attempt.
            caution = receipt["status"] != "applied" or receipt["kind"] == "destroy" or not binding_matches(receipt)
            if latest is None or (timestamp, caution) > latest[:2]:
                latest = (timestamp, caution, receipt)
        if latest:
            receipt = latest[2]
            result["deployment"] = ("apply-receipt-observed" if receipt["kind"] == "apply" else "destroy-receipt-observed") if receipt["status"] == "applied" and binding_matches(receipt) else "attempt-needs-review"
        return result
    except FileNotFoundError:
        return result
    except (ValueError, OSError, UnicodeError, RecursionError):
        return {"plan": "unreadable", "deployment": "unknown"}
    finally:
        for fd in reversed(handles):
            os.close(fd)


def steps_for(task: str, role: str | None = None) -> list[str]:
    if role == "source":
        return (["migration-assessment"] if task == "migrate" else []) + ["local-workflow", "source-handoff"]
    if task == "setup":
        return ["access", "design-cost", "cloud-plan", "deployment", "acceptance"]
    return (["migration-assessment"] if task == "migrate" else []) + [
        "local-workflow", "access", "design-cost", "cloud-plan", "deployment", "runtime", "recovery"
    ] + (["cutover"] if task == "migrate" else []) + ["acceptance"]


def record_status(store: Store, record: dict, source: str, kit: str) -> str:
    try:
        raw = read_at(store.evidence_fd, record["evidence"], private=True)
    except (OSError, ValueError):
        return "stale"
    if (digest(raw) != record["evidence_sha256"] or source != record["source_sha256"]
            or kit != record["kit_sha256"]):
        return "stale"
    if store.environment and raw.lstrip().startswith(b"{"):
        try:
            data = json.loads(raw, object_pairs_hook=unique)
            if isinstance(data, dict) and data.get("schema") in BOUND_REPORT_SCHEMAS:
                observed = data.get("observed_at")
                if type(observed) is not int or not 0 <= time.time() - observed <= 86400:
                    return "stale"
        except (ValueError, RecursionError):
            return "stale"
    return "owner-recorded" if record["outcome"] == "passed" else "blocked"


INSTRUCTIONS = {
    "source-handoff": "Review the captured source behavior and retained services, then explicitly select the rehearsal environment. Keep the source running; this environment does not select an OCI deployment target.",
    "migration-assessment": "Assess the existing app with oci-migrate-assess and retain a private scope/parity report before adapting it.",
    "local-workflow": "Build and test the app's primary local user flow; retain the actual commands and results privately, then record this checkpoint.",
    "access": "Run the OCI readiness doctor with your private target selection; resolve blocked or unknown checks and retain its JSON report privately.",
    "design-cost": "Review the architecture, security, dated costs and remaining service-limit assumptions; retain the decisions privately.",
    "cloud-plan": "Prepare a fresh plan using the existing deploy gate after reviewing backend, target and costs. The owner must approve that exact plan in the current conversation.",
    "deployment": "Review the exact current plan with the owner, then use the existing approval gate. This guide never applies or authorizes a plan.",
    "runtime": "Verify the deployed endpoint, identity, ownership, persistence and required integrations; retain actual runtime results privately.",
    "recovery": "Rehearse scoped restore and rollback with the required separate approvals; record measured results and remaining resources privately.",
    "cutover": "Review migration parity, data reconciliation and rollback, then obtain the separate traffic-switch approval; retain actual results privately.",
    "acceptance": "Review all evidence and remaining security, recovery and operating risks with the owner. This checklist cannot certify production readiness.",
}


def report(store: Store, data: dict) -> tuple[dict, str, str]:
    source, kit = source_fingerprint(store.root_fd), kit_fingerprint()
    if store.environment:
        kit = digest(canonical([kit, store.environment_config]))
    installed = helper("install").status(store.project)
    installation = "ready" if installed.get("installed") and not installed.get("missing_entries") else "incomplete"
    required = set(AGENTS[:2] if data["agent"] == "both" else [data["agent"]])
    if not required.issubset(set(installed.get("agents", []))):
        installation = "incomplete"
    infrastructure = store.environment_config["infrastructure"] if store.environment else "terraform"
    gate = gate_observation(store.root_fd, infrastructure,
                            environment_config=store.environment_config if store.environment else None,
                            project_path=str(store.project)) if infrastructure else {"plan": "absent", "deployment": "unobserved"}
    steps = []
    for step in steps_for(data["task"], store.environment_config["role"] if store.environment else None):
        status = record_status(store, data["records"][step], source, kit) if step in data["records"] else "not-recorded"
        if step == "cloud-plan":
            status = gate["plan"]
            if gate["deployment"] == "apply-receipt-observed" and status == "absent":
                status = "receipt-observed"
        elif step == "deployment":
            status = gate["deployment"]
        steps.append({"id": step, "status": status})
    if installation != "ready":
        action = {"id": "installation", "instruction": "Review the installed bundle and missing agent entries with install.py --status. Existing source and skills are preserved."}
    elif gate["deployment"] in {"unknown", "attempt-needs-review", "destroy-receipt-observed"}:
        action = {"id": "review-deployment", "instruction": "Review the private deployment attempt and current resources before any retry. Receipts may describe partial changes or destruction; no action is repeated automatically."}
    elif gate["plan"] in {"expired", "changed", "unreadable"}:
        action = {"id": "review-plan", "instruction": "The saved plan is expired, changed or unreadable. Review it privately and prepare a fresh gated plan before seeking approval."}
    else:
        complete = {"owner-recorded", "receipt-observed", "apply-receipt-observed"}
        next_step = next(step for step in steps if step["status"] not in complete)
        action = {"id": next_step["id"], "instruction": INSTRUCTIONS[next_step["id"]]}
        if next_step["status"] == "stale":
            action["instruction"] = "Source, toolkit helpers or evidence changed. Recheck this checkpoint and record fresh evidence. " + action["instruction"]
        if next_step["id"] == "local-workflow" and data["blueprint"] == "fullstack-container":
            action["command"] = ["python3", "local_preview.py", "start"]
        elif next_step["id"] == "cloud-plan" and gate["plan"] == "pending-review":
            action["instruction"] = "A saved plan is awaiting review. Read its exact changes and expiry privately; only current owner approval permits the existing gate to apply it."
    result = {"schema": data["schema"], "task": data["task"], "mode": data["mode"], "agent": data["agent"],
            "stack": data["stack"], "blueprint": data["blueprint"], "installation": installation,
            "inputs_changed": source != data["source_sha256"] or kit != data["kit_sha256"],
            "steps": steps, "next_action": action, "scope": SCOPE}
    if store.environment:
        result.update(environment=store.environment, role=store.environment_config["role"],
                      target_sha256=digest(canonical(store.environment_config)),
                      current_source_sha256=source,
                      blueprint=store.environment_config["blueprint"])
    return result, source, kit


def resume(project: Path, *, refresh: bool = False, environment: str | None = None) -> dict:
    with Store(project, write=refresh, environment=environment) as store:
        data = store.read()
        result, source, kit = report(store, data)
        if refresh:
            data.update(observed_at=int(time.time()), source_sha256=source, kit_sha256=kit)
            store.save(data)
        return result


def start(project: Path, *, task: str = "build", mode: str = "existing", agent: str = "both",
          stack: str = "auto", blueprint: str | None = None) -> dict:
    if mode == "continue":
        return resume(project, refresh=True)
    if task not in TASKS or mode not in {"new", "existing"} or agent not in AGENTS or stack not in STACKS:
        raise ValueError("Invalid project selection.")
    if blueprint not in {None, "fullstack-container"} or (blueprint and (task != "build" or stack != "auto")):
        raise ValueError("Taskboard must be an explicit build selection, without another stack.")
    if mode == "new" and task != "build":
        raise ValueError("Setup and migration use an existing project directory.")
    project = project.expanduser().absolute()
    if (project / ".oci-kit" / "state.json").exists():
        with Store(project) as store:
            data = store.read()
            if any(data[key] != value for key, value in {"task": task, "agent": agent, "stack": stack, "blueprint": blueprint}.items()):
                raise ValueError("Existing project choices differ; use resume without overwriting them.")
        return resume(project, refresh=True)
    installer = helper("install")
    if mode == "new":
        creator = helper("scaffold")
        if blueprint:
            creator.create(blueprint, project, agent, root=ROOT)
        else:
            with creator.target_path(project, ROOT) as (project, previous, parent_fd):
                if previous is None:
                    os.mkdir(project.name, 0o755, dir_fd=parent_fd)
            installer.install(project, agent)
    else:
        project, fd = open_project(project)
        os.close(fd)
        if not installer.status(project).get("installed"):
            installer.install(project, agent)
    with Store(project, create=True, write=True) as store:
        try:
            store.read()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("State appeared during initialization; use resume.")
        if blueprint:
            helper("blueprint").load(blueprint, ROOT)
        source, kit = source_fingerprint(store.root_fd), kit_fingerprint()
        now = int(time.time())
        data = {"schema": SCHEMA, "task": task, "mode": mode, "agent": agent, "stack": stack,
                "blueprint": blueprint, "project_identity": identity(store.root_fd), "created_at": now,
                "observed_at": now, "source_sha256": source, "kit_sha256": kit, "records": {}}
        store.save(data)
        return report(store, data)[0]


def record(project: Path, step: str, evidence: str, outcome: str, *, environment: str | None = None) -> dict:
    if step not in RECORD_STEPS or outcome not in {"passed", "blocked"}:
        raise ValueError("Unsupported checkpoint or outcome.")
    path = Path(evidence)
    prefix = (".oci-kit", "environments", environment, "evidence") if environment else (".oci-kit", "evidence")
    if len(path.parts) != len(prefix) + 1 or path.parts[:-1] != prefix or not NAME.fullmatch(path.name):
        raise ValueError("Evidence must be directly inside the selected private evidence directory.")
    with Store(project, write=True, environment=environment) as store:
        data = store.read()
        if step not in steps_for(data["task"], store.environment_config["role"] if store.environment else None):
            raise ValueError("Checkpoint does not apply to this task.")
        raw = read_at(store.evidence_fd, path.name, private=True)
        if not raw.strip():
            raise ValueError("Evidence cannot be empty.")
        structured = None
        if raw.lstrip().startswith(b"{"):
            structured = json.loads(raw, object_pairs_hook=unique)
        if environment and isinstance(structured, dict) and structured.get("schema") in BOUND_REPORT_SCHEMAS:
            observed = structured.get("observed_at")
            if (structured.get("environment") != environment
                    or structured.get("target_sha256") != digest(canonical(store.environment_config))
                    or structured.get("source_sha256") != source_fingerprint(store.root_fd)
                    or structured.get("kit_sha256") != kit_fingerprint()
                    or type(observed) is not int or not 0 <= time.time() - observed <= 86400):
                raise ValueError("Report is stale or belongs to a different target or source.")
            if step != "access" and outcome == "passed" and structured.get("status") != "passed":
                raise ValueError("A failed or incomplete machine report cannot be recorded as passed.")
        if step == "access":
            readiness = structured
            if environment and (not isinstance(readiness, dict) or readiness.get("schema") != "oci-workload-readiness/1"):
                raise ValueError("Environment access requires a fresh, target-bound workload doctor report.")
            if environment and isinstance(readiness, dict) and readiness.get("schema") == "oci-workload-readiness/1":
                if outcome == "passed" and readiness.get("status") not in {"passed", "incomplete"}:
                    raise ValueError("Resolve known workload blockers before recording access as passed.")
                readiness = readiness.get("access")
            if (not isinstance(readiness, dict) or readiness.get("schema") != "oci-readiness/1"
                    or readiness.get("mode") not in {"offline", "live-read-only"}
                    or readiness.get("status") not in {"passed", "blocked", "incomplete"}):
                raise ValueError("Access evidence must use the existing doctor JSON format.")
            if outcome == "passed" and (readiness["status"] != "passed" or readiness["mode"] != "live-read-only"):
                raise ValueError("Offline or incomplete readiness does not establish live access.")
        source, kit = source_fingerprint(store.root_fd), kit_fingerprint()
        if environment:
            kit = digest(canonical([kit, store.environment_config]))
        data["records"][step] = {"outcome": outcome, "evidence": path.name,
                                "evidence_sha256": digest(raw), "source_sha256": source,
                                "kit_sha256": kit, "recorded_at": int(time.time())}
        data.update(observed_at=int(time.time()), source_sha256=source, kit_sha256=kit)
        store.save(data)
        return report(store, data)[0]


def save_report(store: Store, value: dict, kind: str) -> str:
    raw = canonical(value) + b"\n"
    if len(raw) > LIMIT:
        raise ValueError("Report exceeds the evidence bound.")
    name = f"{kind}-{int(time.time())}-{uuid.uuid4().hex[:12]}.json"
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=store.evidence_fd)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(store.evidence_fd)
    return f".oci-kit/environments/{store.environment}/evidence/{name}"


def doctor(project: Path, *, environment: str, config_file=Path("~/.oci/config"), live=False) -> dict:
    with Store(project, environment=environment, write=True) as store:
        state = store.read()
        value = helper("readiness").diagnose(store.environment_config, config_file=config_file, live=live,
                                           store=store, state=state)
        value["source_sha256"] = source_fingerprint(store.root_fd)
        value["kit_sha256"] = kit_fingerprint()
        value["evidence"] = save_report(store, value, "doctor")
        return value


def verify(project: Path, *, environment: str, kind: str = "runtime", contract: Path | None = None,
           sessions_file: Path | None = None, ca_file: Path | None = None) -> dict:
    with Store(project, environment=environment, write=True) as store:
        data = store.read()
        config = store.environment_config
        target = config["target"]
        if config["role"] == "source" or not target.get("origin") or not target.get("image_digest"):
            raise ValueError("Select an OCI environment with the intended HTTPS origin and immutable digest.")
        source = source_fingerprint(store.root_fd)
        if kind == "migration":
            if data["task"] != "migrate" or contract is None:
                raise ValueError("Migration verification requires the migration task and private contract.")
            migration = helper("migration")
            selected = migration.load_private(contract)
            migration.validate_contract(selected)
            if (selected["environment"] != environment or selected["transport"] != "https"
                    or selected["target"]["origin"].rstrip("/") != target["origin"].rstrip("/")
                    or selected["target"]["image_digest"] != target["image_digest"]
                    or selected["source"]["revision_sha256"] != source):
                raise ValueError("Contract target, source revision or environment changed; review a fresh contract.")
            sessions = migration.load_private(sessions_file, outside_git=True) if sessions_file else None
            value = migration.verify(selected, sessions=sessions, ca_file=ca_file)
        elif kind == "runtime":
            if contract or sessions_file:
                raise ValueError("The runtime probe is anonymous; use the dedicated application test for authenticated workflows.")
            if config["blueprint"] == "fullstack-container":
                readiness = helper("readiness")
                value = readiness.load("blueprints/fullstack-container/production_check.py").run(target["origin"], ca_file=ca_file)
            else:
                migration = helper("migration")
                client = migration.HTTPClient(target["origin"], transport="https", ca_file=ca_file,
                                              deadline=time.monotonic() + 30)
                try:
                    response = client.request("GET", target.get("health_path", "/healthz"), None)
                    status = "passed" if response.status == 200 else "failed"
                except (OSError, ValueError):
                    status = "unknown"
                value = {"schema": "oci-runtime-probe/1", "status": status,
                         "checks": [{"id": "https_health", "status": status}],
                         "scope": "selected-https-origin", "read_only": True,
                         "image_identity_verified": False, "production_readiness_established": False,
                         "not_covered": ["hosted-sign-in", "two-user-isolation", "persistence", "restore", "image-rollback", "deployed-image-identity"]}
        else:
            raise ValueError("Unknown verification kind.")
        if source_fingerprint(store.root_fd) != source:
            raise ValueError("Application changed during verification; repeat against the reviewed revision.")
        value.update(environment=environment, blueprint=config["blueprint"],
                     target_sha256=digest(canonical(config)), selected_image_digest=target["image_digest"],
                     source_sha256=source, kit_sha256=kit_fingerprint(), observed_at=int(time.time()))
        value["evidence"] = save_report(store, value, "verify")
        return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "status", "resume", "record", "doctor", "verify", "dashboard"):
        command = commands.add_parser(name)
        command.add_argument("--project", type=Path, required=True)
        if name != "start":
            command.add_argument("--environment", required=name in {"doctor", "verify", "dashboard"})
        if name == "start":
            command.add_argument("--task", choices=TASKS, default="build")
            command.add_argument("--mode", choices=("new", "existing", "continue"), default="existing")
            command.add_argument("--agent", choices=AGENTS, default="both")
            command.add_argument("--stack", choices=STACKS, default="auto")
            command.add_argument("--blueprint", choices=("fullstack-container",))
        elif name == "record":
            command.add_argument("--step", choices=RECORD_STEPS, required=True)
            command.add_argument("--evidence", required=True, help="Private 0600 file at .oci-kit/evidence/NAME; contents are not printed or copied.")
            command.add_argument("--outcome", choices=("passed", "blocked"), required=True)
        elif name == "doctor":
            command.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
            command.add_argument("--live", action="store_true")
        elif name == "verify":
            command.add_argument("--kind", choices=("runtime", "migration"), default="runtime")
            command.add_argument("--contract", type=Path)
            command.add_argument("--sessions-file", type=Path)
            command.add_argument("--ca-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start(args.project, task=args.task, mode=args.mode, agent=args.agent,
                           stack=args.stack, blueprint=args.blueprint)
        elif args.command == "record":
            result = record(args.project, args.step, args.evidence, args.outcome, environment=args.environment)
        elif args.command == "doctor":
            result = doctor(args.project, environment=args.environment, config_file=args.config_file, live=args.live)
        elif args.command == "verify":
            result = verify(args.project, environment=args.environment, kind=args.kind, contract=args.contract,
                            sessions_file=args.sessions_file, ca_file=args.ca_file)
        elif args.command == "dashboard":
            result = helper("dashboard").render(args.project, environment=args.environment)
        else:
            result = resume(args.project, refresh=args.command == "resume", environment=args.environment)
        print(json.dumps(result, indent=2))
        if args.command in {"doctor", "verify"}:
            return 0 if result["status"] == "passed" else (1 if result["status"] in {"blocked", "failed"} else 3)
        return 0
    except (ValueError, OSError, UnicodeError, RecursionError, TypeError):
        # Neither exceptions, caller filenames, account identifiers nor raw evidence are echoed.
        sys.stderr.write("Project guide refused: missing or invalid state/evidence, unsafe path, changed project choices, "
                         "unsupported selection, or inspection limit. For an existing project without state, use "
                         "start --mode existing. Preserve any partial setup and review it before retrying; no app "
                         "command or cloud write was run by this guide; explicit doctor/verify reads may have occurred.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
