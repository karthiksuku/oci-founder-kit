# Operate, recover and hand over

The agent should leave a runnable application and a short runbook matched to
its actual stack. This guide specifies the evidence to collect; it does not
automatically operate an account or establish production readiness.

## Before real users

Record the deployed source/image revision, owner and incident contact, selected
region and dependencies, health endpoints, operating budget and recovery goals.
Complete the [five-pillar review](../skills/oci-foundation/references/well-architected.md).
Verify these controls against the running app:

- HTTPS with the correct hostname/certificate, secure cookies and redirect rules.
- Server-validated identity and ownership checks using two users, including denied
  reads, writes and attachment access. Preserve the agreed identity provider.
- Runtime secret retrieval with least privilege; no secret values in images,
  browser bundles, environment reports or logs.
- Protected, access-controlled state with locking and recovery. Terraform's
  [OCI backend](https://developer.hashicorp.com/terraform/language/backend/oci)
  supports state locking; enable versioning on the selected private bucket.
  Review inherited tenancy/ancestor IAM and operator membership; a private
  bucket alone does not establish who can read state. Use the
  [approved backend workflow](../skills/oci-deploy/references/backend-state.md)
  before remote initialization or planning. Live lock/version/recovery acceptance
  remains pending for the kit; collect your own evidence before relying on it.
- Restart persistence, dependency failure behavior, useful readiness checks,
  actionable alarms and bounded retries.
- A restored backup and rehearsed application rollback, with measured recovery.

## Update and rollback

For native OCI state, `backend-plan --operation init --backend-config PRIVATE_JSON`
prepares initialization offline. The owner approves its hash before `backend-run`.
After initialization, prepare `backend-plan --operation plan` with the chosen
variable files/targets, approve that operation, and use `backend-run` to generate
the resource plan. Its separate resource-plan hash needs separate approval before
`apply`. The supported path uses an existing APIKey profile and the default
workspace; follow the linked workflow instead of direct remote Terraform commands.

Keep the previous immutable image digest and source revision. Review application
and schema compatibility before rollout. Prefer additive schema changes that
let the old and new app work during the rollback window. Run local/staging checks,
prepare a new cloud plan and request approval of that exact plan.

On failure, retain the private receipt and deployment logs. Determine whether
resources or data changed; do not repeatedly apply or destroy. Roll back using a
new reviewed plan. Reverting an image does not reverse database writes, payment
events, emails or other external effects. Use the agreed reconciliation procedure.

## Backup and restore

Document data scope, frequency, encryption, retention and who can restore.
Rehearse a restore into an isolated, approved target using nonproduction data.
Verify record/file integrity, permissions and the app's primary workflow; measure
recovery time and the newest recovered data. Do not overwrite the working source
to test a backup. Keep connection strings and raw dumps private.

## Cleanup

Inventory resources from successful and partial receipts. Identify shared
resources and retained backups before preparing a destroy plan. Buckets,
registries and data services can require separate reviewed cleanup; a blanket
recursive delete is not an acceptable shortcut.

Use the deploy gate for the exact approved destroy plan, then check remaining
resources. For remote state, first approve and run `backend-plan --operation
destroy-plan` through `backend-run`; separately approve its resulting resource
destroy plan. Report **present**, **confirmed removed** and **unknown** separately.
Missing permissions, unsupported identifiers and empty search results must remain
unknown until checked with suitable service-specific evidence. Review billing
and retained resources independently; do not claim that every charge has stopped
from a Terraform exit code.

Versioned state buckets retain prior state and lock history after normal updates
or lock release. Review retained bytes, exact object versions and deletion
permissions independently. State migration, state push, workspace changes, lock
repair and version-specific cleanup have no gated implementation yet. Do not
substitute a broad recursive delete or workspace deletion, and do not remove a
shared state bucket as part of application teardown.

## Incident diagnosis

Start with [read-only troubleshooting](../skills/oci-ready/references/troubleshooting.md).
Keep one hypothesis, the evidence gathered, the next safe check and the stopping
condition. Redact source data and credentials before sharing an issue. Record
the final result and next action in the [progress record](PROGRESS.md).
