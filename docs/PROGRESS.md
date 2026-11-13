# Know what is actually done

Keep a short progress file in the application's documentation, separate from
private deployment receipts. Update it at meaningful checkpoints. The site and
prompt builder do not measure progress automatically.

Use **not started**, **in progress**, **passed**, **blocked** or **not applicable**.
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
