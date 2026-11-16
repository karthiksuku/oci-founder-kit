# Know what is actually done

Keep a short progress file in the application's documentation, separate from
private deployment receipts. Update it at meaningful checkpoints. The site and
prompt builder do not measure progress automatically.

For the shareable Markdown summary, use **not started**, **in progress**,
**passed**, **blocked** or **not applicable**.
Every passed row needs evidence; explain why a row is not applicable.

| Checkpoint | Status | Evidence to record | Next action |
|---|---|---|---|
| Useful local app | Not started | Source revision, build/test commands, primary user flow and result | Implement or fix the local workflow |
| Access and target | Not started | Doctor result, chosen auth method, region/compartment confirmed privately | Resolve specific missing access |
| Design and cost | Not started | Five-pillar decisions, dated pricing basis, retained providers and risks | Review unresolved decisions |
| Cloud plan | Not started | Private saved-plan reference, expiry, changes and owner decision | Review the exact current plan |
| Deployment | Not started | Private receipt reference, verified endpoint and runtime checks | Verify health, identity and persistence |
| Recovery and operations | Not started | Restore/rollback results, remaining resources, owner/runbook | Resolve unverified operations |
| Migration cutover | Not started | Approved traffic switch, parity/data checks and rollback window | Keep source until acceptance |
| Production acceptance | Not started | Security, recovery, cost and operational evidence accepted by the owner | Resolve each blocker before real users |

Record commands and outcomes, including skipped checks and environmental limits.
A successful local build is not a deployed app. A saved plan is not a completed
deployment. An empty resource search is not proof that cleanup succeeded.

Keep reports shareable: no passwords, key material, account identifiers, customer
data, signed URLs or full private logs. Use an app-owned private evidence folder
for raw results. Link only public or deliberately redacted evidence in Git.

At handoff state: **what works, what was checked, what remains unknown, and the
one next action**. See [operations and recovery](OPERATIONS.md).


## Private project checklist

The local `scripts/project.py` helper maintains `.oci-kit/state.json` and returns
JSON with `schema: oci-kit-project/1`, applicable checkpoint statuses and exactly
one `next_action`. These legacy commands remain local guidance.
Initialize it through the [new/existing project paths](INSTALL.md). Keep the saved
task, agent, stack and blueprint consistent; resume does not rewrite those choices.

From the application folder:

```sh
python3 .oci-founder-kit/scripts/project.py status --project .
python3 .oci-founder-kit/scripts/project.py resume --project .
```

`status` reads current observations without updating the record. `resume` refreshes
local observation fingerprints and returns the next action. Neither runs app
commands, opens known credential stores, contacts OCI or authorizes a change. A command
in `next_action` has not been executed. Missing state calls for inspection and
`start --mode existing`, not replacement of working app code.

The helper creates `.oci-kit/` and its evidence directory with private permissions,
and an internal `.gitignore` containing `*`. Keep this directory out of Git,
including state, raw reports and update backups. Ignore rules do not remove
previously tracked files and do not prevent force-add; review what you publish.
Keep `docs/PROGRESS.md` deliberately redacted and separate from raw evidence.

### Record an actual result

Run the meaningful check yourself or through your coding agent within its current
authorization. Save the real command, result, source revision and remaining limits
in a private, nonempty report, for example `.oci-kit/evidence/local-workflow.txt`.
The report must be an owner-readable/writable regular file with mode `0600`, directly
inside `.oci-kit/evidence/`; nested paths and unsafe file types are refused.

After that report exists, record it from the app folder:

```sh
chmod 600 .oci-kit/evidence/local-workflow.txt
python3 .oci-founder-kit/scripts/project.py record --project . \
  --step local-workflow --evidence .oci-kit/evidence/local-workflow.txt \
  --outcome passed
```

Use `--outcome blocked` for a check that is blocked. Recording does not execute or
independently validate the report's assertions. A passed record is labeled
**owner-recorded**, not verified. The helper stores evidence/source/helper hashes
and a timestamp, not the report content in its JSON output.

Recordable steps are `migration-assessment`, `local-workflow`, `access`,
`design-cost`, `runtime`, `recovery` and `cutover`; only those applicable to the
saved task are accepted. Setup has no app workflow, and cutover applies to
migration. For `access`, use the existing doctor's `oci-readiness/1` JSON report.
A passed access record requires a passed **live-read-only** doctor result;
offline readiness does not establish live access, complete provisioning permissions
or regional capacity. Authorize the read probes separately when needed.

### Read statuses honestly

| Local result | Meaning |
| --- | --- |
| `not-recorded` | No owner evidence has been recorded for this checkpoint. |
| `owner-recorded` | The owner recorded a passed outcome and its tracked inputs still match; the assertions were not independently tested by this helper. |
| `blocked` | The owner recorded a blocked outcome for the current inputs. |
| `stale` | Source inputs, toolkit helpers or the evidence file changed, disappeared or became unsafe. Recheck and record current evidence. |

The source fingerprint is bounded and does not prove that every external setting
or service stayed unchanged. Known private paths use metadata or are excluded;
other source files, including unrecognized JSON, are read for local hashing.
This is not arbitrary-secret detection. Relevant file metadata can invalidate
records. Restoring unchanged metadata deliberately
is outside this freshness check. An unchanged hash is not proof of runtime health.

The helper separately observes the conventional `terraform/.gate` plan and receipt
metadata. It can surface absent, expired, changed or unreadable plans, a pending
review, an observed apply/destroy receipt, or an attempt needing review. An apply
receipt is not evidence that HTTPS, identity, recovery or user behavior works.
Other infrastructure layouts are not automatically discovered.

`cloud-plan`, `deployment` and `acceptance` cannot be marked passed through the
ordinary `record` command. Cloud changes still require the existing exact-plan
deploy gate and current owner approval. Final production acceptance remains an
owner decision about actual workload evidence and risks. Neither a site selection,
a local record, a receipt nor an old approval substitutes for that decision.

## Explicit environments and executable read checks

The [environment workflow](ENVIRONMENTS.md) adds private `oci-kit-project/2`
records without replacing the original v0.5 record. Every operation names its
environment; production has a separate infrastructure root, configuration,
backend key, evidence and receipts. A legacy conversion backs up observations
and starts empty checkpoints; approvals and passed assertions never transfer.

`project.py doctor --environment NAME` composes blueprint-specific prerequisites;
`--live` enables its documented bounded OCI reads. `verify` performs the selected
HTTPS health or migration-contract reads. Both save private reports bound to the
target, source, executed helpers and observation time. They do not apply resources
or certify production readiness. An environmental access record must reference a
fresh bound workload-doctor envelope; a legacy doctor report cannot stand in for it.

For environmental evidence, use `.oci-kit/environments/NAME/evidence/FILE` and
pass the same `--environment NAME` to `record`. Known machine reports expire after
24 hours as well as on input changes. Plain owner notes remain assertions, not
time-bounded machine verification. `dashboard --environment NAME` renders a
private, network-free local view from these same reports. Missing cost and health
evidence stays unknown; the public website does not read any of this state.
