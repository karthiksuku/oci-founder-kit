# 0.5.0 preview evidence

This release connects the local founder journey: choose a new or existing app,
save private progress, resume the next action and update the installed toolkit
without replacing application edits. It does not establish a completed OCI
application deployment or migration.

## Included

- `project.py` starts build, migration or setup workflows. Private checkpoints
  bind to source and evidence fingerprints; stale records need review. Recognized
  private configuration is excluded or observed through metadata; other source
  files, including unrecognized JSON, are read for hashing. Recorded
  outcomes remain owner assertions and never supply cloud approval.
- The website separates new, existing and continuing projects, with stage-aware
  handoff, inline setup help, mobile copy controls and ephemeral project briefs.
- An explicit release manifest limits distributed files and verifies their
  bytes. Ownership records support update previews, conflict refusal, backup
  and recovery. Legacy snapshots need a clean matching baseline. Hashes are not
  publisher signatures.
- The hardened Taskboard checker offers bounded anonymous HTTPS checks and an
  explicit two-session synthetic exercise. Authentication, authorization, CSRF
  and file round trips have local route coverage. Hosted login, real OCI backing
  services, restart/restore and object-version deletion remain separate.
- Hook Git inspection disables fsmonitor and lazy fetching; validation redacts
  token-shaped filenames. Private project progress is excluded from publication.

## Verification scope

Checks ran on Linux with local dependencies already installed:

| Check | Result |
| --- | --- |
| Root Python suite with local HTTPS and Next.js packaging opt-ins | 584 tests passed; no skips |
| Repository validator and Claude plugin validation | Passed |
| Website build/type checks | Passed, no errors or warnings |
| Website unit cases and browser tests | 20 cases and 20 browser tests passed |
| Website visual review | 24 desktop/mobile/light/dark captures reviewed |
| Independent consumer checks from an exact indexed-source archive | Seven scenarios passed, including an actual v0.4.1 upgrade |
| Publication content check | Passed across all 279 indexed files |
| Gitleaks source scan | Two byte-identical, previously reviewed noncredential findings; none unresolved |
| Built website scan | No findings |
| Fresh installation and editable-starter scans | Documentation/test expressions and verified file-integrity hashes only; none unresolved |
| Current hook script in normal Codex host | Four commands trusted; actual SessionStart and one PreToolUse denial verified in an isolated fixture |

Consumer checks cover both coding-agent installations, generic new apps, existing
repository preservation, explicit editable Taskboard creation, installed resume,
legacy upgrade preservation and exclusion of unlisted synthetic JSON. Website
checks include keyboard access, mobile layouts, no-JavaScript fallback, clipboard
fallback and ephemeral brief handling. The 17 checker tests include real local
HTTPS production routes with synthetic stores; they do not prove OCI deployment.

No cloud write, deployment, traffic change or resource cleanup is part of this
release. Scans are bounded checks, not proof that every possible secret is detectable.

Independent local review exercised concurrent update/recovery, interrupted writes,
edited ownership, legacy Git filters, private filename handling and mixed-format
receipt timestamps. Regression tests cover the corrected cases.

## Remaining acceptance

The existing bounded synthetic OCI backend rehearsal and digest publication
evidence still apply only to their documented scope. Effective inherited IAM,
full application deployment, hosted identity, cloud recovery and stateful
migration/cutover require workload-specific plans and verification.

Optional hooks require normal host trust review in each applicable project.
See [dated hook evidence](HOOKS.md) for exact host coverage. A hook or progress
record cannot supply human approval for a cloud write.

The [CI workflow template](ci/validate.workflow.yml) is supplied but has not been
installed as an Actions workflow with the available publication credential.
Local test results are not a GitHub CI pass.
