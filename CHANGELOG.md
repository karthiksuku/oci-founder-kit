# Changelog

## 0.3.4 - 2026-11-13

- Fixed synthetic OCI backend rehearsal with separate exact approval, observed native lock contention, overwrite and historical-version recovery into a separate key.
- Separate exact-version cleanup; no workspace/prefix deletion or forced unlock.
- Private identity/source binding, bounded output retention, normal unlock on failure and conservative handling of interrupted native launches.
- Local native behavior and fake-client controls are verified; live OCI write/recovery acceptance remains pending. See [0.3.4 evidence](docs/RELEASE-0.3.4.md).

## 0.3.3 - 2026-11-13

- Offline preparation and one-attempt approval for OCI backend initialization
  and resource planning. Remote lock/state activity is reviewed before running;
  applying the resulting resource plan still requires its separate exact approval.
- Backend/source/environment checks prevent changed destinations, stale legacy
  plans and expired operations from reaching Terraform. Local planning remains
  available through the deploy gate.
- Private JSON backend settings are excluded by Git, project installation and
  staged-content checks. Hooks flag direct Terraform init/plan calls for review.
- Updated state-access, versioning and recovery guidance; APIKey/default-workspace
  limitations and remaining live acceptance are recorded in
  [0.3.3 evidence](docs/RELEASE-0.3.3.md).

## 0.3.2 - 2026-11-13

- Local Taskboard/PostgreSQL preview with persistent data, private generated
  configuration and separate start/status/stop commands.
- Offline blueprint metadata inspection, informed by public AWS, Azure and
  Google Cloud starter patterns, with pinned references and license provenance.
- Digest-only image publication with validated content and no remote tag
  assignment. Corrected OCI registry identifier handling and service-dependent
  immutability guidance; legacy tagged publication still requires immutability.
- Optional restricted API Gateway managed-hostname rehearsal, explicit resource
  targets in reviewed plans, and OIDC discovery with a separately pinned issuer.
- Installer and staged-content guards exclude private preview files. Runtime,
  restore and public-content evidence is recorded in
  [0.3.2 evidence](docs/RELEASE-0.3.2.md).

## 0.3.1 - 2026-11-13

- Separate approval gate for publishing a tested image to an existing private
  OCI registry: exact image and destination, expiry, one-use attempts and remote
  digest, image configuration and platform verification.
- Two-stage registry instructions: create empty, then separately review enabling
  immutable tags. Publication refuses mutable repositories and existing tags.
- Local Docker runtime and logical PostgreSQL restore evidence, plus clearer
  limits for live OCI, GitHub validation CI and trusted Codex hook execution.
- Public-content and fresh-install checks repeated for the release; see
  [0.3.1 evidence](docs/RELEASE-0.3.1.md).

## 0.3.0 - 2026-11-13

- Static founder website with build/migrate/setup prompt builder, light/dark
  themes, mobile and keyboard support, and public-source examples.
- Safer IaC inventory output, bounded discovery, malformed-input handling and
  cleanup verification that preserves unknown results instead of claiming success.
- Opt-in local hook pack with staged/public content checks, readiness, relevant
  validation, common cloud-mutation guards and evidence reminders.
- Explicit hardened container reference: HTTPS, verified OIDC identity,
  per-user authorization, PostgreSQL sessions, runtime Vault secrets, pinned
  database secret version, backup policy and remote-state guidance/checks.
- Project brief, progress, migration acceptance, troubleshooting and operations
  guides; version/status inspection for project-local installs.
- Local checks do not establish live OCI deployment, hosted identity, recovery
  or traffic cutover. See the release evidence for exact coverage and limits.

## 0.2.1 - 2026-11-13

- Preserve executable helpers during project-local installation; the installed
  deployment-gate tests now run successfully. Special permission bits are not copied.
- Route named Well-Architected reviews to the canonical reference during web
  migration and scope Git inspection to the selected workload.
- Record fresh public-install, real PostgreSQL/runtime, agent-consumer and
  read-only OCI readiness/plan rehearsals with explicit live-deployment limits.

## 0.2.0 - 2026-11-13

- Project-local installer for Claude Code and Codex, with self-contained source
  resources and no overwrites of existing app instructions or skills.
- OCI credentials/readiness diagnostics, scoped compartment/IAM foundation,
  five-pillar Well-Architected review and Vercel/Next.js migration workflow.
- Build-first routing, source reviewed ecosystem references and explicit preview
  limits; preserves sandbox and exact-plan deployment approval boundaries.
- Private image registry stage, single/multi-AD database storage selection and
  partial-apply resource receipts from the existing source fixes.

### Previously unreleased build and assessment work

- `oci-build` and the `fullstack-container` golden path: a reference Taskboard app
  (Express, PostgreSQL with verified TLS, Object Storage uploads through
  pre-authenticated requests and a resource principal) and Terraform for
  Container Instances, OCI Database with PostgreSQL, a load balancer, private
  networking, scoped IAM and an alarm. Security properties are pinned in tests.
- `oci-kit`: entry skill that routes requests to the Decide, Build or Migrate
  track and carries the kit's safety contract.
- `oci-migrate-assess`: read-only migration assessment with `iac_scan.py`
  (Terraform, registry modules, CloudFormation/SAM, ARM/Bicep, Deployment
  Manager, Kubernetes, Compose, npm/PyPI/Go/Maven/Gradle/NuGet dependencies).
- Service map of 59 OCI target services and about 330 rules, tested against
  the OCI, AWS, azurerm and Google Terraform providers and the CloudFormation
  specification; `scripts/refresh_provider_types.py` refreshes those lists.
- Example migration scan of an AWS application.
- `oci-deploy` and `deploy_gate.py`: Terraform applies only for the exact plan
  approved (SHA-256), with an expiry fixed at plan time, one-time use, the same
  Terraform binary, re-checked plan contents, IAM changes called out, receipts
  for every attempt and teardown verification. Hardened after an adversarial
  review; its limits are documented in the skill.

## 0.1.0 - 2026-10-21

First preview.

- Five skills: `founder-value`, `founder-value-economics`, `founder-value-ai`,
  `founder-value-gtm`, `founder-value-brief`.
- `value_model.py`: durable and cash gross margin, margin bridge, payback with
  and without credits, the credit cliff, runway, AI cost per action.
- `price_lookup.py`: search, part lookup and scenario filling from Oracle's
  public price list API, with tier support and dated provenance.
- Worked example priced on 2026-10-21; program facts checked the same day.
- Claude Code plugin and single-plugin marketplace, Codex plugin, Agent
  Plugins manifest; repository validator and unit tests.
