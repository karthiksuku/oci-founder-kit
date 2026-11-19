# Give a founder a scoped OCI operator role

Use these original Terraform templates after an authorized administrator has
selected an existing human group and separate application/state compartments.
They make the required grants visible before the founder prepares infrastructure.
They do not create users, change memberships, grant administrator privileges or
claim that the application is ready to deploy.

Choose one role explicitly. Use separate groups and private working directories
when different people need different roles. A role is proposed policy text, not proof
that a member session is authorized or isolated.

| Role | Application compartment | Separate state compartment |
|---|---|---|
| `foundation-provisioner` | Create/change/delete the eight networking resource types used by the minimal VCN foundation; create/read the exact named repository, including pulling its images | Create the exact named bucket and read its metadata; no updates to an existing bucket |
| `observer` | Read selected network, Container Instance, load-balancer and metrics metadata; inspect the exact named repository | Read the exact named bucket's metadata |
| `app-deployer` | Manage the generic web target's Container Instances, load balancer and NSGs; attach to existing networking; read the selected repository and associate the selected existing certificate | No policy attached |
| `state-operator` | No policy attached | Read bucket-wide object metadata; read/write/delete only the exact state key and its `.lock` companion |
| `image-publisher` | Read/push to the exact existing repository; OCI's required update permission also permits image, tag and signature mutations | No policy attached |

The network types are VCNs, subnets, route tables, security lists, DHCP options,
internet gateways, NAT gateways and service gateways. The provisioner can change
or delete existing resources of those types in the selected app compartment;
use a dedicated compartment. The observer also reads network security group
metadata, but this does not include every operation for inspecting NSG rules.
Container Instance configuration and metrics can contain sensitive operational
metadata, including environment-variable values. If an existing application puts
plaintext secrets there, a configuration reader can see them. Treat observer
access as access to private workload information; keep secret values in Vault
and use runtime retrieval instead of plaintext container configuration.
Bucket metadata access also permits multipart-upload and existing preauthenticated
request summaries, which can reveal object names and access settings. The summary
does not return a preauthenticated access URL; that URL is available only when
the request is created. Keep this metadata private.

The original `foundation-provisioner` and `observer` grants remain unchanged.
They exclude state content, publication and app deployment. Every role excludes
IAM administration, human enrollment, direct Vault secret-bundle reads,
preauthenticated request creation, retention-rule changes, bucket deletion and
bucket/repository settings that could make an existing private resource public. These creation permissions do not constrain
every initial resource setting: use the kit's reviewed private-bucket/repository
plans. Later configuration changes require a separate administrator review and
exact plan. Inherited permissions can be broader and are never revoked by this
template. The provisioner's repository read permission permits image pulls;
the observer and state roles exclude repository image content access.

## Deployment, state and publication boundaries

`app-deployer` supports the generic `web-container` with `manage_runtime_iam=false`.
An administrator must already have configured the runtime identity, image-pull
access and any app-specific secret access. The existing certificate, registry,
VCN, public/private subnets and Container Instances must use the dedicated app
compartment for this role. A certificate elsewhere needs a separately reviewed
policy in its own compartment; do not broaden this policy to the tenancy.
The role includes exact certificate metadata/public bundle reads and association
management, but no certificate private-key read or certificate creation/renewal.
Certificate association behavior still requires live acceptance.

Deployment grants include resource deletion and changing traffic/exposure through
NSGs and load-balancer configuration. They are compartment-wide for these resource
types, not limited to resources named by the kit. VCN attachment/detachment supports
NSG creation/deletion without granting VCN creation, configuration or deletion.
Container, load-balancer and NSG moves are excluded. Container log retrieval is
excluded, though work-request diagnostics remain available. Creating arbitrary
containers also lets the operator exercise the runtime identity's permissions
indirectly. A direct secret-read exclusion does not prevent code deployed by that
operator from using existing runtime secret permissions. Keep workers and state
in separate compartments and review the effective runtime permissions.

