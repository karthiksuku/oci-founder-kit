# Start here: let your agent build or migrate

Choose **New project**, **Existing project** or **Continue** in the
[founder guide](https://karthiksuku.github.io/oci-founder-kit/#start). Copy its prompt
into Claude Code or Codex in your intended app folder. The guide shows the first
expected result and relevant prerequisites; it does not inspect your machine or
mark work complete. The [installation guide](INSTALL.md) provides matching terminal
commands. Your coding-tool account and OCI account are separate.

## New application

```text
Use oci-kit. Build a small app for my team to track customer requests.
Inspect this repository first. Implement a useful local version with tests,
help me authenticate to OCI, prepare a dedicated compartment and scoped IAM,
and review the design against OCI's Well-Architected Framework.
Show the exact deployment plan and recurring cost before making cloud changes.
```

For a fresh app, `project.py start --mode new --task build` creates an empty
project, local skills and a private checklist. `--stack nextjs` or `--stack fastapi`
records the requested stack; your agent still implements it. Taskboard requires
the explicit `--blueprint fullstack-container` choice. For an existing app, use
`--mode existing` so the helper preserves its code and reuses an installed kit.
Use the full path/agent arguments from the installation guide.

The agent starts local development while you complete any account enrollment or
administrator steps. It chooses a maintainable architecture based on the workload,
not Kubernetes by default. Expect a working local project, readiness results,
a deployment plan and explicit unfinished acceptance checks.

Start with a short [project brief](PROJECT-BRIEF.md) and keep a
[progress record](PROGRESS.md) of actual checks. The first checkpoint is a
useful local workflow. The [optional hooks](HOOKS.md) can help catch accidental
secret publication and skipped checks without changing the basic installation.

For a working starting point, use the [local Taskboard preview](../blueprints/fullstack-container/LOCAL.md).
To make it your own, use [editable project creation](INSTALL.md#create-a-new-editable-starter).
This explicit starter choice exports source into your project's `app/`; preserve
a different requested or existing framework instead of replacing it with Taskboard.
After creation, run `python3 local_preview.py start` from the new project to
start the app and PostgreSQL without OCI credentials. From the kit root,
`python3 scripts/blueprint.py inspect fullstack-container` shows its paths,
requirements, commands and remaining acceptance checks; `check` validates the
metadata and files offline. Neither command runs the listed commands or proves
cloud readiness. In an installed bundle, these helpers live under `.oci-founder-kit`.

## Existing Vercel or Netlify application

```text
Use oci-kit to migrate this app to OCI. Identify framework/runtime versions,
functions, edge middleware, image handling, scheduled jobs, storage, database,
identity, environment variable names and other hosted-service dependencies.
Preserve existing behavior, implement local changes and test them. Prepare an
OCI rehearsal deployment and separate traffic-cutover/rollback plans. Keep the
existing database, storage and authentication initially; migrate data in a later
tested step after hosting acceptance. Do not modify the source
account, migrate production data or switch DNS without my explicit approval.
```

The scan cannot see console-only settings, provider-managed data, traffic or
service contracts. The agent must ask for the missing facts without requesting
secret values. Keeping an external database or identity service can be a valid
first migration stage and is the default here; show what remains external and why.

Initialize a migration checklist with `project.py start --mode existing --task migrate`
and the appropriate project/agent/stack arguments. It records local context and
installs the kit if absent; it does not assess the app, migrate data or
execute the next command for you.

Use the [migration acceptance record](MIGRATION-ACCEPTANCE.md) to compare source
and target behavior and define hosting rollback before cutover. Data migration
is a separate later acceptance phase. Follow [the reusable target and explicit
environments](ENVIRONMENTS.md) for workload-specific doctor checks, temporary
sessions, read-only verification and the private local dashboard.

The [runnable Next.js example](../examples/migrate-nextjs/README.md) demonstrates
local production-server versus standalone-package checks on a small stateless
app. Use its capability matrix to understand the boundary; it does not validate
an arbitrary Vercel application or migrate provider-managed data.

## Resume an existing project

Open the same application folder and choose **Continue** on the site. Optionally
select a focus such as local workflow, access, design/cost or deployment
verification. Your selection is context, not a completed checkpoint or approval.
The agent must recheck current evidence and earlier prerequisites.

With a saved local project record, inspect or refresh it from the app folder:

```sh
python3 .oci-founder-kit/scripts/kit.py environment list --project .
python3 .oci-founder-kit/scripts/kit.py status --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py next --project . --environment rehearsal
```

Select the existing target explicitly; `rehearsal` is an example name. Legacy projects with no named environments may omit the flag only after inspection. `status` is read-only; `next` refreshes the local observations. Both return one
next action without running app tests or cloud operations. If the record is
missing, inspect the app and initialize it with `start --mode existing`; do not
recreate it. For an older installed kit, follow the [reviewed update path](INSTALL.md#update-or-remove-a-project-installation) first.

Use the website's continuation prompt, or paste:

```text
Use oci-kit to continue this project. Read its instructions, current changes and
docs/PROGRESS.md if present. Inspect the existing kit installation before trying
to install anything. Preserve the app's framework, services and uncommitted work.
If the unified helper is available, list environments and select the intended
named environment explicitly for status and next. Never silently choose production
or legacy progress. Check whether
recorded evidence still matches the current source. Continue the next unfinished
local checkpoint and update the progress record with actual
results. Explain missing facts together when they block the next step. Cloud
changes still need fresh approval of the exact plan; old progress is not approval.
Never request credential values. Finish with one clear next action.
```

Progress is maintained in your application, not measured by the website. Keep
raw evidence and machine state private in `.oci-kit/`; use the
[progress guide](PROGRESS.md) for recording results and a shareable summary. A
bookmark retains only allowlisted project mode, task, agent, stack and focus.
It does not save your brief, project files, credentials, completion status or
approval decisions.

## OCI credentials and initial setup

Use [oci-ready](../skills/oci-ready/SKILL.md) and its
[credential guide](../skills/oci-ready/references/credentials.md). Existing local
profiles, temporary sessions and workload principals are preferable to copying
credentials. A new tenancy requires user enrollment and possibly an administrator
to register the public key and prepare a parent compartment and group. Never paste
private key material or tokens into chat. No personal tenancy defaults ship here.

The doctor defaults to offline checks. `--live` authorizes the documented read
probes, not cloud writes. Successful authentication does not establish permission
to deploy every resource or confirm regional capacity.

After access is understood, use [oci-foundation](../skills/oci-foundation/SKILL.md)
for a scoped foundation plan. New IAM grants are reviewed separately from app
resources. Do not solve insufficient permissions with tenancy-wide administration.

## Deploy, verify and operate

1. Run the application's tests and the relevant infrastructure validators.
2. Review the five-pillar decisions, resource selection, external providers,
   dated recurring costs, access changes, recovery objectives and rollout plan.
3. Inspect the saved Terraform plan through `oci-deploy`. Explicitly approve that
   exact plan only when its target and consequences are correct.
4. Verify the running app: HTTPS, sign-in, permission isolation, persistence,
   health, logs and backup recovery. A unit-test pass is not a deployment receipt.
5. Retain update/rollback and approved cleanup instructions. Check for residual
   resources after partial failures or teardown. Review running costs separately.

The bundled full-stack blueprint defaults to a restricted sandbox. Its
[hardened reference](../blueprints/fullstack-container/PRODUCTION.md) adds
HTTPS, OIDC sign-in and ownership checks, Vault secrets and backups. Configure
protected state and validate the running controls and recovery before real users.

## Troubleshooting and updates

- Skill missing: restart the agent session, check installation.json in
  `.oci-founder-kit`, or open the source `skills/oci-kit/SKILL.md` directly.
- Existing install: use the [new-source updater](INSTALL.md#update-or-remove-a-project-installation)
  to check changes before applying them. It refuses edited owned files and
  registered hooks, preserves app/unowned files, and provides interrupted-update
  recovery. Legacy installs need a clean matching baseline checkout.
- Login or region failure: use the doctor's redacted result and official credential
  instructions. Do not send config files, token files or Terraform state to issues.
- Denied or unknown checks: the agent should explain the specific administrator
  action or unverified capability; it must not claim full readiness.
- Stale project evidence: source, helper code or evidence changed. Recheck it and
  record actual new results; a JSON status cannot grant deployment approval.
- Invalid app build: keep cloud deployment stopped and resolve local failures.
- Failed infrastructure apply: preserve the private receipt, inspect state and
  produce a recovery plan. Never automatically destroy shared resources.

The installer preserves your existing AGENTS.md, CLAUDE.md, agent settings and
skills. It does not install either coding tool or connect their accounts.

For specific runtime failures, use [read-only troubleshooting](../skills/oci-ready/references/troubleshooting.md).
For ownership, recovery and release evidence, use the [operations guide](OPERATIONS.md).
