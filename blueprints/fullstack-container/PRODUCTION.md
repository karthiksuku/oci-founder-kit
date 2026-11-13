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

1. For default load-balancer ingress, a domain and an OCI Certificates certificate
   valid for it in that region. Review the [certificate access requirements](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingcertificates.htm).
   DNS changes are a separate approved operation after the load balancer IP exists.
   The [optional API Gateway rehearsal](#optional-api-gateway-rehearsal) obtains
   an OCI-managed hostname/certificate through a separate bootstrap plan.
2. An OIDC confidential web client at the chosen provider, with authorization-code
   flow, PKCE, `client_secret_post` token authentication and an exact callback of
   `https://<actual-app-hostname>/auth/callback`. For the gateway, register this
   only after its actual hostname exists. All discovery, authorization, token
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
   limited to the reviewed deployment operators. Review inherited tenancy and
   ancestor-compartment grants as well as bucket-specific policies; private
   access does not establish least privilege. Keep it separate from app uploads
   and teardown. Follow the [state operations and IAM review](../../skills/oci-deploy/references/backend-state.md).

The app policy grants its resource principal read access to only the three named
secret bundles. The deploying identity still needs reviewed permissions to create
the listed resources and policies. Do not grant tenancy-wide management to fix an
access failure. Load-balancer certificate, identity client, secret creation and
state-bucket creation are not silently performed by this stack.

## Configure identity discovery

`production.oidc_issuer` is the expected token issuer. Normally the app discovers
metadata from that issuer. Some providers, including OCI IAM identity domains,
serve a domain-specific discovery document whose issuer identifier differs from
its host. [Oracle discovery API](https://docs.oracle.com/en/cloud/paas/iam-domains-rest-api/op-well-known-openid-configuration-get.html).

For that case, also set `production.oidc_discovery_url` to the reviewed domain's
exact HTTPS `/.well-known/openid-configuration` URL. Keep `oidc_issuer` equal to
the issuer in that document. The app refuses a discovered issuer that differs
from the configured value; ID-token signature, issuer, audience, state and nonce
checks remain enabled. This adds an explicit issuer check to the pinned client's
[direct-document discovery option](https://github.com/panva/openid-client/blob/v6.8.9/docs/functions/discovery.md).

For OCI IAM, the corresponding runtime settings are:

```text
OIDC_ISSUER=https://identity.oraclecloud.com/
OIDC_DISCOVERY_URL=https://<identity-domain-host>/.well-known/openid-configuration
```

Verify the selected document's issuer and authorization, token and signing-key
endpoints against the intended identity domain. Discovery locations come from
operator configuration, never request parameters. Other providers can leave the
optional discovery URL unset and retain their normal issuer discovery.

## Approve state initialization before planning

Use Terraform 1.16.6, the version used for this reference's local checks. From
this blueprint directory, inspect and copy the examples:

```sh
umask 077
cp terraform/backend.tf.json.example terraform/backend.tf.json
cp terraform/backend.tfbackend.json.example terraform/backend.tfbackend.json
cp terraform/terraform.tfvars.example terraform/production-common.tfvars
cp terraform/production.tfvars.example terraform/production.tfvars
chmod 600 terraform/backend.tfbackend.json terraform/production-common.tfvars terraform/production.tfvars
```

Keep the empty `backend.tf.json` declaration unchanged. Fill the ignored private
backend JSON and both variable files locally. Replace every backend placeholder,
including the fictional region. The backend JSON has exactly seven fields:
`bucket`, `namespace`, `region`, `key`, `workspace_key_prefix`, `auth` and
`config_file_profile`. This gated path requires `auth = "APIKey"`, an existing
private profile and the default workspace. It does not yet accept principal or
security-token authentication for the backend.

The common variable file supplies tenancy, compartment, region, home region,
provider authentication and ingress settings. The production file supplies the
immutable image and hardened options and is loaded last. Review both provider
and backend identity choices; do not infer that they are the same. Never put
private keys or tokens in backend JSON. Review the
[supported environment and file restrictions](../../skills/oci-deploy/references/backend-state.md#supported-configuration),
then prepare initialization offline:

```sh
python3 ../../skills/oci-deploy/scripts/deploy_gate.py backend-plan \
  --dir terraform --operation init --backend-config terraform/backend.tfbackend.json
```

This prepares a private destination/input-hash packet without invoking Terraform
or OCI. Have the owner review and approve its exact hash, then run:

```sh
python3 ../../skills/oci-deploy/scripts/deploy_gate.py backend-run \
  --dir terraform --approve <backend-init-sha256>
```

The approved operation initializes the backend and may install reviewed modules
and providers. It does not approve resource planning or deployment. Existing
local state/workspace history and changes to a different backend are refused;
state migration has no gated implementation yet. Backend metadata, state, plans
and receipts can contain sensitive data and stay outside Git. Independently
verify effective IAM, versioning and recovery before using credential-bearing
state. Live backend lock contention and restore acceptance remain pending.

## Build, review and deploy

Run app tests and build the image. Use the
[image publication gate](../../skills/oci-deploy/references/image-publication.md)
to prepare a private layout and approve an exact digest upload to the private
registry, without assigning a remote tag. Keep its original creation receipt;
`immutable_tags = false` is compatible with digest publication. Live OCI digest
publication remains unverified until the actual attempt passes its checks. Pin `app_image`
to the verified receipt's immutable `@sha256:` digest; production rejects mutable
tags. For default load-balancer ingress, fill `production.tfvars` with the
certificate, public origin, OIDC client identifier and secret references, never
their values. For the gateway, complete the staged procedure below first.

```sh
python3 ../../skills/oci-deploy/scripts/deploy_gate.py backend-plan \
  --dir terraform --operation plan --var-file production-common.tfvars \
  --var-file production.tfvars
```

This is offline preparation for planning, not the resource plan itself. Obtain
owner approval of its backend-operation hash, then:

```sh
python3 ../../skills/oci-deploy/scripts/deploy_gate.py backend-run \
  --dir terraform --approve <backend-plan-sha256>
```

Planning can create/delete lock objects and retain version history. Review its
resulting saved resource plan, scoped IAM statements, DNS/certificate dependencies
and dated cost estimate. Obtain **separate approval of the resource-plan hash**
before invoking `apply --dir terraform --approve <resource-plan-sha256>`. The gate
rechecks the bound backend and source. Do not use direct remote Terraform
initialization/planning or plain gate `plan` as a shortcut.

The selected hardened entry point accepts only HTTPS from the chosen CIDRs;
port 80 is closed. TLS terminates there. The private app connection uses HTTP on
port 8080 restricted to that entry point's NSG; workloads requiring encrypted internal transport must
add and verify it. Database TLS verifies the service CA. Outbound production
traffic permits DNS, the database port and HTTPS; HTTPS egress is not a domain
allowlist. Narrow it further if your policy requires that control.

## Optional API Gateway rehearsal

The default remains `ingress_mode = "load_balancer"`. For a restricted rehearsal
in the commercial OC1 realm, `ingress_mode = "api_gateway"` uses OCI's generated
HTTPS hostname and default certificate. This avoids a custom DNS/certificate
prerequisite for the rehearsal. Oracle recommends default certificates for
private or nonproduction systems; use a reviewed custom-certificate design for
public production use. See [Oracle's certificate guidance](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaysettingupcustomdomainscerts.htm).

This option changes only ingress. The app still runs in `APP_MODE=production`
with server-side OIDC, PostgreSQL sessions, ownership checks, CSRF, Vault retrieval
and verified database TLS. It does not enable the unauthenticated sandbox app.
The generated hostname flow is locally schema/mock tested; live OCI gateway,
OIDC, cookie and attachment behavior remains unverified.

1. Complete the separately approved OCI backend initialization and configure
   common variables above. Choose the
   actual tester/browser IPv4 `/32` addresses for `allowed_ingress_cidrs`; do not
   assume the coding agent's egress address is the browser's. The dedicated
   regional gateway subnet must have at least 32 free addresses; the default
   VCN produces a `/24` gateway subnet.
2. Create an ignored `terraform/gateway-bootstrap.tfvars` with only:

   ```hcl
   ingress_mode = "api_gateway"
   production   = null
   ```

   Prepare the exceptional gateway planning operation offline from this
   blueprint directory:

   ```sh
   python3 ../../skills/oci-deploy/scripts/deploy_gate.py backend-plan \
     --dir terraform --operation plan --var-file production-common.tfvars \
     --var-file gateway-bootstrap.tfvars \
     --target 'oci_apigateway_gateway.web[0]'
   ```

   Keep `gateway-bootstrap.tfvars` private (`0600`). Obtain approval of the
   backend-operation hash and invoke `backend-run --dir terraform --approve
   <backend-plan-sha256>` to generate the resource plan. A target includes
   dependencies. Review every actual change: the intended
   fresh-stack bootstrap contains the gateway, VCN, internet gateway, public
   route table, empty security list, gateway subnet, gateway/app NSGs and three
   restrictive rules. It must not create the app, database, API deployment,
   IAM policies, bucket or secrets. Obtain separate approval of that exact
   resource-plan hash before
   the matching gate apply. Existing stacks can have different changes; do not
   treat this list as approval or switch a running ingress without review.
3. Read only `api_gateway_hostname` from the resulting Terraform outputs. Verify
   the hostname and certificate, then register the confidential client's callback
   as `https://<actual-gateway-hostname>/auth/callback` through the separately
   approved identity workflow. Keep inherited sign-on/MFA controls and restrict
   client membership. Prepare the three Vault secrets privately.
4. Complete `production.tfvars`: set top-level `ingress_mode = "api_gateway"`,
   fill the OIDC and secret reference fields, and **omit** `public_origin` and
   `certificate_ocid` from `production`. Terraform derives PUBLIC_ORIGIN from
   the actual gateway. Use `oidc_discovery_url` only as described above. Do not
   pass `gateway-bootstrap.tfvars` to the full plan.
5. Prepare the **full**, untargeted planning operation from the preceding
   section, obtain its backend-operation approval, and run it through
   `backend-run`. The resulting resource plan creates the authenticated app and
   its root API deployment only after complete production inputs are present.
   Obtain a separate resource-plan approval, apply through the gate, and perform
   the acceptance checks below.

The root route forwards nested paths and callback queries to the fixed private
app. It overwrites `X-Forwarded-Proto` to `https`; the app trusts only the dedicated
gateway subnet. No response caching, query rewriting or callback logging is
configured. Production uploads and downloads stay behind the authenticated app;
this flow creates no public pre-authenticated object URLs.

The gateway option does not create the load-balancer alarm. Prepare reviewed
availability/health checks without logging callback codes, session cookies or
tokens. Test the workload against [API Gateway limits](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Reference/apigatewaylimits.htm)
and timeouts, including the app's 10 MiB upload limit. Replacing the gateway can
change its hostname and therefore requires a new exact callback registration.

## Validate the running application

Use synthetic data and two independently signed-in test users. Record each result
in the [progress record](../../docs/PROGRESS.md), keeping raw account details private.

- Verify the hostname, certificate chain, HTTPS-only entry point and `/readyz`.
- For the gateway, verify `/`, nested assets, callback query parameters, redirects
  and Secure/HttpOnly/SameSite cookies. Spoofed forwarded-protocol headers must
  not weaken HTTPS behavior; unapproved client IPs and direct backend access
  must fail. Verify binary upload/download hashes and oversize rejection.
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

Prepare cleanup through `backend-plan --operation destroy-plan`, obtain approval
and run it through `backend-run`, then review and approve its separate resource
destroy plan before `destroy`. Inventory retained versions/backups and shared
resources before deletion. The kit has no gated state-version deletion operation.
The separate registry, previous image digests, state bucket, identity resources
and Vault secrets remain until their individual retention/cleanup plans are
approved; destroying the app stack does not establish that they were removed.
An empty resource-search result is **unknown**, not evidence that cleanup finished.
Publish only a redacted result summary, with unverified items left explicit.
