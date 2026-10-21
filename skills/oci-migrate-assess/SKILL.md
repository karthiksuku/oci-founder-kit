---
name: oci-migrate-assess
description: Migration assessment for moving an application from AWS, Azure or Google Cloud to Oracle Cloud Infrastructure (OCI). Use it whenever someone asks what it would take to move an app or repository to OCI, which OCI services replace their current ones, what does not map, or what to migrate first, even for a small repository. It runs a tested scanner and a service map checked against the OCI, AWS, azurerm and Google Terraform providers, so fit, gaps and alternatives (for example Cloudflare@OCI for CDN, the S3 Compatibility API for object storage) come from evidence rather than memory. Reads Terraform, CloudFormation/SAM, ARM/Bicep, Deployment Manager, Kubernetes, Compose and SDK dependencies, and produces a migration assessment with an effort signal and a first-wave recommendation. Read-only.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.1.0"
---

# Migration assessment

Turn a repository on AWS, Azure or Google Cloud into an evidence-based answer:
what runs today, what each piece becomes on OCI, what does not map cleanly,
how big the job is, and which workload to move first.

Everything here is read-only. Never change the source cloud, the repository
or an OCI account from this skill.

## Workflow

1. **Agree the scope.** Which repositories or folders, and which
   environments. Infrastructure created by hand in a console does not appear
   in code; say so up front.
2. **Scan the code.**
   ```bash
   python3 scripts/iac_scan.py /path/to/repo --out migration-scan.md
   python3 scripts/iac_scan.py /path/to/repo --format json --out inventory.json
   ```
   The scanner skips dependency and build folders and never opens `.env`
   files, keys, certificates, Terraform state or `.tfvars`. Paths in its
   output are relative.
3. **Fill what code cannot show** with
   [references/interview.md](references/interview.md): data volumes, traffic,
   recovery targets, residency, identity provider, third-party services, CI/CD,
   and commitments with the current provider.
4. **Optionally confirm against the live account.** Only with the owner's
   explicit go-ahead and their own read-only credentials, using the commands in
   [references/live-inventory.md](references/live-inventory.md). This catches
   console-created resources the scan missed.
5. **Decide a strategy per workload** with
   [references/strategies.md](references/strategies.md): rehost, replatform,
   refactor, retain or retire, and pick a first wave.
6. **Write `migration-assessment.md`** following
   [references/assessment-template.md](references/assessment-template.md).
7. **Hand off:** costs to `founder-value-economics` (current invoice against
   OCI list prices), the detailed plan to `oci-migrate-plan`, deploys to
   `oci-deploy`. Name a hand-off even when that skill is not installed yet.

## How to read the scan

- **Partial fits and gaps come first.** Each one is a decision someone must
  make (redesign, keep on the old cloud, accept a feature loss). List the
  decision and its owner; do not bury it in a table.
- **Unrecognised resources** are unknowns, not zero work. Review each by hand
  and say what it is.
- **SDK findings** mean code changes. `cloud-sdk` means the package is generic
  (for example `boto3`); find the call sites before estimating.
- **Self-hosted images** run unchanged on OCI; a managed service is an option,
  not a requirement.
- **Kubernetes coupling** (load balancer annotations, ingress classes, storage
  classes, pod identity) must be replaced for OKE.
- **The effort signal** (S, M, L, XL) is a heuristic from the map's
  complexity ratings. Present it as a signal with its method, never as an
  estimate in weeks.

## Rules

- Evidence classes as in `founder-value`: `measured`, `stated`, `sourced`,
  `assumed`. The scan is `measured` for what is in code and nothing else.
- Do not claim compatibility the service map does not support. Where a
  feature matters (an extension, an API call, a limit), check the linked OCI
  documentation for that feature and cite it.
- Do not open secrets, Terraform state, `.tfvars` or `.env` files, and do not
  print credentials found by accident; stop and tell the owner.
- Do not run commands against the source cloud without explicit approval;
  read-only listing commands only.
- Name AWS, Azure and Google Cloud factually as migration sources.

## Finish with

The first-wave recommendation, the open decisions with owners, the effort
signal with its caveat, and one next action labelled **read-only**, **local
write** or **owner action**.
