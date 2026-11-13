# 0.2.1 preview: fresh-user testing and installation fix

Test date: 13 November 2026. Public baseline tested: `3bf5146` (0.2.0).
The installer fix was verified independently before this patch release.

## Installation defect fixed

Fresh project installation dropped executable bits from bundled helpers. The
source checkout passed tests, but its installed deployment-gate suite failed
with permission errors. Installation now normalizes executable files to mode
755 and regular files to 644, dropping special mode bits. A regression executes
the installed helper. The original failing installed suite now passes all 38
checks; installer checks pass on the source and installed bundle.

The original public install was tested in both-agent, Codex-only and Claude-only
modes, with path spaces, dry run, existing skills, symlink refusal and the
remove/reinstall procedure. Existing app instructions and unrelated skills were
preserved. The patched installed source passes its own validator.

A consumer assessment also named generic Well-Architected categories without
loading the OCI guide. Entry and migration workflows now explicitly require the
canonical source before naming pillars, including source-only assessments. The
subsequent actual Codex run loaded that reference and scoped Git inspection to
the selected app. Local runtime guidance uses unique app-owned temporary paths
and owned child-process cleanup.

## Application and infrastructure evidence

- Reference app against an isolated real PostgreSQL 16 database: 21 tests passed,
  including SQL parameterization, data constraints and attachment metadata.
- Real HTTP reference app: create, invalid-input rejection, update, delete and
  persistence across app restart passed. The temporary database and app were
  stopped afterward. No existing database was modified.
- A runnable Next.js application was built and adapted to standalone Node output.
  A local exact-path shim represented the fixture's Vercel rewrite/header settings;
  it was explicitly not a live Vercel deployment. All 36 runtime assertions passed:
  authentication and bypass denial, routing/headers, runtime environment metadata,
  asset packaging, fictional record transfer, source retention and restart persistence.
- Live read-only OCI doctor passed against the configured sandbox: active region
  subscription and readable active nonroot compartment. Deployment permissions
  and capacity remain unknown until separately checked.
- Live read-only saved-plan rehearsals passed for foundation (2 creates), private
  image registry (1 create) and app infrastructure (29 creates). No plan was
  applied. Group/account metadata and plans were kept private and removed after
  testing; no images were pushed and no infrastructure resources were created.

## Agent consumer testing

Actual Claude Code loaded the installed entry and build skills and generated a
Python/SQLite request tracker. Independent verification passed 56 unit tests and
10 HTTP/restart checks. Its initial build run ended at the evaluator's small
usage-estimate cap rather than returning a final answer; a short verification
pass on the same unchanged source completed normally with 56 tests and 14 smoke
checks passing. The app remains a local development example with explicit OCI
and production blockers.

Actual Codex loaded installed skills, ran the migration scanner and produced a
source assessment while preserving the original code. A second run using the
corrected reference routing implemented a standalone Next.js package, nonroot
Dockerfile, tests, validation/persistence fixes and an operational handover. It
read the canonical OCI review and named all five pillars correctly. Baseline
and adapted builds/package checks passed; its nested sandbox denied socket
startup and Git branch creation, and the agent reported those limits rather
than bypassing them. Independent verification of the actual Codex-generated target then passed a
fresh build/package run, its eight smoke-check groups and 30 separate HTTP,
authentication, validation, asset, concurrency, private-file and restart checks.
Sixteen concurrent creates retained all records with unique IDs; runtime metadata
changed without rebuilding. Test servers and temporary data were cleaned up.

## Regression verification

- Repository validator: zero problems.
- Full Python suite: 238 tests passed, including the installed-executable regression.
- Independent installed bundle: 38 deployment-gate tests and 10 installer tests passed.
- Claude marketplace validation passed; direct plugin validation passed with the
  existing root-CLAUDE.md advisory. Consumer instructions are shipped as skills.
- Terraform formatting passed; schemas and read-only live plan results above
  cover all three blueprints. No infrastructure apply was used as a test shortcut.

## Limits

This is a preview. No live OCI app deployment, Object Storage upload, production
identity lifecycle, cloud backup recovery, DNS traffic switch or teardown was
performed. Native Windows execution/ACLs and additional fresh-account enrollment
flows remain untested. Local fixture and plan success do not establish universal
migration compatibility, spare OCI capacity or production readiness.

The optional CI template remains uninstalled because the connected publication
credential lacks GitHub workflow permission. No GitHub Actions result is claimed.
