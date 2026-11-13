# 0.3.2 preview evidence

Checked 13 November 2026. This release adds a runnable local starter and a
blueprint contract for coding agents, informed by the public references in
[starter patterns](STARTER-PATTERNS.md). The implementation is original; no
internal source, account configuration or third-party starter code was copied.

## Local application

The new Compose preview passed 23 real startup, task-operation, status and
persistence checks with Docker Engine 29 and Compose 5 on Linux. Stopping kept
the test database volume; restarting preserved the task, password and project
identity. Attachment requests correctly reported unavailable. All synthetic
preview containers, network and volume were removed afterward. Two earlier
private rehearsal runs failed because the test copy gave source files permissions
the non-root app could not read; preserving public source permissions resolved
that fixture problem. Linux is the verified preview host; other hosts remain
unverified. Fourteen helper tests and 12 blueprint/installation tests also passed.

All 33 Node tests passed with a real temporary PostgreSQL database, including
signed OIDC fixtures, issuer validation, sessions, ownership and CSRF checks.
The temporary database was stopped and removed. The updated app was rebuilt
as a Linux/amd64 Docker image and passed 46 runtime checks: task operations,
non-root execution, restricted container settings, loopback-only app ports,
unpublished database ports, restart persistence and a logical dump restored
into a separate database/application. All eight owned temporary runtime
resources were confirmed removed; local build images were retained.

These runtime checks used sandbox mode. They do not prove hosted sign-in,
Vault access, cloud storage, managed backup recovery or a live OCI deployment.

## Image publication and actual service findings

The owner-approved empty private OCI repository was created and verified. A
separately approved update to enable immutable tags was rejected by OCI with
“Setting isImmutable is not currently supported.” The failed plan is consumed;
the repository remains private and mutable. This corrects the unverified
two-stage guidance in [0.3.1](RELEASE-0.3.1.md).

The new primary publication path assigns no tag. It validates a prepared
single-platform Docker v2s2 image against its tested configuration, compressed
blobs and uncompressed layer hashes, binds the exact digest/destination and
requires a fresh one-use approval. A real isolated TLS registry test observed
one manifest PUT to its digest, the expected blobs, no tag, and identical
remote manifest bytes. Its temporary runtime was removed.

Forty-five image-gate tests passed, including exact source and destination checks,
expiry/replay, partial failures, malformed layouts, repeated-layer bounds and
the documented segmented OCI repository/image identifier format. The gate uses
repository-scoped listing and retrieval by image ID, compatible with the tested
OCI CLI 3.68.1; newer lookup/filter commands were unavailable on that CLI. Existing
credentials successfully performed a read-only check against the exact empty
OCI repository. Live OCI digest publication remains unverified. Regional/custom
retention policy was not exposed by the configuration API and remains unverified.

The repository is retained for the ongoing rehearsal. It has not been cleaned
up. Image upload, application deployment and eventual cleanup require their own
exact plans and approvals; no approval from the failed update is reused.

## Infrastructure and identity

The optional API Gateway configuration passed provider validation and 14 mocked
Terraform tests. The targeted bootstrap plans only the gateway and its network
dependencies. It does not create the application, database or identity client.
The default load-balancer path remains available. Gateway routing, query/cookie
preservation, hosted sign-in, uploads and negative network checks still need
live acceptance; gateway mode does not include a replacement for the LB alarm.

Explicit OIDC discovery supports a document hosted separately from its issuer.
The app checks the advertised issuer against the configured expected issuer
before use, retaining token signature, state, nonce, PKCE and audience checks.
Matching and mismatched metadata tests passed; hosted provider acceptance is
still open.

## Release checks

All 395 Python tests, repository validation, Claude plugin validation, Terraform
formatting and provider validation passed. The initial integrated run found two
network assertions still using the old unindexed load-balancer address; they
were updated to check the conditional load-balancer and gateway resources, and
the complete suite passed again. Fresh project installation and blueprint
inspection passed, including exclusion of generated preview settings.

The website built with no type diagnostics. Its prompt/link test files and all
11 browser tests passed, including mobile layouts, keyboard behavior, clipboard
fallback, no-JavaScript use and automated accessibility checks. The site now
links directly to the local preview and public starter comparison.

## Remaining acceptance and privacy

The validation workflow remains a template because the connected GitHub
credential lacks workflow permission. Pages publishing is separate. Codex loaded
the hook definitions, but the owner's normal trust review and trusted runtime
test remain pending. Prior Claude hook runtime evidence is in the previous
release; the new helper checks are separately covered by repository tests.

Live OCI application deployment, hosted identity, deployed HTTPS, backup
recovery, rollback and cloud cleanup remain open. Internal research, credentials,
account identifiers, Terraform state/plans and raw receipts stay outside the
public repository. Generated local preview settings are ignored by Git,
excluded from installation, and blocked by the staged private-artifact check.
