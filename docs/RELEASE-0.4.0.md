# 0.4.0 preview — create, continue and rehearse

This preview improves the path from reading the kit to working in your own
application. It adds an explicit editable Taskboard creator, a task-specific
website handoff with a resume prompt, and a small runnable Next.js packaging
rehearsal. Existing cloud approval and credential boundaries are unchanged.

## Editable application creation

`python3 scripts/blueprint.py create fullstack-container --project PATH --agent both`
exports the existing Taskboard into a separate project with editable app source,
infrastructure templates, local preview helper and project-local agent skills.
It generates project instructions and a progress record. Creation is offline;
it does not install dependencies, run tests or start containers. The returned
commands and `not_run` results distinguish creation from runtime verification.

This is an explicit Node.js/PostgreSQL starter choice. Existing applications and
requested Next.js/FastAPI stacks keep their own source and workflows. The
general installer remains available for those projects.

## A clearer first result and return path

The site shows the chosen task's first observable checkpoint and a resume prompt
that inspects existing installation and project evidence before continuing.
Only allowlisted task, agent and stack selections are kept in a bookmarkable
fragment. The brief remains ephemeral; it is never written to URLs, storage or
network requests. The site does not measure completion or grant cloud approval.

## A runnable packaging rehearsal

The [Next.js example](../examples/migrate-nextjs/README.md) compares a production
Next.js server with its standalone package using shared HTTP behavior checks.
Its capability matrix separates the stateless local example from provider
features, production data and deployed OCI behavior that still need validation.
The older discovery-only fixture remains available for scanner demonstrations.

## Verification

Verified on Linux on **14 November 2026**:

- **512 repository tests passed**, including the opt-in real Next.js HTTP
  rehearsal. Repository validation, Claude plugin validation, Terraform
  formatting and blueprint metadata checks passed.
- **17 creator tests passed** within that suite. Independent negative probes
  checked ancestor replacement, preservation of concurrent user files, no-write
  dry runs and generated guide links. Creation uses exclusive writes; it is not
  an atomic directory transaction. A failed publication preserves partial output
  for review rather than deleting destination files.
- A separately created Taskboard ran with real local PostgreSQL. Health,
  readiness, invalid-input refusal and create/read/update/delete passed. An
  edit to its own `app/` appeared after rebuilding; its task survived stopping
  and restarting. The source template and hidden toolkit app stayed unchanged.
  The owned test containers, network, synthetic database volume and app image
  were removed after verification.
- The stateless Next.js example passed **17 shared HTTP checks per runtime**
  against normal `next start`, standalone output and its built Docker container.
  The container was healthy, ran as UID 1000 with a read-only filesystem and
  loopback host publication, and was removed with its test image afterward.
  The dated production-dependency audit reported zero advisories.
- The site built with zero reported errors, warnings or hints. **15 unit/link
  checks and 17 browser tests passed**, including keyboard use, clipboard
  outcomes, bookmark/history behavior, ephemeral briefs, no-JavaScript fallback,
  and mobile/desktop accessibility checks in both themes. Visual review found
  no overflow, failed assets or browser errors in the four viewport/theme runs.
- Public-content review found no credential or internal-identifier patterns.
  Project installation and creation exclude local state, credentials and build
  artifacts. Pattern scans are useful checks, not proof against every possible
  secret or proprietary concept.

The combined run initially exposed a test-option name that conflicted with the
backend's OCI environment guard. The option was renamed to
`FOUNDER_KIT_NEXTJS_PARITY`; the guard was retained and the full run passed.
The local Docker host needed a checked unused subnet because its automatic
address pools were exhausted. The Next.js container used that host's explicitly
selected legacy builder because Buildx was unavailable. These local setup
adjustments did not change cloud settings or establish hosted behavior.

## Remaining acceptance

This preview does not establish full hosted application deployment or migration.
Effective IAM isolation, hosted identity, deployed HTTPS/Vault controls, data
recovery, traffic cutover and broader cloud teardown require workload-specific
evidence. The dated synthetic OCI write/lock/recovery and exact-version cleanup
results remain recorded in [0.3.4 evidence](RELEASE-0.3.4.md).

The validation Actions workflow remains a template because the available
publication credential lacks workflow permission. Normal trusted Codex hook
runtime remains unverified. Native Windows and fresh-user macOS runs are not
established by Linux validation.
