---
name: founder-value-economics
description: Turn a startup's cloud invoice and business metrics into gross margin, cloud cost per customer, runway, migration payback and the credit cliff, comparing the current cloud with Oracle Cloud Infrastructure (OCI) at list price and with credits. Use when a founder shares a bill or billing export, asks what their cloud costs per customer, how credits change runway, when a migration pays back, or wants low, expected and high cases. Requires the founder-value skill's scripts.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.2.0"
---

# Founder unit economics

Translate a cloud bill into the numbers a founder runs the company on: gross
margin, cost per customer, runway and payback. The calculator and price
lookup live in the `founder-value` skill (`../founder-value/scripts/`). If
that skill is not installed, say so, do the arithmetic by hand from the
formulas in [references/reading-results.md](references/reading-results.md),
and mark the result as unchecked.

## Workflow

1. **Map the invoice** to scenario lines with
   [references/invoice-mapping.md](references/invoice-mapping.md). Each
   invoice line becomes a `stated` amount, split into `fixed` and
   `per_customer` where the founder can say what grows with customers.
2. **Size the OCI side** from measured utilization with
   [references/sizing.md](references/sizing.md). Give each line a
   `part_number` and an `expected_metric`, then run
   `price_lookup.py fill`. Keep the same availability and environments as the
   current setup; a cheaper result that drops staging or a replica is not a
   fair comparison.
3. **Add the counterweights:** migration hours times the founder's loaded
   rate, dual-running months, and any credits or discounts on the current
   cloud.
4. **Run three cases.** Expected, low and high. Change only explicit inputs:
   customer growth, AI actions per customer, egress, migration hours. Save
   each as its own scenario file so the cases can be reproduced.
5. **Read the results** in the order in
   [references/reading-results.md](references/reading-results.md) and give
   the founder the three numbers that matter for their decision.

```bash
cd ../founder-value
python3 scripts/price_lookup.py fill /path/to/scenario.json --out /path/to/scenario.priced.json
python3 scripts/value_model.py /path/to/scenario.priced.json --out /path/to/value-report.md
```

## What to report

| Number | Why the founder cares |
|---|---|
| Durable gross margin, now and at the horizon, both options | Investors value margin; it survives the end of credits |
| Gross margin change in points | The headline for a board |
| Cloud cost per customer | Shows whether cost scales with revenue or ahead of it |
| Payback month with and without credits | Whether the move pays for itself on its own merits |
| Credit cliff month and the monthly cash jump | What the plan must fund in month 13 |
| Credits expiring unused | Work to pull forward while it is free |
| Cash kept as months of runway | Puts the saving in the founder's own currency: time |
| Largest three cost drivers | Where to look first, on either cloud |

Lead with the result that is most decision-relevant, including when it is
unfavourable to OCI.

## Rules

- Never type a price from memory. If the price list API is down, leave the
  line unpriced; the report will say INCOMPLETE.
- An invoice total is not a line breakdown. If the founder can only give a
  total, model it as one `stated` line and say the comparison is coarse.
- Do not convert vCPU counts to OCPU counts mechanically. Size from measured
  utilization and say what was measured.
- Show low and high cases as ranges, not as a single precise number.
- Do not give tax or accounting treatment for credits or migration costs;
  point to the founder's accountant.

## Finish with

The three numbers, the verdict implication for `founder-value`, the input
that most changes the answer, and the one measurement that would narrow it.
