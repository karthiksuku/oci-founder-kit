# Build locally, rehearse on OCI, then promote

Use this path for your own Next.js, FastAPI or container application. Keep the
app's database, storage and sign-in provider during the first hosting migration.
Data moves only after hosting acceptance, with its own reconciliation, backup,
restore and rollback tests.

The commands below run from the application directory after the normal
[project installation](INSTALL.md). Claude Code or Codex can run the local steps
and prepare the private inputs. Credential values stay in your local credential
store; none belong in a prompt, Git commit, Terraform variable or public website.

## 1. Establish the application workflow

For an existing app, initialize with `project.py start --mode existing --task
migrate` (or `--task build` when it is not a migration). Preserve the existing
framework, source, tests and uncommitted changes. For a new app, use the normal
empty-project workflow, implement a useful user flow and test it locally first.

Attach the reusable target without touching the app's source:

```sh
python3 .oci-founder-kit/scripts/blueprint.py inspect web-container
python3 .oci-founder-kit/scripts/blueprint.py attach web-container --project . --directory deploy/rehearsal --dry-run
python3 .oci-founder-kit/scripts/blueprint.py attach web-container --project . --directory deploy/rehearsal
```

The selected destination must be absent. Configure its private Terraform variable
file rather than the hidden kit snapshot. The [application contract](../blueprints/web-container/README.md)
requires a tested image, health endpoint, runtime secret adapter when needed,
and demonstrated absence or disabling of background work. It does not add
authentication or database connectivity to an arbitrary image.

## 2. Name every environment explicitly

```sh
python3 .oci-founder-kit/scripts/environments.py create --project . \
  --name rehearsal --role rehearsal --blueprint web-container \
  --infrastructure deploy/rehearsal/terraform --convert-legacy
python3 .oci-founder-kit/scripts/environments.py create --project . \
  --name source --role source --blueprint web-container
python3 .oci-founder-kit/scripts/environments.py list --project .
python3 .oci-founder-kit/scripts/project.py status --project . --environment rehearsal
```

There is no active/default environment. Production requires its own explicit
`--name production --role production`, a separate deployment directory, dedicated
compartment and backend key. Do not reuse Terraform workspaces as an isolation
shortcut: the gate deliberately uses the default workspace inside each separate
root. Inspect the actual Terraform target and backend before approval; environment
configuration does not itself enforce tenancy-wide IAM isolation.

Known rehearsal/production compartment collisions are refused. Before cloud
planning, bind distinct backend destinations. The gates compare the selected
region, namespace, bucket, state key and workspace prefix with the actual backend.
Changing profiles does not make a shared state key a separate environment.
Overlapping keys and workspace prefixes in the same bucket are refused. Distinct
keys still require an effective IAM isolation review.

Each environment has private configuration, state, evidence and generated pages
under `.oci-kit/environments/NAME/`. Its deployment root contains its separate
gate plans and receipts. The source environment retains the existing hosting and
has no OCI deployment root. No commands silently select production.

`--convert-legacy` first backs up the old progress record and evidence into
`.oci-kit/environment-backups/`. The original v0.5 record remains intact. The new
environment begins with empty checkpoints; old approvals, receipts and assertions
are not copied. The lower-level `project.py` commands without `--environment`
retain compatibility with the original record. The `oci-kit` facade requires
explicit selection whenever named environments exist. Review any `.pending-*`
directory after interruption rather
than overwriting or automatically deleting it.

## 3. Configure the private target and run the doctor

Have your agent create a mode-0600 JSON file inside ignored `.oci-kit/` containing
only the selected nonsecret target references. Use the actual values from your
existing approved foundation and image-publication receipt, not sample defaults.

| Private environment key | Meaning / deployment variable |
| --- | --- |
| `profile`, `auth` | Local OCI profile and `api_key` or `security_token`; no token values |
| `region`, `compartment_id` | Intended region and dedicated application compartment |
| `vcn_id`, `app_subnet_id`, `lb_subnet_id` | Existing VCN, private application subnet and public load-balancer subnet |
| `app_private_ip` | Selected available private IPv4 address in the application subnet |
| `certificate_id`, `registry_id` | Existing certificate and private repository metadata references |
| `availability_domain`, `ocpus`, `memory_gbs` | Intended E4 Container Instance placement and size |
| `image_digest`, `image_architecture` | Receipt's `sha256:…` digest and `AMD64`; selection still needs image-manifest verification |
| `port`, `health_path` | Actual app listener and non-sensitive health route |
| `origin` | Exact lowercase HTTPS origin, without credentials, path, query or fragment |

