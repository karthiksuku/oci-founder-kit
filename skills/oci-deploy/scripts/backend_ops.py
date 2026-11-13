"""Approve native OCI backend initialization and planning before they run.

This reuses the image gate's private files and one-attempt receipts. It does not
approve resource applies, state migration, state push, workspace changes or IAM.
Only a canonical partial backend declaration, API-key profile authentication
and the default Terraform workspace are supported by this initial path.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import backend_config
import image_gate as files

PLAN = "backend-plan.json"
DECLARATION = {"terraform": {"backend": {"oci": {}}}}
FIELDS = {"bucket", "namespace", "region", "key", "workspace_key_prefix", "auth", "config_file_profile"}


def require(condition, message):
    files.require(condition, message)


def configuration(value):
    require(isinstance(value, dict) and set(value) == FIELDS,
            "Backend config must contain exactly bucket, namespace, region, key, workspace_key_prefix, auth and config_file_profile.")
    require(all(isinstance(v, str) and v for v in value.values()), "Backend settings must be nonempty strings.")
    for name, pattern in (("bucket", r"[A-Za-z0-9_.-]{1,256}"),
                          ("namespace", r"[a-zA-Z0-9_-]{1,64}"),
                          ("region", r"[a-z]+-[a-z]+-\d+"),
                          ("config_file_profile", r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")):
        require(re.fullmatch(pattern, value[name]) is not None, "Invalid backend identifier format.")
    for name in ("key", "workspace_key_prefix"):
        text = value[name]
        require(len(text) <= 512 and re.fullmatch(r"[A-Za-z0-9_./-]+", text) is not None
                and not text.startswith("/") and all(p not in {"", ".", ".."} for p in text.split("/")),
                "State keys and workspace prefixes must use explicit relative object paths.")
    require(value["key"].endswith(".tfstate"), "Use an explicit .tfstate object key.")
    require(value["auth"] == "APIKey", "This backend operation path currently requires an existing APIKey profile.")
    return value


def environment_binding():
    # Backend attributes are explicit; environment-based alternate auth/endpoints
    # and implicit command flags are intentionally unsupported by this path.
    forbidden = [name for name in os.environ if name.startswith(("OCI_", "TF_CLI_ARGS", "TF_LOG"))
                 or name in {"TF_CLI_CONFIG_FILE", "TF_REATTACH_PROVIDERS"}]
    require(not forbidden, "Clear OCI/TF command, logging and provider overrides before a backend operation.")
    selected = {name: value for name, value in os.environ.items() if name.startswith("TF_")}
    return files.sha(files.canonical(selected))


def source_binding():
    folder = Path(__file__).resolve().parent
    return {name: files.sha((folder / name).read_bytes()) for name in
            ("backend_ops.py", "backend_config.py", "deploy_gate.py", "image_gate.py")}


def snapshot(stack):
    return backend_config.inspect_backend(stack)


def binding(observed):
    """Only hashes/types leave the private metadata object; no credential values."""
    return {key: observed[key] for key in ("types", "cloud", "declarations", "metadata_sha256", "source_sha256", "workspace")}


def canonical_declaration(stack, observed):
    require(not observed["cloud"] and observed["declarations"] == [{"file": "backend.tf.json", "type": "oci"}],
            "Use one canonical backend.tf.json OCI declaration; inline backend/cloud settings are not supported.")
    require(files.parse((stack / "backend.tf.json").read_bytes()) == DECLARATION,
            "backend.tf.json must contain only the empty OCI backend declaration.")


def metadata_config(observed):
    metadata = observed["metadata"]
    require(isinstance(metadata, dict) and metadata.get("type") == "oci", "Initialize the approved OCI backend first.")
    value = metadata.get("config")
    require(isinstance(value, dict), "Invalid initialized backend metadata.")
    require(all(v is None for k, v in value.items() if k not in FIELDS),
            "Initialized backend has unsupported credential, encryption or endpoint overrides.")
    return configuration({name: value.get(name) for name in FIELDS})


def variable_files(stack, names):
    result = []
    for name in names:
        path = Path(name)
        require(not path.is_absolute() and len(path.parts) == 1 and path.name not in {".", ".."},
                "Backend planning accepts variable files directly inside the stack only.")
        require(path.name.endswith((".tfvars", ".tfvars.json")), "Expected a private Terraform variable file.")
        raw = files.read_private(stack / path)
        result.append({"name": path.name, "sha256": files.sha(raw)})
    require(len({f["name"] for f in result}) == len(result), "Duplicate variable files are not accepted.")
    return result


def ensure_no_migration(stack):
    require(not any(stack.glob("terraform.tfstate*")) and not (stack / "terraform.tfstate.d").exists(),
            "Local state or workspace history exists. Migration needs a separate reviewed operation.")


def prepare(args, gate):
    import deploy_gate as core
    require(1 <= args.max_age_minutes <= 120, "Backend approval lifetime must be 1 to 120 minutes.")
    observed = snapshot(args.dir)
    canonical_declaration(args.dir, observed)
    config_input = None
    if args.operation == "init":
        require(args.backend_config is not None, "Initialization requires a private JSON --backend-config.")
        require(not args.var_file and not args.target, "Initialization does not accept resource-plan options.")
        ensure_no_migration(args.dir)
        raw = files.read_private(args.backend_config)
        config = configuration(files.parse(raw))
        config_input = {"path": str(args.backend_config.absolute()), "sha256": files.sha(raw)}
        if observed["metadata"] is not None:
            require(metadata_config(observed) == config, "Reconfiguration/migration to a different backend is not supported.")
    else:
        require(args.backend_config is None, "Resource planning uses the previously initialized backend.")
        config = metadata_config(observed)
    # Validate target syntax before approval, not after consuming an attempt.
    core.validate_targets(args.target)
    now = time.time()
    payload = {"schema": "oci-backend-operation/1", "operation": args.operation,
               "stack_path": str(args.dir), "backend": config, "backend_config_input": config_input,
               "snapshot": binding(observed), "variables": variable_files(args.dir, args.var_file),
               "targets": args.target, "terraform": core.terraform_binary(), "gate_sources": source_binding(),
               "environment_sha256": environment_binding(), "created_at_epoch": now,
               "expires_at_epoch": now + args.max_age_minutes * 60,
               "resource_plan_max_age_minutes": args.max_age_minutes}
    digest = files.sha(files.canonical(payload))
    files.write_at(gate, PLAN, {"sha256": digest, "payload": payload})
    print(f"Backend operation: {args.operation}; default workspace; APIKey profile {config['config_file_profile']}.")
    print(f"OCI target: {config['region']}, namespace {config['namespace']}, bucket {config['bucket']}.")
    print(f"State key: {config['key']}; lock key: {config['key']}.lock.")
    print(f"Workspace prefix may be listed: {config['workspace_key_prefix']} (no workspace creation).")
    print("Init may contact the backend and install reviewed modules/providers. Planning creates/deletes lock objects;")
    print("versioned lock history may remain. No resource apply, state migration, state push, IAM or cleanup is approved.")
    print("Review bucket IAM/versioning, code/provider behavior, request costs and retained versions separately.")
    print(f"Expires at UTC epoch {payload['expires_at_epoch']:.3f}. SHA-256: {digest}")
    print(f"After exact owner approval: backend-run --dir {args.dir} --approve {digest}")
    return 0


def execute(args, gate):
    import deploy_gate as core
    envelope = files.parse(files.read_at(gate, PLAN))
    require(isinstance(envelope, dict) and set(envelope) == {"sha256", "payload"}, "Invalid backend approval envelope.")
    payload = envelope["payload"]
    digest = files.sha(files.canonical(payload))
    require(re.fullmatch(r"[0-9a-f]{64}", args.approve or "") is not None
            and digest == envelope["sha256"] == args.approve, "Approval does not match the pending backend operation.")
    require(payload.get("schema") == "oci-backend-operation/1" and payload.get("operation") in {"init", "plan", "destroy-plan"},
            "Unknown backend operation.")
    now = time.time()
    created, expires = payload["created_at_epoch"], payload["expires_at_epoch"]
    require(isinstance(created, (int, float)) and isinstance(expires, (int, float))
            and 0 < expires - created <= 7200 and created <= now + 300 and now <= expires,
            "Backend approval expired or has invalid timestamps; prepare a fresh operation.")
    require(payload["stack_path"] == str(args.dir), "Backend approval belongs to another stack.")
    require(payload["gate_sources"] == source_binding(), "Gate source changed; prepare a fresh operation.")
    require(payload["terraform"] == core.terraform_binary(), "Terraform binary changed; prepare a fresh operation.")
    require(payload["environment_sha256"] == environment_binding(), "Terraform environment changed; prepare a fresh operation.")
    observed = snapshot(args.dir)
    canonical_declaration(args.dir, observed)
    require(binding(observed) == payload["snapshot"], "Backend configuration or stack source changed; prepare a fresh operation.")
    config = configuration(payload["backend"])
    names = [v["name"] for v in payload["variables"]]
    require(variable_files(args.dir, names) == payload["variables"], "Variable files changed; prepare a fresh operation.")
    core.validate_targets(payload["targets"])
    if payload["operation"] == "init":
        ensure_no_migration(args.dir)
        config_input = payload["backend_config_input"]
        raw = files.read_private(Path(config_input["path"]))
        require(files.sha(raw) == config_input["sha256"] and configuration(files.parse(raw)) == config,
                "Backend settings changed; prepare a fresh operation.")
    else:
        require(metadata_config(observed) == config, "Initialized backend settings changed.")
    require(time.time() <= expires, "Backend approval expired during validation; prepare a fresh operation.")
    with files.private_directory(gate, "backend-receipts") as receipts:
        receipt_name = digest + ".json"
        receipt = {"schema": "oci-backend-receipt/1", "operation": payload["operation"], "status": "attempted",
                   "operation_sha256": digest, "started_at_epoch": now, "backend": config,
                   "snapshot": payload["snapshot"], "resource_apply_authorized": False}
        files.write_at(receipts, receipt_name, receipt, exclusive=True)
        os.unlink(PLAN, dir_fd=gate)  # consumed before the first client invocation
        try:
            if payload["operation"] == "init":
                require(time.time() <= expires, "Backend approval expired before initialization; no client was started.")
                core.run_terraform(payload["terraform"], ["init", "-input=false", "-no-color",
                                   "-backend-config=" + payload["backend_config_input"]["path"]], args.dir, args.dir / ".gate")
                after = snapshot(args.dir)
                canonical_declaration(args.dir, after)
                require(metadata_config(after) == config, "Initialized backend did not match the approved destination.")
                receipt["initialized_backend_sha256"] = after["metadata_sha256"]
            else:
                core.cmd_plan(args.dir, "destroy" if payload["operation"] == "destroy-plan" else "apply",
                              names, payload["resource_plan_max_age_minutes"], "oci", payload["targets"],
                              backend_activity={"operation_sha256": digest, "binding": binding(observed),
                                                "backend": config, "expires_at_epoch": expires})
                summary = json.loads((args.dir / ".gate" / core.SUMMARY_FILE).read_text())
                receipt["resource_plan_sha256"] = summary["plan_sha256"]
            receipt["status"] = "completed"
        except Exception:
            receipt["status"] = "failed"
            receipt["remote_objects_may_have_changed"] = True
            raise
        finally:
            receipt["finished_at_epoch"] = time.time()
            files.write_at(receipts, receipt_name, receipt)
    print(f"Backend {payload['operation']} completed; private receipt .gate/backend-receipts/{receipt_name}.")
    print("This approval is consumed. Resource apply and any residual-version cleanup require separate exact approvals.")
    return 0


def dispatch(args):
    import deploy_gate as core
    try:
        args.dir = args.dir.absolute()
        with files.workspace(args.dir) as gate:
            return prepare(args, gate) if args.command == "backend-plan" else execute(args, gate)
    except files.ImageGateError as exc:
        print(f"backend gate: {exc}", file=sys.stderr)
        return exc.code
    except (core.GateRefused, core.GateInputError, core.TerraformError) as exc:
        print(f"backend gate: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, core.TerraformError) else 3
    except (OSError, ValueError, KeyError, TypeError, backend_config.BackendConfigError) as exc:
        print("backend gate: invalid or unsafe local input; inspect private files without sharing credentials.", file=sys.stderr)
        return 3
