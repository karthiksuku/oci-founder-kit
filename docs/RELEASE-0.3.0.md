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
