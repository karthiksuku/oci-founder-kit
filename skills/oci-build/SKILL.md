---
name: oci-build
description: Build and test a useful application locally, preserve its chosen framework and services, then prepare and verify an owner-approved OCI deployment. Includes an optional container/PostgreSQL/Object Storage reference. Use for a new app, an existing containerised app or the implementation stage of an OCI web migration.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.3.1"
---

# Build a full-stack app on OCI

Start with the founder's useful outcome and the application's existing stack.
Reuse a reference when it fits, and deploy through the approval gate. A reference
is not a reason to replace working database, storage or identity services.

## Choose the path

| The app | Path |
|---|---|
| A containerised web app or API, one service, modest steady traffic | `fullstack-container` (this kit): Container Instances, PostgreSQL, Object Storage, load balancer |
| Several services, autoscaling, rolling deploys, Kubernetes already in use | OKE: route to `oracle/skills` OKE skills if installed; keep this kit's gate for the apply |
| Event-driven or bursty handlers | OCI Functions: route to `oracle/skills` Functions skills if installed |
| No container yet | Containerise first: a Dockerfile that runs as a non-root user, reads configuration from environment variables and serves `/healthz` and `/readyz` |

The `fullstack-container` blueprint lives at
`blueprints/fullstack-container` in the kit (two levels above this skill's
directory): `app/` is a reference application, `terraform/` the stack. Read
its README before changing it.

## Workflow

1. **Develop and check readiness.** Read [the app workflow](references/app-workflow.md)
   and build/test the user's app locally. Use [oci-ready](../oci-ready/SKILL.md)
   for read-only credential and target checks. For missing compartments or scoped
   permissions use [oci-foundation](../oci-foundation/SKILL.md), including its
   Well-Architected review. Missing OCI access does not block local development.
2. **Fit the app to the path.** Document its bind address, port, health endpoints,
   environment variable names and retained external services. Keep existing
   database and identity choices unless migration of them was requested.
   Only the supplied Taskboard requires its documented `APP_MODE` and adapter
   contract: sandbox `DATABASE_URL`, or the hardened
   [HTTPS/OIDC/Vault configuration](../../blueprints/fullstack-container/PRODUCTION.md).
   Other apps keep their own validated configuration contract.
3. **Test locally.** The app's own tests must pass before any image is built.
4. **Image.** Build and test it. Create the empty private registry, then enable
   immutable tags in a separately approved update through
   `oci-deploy`, then follow [gated image publication](../oci-deploy/references/image-publication.md)
   to prepare and approve the exact image upload. Never use a direct push as a
   substitute. Use existing private registry authentication; creating an auth
   token is a separate IAM change, not implied by this workflow.
5. **Variables.** Copy `terraform.tfvars.example` to a `.tfvars` file that
   Git ignores. Choose `allowed_ingress_cidrs` with the owner; there is no
   open default.
6. **Plan, cost, approve, apply** with `oci-deploy`. The plan includes IAM
   changes (a dynamic group and a policy); the gate lists them separately.
7. **Smoke test.** From an allowed address, check the app's actual health and
   primary user workflow. For Taskboard: `/healthz`, `/readyz`, create a task,
   upload and download a file when storage is enabled. Use a second user to
   verify authorization when identity is enabled.
8. **Hand over** the receipt, verified URL, dated monthly cost basis, update,
   rollback, backup/restore and teardown instructions. Report unfinished checks.

The fullstack-container defaults to a restricted sandbox. Its opt-in hardened
reference implements HTTPS, OIDC ownership checks, Vault retrieval and backup
configuration; configure protected remote state and verify the deployed controls
and recovery before real users. Use `--require-backend oci` with the gate for
that reference. Keep the default sandbox reachable only from approved addresses.

## Rules

- Never apply outside `oci-deploy`. Never widen `allowed_ingress_cidrs` to
  `0.0.0.0/0` without the owner choosing it explicitly.
- Before real users: HTTPS, server-verified sign-in through the explicitly chosen
  identity provider, resource ownership checks, approved secret retrieval and
  protected remote Terraform state. OCI identity domains and OCI Vault are
  supported choices; preserve an existing provider when that is the agreed scope.
- Keep IAM policies scoped to the compartment and the resources the app uses.

## Finish with

What is running, where, its cost per month, what is still sandbox-grade, and
the next step: production hardening, or teardown.
