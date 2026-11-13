# Hardened deployment reference

This opt-in configuration adds HTTPS, server-side OIDC sign-in, per-user task
and attachment access, Vault secret retrieval, PostgreSQL sessions, daily database
backups and bucket versioning. It is a preview reference: local tests and mocked
Terraform checks do not prove an OCI deployment, recovery or production readiness.
Complete the [operations acceptance](../../docs/OPERATIONS.md) for your workload.

## Prepare privately

Use a dedicated workload compartment and the approved foundation workflow.
Choose the region, capacity, ingress ranges, cost limit, identity provider and
recovery goals with the owner. The reference runs one container and one database
instance; it does not provide horizontal scaling or an availability SLA.

Before planning, an authorized administrator prepares or selects:

1. A domain and an OCI Certificates certificate valid for it in the load balancer
   region. Review the [certificate access requirements](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingcertificates.htm).
   DNS changes are a separate approved operation after the load balancer IP exists.
2. An OIDC confidential web client at the chosen provider, with authorization-code
   flow, PKCE, `client_secret_post` token authentication and an exact callback of
   `https://app.example.com/auth/callback`. All discovery, authorization, token
   and signing-key endpoints must support HTTPS and be reachable from the app
   or browser as appropriate. Other client authentication methods need an
   explicitly implemented and tested adapter.
   Limit application membership at the provider. The reference accepts identities
   admitted by that client; it does not implement invitations or tenant administration.
3. Three distinct OCI Vault secrets in the workload region: database password,
   OIDC client secret and a
   cryptographically random session-signing value of at least 32 characters.
   Create values through an approved private mechanism, never chat, shell history,
   Terraform variables or Git. Select a specific database secret version; the app
   and database must use the same version. Review the
   [PostgreSQL service permissions](https://docs.oracle.com/en-us/iaas/Content/postgresql/policies.htm).
4. A private, versioned Object Storage bucket for Terraform state with access
   limited to deployment operators. Keep it separate from app uploads and teardown.
   Review the backend's [authentication and locking](https://developer.hashicorp.com/terraform/language/backend/oci).

The app policy grants its resource principal read access to only the three named
secret bundles. The deploying identity still needs reviewed permissions to create
the listed resources and policies. Do not grant tenancy-wide management to fix an
access failure. Certificate, identity client, secret creation and state-bucket
creation are not silently performed by this stack.

## Configure state before the first plan

Use Terraform 1.16.6, the version used for this reference's local checks. From
this blueprint directory, inspect and copy the examples:

```sh
cp terraform/backend.tf.example terraform/backend.tf
cp terraform/backend.tfbackend.example terraform/backend.tfbackend
cp terraform/terraform.tfvars.example terraform/production-common.tfvars
cp terraform/production.tfvars.example terraform/production.tfvars
```

Fill the ignored backend and both variable files locally; all example identifiers
are placeholders. The common file supplies tenancy, compartment, region, home
region, authentication and ingress settings. The production file supplies the
immutable image and hardened options and is loaded last. Authenticate using a
supported private OCI profile or principal.
Do not put private keys or tokens into backend configuration. Then initialize:

```sh
terraform -chdir=terraform init -backend-config=backend.tfbackend
```

This command configures the selected remote backend. If state already exists,
stop and review a backup and state migration procedure with the owner before
continuing. Do not use unattended `-migrate-state`, `-force-copy` or force-unlock.
Backend metadata, state, plans and receipts can contain sensitive data and stay
outside Git. Independently verify bucket privacy, versioning, IAM and recovery;
the deploy gate only checks the initialized backend type.

## Build, review and deploy

Run app tests and build the image. Use the
[image publication gate](../../skills/oci-deploy/references/image-publication.md)
to review and approve upload to a private, immutable-tag registry. Pin `app_image`
to the verified receipt's immutable `@sha256:` digest; production rejects mutable
tags. Fill `production.tfvars` with the certificate, public origin,
OIDC client identifier and secret references, never their values.

```sh
python3 ../../skills/oci-deploy/scripts/deploy_gate.py plan \
  --dir terraform --var-file production-common.tfvars \
  --var-file production.tfvars --require-backend oci
```

Review the exact plan, scoped IAM statements, DNS/certificate dependencies and
dated cost estimate. Obtain approval of its hash before invoking the matching
gate apply command. The required backend is checked again before apply.

The load balancer accepts only HTTPS from the chosen CIDRs; port 80 is closed.
TLS terminates there. The private app connection uses HTTP on port 8080 restricted
to the load balancer NSG; workloads requiring encrypted internal transport must
add and verify it. Database TLS verifies the service CA. Outbound production
traffic permits DNS, the database port and HTTPS; HTTPS egress is not a domain
allowlist. Narrow it further if your policy requires that control.

## Validate the running application

Use synthetic data and two independently signed-in test users. Record each result
in the [progress record](../../docs/PROGRESS.md), keeping raw account details private.

- Verify the hostname, certificate chain, HTTPS-only entry point and `/readyz`.
- A signed-out request to task or attachment APIs must return 401.
- User A creates a task and file; user B cannot list, modify, delete or download
  them, even with a copied identifier. Production downloads proxy through the
  authenticated app; it does not issue public pre-authenticated object URLs.
- Invalid sign-in responses, reused callbacks and missing CSRF proofs are rejected.
  Cookies are Secure/HttpOnly; sessions expire after 30 minutes idle or 8 hours
  absolute. Logout invalidates the local app session; provider-wide logout is separate.
- Restart the app. Tasks/files persist and the session store remains usable.
  Deny one required dependency in an isolated rehearsal and verify useful failure
  behavior without revealing connection strings, tokens or secret values.

Existing sandbox rows remain owned by the sandbox identity. The kit never assigns
old rows to a new signed-in user automatically. Review and rehearse any ownership
mapping or data migration separately. Deleting a task removes its database
references; retained bucket objects/versions require a separate approved retention
and deletion procedure, especially where user erasure is required.

## Recovery and rollback evidence

The configured database policy requests a daily 03:00 UTC backup retained for
seven days; bucket versioning retains earlier objects. Neither setting proves
restorability or replaces a retention/cost policy. Follow the service's current
[backup and restore documentation](https://docs.oracle.com/en-us/iaas/Content/postgresql/backups.htm).

Rehearse with nonproduction records and files. Record a baseline manifest of
counts and file hashes, obtain approval for an isolated restore target, restore
the chosen backup and required object versions, then connect a temporary app
using its own reviewed configuration. Recheck two-user authorization, primary
workflow, counts and hashes. Record recovery duration and newest recovered data.
Do not overwrite the original database to test recovery.

For application rollback, retain the previous image digest and review database
compatibility. Prepare a new gate plan selecting that digest, obtain approval,
apply and rerun the primary workflow. Reverting an image does not undo database
writes. Secret rotation, ownership mapping and destructive schema changes need
their own rehearsed procedure.

Plan cleanup of rehearsal resources through the same gate with `--require-backend
oci`. Inventory retained versions/backups and shared resources before deletion.
An empty resource-search result is **unknown**, not evidence that cleanup finished.
Publish only a redacted result summary, with unverified items left explicit.
