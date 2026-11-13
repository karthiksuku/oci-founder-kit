---
name: oci-foundation
description: Set up a dedicated OCI workload compartment and scoped IAM access, then review networking, secrets, monitoring and recovery against OCI Well-Architected guidance before building or migrating an application. Use after OCI authentication works; cloud changes require approval of the exact plan.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.3.4"
---

# Prepare the OCI foundation

Help the user establish the account boundaries their app needs. Reuse existing
resources when appropriate; do not make a second landing zone automatically.

1. Run `oci-ready` first. Confirm the authenticated tenancy, profile, home
   region and an existing non-root parent compartment. Keep credentials and
   private target identifiers outside Git. If the account is new, guide the
   owner through account verification and administrator setup; do not sign up
   or create a permanent administrator key on their behalf.
2. Inspect existing compartments, identity-domain groups, policies and network
   controls read-only. Ask only for choices that change access, location or
   cost. Separate production and development, including data and credentials.
3. Read the [foundation blueprint](../../blueprints/foundation/README.md).
   Bind `tenancy_ocid` to the expected authenticated account; this is account
   metadata, not a tenancy-root resource target. It creates a child compartment
   and a read-only policy for an existing developer group. It does not create
   users, groups, memberships, networks
   or a production security baseline. Group creation and identity-domain
   enrollment need the separate administrator bootstrap in that guide.
4. For app deployment, propose only the additional resource permissions the
   selected blueprint needs, scoped to this workload. Do not grant developers
   tenancy-wide administration, IAM management or secret-value access by
   default. Runtime resource-principal permissions and human deployment
   permissions are separate policies.
5. Complete the [Well-Architected review](references/well-architected.md).
   For each relevant decision record evidence, residual risk and the next
   validation action. A checked box does not establish a deployed control.
6. Generate and validate local Terraform. The foundation's `region` must be
   the tenancy home region; its `compartment_ocid` is the existing parent.
   Reuse `oci-deploy` to plan, show resource and IAM changes and dated cost
   estimates, then apply only the exact plan explicitly approved by the
   owner. Never use direct OCI writes or raw `terraform apply` as a shortcut.
7. Verify the created child's parent, policy scope and the intended developer
   identity's access. Positive access must work and access outside the
   approved workload must fail. Inspect inherited grants too: this policy
   cannot revoke broader grants inherited from elsewhere.

For a production app, configure and test private app/data networks, narrow
NSGs, HTTPS and application sign-in, secret retrieval, logging, alerts,
backup/restore and updates as part of the selected workload plan. Review
Cloud Guard and budgets with the account owner. Do not enable or overwrite
tenancy-wide settings merely to complete a workload setup.

Finish with the target, evidence, approved changes, remaining blockers and
next build/migration step. Keep local receipts private; provide redacted
evidence for sharing. Explain approved cleanup, retained data and resources
that still incur costs. Never describe a foundation-only apply as a secure
production application or as Oracle certification.
