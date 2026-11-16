# Operating the SaaS reference

## Ownership, permissions and migration

Maintain one database per named environment. Use separate web and worker DB
credentials, reviewed table grants and network scopes. The web role needs normal
Taskboard/session access, insertion of jobs/outbox/inbox, and owner-filtered job
reads. The worker needs the ledger/outbox and request/summary tables plus **read**
access to ownership/schedules. Grant the worker cursor-only updates and schedule-run
insertion as illustrated below. Neither runtime role should change ownership,
schedule configuration (enabled, period, anchor, version or owner), replay audit
records or schema. Those belong to the
administrator role and a separately reviewed database change. For the administrator's exact reviewed grant plan (substitute the chosen restricted
worker role), the scheduling portion is:

```sql
GRANT SELECT ON saas_ownership, saas_schedules TO worker_role;
-- FOR SHARE needs UPDATE on at least one column. The guard is constrained FALSE.
GRANT UPDATE (lock_guard) ON saas_ownership TO worker_role;
GRANT UPDATE (last_due, skipped) ON saas_schedules TO worker_role;
GRANT SELECT, INSERT ON saas_schedule_runs TO worker_role;
```

These are illustrative grants to review with the database's existing policies,
not an automatically executed migration. Application query
filters are tested; they do not claim database RLS or tenant-wide IAM isolation.
Do not claim cross-environment cloud denial until a real negative permission test
passes against each deployed identity.

Initialize `saas_ownership` with the selected environment, `owner='paused'`,
generation 1 and the reviewed change's evidence digest. Missing ownership blocks
new accepted work through a foreign key; it never guesses a default target.
Existing source queues and schedulers remain authoritative during hosting-only
migration. Before transfer, inspect source in-flight work and reconcile outstanding
external effects. Record the exact old and new owners, generation, DB target,
source-quiescence evidence and rollback steps in the approved change.

The internal `transferOwnership` function requires `source → paused → oci` or
`oci → paused → source` as separate transitions. It checks the expected owner and
generation. Pausing increments the fencing generation. Old claims then fail
before transactional effects can commit; a running effect holds the ownership
lock until its transaction finishes. An interrupted transfer remains paused.
These functions have **no public HTTP route or automatic CLI executor**. An
administrator calls them only inside the approved database change process;
an evidence hash is audit metadata, not authorization or proof that a source
outside this database has stopped.

## Processing and failure recovery

The web service commits request + job + outbox together. A webhook commits inbox,
job and outbox before HTTP 202. Outbox retries always publish the same job ID;
a lost successful enqueue response therefore creates safe duplicate deliveries.
Queue payloads carry only schema, environment and job ID, not customer content.
The consumer loads the actual work from the selected database, claims a 60-second
lease and renews visibility/lease every 20 seconds while processing. PostgreSQL
ownership and lease checks fence stale workers. Reference effects and completion
commit together before Queue deletion. A lost deletion response is deduplicated
on redelivery.

Five failed processing attempts mark a job dead. The worker does not acknowledge
dead/invalid deliveries; the template enables Queue's DLQ after ten deliveries.
The queue has seven-day retention, **not permanent archival**. The durable ledger
retains the error code and job identity. A bounded reconciliation pass republishes
pending or expired claims stranded for ten minutes by transport loss/expiry; the
same retry limit and identity still apply. Inspect these sources separately:

- `saas_jobs`: owner-filtered state, attempt count, result and safe error code.
- `saas_outbox`: durable acceptance versus acknowledged publication.
- OCI Queue/DLQ metrics: delivery backlog and transport failures.
- OCI Container Instance state/work requests: runtime failures.

For a dead job, diagnose and fix the cause before preparing a replay. The exact
reviewed plan must identify its environment, DB target, job ID, current dead state,
expected replay count and evidence digest. `replayDeadJob` compares that scope,
keeps the original ID, records an audit row and republishes from the outbox. It
cannot replay another environment or repeatedly consume the same approval state.
It does not blindly drain a DLQ. External actions require provider-side idempotency
or reconciliation even when the database job is deduplicated.

## Schedules

The initial reference supports UTC hourly-or-less-frequent intervals. Each schedule
has environment, owner, ID, version, UTC anchor, period, cursor and explicit enabled
flag. The worker derives the latest due occurrence from the durable cursor, emits
one summary job, records `(environment, schedule, version, dueAt)` uniquely and
reports the count of skipped intermediate occurrences. All happen in one DB
transaction. Clock regression does not replay a completed occurrence. Changing
version/period/anchor requires a reviewed data change and a deliberate cursor
transition; it is not a runtime edit.

The reference worker can check its own cursor once per minute only after ownership
is explicitly activated. During a hosting migration, keep the existing scheduler.
The optional native path is Resource Scheduler → enqueue Function → Queue wakeup.
Only pure enqueue/wakeup logic is available under `experimental/`; no Function or
Resource Scheduler deployment resources are enabled. Its pinned provider/image
contract, function packaging, scoped invocation and live evidence remain blockers.
A detached invocation's HTTP 202 is not enqueue or processing completion. Never
weaken digest checks, create a tag silently or grant broad Functions permissions
to make this experiment appear supported.

## Release and recovery acceptance

Before promotion, record web/worker source revisions and exact image digests,
component environment hashes, Queue/DB target, deployment receipts and previous
accepted artifacts. Verify the actual OCI images, HTTPS, hosted sign-in,
two-user isolation, private upload/download, durable processing, schedule ownership
and a private negative-access test for the other environment. Rehearse worker
crash/redelivery and interrupted transfer. Restore the database into an isolated
target and prove inbox/outbox/ledger/cursor consistency there. Restored targets
start **paused**; never attach a restored copy to the live queue or external
providers. Rollback needs a new exact plan for the previous component digest and
compatibility with the current database schema.

Report the web/worker instances, Queue, retained DLQ messages, state versions,
registry images, database/storage and migration overlap separately. Missing billing
reads mean unknown cost, never zero. Budget alerts do not cap spending. Cleanup of
these retained resources and data needs its own exact reviewed operation.
