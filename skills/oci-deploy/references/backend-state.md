# Approve remote state operations before they run

Terraform planning can create and delete backend lock objects. Initialization
contacts the selected backend and can install modules/providers. Prepare and
approve that activity before running it; approval of an eventual resource apply
does not retroactively authorize initialization or planning.

The kit provides an offline `backend-plan` and a one-attempt `backend-run` for
native OCI backend initialization, resource planning and destroy planning. A
successful backend operation is not proof of least privilege, lock contention,
state recovery or production readiness. The full live lock/version/recovery
acceptance remains pending.

The optional [synthetic backend rehearsal](backend-rehearsal.md) provides a
separately approved fixed lock/overwrite/version-recovery test and exact-version
cleanup. Local native behavior and fake-client orchestration have been tested;
live OCI write/recovery acceptance remains pending.

## Establish the storage boundary

Select an existing private, versioned state bucket separately from application
uploads. Keep its creation state and receipt outside that bucket. Review:

- The exact operator identity, existing API-key profile, region, namespace,
  bucket, state key and lock key. The lock key is the state key plus `.lock` in
  the [pinned Terraform 1.16.6 implementation](https://github.com/hashicorp/terraform/blob/v1.16.6/internal/backend/remote-state/oci/backend.go#L18-L19).
- Effective IAM for the bucket, including applicable tenancy and ancestor
  compartment policies and group/dynamic-group membership. A restrictive Allow
  statement does not revoke another applicable Allow. `NoPublicAccess` is a
  bucket visibility setting, not a list of authorized readers; review existing
  pre-authenticated requests separately. State can contain credentials even when variables are marked
  sensitive. Review [Oracle IAM policy inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policies.htm)
  and [bucket access](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingbuckets.htm).
- Necessary object operations: inspect, read, create, overwrite and normal
  delete, restricted to the reviewed state/lock scope where the service permits.
  Updating an existing state key needs `OBJECT_OVERWRITE`; an initial successful
  creation does not establish that permission. Version-specific deletion uses
  the separate `OBJECT_VERSION_DELETE` permission. See the
  [Object Storage operation-to-permission table](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).
- Version retention, encryption, request/storage costs and recovery ownership.
  Versioning retains prior content and deletion markers, including history from
  normal lock operations: the [pinned unlock implementation](https://github.com/hashicorp/terraform/blob/v1.16.6/internal/backend/remote-state/oci/client.go#L284-L335)
  performs an ordinary delete, not deletion of a specific historical version.
  Versioning adds storage and eventual cleanup obligations; it
  does not prove a usable restore. See [Oracle object versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Do not put credential-bearing state into a bucket whose inherited access has
not been accepted. Creating a private bucket does not narrow existing IAM.
Changing IAM, creating the bucket, or deleting retained versions each requires
its own reviewed scope and approval. A storage estimate or budget alert is not a
hard spending limit.

## Supported configuration

This path supports the native `oci` backend, an existing `APIKey` profile and
the `default` workspace only. The backend supports other authentication methods,
but this gate does not yet accept them. See the
[HashiCorp OCI backend reference](https://developer.hashicorp.com/terraform/language/backend/oci).

Use Terraform 1.16.6 for the reference's verified local command behavior. Review
all Terraform, modules, providers and external data sources first. Source hashes
bind root configuration, the dependency lockfile and automatic variable files;
they are not an integrity sandbox for installed module/provider implementations.

The stack must contain exactly one backend declaration, named `backend.tf.json`:

```json
{"terraform":{"backend":{"oci":{}}}}
```

Copy the [declaration example](../../../blueprints/fullstack-container/terraform/backend.tf.json.example)
without adding inline attributes. Put the actual destination in a private JSON
file using the [backend settings example](../../../blueprints/fullstack-container/terraform/backend.tfbackend.json.example).
It must contain exactly these seven nonempty string fields:

| Field | Reviewed value |
|---|---|
| `bucket` | Existing private, versioned state bucket |
| `namespace` | The bucket's Object Storage namespace |
| `region` | The bucket's actual OCI region |
| `key` | Explicit relative object path ending in `.tfstate` |
| `workspace_key_prefix` | Explicit prefix Terraform may list; no workspace creation is authorized |
| `auth` | `APIKey` |
| `config_file_profile` | Existing local OCI profile name |

Replace every example placeholder, including the fictional `replace-region-1`.
Keep the directory private and settings/variable files readable only by their
owner (`0700` directory, `0600` files). Store credentials in the existing private
OCI configuration/key files; never put key material, tokens or passwords in this
JSON, Git, chat or shell arguments. Plans, backend metadata and receipts also
remain private.

Use a clean process environment. The gate refuses `OCI_*`, `TF_CLI_ARGS*`,
Terraform logging, alternate CLI configuration and provider reattachment
overrides. It refuses redirected `TF_DATA_DIR`, non-default `TF_WORKSPACE`,
non-default cached workspace selection, cloud blocks and provider-defined
`state_store` configuration. Do not work around those checks or silently switch
the selected identity. Review any changed environment and prepare a fresh packet.

## 1. Prepare and approve initialization

From the kit checkout, prepare an offline operation:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-plan \
  --dir /private/workload/terraform --operation init \
  --backend-config /private/workload/backend.tfbackend.json
```

`backend-plan` reads local inputs and fingerprints the Terraform executable; it
does not invoke Terraform or contact OCI. It writes the private
`.gate/backend-plan.json` packet. Review its destination, exact state/lock names,
workspace list prefix, source/binary/input hashes, authentication choice, costs
and expiry. Ask the owner to approve that exact SHA-256 in the conversation.
Approval lasts at most 120 minutes and permits one attempt.

Only after that approval:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-run \
  --dir /private/workload/terraform --approve <backend-init-sha256>
```

The gate consumes approval before invoking initialization and records the
attempt under `.gate/backend-receipts/`. It verifies the resulting destination
against the approved settings. It refuses an existing local state/workspace
history or a change to a different backend; this is not a migration procedure.
Provider/module installation and backend requests happen during this approved
run, not during offline preparation.

## 2. Approve planning, then review its resource plan

Once the approved backend is initialized:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-plan \
  --dir /private/workload/terraform --operation plan \
  --var-file production-common.tfvars --var-file production.tfvars
```

Variable files must be private files directly inside the stack. This operation
uses the initialized destination; do not pass `--backend-config` again. For an
exceptional bootstrap, repeatable `--target RESOURCE_ADDRESS` arguments bind the
selected managed resources and their dependencies. Targets do not establish
whole-stack readiness; run a full plan after bootstrap.

Obtain approval of the new backend-operation hash, then run:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-run \
  --dir /private/workload/terraform --approve <backend-plan-sha256>
```

This approved operation runs resource planning with the existing backend; it
does not reinitialize it. Planning may create and release lock objects, read
state and refresh resource metadata. Review the resulting saved resource plan,
every change, IAM statements and current cost estimate. The resource plan has a
different hash and requires **separate owner approval** before:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py apply \
  --dir /private/workload/terraform --approve <resource-plan-sha256>
```

The apply approval covers that saved resource plan and its bound backend. The
gate rechecks source/backend bindings and refuses changed, expired or previously
attempted plans. Plain `plan`/`destroy-plan` refuses a detected remote backend,
including stale remote metadata after a declaration was removed.

For resource teardown, use the same two approvals: `backend-plan --operation
destroy-plan`, approved `backend-run`, then approval of the resulting resource
destroy plan followed by `destroy --approve <resource-plan-sha256>`.

## Failure, recovery and cleanup boundaries

If a backend run fails, preserve its private receipt and inspect the outcome
with authorized read-only checks. Lock objects or retained versions may have
changed. Do not repeatedly run a consumed approval, use a direct Terraform
command as a fallback, disable locking or force-unlock an active operation.
The gate's hashes and receipts do not prove that a human approved them; keep the
[coding-agent permission controls](permissions.md) and conversational approval.

The kit does not yet provide gated state migration, state push, workspace
creation/deletion, lock repair or version-specific cleanup. Native OCI locking
and version support are service/implementation capabilities, not completed live
acceptance for this kit. Rehearse recovery in a separately approved isolated
target before relying on it for a workload.

Keep the state bucket separate from app teardown. Before eventual version
cleanup, stop all clients, review current locks, enumerate exact object names
and version IDs with complete pagination, and obtain separate approval and
permissions for those versions. Do not delete by broad prefix or use workspace
deletion as a cleanup shortcut. Retain required audit/bootstrap evidence and
report any history that remains; a successful app destroy does not remove it.
