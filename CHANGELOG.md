# Changelog

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
