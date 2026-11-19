# Capabilities and evidence

This is an agent toolkit: deterministic local helpers support a coding agent that
implements and validates the user's application. Workflow instructions do not
establish a completed migration or a production deployment.

## 0.9.0 preview

The [unified workflow](WORKFLOW.md) connects the existing helpers. The generated
[capability registry and platform table](CAPABILITIES.md) is the canonical source
for current commands, prerequisites, evidence labels and limits. It also drives
website capability cards. The broader inventory below explains inherited features.

New in this preview: reviewed private deployment configuration, separate operator-access roles, a Well-Architected evidence report and a founder acceptance map. Inherited capabilities include additive packaging recipes, separately reviewed foundation
components, bounded OCI operating reads, optional Usage API projections, safe
support export, release records and rollback preparation, and an optional
[SaaS essentials integration](../blueprints/saas-essentials/README.md). Native
scheduling remains experimental; cloud acceptance and effective IAM are separate
from local tests. Release automation is prepared, not activated without a
workflow-authorized credential.


| Capability | Included | Evidence boundary |
| --- | --- | --- |
| Claude Code/Codex installation | Project-local installer, source bundle, discoverable entry skills; Claude plugin alternative | Installer tests and plugin validation; coding agents require their own account |
| Reusable OCI target | `web-container` attaches only infrastructure/docs to an existing app, reuses approved networking and retains external providers | Provider schema and mocked-plan tests; app-specific Vault/identity/worker controls and live OCI acceptance are still required |
| Explicit environments | Separate named source/rehearsal/production configuration, evidence and infrastructure roots, backed-up legacy conversion | Filesystem/refusal/freshness tests; records never transfer approvals or prove inherited IAM isolation |
| Workload doctor | Blueprint-specific selections, bounded metadata/quota reads, temporary-session checks and narrow administrator handoffs | Offline/mock tests; denied reads and physical capacity remain unknown, and declared image architecture is not independent image evidence |
| Hosting-first verification | Reviewed dependency outcomes, exact-origin HTTP parity, private per-origin sessions and cutover/rollback review | Local HTTP/TLS and application examples; real hosted sign-in, cross-cloud behavior, traffic changes and data migration need separate acceptance |
| Private operating view | Local static dashboard from bound reports, stale evidence, failures, recovery and dated cost/retained-resource inputs | No telemetry or cloud polling; missing data remains unknown and owner-recorded costs are not authenticated billing or spending caps |
| Project progress | New/existing/continue workflows, private checkpoints, source/evidence freshness and one next action | Offline consumer tests; records remain owner assertions, never deployment approval or independent production verification |
| Release integrity and updates | Explicit file manifest, installation ownership, update preview, conflict refusal and interruption recovery | Local integrity, legacy-upgrade and recovery tests; hashes do not authenticate the publisher, and user-edited toolkit files require reconciliation |
| OCI access | Credential setup guide, offline doctor and opt-in IAM read probes | Unit tests with recorded/mocked responses; no real user credentials in fixtures; live read-only region/compartment access verified against the configured sandbox |
| Compartment foundation | Terraform child compartment and inspection policy for an existing developer group | Provider validation, scoped-policy tests and live read-only plan; no cloud apply performed; workload provisioning grants remain a separate reviewed plan |
| Well-Architected design | Source-backed five-pillar review with evidence and risk decisions | Agent guidance, not Oracle certification or an automatic deployed-control audit |
| Build | Local app workflow, container/PostgreSQL/storage reference, optional HTTPS/OIDC/Vault configuration and private registry stage | Real local PostgreSQL and signed-OIDC tests; live deploy/identity/recovery/teardown remain workload acceptance |
| Hardened app checks | Anonymous HTTPS checks and opt-in two-session synthetic task/file exercise | Real local HTTPS application routes with synthetic backing stores; hosted login, OCI storage, restart/restore and retained-version deletion are separate acceptance |
| Local starter | Editable Taskboard project creation with local agent skills, PostgreSQL Compose preview and blueprint inspection | Creation performs no network or runtime operations; actual local app and cloud acceptance remain distinct |
| Web migration | Static scanner, runnable Next.js production-server/standalone packaging example and staged cutover workflow | Shared local HTTP checks cover the stateless example; arbitrary apps and hosted provider features need their own build, data rehearsal and target verification |
| Other clouds | IaC/SDK scanner and OCI mapping for AWS, Azure and Google Cloud | Provider-type fixture tests; map documentation freshness remains dated in the source |
| Infrastructure approval | Hash-bound saved plan, expiry, one attempt, Terraform binary check, IAM summary, private receipts and cleanup checks | Fake Terraform regression tests; actual human approval remains a conversation/harness control |
| OCI backend operations | APIKey and SecurityToken initialization/planning/deployment, fixed synthetic lock/overwrite/recovery rehearsal and separate exact-version cleanup | Session expiry/rotation/identity/signing tests are local. An earlier APIKey live synthetic run verified lock/recovery/version cleanup; live session-backed deployment/recovery, IAM isolation and application recovery remain pending |
| Image publication | Exact digest-only destination, private registry, validated image content, one-use receipt and remote manifest verification | Fake-client regressions, a local TLS registry probe and live OCI digest publication with independent content readback. Legacy tags require verified immutability |
| Managed hostname rehearsal | Optional API Gateway HTTPS entry point with restricted ingress and separate hostname bootstrap | Provider validation and mocked plans; live routing, hosted identity and gateway recovery remain unverified |
| Business case | Five founder-value skills, pricing lookup, value model and worked scenario | Existing tests; example prices and program facts carry their own source dates |
| Founder website | New/existing/continue paths, stage-aware prompts, contextual setup help, bookmarkable choices and explicit starter selection | Static browser experience; brief stays ephemeral, progress is private in the app, and no account is connected |
| Optional hooks | Local staged/public-content checks, readiness, syntax validation, mutation guard and handoff | [Dated host evidence](HOOKS.md) is bound to the tested script; changed hooks require normal host review. Local guards do not establish arbitrary shell coverage |

Actual results and skipped checks for this release are in
[RELEASE-0.9.0.md](RELEASE-0.9.0.md). Earlier release evidence remains dated in
[RELEASE-0.6.0.md](RELEASE-0.6.0.md) and
[RELEASE-0.5.0.md](RELEASE-0.5.0.md).

Credential-free validation and trusted-release provenance workflows are prepared
with a deterministic manifest-only archive builder. Publishing workflows requires
an authorized GitHub credential; a prepared workflow is not a successful Actions
run or an attestation. Read [the CI guide](ci/README.md) and dated release evidence
for the actual publication/run status.

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
