# Your app on OCI

Deploy an existing Next.js, FastAPI or ordinary Docker web service while keeping
its application source, database, object storage and sign-in provider. This
blueprint supplies an OCI HTTPS deployment target. It does not supply an app,
a database, authentication code or an automatic migration.

## Attach it to your application

From a reviewed kit checkout or installed `.oci-founder-kit/` bundle:

```sh
python3 scripts/blueprint.py inspect web-container
python3 scripts/blueprint.py attach web-container --project /path/to/app --directory deploy/rehearsal --dry-run
python3 scripts/blueprint.py attach web-container --project /path/to/app --directory deploy/rehearsal
```

Use the installed helper's actual path when running from your app. The selected
directory must not exist. Its parent directories may be created. Attachment
copies reviewed infrastructure and this guide, preserves existing files, and
does not install skills, run your app or contact OCI. A failed copy leaves its
partial directory for review; do not delete app files to retry. Existing v1
`fullstack-container` creation remains the independent Taskboard starter.

Your deployment target is now `deploy/rehearsal/terraform/`. Configure its private
variable file and keep application edits in your original source tree. Named
environment gates require the reviewed Terraform source files; infrastructure
code customizations need separate reviewed support. Follow the
[environment guide](../../docs/ENVIRONMENTS.md) from the kit checkout or installed
bundle. The copied `.gitignore` protects local target inputs,
state, plans, credentials and receipts within this deployment directory. Keep
private evidence elsewhere under the project's ignored `.oci-kit/` directory.

## What the target creates

One private Container Instance (`CI.Standard.E4.Flex`, Linux amd64), one public
flexible load balancer with an HTTPS-only listener, and two NSGs with explicit
rules. It reuses the selected VCN, public subnet, private subnet, certificate and
private image repository. It does not modify DNS, replace subnets, create a
database, change the identity provider, or transfer background processing.

Rehearsal and production need distinct compartment/state/configuration selections.
The compartment must be dedicated to this environment. `manage_runtime_iam`
defaults to false so an administrator can supply existing reviewed IAM. Enabling
it includes a compartment-based Container Instances dynamic group, read-only
pull access to the named repository, and read-only access to each selected Vault
secret in the saved plan. All Container Instances in that compartment match the
group. Check inherited policies too; these definitions cannot prove IAM isolation.
IAM changes run against the tenancy home region and can take time to propagate.

Existing networking is a prerequisite. Have the network owner verify the public
subnet's Internet Gateway path, the private subnet's NAT/service routes, DNS,
security lists, and available private address. Subnet security lists and NSGs
are additive: permissive inherited rules can defeat a restrictive NSG. The kit's
compartment foundation alone does not create this network. The Terraform target
checks subnet/VCN consistency and private-IP membership; those checks do not
establish routing, capacity or the absence of broader access.

## Adapt and test your image

1. Build for Linux amd64. Pin and promote the same tested OCIR digest; tags are
   refused. Keep `.env`, keys and build credentials out of build context/layers.
2. Listen on `0.0.0.0` and the configured `app_port` (default 8080). Implement a
   non-sensitive unauthenticated health route returning 200 at `health_path`.
3. Make local storage disposable. Keep uploads and durable state in the existing
   external services and test restart persistence. This single-instance target
   provides no high-availability or zero-downtime rollout guarantee.
4. Keep the existing authentication provider. Configure the rehearsal HTTPS
   callback separately and test sign-in, sign-out, cookie attributes, CSRF,
   ownership checks with two users, and the trusted proxy configuration in your
   app. The load balancer does not add authentication. TLS terminates there;
   app traffic travels over HTTP within the private VCN. Use a separately reviewed
   design when end-to-end backend TLS is required.
5. For Next.js, choose a supported self-hosting output, preserve public build-time
   settings, and test streaming, redirects, cache behavior, image optimization
   and uploads. Multiple replicas require a separate cache/session design.
   FastAPI and other containers must preserve forwarded-header trust and their
   own worker/concurrency semantics.
6. Keep schedulers, consumers and background workers owned by the source. Verify
   the target image has none, or disable them using controls the application
   actually implements. `RUN_WORKERS=false` is only an example; this kit cannot
   make an arbitrary image honor it. No default injected flag pretends to do so.

Record private evidence tied to the exact image digest. Set
`application_contract.evidence_sha256` to that report's SHA-256 and choose
`background_work = "absent"` or `"disabled"`. Disabled mode also requires the
real tested `background_control_environment`. Unreviewed defaults refuse a plan.
This declaration records an owner-reviewed claim; it does not independently
verify that evidence or authorize deployment. Worker activation is deliberately
outside this target and needs a later ownership-transfer plan.

