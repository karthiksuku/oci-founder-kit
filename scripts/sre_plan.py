"""Inspect an existing app without running it. A test plan is never test evidence."""
import os
import re
import stat

# Human-readable acceptance criteria, also returned verbatim to both coding agents.
STAGES = {
    "pull_request": ["Build, type/lint and unit checks using the project's reviewed commands.",
                     "Exercise an API boundary, invalid input and a real disposable dependency.",
                     "For a UI change check browser behavior, keyboard navigation and accessible names.",
                     "Scan source, dependencies and Terraform; untrusted PR jobs have no cloud secrets."],
    "candidate": ["Build once; record source revision, manifest digest and a private software inventory.",
                  "Test the exact image: direct HTTP 200, startup, graceful shutdown and missing configuration.",
                  "Run the named user journey; reload and verify private data stays isolated between two test users."],
    "rehearsal": ["Bound traffic, duration and concurrency; compare latency and errors with the agreed objective.",
                  "Exercise a dependency timeout and demonstrate recovery.",
                  "Restore owned data to an isolated target; measure elapsed recovery time and recovered data age.",
                  "Roll back the image and repeat the user journey.",
                  "Demonstrate an alert reaches the responder and recovery clears it."],
    "production": ["Re-evaluate signed evidence against the exact saved plan and get separate owner approval.",
                   "Read back the deployed digest; verify HTTPS and a read-only customer action.",
                   "Monitor real request success and latency separately from probes; re-scan the running digest daily."],
}


def ordinary(fd, name):
    try:
        return stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return False


def workflow_count(fd, p):
    opened = []
    try:
        for part in (".github", "workflows"):
            opened.append(os.open(part, p.DIRECTORY, dir_fd=opened[-1] if opened else fd))
        entries = os.listdir(opened[-1])
        if len(entries) > 512:
            raise ValueError("Workflow directory exceeds inspection limit.")
        return sum(ordinary(opened[-1], n) for n in entries if n.endswith((".yaml", ".yml")))
    except FileNotFoundError:
        return 0
    finally:
        for directory in reversed(opened):
            os.close(directory)


def journey_declaration(directory, p):
    """Return nonsecret identifiers for the exact private journey, never its assertions."""
    try:
        declaration = p.object_at(directory, "sre-journey.json", private=True)
    except FileNotFoundError:
        return None
    if (set(declaration) != {"schema", "journey", "assertions"}
            or declaration["schema"] != "oci-sre-journey/1" or not isinstance(declaration["journey"], str)
            or not re.fullmatch("[a-z][a-z0-9-]{1,47}", declaration["journey"])
            or not isinstance(declaration["assertions"], list) or not 1 <= len(declaration["assertions"]) <= 12
            or any(not isinstance(a, str) or not a.strip() or len(a) > 180 or not a.isprintable() for a in declaration["assertions"])):
        raise ValueError("Invalid private critical journey; supply a short name and 1-12 expected customer outcomes.")
    return {"journey": declaration["journey"], "journey_sha256": p.digest(p.canonical(declaration)),
            "assertion_count": len(declaration["assertions"])}


