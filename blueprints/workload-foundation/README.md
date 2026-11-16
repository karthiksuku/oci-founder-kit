# Minimal workload foundation

Complete the prerequisites for the generic web-container target through separate
reviewed components. Reuse approved resources first. This preview does not deploy
the enterprise landing zone, grant administrator access or claim CIS certification.

| Component | Prepared resources | Deliberate boundary |
|---|---|---|
| compartments | Dedicated app and Terraform-state child compartments | Authorized non-root parent; home-region identity endpoint; no new policy or group. Deletion is protected. |
| network | VCN, public load-balancer subnet, private application subnet, internet/NAT/service gateways, routes and an empty security list | Explicit nonoverlapping RFC1918 /16; no default SSH access. App blueprint supplies reviewed NSGs. NAT permits routed egress only when NSGs allow it. |
| state | Empty private versioned bucket in the separate state compartment | No state upload, credential or IAM change. Inherited access and backend locking still need verification. Deletion is protected. |
| registry | Empty private repository in the app compartment | Digest-only publication, no implicit tag or upload. Deletion is protected. |

All components pin OCI provider 9.10.0 with the reviewed provider lock. Each has
credential-free Terraform mock-plan assertions. Mock results and configuration
handoffs are not evidence of live OCI behavior.

Run the lifecycle from the application project:

~~~sh
.oci-founder-kit/scripts/oci-kit foundation inspect --environment rehearsal
.oci-founder-kit/scripts/oci-kit doctor --environment rehearsal
~~~

Inspection consolidates missing choices and an administrator handoff. Run the
doctor's explicit live read mode when authorized to inspect OCI metadata. Denied
reads, inherited IAM, actual capacity and network overlap remain unknown until
verified. Never select a different profile to circumvent an existing deny.

To reuse existing infrastructure, provide an owner-only file containing mode
reuse, existing target/backend selections, and certificate responsibility.
The target and backend use the existing named-environment schemas.
The helper backs up the selected environment before changing it and does not
transfer old approvals or passing evidence.

For registry reuse, the [image publication gate](../../skills/oci-deploy/references/image-publication.md#prerequisites)
also requires this kit's original successful creation receipt for the selected
repository. A supplied identifier or foundation handoff does not establish that
anchor. If no matching receipt exists, prepare a separate reviewed registry
creation or retain the existing publication workflow.

To create a missing component, use a private workspace outside application
projects and their ancestors. Set mode create and supply these private JSON
fields; choices already present in the selected environment or prior component
handoff are remembered:

| Scope | Choices |
|---|---|
| Every creation | component, workspace (absolute existing 0700 directory), name, region, profile, auth (api_key or security_token), tenancy_id |
| compartments | parent_compartment_id, home_region |
| network | vcn_cidr; app compartment already bound to the environment |
| state | state_compartment_id, namespace, state_key ending .tfstate, workspace_key_prefix with no overlap |
| registry | app compartment already bound to the environment |
| Optional certificate responsibility | certificate: hostname, renewal_owner (role name), ownership (unverified or verified-by-owner) |

~~~sh
.oci-founder-kit/scripts/oci-kit foundation propose --environment rehearsal --config /private/foundation.json
.oci-founder-kit/scripts/oci-kit foundation prepare --environment rehearsal --approve '<local-proposal-sha256>'
~~~

Prepare writes only reviewed Terraform sources and owner-only variables into a
new component directory. It returns the existing deploy-gate plan command. Review
the exact cloud resources, IAM dependencies, dated cost estimate and retained
resources before separately approving the resulting cloud plan. The local
proposal hash does **not** authorize cloud execution.

Prepare one component at a time. After its separately approved apply, capture
native Terraform outputs privately and import them without copying identifiers:

~~~sh
umask 077
terraform -chdir=/private/prepared-component output -json > /private/foundation-output.json
.oci-founder-kit/scripts/oci-kit foundation handoff --environment rehearsal --outputs /private/foundation-output.json
.oci-founder-kit/scripts/oci-kit doctor --environment rehearsal
~~~

The handoff accepts only the component's typed allowlisted output bundle and
checks the selected environment, exact proposal hash, prepared source/variable
bytes and backend destination. Stale or replayed bundles are refused. App
compartments and state destinations cannot collide with sibling environments.
Output bundles remain owner-supplied configuration; a successful import does not
establish apply success, IAM isolation or live readiness.

The compartments handoff remembers the separate state compartment for the state
component. Network and registry handoffs bind the app target directly. State
handoff binds the backend destination, while initialization and synthetic lock/
recovery tests retain their own approval boundaries.

Before using any state bucket, the authorized administrator must resolve inherited
access restrictions and verify isolation. The private bucket flag alone is
insufficient. Runtime IAM is also a separate reviewed operation: preserve the
dedicated web/worker boundaries and never grant compartment-wide worker access
to the web application.

Use an existing OCI Certificates resource for HTTPS, record domain ownership and
renewal responsibility, then verify metadata with the doctor. This foundation
never accepts a certificate private key or puts one into Terraform state. Domain
purchase, certificate issuance/import, renewal and DNS traffic changes are
separate reviewed operations. Imported or externally managed certificates do not
gain automatic renewal merely by being stored in OCI Certificates.

Resources retained after a failed apply can remain billable. Obtain a dated
estimate for the exact topology; budgets are alerts, not caps. Private local
bootstrap state is sensitive even though these templates have no secret-valued
inputs. Keep it owner-only and outside Git. Cleanup requires a separate exact
plan and may require explicitly reviewing deletion protection.

Public design references reviewed 16 November 2026:
[OCI Core Landing Zone](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/oci-core-landing-zone.htm),
[certificate renewal](https://docs.oracle.com/en-us/iaas/Content/certificates/renewing-certificate.htm).
The implementation is original kit code; no internal policy or customer material
is included.
