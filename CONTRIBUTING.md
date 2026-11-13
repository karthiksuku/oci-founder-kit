# Contributing

Open a focused pull request with the user-visible problem, change and actual
validation results. Read AGENTS.md. Keep credentials, real customer artifacts,
state, plans and unredacted receipts outside Git. Use fictional test fixtures.

For code changes, run the repository validator, Python tests and relevant app or
Terraform checks. Skill changes should be evaluated with realistic build/setup
and migration requests, including denied access and partial failure. Record what
was not tested. Do not mark a deployment verified from a static scan or fake CLI.

Examples should include the pinned source revision, license, prerequisites,
external accounts, cost basis, expected behavior, cleanup and known limitations.
An OCI-verified label needs redacted evidence from the exact revision and approved
sandbox deployment/recovery/cleanup; public links alone are source-reviewed.

Use SECURITY.md for reporting security problems; never post credentials in an issue.
