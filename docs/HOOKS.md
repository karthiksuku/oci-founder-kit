# Optional checks for Claude Code and Codex

The kit works without hooks. Enable these checks when you want quick, local
feedback while your agent builds. They do not call OCI, install dependencies,
collect transcripts or approve cloud changes.

## Choose the checks

| Check | When it runs | What it does |
| --- | --- | --- |
| `secrets` | Before a plain `git commit` tool call | Scans the staged bytes for private artifacts and common secret patterns; blocks findings and incomplete coverage |
| `readiness` | Session starts or resumes | Reports kit version and missing local executables; leaves credential/permission checks to `oci-ready` |
| `validation` | A supported edit tool completes | Parses changed Python, JSON, TOML and skill frontmatter without executing application code; reports errors with paths and rule names |
| `cloud` | Before a supported shell tool call | Catches common direct cloud mutations and points back to the reviewed deployment workflow |
| `handoff` | The agent finishes a turn | Gives a non-blocking reminder to distinguish actual tests, plans, deployment and unfinished work |

Validation is bounded to 20 named files and 2 MiB per file. Identical content
checks are debounced for two seconds. A private local cache stores only hashes
and timestamps. Unsupported file types and paths outside the chosen project are
skipped; syntax checks do not replace the application's build or tests.

## Install into your application

First [install the kit](INSTALL.md) into your application. From the application
root, inspect the proposed setup:

```sh
python3 .oci-founder-kit/scripts/hooks_install.py install --project . --agent both --dry-run
```

Then explicitly opt in:

```sh
python3 .oci-founder-kit/scripts/hooks_install.py install --project . --agent both
```

Choose `--agent claude` or `--agent codex` for one host. To start with only
readiness and staged-secret checking, add `--checks readiness,secrets`.

The installer adds its entries to project-local `.claude/settings.local.json`
and/or `.codex/hooks.json`. Existing settings and hook entries are preserved.
It refuses malformed settings, symlinked directories and an existing installation;
there is no overwrite or force mode. Generated settings use absolute local paths,
so keep them out of Git using your local Git excludes. The kit's private hook
registration and cache directory has its own ignore file.

Open `/hooks` in each coding agent and review the generated commands using the
host's normal trust controls. Restart after changing trust. Codex also needs its
project configuration layer trusted. The installer never changes trust,
permissions, global configuration or existing hook enable/disable choices.
Managed organization policy can restrict which hooks run.

## Check status, update or remove

```sh
python3 .oci-founder-kit/scripts/hooks_install.py status --project . --agent both
python3 .oci-founder-kit/scripts/hooks_install.py uninstall --project . --agent both --dry-run
python3 .oci-founder-kit/scripts/hooks_install.py uninstall --project . --agent both
```

Uninstall removes exactly the registered entries and preserves unrelated hooks,
including ones added later. If a registered entry was edited, it refuses and asks
for manual review rather than guessing which configuration belongs to it.

Uninstall hooks **before** replacing or removing the bundled kit. After an update
or moving the project, install again and review the new commands. Each command
contains the hook script's SHA-256; a changed script stops protected pre-tool
checks with an explicit denial until the installation is reviewed. Status checks
registration and script consistency, not whether the host actually trusts it.

## Use the checks without lifecycle hooks

Before a commit from any tool or terminal:

```sh
python3 .oci-founder-kit/scripts/hooks.py staged --project .
```

The command checks the Git index, including binary blobs, without following
working-tree symlinks. Cleaning a working file does not clean a secret already
staged in the index. Stage corrected content and rerun the check.

Private artifacts include keys, real `.env` files, Terraform variable/state/plan/backend
files, credential folders and private gate receipts. Example files are permitted
by filename but still scanned for secrets. Placeholder values such as
`<set-locally>` and `${VARIABLE}` are accepted; a sample filename is not a blanket
exception. Findings show paths and rule identifiers, never matched values.

Large files, submodules, unavailable Git and exceeded limits produce incomplete
coverage, not a pass. Review large legitimate artifacts separately. The scanner
has common pattern checks; it cannot identify every possible secret or prove an
entire repository/history safe.