## Keep secrets out of Terraform

`public_environment` contains **nonsecret** application settings. These values
are visible in Terraform state and OCI metadata. Never put connection strings,
passwords, tokens, private keys or credential-bearing URLs there. Obvious secret
names are rejected, but that is not a secret scanner or a guarantee. Review every
value and protect state even when all values are nonsecret identifiers.

`secret_references` maps app-specific names such as `DATABASE_SECRET_OCID` to
existing OCI Vault secret identifiers. The app must use an OCI SDK resource
principal signer to retrieve and decode secret bundles at runtime, retain values
only in memory, and avoid logging them. No Terraform secret-bundle data source,
plaintext environment injection or private registry credential is used here.
There is no universal adapter: an unchanged app expecting `DATABASE_URL` will
not automatically understand `DATABASE_SECRET_OCID`. Implement and test that
small adapter in the app before marking `vault_references_implemented = true`.
Use least-privilege external database/service credentials in those secrets.

Retain external services initially. Test TLS certificate validation, callback
allowlists, DNS and cross-cloud latency from OCI. `dependency_egress` permits
selected extra CIDRs/ports, for example retained database endpoints on 5432.
HTTPS egress is permitted on 443; NSGs do not restrict hostnames or enforce TLS.
External provider IP changes need review. Do not disable TLS validation to get
connectivity working.

## Review and deploy

Prepare ignored target variables from `terraform/terraform.tfvars.example` and
prepare private backend configuration using the installed state guide. The sample
identifiers are fictional and the unreviewed application contract intentionally
fails. Reuse the existing registry and image-publication gates; never place a
registry auth token in this target. Confirm exact repository, digest, architecture
and pull IAM before deploying.

Local provider checks need initialized pinned providers and no cloud credentials:

```sh
terraform -chdir=deploy/rehearsal/terraform init -backend=false -lockfile=readonly
terraform -chdir=deploy/rehearsal/terraform validate
terraform -chdir=deploy/rehearsal/terraform test
```

The included tests use mocked providers and do not establish OCI runtime success.
Before remote-state operations, use the installed
[workflow guide](../../docs/WORKFLOW.md#review-and-deploy): create the named
environment bound to `deploy/rehearsal/terraform`, copy its canonical backend
declaration, and bind its complete private target and seven-field backend file.
Then, from the application root, prepare the offline initialization request:

```sh
python3 .oci-founder-kit/scripts/kit.py release init --project . --environment rehearsal \
  --backend-config .oci-kit/rehearsal-backend.json
```

Substitute the selected environment and its actual private paths. Review the
returned initialization packet before requesting approval and `release run`.
After initialization, `release plan` prepares a separate remote planning request;
its approved `release run` produces the resource plan, which needs its own exact
approval for `release apply`. Follow each handoff in the workflow guide. A direct
`deploy_gate.py plan` command does not authorize native backend operations.

Before any apply, review the exact target, changes, permissions, dated estimate,
retained resources and rollback approach. Approve that exact plan through the
gate. Quotas and service limits do not establish current capacity. Estimate CI,
load balancer, existing network/registry/state costs, egress and source/OCI overlap
using the kit's current price lookup; budget alerts are not spending caps.

After an approved deployment, verify the live instance digest and target, HTTPS
certificate, dependency connectivity, browser workflows, two-user isolation and
persistence. Test restore into an isolated target. Rehearse both image rollback
and return of traffic to the source before cutover. A rollback may replace the
container and interrupt service; keep the source available and approve its exact
plan. Change traffic only through a separate reviewed operation, and transfer
one scheduler/worker owner at a time. Hosting acceptance precedes data migration.
Record retained OCI and source resources, observed costs and approved cleanup.

## Public references

Implementation reuses this kit's UPL-1.0 container, networking and deployment
gate patterns. These public documentation references were reviewed on 2026-11-16;
reviewing them is separate from independently verifying a live deployment:

- [OCI Container Instances policies](https://docs.oracle.com/en-us/iaas/Content/container-instances/permissions/policy-reference.htm)
- [OCI Container Instances shapes](https://docs.oracle.com/en-us/iaas/Content/container-instances/container-instance-shapes.htm)
- [OCI Container Instances overview](https://docs.oracle.com/en-us/iaas/Content/container-instances/overview-of-container-instances.htm)
- [Next.js self-hosting](https://nextjs.org/docs/app/guides/self-hosting)
- [OCI limits and quotas](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm)
