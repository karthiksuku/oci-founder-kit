---
name: founder-value-brief
description: Turn a startup's OCI value case and model results into a board or investor brief - the infrastructure decision in one page, a gross margin bridge, honest treatment of credits and the credit cliff, a risk register, and answers to the diligence questions investors ask about cloud and AI costs. Use when a founder needs a board update, an investor memo or data-room note, or a slide's worth of content on their cloud and AI cost strategy. Builds on founder-value outputs; never fabricates metrics.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.2.0"
---

# Board and investor brief

Investors and boards ask the same things about infrastructure: what it does
to gross margin, whether the numbers depend on credits, what happens when
the credits end, and what could go wrong. This skill answers those questions
from the founder's own model, in their voice, in a page.

## Inputs

- A `value_model.py` report or JSON result, and the scenario behind it.
- The verdict and risks from a `founder-value` value case, if one exists.
- The audience: board update, investor memo, data-room note or a slide.

If there is no model yet, say so and run `founder-value` first. Do not write
a brief from adjectives.

## Deliverable: `investor-brief.md`

Follow [references/brief-template.md](references/brief-template.md):

1. **The decision in one paragraph.** What the company is doing about
   infrastructure and why, with the deciding number.
2. **Gross margin bridge.** Current durable margin, each driver's
   contribution in points, the resulting margin. Use
   [references/margin-bridge.md](references/margin-bridge.md).
3. **Credits, stated plainly.** What credits cover, when they end, the cash
   jump at the cliff, and that durable numbers exclude them.
4. **Cost and payback.** Migration cost, dual running, payback with and
   without credits.
5. **Risk register.** Risk, likelihood, impact, mitigation, owner.
6. **Questions investors will ask**, answered from the model:
   [references/diligence-questions.md](references/diligence-questions.md).

## Rules

- Every number comes from the model or the founder and carries its evidence
  class in the appendix. If the model is INCOMPLETE, the brief says so on
  page one.
- Lead with durable, list-price margin. Credit-adjusted figures are labelled
  as temporary wherever they appear.
- No forward-looking promises. "The model shows" and "we expect", not "will".
- No Oracle logos and no partnership or endorsement wording unless the
  founder has Oracle's written authorization; describe the company as
  running on OCI, which is a factual statement.
- No competitor disparagement. Compare on the founder's own costs.
- Keep it to what the audience reads: one page for a board update, two for a
  memo.

## Finish with

The brief, a list of the inputs it relies on that are still `assumed`, and
the question a sceptical investor is most likely to ask next.
