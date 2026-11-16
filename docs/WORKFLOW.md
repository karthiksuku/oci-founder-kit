# One workflow from app to operations

Describe the useful app to Claude Code or Codex, work in your own application
folder, and ask it to use `oci-kit`. The agent inspects existing instructions,
source, services and saved configuration before asking for missing choices.
Local implementation can continue while OCI permissions are being prepared.
Credentials stay in local configuration; never paste keys or tokens into a prompt.

The canonical interface is Python 3.11+:

```sh
python3 .oci-founder-kit/scripts/kit.py --help
```

The project-local `.oci-founder-kit/scripts/oci-kit` launcher invokes the same
interface. No global installation or cloud-executing server is required. Add
`--json --non-interactive` after a command for structured automation. Missing
decisions produce a blocked result with a safe code, responsible party, recovery
instruction and recheck command. Neither mode guesses a production target.

## Start and select

From a reviewed kit checkout outside the app, use `scripts/kit.py start` with
the intended path, task (`build`, `migrate`, `setup`), mode (`new`, `existing`)
and agent (`claude`, `codex`, `both`). Existing applications keep their framework,
files, uncommitted work and services. Taskboard is an explicit optional blueprint,
never the default for someone else's app. See [installation](INSTALL.md).

Inspect installations and saved targets before continuing:

```sh
python3 .oci-founder-kit/scripts/kit.py environment list --project .
python3 .oci-founder-kit/scripts/kit.py next --project . --environment rehearsal
```

Here `rehearsal` means the existing target you selected. Substitute its actual
name. `status` reads without refreshing progress; `next` refreshes local
observations and returns one next action. Neither executes that action. Named
records never silently fall back to legacy progress. A legacy project with no
named targets may still use `status` or `next` without the flag; conversion backs
up private records and imports no approvals or passing checkpoints.

For a new generic OCI target, first attach the reviewed infrastructure to an
unused project-relative directory. Inspect the dry run before attachment:

```sh
python3 .oci-founder-kit/scripts/blueprint.py inspect web-container
python3 .oci-founder-kit/scripts/blueprint.py attach web-container --project . --directory deploy/rehearsal --dry-run
python3 .oci-founder-kit/scripts/blueprint.py attach web-container --project . --directory deploy/rehearsal
python3 .oci-founder-kit/scripts/kit.py environment create --project . \
  --environment rehearsal --role rehearsal --blueprint web-container \
  --infrastructure deploy/rehearsal/terraform
```

Attachment preserves application code and creates `deploy/rehearsal/terraform`.
Bind that Terraform directory, not its parent. Taskboard uses its own existing
reviewed target instead. When deliberately converting legacy progress, add
`--convert-legacy` to environment creation; the backup imports no approvals or
passing checkpoints. Target and backend files use the private schemas in
[environments](ENVIRONMENTS.md).

Create the application locally in the chosen framework and demonstrate its
primary user workflow. Use [the project brief](PROJECT-BRIEF.md) and preserve
actual checks in private evidence. An installation or empty project is not a
working app.

`next` advances through explicitly recorded checkpoints. After the meaningful
local tests pass, save their actual commands, results and limits in an owner-only
report, then use the existing checkpoint helper:

```sh
chmod 600 .oci-kit/environments/rehearsal/evidence/local-workflow.txt
python3 .oci-founder-kit/scripts/project.py record --project . --environment rehearsal \
  --step local-workflow --evidence .oci-kit/environments/rehearsal/evidence/local-workflow.txt \
  --outcome passed
python3 .oci-founder-kit/scripts/kit.py next --project . --environment rehearsal
```

