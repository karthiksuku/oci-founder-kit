# `investor-brief.md` template

Replace every angle-bracket field from the model or the founder. Delete a
section rather than filling it with generic text.

```markdown
# Infrastructure and AI cost: <company>, <month year>

<If INCOMPLETE: "Status: incomplete. <n> cost lines are not yet priced: <ids>.">

## The decision
We are <moving workload X to OCI | building on OCI | piloting Y on OCI | staying on our current cloud>.
At list price this changes durable gross margin from <a>% to <b>% (<+/-c> points) by <month>,
and the move pays back in month <p> without credits.

## Gross margin bridge (durable, list price)
| Step | Points |
|---|---:|
| Current durable gross margin | <a>% |
| Compute and memory | <+/-x> |
| Network egress | <+/-x> |
| AI model cost | <+/-x> |
| Other lines | <+/-x> |
| Durable gross margin on OCI | <b>% |

## Credits
<amount> of credits, available from <month> for 12 months, cover cloud cost until month <cliff - 1>.
From month <cliff> cash cloud cost is <amount> a month, which the plan funds from <source>.
Durable figures above exclude credits. <If any: "<amount> would expire unused; we are using it for <work>.">

## Cost and payback
| | With credits | Without credits |
|---|---:|---:|
| Migration and dual running | <amount> | <amount> |
| Payback month | <m> | <m> |
| Cash kept over <h> months | <amount> | <amount> |

## Risks
| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|

## What would change this
<the one or two conditions that would reverse the decision>

## Appendix: inputs
Scenario <file>, price list updated <date>, checked <date>. Assumed inputs still to confirm: <list>.
```
