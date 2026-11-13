# Capabilities and evidence

This is an agent toolkit: deterministic local helpers support a coding agent that
implements and validates the user's application. Workflow instructions do not
establish a completed migration or a production deployment.

## 0.3.0 preview

| Capability | Included | Evidence boundary |
| --- | --- | --- |
| Claude Code/Codex installation | Project-local installer, source bundle, discoverable entry skills; Claude plugin alternative | Installer tests and plugin validation; coding agents require their own account |
| OCI access | Credential setup guide, offline doctor and opt-in IAM read probes | Unit tests with recorded/mocked responses; no real user credentials in fixtures; live read-only region/compartment access verified against the configured sandbox |
| Compartment foundation | Terraform child compartment and inspection policy for an existing developer group | Provider validation, scoped-policy tests and live read-only plan; no cloud apply performed; workload provisioning grants remain a separate reviewed plan |
| Well-Architected design | Source-backed five-pillar review with evidence and risk decisions | Agent guidance, not Oracle certification or an automatic deployed-control audit |
| Build | Local app workflow, container/PostgreSQL/storage reference, optional HTTPS/OIDC/Vault configuration and private registry stage | Real local PostgreSQL and signed-OIDC tests; live deploy/identity/recovery/teardown remain workload acceptance |
| Web migration | Vercel/Netlify/Next.js static scanner, source adaptation and staged cutover workflow | Fictional fixtures and security/behavior tests; arbitrary apps need their own build, data rehearsal and target verification |
| Other clouds | IaC/SDK scanner and OCI mapping for AWS, Azure and Google Cloud | Provider-type fixture tests; map documentation freshness remains dated in the source |
| Infrastructure approval | Hash-bound saved plan, expiry, one attempt, Terraform binary check, IAM summary, private receipts and cleanup checks | Fake Terraform regression tests; actual human approval remains a conversation/harness control |
| Business case | Five founder-value skills, pricing lookup, value model and worked scenario | Existing tests; example prices and program facts carry their own source dates |
| Founder website | Build/migrate/setup prompt builder, guides, examples and light/dark themes | Static build, browser/mobile/keyboard and automated accessibility checks; no account connection or credential collection |
| Optional hooks | Local staged/public-content checks, readiness, syntax validation, mutation guard and handoff | Unit tests and actual Claude runtime; Codex schema parsed but trusted runtime remains unverified |

Actual results and skipped checks for this release are in
[RELEASE-0.3.0.md](RELEASE-0.3.0.md).

An optional [CI template](ci/validate.workflow.yml) is supplied. It is not
installed as an Actions workflow because the publication credential lacks that
permission; there is no GitHub CI result for this release.

## Follow-on work

- Rehearse foundation, container deployment, partial failure, backup recovery and
  cleanup in an owner-selected sandbox after approval of the exact cloud plans.
- Verify the hardened reference in OCI: hosted identity/authorization, HTTPS,
  runtime secret retrieval, protected remote state, backup restore and rollback.
- Rehearse a representative Vercel application migration, including relevant
  caching, scheduled work, data synchronization, traffic switch and rollback.
- Test fresh-user setup on additional operating systems and coding-agent versions.
- Add example apps only with source licenses, supported versions, dated costs,
  explicit external dependencies and evidence appropriate to their verification label.
- Add more runtime paths by composing relevant Oracle Skills where available;
  expand only with workload-specific tests and receipts.
