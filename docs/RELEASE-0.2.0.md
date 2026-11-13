# 0.2.0 preview release evidence

Release date: 13 November 2026. This release provides agent workflows and local
helpers; it is not a claim of a completed arbitrary workload migration or a
production-ready app deployment.

## Verification

- Repository validator: **0 problems**.
- Python regression suite: **237 tests passed**, including project-local
  installation, credential diagnosis, migration discovery, foundation scope,
  approval/receipt behavior and reference-app checks.
- Reference app: **17 tests passed**. PostgreSQL integration suite was not run
  because no dedicated `TEST_DATABASE_URL` was supplied. No real database was
  selected implicitly.
- Dependency audit after compatible body-parser lockfile update: **0 known
  vulnerabilities reported by npm** at validation time. This is not a guarantee
  against undisclosed vulnerabilities.
- Terraform formatting and provider validation: foundation, private registry
  and full-stack application blueprints all passed, with zero provider
  diagnostics. Validation used the committed OCI 9.10.0 locks and Terraform
  1.16.6. No plan/apply was run.
- Claude marketplace validation passed. Direct plugin manifest validation
  passed with the existing advisory that a root CLAUDE.md is maintainer context,
  not installed plugin context; consumer instructions live in skills.
- Fresh Codex-only installation forward-test: all 12 skill entry references
  resolved; an installed scanner identified the synthetic Vercel/Next.js signals
  and environment variable names while excluding `.env.local`.
- Both-agent install check: 24 generated entries resolve their source; the installed
  bundle passes the repository validator.
- Independent review identified installer secret-file/symlink handling and raw
  provider error exposure. Fixes and regression tests are included.
- Credential-pattern review of the four prior commits and release source tree
  found no flagged credentials outside deliberately synthetic test fixtures.
  Build caches, private working files, state and receipts are excluded.

Tests that bind loopback sockets or launch Terraform provider processes were
run with the local execution permission needed by this environment. A restricted
sandbox initially blocked a reference-app socket; the permitted rerun passed.
No test required cloud write permission.

## Preserved work and limits

The original checkout's uncommitted work was preserved. Only inspected registry,
regional-storage and partial-apply source fixes were copied into this isolated
release checkout. No state, credentials, private receipts or cloud plans are
published.

No OCI resources, source-provider accounts, production data or DNS were changed.
Live credential reads, deployment, recovery and teardown were not rehearsed for
this release. The minimal foundation creates a child compartment and inspection
policy for an existing developer group. Actual deployment/runtime IAM policies
and production controls require the workload-specific reviewed plan.

The existing full-stack app is a restricted sandbox. HTTPS, application sign-in,
production secret retrieval and protected remote state remain required work
before real users. Native Windows filesystem ACLs and additional fresh-user
operating-system/coding-agent combinations have not been exercised here.

An optional GitHub Actions template is included at
`docs/ci/validate.workflow.yml`. The connected publication credential lacks
GitHub's `workflow` permission, so it cannot install `.github/workflows` files.
An authorized maintainer can copy the template into that directory later.
No GitHub Actions run is claimed; the checks above ran locally.