`state-operator` requires `state_key`. It grants content operations on exactly that
key and `<state_key>.lock`; no wildcard or non-default Terraform workspace is
granted. The backend enumerates workspace keys during initialization, so the role
also grants **bucket-wide object metadata** listing. Use a dedicated bucket with
no unrelated workloads. Reads include historical state at the permitted name;
state may contain secrets and must remain private. `OBJECT_DELETE` allows deletion
of the current state/lock object and can leave versioning markers; the role does
not grant `OBJECT_VERSION_DELETE` for permanently deleting prior versions. Version
cleanup and restoration remain separate exact reviewed operations. Keep versioning
enabled and verify the backend's synthetic lock/recovery test before real state.

`image-publisher` is **not upload-only**: Oracle requires `REPOSITORY_UPDATE` for
pushes and also uses it for deleting/restoring images, removing versions and
changing tags/signatures. `REPOSITORY_MANAGE`, which controls repository settings
and visibility, is excluded, as are repository creation/deletion. Use the existing
digest-only publication gate for each actual upload. That gate restricts this
workflow; it cannot prevent a human with the role using another client to perform
other allowed image operations. Review this authority before granting membership.

## First account: the administrator handoff

1. The account owner activates the account and completes sign-in, required MFA
   and recovery setup in their browser. Keep activation links, passwords, MFA
   codes, private keys and session tokens out of chat and Git.
2. Reuse the intended identity domain and existing group where suitable.
   Otherwise, the administrator creates a dedicated group and reviews each
   membership change in the Console. Use the group's OCI OCID in this template,
   not its SCIM identifier or an assumed default-domain group name.
3. If only the tenancy root exists, the administrator creates a non-root parent
   through the Console as a separate reviewed action. The existing deployment
   gate intentionally refuses the tenancy root; do not insert a dummy child
   identifier to hide a root operation.
4. Use an authorized administrator to prepare the separate app/state children
   with the [compartments foundation](../workload-foundation/README.md). The
   provisioner role here does not itself create compartments or policies.
5. Verify the selected group belongs to this tenancy and review its members,
   inherited policies, domain roles and any tenancy-wide grants. Never use
   `Administrators` or `All-Domain-Users` as a shortcut for this workload role.

The administrator applying this template needs policy-authoring permission in
each compartment receiving a policy; the original two roles attach in **both**. The application and state policies attach separately;
an application-child policy does not grant access to a sibling state compartment.
An inherited deny or denied read requires the authorized administrator to resolve
the boundary. Do not switch identities to circumvent it.

## Prepare the exact policy plan

Work in a new private directory outside the application and repository. Copy
`terraform/*.tf`, the pinned `.terraform.lock.hcl`, and
`terraform.tfvars.example` there. Rename the example to `access.tfvars`, replace
the placeholders privately, and restrict the directory to mode 700 and the
variables to mode 600 on POSIX. Verify equivalent owner-only ACLs elsewhere.
Keep local Terraform state private; these templates contain no credential inputs
but the state still contains account identifiers and access policies.

Required inputs are the expected tenancy, selected group, app compartment,
separate state compartment, exact repository/bucket names, role, policy prefix,
home region, profile and authentication method. `state-operator` additionally
requires `state_key`; `app-deployer` requires `certificate_ocid`. Other roles can
omit those fields. The authenticated profile must
match the expected account. The IAM region must equal the confirmed home region;
the app may use another subscribed region. The template compares the supplied
region values, but does not independently discover the home region.

From the kit checkout, with `PRIVATE_ACCESS_STACK` set to that private directory:

```sh
terraform -chdir="$PRIVATE_ACCESS_STACK" fmt -check
terraform -chdir="$PRIVATE_ACCESS_STACK" init -backend=false -lockfile=readonly
terraform -chdir="$PRIVATE_ACCESS_STACK" validate
python3 skills/oci-deploy/scripts/deploy_gate.py plan \
  --dir "$PRIVATE_ACCESS_STACK" --var-file access.tfvars
```

Initialization downloads the pinned public provider. Planning reads OCI and
writes local plan/state evidence. Review both policy attachments, the exact group,
every statement and any changes to existing policies. The gate flags both
resources as IAM changes. Show the full private Terraform plan as well as the
gate summary: its headline names the app compartment, while the second policy
targets the separately declared state compartment. Only after the owner approves
that exact plan, use the gate's printed apply command. Do not run raw apply or
claim an approved plan was already executed.

