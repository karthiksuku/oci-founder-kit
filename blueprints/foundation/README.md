# Workload foundation

Create a dedicated child compartment and a read-only inspection policy for
an **existing, explicitly selected developer group**. This is a minimal
bootstrap, not a complete landing zone or production application.

## Administrator preparation

An OCI account owner must first complete signup/verification and establish
an administrator recovery path. Reuse their normal identity-domain sign-in
and MFA. The agent can guide setup and validate access without receiving
passwords, MFA codes or private key contents in chat.

The owner or delegated administrator chooses an existing non-root parent
compartment and an existing group. If either is missing, prepare it as a
separate, explicitly reviewed administrator action. User/group creation and
membership changes are identity/tenancy administration, not permissions that
this workload policy grants. Guide the administrator through the Console;
do not bypass the kit's gate with direct API writes. Do not silently add all
users to a group, reuse Administrators or grant `manage all-resources in tenancy`.

For an identity-domain group, use the group's OCI OCID as supported by IAM
policy syntax. Confirm it belongs to the intended tenancy. Adding or
removing a group member changes who can access this workload and requires
its own review. The authenticating administrator needs permission to create
a child under the selected parent and create its attached policy. The
developer group receives neither capability from this blueprint.

Authenticate using a local OCI profile, security-token session or an
approved workload principal. The provider supports these methods; select
the same identity and region as the readiness checks. Private configuration,
keys, token files and state stay outside Git. See
[provider authentication](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm)
and the [credentials guide](../../skills/oci-ready/references/credentials.md).

## What Terraform creates

| Resource | Scope |
|---|---|
| `oci_identity_compartment.workload` | A new child of `compartment_ocid`; this variable must identify an existing non-root compartment |
| `oci_identity_policy.developer_inspect` | Attached to the child; grants the selected group `inspect all-resources` in that child only |

The policy intentionally permits inventory, not application provisioning,
application data reads, secret reads, user/group changes or tenancy-wide
administration. Existing inherited grants may be broader; this policy does
not revoke them. Additional workload deployment/runtime permissions must be
reviewed against the chosen application's exact resources. Inspection
access alone cannot deploy the full-stack blueprint.

IAM writes run in the tenancy's **home region**. `region` is therefore the
home region for this stack, even if the app will run elsewhere.
`tenancy_ocid` explicitly identifies the expected account and is bound in
the OCI provider. Compare it with the authenticated identity before planning;
setting an account identifier does not authenticate or grant access to that
account. It is account metadata, not permission to target the tenancy root.
`compartment_ocid` means **parent compartment** in its plan summary; the new
workload compartment is an output after apply. The existing non-root parent
is the bootstrap boundary; root-level identity setup is not hidden in this
plan.

## Prepare, plan and review

From the kit root, copy `terraform/terraform.tfvars.example` to an ignored
local `.tfvars` file and replace placeholders. Do not put real targets in
the committed example. Backend selection and sensitive state protection are
owner decisions; this minimal stack uses Terraform's local backend until
the operator configures a protected backend. Keep the working directory
private, and establish remote locking/state protection before team use.

```bash
terraform -chdir=blueprints/foundation/terraform fmt -check
terraform -chdir=blueprints/foundation/terraform init -backend=false
terraform -chdir=blueprints/foundation/terraform validate
python3 skills/oci-deploy/scripts/deploy_gate.py plan \
  --dir blueprints/foundation/terraform --var-file foundation.tfvars
```

`foundation.tfvars` is resolved relative to the Terraform directory. `init`
downloads a provider; `plan` reads cloud resources. Neither is an apply.
Review the exact tenancy, parent compartment, profile, authentication method,
home region, child name, group OCID, policy statement,
all resource actions and cost implications with the owner. The plan gate
lists IAM changes but does not prove the user approved them. Only after
the owner approves that exact plan in the conversation, use the gate's
printed `apply --approve <sha256>` command. Never run raw `terraform apply`.

The `.terraform.lock.hcl` pins the OCI provider used for validation. Review
and intentionally update it when upgrading providers.

## Verify and continue

Verify the child's parent and lifecycle state, policy attachment and
statements using read-only calls. Confirm a group member can inspect this
child and cannot access an unrelated compartment unless separately
authorized. Use the output `workload_compartment_ocid` for the application
stack's `compartment_ocid`; continue with `oci-build` or `oci-migrate-web`.

Before real users, the application plan must implement and test its network
boundaries, NSGs, HTTPS, sign-in and authorization, secret retrieval, logs,
alerts, backups and recovery. Review Cloud Guard coverage and budget alerts
separately. Follow the
[Well-Architected review](../../skills/oci-foundation/references/well-architected.md).

Cleanup is a separate destructive plan through `oci-deploy destroy-plan`
and `destroy`, with explicit approval. Remove or retain workload resources
and data by agreement before deleting a compartment. Verify residual
resources and asynchronous compartment deletion status; a successful API
request does not establish that deletion has completed. No cloud apply or
cleanup was performed to validate this blueprint.
