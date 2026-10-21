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

| Item | Evidence of done |
|---|---|
| Machine-readable service map: AWS, Azure and Google Cloud to OCI, with fit (equivalent, partial, gap), non-equivalences and documentation links | Every OCI Terraform resource type checked against the OCI provider schema |
| `iac_scan.py`: inventory from Terraform, CloudFormation, ARM and Bicep, Kubernetes manifests, Compose files and SDK dependencies | Unit tests over source fixtures for one sample app on each cloud |
| `oci-migrate-assess` skill: inventory, mapping, gaps, effort and a first verdict | Eval prompts on the fixtures |

## Phase 2: build with approval gates

| Item | Evidence of done |
|---|---|
| `deploy_gate.py`: Terraform plan summary with a plan hash, apply only with the approved hash, receipts, destroy and teardown verification | Unit tests with a fake Terraform; one live run |
| `oci-deploy` skill | Eval prompts: never applies without approval, never applies a changed plan |
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
