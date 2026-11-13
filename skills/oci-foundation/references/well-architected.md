# OCI Well-Architected decision review

Source checked 13 November 2026:
[Oracle's Well-Architected Framework](https://docs.oracle.com/en/solutions/oci-best-practices/index.html).
Its five pillars are Security and compliance; Reliability and resilience;
Performance and cost optimization; Operational efficiency; and Distributed
cloud. These review prompts are kit guidance, not certification criteria.

Record each applicable decision with **requirement, chosen control, evidence,
residual risk, owner and validation**. Mark unknowns explicitly. Apply the
review proportionately: a learning sandbox and a production payments service
have different availability and recovery needs.

| Pillar | Decisions and evidence before real users |
|---|---|
| Security and compliance | Identify users, data sensitivity, location and retention. Separate app sign-in from OCI operator sign-in; use least-privilege compartment-scoped policies and runtime principals. Verify denied access using a second identity. Keep app/database private behind an HTTPS edge, narrow NSGs and controlled egress. Fetch secret values on the server; never place them in browser bundles, logs or Terraform outputs. Check effective inherited policies, Audit visibility, Cloud Guard coverage and incident ownership. |
| Reliability and resilience | Agree availability and recovery objectives; name the acceptable failure modes of a single instance or region. Test readiness, restart, capacity limits, backups, restoration and rollback. Record recovery point/time results instead of assuming backups are restorable. Separate application rollback from database/data recovery. |
| Performance and cost optimization | Estimate load and measure latency, throughput and resource use. Size the actual selected services and identify capacity limits. Use the kit's dated price lookup for billable components, including networking, database, storage, backups and external providers. Review tags and budget alerts; a budget is a soft alerting threshold, not a spending cap. Avoid unsupported free-tier promises. |
| Operational efficiency | Pin source/image and infrastructure versions; deploy through the exact-plan gate. Configure health checks, redacted logs, actionable alarms, ownership, patching and support. Rehearse deploy, failed deploy, update, restore and cleanup. Keep sensitive state/receipts protected and choose a supported protected state backend before team/production operation. |
| Distributed cloud | Explain workload placement and dependencies, including external identity, email, payment and AI providers. Check regional availability, data flows, residency constraints, network latency and transfer costs. For migration, verify DNS, callbacks, webhooks, state, cache behavior, cutover criteria and rollback while the source remains available. A single-region deployment can be appropriate when its risks are explicit. |

## Security controls are separate changes

The foundation blueprint creates only a compartment and a narrow inspection
policy. Configure workload networking, NSGs, HTTPS, application authorization,
Secret Management, logging and alarms through the chosen application plan.
Declare which controls are implemented, tested, proposed or blocked.

Cloud Guard initial enablement and target/responder changes can affect a
broader compartment subtree. First inspect the existing reporting region,
targets and administrator policies. Propose an explicit scope and keep
automated remediation disabled unless the owner approves it. Do not change
an established Cloud Guard setup just to make a checklist green.

Budgets and their alert recipients are account-owner choices. Show the
proposed scope and notifications separately; do not subscribe other people
or promise a hard cost ceiling. Tags help allocate costs but do not enforce
permissions or stop resource creation.

## Release evidence

- Local tests and static Terraform validation establish local properties.
- An approved cloud plan establishes intent for a specific target, not success.
- A successful apply needs runtime verification, including negative access
  checks and data persistence.
- A production release additionally needs agreed operational ownership,
  recovery evidence and accepted residual risks.

References:

- [IAM overview and home-region changes](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm)
- [Policy syntax and compartment scope](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm)
- [Managing compartments and inherited permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm)
- [Cloud Guard setup and targets](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/part-start.htm)
- [Budgets are soft limits](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm)
- [Secret Management](https://docs.oracle.com/en-us/iaas/Content/secret-management/overview.htm)
