# The business value of the Founder Value Kit

Written for two readers: founders deciding where to build, and the Oracle
startup, partner and field teams who work with them. Every number below is
either from the [illustrative worked example](../examples/seed-ai-saas/README.md)
or from a dated source in [the facts file](../skills/founder-value/references/facts.md).
No customer results are claimed, because none have been measured yet.

## The problem it solves

A founder decides where to build in the first weeks of a company, usually on
the strength of credits and familiarity. The cost of that decision shows up a
year later: in gross margin when investors start asking, in the month the
credits end, and in the AI bill once usage grows. By then moving is
expensive.

OCI rarely loses that early decision on price. It loses on uncertainty: the
founder cannot see what it would be worth, cannot price it in an afternoon,
and does not know whether Oracle can help them sell. The
[Founder Toolkit for OCI](https://github.com/danielgandolfi1984/oracle_founder_pack)
removes the technical uncertainty: how to map services, set up an account and
deploy safely. This kit removes the commercial uncertainty: whether it pays,
by how much, and how to make the case to a co-founder, a board and Oracle.

## Value to a founder

| Founder question | What the kit produces | In the worked example |
|---|---|---|
| Does it improve our margin? | Durable (list-price) gross margin for each option and a bridge by cost group | +7.9 points in month 1, +4.1 points in month 24 |
| What does a customer cost to serve? | Cloud cost per customer over time | USD 39 versus USD 14 per customer in month 24 |
| Does the move pay for itself? | Payback with and without credits, including migration hours and dual running | Month 10 with credits, month 15 without |
| What happens when credits end? | The credit cliff month and the monthly cash jump; credits that would expire unused | Month 13, USD 0 to USD 1,618 a month; USD 7,978 unused |
| What is the saving worth in time? | Cash kept, expressed as months of the founder's own burn | About 1.2 months of runway over 24 months |
| What does our AI feature really cost? | Cost per action, AI share of ARPA, heavy-user cost, an evaluation gate | USD 0.01476 versus USD 0.00399 per action, pending an evaluation |
| Can Oracle help us sell? | A fit check against the Startup Growth Engine's published criteria and a five-stage readiness review | Not part of the numeric example |
| What do we tell investors? | A one-page brief with a margin bridge, credits stated plainly and a risk register | Generated from the same model |

Three things make these numbers useful rather than decorative.

1. **They survive diligence.** The headline is always the list-price result,
   so a margin story does not collapse when an investor asks "and without
   credits?". The example shows why this matters: with credits the move pays
   back in month 10; without them, month 15.
2. **They are dated and sourced.** OCI prices come from Oracle's public price
   list with the part number, metric and date. A reader can recheck any line.
3. **They say no.** The verdict rules return "Not now" when payback falls
   outside the runway or durable margin gets worse. A tool that only ever
   says yes would not be trusted with the decision.

### Where the value usually comes from

The kit does not assume any of these apply; it checks each against the
founder's own bill.

- **AI model cost.** For AI products, the model bill often outweighs the
  servers. OCI Generative AI offers models from several providers on one
  bill, priced per token for many models. In the example, AI is the largest
  single margin driver (+2.2 points of the +4.1).
- **Compute sized to need.** CPU and memory are billed separately on flexible
  shapes, so a memory-light service does not pay for unused memory.
- **Egress.** The first 10 TB of internet egress each month is not charged,
  and data movement within a region is free. For media, download or
  API-heavy products this can be a visible share of the bill.
- **Fewer services.** One database for relational, JSON and vector data can
  replace a separate vector store, which is engineering time as much as money.
- **A route to enterprise buyers.** For selected companies with commercially
  ready products, the Startup Growth Engine includes Oracle Cloud Marketplace
  readiness and joint go-to-market where there is mutual fit. This is at
  Oracle's discretion and is never counted as revenue by the kit.

## Value to Oracle and the startup ecosystem

These are hypotheses to test, with the metric that would confirm each one.

| Hypothesis | Why it should hold | Metric to watch |
|---|---|---|
| Better Startup Growth Engine applications | Oracle reviews the proposed workload, commercial readiness and growth opportunity. The kit's value case quantifies all three before the founder applies | Share of applications with a quantified workload; time to assess an application |
| Credits spent on durable work | The model shows credits that would expire unused and points them at migration rehearsal, load tests and AI evaluation | Credit utilization before expiry |
| Fewer surprises at month 13 | The credit cliff and its cash jump are in the plan from day one, so the move to pay-as-you-go is budgeted rather than discovered | Share of credit-funded tenancies still active and paying three months after credits end |
| Earlier AI consumption | AI unit economics are worked out when the founder is choosing a model, not after launch | Time from first value case to first Generative AI usage |
| Marketplace listings that are ready | The five-stage readiness review closes packaging, support and legal gaps before a listing is reviewed | Listings published without rework |
| Less spreadsheet work in the field | A first value case comes from a working session with the founder rather than a custom model built afterwards | Time from first meeting to a value case the founder accepts |

None of these has a measured baseline yet. Set the baseline before rolling
the kit out, then compare.

## How to measure it with founders

| Measure | Definition | Source |
|---|---|---|
| Time to verdict | Minutes from the first prompt to a verdict with deciding numbers | Session notes |
| Verdict accepted | The founder agrees the verdict reflects their situation | Founder feedback |
| Estimate accuracy | First three months of OCI billing against the model, by line | Billing export versus scenario |
| Decision follow-through | A pilot started, an application submitted or a decision not to move, within 30 days | Founder follow-up |
| Credit cliff readiness | The cliff month's cost is in the founder's financial plan | Founder plan |

Estimate accuracy is the one that keeps the kit honest: if the model is
consistently wrong on a line, fix the sizing guidance or the scenario
template.

## What the kit does not claim

- It does not claim OCI is cheaper for every workload; the example's
  baseline is an illustrative invoice, not a measured competitor price.
- It does not promise credits, acceptance, introductions, co-selling or
  Marketplace publication. All of these are at Oracle's discretion.
- It does not count a cheaper AI model as a saving until it passes the
  founder's own quality evaluation.
- It is not a quote. List prices exclude discounts, commitments, taxes and
  support terms.
- It is not tax, accounting, legal or investment advice.

## How it relates to the Founder Toolkit for OCI

| | Founder Toolkit for OCI | Founder Value Kit |
|---|---|---|
| Core question | How do I move this backend to OCI safely? | Is it worth it, by how much, and how do I make the case? |
| Primary reader | Technical founder, backend engineer | Founder, CEO, board, Oracle startup teams |
| Output | Architecture plan, account setup, deployment gates | Verdict, value case, model report, application draft, board brief |
| Prices | Cost drivers kept unpriced by design | Priced from the public list with dates; unknowns marked |
| Executable parts | Container API blueprint, local backend lab | Value calculator, price list lookup |
| Hand-off | Planning to deployment | Value case to [oci-kit](../skills/oci-kit/SKILL.md) for the technical plan |
