# Faster founder onboarding: research and implementation decisions

Public sources reviewed 18 November 2026. These are documentation and source
reviews, not independent deployments of Oracle Landing Zones or evidence that
this kit has completed a fresh-tenancy cloud journey. No internal documentation,
customer account data or proprietary implementation was used.

## Observed obstacles

The existing unified doctor requires a named environment. A founder beginning
with a welcome email has no environment yet. Preparing one also requires knowing
the relationship between blueprint attachment and its Terraform directory.
The foundation inspector produces administrator instructions, but the facade's
blocked-result handling previously discarded them. The initial non-root parent
and human group were prerequisites without a continuous first-account guide.

These are coordination problems across existing helpers. The implementation
adds first-run inspection and local preparation over those helpers, preserves
safe foundation diagnostics, and documents the initial administrator handoff.
The local `onboard configure` operation saves the selected profile, authentication
method and region through the existing backed-up environment helper. This avoids
repeated answers and manual JSON assembly while preserving other selections.
It does not introduce a second deployment engine or bypass the cloud gate.

## Public guidance and resulting choices

| Source reviewed | Relevant guidance | Kit decision |
|---|---|---|
| [Oracle first sign-in](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingin_topic-Signing_In_for_the_First_Time.htm) | Account activation and required security verification are interactive owner actions | The agent gives instructions; activation links, passwords and verification codes stay with the owner |
| [CLI temporary sessions](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm) | Browser authentication creates temporary local session configuration; subsequent commands select security-token authentication | Prefer an appropriate existing profile or owner-created session; inspection never silently authenticates or claims expiry was checked offline |
| [Identity-domain groups](https://docs.oracle.com/en-us/iaas/Content/Identity/groups/managinggroups.htm) | Group membership and IAM policies jointly determine access | Separate human enrollment, scoped operator permissions and runtime identities; never treat the inspection policy as deployment authorization |
| [Creating compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm) | A permitted administrator can create a compartment under the root or another compartment | Keep initial root-child bootstrap an explicit administrator action; reuse the existing non-root gate for workload children |
| [IAM structure](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/iam-security-structure.htm) | Decide identity and compartment boundaries before provisioning workloads; tenancy and domain region responsibilities differ | Record home and workload regions separately and keep app/state/runtime boundaries explicit |
| [OCI Core Landing Zone](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/oci-core-landing-zone.htm) | Modular IAM, networking and security foundations organize scoped cloud environments | Reuse the kit's small foundation components; do not silently install the full enterprise landing zone |
| [OCI Well-Architected Framework](https://docs.oracle.com/en/solutions/oci-best-practices/index.html) | Five pillars cover security, resilience, performance/cost, operations and distributed cloud | Keep a proportionate decision review with evidence and remaining risks; generated Terraform is not certification |

No third-party source code was copied for these changes. Referenced documents
remain with their publishers; the kit links them and implements its own workflow.

## What the preview is intended to establish

- A missing installation, environment or credential profile has a useful local
  next action instead of an environment-selection dead end.
- Local preparation preserves application bytes and services, chooses no
  production environment automatically, and binds the actual Terraform directory.
- Saving the three initial access choices preserves resource, backend and
  component bindings; changing a bound target's region or profile requires the
  separate reviewed full-configuration path.
- Missing nonsecret choices are grouped by the current phase. Later requirements
  remain visible without becoming prerequisites for unrelated local work.
- Foundation diagnostics survive the CLI boundary without exposing arbitrary
  input, resource identifiers or raw service errors.
- An empty-tenancy founder knows which initial user/group/parent steps need an
  administrator, and what must be checked afterward.

Actual check results belong in the release evidence and capability registry.
Local tests do not establish effective OCI permissions, usable capacity,
certificate renewal, a deployed application or recovery. Full live acceptance
still requires an authorized sandbox, exact approved plans and runtime evidence.
