# The `value-case.md` deliverable

Produce this only when the founder asks for a full business case. Keep it to
what a founder, a co-founder and an investor would read in ten minutes.
Every number cites its evidence class and, for `sourced` numbers, its date.

## Sections, in order

1. **Verdict.** Go, Pilot, Not now or Build here, in one sentence, with the
   two or three numbers that decide it.
2. **The decision and the stakes.** What is being decided, by when, and what
   happens if nothing changes.
3. **What OCI is worth here.** The two to four value drivers chosen, each with
   its number, formula and evidence class. Durable (list-price) results first;
   credit-adjusted results second.
4. **What it costs.** Migration hours and cost, dual-running months, founder
   attention, skills and tooling. Payback with and without credits.
5. **Credits and the cliff.** Credits held or expected, the cliff month and
   the monthly cash jump, how the plan funds it, and any credits that would
   expire unused.
6. **Risks and what would reverse the verdict.** Each risk with an owner and
   a test. Include ecosystem gaps, model quality and program discretion.
7. **The next step.** One bounded action: what, who, by when, cost ceiling,
   success threshold, and its authorization level.
8. **Inputs and sources.** The scenario file, the price list date, the
   assumed lines still to confirm, and the facts file date.

## Rules

- Lead with the verdict. Do not open with a description of OCI.
- If the model is INCOMPLETE, say so in the verdict line and name the
  unpriced lines.
- Show the number that hurts the case as clearly as the ones that help it.
- No logos, no endorsements, no customer names unless the founder supplies
  them and has the right to use them.
- Attach or link the report from `scripts/value_model.py` rather than
  re-typing its tables.

## Skeleton

```markdown
# Value case: <company> on OCI

**Verdict: <Go | Pilot | Not now | Build here>.** <one sentence with the deciding numbers>

## The decision
## What OCI is worth here
| Driver | Result | Formula | Evidence |
## What it costs
## Credits and the credit cliff
## Risks and what would reverse this
| Risk | Owner | Test | Reverses the verdict if |
## Next step
## Inputs and sources
```
