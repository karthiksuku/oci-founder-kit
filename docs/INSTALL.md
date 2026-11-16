# Install OCI Founder Kit

Choose **New project**, **Existing project** or **Continue** in the
[founder guide](https://karthiksuku.github.io/oci-founder-kit/#start), then open
Claude Code or Codex in your application folder. You need Git, Python 3.11+ and
your own coding tool and account. The project helper supports Linux, macOS and
WSL2. OCI access can be configured after local development starts.

Use a fresh, reviewed release checkout outside your app. Installation and
creation copy only the exact files listed in `release-manifest.json`, checking
their SHA-256 bytes first. Missing or changed listed files are refused; extra
unlisted files are not added to the installed bundle. These hashes detect byte
changes, **not publisher authenticity or secret safety**. The manifest is not a
signature. Keep operational data and credentials outside the source checkout,
and review the resulting project before sharing it.

## Start a new project

For a new app in your chosen stack, clone the kit once or reuse a reviewed clone:

```sh
git clone https://github.com/karthiksuku/oci-founder-kit.git
python3 oci-founder-kit/scripts/project.py start \
  --project /absolute/path/to/my-app --task build --mode new \
  --agent both --stack nextjs
cd /absolute/path/to/my-app
```

Use `--stack nextjs`, `fastapi`, `custom` or `auto`. The choice is advisory:
this command creates the empty project, local skills and private progress state;
your coding agent implements the app. It does not generate Taskboard or replace
a requested framework. The target must be a new child of an existing parent,
or an empty existing directory outside the kit. Nonempty targets are refused.

The JSON result has one `next_action`. Follow that instruction in your coding
agent; a listed command is guidance, not something the helper executed. No app
tests, dependency installation or cloud operations run. If setup fails, preserve
any partial folder and inspect the failure before retrying.

## Create a new editable starter

Choose this path explicitly for the included Node.js/PostgreSQL Taskboard.
From outside your app, clone the kit once or reuse your reviewed clone:

```sh
git clone https://github.com/karthiksuku/oci-founder-kit.git
python3 oci-founder-kit/scripts/project.py start \
  --project /absolute/path/to/my-app --task build --mode new \
  --agent both --stack auto --blueprint fullstack-container
cd /absolute/path/to/my-app
```

The blueprint flag is required for Taskboard. It cannot be combined with a
Next.js/FastAPI stack selection. The same new-or-empty target rules apply.
Creation copies app source, infrastructure, agent skills and local project state
offline. It enables no hooks, installs no dependencies and starts no services.

With local Docker and Compose available, start the preview separately:

```sh
python3 local_preview.py start
```

Follow the [preview requirements](../blueprints/fullstack-container/LOCAL.md).
Edit **your project's `app/` and `terraform/`**; `.oci-founder-kit/` is the toolkit
snapshot. Run `start` again after app edits to rebuild. `stop` preserves the
local database and private settings. This is an unauthenticated local sandbox,
not a deployed app.

The lower-level `scripts/blueprint.py create fullstack-container` command remains
available, including its `--dry-run` option. It exports the app and skills without
initializing the new project checklist. `project.py` has no `--dry-run` flag.

## Project installation

Clone the kit outside your existing app, or reuse a reviewed clone. Set
`--project` to the existing application folder:

```sh
git clone https://github.com/karthiksuku/oci-founder-kit.git
python3 oci-founder-kit/scripts/project.py start \
  --project /absolute/path/to/my-app --task build --mode existing \
  --agent both --stack custom
cd /absolute/path/to/my-app
```

Use `--task migrate` for an existing hosted app, or `--task setup` for OCI access
and foundation work. Setup can use an empty existing folder. Existing mode
preserves app files and reuses an installed kit instead of reinstalling it.
If saved project choices already exist, use `resume`; a different task, agent,
stack or blueprint is not silently written over them.

Choose the coding tool you use:

| Installer option | Project skill directory |
| --- | --- |
| `--agent codex` | `.agents/skills/` |
| `--agent claude` | `.claude/skills/` |
| `--agent both` | Both directories |

The installer copies the toolkit into `.oci-founder-kit/`. Generated entry
skills point to that snapshot. It preserves app instructions, global settings
and unrelated skills, refusing occupied destinations. The project helper adds
private state under `.oci-kit/`; its own ignore file excludes those contents
from ordinary Git additions. Do not force-add them or publish raw reports.

## Kit-only installation

The existing installer still works when you only want skills and the bundle:

```sh
python3 oci-founder-kit/scripts/install.py --project /absolute/path/to/my-app --agent both
```

The target must already exist. Add `--dry-run` to preview the selected agents
and skill names without writing files. This does not create a project progress
record. Initialize one later with `kit.py start --mode existing`; do not
reinstall or delete working app files. Git clone, coding-agent sessions and
later OCI operations have their own network and account requirements.

## Start your first session

Launch your coding tool from the app directory. If the new skills do not appear,
open a fresh session.

| Codex | Claude Code |
| --- | --- |
| `$oci-kit Build my app on OCI.` | `/oci-kit Build my app on OCI.` |

For migration, replace the goal with “Migrate this Vercel application to OCI,
starting with a repository assessment.” For setup, use “Check my OCI access and
help me prepare a dedicated compartment.” The [start guide](START-HERE.md)
provides full prompts, first checkpoints and continuation guidance.

## Continue a project

From the same application folder, inspect the local record:

```sh
python3 .oci-founder-kit/scripts/kit.py environment list --project .
python3 .oci-founder-kit/scripts/kit.py status --project . --environment rehearsal
```

`status` reads observations without updating the project record. To refresh the
record and receive the next action:

```sh
python3 .oci-founder-kit/scripts/kit.py next --project . --environment rehearsal
```

Neither command runs app tests, contacts OCI or grants approval. Known private
paths are excluded from content reads; other source files are hashed locally.
This is not a secret detector. Replace `rehearsal` with the existing named target.
For legacy records with no named environments, omit the flag only after inspection.
`start --mode continue` preserves the explicit environment selection and saved choices. Changed source, helper code or evidence makes earlier records stale.
See [recording actual evidence](PROGRESS.md#private-project-checklist).

For an installation with no project state, initialize it once with
`kit.py start --mode existing`, using the intended task, agent and stack.
For an older kit without `project.py`, review and update it first using the new
source helper below. Do not recreate an existing app to obtain a progress file.

## Claude Code plugin alternative

The kit is also a Claude Code plugin:

```sh
claude plugin marketplace add karthiksuku/oci-founder-kit
claude plugin install oci-founder-kit@oci-founder-kit-marketplace
```

Invoke the plugin entry with `/oci-founder-kit:oci-kit`; project-local skills
use `/oci-kit`. Choose one delivery method per scope to avoid duplicate entries.
The project installer does not configure the plugin marketplace. Project-local
commands above assume a `.oci-founder-kit/` installation.

## Update or remove a project installation

An installed kit is a snapshot. Updating its original checkout does not update
the app's `.oci-founder-kit/`. First inspect the installation from the app:

```sh
python3 .oci-founder-kit/scripts/install.py --project . --status
```

Read the new release notes and obtain a separate, reviewed **new release source**
outside the app. Run the updater from that new source, not from the old bundle:

```sh
python3 /absolute/path/to/oci-founder-kit-new/scripts/update.py check \
  --project /absolute/path/to/my-app
```

`check` stages and verifies the replacement in a temporary directory, reports
owned-file changes, and does not change the app. After reviewing that report:

```sh
python3 /absolute/path/to/oci-founder-kit-new/scripts/update.py apply \
  --project /absolute/path/to/my-app
```

The updater changes only owned kit files and generated skill entries. It keeps
application code, unrelated files and `.oci-kit/` project state. Edited or missing
owned files, collisions with unowned files and registered kit hooks are refusals,
not permission to overwrite. Preserve and reconcile local edits first. Uninstall
kit hooks with the installed hook helper before updating, following the
[hook guide](HOOKS.md); review their new commands through the normal trust flow
if you enable them afterward. The updater does not grant hook trust.

Legacy installations such as **v0.4.1** lack the new per-file ownership list.
For both `check` and `apply`, add
`--baseline /absolute/path/to/oci-founder-kit-v0.4.1`: a separate clean Git checkout
of the exact installed version. Its index and tracked working bytes must match
its release commit. An arbitrary folder or edited checkout is not a baseline.
Inspect the installed version first; use its matching release rather than
assuming every legacy installation is v0.4.1.

Updates retain a private backup/journal under `.oci-kit/updates/`. If an
interruption leaves a recovery marker, preserve that directory and use the
same reviewed new-source updater:

```sh
python3 /absolute/path/to/oci-founder-kit-new/scripts/update.py recover \
  --project /absolute/path/to/my-app
```

Recovery restores the previous owned files for an interrupted update, or verifies
a completed update and clears its stale marker. Unexpected post-update edits
cause refusal. It is not an arbitrary downgrade command. Inspect the result,
open a fresh agent session and recheck project evidence after an update.

For manual uninstall, inspect `installation.json`, preserve private data and
local changes, then remove only the kit-owned bundle files and matching generated
entry files. Keep unrelated `.agents/`, `.claude/`, instructions and skills.
Removing the kit does not destroy cloud resources or cancel cloud charges;
cleanup remains a separately reviewed operation.

## Optional local hooks

The basic installation does not change agent settings or enable hooks. The
[hook guide](HOOKS.md) covers staged content checks, readiness, targeted validation
and cloud-operation reminders. Review the exact commands and use the agent's
normal trust flow before enabling them. Existing hooks are preserved.

## Platform and troubleshooting notes

- Project state, editable creation and the update/recovery workflow require the
  supported local filesystem operations on Linux, macOS or WSL2. Use WSL2 for
  these workflows on Windows; native Windows behavior is not established here.
- Installation refusal: check the target folder, existing kit ownership and
  symlinked paths. Preserve conflicts rather than deleting unknown files.
- Missing state: inspect the app and initialize with `start --mode existing`;
  missing state is not a reason to replace the app.
- Update refusal: inspect owned edits, hooks, release integrity, legacy baseline
  and any interrupted update before retrying.
- Read the release evidence for tested platforms and limitations; a platform
  listed as supported by a helper is not a claim of fresh-user acceptance here.

Use the [credential guide](../skills/oci-ready/references/credentials.md) for
access problems and [capability status](ROADMAP.md) for deployment boundaries.
Share only deliberately redacted diagnostics. Keep credential files, state,
raw evidence and update backups out of GitHub issues.
