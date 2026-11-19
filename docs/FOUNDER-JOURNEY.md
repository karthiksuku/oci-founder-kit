# Verify a complete founder journey

Use the journey report to see what the selected application has demonstrated and
what still needs evidence. Run it from the application root after local onboarding:

```sh
python3 .oci-founder-kit/scripts/kit.py journey --environment rehearsal --kind build
python3 .oci-founder-kit/scripts/kit.py journey --environment rehearsal --kind migrate --json --non-interactive
```

Use the actual environment name. Migration requires a project initialized for
the migration task. A retained source environment cannot be selected as the OCI
target. The report makes no network requests, executes no application code,
changes no files and grants no approval. Commands it prints are suggestions;
they are never executed by the report.

The report connects [new-account setup](NEW-OCI-ACCOUNT.md), the
[deployment workflow](WORKFLOW.md), [operating observations](OPERATIONS.md) and
[migration acceptance](MIGRATION-ACCEPTANCE.md). It uses the same environment,
source and toolkit bindings as those helpers instead of another progress store.

## Read the evidence correctly

| Status | Meaning |
| --- | --- |
| `configured` | Required local choices exist; their cloud behavior is unproven. |
| `owner-recorded` | Someone recorded a local-workflow result. Inspect its underlying evidence. |
| `reported` | A current report describes a narrow read-access or HTTPS check. It does not establish the complete journey. |
| `observed` | The existing OCI observation validator accepted live-mode image readback against the current deployment receipt and selected digest. This is still local evidence, not a signed service attestation. |
| `missing` / `unknown` | Evidence is absent or insufficient. Unknown never means passed. |
| `stale` / `ambiguous` / `invalid` | The latest evidence cannot be safely interpreted; rerun the appropriate check. |
| `failed` | A relevant check failed; investigate before any new cloud plan. |

Reports must match the selected environment, source, kit and target, and be no
older than 24 hours. An ambiguous newest timestamp, malformed report or newer
failure cannot fall back to an older passing result. Updating the source, kit or
environment requires new evidence. Resource observation also validates the
latest exact deployment receipt. Injected test clients cannot establish OCI
image identity.

Current report formats do not prove hosted login, persistence after restart,
isolated restore, rollback, effective IAM isolation or retained-resource review.
Those remain explicit manual gates. Adding a JSON boolean or recording a
checkpoint cannot mark them accepted. Consequently this preview returns
`journey_accepted: false` until those acceptance contracts are implemented and
their real outcomes verified. The CLI returns exit status 3 for incomplete or
failed acceptance while still displaying the coverage report. Automation must
inspect the reported gates; producing a report does not establish readiness.

## New application: reproducible acceptance

1. **Start from a real founder environment.** Activate the OCI account and MFA,
   complete authorized administrator setup, and select a dedicated rehearsal
   environment. Record kit, agent, model and platform versions privately.
   Preserve all attempts, including failures. Credentials remain in local
   configuration, outside the application and transcripts intended for sharing.
2. **Prove the local application.** Ask the chosen agent to implement the intended
   user workflow, then independently run its meaningful tests. Keep the framework
   and application source; do not substitute the reference application. Prepare
   and review packaging and foundation changes through the existing workflow.
3. **Deploy through exact plans.** Review the destination, image digest, resource
   scope, costs and identity boundaries. Obtain the owner's approval of each
   exact cloud plan before execution. A passing doctor, saved preference or
   earlier approval does not authorize a later operation. Resolve inherited IAM
   restrictions with an authorized administrator.
4. **Collect narrow observations, then exercise real behavior.** The following
   commands collect existing bounded read-only reports for the selected target:

   ```sh
   python3 .oci-founder-kit/scripts/kit.py doctor --environment rehearsal --live
   python3 .oci-founder-kit/scripts/kit.py observe --environment rehearsal --live
   python3 .oci-founder-kit/scripts/kit.py verify --environment rehearsal --kind runtime
   python3 .oci-founder-kit/scripts/kit.py journey --environment rehearsal --kind build
   ```

   Separately verify hosted sign-in, callback/logout/expiry, two-user isolation
   and meaningful application workflows. Synthetic application writes require
   their own reviewed scope. Retain real results; successful anonymous health
   checks do not cover these behaviors.
5. **Demonstrate recovery and finish the trial.** Approve a scoped restart and an
   isolated restore, verify persistence and restored application behavior, then
   prepare and approve image rollback to the previous accepted digest. Record
   actual recovery outcomes, retained resources and dated costs. Finish each
   sandbox run with separately approved cleanup and readback of what remains.
   Never delete live data merely to make a trial look clean.

The acceptance outcome is the demonstrated behavior and reviewed evidence, not
the agent's final prose or a count of passing unit tests. Maintain separate
records for Claude Code and Codex. Keep the existing
[restricted local evaluations](AGENT-EVALUATIONS.md) separate from ordinary
agent sessions and approved live OCI trials.

## Hosting-first migration: additional acceptance

Use a representative existing Next.js application or ordinary containerized web
service. Keep its existing database, authentication, storage, schedulers and
workers initially. Bind distinct source, rehearsal and production environments.

Prepare the exact private migration contract and run the existing verification
command with that contract and any required private sessions. `verify --help`
lists its current arguments; secrets and private filenames do not appear in the
journey report. Review the contract's actual coverage alongside the report:
HTTP parity alone cannot establish browser acceptance.

The independent review must demonstrate:

- User workflows across browser navigation/hydration, cookies, redirects,
  uploads, streaming and application-specific caching behavior.
- OCI connectivity, TLS, callback origins and measured latency to retained
  services; a successful local container build is insufficient.
- One owner for scheduled work and workers. Keep the target disabled until a
  separate approved ownership transfer prevents duplicate effects.
- Separately reviewed traffic cutover and rollback to the preserved source,
  with observable success and failure criteria.
- Hosting acceptance before any later database or object migration. Track
  overlap and retained-resource costs separately.

The report surfaces these as pending gates rather than inventing a general
browser or recovery verifier for arbitrary founder applications.

## Share results without sharing private infrastructure

The journey output projects fixed statuses and instructions. It excludes account
identifiers, hostnames, image references, private filenames, credentials, raw
logs and application source. Keep underlying evidence private. Use the existing
[support export](WORKFLOW.md) for a reviewed support bundle; neither tool uploads
anything automatically. Redact independently before publishing any live-trial
evidence or agent transcript.
