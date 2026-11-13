# Test native state locking and recovery with synthetic data

Use this optional rehearsal before entrusting a backend with application state.
It tests the native OCI backend's write, overwrite, lock contention and recovery
behavior using two synthetic outputs and no infrastructure resources. It does
not establish effective IAM isolation or restore an application/database.

The implementation has local Terraform and fake-client evidence. Live OCI
write/lock/recovery acceptance remains pending. The read-only metadata adapter
has been checked against an existing private, versioned bucket.

## Prerequisites and scope

Use POSIX, Python 3.11+, Terraform **1.16.6**, and the OCI Python SDK in the same
Python environment as the gate. The adapter has been exercised with SDK 2.167.2;
it records the installed version. Installing the OCI CLI in a separate pipx
environment does not necessarily make its SDK importable by `python3`. Review
dependencies before installing them; the gate does not install packages.

Select an existing API-key profile in `~/.oci/config`. Its key path must expand
to an absolute path, its RSA public fingerprint must match, and configuration
and key files must be private regular files without symlinks. The gate binds the
profile's tenancy/user/fingerprint, config/key hashes, HOME, source and Terraform
binary. Key material and passphrases stay in memory and existing private files;
never paste them into the target file, chat or Git. Native child commands use a
fixed environment, disable update checks and exclude inherited auth, proxy,
Terraform and HTTP overrides. Only commercial-realm OCI endpoints are supported.

Prepare a fresh directory with mode `0700` outside your source checkout. Keep
the successful bucket creation receipt available. If that receipt lacks an OCI
bucket OCID, its exact bucket name, compartment, region, tenancy and profile are
still checked; obtain the actual bucket OCID through a separate read-only
GetBucket lookup. Execution independently rechecks that exact bucket identity,
private visibility and enabled versioning. Review [effective IAM and storage
retention](backend-state.md) separately. Synthetic success never authorizes
credential-bearing state in a bucket with unaccepted inherited access.

Create a private `0600` target JSON containing exactly:

```json
{
  "bucket": "replace-bucket-name",
  "namespace": "replace_namespace",
  "region": "replace-region-1",
  "bucket_id": "ocid1.bucket.oc1..replace",
  "compartment_id": "ocid1.compartment.oc1..replace",
  "tenancy_id": "ocid1.tenancy.oc1..replace"
}
```

## Prepare one fixed recipe

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-rehearsal-plan \
  --dir /private/backend-check --target /private/target.json \
  --bucket-receipt /private/bucket-creation-receipt.json --profile DEFAULT
```

This preparation is offline. Review `.gate/backend-rehearsal-plan.json`, its
SHA-256, expiry, exact destination and dated request/storage estimates. It
generates a fresh run identifier and exactly four permitted object names under
`backend-check/<run>/`: primary/recovery state and their `.lock` objects. A
separate unused workspace prefix may be listed; only the default workspace is
used. The recipe refuses preexisting objects, versions or markers in its prefix.

After the owner approves that exact packet in the conversation:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-rehearsal-run \
  --dir /private/backend-check --approve <exact-rehearsal-sha256>
```

The single attempt includes these fixed steps:

1. Initialize three isolated native clients with no external modules/providers.
2. Push a generated state containing only the run identifier and generation 1.
3. Hold a real plan lock using a bounded loopback HTTP data source. Require a
   competing plan to fail on that observed lock before reaching its data source.
4. Release the holder normally; require the competing plan to succeed afterward
   and persistent state/version content to remain unchanged.
5. Generate generation 2 using only validated generation 1's lineage and serial
   plus one. Native persistence may advance the serial again; record the actual
   state hash and version ID.
6. Retrieve the exact recorded first version and recover it to the separate
   recovery key. Require generation 2 at the primary key to remain unchanged.

The loopback port and native lineage/serialization are constrained runtime
values; source hashes bind their transformations. This is not an arbitrary
state-push interface. No apply, resource creation, IAM change, migration,
force-unlock, disabled locking or automatic cleanup is included.

Private receipts record each attempted command and observed versions. Native
output retains at most 256 KiB per command while a separate reader drains excess
without blocking the writer. A timeout stops subsequent work, releases the
loopback fixture and gives native clients time to finish/unlock normally. It
does not kill them. A client that remains alive is reported as unresolved;
do not retry, force-unlock or clean up until its outcome is reconciled. The
HTTP wait is bounded at 30 seconds; this does not guarantee a hard total cloud
execution deadline. Approval expiry stops new commands, not normal unlock.

## Review permanent cleanup separately

Versioning retains previous state, lock versions and deletion markers. The
rehearsal leaves them in place. Once native clients have finished and no current
locks exist, prepare a fresh exact-version plan:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-cleanup-plan \
  --dir /private/backend-check --receipt /private/backend-check/.gate/rehearsal-receipts/<hash>.json
```

Cleanup preparation performs bounded **read-only** inventory and content checks.
It refuses unknown state payloads, active locks or unresolved native launches.
Review every object name/version ID and marker in `.gate/backend-cleanup-plan.json`.
Permanent deletion is irreversible; obtain separate approval of that exact hash:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py backend-cleanup-run \
  --dir /private/backend-check --approve <exact-cleanup-sha256>
```

The gate rechecks the complete inventory, deletes only approved version IDs,
removes historical data before markers, and keeps current data until last.
It requires empty current **and** version listings before reporting success.
It never uses workspace deletion, prefix deletion, an unversioned object delete
or bucket deletion. An interrupted or stale cleanup is consumed; reconcile and
prepare a new remaining-version plan rather than retrying the old approval.
The bucket and its original local bootstrap state remain retained.

## Evidence limits

Native OCI writes do not use a conditional overwrite precondition: Terraform
locking coordinates cooperating clients, while another authorized writer can
bypass it. Inherited IAM must be addressed independently. An inventory/readback
check cannot eliminate concurrent-writer races. Native Terraform state reads and
SDK metadata deserialization are not a memory sandbox for hostile remote data.
Source/executable hashes do not bind every installed Python/SDK dependency or
defend against malicious same-user changes. Keep this fixture synthetic and use
the results as one part of deployment acceptance.

Relevant implementations: [Terraform OCI backend](https://developer.hashicorp.com/terraform/language/v1.16.x/backend/oci),
[pinned native client](https://github.com/hashicorp/terraform/blob/v1.16.6/internal/backend/remote-state/oci/client.go),
[Oracle versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm),
and [Object Storage SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/object_storage/client/oci.object_storage.ObjectStorageClient.html).
