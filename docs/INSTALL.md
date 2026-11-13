# Install OCI Founder Kit

Install the kit into the application you want to build or migrate, then start
Claude Code or Codex in that application directory. You need Git, Python 3.11+
and your own installed coding tool and account. OCI credentials are configured
separately when you are ready to connect to your tenancy.

## Project installation

Clone the kit outside your app directory. Set `--project` to an existing
application folder; create an empty folder first if you are starting a new app.

```sh
git clone https://github.com/karthiksuku/oci-founder-kit.git
python3 oci-founder-kit/scripts/install.py --project /absolute/path/to/my-app --agent both
cd /absolute/path/to/my-app
```

Choose the coding tool you use:

| Installer option | Project skill directory |
| --- | --- |
| `--agent codex` | `.agents/skills/` |
| `--agent claude` | `.claude/skills/` |
| `--agent both` | Both directories |

The installer copies the toolkit into `.oci-founder-kit/`. Its generated skill
entries point back to that bundle so scripts, diagrams, references and blueprints
stay together. Installation makes no network calls or cloud changes and does
not edit global settings, `AGENTS.md`, `CLAUDE.md` or existing skills. It refuses
occupied destinations instead of overwriting them.

Add `--dry-run` to preview the selected agents and skill names without writing
files. The Git clone itself requires internet access; subsequent agent and OCI
operations have their own connectivity and account requirements.

## Start your first session

Launch your coding tool from the app directory. If the new skills do not appear,
open a fresh session.

In **Codex**, use:

```text
$oci-kit Build my app on OCI. Help me set up access and the required foundation.
```

In **Claude Code**, use:

```text
/oci-kit Build my app on OCI. Help me set up access and the required foundation.
```

For migration, replace the goal with “Migrate this Vercel application to OCI,
starting with a repository assessment.” For credentials or an existing tenancy,
start with “Check my OCI access and help me prepare a dedicated compartment.”
See [the start guide](START-HERE.md) for complete task prompts and what to expect.

The agent can build locally while cloud setup is incomplete. Account enrollment,
identity verification and administrator bootstrap use your own account or an
authorized administrator. Never paste private keys or tokens into chat. The
kit prepares reviewed plans; every cloud write requires approval of its exact
target, permissions, resources and costs.

## Claude Code plugin alternative

The complete kit is also a Claude Code plugin:

```sh
claude plugin marketplace add karthiksuku/oci-founder-kit
claude plugin install oci-founder-kit@oci-founder-kit-marketplace
```

Invoke the plugin entry with `/oci-founder-kit:oci-kit`. This differs from the
project-local `/oci-kit` command. Choose one delivery method for a given scope
to avoid duplicate skill entries. The project installer does not install or
configure the plugin marketplace.

## Update or remove a project installation

The installed bundle is a snapshot. Updating the original Git checkout does
not update an application that already has `.oci-founder-kit/`.

Inspect its version and entry skills without changing anything:

```sh
python3 .oci-founder-kit/scripts/install.py --project . --status
```

The manifest fingerprint identifies public release metadata; it is not proof
of publisher authenticity or an integrity check of every installed file.

1. Review the new [release notes](https://github.com/karthiksuku/oci-founder-kit/releases).
   Check your app's version-control status and preserve any changes you made
   inside the installed bundle or generated skill entries.
2. Inspect `.oci-founder-kit/installation.json` to identify the agents and skill
   names installed by this copy. Keep unrelated skills and agent configuration.
3. Preserve any private Terraform state, working plans and receipts before
   replacing the bundle. Removing the kit does not destroy cloud resources;
   teardown is a separate approved operation.
4. If you enabled [optional hooks](HOOKS.md), use their uninstall command first.
   Remove only this kit's bundle and its matching generated skill folders,
   then run the installer from the reviewed new checkout. Do not delete the
   whole `.agents/`, `.claude/` or `skills/` directory.
5. Open a fresh agent session and confirm the expected skill is available.

To uninstall, follow the same review and preservation steps and omit the final
reinstall. There is no force-overwrite or automatic uninstall command.

## Optional local hooks

The basic installation does not change agent settings or enable hooks. See the
[hook guide](HOOKS.md) for staged secret checks, offline readiness, targeted
validation and cloud-operation reminders. Review the commands and use your
agent's normal trust flow before enabling them. Existing hooks are preserved.

## Platform and troubleshooting notes

- **Linux:** the fresh-install and local runtime tests in the
  [0.2.1 evidence](RELEASE-0.2.1.md) ran here.
- **macOS:** the installer uses standard-library Python and project-local files;
  a fresh-user macOS run is not recorded in this release.
- **Windows:** use Python 3.11+ (`py -3` can replace `python3`) and a valid absolute
  Windows app path. Native Windows execution and credential ACLs remain untested.

If installation refuses, verify that the app directory exists and is outside
the source kit, and that the target bundle or skill names are not already
occupied. Symlinked discovery directories are refused. Do not remove an existing
skill without checking who owns it and preserving any local edits.

For authentication failures use the [credential guide](../skills/oci-ready/references/credentials.md).
For deployment limits and tested capabilities read [the status](ROADMAP.md).
Send only redacted diagnostics when reporting a problem; keep credentials,
Terraform state and private receipts out of GitHub issues.