The `oci-kit foundation` access component can prepare this template with an
explicit role and bind its private handoff to the named environment and proposal.
Its output transfers no target resources or authorization claims. Standalone use
can omit `environment` and `request_sha256`; when supplied, both are required.
Use the existing deploy gate for every cloud change and never pass this policy
stack off as a named web deployment or transfer prior approvals.

Existing v0.8 state has two unindexed policy addresses. The included `moved`
blocks preserve those resources as `[0]` when introducing optional attachments.
Review the full plan when upgrading; the same original role should not replace
policies solely because of this address change. Changing role can remove an
attachment and alter grants, so it requires its own exact reviewed plan.

## Verify access and continue

Verify every planned policy attachment and statement with the administrator. After IAM
propagation, use a separate member session to inspect the intended metadata.
Check denied access to an unrelated compartment, another environment's state
content and direct secret APIs. For state operators test approved synthetic names
only; for app deployers account for indirect runtime authority.
Record the identity, target, timestamp, actual result and remaining inherited
grants privately. Do not print object content, secrets or unredacted policy IDs
into shared reports. A denied inventory read does not prove an absent resource.

For the provisioner, prepare the [network, state and registry components](../workload-foundation/README.md)
under separately reviewed plans. The bucket/repository grants cover creation
and reads, not later updates, deletion or image uploads. This blueprint's mocks validate configuration
and grant boundaries, not actual service permission evaluation. Exact name
conditions can make broad list operations unavailable; use explicit known
resource identifiers and administrator inspection instead of broadening grants.
OCI policy condition matching can be case-insensitive: review name collisions
before granting access, even though these inputs require lowercase names.

The three new roles propose separate workload, publication and state grants.
Container Instance runtime identities, effective certificate integration, backend
locking and billing reads still need separate review and live acceptance.
The observer does not grant certificate metadata, billing access, raw logs,
registry image reads or all checks needed by the operations dashboard. Missing
reads remain unknown. No role grants tenancy-level region/limit/IAM
inventory; the administrator can supply those prerequisites privately.

Before production use, verify meaningful positive and negative access checks in
OCI and the [Well-Architected decisions](../../skills/oci-foundation/references/well-architected.md).
Terraform mock tests are local evidence only. No live policy apply or denial
test was performed to establish this template. Policy removal or changing role
is another exact reviewed plan, not automatic cleanup.

## Public design references

Reviewed 19 November 2026. The templates are original code; no external Terraform
module, internal policy or customer configuration was copied.

- [First sign-in and security verification](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingin_topic-Signing_In_for_the_First_Time.htm)
- [Identity-domain groups and required administrator roles](https://docs.oracle.com/en-us/iaas/Content/Identity/groups/managinggroups.htm)
- [Policy group subjects by OCID](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm)
- [Create a parent compartment](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm)
- [Compartment inheritance and policy attachment](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm)
- [Home region and IAM propagation](https://docs.oracle.com/en-us/iaas/Content/Identity/regions/managingregions.htm)
- [Networking resource types and API permission dependencies](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm)
- [Container Registry permissions and name conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/registrypolicyreference.htm)
- [Object Storage permissions and bucket-name conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm)
- [Repository reads permit image pulls](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registrypolicyrepoaccess.htm)
- [Preauthenticated access URL is only available at creation](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests_topic-To_create_a_preauthenticated_request_for_all_objects_in_a_bucket.htm)
- [Container Instance metadata permissions](https://docs.oracle.com/en-us/iaas/Content/container-instances/permissions/policy-reference.htm)
- [Container configuration and environment variables](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/container_instances_container_instance.html)
- [Load-balancer metadata permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/lbpolicyreference.htm)
- [Metric read permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/monitoringpolicyreference.htm)
- [Exact object-name IAM conditions](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm)
- [Certificate identifiers, public bundle conditions and associations](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/certificatespolicyreference.htm)
- [Native Terraform OCI backend state/lock paths and permissions](https://developer.hashicorp.com/terraform/language/v1.16.x/backend/oci)
