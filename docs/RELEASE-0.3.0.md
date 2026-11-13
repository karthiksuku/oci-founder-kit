# 0.3.0 preview evidence

Checked 13 November 2026. This is a public preview, with local test results kept
separate from cloud deployment evidence. The previous release's agent-consumer
and live **read-only** OCI planning results remain in
[0.2.1 evidence](RELEASE-0.2.1.md); they are not a live test of the new hardened path.

## Current implementation checks

| Area | Result | Limits |
| --- | --- | --- |
| Repository | 309 Python tests passed; repository validator and Claude plugin validation passed | No cloud resources created by this suite |
| Hardened app | 31 Node tests passed with real temporary PostgreSQL 16; none skipped | Vault/Object Storage calls use injected doubles; OIDC uses a local RSA-signed test provider |
| Independent identity review | Additional negative tests passed for issuer, subject, nonce, expiry, session revocation and untrusted proxy headers | No hosted identity provider or deployed load balancer exercised |
| Terraform | Provider validation passed; four mocked-provider plan tests passed for sandbox, hardening and rejected insecure inputs | Mocked plans do not check permissions, capacity, certificates or service behavior |
| Read-only OCI plans | Current registry plan proposed one resource; restricted sandbox app plan proposed 29 resources, including two IAM changes, in the selected non-root compartment | No apply; image was a planning placeholder; private temporary targets and plans removed |
| Website | Static build; 12 unit/link tests and 11 browser tests passed, including mobile/keyboard, copy fallback, no-JS and privacy behavior | Automated accessibility checks do not replace a full assistive-technology audit |
| Dependencies | Website and reference app npm advisory audits reported zero known vulnerabilities at review time | A dated advisory result is not a security guarantee |
| Optional hooks | 49 tests passed; actual Claude SessionStart and PreToolUse behavior exercised | Codex parsed all four event definitions but workspace trust prevented runtime execution; no trust bypass was used |
| Fresh installations | Codex, Claude and combined installs passed; each self-contained bundle contains 194 files, with 12 entry skills per agent | Tested on Linux; additional operating systems remain unverified |
| Public publication | Main source and all 11 live website files verified anonymously against audited local bytes; live desktop/mobile/no-JS browser checks passed over HTTPS | GitHub's guide HTML was rate-limited during one extra link probe; its public raw source returned 200. Pages publication does not establish kit-validation CI or OCI deployment |

The site uses Node 22.23.4 and locked dependencies. Infrastructure checks use
Terraform 1.16.6 with committed provider lockfiles. See
[maintenance instructions](MAINTAINING.md) for reproducible commands.

## Public-content review

The release source, examples, diagrams, website output, installer bundle and
reachable Git history were reviewed for common credential patterns, internal
workplace links, real account identifiers and private local paths. Initial
independent coverage included 209 working files, 239 historical blobs and eight
commit messages, plus a fresh 192-file installer bundle. No credential or internal
content matches were identified in that scope. Final indexed content is checked
again with `python3 scripts/hooks.py public --project .` before publication.

Internal research notes remain outside this repository. Examples use fictional
values; test signing keys are generated at runtime. Public source references
carry pinned revisions and license information. Original artwork and the
self-hosted font's license are included. Existing public author attribution and
Git contact metadata remain; this is not an anonymized repository. Pattern scans
cannot prove the absence of every secret or proprietary passage.

The final indexed scan checked 211 files with no findings or incomplete coverage.
GitHub secret scanning and push protection were enabled and verified; the alert
API returned no alerts at that time. These complement review and do not detect
every proprietary passage or possible credential format.

## Fresh agent trials

An actual Claude Code consumer built a synthetic Python/SQLite feedback board
from the functional development snapshot before its manifest version was bumped
from 0.2.1 to 0.3.0. The exact installed snapshot was retained for evaluation;
separate final 0.3.0 installs passed the checks above. Independent testing found
cross-origin mutation acceptance and CSS visibility defects in the generated app.
The same normal consumer repaired them. Independent follow-up checks passed
80 generated tests, 47 HTTP assertions and 16 browser assertions, including
cross-origin rejection, restart persistence, retry recovery and mobile layout.
This is a local-only prototype trial, not production identity or cloud evidence.

An actual Codex 0.162.1 consumer used an installed 0.3.0 snapshot to migrate a
synthetic Next.js application locally. Its production build, standalone package
and seven generated tests passed. Independent source and isolated-target probes
passed 26 and 31 checks, covering routes/assets, authorization denial, headers,
synthetic data checksums, retained source data and restart persistence.

The generated HTTP harness initially chose an invalid ephemeral-port strategy.
A second normal Codex turn repaired that harness; an independent run passed
32 checks. The initial failure remains in private evaluation evidence. The
prototype's existing JSON-store concurrency failure and shared-token identity
model remain explicit limits. No real identity provider, tenant isolation,
production-data transfer, Docker runtime, OCI deployment or cutover was claimed.

## Deployment and operating limits

The hardened reference implements HTTPS configuration, OIDC verification,
server-side sessions, owner-scoped access, Vault references, database backup
configuration and object versioning. Live OCI deployment, hosted identity,
secret retrieval, restored backups, rollback, teardown and traffic cutover have
**not** been verified for this release. Complete the
[hardened guide](../blueprints/fullstack-container/PRODUCTION.md) and
[operations acceptance](OPERATIONS.md) in the selected account before real users.

The [CI template](ci/validate.workflow.yml) is prepared with immutable action
revisions, PostgreSQL fixtures and site/browser tests. It remains a template until
a workflow-capable GitHub credential installs it and a real run passes. Local
results must not be presented as a GitHub Actions pass.
