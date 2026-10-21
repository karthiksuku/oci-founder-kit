# Worked example: a seed-stage AI SaaS company in APAC

**Illustrative inputs. This is not a real company.** It shows how the kit
reaches a verdict, not what any particular founder will save.

- Scenario (priced): [`scenario.example.json`](../../skills/founder-value/assets/scenario.example.json)
- Scenario (unpriced template): [`scenario.template.json`](../../skills/founder-value/assets/scenario.template.json)
- Model report: [`value-report.md`](value-report.md)

## The company

40 paying customers growing 6% a month, USD 600 average revenue per account,
USD 85,000 a month of operating spend and USD 1.1 million in the bank. Its
product has an AI assistant used about 1,200 times per customer a month, with
3,000 input tokens (40% cached) and 600 output tokens per call.

## The inputs and their evidence

| Side | Source | Evidence class |
|---|---|---|
| Current cloud | A founder-stated invoice for a comparable footprint | `stated` |
| Current AI model | Founder-stated per-token prices | `stated` |
| OCI services | Oracle public price list, `lastUpdated` 2026-10-08, checked 2026-10-21, 744 hours a month | `sourced` |
| OCI AI model | A different model on OCI Generative AI, priced per token from the same list | `sourced`, quality not yet evaluated |
| Credits | USD 25,000 for 12 months, inside the published range | `assumed` |
| Migration | 240 engineering hours at USD 110, two months of dual running | `assumed` |
| Monitoring vendor | Kept on both sides, USD 300 a month | `stated` / `assumed` |

## What the model says

- Durable gross margin rises 7.9 points in month 1 and 4.1 points by month
  24. The bridge puts 2.2 of those points on AI model cost, 1.0 on compute
  and 0.6 on network.
- The move pays back in month 10 with credits and month 15 without.
- The 12-month credit window closes before the credits are spent: USD 7,978
  of the USD 25,000 would expire unused. From month 13 the OCI bill of about
  USD 1,618 a month is paid in cash.
- Over 24 months OCI keeps USD 47,256 more cash, about 1.2 months of the
  baseline's burn. The bigger prize is margin, not runway.

## The verdict: Pilot

Payback without credits (month 15) is outside the 12-month threshold for Go,
and the largest single driver depends on a model change that has not been
evaluated. Runway is not at risk, so the answer is not "Not now".

**Next step:** run the evaluation gate in `founder-value-ai` on 100 real
assistant tasks, funded by the credits that would otherwise expire. Pass
threshold: no more than 2 points below the current model on the team's
rubric, p95 latency within the product's limit. If it passes, the AI saving
is real and the case moves towards Go; if it fails, rerun the model with the
current model's prices on OCI or keep AI where it is.

## Re-run it

```bash
cd skills/founder-value
python3 scripts/price_lookup.py fill assets/scenario.template.json --out /tmp/example.priced.json
python3 scripts/value_model.py /tmp/example.priced.json
```

Prices will move over time; the committed `scenario.example.json` keeps the
2026-10-21 prices so the report above can be reproduced offline.
