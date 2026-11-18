"""First-run guidance and additive local preparation using existing kit helpers.

No account activation, credential creation, executable discovery probes, application
commands or cloud requests run here. Authentication discovery reads only an explicitly
selected profile's config; private key and session token contents are never read.
"""
from __future__ import annotations

import configparser
import importlib.util
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
GUIDE = "docs/NEW-OCI-ACCOUNT.md"


def common_module():
    spec = importlib.util.spec_from_file_location("oci_onboarding_common", ROOT / "scripts/kit_common.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def project_path(path, p):
    path = Path(path).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Symlinked project paths are refused.")
    if path.exists():
        _, fd = p.open_project(path)
        os.close(fd)
    elif not path.parent.is_dir():
        raise ValueError("Create the project parent directory first.")
    return path


def command(*words, environment=None):
    return ["python3", ".oci-founder-kit/scripts/kit.py", *words, "--project", ".",
            *(["--environment", environment] if environment else [])]


def context(project, environment, p, common, *, allow_new=False):
    path = project_path(project, p)
    present = path.is_dir()
    installed = p.helper("install").status(path) if present else {"installed": False}
    configs, state = [], None
    if (path / ".oci-kit").exists():
        with p.Store(path) as store:
            state = store.read()
            configs = p.helper("environments").list_configs(store, p)
    if environment is not None and not p.helper("environments").NAME.fullmatch(environment):
        raise common.KitError("UNSAFE_INPUT")
    selected = next((c for c in configs if c["name"] == environment), None)
    if configs and environment and selected is None and not allow_new:
        raise common.KitError("ENVIRONMENT_UNKNOWN", missing=("environment",))
    if installed.get("installed"):
        release = p.helper("install").manifest_module()
        installed["same_release"] = release.read_file(path / ".oci-founder-kit", "release-manifest.json") == release.read_file(ROOT, "release-manifest.json")
    return path, installed, configs, state, selected


def access(config_file, profile, auth, region, p):
    doctor = p.helper("readiness").load("skills/oci-ready/scripts/oci_doctor.py")
    if ((profile is not None and not doctor.PROFILE.fullmatch(profile))
            or (region is not None and not doctor.REGION.fullmatch(region))
            or auth not in {None, "api_key", "security_token"}):
        raise ValueError("Invalid explicit authentication selection.")
    missing = [key for key, value in (("profile", profile), ("auth", auth), ("region", region)) if not value]
    # Presence is not authentication. Never select DEFAULT or inspect token contents.
    config = Path(config_file).expanduser().absolute()
    if not profile or not auth:
        return {"status": "not_selected", "config_present": config.exists(), "missing": missing,
                "identity": "not_checked", "session_expiry": "not_checked"}
    try:
        values, checks = doctor.read_profile(config, profile, auth)
    except (ValueError, OSError, configparser.Error):
        values, checks = {}, [{"status": "blocked"}]
    configured = bool(values) and not any(c["status"] == "blocked" for c in checks)
    return {"status": "configured" if configured else "needs_setup", "config_present": config.exists(),
            "missing": missing, "identity": "not_checked", "session_expiry": "not_checked"}


def inspect(project, *, environment=None, config_file=Path("~/.oci/config"), profile=None,
            auth=None, region=None, which=shutil.which):
    common = common_module(); p = common.project_module()
    path, installed, configs, state, selected = context(project, environment, p, common)
    target = selected["target"] if selected else {}
    chosen = {"profile": profile or target.get("profile"), "auth": auth or target.get("auth"),
              "region": region or target.get("region")}
    for key, value in (("profile", profile), ("auth", auth), ("region", region)):
        if value and target.get(key) and value != target[key]:
            raise common.KitError("ONBOARD_TARGET_CONFLICT", missing=(key,))
    credentials = access(config_file, **chosen, p=p)
    tools = {name: "available" if which(name) else "missing" for name in ("git", "oci", "terraform", "docker")}
    tools["python"] = "available" if sys.version_info >= (3, 11) else "unsupported"
    setup = bool(state and installed.get("installed") and installed.get("same_release") and not installed.get("missing_entries") and selected)
    missing = [*credentials["missing"]]
    if not selected:
        missing.extend(["environment", "role"])
    checks = [
        {"id": "account", "status": "owner_action", "owner": "account-owner",
         "action": "Use Oracle's activation email, complete sign-in/MFA and establish account recovery. Keep passwords and activation links out of agent prompts.", "guide": GUIDE + "#authenticate-without-sharing-credentials"},
        {"id": "local-project", "status": "prepared" if setup else "needs_setup", "owner": "agent",
         "action": "Prepare the existing app and an explicitly named environment. This installs local kit files and adds deployment definitions without replacing application code.",
         "guide": GUIDE + "#prepare-your-local-environment"},
        {"id": "authentication", "status": credentials["status"], "owner": "founder",
         "action": "Install OCI CLI if missing, reuse an explicitly selected profile or complete browser session authentication. Config presence does not prove valid or unexpired access.",
         "guide": "skills/oci-ready/references/credentials.md"},
        {"id": "administrator-bootstrap", "status": "unknown", "owner": "authorized-administrator",
         "action": "Confirm the home region, an initial non-root parent, the intended identity-domain users/group and reviewed membership. Verify scoped permissions and inherited access before foundation creation.",
         "guide": GUIDE + "#administrator-handoff-for-an-empty-tenancy"},
        {"id": "foundation", "status": "not_checked", "owner": "agent-and-owner",
         "action": "Inspect approved resources, then prepare separate plans for compartments, networking, private state and registry. Review costs and approve each exact cloud plan before execution.",
         "guide": "blueprints/workload-foundation/README.md"},
        {"id": "application-and-https", "status": "not_checked", "owner": "agent-and-owner",
         "action": "Build and test locally; package the exact image; select hostname, certificate and renewal ownership. Preserve external data and identity during hosting migration.",
         "guide": "docs/WORKFLOW.md"},
        {"id": "deployment-and-recovery", "status": "not_checked", "owner": "agent-and-owner",
         "action": "Approve the exact deployment plan, then verify HTTPS, application access, persistence and isolated recovery. Terraform creation alone is not Well-Architected acceptance.",
         "guide": "skills/oci-foundation/references/well-architected.md"},
    ]
    if installed.get("installed") and (not installed.get("same_release") or installed.get("missing_entries")):
        next_action = {"phase": "installation", "owner": "agent", "instruction": "Review the existing installation and use the backed-up kit update path before onboarding. Preserve local skills, application files and private records.",
                       "guide": "docs/INSTALL.md#update-or-remove-a-project-installation",
                       "command": ["python3", str(ROOT / "scripts/install.py"), "--project", str(path), "--status"]}
    elif selected and selected["role"] == "source":
        next_action = {"phase": "environment", "owner": "founder", "instruction": "This is retained source hosting. Select an existing OCI rehearsal environment or prepare a separate one; the source is never a deployment target.",
                       "command": command("environment", "list")}
    elif configs and not environment:
        next_action = {"phase": "environment", "owner": "founder", "instruction": "Select one of the existing environments explicitly; none was chosen automatically.",
                       "command": command("environment", "list")}
    elif not setup:
        next_action = {"phase": "local-project", "owner": "agent", "instruction": "Choose an environment and role, then run onboard prepare. Use --dry-run to inspect the additive local changes first.",
                       "command": ["python3", str(ROOT / "scripts/kit.py"), "onboard", "prepare", "--project", str(path),
                                   "--environment", environment or "rehearsal", "--role", "rehearsal",
                                   "--mode", "existing" if path.exists() else "new", "--dry-run"],
                       "suggested_only": True}
    elif tools["oci"] == "missing":
        next_action = {"phase": "authentication", "owner": "founder", "instruction": "Install OCI CLI using Oracle's installation guide, then recheck onboarding.",
                       "guide": "https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm",
                       "command": command("onboard", "inspect", environment=environment)}
    elif credentials["missing"] or credentials["status"] != "configured":
        next_action = {"phase": "authentication", "owner": "founder", "instruction": "Select the profile, authentication method and workload region together. For a new browser session follow the credential guide; keep credentials outside the app.",
                       "guide": "skills/oci-ready/references/credentials.md",
                       "command": command("onboard", "inspect", environment=environment)}
    elif any(target.get(key) != value for key, value in chosen.items()):
        next_action = {"phase": "configuration", "owner": "founder", "instruction": "Save these explicit access choices in the private environment before using doctor or foundation. This local operation backs up configuration and invalidates affected evidence; it grants no OCI access.",
                       "command": command("onboard", "configure", *[part for key, value in chosen.items() for part in ("--" + key, value)], environment=environment)}
    elif not target.get("compartment_id"):
        next_action = {"phase": "administrator-bootstrap", "owner": "authorized-administrator", "instruction": checks[3]["action"],
                       "guide": checks[3]["guide"], "command": command("foundation", "inspect", environment=environment)}
    else:
        next_action = {"phase": "readiness", "owner": "agent", "instruction": "Run the selected environment's doctor. Explicit --live enables bounded reads; deployment permission and capacity still need review.",
                       "command": command("doctor", environment=environment)}
    # Commands must work from the checkout as well as from inside the app. This
    # local report can contain paths, but never config values or credential data.
    if next_action["phase"] != "installation":
        next_action["command"][1] = str((path / ".oci-founder-kit" if installed.get("installed") else ROOT) / "scripts/kit.py")
        next_action["command"][next_action["command"].index("--project") + 1] = str(path)
        if next_action["phase"] in {"authentication", "configuration", "readiness"} and Path(config_file) != Path("~/.oci/config"):
            next_action["command"] += ["--config-file", str(Path(config_file).expanduser().absolute())]
    return {"schema": "oci-kit-onboarding/1", "status": "guidance", "mode": "local-only",
            "environment": environment, "environments": [{"name": c["name"], "role": c["role"]} for c in configs],
            "installation": "present" if installed.get("installed") else "absent", "tools": tools,
            "authentication": credentials, "missing": sorted(set(missing)), "phases": checks,
            "next_action": next_action, "cloud": "not_checked", "approval_granted": False,
            "application_commands_run": False, "profile_selected_automatically": False,
            "well_architected": "review-required", "guide": GUIDE}


def configure(project, *, environment=None, profile=None, region=None, auth=None, config_file=Path("~/.oci/config")):
    common = common_module(); p = common.project_module()
    missing = [key for key, value in (("environment", environment), ("profile", profile), ("region", region), ("auth", auth)) if not value]
    if missing:
        raise common.KitError("INPUTS_REQUIRED", missing=missing)
    common.select(project, environment, required=True)
    env = p.helper("environments")
    with p.Store(project, environment=environment) as store:
        store.read()
        # Derive the merged target and the optimistic write binding from the same
        # locked snapshot. An earlier discovery read cannot overwrite a newer edit.
        selected = store.environment_config
        if selected["role"] == "source":
            raise common.KitError("ONBOARD_TARGET_CONFLICT")
        target = dict(selected["target"], profile=profile, region=region, auth=auth)
        has_resources = bool(selected.get("backend") or selected.get("components") or any(key.endswith("_id") for key in target))
        if has_resources and any(
                selected["target"].get(key) and selected["target"][key] != target[key] for key in ("region", "profile")):
            raise common.KitError("ONBOARD_TARGET_CONFLICT")
        env.validate(dict(selected, target=target))
        binding = common.bound(store, p, "oci-kit-onboarding/1")
    result = env.configure(project, name=environment, target=target,
                           expected_binding={key: binding[key] for key in ("target_sha256", "source_sha256", "kit_sha256")})
    path = Path(project).expanduser().absolute()
    next_command = ["python3", str(ROOT / "scripts/kit.py"), "onboard", "inspect", "--project", str(path), "--environment", environment]
    if Path(config_file) != Path("~/.oci/config"):
        next_command += ["--config-file", str(Path(config_file).expanduser().absolute())]
    return {"schema": "oci-kit-onboarding/1", "status": "configured" if result["changed"] else "unchanged", "mode": "local-only",
            "environment": environment, "changes": ["save-selected-access"] if result["changed"] else [],
            "previous_evidence": "stale" if result["changed"] else "unchanged", "approval_granted": False, "cloud": "not_checked",
            "next_action": {"instruction": "Recheck the saved selections. Authentication and OCI access remain unverified.", "command": next_command}}


def prepare(project, *, environment=None, role=None, mode="existing", task=None, agent=None,
            stack=None, target_file=None, dry_run=False):
    common = common_module(); p = common.project_module(); env = p.helper("environments")
    missing = [key for key, value in (("environment", environment), ("role", role)) if not value]
    if missing:
        raise common.KitError("INPUTS_REQUIRED", missing=missing)
    if role not in {"rehearsal", "production"} or mode not in {"new", "existing"}:
        raise common.KitError("UNSAFE_INPUT")
    path, installed, configs, state, selected = context(project, environment, p, common, allow_new=True)
    if not path.exists() and mode != "new":
        raise common.KitError("PROJECT_REQUIRED")
    target = env.read_target(target_file) if target_file else {}
    directory = "deploy/" + environment
    infrastructure = directory + "/terraform"
    proposal = {"schema": "oci-kit-environment/1", "name": environment, "role": role,
                "blueprint": "web-container", "infrastructure": infrastructure, "target": target, "backend": None}
    installed_agents = installed.get("agents", [])
    existing_agent = installed_agents[0] if len(installed_agents) == 1 else "both"
    options = {"task": task or (state or {}).get("task", "build"),
               "agent": agent or (state or {}).get("agent", existing_agent),
               "stack": stack or (state or {}).get("stack", "auto")}
    if (options["task"] not in p.TASKS or options["agent"] not in p.AGENTS or options["stack"] not in p.STACKS
            or (mode == "new" and options["task"] != "build")):
        raise common.KitError("UNSAFE_INPUT")
    if state and any(state[k] != v for k, v in options.items()):
        raise common.KitError("ONBOARD_PROJECT_CONFLICT")
    if installed.get("installed"):
        installer = p.helper("install")
        release = installer.manifest_module()
        bundle = path / ".oci-founder-kit"
        release.verified(bundle, lambda item: installer.distributable(ROOT / item.relative_to(bundle)))
        required_agents = {"claude", "codex"} if options["agent"] == "both" else {options["agent"]}
        if (not required_agents.issubset(installed_agents) or installed.get("missing_entries") or
                release.read_file(path / ".oci-founder-kit", "release-manifest.json") != release.read_file(ROOT, "release-manifest.json")):
            raise common.KitError("ONBOARD_UPDATE_REQUIRED")
    if selected:
        if not installed.get("installed"):
            raise common.KitError("ONBOARD_UPDATE_REQUIRED")
        if selected["role"] != role or (target_file and selected["target"] != target):
            raise common.KitError("ONBOARD_TARGET_CONFLICT")
        # Resume existing configuration without rebinding infrastructure or copying approvals.
        result = inspect(path, environment=environment)
        result.update(status="unchanged", changes=[], dry_run=dry_run)
        return result
    env.validate_isolation(proposal, configs)
    if (path / directory).exists() or (path / directory).is_symlink():
        raise common.KitError("ONBOARD_DESTINATION_EXISTS")
    installer = p.helper("install")
    installer.manifest_module().verified(ROOT, installer.distributable)
    if path.exists():
        if not installed.get("installed"):
            installer.install(path, options["agent"], dry_run=True)
        p.helper("deployment_scaffold").attach("web-container", path, directory, dry_run=True, root=ROOT)
    changes = ([] if installed.get("installed") else ["install-project-local-kit"]) + ([] if state else ["initialize-private-project-record"])
    changes += ["attach-web-container-deployment", "create-explicit-environment"]
    next_command = ["python3", str(path / ".oci-founder-kit/scripts/kit.py"), "onboard", "inspect",
                    "--project", str(path), "--environment", environment]
    if dry_run:
        next_command = ["python3", str(ROOT / "scripts/kit.py"), "onboard", "prepare", "--project", str(path),
                        "--environment", environment, "--role", role, "--mode", mode,
                        *[part for key, value in options.items() for part in ("--" + key, value)],
                        *(["--target-file", str(Path(target_file).expanduser().absolute())] if target_file else [])]
    result = {"schema": "oci-kit-onboarding/1", "status": "proposed" if dry_run else "prepared", "mode": "local-only",
              "environment": environment, "role": role, "infrastructure": infrastructure, "changes": changes,
              "dry_run": dry_run, "application": "preserved", "cloud": "not_checked", "approval_granted": False,
              "next_action": {"instruction": "Review these local changes, then run prepare without --dry-run." if dry_run else "Inspect onboarding and complete the next prerequisite.",
                              "command": next_command}}
    if dry_run:
        return result
    if state is None:
        p.start(path, mode=mode, **options)
    elif not installed.get("installed"):
        installer.install(path, options["agent"])
    p.helper("deployment_scaffold").attach("web-container", path, directory, root=ROOT)
    env.create(path, name=environment, role=role, infrastructure=infrastructure, target=target)
    return result


def render(value):
    print("OCI onboarding · " + value["status"] + " · local only")
    if "tools" in value:
        print("Tools: " + ", ".join(k + "=" + v for k, v in value["tools"].items()))
        for phase in value["phases"]:
            print(f"{phase['id']}: {phase['status']} · {phase['owner']}")
        if value["missing"]:
            print("Missing choices: " + ", ".join(value["missing"]))
    else:
        print("Local changes: " + ", ".join(value["changes"]))
    print("Next: " + value["next_action"]["instruction"])
    import shlex
    print(shlex.join(value["next_action"]["command"]))
    print("Guide: " + value.get("guide", GUIDE))