The environment file is a readiness/evidence selection. Match these references
to the actual variable names in the attached target before preparing its plan.
The image reference in Terraform also needs its registry/repository name and
digest. Do not pass the environment JSON directly to Terraform.

```sh
python3 .oci-founder-kit/scripts/environments.py configure --project . \
  --name rehearsal --target-file .oci-kit/rehearsal-target.json
python3 .oci-founder-kit/scripts/project.py doctor --project . --environment rehearsal
python3 .oci-founder-kit/scripts/project.py doctor --project . --environment rehearsal --live
```

The first command is local. `--live` performs only bounded metadata reads:
region subscription, compartment, selected network/certificate/repository and
E4 quota availability. It does not request certificate bundles or private keys.
Denied reads and unavailable quota APIs stay unknown, with a narrow administrator
handoff. Authentication, readable metadata, quota allowance, provisioning IAM and
physical capacity are distinct. Network egress, callback behavior, hostname
coverage, runtime Vault access and actual capacity require further evidence.

The native backend and deployment gates accept SecurityToken authentication.
Local expiry, rotation and signer tests passed; live session-backed deployment
remains unverified.
Read [temporary credentials](../skills/oci-ready/references/credentials.md) and
[backend state](../skills/oci-deploy/references/backend-state.md). Local checks
require at least ten minutes left in the session; OCI verifies token authenticity
when it receives a request. A refreshed token invalidates pending plans, requiring
a new exact plan and approval. The native backend selects the profile in
`~/.oci/config`; an alternate doctor config does not establish backend readiness.

The doctor saves a private environment-bound report and returns its safe relative
evidence path. For the `access` checkpoint, record that report with the same
`--environment`; an access pass requires passed nested live access checks and no
known workload blocker. It does not resolve the report's remaining unknowns. Changing the target,
application or executed helpers makes evidence stale; timed machine reports also
expire after 24 hours. Recheck before relying on them.

## 4. Deploy and verify the selected workload

Prepare the private seven-field native backend JSON described in the state guide.
Attachment supplies `backend.tf.json.example`; the gate requires the actual
canonical declaration. When that destination is absent, copy it without adding
inline backend settings:

```sh
cp -n deploy/rehearsal/terraform/backend.tf.json.example deploy/rehearsal/terraform/backend.tf.json
```

If the destination already exists, inspect it against the state guide instead of
replacing it. Bind the complete private target and backend to this environment
before initialization or resource planning. Preserve fields supplied by a prior
foundation handoff; `configure` replaces the target selection:

```sh
python3 .oci-founder-kit/scripts/environments.py configure --project . \
  --name rehearsal --target-file .oci-kit/rehearsal-target.json \
  --backend-config .oci-kit/rehearsal-backend.json
```

Only the five nonsecret destination fields are copied into private environment
configuration; the full backend file remains separate. The selected target must
include region, compartment, profile and authentication before a cloud operation.
The target's chosen image digest is compared with the actual resource plan.
For named stacks, prepare native backend operations with explicit project and
environment selection:

```sh
python3 .oci-founder-kit/skills/oci-deploy/scripts/deploy_gate.py backend-plan \
  --dir deploy/rehearsal/terraform --project . --environment rehearsal \
  --operation init --backend-config .oci-kit/rehearsal-backend.json
```

This creates an offline review packet, not a backend write. `backend-run` needs
approval of that packet's exact hash and rechecks the saved environment binding.
Resource planning similarly uses `backend-plan --operation plan --project .
--environment rehearsal` after initialization; the resulting apply needs its own
approval. Missing or changed bindings, another environment's destination, an old
unbound plan and target-variable mismatches stop the gate. Source environments
cannot select OCI backends or execute these deployment operations.

Named web deployment gates support the reviewed, unmodified Terraform sources of
`web-container` and `fullstack-container`. The optional
[SaaS worker](../blueprints/saas-essentials/README.md) has its own explicitly bound
component, infrastructure root, image, compartment and backend; use
`oci-kit release ... --component worker` for its operations. Native Function role
activation remains blocked pending its separate acceptance. Private variable
files and the canonical native backend are configurable. Additional or modified infrastructure code needs
separate reviewed support; an environment label alone cannot prove its target.
The gate checks the evaluated workload compartment and image as well as the
selected configuration. Shared registry, Vault and home-region IAM scopes still
need explicit review in the exact resource plan.

