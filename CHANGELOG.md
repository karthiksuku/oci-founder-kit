# Changelog

## Unreleased

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
