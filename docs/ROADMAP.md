# Capabilities and evidence

This is an agent toolkit: deterministic local helpers support a coding agent that
implements and validates the user's application. Workflow instructions do not
establish a completed migration or a production deployment.

## 0.2.0 preview

| Capability | Included | Evidence boundary |
| --- | --- | --- |
| Claude Code/Codex installation | Project-local installer, source bundle, discoverable entry skills; Claude plugin alternative | Installer tests and plugin validation; coding agents require their own account |
| OCI access | Credential setup guide, offline doctor and opt-in IAM read probes | Unit tests with recorded/mocked responses; no real user credentials in fixtures; no live access verified for this release |
| Compartment foundation | Terraform child compartment and inspection policy for an existing developer group | Provider validation and scoped-policy tests; no cloud apply performed; workload provisioning grants remain a separate reviewed plan |
| Well-Architected design | Source-backed five-pillar review with evidence and risk decisions | Agent guidance, not Oracle certification or an automatic deployed-control audit |
| Build | Local app implementation workflow, container/PostgreSQL/storage sandbox reference, private image registry stage | App/unit/infrastructure checks; production hardening and live deploy/recovery/teardown remain workload acceptance |
| Web migration | Vercel/Netlify/Next.js static scanner, source adaptation and staged cutover workflow | Fictional fixtures and security/behavior tests; arbitrary apps need their own build, data rehearsal and target verification |
| Other clouds | IaC/SDK scanner and OCI mapping for AWS, Azure and Google Cloud | Provider-type fixture tests; map documentation freshness remains dated in the source |
| Infrastructure approval | Hash-bound saved plan, expiry, one attempt, Terraform binary check, IAM summary, private receipts and cleanup checks | Fake Terraform regression tests; actual human approval remains a conversation/harness control |
| Business case | Five founder-value skills, pricing lookup, value model and worked scenario | Existing tests; example prices and program facts carry their own source dates |

Actual results and skipped checks for this release are in
[RELEASE-0.2.0.md](RELEASE-0.2.0.md).

An optional [CI template](ci/validate.workflow.yml) is supplied. It is not
installed as an Actions workflow because the publication credential lacks that
permission; there is no GitHub CI result for this release.

## Follow-on work

- Rehearse foundation, container deployment, partial failure, backup recovery and
  cleanup in an owner-selected sandbox after approval of the exact cloud plans.
- Complete and verify a production application path: HTTPS, server-validated
  identity/authorization, secret retrieval, protected remote state and recovery.
- Rehearse a representative Vercel application migration, including relevant
  caching, scheduled work, data synchronization, traffic switch and rollback.
- Test fresh-user setup on additional operating systems and coding-agent versions.
- Add example apps only with source licenses, supported versions, dated costs,
  explicit external dependencies and evidence appropriate to their verification label.
- Add more runtime paths by composing relevant Oracle Skills where available;
  expand only with workload-specific tests and receipts.