The report must already contain real results; these commands do not create test
evidence. Use `--outcome blocked` when the check is blocked. Recording is an owner
assertion, not independent verification or cloud approval. Source and target
changes can make it stale. Follow the same explicit environment selection for
later checkpoints in [the progress guide](PROGRESS.md#explicit-environments-and-executable-read-checks).

## Package and prepare prerequisites

Use [packaging](../recipes/README.md) to inspect, propose and review additive Next.js
standalone, FastAPI or existing-Dockerfile changes. The private application
descriptor records commands, port, health route and external dependency names.
It carries no credentials or account references. Packaging approval covers local
files only; running a build and publishing an image remain distinct operations.

```sh
python3 .oci-founder-kit/scripts/kit.py package inspect --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py foundation inspect --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py doctor --project . --environment rehearsal
```

[Foundation](../blueprints/workload-foundation/README.md) first considers supplied approved resources, then
prepares separate compartment, network, private state and registry stacks where
needed. The handoff copies validated outputs into backed-up private target
configuration. Imported outputs are owner-supplied configuration, not proof of
live resources or permission. `doctor --live` opts into bounded metadata reads;
denied reads, inherited IAM and physical capacity remain explicit unknowns.

Use the existing API-key or temporary browser-session credential guide. Sessions
are checked for expiry and identity changes. Refreshing or changing identity
requires new affected plans. Resolve missing grants through an authorized
administrator; do not switch identities or broaden tenancy access as a shortcut.
Hostname ownership, certificate issuance/renewal and DNS changes have explicit
owners. Certificate private keys never enter the application Terraform variables.

## Review and deploy

Before initialization, prepare the selected stack's canonical native backend
declaration. Attachment includes only its example. If `backend.tf.json` already
exists, inspect it against the [state guide](../skills/oci-deploy/references/backend-state.md#supported-configuration)
instead of replacing it:

```sh
cp -n deploy/rehearsal/terraform/backend.tf.json.example deploy/rehearsal/terraform/backend.tf.json
```

The declaration contains only the empty OCI backend block. Keep its actual
destination in a separate owner-only seven-field backend JSON file. Prepare the
complete private target JSON using [the environment schema](ENVIRONMENTS.md#3-configure-the-private-target-and-run-the-doctor),
including the tested image digest and intended HTTPS origin. If foundation
handoff already supplied target fields, preserve those selections. Bind the
complete target and backend before initialization:

```sh
python3 .oci-founder-kit/scripts/kit.py environment configure --project . --environment rehearsal \
  --target-file .oci-kit/rehearsal-target.json --backend-config .oci-kit/rehearsal-backend.json
python3 .oci-founder-kit/scripts/kit.py doctor --project . --environment rehearsal --live
```

The files above must already exist with mode `0600`; configuration replaces the
target selection and backs up the old record. Recheck any stale evidence. Doctor
saves a report and returns its `evidence` path. After reviewing a current report
whose live access checks pass and whose workload has no known blocker, record
that access checkpoint with its exact returned path:

```sh
python3 .oci-founder-kit/scripts/project.py record --project . --environment rehearsal \
  --step access --evidence '<doctor-evidence-path>' --outcome passed
```

Replace the quoted placeholder with the returned path under this environment's
private evidence directory. Denied, incomplete or unknown access is not a pass;
resolve the reported blocker and rerun the doctor. Remaining capacity and IAM
unknowns still require review even when the access checkpoint is recorded.

The facade delegates to the existing deployment gate. It does not create another
approval mechanism. For native OCI state the sequence is:

1. `release init --backend-config PRIVATE_JSON`: prepare the exact offline
   backend-initialization request. Review its hash, scope, costs and expiry.
2. After owner approval, `release run --approve APPROVED_HASH`: execute that
   backend request once, preserving its private receipt.
3. `release plan --var-file PRIVATE_TFVARS_JSON`: prepare the backend planning
   request. Remote planning can write lock objects and retain versions, so review
   and approve it before another `release run`.
4. Review the resulting **resource plan** and its separate hash. Only its exact
   approval permits `release apply --approve APPROVED_RESOURCE_PLAN_HASH`.

Every command above also needs `--project . --environment rehearsal`.
Use an owner-readable `*.tfvars.json` file inside the selected infrastructure
directory and pass its basename to `--var-file`; external paths are refused by
the deployment gate. A worker uses explicit `--component worker` after its
separate role is configured. Bind and verify the worker image independently;
the same image bytes may serve both roles. Never share their compartment, runtime
identity or approval. The gate retains its strict reviewed infrastructure-source
checks. Image publication continues through
the [exact image gate](../skills/oci-deploy/references/image-publication.md).

The current default is a single application Container Instance behind a load
balancer. Updating or rolling it back can interrupt service. High availability
and zero-downtime updates are not established by this topology.

## Verify, operate and recover

```sh
python3 .oci-founder-kit/scripts/kit.py verify --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py observe --project . --environment rehearsal --live
python3 .oci-founder-kit/scripts/kit.py observe --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py support export --project . --environment rehearsal
```

`verify` makes bounded HTTPS reads; migration verification takes its reviewed
private contract. `observe --live` reads only resources identified by the latest
bound successful deployment receipt, then saves a projected private report.
`observe` without `--live` renders the network-free dashboard from saved reports.
When verification passes and the live observation establishes the exact deployed
image, record the release explicitly, using the `evidence` path returned by
`verify` for this environment:

```sh
python3 .oci-founder-kit/scripts/kit.py release record --project . --environment rehearsal \
  --evidence '<verify-evidence-path>'
python3 .oci-founder-kit/scripts/kit.py release list --project . --environment rehearsal
```

Replace the quoted placeholder with the actual private report path. A dashboard
or a health check alone does not create a release record. Keep a record after
each accepted deployment; rollback needs a previous different accepted digest.
Support export shows an allowlisted preview; `--write` saves it privately. It
never uploads. See [operating checks](OPERATIONS.md) and
[release records and rollback](RELEASE-LIFECYCLE.md).

Health and image identity are separate checks. Before real users, verify hosted
sign-in, two-user isolation, persistence, an isolated restore and actual image
rollback. Record exact targets, retained resources, cost dates and limitations.
An accepted limited runtime record never establishes all production controls.

## Hosting-first migration and the SaaS pack

Preserve the source database, authentication, storage, queues and schedules during
the hosting move. Use separate source/rehearsal/production records and the
[hosting-first guide](../skills/oci-migrate-web/references/hosting-first.md).
Compare meaningful browser flows, external-provider connectivity and latency.
Keep target workers disabled until a separately reviewed ownership transfer.
Traffic cutover and traffic rollback are separate exact operations. Data migration
follows only after hosting acceptance.

The optional [SaaS essentials pack](../blueprints/saas-essentials/README.md)
demonstrates private customer requests and attachments, durable work, reliable
webhooks and summaries. Existing apps opt into individual integrations. The pack
does not replace their code or add a billing system. Native scheduling remains
experimental until the specific Functions image, provider and IAM path passes
live acceptance; otherwise retain the existing scheduler.

See the generated [capability and platform table](CAPABILITIES.md) for dated
support. The public website and installed help use the same registry. Release
checks, restricted agent trials, ordinary agent sessions and live OCI evidence
have separate meanings and must stay separate in the report.
