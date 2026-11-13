---
name: founder-value
description: Build the business case for running a startup on Oracle Cloud Infrastructure (OCI) - what it is worth in gross margin, runway, AI unit cost and revenue access, what moving costs, and whether to go now, pilot or wait. Use when a founder asks whether OCI is worth it, wants a cloud cost or margin comparison, a value case, a credits or Oracle Startup Growth Engine decision, or numbers for a board. Hands AI cost work to founder-value-ai, Oracle go-to-market to founder-value-gtm, investor material to founder-value-brief, and technical implementation to oci-kit.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.3.0"
---

# Founder Value Kit for OCI

Give a founder a defensible answer to three questions:

1. What is OCI worth to this company, in margin, runway and revenue?
2. What does it cost to get there, including the founder's time?
3. What should we do next: go, pilot one workload, or not now?

The answer is a verdict with the two or three numbers that decide it and the
conditions that would reverse it. It is not a brochure. Say plainly when OCI
is the wrong choice.

This kit is an independent project. It is not an Oracle product and is not
sponsored, endorsed or supported by Oracle.

## Pick the mode first

| Mode | Use when | Deliverable | Boundary |
|---|---|---|---|
| Answer | A focused question ("do credits help our margin?") | A direct answer in a few paragraphs | No files |
| Value check | "Is OCI worth it for us?" with few facts | Verdict, the deciding numbers or the facts still missing, one next step | No files unless asked |
| Model | The founder shares a bill, metrics or asks for numbers | `scenario.json` and a report from `scripts/value_model.py` | Write only those files, where the founder says |
| Value case | The founder asks for the full business case | `value-case.md` following [references/value-case.md](references/value-case.md) | Same as Model |
| Route | AI economics, Oracle go-to-market, investor material, technical migration | Hand to the companion skill | Carry every constraint across |

Stay in the lightest mode that answers the question. A value check does not
need a full value case, and a question about credits does not need a model.

Never apply to a program, contact Oracle or anyone else, accept terms, sign
up for an account or send material on the founder's behalf. Draft; the
founder acts.

## Workflow

1. **Name the decision.** Where to build a new product, whether to migrate,
   whether to apply to the Startup Growth Engine, or how to price an AI
   feature. The decision sets which numbers matter.
2. **Collect the minimum facts** in [references/discovery.md](references/discovery.md).
   If a repository is present, read it (read-only) for runtime, database,
   storage, AI calls and egress-heavy features. Ask only for what the code and
   the founder's bill cannot tell you.
3. **Choose two to four value drivers** from
   [references/value-drivers.md](references/value-drivers.md). Do not walk the
   founder through all six. Include the counterweights that apply.
4. **Price it.** Copy [assets/scenario.template.json](assets/scenario.template.json),
   fill current-cloud lines from the founder's invoice (`stated`), give OCI
   lines a `part_number`, then run `scripts/price_lookup.py fill`. Schema:
   [references/scenario-schema.md](references/scenario-schema.md). Never type
   a price from memory. Include credits and discounts the founder already has
   on the current cloud; leaving them out flatters OCI.
5. **Run the model** with `scripts/value_model.py` and read it in this order:
   unpriced lines, durable gross margin change, payback without credits,
   credit cliff, cash kept as months of runway, largest drivers.
6. **Give the verdict** using the rules below.
7. **End with one next action**, its owner, and its authorization level.

```bash
python3 scripts/price_lookup.py search "E5 - OCPU" --currency USD
python3 scripts/price_lookup.py fill scenario.json --out scenario.priced.json
python3 scripts/value_model.py scenario.priced.json --out value-report.md
python3 scripts/value_model.py scenario.priced.json --format json --strict
```

Paths are relative to this skill's directory. The scripts use the Python
standard library only. If the price list API is unreachable, keep the lines
unpriced and say so; the report will be marked INCOMPLETE.

## Verdict rules

Default thresholds. The founder may change them; state the ones you used.

- **Go** when payback *without credits* falls inside 12 months and inside the
  remaining runway minus six months, durable gross margin does not get worse,
  the migration fits the next quarter's roadmap, and no must-have requirement
  is unresolved.
- **Pilot** when the value rests on one unproven assumption: an AI model's
  quality, a performance target, a service the product needs, or a credit
  award. Propose one bounded experiment with a success threshold, a stop date
  and a cost ceiling. Use credits for it if they exist.
- **Not now** when payback without credits falls outside the runway, durable
  margin gets worse, the move would compete with a launch or fundraise in the
  next 90 days, or a must-have is missing. Say what would change the answer.
- **Build here** for a greenfield product: there is no migration cost, so
  decide on durable margin, AI unit cost, the services the product needs and
  go-to-market fit.

A payback that only works because of credits is a Pilot at best.

## Rules that keep the case honest

- Credits are cash relief with an expiry date, not margin. Report durable
  (list-price) results next to credit-adjusted ones, and always report the
  credit cliff.
- Compare like with like: the same footprint, availability and support level.
- An unpriced line is unknown, never zero.
- List prices are not quotes. Discounts and commitments are negotiated; do not
  assume them.
- Startup Growth Engine acceptance, credit amounts, customer introductions,
  co-selling and Marketplace publication are all at Oracle's discretion. Never
  present them as likely or promised. Facts and dates:
  [references/facts.md](references/facts.md).
- A cheaper AI model is only a saving after it passes the founder's own
  quality evaluation.
- Do not invent customer stories, benchmarks, competitor prices or quotes from
  Oracle staff. Current-cloud costs come from the founder.
- This is planning, not tax, accounting, legal or investment advice. Point to
  an accountant for capitalising migration work or treating credits.

## Evidence classes

Label every input and every claim in a deliverable.

| Class | Meaning |
|---|---|
| `measured` | From the founder's monitoring, billing export or a test run in this task |
| `stated` | Told by the founder, not checked |
| `sourced` | From a dated public source, such as the price list API |
| `assumed` | A working guess that must be confirmed before a decision |

Present a number whose inputs are mostly `assumed` as a range or a question,
not as a result.

## Reference routing

| Need | Read |
|---|---|
| What to ask, by company stage, and what to read from a repository | [references/discovery.md](references/discovery.md) |
| The six value drivers, their formulas and their counterweights | [references/value-drivers.md](references/value-drivers.md) |
| The full `value-case.md` deliverable | [references/value-case.md](references/value-case.md) |
| Scenario JSON fields and examples | [references/scenario-schema.md](references/scenario-schema.md) |
| Startup Growth Engine terms, egress, price list behaviour, compute units | [references/facts.md](references/facts.md) |

## Companion skills

Use these when installed; if one is missing, say so and stay at the level of
detail this skill supports.

| Need | Skill |
|---|---|
| Cost per AI action, model choice, dedicated versus on-demand, AI margin by plan | `founder-value-ai` |
| Invoice mapping, sizing, sensitivity ranges, cost per customer | `founder-value-economics` |
| Startup Growth Engine fit, Marketplace and enterprise-buyer readiness | `founder-value-gtm` |
| Board or investor brief, margin bridge, risk register | `founder-value-brief` |
| Architecture, account setup and migration mechanics on OCI | [oci-kit](../oci-kit/SKILL.md), which routes to the build, setup and migration workflows |

Routing never widens what the founder has authorized.

## Finish every response with

- the verdict (or "not enough facts yet" and which facts);
- the one next action, who does it, and its level: **read-only**, **local
  write** (files in the founder's folder) or **founder action** (anything
  that leaves the machine, such as an application, an email or a purchase).
