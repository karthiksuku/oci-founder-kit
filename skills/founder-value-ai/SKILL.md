---
name: founder-value-ai
description: Work out the unit economics of a startup's AI features on Oracle Cloud Infrastructure (OCI) Generative AI - cost per AI action, AI cost per customer and per plan, gross margin after AI, model tiering, cached input, and on-demand versus dedicated capacity - and gate any model change behind a quality evaluation. Use when a founder asks what an AI feature costs per user, how to price or cap it, whether a cheaper model would protect margin, or whether moving model calls to OCI is worth it. Uses the founder-value skill's calculator and price lookup.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.3.1"
---

# AI unit economics for founders

For an AI product, the model bill often decides gross margin more than the
servers do. This skill turns token counts into cost per action, cost per
customer and margin per plan, then checks whether a different model or
capacity type on OCI changes the answer without breaking quality.

## Workflow

1. **Measure usage.** Actions per customer per month, input tokens, output
   tokens and the cached share of input, from the product's own logs. If the
   product does not log tokens yet, the first next step is to add that
   logging; estimates from prompt length are `assumed`.
2. **Price the current model** from the founder's provider invoice
   (`stated`).
3. **Find OCI candidates** with the price lookup. Prefer models priced per
   1,000,000 tokens; the lookup refuses to auto-fill other metrics.
   ```bash
   cd ../founder-value
   python3 scripts/price_lookup.py search "Generative AI" --currency USD
   ```
4. **Model each candidate as its own option** in one scenario (for example
   `current`, `oci_large`, `oci_small`) with `ai.input_part`,
   `ai.cached_input_part` and `ai.output_part`, then run `fill` and
   `value_model.py`. The report gives cost per action and margin for each.
5. **Check the formulas** and the tiering, dedicated and pricing questions
   in [references/ai-cost-model.md](references/ai-cost-model.md).
6. **Gate the saving** with [references/eval-gate.md](references/eval-gate.md).
   Until a candidate passes, its saving is a hypothesis and the verdict is
   at most Pilot.

## What to report

| Number | Use |
|---|---|
| Cost per action, by model | The unit the product team can act on |
| AI cost per customer per month | Compare with ARPA |
| AI share of ARPA | The margin risk; the founder sets the ceiling they accept |
| Gross margin after AI, per plan | Shows which plans lose money on heavy users |
| Heavy-user cost (p90 or p95 of actions) | Sets fair-use caps or usage pricing |
| Dedicated breakeven | Monthly actions above which dedicated capacity is cheaper, if throughput is confirmed |

## Rules

- A cheaper model is not a saving until it passes the founder's own
  evaluation on the founder's own tasks.
- Do not convert prices per character or per transaction into per-token
  prices by rule of thumb. Measure, or leave the line unpriced.
- Do not assume dedicated capacity throughput. Ask for the measured or
  documented throughput of the specific model and unit before computing a
  breakeven.
- Check that a model is offered in the region the founder needs before
  recommending it; model availability differs by region.
- Keep provider credentials out of prompts, files and reports. Calls from a
  browser should go through the founder's server, not carry OCI keys.

## Finish with

Cost per action today and with the best candidate, AI share of ARPA, the plan
or user segment at risk, the evaluation still needed, and one next step.
