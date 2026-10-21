# The `migration-assessment.md` deliverable

Readable in ten minutes by an engineering lead and an executive. Attach the
scanner's report rather than re-typing its tables.

## Sections, in order

1. **Verdict.** Migrate now, migrate in waves, partially migrate, or not now,
   with the two or three facts that decide it.
2. **What runs today.** Source clouds, environments, workloads, data volumes;
   anything created outside code.
3. **How it maps to OCI.** Counts by fit; the services that need decisions.
4. **Decisions needed.** One line per partial fit or gap: the choice, the
   owner, the date it is needed by.
5. **Strategy per workload.** Rehost, replatform, refactor, retain or retire.
6. **First wave.** The workload, why it is first, what it proves.
7. **Data.** Sizes, method per store, downtime per workload.
8. **Effort signal and risks.** The S to XL signal with its method; the top
   five risks with owners.
9. **Cost and value.** A link to the `founder-value` model, or "not yet
   priced".
10. **Next steps.** Each with an owner and an authorization level.
11. **Evidence.** Scan date and repository revision, service map date, which
    facts are `stated` or `assumed`.

## Skeleton

```markdown
# Migration assessment: <system> to OCI

**Verdict: <migrate now | in waves | partially | not now>.** <one sentence with the deciding facts>

## What runs today
## How it maps to OCI
## Decisions needed
| Decision | Options | Owner | Needed by |
## Strategy per workload
| Workload | Strategy | Why |
## First wave
## Data
| Store | Size | Method | Downtime |
## Effort signal and risks
## Cost and value
## Next steps
## Evidence
```
