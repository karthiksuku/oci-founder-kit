# 0.3.1 preview evidence

Checked 13 November 2026. This patch adds an explicit image-publication gate and
corrects registry setup guidance. The website and reference application are
unchanged from [0.3.0](RELEASE-0.3.0.md).

The repository validator, all 333 Python tests and Claude plugin validation
passed. Terraform formatting and registry provider validation passed. The first
restricted run could not start local test servers/provider IPC; the checks passed
with those local execution permissions. No cloud access was needed for them.

## Image publication

The gate requires the original successful registry-creation receipt, an existing
private immutable repository, a tested local single-platform Linux image and
approval of the exact upload request. It binds the image ID, size, platform,
destination, client executables and expiry. An attempt consumes the request;
success requires OCI identity and registry-manifest verification. Failed or
unverified attempts may leave remote data and must be inspected before retrying.

Twenty-four image-gate tests passed using fake OCI and Docker clients, including
changed or expired approval, replay, wrong scope, mutable/public repositories,
existing tags, unsafe files, partial failure and manifest mismatch. The existing
48 Terraform-gate tests also passed. Independent review reproduced and resolved
two defects: absent Docker variant metadata and expiry crossing during final
reads. A real local Docker inspection passed after the fix. No real image push
has been performed; simulated clients do not establish OCI publication support.

The [publication guide](../skills/oci-deploy/references/image-publication.md)
documents a private empty repository followed by a separately approved update
enabling immutability. Current Oracle creation documentation says immutability
cannot be enabled at creation. The provider exposes the update, but the live
two-stage sequence remains unverified. The gate refuses to publish if read-back
cannot confirm immutability. Linux is the tested host; other hosts are unverified.

## Actual local container and restore checks

A Linux/amd64 image was built from the unchanged reference application in the
0.3.0 source revision. Forty-six runtime checks passed with real Docker and
PostgreSQL 16.16: non-root execution, read-only application filesystem, dropped
capabilities, loopback-only application ports, no database host port, health and
task operations, invalid-input rejection, application/database restarts, and a
logical dump restored into a separate database and application. Restored records,
sequence behavior and new writes were checked. Both applications shut down
cleanly; all eight temporary containers, volumes and network resources were
confirmed removed. Local build images were retained.

These checks used the explicit sandbox application mode. They do not establish
hosted identity, TLS, Vault, OCI Object Storage, managed database backup recovery,
OCI rollback, cloud teardown or traffic cutover. Initial harness/environment
failures and their fixes were retained in private evaluation evidence.

## Other acceptance boundaries

The CI template passed actionlint 1.7.12. It is still a template: a workflow-capable
GitHub credential must install it and a real validation run must pass. GitHub
Pages publishing is a separate workflow.

Codex 0.162.1 loaded the hook definitions from an active project configuration
without parse errors. Each of the four events still requires the owner's normal
hook trust review. No trust records were modified to bypass that step, and trusted
Codex hook runtime remains unverified. Existing Claude runtime evidence is in
the previous release report.

Live OCI deployment acceptance remains open. No OCI resources, credentials or
images were created during this patch's checks. Exact plan approvals and the
chosen account's deployment prerequisites remain necessary.

## Public-content boundary

Internal research and raw evaluation evidence stay outside the repository.
Public examples and test clients use synthetic identifiers; private credentials,
Terraform plans/state and upload receipts are excluded. The public release
retains author attribution and third-party license information. Secret scanning
and push protection complement source/history and installer review; none proves
the absence of every possible secret or proprietary passage.
