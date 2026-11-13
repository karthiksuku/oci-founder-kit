---
name: oci-build
description: Build and deploy a full-stack application on Oracle Cloud Infrastructure (OCI) from a tested golden path - web UI and API in a container, OCI Database with PostgreSQL, Object Storage uploads through a resource principal, load balancer, private networking, alarms - with Terraform that is applied only through the oci-deploy approval gate. Use when someone wants to build a new app on OCI, deploy an existing containerised app to OCI, or turn an idea into a running OCI stack, as a developer or technical founder.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.2.0"
---

# Build a full-stack app on OCI

Start from a golden path that has been validated, adapt it to the app, and
deploy through the approval gate. Do not hand-write a new architecture when a
golden path fits.

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
2. **Fit the app to the path.** The app must listen on the address in `HOST`
   and `PORT`, take `DATABASE_URL` and `DATABASE_CA_CERT`, and use
   `OCI_BUCKET`, `OCI_NAMESPACE` and `OCI_REGION` with a resource principal
   for files. Use the reference app's adapters as the pattern.
3. **Test locally.** The app's own tests must pass before any image is built.
4. **Image.** Build it, and push to OCI Container Registry. Creating an auth
   token for the registry is an IAM change: it needs the owner's approval,
   and the token is stored only in the owner's credential store.
5. **Variables.** Copy `terraform.tfvars.example` to a `.tfvars` file that
   Git ignores. Choose `allowed_ingress_cidrs` with the owner; there is no
   open default.
6. **Plan, cost, approve, apply** with `oci-deploy`. The plan includes IAM
   changes (a dynamic group and a policy); the gate lists them separately.
7. **Smoke test.** `app_url` from an allowed address: `/healthz`, `/readyz`,
   create a task, upload and download a file.
8. **Hand over** the receipt, verified URL, dated monthly cost basis, update,
   rollback, backup/restore and teardown instructions. Report unfinished checks.

The existing fullstack-container is a sandbox reference, not a universal app
converter. For real users, implement and test HTTPS, server-verified identity,
authorization, proper secret retrieval, durable protected state and recovery first.
Keep the default sandbox reachable only from approved restricted addresses.

## Rules

- Never apply outside `oci-deploy`. Never widen `allowed_ingress_cidrs` to
  `0.0.0.0/0` without the owner choosing it explicitly.
- Before real users: HTTPS, sign-in through an OCI identity domain, secrets
  in OCI Vault, remote Terraform state. Say so in the hand-over.
- Keep IAM policies scoped to the compartment and the resources the app uses.

## Finish with

What is running, where, its cost per month, what is still sandbox-grade, and
the next step: production hardening, or teardown.
