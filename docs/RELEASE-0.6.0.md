# 0.6.0 preview evidence

This preview implements the reusable deployment and hosting-first migration
workflows. It is not a claim that an arbitrary application is production-ready or
that the two complete live OCI journeys have been accepted.

## Included changes

- A generic E4 Container Instances/HTTPS load-balancer target attaches to an
  existing app, retaining its database, storage and sign-in. It reuses selected
  networking and requires reviewed application/worker/secret-adapter evidence.
- Explicit source/rehearsal/production environments preserve legacy records,
  back up conversions, separate configuration/evidence/roots and refuse overlapping
  backend destinations. The gates bind reviewed infrastructure sources and evaluated
  workload identity; stale plans and evidence stop. Existing v0.5 commands remain supported.
- A workload-specific doctor combines bounded read-only OCI metadata and quota
  checks with private administrator handoffs. Permissions and capacity unknowns
  are not turned into passes.
- SecurityToken support spans native backend operations, deployment, synthetic
  recovery and exact-version cleanup. Expiry, rotation and identity changes stop
  stale operations; refreshed tokens need new plans and approvals.
- Hosting-first assessments, bounded HTTP parity and separate cutover/rollback
  review retain external data/auth/storage and require single-owner background work.
- A private static dashboard uses the same current bound reports and shows unknown
  costs and retained resources honestly. It makes no network requests.
- Reproducible manifest-only release archives, credential-free CI and trusted-release
  provenance workflow templates, and bounded real-agent evaluation tooling are supplied.

## Evidence boundaries

Verification on 16 November 2026:

- **744 combined Python/integration tests passed**, with the local HTTP/TLS,
  Next.js and browser migration checks enabled and no skipped tests. A preceding
  run found one outdated test fixture missing the required backend declaration;
  the fixture was corrected and the complete suite rerun.
- Site build, **20 site browser tests**, provider schema validation and **16
  web-container Terraform mock tests** passed. The migration browser checks cover
  five positive workflows, two negative controls and interrupted-run cleanup.
- **27 named-environment gate tests** passed, with independent adversarial checks.
  Actual Terraform provider configuration and mocked workload resource rows also
  passed a composite schema check for both blueprints. This composite is not a
  single live workload plan. Named gates support the reviewed Terraform files;
  custom infrastructure requires separate reviewed support.
- Local APIKey/SecurityToken signer, expiry, refresh and identity checks passed,
  including **48 focused tests** with the pinned CI SDK dependencies. These do
  not establish live session-backed OCI deployment.
- Claude Code and Codex each passed one new-app and one hosting-first trial:
  **four bounded local trials**, with independent application checks and no
  unnecessary questions observed in manual review. These used candidate snapshots
  before the final deployment-binding hardening, which was verified separately.
  Earlier development trials included two output-contract failures; their records
  remain retained. One successful trial per agent/scenario is not a reliability
  estimate or proof of a complete cloud journey.

Clean Linux installation and v0.5.0 upgrade checks preserve existing application
bytes. Deterministic archives are built from verified manifest entries only.
Public source, archive and site privacy scans check credential patterns, known
private identifiers and accidental generated/private files; pattern scans cannot
guarantee that every possible sensitive value has been detected.

No new OCI resource, traffic or IAM write was performed for this preview.

Live HTTPS deployment, hosted sign-in, two-user OCI behavior, persistence, isolated
restore, image rollback and source traffic recovery remain required sandbox
acceptance. Earlier narrowly approved registry/state synthetic tests do not prove
these outcomes or authorize another operation. Inherited IAM isolation remains
an administrator prerequisite for credential-bearing application state.

Workflow definitions and hashes are not artifact provenance. A successful trusted
GitHub build and verified attestation are needed before claiming authenticated
release artifacts. The current publication credential lacks workflow write
authority. Reviewed definitions are supplied under `docs/ci/` as templates;
hosted CI, macOS checks and artifact attestations remain unverified.

Public source references and license notes accompany the relevant guides. No
internal enterprise materials, personal account defaults or real credentials are
included intentionally. No internal enterprise source was used for these changes.
