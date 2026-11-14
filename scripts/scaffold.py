"""Export the existing Taskboard into a new project with locally installed skills.

Creation copies reviewed source only. It never starts tools, containers or cloud
operations. Publication uses exclusive file creation. If publication fails,
partial destination files remain for manual review; they are never unlinked.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def sibling(root: Path, name: str):
    path = root / "scripts" / f"{name}.py"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Required kit helper is unavailable.")
    spec = importlib.util.spec_from_file_location(f"oci_create_{name}", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def open_directory(path: Path) -> int:
    anchor = os.open(path.anchor, DIRECTORY_FLAGS)
    try:
        return open_parent(anchor, path.parts[1:])
    finally:
        os.close(anchor)


def check_parent(project: Path, parent_fd: int) -> None:
    current_fd = open_directory(project.parent)
    try:
        current, expected = os.fstat(current_fd), os.fstat(parent_fd)
        if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError("Project parent changed during creation.")
    finally:
        os.close(current_fd)


@contextlib.contextmanager
def target_path(project: Path, root: Path):
    project = project.expanduser().absolute()
    # Refuse links rather than resolving a requested target into another tree.
    if any(path.is_symlink() for path in (project, *project.parents)):
        raise ValueError("Symlinked project paths are refused.")
    # Open every original component without following links, including before
    # normalizing '..'. Keep this parent handle until publication finishes.
    parent_fd = open_directory(project.parent)
    try:
        project = Path(os.path.normpath(project))
        if project == root or root in project.parents or project in root.parents:
            raise ValueError("Create the app outside the source kit.")
        check_parent(project, parent_fd)
        identity = None
        try:
            info = os.stat(project.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            info = None
        if info is not None:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("The target must be a new or empty directory.")
            target_fd = os.open(project.name, DIRECTORY_FLAGS, dir_fd=parent_fd)
            try:
                info = os.fstat(target_fd)
                if os.listdir(target_fd):
                    raise ValueError("The target must be a new or empty directory.")
                identity = (info.st_dev, info.st_ino)
            finally:
                os.close(target_fd)
        yield project, identity, parent_fd
    finally:
        os.close(parent_fd)


def guidance(stage: Path, installation: dict) -> None:
    (stage / "README.md").write_text("""# My Taskboard app

