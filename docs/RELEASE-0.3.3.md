# 0.3.3 preview — approved backend operations

Terraform planning with a remote backend can create and delete lock objects.
Initializing some backend/workspace configurations can also write state.
This release adds a separate approval before native OCI backend initialization
or planning. The generated resource plan still needs its own exact approval
before apply. See the [backend workflow](../skills/oci-deploy/references/backend-state.md).

## What changed

`backend-plan` prepares a private operation packet without invoking Terraform
or a cloud client. `backend-run` requires the exact approved packet hash and
consumes it before its first client invocation. It records successful and failed
attempts privately. Operations bind the selected bucket, namespace, region,
state/lock keys, profile, default workspace, root configuration, variable files,
Terraform executable and gate source. Expiry is rechecked before client start.

Resource apply rechecks backend metadata, root source and the Terraform
environment. Older saved plans without these bindings require a fresh plan.
Unapproved remote initialization/planning is refused before Terraform runs.
Source/cache inspection also refuses unknown state-store formats and unsafe
symlink, FIFO, oversized or redirected inputs.

The initial workflow supports existing APIKey profiles and the default
workspace on POSIX systems. It uses a canonical empty `backend.tf.json`
declaration plus private JSON backend settings. State migration, state push,
workspace changes and version-specific cleanup are not implemented by this
operation path. Instructions preserve those boundaries rather than authorizing
manual cloud writes. Local resource planning remains available through `plan`.

Git ignores, the project installer and staged-content hooks exclude private
`*.tfbackend.json` files. The optional cloud hook also flags direct Terraform
init/plan calls, because the shell command alone cannot establish that the
backend is local. Normal help, formatting and saved-plan inspection remain
available.

## Evidence and limits

The full Python suite passed **441 tests**, including 45 focused backend checks;
the repository validator and Claude plugin validator passed. The first full run
failed in the app harness under the restricted sandbox; the same suite passed
when local test sockets were permitted. The app implementation was unchanged.

Focused offline checks cover configuration syntax/cache cases, changed
destinations and environment, legacy plans, wrong/expired/reused approvals,
failed attempts and separate resource-apply authorization. Independent review
reproduced legacy-plan and expiry gaps before their fixes, then verified refusal
afterward. These tests use fake clients and do not prove OCI authorization or
native backend lock/recovery behavior.

A bounded local experiment with Terraform 1.16.6 disproved the proposed use of
a piped console as a lock holder: a competing default-locking state push
succeeded while the console was open. That method is not recommended or used.
Console presence must not be substituted for lock-contention evidence.

The gate is not a sandbox or proof of human approval. Its root-file hashes do
not bind module/provider implementations, external profile contents or signer
identity. Review those inputs and real account permissions independently.
Expiry controls command start, not total execution duration. Versioned lock
history and API usage may remain after an operation; no automatic cleanup or
spending cap is promised.

Live backend contention, state recovery, full hosted application/identity/HTTPS
acceptance, rollback and teardown remain unverified. A private, versioned bucket
does not establish inherited IAM isolation. No account identifiers, internal
policy statements, credentials, state or raw cloud receipts are included here.

The earlier [0.3.2 evidence](RELEASE-0.3.2.md) records application/runtime checks
whose scope is unchanged by this patch. GitHub validation CI and trusted Codex
hook execution remain pending; local tests are not a claim that either ran.
After 0.3.2 was tagged, a separately approved live OCI digest upload succeeded;
independent readback verified its manifest and every content blob, with no tag
assigned. The [0.3.2 release notes](https://github.com/karthiksuku/oci-founder-kit/releases/tag/v0.3.2)
record that later result. It does not establish application deployment.
