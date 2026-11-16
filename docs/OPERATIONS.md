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
  before remote initialization or planning. A bounded synthetic OCI rehearsal
  verified writes, lock contention and historical-version recovery on 14 November
  2026, followed by separately approved exact-version cleanup. This does not
  establish your workload's inherited IAM, application state or recovery.
- Restart persistence, dependency failure behavior, useful readiness checks,
  actionable alarms and bounded retries.
- A restored backup and rehearsed application rollback, with measured recovery.

For the hardened Taskboard, use the [HTTPS acceptance checker](../blueprints/fullstack-container/PRODUCTION.md#bounded-https-checker).
Its default mode makes four anonymous reads. The explicit two-user exercise
checks authorization, CSRF and authenticated attachment round trips with synthetic
data. It removes only confirmed synthetic task rows; uploaded object versions
can remain. Preserve its private report and separately review retention/cleanup.
It does not automate hosted login, restart, restore, rollout or OCI operations.

## Update and rollback

For native OCI state, `backend-plan --operation init --backend-config PRIVATE_JSON`
prepares initialization offline. The owner approves its hash before `backend-run`.
After initialization, prepare `backend-plan --operation plan` with the chosen
variable files/targets, approve that operation, and use `backend-run` to generate
the resource plan. Its separate resource-plan hash needs separate approval before
`apply`. The supported path uses an existing APIKey or SecurityToken profile and the default
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
repair and general version-specific cleanup have no gated implementation yet.
The separate synthetic backend rehearsal supports only its own recorded exact
versions under a separate approval. Do not
substitute a broad recursive delete or workspace deletion, and do not remove a
shared state bucket as part of application teardown.

## Incident diagnosis

Start with [read-only troubleshooting](../skills/oci-ready/references/troubleshooting.md).
Keep one hypothesis, the evidence gathered, the next safe check and the stopping
condition. Redact source data and credentials before sharing an issue. Record
the final result and next action in the [progress record](PROGRESS.md).


## Collect current operating evidence

Use the [unified interface](WORKFLOW.md) with the intended named environment:

```sh
python3 .oci-founder-kit/scripts/kit.py observe --project . --environment rehearsal --live
python3 .oci-founder-kit/scripts/kit.py observe --project . --environment rehearsal
```

The first command performs bounded read-only OCI metadata/Monitoring requests.
The second renders a private static HTML dashboard from saved evidence without
network requests. No background polling or automatic telemetry is installed.
Use `--component worker` to observe an explicitly configured worker independently.
The collector requires the latest bound successful apply receipt; an interrupted,
failed, ambiguous, stale or wrong-environment receipt requires review first.

Readback checks the actual Container Instance, container image digest, selected
load-balancer health, certificate expiry, recent work requests and a bounded CPU
metric window. It verifies resource identity/compartment before accepting the
image. Missing metadata, denied monitoring, partial responses and missing samples
stay unknown. Certificate metadata does not establish hostname/chain validity.
Raw logs and arbitrary service error messages are not collected or exported.
Read the [Container Instance metric contract](https://docs.oracle.com/en-us/iaas/Content/container-instances/container-instance-metrics.htm)
and the [resource health API](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/load-balancer-health/get.html).

Observation is bounded to 20 client requests, 120 seconds overall and the existing
bounded client-output limit. Each request checks temporary-session consistency;
expiry, refresh or identity change requires a fresh observation. The live mode
label identifies an actual CLI read path, not proof of successful reads. Injected
test clients are labeled separately and cannot establish cloud image acceptance.
Reports become stale after 24 hours or a change to source, kit or environment.

For optional Usage API reads add `--cost-config /private/path/cost-period.json`.
The private JSON contains exactly `tenant_id`, `period_start_utc` and
`period_end_utc`. Choose completed UTC-midnight dates, at most 31 days apart.
The query filters the selected compartment/region and recorded resource IDs;
returned rows must match the scope and one explicit currency. Empty, truncated,
unreadable or mixed-currency responses remain unknown, never zero. Reported cost
can lag and is not the final invoice. This does not discover every retained or
shared billable resource: keep the separate inventory and migration overlap
estimate. The [Usage API contract](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/usage-api/usage-summary/request-summarized-usages.html)
is distinct from pricing estimates and budget alerts.

Use [release records](RELEASE-LIFECYCLE.md) to connect a tested image, source
fingerprint, deployment receipt and observed target. Prepare rollback to the
previous accepted digest through a new proposal and exact cloud plans, then
verify app behavior. The default single-instance deployment can interrupt service
on update or rollback. Retained database writes and external effects need their
own recovery/reconciliation procedure.

## Export a support summary

```sh
python3 .oci-founder-kit/scripts/kit.py support export --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py support export --project . --environment rehearsal --write
```

Inspect the preview before sharing the optional saved JSON. Its allowlist contains
kit/Python/platform versions, capability evidence states, safe error codes and
evidence ages. It excludes account identifiers, environment names, domains,
application source, credentials, raw logs and Terraform state. No upload occurs;
use a private security-reporting route for security issues.