Your editable application is **app/**. Your editable OCI definitions are
**terraform/** and **registry/**. The hidden **.oci-founder-kit/** directory is
a toolkit snapshot; its bundled example is not this application's source.

## Run and edit locally

From this project directory, with Python 3.11+ and a local Docker Engine 28+
and compatible Compose installation:

```sh
python3 local_preview.py start
```

Open the loopback URL it prints. Edit app/ and run start again to rebuild.
The local sandbox has a real PostgreSQL database but no hosted sign-in or OCI
uploads. Do not expose it through a tunnel or public interface.

```sh
python3 local_preview.py status
python3 local_preview.py stop
```

Stop retains the database volume and its private settings. Do not delete
.local-preview/ or a stored data volume without a separate backup/removal decision.

For host-side application tests, install Node.js 22+ and run:

```sh
npm --prefix app ci --ignore-scripts
npm --prefix app test
```

Creation did not run these commands, inspect credentials or verify OCI readiness.
Record actual results and the next action in [docs/PROGRESS.md](docs/PROGRESS.md).

## Continue with your coding agent

Open this project in Codex and use `$oci-kit`, or in Claude Code use `/oci-kit`
when that agent was selected during creation:

> Improve my Taskboard app. Work in app/ and preserve its existing stack.
> Keep terraform/ and registry/ as this project's infrastructure sources.
> Test the useful local workflow, maintain docs/PROGRESS.md, then help me set up
> OCI access and a scoped foundation. Show exact resources, target, permissions,
> dated costs and a saved plan before cloud changes. Never request secret values.

Read the [installed start guide](.oci-founder-kit/docs/START-HERE.md),
[credential guide](.oci-founder-kit/skills/oci-ready/references/credentials.md)
and [Well-Architected review](.oci-founder-kit/skills/oci-foundation/references/well-architected.md).
The reference cloud definitions default to a restricted sandbox. Configure and
verify production identity, HTTPS, secrets, protected state and recovery before
real users. Use the installed deploy gate against this project's terraform/
or registry/, not the hidden toolkit example:

```sh
python3 .oci-founder-kit/skills/oci-deploy/scripts/deploy_gate.py plan --dir terraform
```

Planning needs separately prepared private target variables, credentials and
backend configuration. No plan or cloud write was run during project creation.
IAM, image publication, apply, data movement, traffic changes and cleanup retain
their explicit approval boundaries. The source license is retained in LICENSE.

Generated toolkit bundles and entry skills are ignored by Git. A collaborator
can install the kit from its reviewed public repository into this existing app;
ordinary app source remains independent of the toolkit snapshot.
""", encoding="utf-8")
    (stage / "PRODUCTION.md").write_text("""# Deploy this project's app

Your application is app/; its infrastructure is terraform/ and registry/.
Read the [hardened reference](.oci-founder-kit/blueprints/fullstack-container/PRODUCTION.md)
for identity, HTTPS, Vault, private state and recovery requirements, and the
[operations acceptance](.oci-founder-kit/docs/OPERATIONS.md) before real users.
The installed reference's example-directory paths are not this project's paths.
Keep commands rooted in this project and use the installed gate, for example:

```sh
python3 .oci-founder-kit/skills/oci-deploy/scripts/deploy_gate.py backend-plan \\
  --dir terraform --operation init --backend-config terraform/backend.tfbackend.json
```

Prepare private target variables and backend configuration first, following the
[state guide](.oci-founder-kit/skills/oci-deploy/references/backend-state.md).
This command prepares an offline approval packet; it does not initialize a
backend or deploy the app. Review and approve each exact operation separately.
Use this project's terraform/ or registry/ as the target. Do not deploy or edit
the hidden toolkit's bundled app instead of app/. Creation verified no hosted
identity, OCI access, deployment or recovery; record actual checks in
[docs/PROGRESS.md](docs/PROGRESS.md).
""", encoding="utf-8")
    (stage / "AGENTS.md").write_text("""# Working on this app

This project's application source is app/. Its infrastructure source is
terraform/ and registry/. Keep the existing framework and database unless the
user explicitly requests a change. The installed .oci-founder-kit/ is tooling;
do not edit or deploy its bundled example instead of this project's source.

Use oci-kit for setup, build and migration work. Read the installed source skill
at .oci-founder-kit/skills/oci-kit/SKILL.md if discovery is unavailable. Preserve
the user's target and approval boundaries. Never request or publish credentials.

Run local checks appropriate to a change. Record real evidence and the next
action in docs/PROGRESS.md; creation, a valid manifest or a plan is not evidence
that application, OCI, security or recovery checks passed. Keep local development
moving while OCI enrollment is incomplete. Every cloud write waits for the
owner's approval of its exact plan, target, permissions and dated cost basis.
""", encoding="utf-8")
    (stage / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (stage / "docs").mkdir()
    (stage / "docs/PROGRESS.md").write_text("""# Project progress

Creation copied source and installed local skills. It did not run application,
credential, infrastructure or recovery checks. Update this manual evidence record
after performing each check; keep secret values and private receipts outside it.

| Checkpoint | Status | Evidence | Next action |
| --- | --- | --- | --- |
| Useful local app | Not started | None recorded | Run python3 local_preview.py start and exercise the main task workflow |
| Application tests | Not started | None recorded | Run the app's tests and record the command and result |
| OCI access and target | Not started | None recorded | Use oci-ready without exposing credential values |
| Foundation and design | Not started | None recorded | Review scoped IAM and OCI Well-Architected decisions |
| Cloud plan and cost | Not started | None recorded | Prepare the exact private plan and dated estimate for approval |
| Deployment and security | Not started | None recorded | Verify only after an approved deployment |
| Recovery and cleanup | Not started | None recorded | Agree retention, rehearse recovery and approve exact cleanup separately |
""", encoding="utf-8")
    ignored = ["# Local development and private cloud files", ".local-preview/", "node_modules/",
               ".next/", ".vercel/", ".netlify/", ".env", ".env.*", "*.pem", "*.key",
               "*.p12", "*.pfx", ".oci/", ".terraform/", ".gate/", "*.tfvars", "*.tfvars.json",
               "*.tfbackend", "*.tfbackend.json", "*.tfstate", "*.tfstate.*", "*.tfplan", "tfplan*",
               "crash.log", "__pycache__/", "*.pyc", "", "# Per-user toolkit installation",
               "/.oci-founder-kit/"]
    agent_directories = {"codex": ".agents", "claude": ".claude"}
    for agent in installation["agents"]:
        ignored.extend(f"/{agent_directories[agent]}/skills/{skill}/" for skill in installation["skills"])
    (stage / ".gitignore").write_text("\n".join(ignored) + "\n", encoding="utf-8")


def export_sources(root: Path, name: str) -> tuple[object, list[tuple[Path, Path]]]:
    blueprint = sibling(root, "blueprint")
    contract = blueprint.load(name, root=root)
    if name != "fullstack-container" or contract["paths"]["app"] != "app" or contract["paths"]["infrastructure"] != "terraform":
        raise ValueError("This blueprint does not have a supported editable-project layout.")
    base = root / "blueprints" / name
    for path in ("app/package.json", "app/src/server.js", "terraform/versions.tf", "registry/main.tf",
                 "local_preview.py", "compose.local.yaml"):
        blueprint.local_path(base, path, directory=False)
    installer = sibling(root, "install")
    selected = []
    for source in installer.source_files():
        relative = source.relative_to(root)
        if relative == Path("LICENSE"):
            selected.append((source, Path("LICENSE")))
        elif relative.parts[:2] == ("blueprints", name):
            exported = Path(*relative.parts[2:])
            if exported.parts[0] in {"app", "terraform", "registry"} or exported.as_posix() in {"local_preview.py", "compose.local.yaml"}:
                selected.append((source, exported))
    required = {Path(value) for value in ("LICENSE", "app/package.json", "app/src/server.js",
                                        "terraform/versions.tf", "registry/main.tf",
                                        "local_preview.py", "compose.local.yaml")}
    if not required.issubset({path for _, path in selected}):
        raise ValueError("Required export files must be distributable regular files.")
    return installer, selected


def prepare(root: Path, name: str, stage: Path, agent: str) -> dict:
    installer, selected = export_sources(root, name)
    for source, relative in selected:
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
    installation = installer.install(stage, agent)
    guidance(stage, installation)
    return installation


def publish_file(source: Path, directory_fd: int, name: str) -> None:
    content = source.read_bytes()
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fchmod(handle.fileno(), 0o755 if source.stat().st_mode & 0o111 else 0o644)


def open_parent(root_fd: int, parts: tuple[str, ...]) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def publish(stage: Path, root_fd: int, relative: tuple[str, ...] = ()) -> None:
    directory_fd = open_parent(root_fd, relative)
    try:
        for source in sorted(stage.iterdir()):
            path = (*relative, source.name)
            if source.is_symlink():
                raise ValueError("Staged links are refused.")
            if source.is_dir():
                os.mkdir(source.name, mode=0o755, dir_fd=directory_fd)
                publish(source, root_fd, path)
            else:
                publish_file(source, directory_fd, source.name)
    finally:
        os.close(directory_fd)


def create(name: str, project: Path, agent: str, dry_run: bool = False, *, root: Path = ROOT) -> dict:
    root = root.resolve(strict=True)
    export_sources(root, name)  # Dry runs validate the same layout and required source as creation.
    if name != "fullstack-container" or agent not in {"codex", "claude", "both"}:
        raise ValueError("Unsupported blueprint or agent.")
    if (os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd
            or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")):
        raise ValueError("Project creation requires supported local filesystem operations; use Linux, macOS or WSL2.")
    with target_path(project, root) as (project, previous, parent_fd):
        return create_in_parent(name, project, agent, dry_run, root, previous, parent_fd)


def create_in_parent(name: str, project: Path, agent: str, dry_run: bool,
                     root: Path, previous: tuple[int, int] | None, parent_fd: int) -> dict:
    report = {"schema": "oci-kit-created-project/1", "project": str(project), "blueprint": name,
              "agent": agent, "status": "dry_run" if dry_run else "created",
              "checks": {"application": "not_run", "oci_access": "not_run", "cloud": "not_run", "recovery": "not_run"},
              "commands": {
                  "preview": {"cwd": str(project), "argv": ["python3", "local_preview.py", "start"]},
                  "application_install": {"cwd": str(project), "argv": ["npm", "--prefix", "app", "ci", "--ignore-scripts"]},
                  "application_tests": {"cwd": str(project), "argv": ["npm", "--prefix", "app", "test"]},
                  "agent": {"cwd": str(project), "argv": ["codex" if agent in {"codex", "both"} else "claude"]}},
              "scope": "Source creation preview only; no files written." if dry_run else
                       "Source copied and local skills installed only. No dependency install, tool execution, credential inspection or cloud operations."}
    if dry_run:
        return report
    # Staging is private and separate from a caller-controlled destination path.
    with tempfile.TemporaryDirectory(prefix=".oci-kit-create-") as temporary:
        stage = Path(temporary) / "project"
        stage.mkdir()
        installation = prepare(root, name, stage, agent)
        check_parent(project, parent_fd)
        if previous is None:
            os.mkdir(project.name, mode=0o755, dir_fd=parent_fd)
        root_fd = os.open(project.name, DIRECTORY_FLAGS, dir_fd=parent_fd)
        identity = os.fstat(root_fd)
        try:
            if previous is not None and (identity.st_dev, identity.st_ino) != previous:
                raise ValueError("Project directory changed during creation.")
            check_parent(project, parent_fd)
            if os.listdir(root_fd):
                raise ValueError("The project is no longer empty.")
            publish(stage, root_fd)
            check_parent(project, parent_fd)
            current = os.stat(project.name, dir_fd=parent_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise ValueError("Project directory changed during creation.")
        finally:
            os.close(root_fd)
    report["kit_version"] = installation["kit_version"]
    return report