Before publishing an open-source release, stage the intended release and run:

```sh
python3 scripts/hooks.py public --project .
```

This separate publication check scans **all indexed tracked content**, including
unchanged files, and flags private workplace URLs and machine-specific home
paths in addition to secrets. It does not scan untracked files or Git history.
Private URL rules are publication checks, not a restriction imposed on ordinary
private application work. Keep confidential research outside the release tree.

You can also run data-only syntax checks explicitly:

```sh
python3 .oci-founder-kit/scripts/hooks.py validate --project . app.py package.json
python3 .oci-founder-kit/scripts/hooks.py readiness --project .
```

## Cloud approvals and limits

A hook can catch an accidental `terraform apply`, `tofu destroy`, OCI mutation,
image push, Skopeo registry copy/delete or common Kubernetes mutation. Generated
`.local-preview` files and private `*.tfbackend.json` settings are private artifacts even when force-staged.
Direct Terraform `init` and `plan` also need review because remote backends can
write state or lock objects. Use the deploy gate: local planning stays available,
and native OCI backend initialization/planning has its own exact approval.
The hook does not understand arbitrary
shell programs, aliases, SDK calls, remote execution or commands hidden inside
scripts. It never returns an allow decision or assumes a plan hash proves
human approval. Keep the normal agent permissions, scoped IAM, and the
[exact-plan deployment workflow](../skills/oci-deploy/SKILL.md).

A commit that stages files in the same shell command, uses `commit -a`, specifies
paths or targets another working tree must be split into separate staging and
commit calls. The hook checks the current index from the configured repository
root; it does not claim to cover content that a later command will stage.
Commits made outside the agent are not intercepted: run the staged check manually
or as an explicitly configured CI/pre-commit step.

Host coverage and failure behavior differ. Codex documents that malformed hook
responses, timeouts and some unsupported tool paths can let a tool continue.
Therefore the hook package is supplementary, not a complete enforcement boundary.
The script returns an explicit denial for failed pre-tool checks; other events
report useful feedback without creating an endless Stop loop.

## Compatibility and evidence

Python 3.11+ and Git are required for the staged checker. Generated shell adapters
target Linux, macOS and WSL shells. Linux is the local test platform; native
Windows installation is refused with guidance to use WSL. Other platforms need
their own consumer verification before a compatibility claim.

The implementation follows the current documented interfaces for
[Claude Code hooks](https://code.claude.com/docs/en/hooks) and
[Codex hooks](https://learn.chatgpt.com/docs/hooks), checked 13 November 2026.
Local CLI versions tested were Claude Code 2.1.251 and Codex 0.162.1. Tests
exercise both adapters' event payloads, deny responses, installation preservation,
rollback, script changes and removal.

The published 0.3.4 hook implementation was exercised in isolated Claude projects
on 13 November 2026. Its script SHA-256 is
`7381dc1854dbf6dca7ade94e460ec7ce99ce576ed5476d1c53917e62d649c147`.

- Actual host events verified SessionStart context and the non-blocking Stop reminder.
- Fake Terraform init/plan and Skopeo publication commands were denied before
  execution. A fake saved-plan inspection ran exactly once as a positive control.
- A literal Git commit attempt was denied specifically because a synthetic
  `*.tfbackend.json` file was staged. No commit occurred and the index was unchanged.
- One Write produced an invalid synthetic Python file and a fresh validation-cache
  entry matching its exact path/content hashes. Claude reported the expected
  `invalid-py` warning. This host did not stream a separate raw PostToolUse response,
  so the diagnostic text is model-reported and corroborated by the runtime cache.

The probes used normal restricted host permissions; temporary hooks were removed
through the installer afterward. No application code or OCI command was executed.
These cases do not establish coverage of arbitrary shell commands or every host
version. See the [dated release follow-up](RELEASE-0.3.4.md).

Codex loaded the four current event definitions without configuration errors,
with its project layer active, and reported all four hooks untrusted. Normal
owner review remains required. Trusted Codex runtime is still unverified;
adapter tests and schema loading do not establish that result.