def inspect_application(store, state, p):
    """Inspect only the descriptor-selected app, returning metadata and reviewed source paths."""
    pkg = p.helper("packaging")
    try:
        desc = pkg.descriptor_value(p.object_at(store.fd, "application.json", private=True))
    except FileNotFoundError:
        desc = None
    fd = pkg.app_fd(store, desc, p) if desc else os.dup(store.root_fd)
    blueprint = store.environment_config["blueprint"]
    try:
        if not desc and blueprint == "fullstack-container" and not ordinary(fd, "package.json"):
            try:
                nested = os.open("app", p.DIRECTORY, dir_fd=fd)
            except FileNotFoundError:
                pass
            else:
                os.close(fd)
                fd = nested
        package = p.object_at(fd, "package.json") if ordinary(fd, "package.json") else {}
        scripts = package.get("scripts", {})
        known = [n for n in ("build", "lint", "typecheck", "test", "test:integration", "test:e2e")
                 if isinstance(scripts, dict) and isinstance(scripts.get(n), str) and scripts[n].strip()]
        locks = [n for n in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements.txt", "poetry.lock", "uv.lock")
                 if ordinary(fd, n)]
    finally:
        os.close(fd)
    next_declared = any(isinstance(deps, dict) and isinstance(deps.get("next"), str) and deps["next"].strip()
                        for deps in (package.get("dependencies"), package.get("devDependencies")))
    profile = "other-container"
    if blueprint == "fullstack-container":
        profile = "taskboard"
    elif state["task"] == "migrate" and (next_declared or desc and desc["recipe"] == "nextjs"):
        profile = "hosting-first-nextjs"
    elif state["task"] == "build" and next_declared and (not desc or desc["recipe"] in {"nextjs", "dockerfile"}):
        profile = "new-app-nextjs"
    info = {"profile": profile, "app_descriptor": desc is not None,
            "test_command_declared": bool(desc and desc["commands"]["test"]) or "test" in known,
            "discovered_scripts": known, "dependency_files": locks}
    app_dir = desc["app_directory"] if desc else "."
    tracked_inputs = [name if app_dir == "." else app_dir + "/" + name for name in ("package.json", "package-lock.json")]
    if profile == "new-app-nextjs":
        # A private app-directory/command change must invalidate a signed monorepo launch.
        info["application_selection_sha256"] = p.digest(p.canonical({"descriptor": desc, "manifest": package}))
    return info, tracked_inputs


def launch_route(store, state, p):
    """Founder continuation for the selected rehearsal; never runs app commands or claims eligibility."""
    try:
        info, _ = inspect_application(store, state, p)
    except (OSError, ValueError, TypeError, RecursionError):
        return {"profile": "unknown", "instruction": "Review the selected application descriptor and package manifest."}
    supported = info["profile"] != "other-container"
    return {"profile": info["profile"], "support": "preview" if supported else "diagnostic-only", "recheck_command": [
        "python3", ".oci-founder-kit/scripts/kit.py", "sre", "plan", "--project", ".", "--environment", store.environment],
        "instruction": ("Review the existing project tests and define the customer action to exercise on the rehearsal hostname."
                        if supported else "Use the diagnostic plan for local checks. This workload has no verified production profile.")}


def request(project, *, environment, p):
    with p.Store(project, environment=environment) as store:
        state = store.read()
        if store.environment_config["role"] != "rehearsal":
            raise ValueError("Select a rehearsal environment to plan application testing.")
        info, _ = inspect_application(store, state, p)
        profile = info["profile"]
        declaration = journey_declaration(store.fd, p)
        workflow = ("Sign in, create a task, reload, and confirm a second user cannot see it." if profile == "taskboard"
                    else "Select one existing customer action and compare its visible result on source and target."
                    if state["task"] == "migrate" else "Select the one customer action that must work after deployment.")
        stages = {key: list(items) for key, items in STAGES.items()}
        if state["task"] == "migrate":
            stages["rehearsal"].append("Compare source/target routes and retained providers, prove one scheduler owner, and rehearse restoring source traffic.")
        if profile == "new-app-nextjs":
            stages["rehearsal"].append("Verify the chosen hostname and TLS chain, hosted sign-in callback/logout/expiry, retained identity and data providers, and persistence after a scoped restart. Use synthetic accounts and data.")
        return {"schema": "oci-kit-sre-plan/1", "status": "planned", "environment": environment,
                **info, "support": "diagnostic-only" if profile == "other-container" else "preview", "existing_workflow_count": workflow_count(store.root_fd, p),
                "critical_journey_prompt": workflow, "critical_journey_declared": declaration is not None,
                "critical_journey": declaration["journey"] if declaration else None,
                "journey_sha256": declaration["journey_sha256"] if declaration else None,
                "assertion_count": declaration["assertion_count"] if declaration else 0, "stages": stages,
                "extensions": ["worker: retry, duplicate delivery and idempotency", "schema change: old/new reader and rollback compatibility",
                               "UI: manual keyboard and accessibility review"],
                "next_action": "Confirm the critical customer journey and its assertions with the owner. Review the existing commands before running them.",
                "production_ready": False, "cloud_requests": False, "approval_granted": False}
