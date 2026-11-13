"""One approved, provider-free synthetic native OCI backend rehearsal.

This is a functional test, not IAM isolation or application recovery. All input,
state, plans, lock metadata and receipts stay in a private directory. Installed
Python/SDK libraries and concurrent authorized writers are outside this gate's
integrity boundary. The caller must obtain owner approval of the exact hash.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import uuid

import backend_config
import backend_fixture as fixture
import backend_inspect as inspect
import backend_ops
import image_gate as files

PLAN = "backend-rehearsal-plan.json"
CLEANUP = "backend-cleanup-plan.json"
SCHEMA = "oci-backend-rehearsal/1"
TARGET_FIELDS = {"bucket", "namespace", "region", "bucket_id", "compartment_id", "tenancy_id"}
require = files.require


def sources():
    folder = Path(__file__).parent
    return {name: files.sha((folder / name).read_bytes()) for name in
            ("backend_rehearsal.py", "backend_fixture.py", "backend_inspect.py",
             "backend_config.py", "backend_ops.py", "deploy_gate.py", "image_gate.py")}


def scope(target):
    require(isinstance(target, dict) and set(target) == TARGET_FIELDS, "Invalid rehearsal target fields.")
    require(all(isinstance(v, str) and v for v in target.values()), "Invalid rehearsal target values.")
    for name, kind in (("bucket_id", "bucket"), ("compartment_id", "compartment"), ("tenancy_id", "tenancy")):
        require(re.fullmatch(r"ocid1\." + kind + r"\.oc1\.[A-Za-z0-9.-]+", target[name]),
                "Only explicit commercial-realm target identifiers are supported.")
    backend_ops.configuration({k: target[k] for k in ("bucket", "namespace", "region")} |
                              {"key": "test/primary.tfstate", "workspace_key_prefix": "test/unused",
                               "auth": "APIKey", "config_file_profile": "DEFAULT"})
    return target


def private_root(path):
    with files.directory(path) as fd:
        meta = os.fstat(fd)
        require(meta.st_uid == os.getuid() and not meta.st_mode & 0o077,
                "Use a private, owner-controlled rehearsal directory (0700).")


def receipt_binding(path, target, profile):
    raw = files.read_private(path)
    value = files.parse(raw)
    require(value.get("schema") == "oci-deploy-receipt/2" and value.get("kind") == "apply"
            and value.get("status") == "applied", "Use the successful bucket creation receipt.")
    matches = [r for r in value.get("resources", []) if r.get("type") == "oci_objectstorage_bucket"
               and r.get("id") in (None, target["bucket_id"]) and r.get("name") == target["bucket"]
               and r.get("compartment_id") == target["compartment_id"]]
    expected = {"region": target["region"], "tenancy_ocid": target["tenancy_id"],
                "compartment_ocid": target["compartment_id"], "profile": profile, "auth": "APIKey"}
    require(len(matches) == 1 and all(value.get("target", {}).get(k) == v for k, v in expected.items()),
            "Bucket receipt does not match the approved target and API-key profile.")
    return {"path": str(path.absolute()), "sha256": files.sha(raw)}


def keys(run_id):
    require(isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{24}", run_id), "Invalid run identifier.")
    prefix = "backend-check/" + run_id + "/"
    return prefix, [prefix + suffix for suffix in
                    ("primary.tfstate", "primary.tfstate.lock", "recovery.tfstate", "recovery.tfstate.lock")]


def auth(profile):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", profile), "Invalid API-key profile name.")
    home = str(Path.home().absolute())
    config, binding = inspect.identity(Path(home) / ".oci/config", profile)
    return config, {"home": home, "profile": profile, "identity": binding}


def prepare(args, gate):
    require(1 <= args.max_age_minutes <= 120, "Approval must expire within 1 to 120 minutes.")
    require(set(p.name for p in args.dir.iterdir()) <= {".gate"}, "Use a fresh rehearsal directory.")
    target = scope(files.parse(files.read_private(args.target)))
    config, identity = auth(args.profile)
    require(config.get("tenancy") == target["tenancy_id"], "Profile belongs to a different tenancy.")
    # Identity fields remain in the private packet; never echo account metadata.
    run = secrets.token_hex(12)
    prefix, names = keys(run)
    now = time.time()
    lineage = str(uuid.uuid4())
    payload = {"schema": SCHEMA, "directory": str(args.dir), "run_id": run, "prefix": prefix,
               "names": names, "target": target, "identity": identity,
               "bucket_receipt": receipt_binding(args.bucket_receipt, target, args.profile),
               "terraform": files.fingerprint("terraform"), "sources": sources(),
               "v1_lineage": lineage, "v1_sha256": files.sha(fixture.synthetic(run, 1, lineage, 1)),
               "created_at": now, "expires_at": now + args.max_age_minutes * 60,
               "transform": "synthetic-generation-2-observed-lineage-serial-plus-one/1"}
    digest = files.sha(files.canonical(payload))
    files.write_at(gate, PLAN, {"sha256": digest, "payload": payload})
    print("Synthetic native OCI backend rehearsal: 2 state keys and their 2 lock keys.")
    print("Scope: three default-workspace initializations; synthetic create/overwrite; plan lock contention;")
    print("normal release and positive control; historical-version recovery to a separate state key.")
    print("No resources, IAM changes, credential-bearing state, apply, force-unlock or permanent cleanup.")
    print("Native serialization/lineage and the loopback port are constrained runtime values; inspect the packet.")
    print("Versions/markers remain billable until a separate exact-version cleanup approval.")
    print(f"Private packet: {args.dir / '.gate' / PLAN}\nSHA-256: {digest}")
    return 0


def alive(proc):
    return proc.poll() is None


class Native:
    """Bounded observation without killing a native owner or bypassing its lock."""
    def __init__(self, root, payload, receipt, save):
        self.root, self.payload, self.receipt, self.save = root, payload, receipt, save
        self.running = []
        self.drainers = {}
        self.env = {"HOME": payload["identity"]["home"], "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                    "TF_INPUT": "0", "TF_IN_AUTOMATION": "1",
                    "TF_CLI_CONFIG_FILE": str(root / "terraform.rc"), "CHECKPOINT_DISABLE": "1"}

    def start(self, label, client, argv):
        require(not any(step.get("status") not in {"attempted", "completed"} for step in self.receipt["steps"]),
                "An earlier native step failed or is unresolved; no new command is permitted.")
        _, identity = auth(self.payload["identity"]["profile"])
        require(identity == self.payload["identity"], "Identity changed before the next native command.")
        require(self.payload["sources"] == sources()
                and self.payload["terraform"] == files.fingerprint("terraform"),
                "Reviewed implementation changed before the next native command.")
        require(time.time() <= self.payload["expires_at"], "Approval expired before the next native command.")
        require(len(self.receipt["steps"]) < 10, "Native command limit exceeded.")
        path = self.root / (label + ".log")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        step = {"label": label, "client": client, "argv": argv, "status": "attempted", "started_at": time.time()}
        self.receipt["steps"].append(step)
        self.save()
        drain = proc = None
        native_launch_entered = False
        try:
            with os.fdopen(fd, "wb") as log:
                # An independent draining process survives a controller timeout.
                # It caps retained bytes, keeps reading/discarding overflow, and
                # never closes a live native writer's pipe merely on timeout.
                drain = subprocess.Popen([sys.executable, str(Path(__file__).absolute()), "--drain"],
                                         stdin=subprocess.PIPE, stdout=log, stderr=subprocess.DEVNULL,
                                         env=self.env, start_new_session=True)
                step["drain_pid"] = drain.pid
                try:
                    require(time.time() <= self.payload["expires_at"], "Approval expired before native launch.")
                    native_launch_entered = True
                    proc = subprocess.Popen([self.payload["terraform"]["path"]] + argv, cwd=self.root / client,
                                            env=self.env, stdin=subprocess.DEVNULL, stdout=drain.stdin,
                                            stderr=subprocess.STDOUT, start_new_session=True)
                    step["pid"] = proc.pid
                    self.drainers[proc.pid] = drain
                    self.running.append((proc, step, path))
                finally:
                    drain.stdin.close()
        except BaseException as error:
            # An interrupt can arrive after fork but before Popen returns. Only
            # an ordinary exec OSError with no returned child proves no launch.
            step["status"] = ("launch-failed" if not native_launch_entered
                              or isinstance(error, OSError) and proc is None else "launch-outcome-unknown")
            if drain is not None and proc is None:
                try:
                    drain.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                step["drain_exit_code"] = drain.poll()
            self.save()
            raise
        self.save()
        return proc, step, path

    def finish(self, entry, expected=0, timeout=90):
        proc, step, path = entry
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            step["status"] = "still-running-outcome-unknown"
            self.save()
            raise files.ImageGateError("Native client is still running; inspect private receipt. No retry or cleanup.") from None
        step.update(status="completed" if code == expected else "failed", exit_code=code, finished_at=time.time())
        self.save()
        require(code == expected, "Native command failed; inspect the private log. Approval is consumed.")
        drain = self.drainers[proc.pid]
        try:
            drained = drain.wait(timeout=10)
        except subprocess.TimeoutExpired:
            step["status"] = "output-outcome-unknown"
            self.save()
            raise files.ImageGateError("Native output reader is still running; inspect the private receipt.") from None
        if drained != 0:
            step["status"] = "output-failed"
            self.save()
        require(drained == 0, "Native output exceeded its retained limit or could not be captured; stop.")
        raw = files.read_private(path)
        require(len(raw) <= 262144, "Native log exceeded the review limit; stop and inspect privately.")
        return raw

    def run(self, label, client, argv, expected=0):
        return self.finish(self.start(label, client, argv), expected)

    def settle(self):
        # The HTTP helper is released before this call. Allow normal unlock even
        # after approval expiry. Never send a signal, force-unlock or retry.
        deadline = time.monotonic() + 60
        for proc, step, _ in self.running:
            if alive(proc):
                try:
                    proc.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    step["status"] = "still-running-outcome-unknown"
            step["final_exit_code"] = proc.poll()
            drain = self.drainers[proc.pid]
            if not alive(proc):
                try:
                    drain.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
            step["drain_exit_code"] = drain.poll()
        self.save()


def put(root, name, raw):
    with files.directory(root) as fd:
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(out, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())


def backend(payload, key):
    return {k: payload["target"][k] for k in ("bucket", "namespace", "region")} | {
        "key": key, "workspace_key_prefix": payload["prefix"] + "unused-workspaces",
        "auth": "APIKey", "config_file_profile": payload["identity"]["profile"]}


def current(inventory, name):
    return any(row["name"] == name for row in inventory["objects"])


def observed(client, name, run, generation, version=None):
    obj = client.object(name, version_id=version)
    require(obj is not None, "Expected synthetic state is missing.")
    state = fixture.validate(obj["bytes"], run, generation)
    require(isinstance(obj["version_id"], str) and obj["version_id"], "Versioned state response lacks a version ID.")
    if version is not None:
        require(obj["version_id"] == version, "Historical state version differs from the requested version.")
    return obj, state


def public_object(obj):
    return {k: obj[k] for k in ("version_id", "etag")} | {"sha256": files.sha(obj["bytes"])}


def run_recipe(root, p, client, receipt, save):
    prefix, names = keys(p["run_id"])
    primary, lock, recovery, recovery_lock = names
    client.preflight()
    require(client.inventory(prefix, names) == {"objects": [], "versions": []}, "Rehearsal prefix is not empty.")
    # Private fresh directories and fixed source only. The empty mirror prevents
    # external providers; the fixture uses only Terraform's built-in provider.
    for name in ("holder", "contender", "recovery", "empty-mirror"):
        (root / name).mkdir(mode=0o700)
    put(root, "terraform.rc", ('disable_checkpoint = true\nprovider_installation { filesystem_mirror { path = '
                              + json.dumps(str(root / "empty-mirror")) + ' } }\n').encode())
    base = fixture.synthetic(p["run_id"], 1, p["v1_lineage"], 1)
    require(files.sha(base) == p["v1_sha256"], "Synthetic fixture hash changed.")
    put(root, "v1.json", base)
    native = Native(root, p, receipt, save)
    try:
        with fixture.LoopbackFixture(base) as server:
            configs = {}
            for name in ("holder", "contender", "recovery"):
                configs[name] = backend(p, recovery if name == "recovery" else primary)
                put(root / name, "backend.tf.json", files.canonical(backend_ops.DECLARATION))
                if name != "recovery":
                    put(root / name, "main.tf.json", fixture.module(name))
                put(root / name, "backend.tfbackend.json", files.canonical(configs[name]))
            version = files.parse(native.run("version", "recovery", ["version", "-json"]))
            require(version.get("terraform_version") == "1.16.6", "This recipe requires Terraform 1.16.6.")
            receipt["initialized"] = {}
            for name in ("holder", "contender", "recovery"):
                native.run("init-" + name, name, ["init", "-get=false", "-input=false", "-no-color",
                                               "-backend-config=backend.tfbackend.json"])
                cached = backend_config.inspect_backend(root / name)
                require(backend_ops.metadata_config(cached) == configs[name], "Initialized backend destination differs.")
                receipt["initialized"][name] = backend_ops.binding(cached)
                save()
            require(client.inventory(prefix, names) == {"objects": [], "versions": []},
                    "Initialization unexpectedly changed the rehearsal prefix.")

            def command(label, who, argv, expected=0, asynchronous=False):
                cached = backend_config.inspect_backend(root / who)
                require(backend_ops.binding(cached) == receipt["initialized"][who], "Backend or fixture source changed.")
                return native.start(label, who, argv) if asynchronous else native.run(label, who, argv, expected)

            command("push-v1", "holder", ["state", "push", "-lock-timeout=1s", str(root / "v1.json")])
            v1, s1 = observed(client, primary, p["run_id"], 1)
            receipt["v1"] = public_object(v1)
            before = client.inventory(prefix, names)
            require(not current(before, lock), "Generation 1 left a current lock; stop.")
            plans = ["plan", "-input=false", "-no-color", "-lock-timeout=1s",
                     "-var=fixture_port=" + str(server.port), "-out=discard.tfplan"]
            holder = command("holder-plan", "holder", plans, asynchronous=True)
            try:
                require(server.holder_seen.wait(20), "Holder did not reach its bounded local data source.")
                held = client.object(lock, limit=16384)
                require(held is not None, "No native lock was observed.")
                info = files.parse(held["bytes"])
                require(info.get("Operation") == "OperationTypePlan" and isinstance(info.get("ID"), str)
                        and len(info["ID"]) >= 16, "Unexpected native lock metadata.")
                receipt["holder_lock"] = info
                save()
                diagnostic = command("contender-blocked", "contender", plans, expected=1)
                require(b"Error acquiring the state lock" in diagnostic and info["ID"].encode() in diagnostic
                        and server.counts().get("/contender", 0) == 0 and alive(holder[0]),
                        "Contender did not demonstrably fail on the observed live native lock.")
            finally:
                server.release()
            native.finish(holder)
            released = client.inventory(prefix, names)
            require(not current(released, lock), "Holder has not released its current lock.")
            command("contender-control", "contender", plans)
            require(server.counts().get("/contender", 0) >= 1, "Positive control never reached the local fixture.")
            after = client.inventory(prefix, names)
            require(not current(after, lock) and [r for r in before["versions"] if r["name"] == primary]
                    == [r for r in after["versions"] if r["name"] == primary], "Planning changed state versions or left a lock.")
            unchanged, _ = observed(client, primary, p["run_id"], 1)
            require(public_object(unchanged) == public_object(v1), "Planning changed the persistent state.")
            receipt["lock_contention_verified"] = True
            save()
            put(root, "v2.json", fixture.v2(v1["bytes"], p["run_id"]))
            command("push-v2", "holder", ["state", "push", "-lock-timeout=1s", str(root / "v2.json")])
            v2, s2 = observed(client, primary, p["run_id"], 2)
            require(s2["lineage"] == s1["lineage"] and s2["serial"] == s1["serial"] + 2
                    and v2["version_id"] != v1["version_id"], "Unexpected native overwrite transition.")
            receipt["v2"] = public_object(v2)
            historical, _ = observed(client, primary, p["run_id"], 1, v1["version_id"])
            require(public_object(historical) == public_object(v1), "Historical state no longer matches the captured version.")
            put(root, "recovery.json", historical["bytes"])
            require(not current(client.inventory(prefix, names), recovery), "Recovery key is no longer empty.")
            command("restore-v1", "recovery", ["state", "push", "-lock-timeout=1s", str(root / "recovery.json")])
            restored, _ = observed(client, recovery, p["run_id"], 1)
            final_primary, _ = observed(client, primary, p["run_id"], 2)
            require(public_object(final_primary) == public_object(v2), "Recovery changed the primary state.")
            receipt["recovered"] = public_object(restored)
            receipt["inventory"] = client.inventory(prefix, names)
            require(not any(current(receipt["inventory"], n) for n in (lock, recovery_lock)), "A current native lock remains.")
            receipt["status"] = "verified-synthetic-only"
            save()
    finally:
        native.settle()


def execute(args, gate):
    env = files.parse(files.read_at(gate, PLAN))
    require(isinstance(env, dict) and set(env) == {"sha256", "payload"}, "Invalid rehearsal envelope.")
    p = env["payload"]
    require(isinstance(p, dict) and set(p) == {"schema", "directory", "run_id", "prefix", "names", "target",
            "identity", "bucket_receipt", "terraform", "sources", "v1_lineage", "v1_sha256", "created_at",
            "expires_at", "transform"}, "Invalid rehearsal packet fields.")
    digest = files.sha(files.canonical(p))
    require(re.fullmatch(r"[0-9a-f]{64}", args.approve or "") and digest == env["sha256"] == args.approve,
            "Approval does not match the pending rehearsal.")
    require(p.get("schema") == SCHEMA and p["directory"] == str(args.dir), "Wrong rehearsal schema or directory.")
    require(p["sources"] == sources() and p["terraform"] == files.fingerprint("terraform"), "Reviewed implementation changed.")
    require(set(x.name for x in args.dir.iterdir()) <= {".gate"}, "Rehearsal directory is no longer fresh.")
    require(keys(p["run_id"]) == (p["prefix"], p["names"]), "Rehearsal key scope differs.")
    require(p["transform"] == "synthetic-generation-2-observed-lineage-serial-plus-one/1"
            and p["v1_sha256"] == files.sha(fixture.synthetic(p["run_id"], 1, p["v1_lineage"], 1)),
            "Invalid synthetic transform or baseline.")
    target = scope(p["target"])
    config, binding = auth(p["identity"]["profile"])
    require(binding == p["identity"], "Configured identity or HOME changed; re-plan.")
    require(config.get("tenancy") == target["tenancy_id"], "Profile belongs to a different tenancy.")
    require(receipt_binding(Path(p["bucket_receipt"]["path"]), target, binding["profile"]) == p["bucket_receipt"],
            "Bucket creation receipt changed.")
    now = time.time()
    require(type(p["created_at"]) in (int, float) and type(p["expires_at"]) in (int, float)
            and 0 < p["expires_at"] - p["created_at"] <= 7200 and p["created_at"] <= now <= p["expires_at"],
            "Rehearsal approval expired or has invalid timestamps.")
    with files.private_directory(gate, "rehearsal-receipts") as receipts:
        name = digest + ".json"
        receipt = {"schema": "oci-backend-rehearsal-receipt/1", "operation_sha256": digest,
                   "status": "attempted", "payload": p, "started_at": now, "steps": [],
                   "iam_isolation_verified": False, "permanent_cleanup_authorized": False}
        files.write_at(receipts, name, receipt, exclusive=True)
        os.unlink(PLAN, dir_fd=gate)
        os.fsync(gate)
        save = lambda: files.write_at(receipts, name, receipt)
        try:
            run_recipe(args.dir, p, inspect.Inspector(config, target), receipt, save)
        except BaseException:
            receipt["status"] = "incomplete-outcome-review-required"
            raise
        finally:
            receipt["finished_at"] = time.time()
            save()
    print("Synthetic backend rehearsal verified. IAM isolation and application recovery remain separate.")
    print(f"Private receipt: {args.dir / '.gate/rehearsal-receipts' / name}")
    print("State/lock versions remain retained. Permanent deletion requires a separate exact-version approval.")
    return 0


def cleanup_origin(path, root):
    raw = files.read_private(path)
    value = files.parse(raw)
    require(value.get("schema") == "oci-backend-rehearsal-receipt/1"
            and value.get("status") in {"verified-synthetic-only", "incomplete-outcome-review-required"}
            and value.get("payload", {}).get("directory") == str(root), "Invalid originating rehearsal receipt.")
    require(value.get("finished_at") is not None, "The originating rehearsal has not finished.")
    for step in value.get("steps", []):
        require(step.get("status") != "launch-outcome-unknown", "A native launch has unresolved outcome; reconcile it first.")
        require(step.get("final_exit_code") is not None or step.get("status") == "launch-failed",
                "A native client has unresolved process status; reconcile it before preparing cleanup.")
    return value, {"path": str(path.absolute()), "sha256": files.sha(raw)}


def cleanup_inventory(client, p):
    prefix, names = keys(p["run_id"])
    inventory = client.inventory(prefix, names)
    require(not any(current(inventory, name) for name in (names[1], names[3])),
            "Current locks must be absent before permanent cleanup.")
    # Never approve arbitrary data merely because its name has our prefix.
    for row in inventory["versions"]:
        if row["is_delete_marker"]:
            continue
        obj = client.object(row["name"], version_id=row["version_id"])
        require(obj is not None and obj["version_id"] == row["version_id"], "Version changed during cleanup review.")
        if row["name"].endswith(".lock"):
            lock = files.parse(obj["bytes"])
            require(set(lock) <= {"ID", "Operation", "Info", "Who", "Version", "Created", "Path"}
                    and lock.get("Version") == "1.16.6" and isinstance(lock.get("ID"), str)
                    and len(lock["ID"]) >= 16, "Unexpected lock-version payload; manual review required.")
        else:
            parsed = files.parse(obj["bytes"])
            generation = parsed.get("outputs", {}).get("generation", {}).get("value")
            require(type(generation) is int and generation in (1, 2), "Unexpected state version.")
            fixture.validate(obj["bytes"], p["run_id"], generation)
    require(client.inventory(prefix, names) == inventory, "Inventory changed during cleanup review.")
    return inventory


def cleanup_order(inventory):
    active = {(r["name"], r["version_id"]) for r in inventory["objects"]}
    # Remove every historical data version before any deletion marker. In
    # particular, deleting a lock marker can no longer resurrect an old lock.
    def order(row):
        tier = 2 if (row["name"], row["version_id"]) in active else 1 if row["is_delete_marker"] else 0
        return tier, row["name"], row["version_id"]
    return sorted(inventory["versions"], key=order)


def prepare_cleanup(args, gate):
    require(1 <= args.max_age_minutes <= 120, "Approval must expire within 1 to 120 minutes.")
    origin, source = cleanup_origin(args.receipt, args.dir)
    p = origin["payload"]
    config, identity = auth(p["identity"]["profile"])
    require(identity == p["identity"], "Identity changed since the originating rehearsal.")
    client = inspect.Inspector(config, scope(p["target"]))
    client.preflight()
    inventory = cleanup_inventory(client, p)
    require(inventory["versions"], "No retained versions need cleanup.")
    now = time.time()
    payload = {"schema": "oci-backend-cleanup/1", "directory": str(args.dir), "origin": source,
               "identity": identity, "sources": sources(), "inventory": inventory,
               "delete_order": cleanup_order(inventory), "created_at": now,
               "expires_at": now + args.max_age_minutes * 60}
    digest = files.sha(files.canonical(payload))
    files.write_at(gate, CLEANUP, {"sha256": digest, "payload": payload})
    print(f"Permanent cleanup of {len(payload['delete_order'])} exact synthetic state/lock versions or markers.")
    print("Preparation performed bounded reads only. No bucket, IAM, workspace or prefix deletion is included.")
    print(f"Private packet: {args.dir / '.gate' / CLEANUP}\nSHA-256: {digest}")
    return 0


def execute_cleanup(args, gate):
    envelope = files.parse(files.read_at(gate, CLEANUP))
    require(set(envelope) == {"sha256", "payload"}, "Invalid cleanup envelope.")
    p = envelope["payload"]
    require(set(p) == {"schema", "directory", "origin", "identity", "sources", "inventory", "delete_order",
                       "created_at", "expires_at"}, "Invalid cleanup packet fields.")
    digest = files.sha(files.canonical(p))
    require(re.fullmatch(r"[0-9a-f]{64}", args.approve or "") and digest == envelope["sha256"] == args.approve,
            "Approval does not match the pending cleanup.")
    require(p["schema"] == "oci-backend-cleanup/1" and p["directory"] == str(args.dir)
            and p["sources"] == sources(), "Cleanup implementation or directory changed.")
    origin, binding = cleanup_origin(Path(p["origin"]["path"]), args.dir)
    require(binding == p["origin"], "Originating receipt changed.")
    config, identity = auth(p["identity"]["profile"])
    require(identity == p["identity"] == origin["payload"]["identity"], "Cleanup identity changed.")
    now = time.time()
    require(type(p["created_at"]) in (int, float) and type(p["expires_at"]) in (int, float)
            and 0 < p["expires_at"] - p["created_at"] <= 7200 and p["created_at"] <= now <= p["expires_at"],
            "Cleanup approval expired or has invalid timestamps.")
    require(p["delete_order"] == cleanup_order(p["inventory"]), "Cleanup order is invalid.")
    with files.private_directory(gate, "cleanup-receipts") as receipts:
        name = digest + ".json"
        result = {"schema": "oci-backend-cleanup-receipt/1", "operation_sha256": digest,
                  "status": "attempted", "origin": p["origin"], "steps": [], "started_at": now}
        files.write_at(receipts, name, result, exclusive=True)
        os.unlink(CLEANUP, dir_fd=gate)
        os.fsync(gate)
        try:
            client = inspect.Inspector(config, scope(origin["payload"]["target"]))
            client.preflight()
            require(cleanup_inventory(client, origin["payload"]) == p["inventory"],
                    "Inventory changed; this cleanup approval is consumed without deletion.")
            for row in p["delete_order"]:
                require(time.time() <= p["expires_at"], "Cleanup approval expired before the next deletion.")
                step = {"name": row["name"], "version_id": row["version_id"], "status": "attempted"}
                result["steps"].append(step)
                files.write_at(receipts, name, result)
                require(time.time() <= p["expires_at"], "Cleanup approval expired before deletion.")
                client.delete_version(row["name"], row["version_id"], etag=row["etag"])
                step["status"] = "deleted"
                files.write_at(receipts, name, result)
            prefix, names = keys(origin["payload"]["run_id"])
            require(client.inventory(prefix, names) == {"objects": [], "versions": []},
                    "Cleanup did not leave an empty current/version inventory.")
            result["status"] = "verified-empty"
        except BaseException:
            result["status"] = "incomplete-outcome-review-required"
            raise
        finally:
            result["finished_at"] = time.time()
            files.write_at(receipts, name, result)
    print("Exact approved versions and markers removed; current and version inventories are empty.")
    print("The bucket and original local bootstrap state remain retained.")
    return 0


def dispatch(args):
    try:
        args.dir = args.dir.absolute()
        private_root(args.dir)
        with files.workspace(args.dir) as gate:
            return {"backend-rehearsal-plan": prepare, "backend-rehearsal-run": execute,
                    "backend-cleanup-plan": prepare_cleanup, "backend-cleanup-run": execute_cleanup}[args.command](args, gate)
    except files.ImageGateError as exc:
        print(f"backend rehearsal: {exc}", file=sys.stderr)
        return exc.code
    except Exception:
        # SDK, configuration and JSON errors can contain account metadata.
        print("backend rehearsal: stopped; inspect private inputs and receipt. Do not retry an attempted operation.", file=sys.stderr)
        return 3


def drain_output():
    """Retain at most 256 KiB, drain the rest until EOF, never signal a writer."""
    remaining, overflow, failed = 262144, False, False
    while True:
        block = sys.stdin.buffer.read(32768)
        if not block:
            break
        kept = block[:remaining]
        remaining -= len(kept)
        overflow = overflow or len(block) > len(kept)
        if kept and not failed:
            try:
                sys.stdout.buffer.write(kept)
                sys.stdout.buffer.flush()
            except OSError:
                failed = True
    return 3 if failed else 2 if overflow else 0


if __name__ == "__main__" and sys.argv[1:] == ["--drain"]:
    raise SystemExit(drain_output())
