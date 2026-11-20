#!/usr/bin/env python3
"""One project-local interface over the kit's existing helpers and approval gates."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]


def common_module():
    spec = importlib.util.spec_from_file_location("oci_kit_common", ROOT / "scripts/kit_common.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes arbitrary user input, including accidental secrets.
        raise ValueError("Invalid command arguments; use --help.")


def parser():
    cli = Parser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True, parser_class=Parser)
    for name in ("onboard", "start", "status", "next", "doctor", "sre", "trial", "cost", "package", "foundation", "release", "verify", "observe", "architecture", "journey", "support", "environment", "capabilities"):
        child = commands.add_parser(name)
        child.add_argument("--project", type=Path, default=Path("."))
        child.add_argument("--environment")
        child.add_argument("--json", action="store_true")
        child.add_argument("--non-interactive", action="store_true", help="Never prompt; missing choices return a structured blocked result.")
        if name == "onboard":
            child.add_argument("action", choices=("inspect", "prepare", "configure"))
            child.add_argument("--role", choices=("rehearsal", "production"))
            child.add_argument("--mode", choices=("new", "existing"), default="existing")
            child.add_argument("--task", choices=("build", "migrate", "setup"))
            child.add_argument("--agent", choices=("claude", "codex", "both"))
            child.add_argument("--stack", choices=("auto", "nextjs", "fastapi", "custom"))
            child.add_argument("--target-file", type=Path)
            child.add_argument("--dry-run", action="store_true")
            child.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
            child.add_argument("--profile")
            child.add_argument("--region")
            child.add_argument("--auth", choices=("api_key", "security_token"))
        if name == "start":
            child.add_argument("--task", choices=("build", "migrate", "setup"), default="build")
            child.add_argument("--mode", choices=("new", "existing", "continue"), default="existing")
            child.add_argument("--agent", choices=("claude", "codex", "both"), default="both")
            child.add_argument("--stack", choices=("auto", "nextjs", "fastapi", "custom"), default="auto")
            child.add_argument("--blueprint", choices=("fullstack-container",))
        if name in {"doctor", "observe", "sre"}:
            child.add_argument("--live", action="store_true")
            child.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
        if name == "package":
            child.add_argument("action", choices=("inspect", "propose", "apply", "verify"))
            child.add_argument("--descriptor", type=Path)
            child.add_argument("--approve")
            child.add_argument("--image")
            child.add_argument("--layout", type=Path)
        if name == "foundation":
            child.add_argument("action", choices=("inspect", "propose", "prepare", "handoff"))
            child.add_argument("--config", type=Path)
            child.add_argument("--outputs", type=Path)
            child.add_argument("--approve")
        if name == "verify":
            child.add_argument("--kind", choices=("runtime", "migration"), default="runtime")
            child.add_argument("--contract", type=Path)
            child.add_argument("--sessions-file", type=Path)
            child.add_argument("--ca-file", type=Path)
        if name == "observe":
            child.add_argument("--receipt", type=Path)
            child.add_argument("--cost-config", type=Path)
            child.add_argument("--component", choices=("web", "worker"), default="web")
        if name == "trial":
            child.add_argument("action", choices=("inspect", "prepare", "feedback", "close"))
            child.add_argument("--input", type=Path, help="Owner-only trial review or de-identified feedback file.")
            child.add_argument("--trial-id")
        if name == "cost":
            child.add_argument("action", choices=("preview",))
            child.add_argument("--rates", type=Path)
            child.add_argument("--assumptions", type=Path)
            child.add_argument("--after-cleanup", type=Path)
        if name == "support":
            child.add_argument("action", choices=("export",))
            child.add_argument("--write", action="store_true", help="Write the displayed allowlisted projection to a new private file; never upload.")
        if name == "sre":
            child.add_argument("action", choices=("plan", "check", "monitor"))
            child.add_argument("--rehearsal")
            child.add_argument("--plan-sha256")
            child.add_argument("--monitor-input", type=Path)
            child.add_argument("--write", action="store_true", help="Save an aggregate-only monitoring snapshot to the private dashboard.")
        if name == "journey":
            child.add_argument("--kind", choices=("build", "migrate"), default="build")
        if name == "environment":
            child.add_argument("action", choices=("list", "create", "configure"))
            child.add_argument("--role", choices=("source", "rehearsal", "production"))
            child.add_argument("--blueprint", choices=("web-container", "fullstack-container"), default="web-container")
            child.add_argument("--infrastructure")
            child.add_argument("--target-file", type=Path)
            child.add_argument("--backend-config", type=Path)
            child.add_argument("--components-file", type=Path)
            child.add_argument("--convert-legacy", action="store_true")
        if name == "release":
            child.add_argument("action", choices=("configure", "init", "plan", "run", "apply", "list", "record", "rollback"))
            child.add_argument("--approve")
            child.add_argument("--config", type=Path, help="Private nonsecret deployment choices for release configure.")
            child.add_argument("--backend-config", type=Path)
            child.add_argument("--var-file", type=Path, action="append", default=[])
            child.add_argument("--receipt", type=Path)
            child.add_argument("--evidence", type=Path)
            child.add_argument("--variables", type=Path)
            child.add_argument("--component", choices=("web", "worker"), default="web")
    return cli


def gate_request(p, common, args, selected):
    roles = p.helper("environments").component_configs(selected)
    component = next((c for c in roles if c["component_role"] == args.component), None)
    if component is None or component["role"] == "source":
        raise common.KitError("INPUTS_REQUIRED", missing=("role", "target"))
    stack = args.project.expanduser().absolute() / component["infrastructure"]
    operation = {"init": "backend-plan", "plan": "backend-plan", "run": "backend-run", "apply": "apply"}[args.action]
    arguments = [operation, "--dir", str(stack)]
    binding = None
    if operation == "backend-plan":
        arguments += ["--project", str(args.project.expanduser().absolute()), "--environment", args.environment,
                      "--operation", "init" if args.action == "init" else "plan"]
        if args.backend_config:
            arguments += ["--backend-config", str(args.backend_config)]
        if args.action == "init" and args.backend_config is None:
            raise common.KitError("INPUTS_REQUIRED", missing=("backend",))
        for file in args.var_file:
            arguments += ["--var-file", str(file)]
    else:
        if not p.valid_hash(args.approve):
            raise common.KitError("APPROVAL_REQUIRED", missing=("approval",))
        # Explicit selection is checked before the existing gate rechecks its exact binding.
        gate = p.helper("readiness").load("skills/oci-deploy/scripts/environment_gate.py")
        if not component.get("backend"):
            raise common.KitError("INPUTS_REQUIRED", missing=("backend",))
        backend = dict(component["backend"], config_file_profile=component["target"].get("profile"),
                       auth={"api_key": "APIKey", "security_token": "SecurityToken"}.get(component["target"].get("auth")))
        binding = gate.select(stack, project=args.project, environment=args.environment, backend=backend)
        if operation == "backend-run":
            envelope = common.private_json(stack / ".gate/backend-plan.json")
            payload = envelope.get("payload", {})
            if (envelope.get("sha256") != args.approve or payload.get("operation") not in {"init", "plan"}
                    or payload.get("project_environment") != binding):
                raise common.KitError("APPROVAL_REQUIRED", missing=("approval",))
        arguments += ["--approve", args.approve]
    # Keep the mature gate's private logs/receipts. Never echo its raw service errors
    # or resource identifiers through the facade's structured error interface.
    class Sink(io.TextIOBase):
        def write(self, value):
            return len(value)
    previous = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT / "skills/oci-deploy/scripts"))
        module = p.helper("readiness").load("skills/oci-deploy/scripts/deploy_gate.py")
        with contextlib.redirect_stdout(Sink()), contextlib.redirect_stderr(Sink()):
            code = module.main(arguments)
    finally:
        sys.path[:] = previous
    if code:
        raise common.KitError("OPERATION_FAILED")
    result = {"schema": "oci-kit-command/1", "status": "completed", "phase": args.action,
              "environment": args.environment, "component": args.component,
              "approval_transferred": False, "next_action": "Review the private gate result before another operation."}
    filename = "backend-plan.json" if operation == "backend-plan" else None
    if operation == "backend-run":
        backend_receipt = common.private_json(stack / ".gate/backend-receipts" / (args.approve + ".json"))
        if (backend_receipt.get("schema") != "oci-backend-receipt/1" or backend_receipt.get("status") != "completed"
                or backend_receipt.get("operation_sha256") != args.approve or backend_receipt.get("project_environment") != binding
                or backend_receipt.get("operation") != payload["operation"] or backend_receipt.get("resource_apply_authorized") is not False):
            raise common.KitError("OPERATION_FAILED")
        filename = "plan-summary.json" if payload["operation"] == "plan" else None
        if filename is None:
            result["next_action"] = "Initialization completed. Prepare a new backend plan operation for this environment and obtain its exact approval."
    if filename:
        value = common.private_json(stack / ".gate" / filename)
        digest = value.get("sha256") if filename == "backend-plan.json" else value.get("plan_sha256")
        if not p.valid_hash(digest):
            raise common.KitError("UNSAFE_INPUT")
        if filename == "plan-summary.json" and (digest != backend_receipt.get("resource_plan_sha256") or value.get("backend_operation_sha256") != args.approve):
            raise common.KitError("UNSAFE_INPUT")
        result.update(status="awaiting-approval", plan_sha256=digest,
                      review_file=str(Path(component["infrastructure"]) / ".gate" / filename),
                      next_action="Review this exact private plan, its costs and expiry; request owner approval of its hash.")
    if args.action == "plan" or filename == "plan-summary.json":
        result["cost_preview_command"] = ["python3", ".oci-founder-kit/scripts/kit.py", "cost", "preview",
                                          "--environment", args.environment]
    return result


def dispatch(args):
    common = common_module(); p = common.project_module()
    if args.command == "capabilities":
        return p.helper("capabilities").registry()
    if args.command == "onboard":
        onboarding = p.helper("onboarding")
        if args.action == "configure":
            if any((args.role, args.task, args.agent, args.stack, args.target_file, args.dry_run)) or args.mode != "existing":
                raise common.KitError("UNSAFE_INPUT")
            return onboarding.configure(args.project, environment=args.environment, profile=args.profile,
                                        region=args.region, auth=args.auth, config_file=args.config_file)
        if args.action == "inspect":
            if any((args.role, args.task, args.agent, args.stack, args.target_file, args.dry_run)) or args.mode != "existing":
                raise common.KitError("UNSAFE_INPUT")
            return onboarding.inspect(args.project, environment=args.environment, config_file=args.config_file,
                                      profile=args.profile, region=args.region, auth=args.auth)
        if args.profile or args.region or args.auth or args.config_file != Path("~/.oci/config"):
            raise common.KitError("UNSAFE_INPUT")
        return onboarding.prepare(args.project, environment=args.environment, role=args.role, mode=args.mode,
                                  task=args.task, agent=args.agent, stack=args.stack,
                                  target_file=args.target_file, dry_run=args.dry_run)
    if args.command == "start":
        if args.mode == "continue" or (args.project / ".oci-kit/state.json").exists():
            common.select(args.project, args.environment)
            return p.resume(args.project, environment=args.environment, refresh=True)
        if args.environment:
            raise common.KitError("ENVIRONMENT_UNKNOWN", missing=("environment",))
        return p.start(args.project, task=args.task, mode=args.mode, agent=args.agent, stack=args.stack, blueprint=args.blueprint)
    if args.command == "environment":
        env = p.helper("environments")
        if args.action == "list":
            return {"schema": "oci-kit-environments/1", "environments": [env.summary(c, p) for c in common.configurations(args.project)], "selected_automatically": False}
        missing = [key for key, val in (("environment", args.environment), ("role", args.role if args.action == "create" else True),
                   ("infrastructure", args.infrastructure if args.action == "create" and args.role != "source" else True),
                   ("target", args.target_file if args.action == "configure" else True)) if not val]
        if missing:
            raise common.KitError("INPUTS_REQUIRED", missing=missing)
        target = env.read_target(args.target_file) if args.target_file else {}
        backend = env.read_backend(args.backend_config) if args.backend_config else None
        if args.action == "create":
            if args.components_file:
                raise common.KitError("UNSAFE_INPUT")
            return env.create(args.project, name=args.environment, role=args.role, blueprint=args.blueprint,
                              infrastructure=args.infrastructure, target=target, backend=backend, convert_legacy=args.convert_legacy)
        components = common.private_json(args.components_file) if args.components_file else None
        return env.configure(args.project, name=args.environment, target=target, backend=backend, components=components)
    selected = common.select(args.project, args.environment, required=args.command not in {"status", "next"})
    if args.command in {"status", "next"}:
        value = p.resume(args.project, environment=args.environment, refresh=args.command == "next")
        value["continuation_command"] = ["python3", ".oci-founder-kit/scripts/kit.py", "next", "--project", "."] + (["--environment", args.environment] if args.environment else [])
        return value
    if args.command == "doctor":
        return p.doctor(args.project, environment=args.environment, config_file=args.config_file, live=args.live)
    if args.command == "verify":
        return p.verify(args.project, environment=args.environment, kind=args.kind, contract=args.contract,
                        sessions_file=args.sessions_file, ca_file=args.ca_file)
    if args.command == "package":
        return p.helper("packaging").request(args.project, environment=args.environment, action=args.action,
                    descriptor=args.descriptor, approve=args.approve, image=args.image, layout=args.layout)
    if args.command == "foundation":
        return p.helper("foundation").request(args.project, environment=args.environment, action=args.action,
                    config=args.config, approve=args.approve, outputs=args.outputs)
    if args.command == "observe":
        return p.helper("operations").request(args.project, environment=args.environment, live=args.live,
                    receipt=args.receipt, config_file=args.config_file, cost_config=args.cost_config, component=args.component)
    if args.command == "sre":
        if args.action != "monitor" and (args.live or args.write or args.config_file != Path("~/.oci/config")):
            raise common.KitError("UNSAFE_INPUT")
        if args.action == "check":
            if not args.rehearsal or not p.valid_hash(args.plan_sha256) or args.monitor_input or selected["role"] != "production":
                raise common.KitError("SRE_CHECK_INPUT")
            return p.helper("sre_gate").request(args.project, environment=args.environment, rehearsal=args.rehearsal,
                                                plan_sha256=args.plan_sha256)
        if args.rehearsal or args.plan_sha256 or (args.action == "plan" and args.monitor_input):
            raise common.KitError("UNSAFE_INPUT")
        if args.action == "monitor":
            return p.helper("sre_monitor").request(args.project, environment=args.environment, input_file=args.monitor_input, live=args.live, config_file=args.config_file, write=args.write)
        if selected["role"] != "rehearsal":
            raise common.KitError("SRE_PLAN_INPUT")
        return p.helper("sre_plan").request(args.project, environment=args.environment, p=p)
    if args.command == "architecture":
        return p.helper("architecture").request(args.project, environment=args.environment)
    if args.command == "journey":
        return p.helper("journey_acceptance").request(args.project, environment=args.environment, journey=args.kind)
    if args.command == "trial":
        if selected["role"] != "rehearsal":
            raise common.KitError("TRIAL_TARGET")
        try:
            return p.helper("customer_trial").request(args.project, action=args.action, environment=args.environment,
                        trial_id=args.trial_id, input_file=args.input, p=p)
        except (KeyError, ValueError, TypeError, OSError):
            raise common.KitError("TRIAL_INPUT") from None
    if args.command == "cost":
        return p.helper("launch_cost").request(args.project, environment=args.environment, rates=args.rates,
                    assumptions=args.assumptions, after_cleanup=args.after_cleanup, p=p)
    if args.command == "support":
        return p.helper("support").request(args.project, environment=args.environment, write=args.write)
    if args.command == "release":
        if args.action == "configure":
            if args.component != "web" or (args.config and args.approve):
                raise common.KitError("DEPLOYMENT_CONFIG_INPUT")
            return p.helper("deployment_config").request(args.project, environment=args.environment,
                action="prepare" if args.approve else "propose" if args.config else "inspect", config=args.config, approve=args.approve)
        if args.action in {"init", "plan", "run", "apply"}:
            return gate_request(p, common, args, selected)
        if args.component != "web":
            raise common.KitError("CAPABILITY_UNAVAILABLE")
        return p.helper("releases").request(args.project, environment=args.environment, action=args.action,
                    receipt=args.receipt, evidence=args.evidence, variables=args.variables, approve=args.approve)
    raise common.KitError("CAPABILITY_UNAVAILABLE")


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    want_json = "--json" in arguments
    common = common_module()
    try:
        args = parser().parse_args(arguments)
        value = dispatch(args)
        if value.get("status") == "blocked" and args.command in {"package", "foundation"}:
            default = "PACKAGE_INPUT_OR_CHECK_FAILED" if args.command == "package" else "FOUNDATION_CONFIG"
            codes = value.get("findings", [])
            codes = [item.get("code") if isinstance(item, dict) else item for item in codes] if isinstance(codes, list) else []
            known = [item for item in codes if isinstance(item, str) and item in common.ERRORS]
            value = common.project_blocked(value, code=value.get("code", known[0] if known else default),
                                          command=args.command, action=args.action, environment=args.environment)
        code = 3 if value.get("status") in {"blocked", "failed"} or (
            args.command in {"architecture", "journey", "sre", "cost", "trial"} and value.get("status") in {"incomplete", "unknown"}) else 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
        value = common.error(getattr(exc, "code", "UNSAFE_INPUT"), missing=getattr(exc, "missing", ()))
        code = 3
    except Exception:
        # Known gate exceptions are deliberately opaque at this boundary.
        value = common.error("OPERATION_FAILED"); code = 3
    if "error" in value:
        command = args.command if "args" in locals() and args.command in {"onboard", "package", "foundation", "doctor", "observe", "architecture", "journey", "release", "environment", "support", "verify", "status", "next", "start", "sre", "cost", "trial"} else None
        value["error"].setdefault("recheck_command", ["python3", ".oci-founder-kit/scripts/kit.py", *([command] if command else []), "--help"])
        if command == "onboard":
            value["error"]["recheck_command"] = ["python3", str(ROOT / "scripts/kit.py"), "onboard", "--help"]
    if want_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif "error" in value:
        error = value["error"]
        print(f"Blocked: {error['code']} · {error['phase']} · owner: {error['owner']}")
        if error["missing"]:
            print("Missing choices: " + ", ".join(error["missing"]))
        print(error["next_action"])
        common.render_blocked_details(value)
        print("Recheck: " + shlex.join(error["recheck_command"]))
    elif value.get("schema") == "oci-sre-decision/1":
        print("Production decision: " + value["status"] + " (separate exact-plan approval required)")
        for row in value["checks"]:
            age = "unknown" if row["age_seconds"] is None else str(row["age_seconds"]) + "s"
            print(f"{row['id']}: {row['status']} · {row['owner']} · evidence age {age}")
            print("  " + row["recheck"])
    elif args.command == "cost":
        for line in common.project_module().helper("launch_cost").summary_lines(value):
            print(line)
    elif args.command == "sre" and args.action == "plan":
        print(f"Rehearsal test plan: {value['environment']} ({value['profile']}; preview)")
        print(value["critical_journey_prompt"])
        for stage, criteria in value["stages"].items():
            print(stage.replace("_", " ").title())
            for instruction in criteria:
                print("  " + instruction)
        print(value["next_action"])
    elif value.get("schema") == "oci-kit-onboarding/1":
        common.project_module().helper("onboarding").render(value)
    elif value.get("schema") == "oci-founder-journey/1":
        common.project_module().helper("journey_acceptance").render(value)
    elif value.get("schema") == "oci-kit-architecture/1":
        print("Well-Architected evidence: " + value["environment"] + " · " + value["status"])
        print("Controls: " + ", ".join(str(count) + " " + status for status, count in value["control_counts"].items()))
        for pillar in value["pillars"]:
            print(pillar["title"])
            for control in pillar["controls"]:
                print("  " + control["id"] + ": " + control["status"] + " · " + control["owner"])
                print("  " + control["instruction"])
    else:
        print(json.dumps(value, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
