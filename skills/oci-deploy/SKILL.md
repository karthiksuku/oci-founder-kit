---
name: oci-deploy
description: Deploy, change or tear down infrastructure on Oracle Cloud Infrastructure (OCI) only through an approval gate. Runs terraform plan, shows the owner the exact resources, target compartment, region and estimated cost with the plan's SHA-256, applies only that approved plan, writes a receipt of every OCID created, and verifies teardown. Use whenever a Terraform stack for OCI is about to be applied or destroyed, or someone asks to deploy, provision, spin up, update or remove OCI resources, including from the build and migrate skills.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.3.2"
---

# Approval-gated deploys on OCI

Nothing reaches an OCI account unless the owner approved that exact plan in
this conversation. `scripts/deploy_gate.py` makes the approval checkable: an
apply needs the SHA-256 of the saved plan, refuses a changed, stale or
already-used plan, and records what it created.

## The loop

1. **Check readiness (read-only).** The OCI CLI authenticates with the
   intended profile; the target compartment exists; Terraform is installed.
   Never default to the root compartment.
2. **Plan.**
   ```bash
   python3 scripts/deploy_gate.py plan --dir /path/to/stack [--var-file env.tfvars]
   ```
   Review untrusted Terraform, modules, providers and external data sources
   before running this command. A plan does not apply the declared resource
   changes, but Terraform/provider code can execute programs and read secrets;
   the gate is not a sandbox for that code.
   For the hardened reference, initialize the private OCI state backend first
   and add `--require-backend oci` to plan/destroy-plan. The gate rechecks backend
   type before apply; bucket IAM, versioning and recovery still need verification.
   For an exceptional bootstrap, an explicit `--target RESOURCE_ADDRESS` may
   select a managed resource and its dependencies. Targets appear in the summary
   and receipt. Inspect every resulting change and run a full plan afterward;
   a targeted plan does not establish the state of the whole application.
3. **Estimate the cost.** Map the planned resource types to price-list parts
   and run `founder-value`'s `price_lookup.py` and `value_model.py`, or state
   plainly that the estimate is missing. Never type prices from memory.
4. **Ask for approval.** Show the owner the gate's summary as printed: target
   region, compartment and profile; every create, update, delete and replace;
   the estimated monthly cost; anything destructive called out first; the
   plan hash. Ask a direct question: "Apply this plan?" Silence, a general
   "go ahead with the project", or approval of an earlier plan is not
   approval of this one.
5. **Apply exactly that plan.**
   ```bash
   python3 scripts/deploy_gate.py apply --dir /path/to/stack --approve <sha256>
   ```
   If the gate refuses, do not work around it: re-plan and ask again.
6. **Verify the result** (health checks, endpoints, logs) and report the
   receipt path and what was created.
7. **Tear down when asked or when a test ends.** `destroy-plan`, owner
   approval of that destroy plan, `destroy --approve <sha256>`, then
   ```bash
   python3 scripts/deploy_gate.py verify-teardown --receipt /path/to/stack/.gate/receipts/<receipt>.json
   ```
   Use the apply receipt, or the destroy receipt, which records the OCIDs it
   destroyed.
   Report anything still running or unverified, with its available identifier,
   and what it costs. Empty Search results do not prove deletion: permissions,
   unsupported resource types and indexing delay can hide existing resources.
   Use authorized service-specific checks for those unknowns before saying
   cleanup is complete. Do not change profile or region to make the check pass.

## What the gate guarantees, and what it does not

For OCI Container Registry image uploads, follow
[gated image publication](references/image-publication.md). Registry creation,
image upload and workload deployment are separate requests and approvals.
The primary image gate binds the tested local image, prepared content and exact
digest destination without assigning a tag. It records attempts and verifies the
remote manifest. The legacy tagged path still requires verified immutable tags.
A direct Docker or Skopeo push is not a substitute for that reviewed operation.

It guarantees, for any apply that goes through it:

- the applied plan file has the SHA-256 the owner was shown, the plan's
  contents still match the summary, and the same Terraform binary is used;
- an approval works once, and expires at the time fixed when the plan was made;
- every attempt leaves a receipt, including failed ones and applies whose
  result could not be read (exit 5: resources may exist);
- access (IAM) changes are listed separately in the summary.

It does not prove that a person approved anything. The approval is the plan's
hash, which the agent can read; an agent running as the same OS user could
also edit the gate's files, change the environment or call Terraform
directly. The controls for that are the owner's explicit approval in the
conversation and an `ask` permission rule for the apply and destroy commands
([references/permissions.md](references/permissions.md)). The summary shows
addresses, types and actions, not attribute values: an opened port or a
larger shape appears only as "update". Target labels come from plan variables;
the gate does not prove that every provider alias or resource uses that target.
Review those bindings before approving the plan. `verify-teardown` is a residual
resource check using OCI Search. It reports absent results and OCI resources
without usable identifiers as unknown (exit 4), rather than claiming deletion.
Exit 0 means Search reported terminal states for all checked resources; it does
not establish account-wide cleanup. Search results depend on permissions and
indexing, as explained in the [Oracle Search overview](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).

Exit codes: 0 done, 1 Terraform or OCI CLI failed, 2 bad input, 3 refused by
the gate, 4 teardown incomplete, 5 applied but not recorded.

## Rules

- Never run `terraform apply`, `terraform destroy`, `oci ... create|update|delete`
  or console automation directly. The gate is the only path.
- After exit 1 on apply, assume something may have been created: run plan to
  see the state before anything else, and tell the owner.
- One approval covers one plan. A new plan needs a new approval.
- IAM policy changes go to the tenancy's home region; show them on their own
  in the summary, because they widen access.
- Keep `.gate/`, state, `.tfvars` and receipts out of Git. Before a receipt is
  shared as evidence, redact tenancy and compartment OCIDs.
- Recommend the owner adds an `ask` permission rule for the gate's apply and
  destroy commands, so the agent's harness also asks before running them;
  see [references/permissions.md](references/permissions.md).
- A budget alert does not stop spend. For tests, plan the teardown before the
  apply.

## Finish with

What was applied or destroyed, the receipt path, the verification result,
the monthly cost while it runs, and how to tear it down.