Create or reuse the approved foundation and state bucket separately, outside the
application project's named deployment roots. The named application gate is not
a foundation or backend-bucket bootstrap command. Every infrastructure directory
inside a project with named environments must match an explicitly selected
environment; copying a stack into another subdirectory does not bypass that rule.

Use the existing [image](../skills/oci-deploy/references/image-publication.md),
[backend](../skills/oci-deploy/references/backend-state.md) and
[deployment](../skills/oci-deploy/SKILL.md) gates. Review the exact resource plan,
permissions, dated cost, partial-failure recovery and cleanup before approval.
No project, environment or doctor command approves or executes a cloud write.

After deployment:

```sh
python3 .oci-founder-kit/scripts/project.py verify --project . --environment rehearsal --kind runtime
```

For `web-container`, this checks the selected HTTPS health route. For Taskboard,
it runs the existing four anonymous HTTPS checks. Both save current bound reports.
Neither proves hosted sign-in, two-user authorization, persistence, deployed-image
identity, restore or rollback. Run the application's browser/API tests and retain
their actual results. Taskboard's separate `production_check.py --exercise` uses
two private test sessions and explicitly scoped synthetic writes; review its
retained-object limitations before using it.

For hosting-first migration, create a private reviewed
[HTTP compatibility contract](../skills/oci-migrate-web/references/hosting-first.md).
Bind `source.revision_sha256` to `current_source_sha256` from the environment's
current project status, and bind the target origin/digest to its private selection.
Then run:

```sh
python3 .oci-founder-kit/scripts/project.py verify --project . --environment rehearsal \
  --kind migration --contract .oci-kit/hosting-contract.json
```

Optional session files must be owner-only and **outside every Git tree**. They
bind each test user's existing cookie to its exact origin and are never sent to
the other origin. HTTPS validation stays enabled. Reports contain projections and
hashes, never cookies or response bodies. Redirects are compared without following.
This HTTP runner does not execute browser JavaScript or upload files; retain
separate browser and upload tests for the app's real workflows.

Promote the exact tested image digest into a separately reviewed production plan.
Rehearse image rollback and return of traffic to the source independently. Keep
the target's schedulers and workers disabled using tested application controls
until a reviewed ownership transfer. Traffic cutover, rollback, data migration
and source decommissioning are distinct operations; prior approvals do not carry.

## 5. Read the private operating view

```sh
python3 .oci-founder-kit/scripts/project.py dashboard --project . --environment rehearsal
```

Open the returned local HTML path. The dashboard has no server, JavaScript,
external assets, telemetry or polling. It shows the selected digest, observed
deployment receipt, current health/readiness/parity checks, failed checks,
recovery evidence and stale reports. It explicitly distinguishes the selected
image from independently verified deployed-image identity. Keep the HTML private.

Costs remain unknown until current private pricing/usage evidence is supplied.
An optional `oci-operating-costs/1` evidence JSON carries the same environment,
target/source/helper hashes and `observed_at`, plus:

- `estimated_monthly_usd`, `observed_period_usd`, `overlap_monthly_usd`: nonnegative
  totals or `null`, derived from dated evidence rather than copied unit prices.
- `period_start_utc`, `period_end_utc`, `pricing_observed_at_utc`: UTC timestamps
  formatted `YYYY-MM-DDTHH:MM:SSZ`, with an elapsed observed billing period.
- `pricing_evidence_sha256`, `usage_evidence_sha256`: the private evidence hashes;
  `retained_resources_count`: the reconciled inventory count.

Use the existing price lookup for dated Oracle list prices and actual billing
records for observed usage. Include retained source services, overlap, backups,
registry images, object versions, state and network resources. These inputs are
owner-recorded, not automatically fetched or authenticated by this view. Budget
alerts and estimates are not spending caps. Missing data is never shown as zero.

Public source references reviewed on 16 November 2026:
[Container Instances quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_topic-container-instances.htm),
[availability API](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html),
[certificate metadata](https://docs.oracle.com/en-us/iaas/Content/certificates/viewing-certificate-details.htm).
Source review is separate from a successful live deployment.
