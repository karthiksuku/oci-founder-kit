# Roadmap

Each item is done only when its evidence exists in the repository: tests,
a validated plan, or a live deploy and teardown receipt.

## Phase 0: foundation

| Item | Evidence of done |
|---|---|
| Decide track (five `founder-value` skills, value model, price lookup) | Unit tests, worked example, headless agent smoke test |
| One plugin for Claude Code and Codex, single-plugin marketplace | `claude plugin validate .`, isolated install |
| Router skill `oci-kit` and the approval-gate contract | Skill contract tests, eval prompts |
| `oci-ready` and a read-only `oci_doctor.py` | Unit tests with recorded CLI output; one read-only run against a real tenancy |

## Phase 1: migrate discovery

| Item | State | Evidence |
|---|---|---|
| Service map: AWS, Azure and Google Cloud to OCI with fit, differences, migration method and docs | **Done** | `tests/test_service_map.py`: OCI types against oracle/oci 9.10.0; source types against aws 6.69.1, azurerm 5.10.0, google 8.7.0 and CloudFormation spec 268.0.0; 52 doc links checked live 2026-10-21 |
| `iac_scan.py`: Terraform, modules, CloudFormation/SAM, ARM/Bicep, Deployment Manager, Kubernetes, Compose, SDK manifests | **Done** | `tests/test_iac_scan.py` over fixtures for AWS, Azure, Google Cloud and Kubernetes |
| `oci-migrate-assess` skill | **Done** | Headless session with explicit invocation on the AWS fixture: ran the scanner, correct fits and CDN mapping, assessment written, source untouched |
| `oci-kit` router and safety contract | **Done** | Skill validation |
| Implicit triggering | Open | Two plain-language sessions on a machine with about 190 other skills answered without invoking the kit; measure again in a clean profile |
| Eval suite for the Migrate skills | Next | Scored headless sessions per release |

## Phase 2: build with approval gates

| Item | Evidence of done |
|---|---|
| `deploy_gate.py`: Terraform plan summary with a plan hash, apply only with the approved hash, receipts, destroy and teardown verification | **Built.** 34 tests with a fake Terraform, including nine findings from an adversarial review. Live run pending |
| `oci-deploy` skill | **Built.** States what the gate guarantees and what it cannot. Eval prompts pending |
| Golden path `fullstack-container`: web frontend and API on Container Instances behind a load balancer, managed database, Object Storage, Vault, logging, alarms, budget, OIDC sign-in | `terraform validate`; a live deploy in a sandbox compartment, smoke test, teardown receipt |
| Sample full-stack application used by both Build and Migrate | Its own tests; runs locally and on OCI |
| `oci-build` skill | Eval prompts and the live receipt above |

## Phase 3: migrate execution

| Item | Evidence of done |
|---|---|
| `oci-migrate-plan`: waves, target architecture, data strategy, cutover and rollback criteria | Eval prompts on the fixtures |
| `oci-migrate-data` runbooks: PostgreSQL, MySQL, object storage, key-value and document stores | Each runbook rehearsed on sample data |
| `oci-migrate-cutover`: DNS, traffic switch, validation, rollback, decommission | A rehearsed cutover of the sample app from a source cloud |

## Phase 4: more paths and proof

| Item | Evidence of done |
|---|---|
| Golden paths on OKE and OCI Functions, routed to `oracle/skills` where it covers the procedure | Live receipts |
| An eval suite that runs headless agent sessions against the skills and scores them | Results recorded per release |
| Continuous integration: tests, validators, `terraform fmt` and `validate` | Green runs on the repository |
