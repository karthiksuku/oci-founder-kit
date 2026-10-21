# Value drivers and counterweights

Pick the two to four drivers that matter for this company. Each one says what
it is worth, how to calculate it, what evidence it needs and where it stops
being true. The counterweights at the end apply to every case.

## 1. Gross margin from cloud cost of goods sold

**Worth:** each point of gross margin is kept on every future dollar of
revenue, which is why investors look at it before they look at the bill.

```text
cloud COGS per customer = monthly cloud bill at list price / customers
durable gross margin    = (revenue - cloud COGS at list - other COGS) / revenue
margin change (points)  = (OCI durable margin - current durable margin) x 100
```

**Evidence:** the founder's invoice split into lines (`stated` or `measured`),
OCI lines priced from the price list (`sourced`), customer count and ARPA.

**Where OCI often differs:** CPU and memory are billed separately on flexible
shapes, so over-provisioned memory is not forced on you; the first 10 TB of
internet egress each month is not charged; data movement inside a region is
not charged. Check each one for this company; do not assume they matter.

**Stops being true when:** the workload is small enough that the bill is
under a few percent of revenue (the margin gain is real but not decisive), or
when the current provider's negotiated discount is larger than the list-price
gap.

## 2. Runway

**Worth:** cash not spent on cloud buys time to reach the next milestone.

```text
cash kept over horizon = sum(baseline cash cost - option cash cost)
                         including migration and dual running
runway equivalent      = cash kept / baseline average monthly net burn
```

**Evidence:** cash on hand and monthly operating spend from the founder,
credits only when awarded in writing.

**The credit cliff:** Startup Growth Engine credits last 12 months, then the
tenancy pays list price. Report the month the cliff arrives and the monthly
cash jump, and check that the founder's plan funds it. Credits that will
expire unused are a planning signal: pull migration testing, load testing or
AI evaluation earlier so they are used on work that would otherwise cost cash.

**Stops being true when:** the payback only works with credits. Then the
honest description is "credits fund a pilot", not "OCI extends runway".

## 3. AI unit economics

**Worth:** for an AI product, model cost per action often decides gross margin
more than infrastructure does.

```text
cost per action = (input tokens x uncached share x input price
                 + input tokens x cached share x cached price
                 + output tokens x output price) / 1,000,000
AI cost per customer = cost per action x actions per customer per month
```

**Evidence:** token counts from the product's logs (`measured`), prices from
the price list (`sourced`), a quality evaluation on the founder's own tasks.

**Where OCI often differs:** OCI Generative AI offers models from several
providers on one bill, with on-demand per-token pricing for many models and
dedicated capacity priced per AI unit hour. Work through it with
`founder-value-ai`.

**Stops being true when:** the cheaper model fails the founder's quality bar,
or latency targets push the product onto a more expensive tier.

## 4. Revenue access through Oracle

**Worth:** a route to enterprise buyers who already run on Oracle, through
Oracle Cloud Marketplace and joint go-to-market for selected companies.

```text
expected pipeline value = qualified opportunities x win rate x first-year value
```

Every input here starts as `assumed`. Oracle does not guarantee introductions,
co-selling or Marketplace publication.

**Evidence:** the founder's ideal customer profile, overlap with industries
where Oracle is strong, product readiness for enterprise procurement.
Work through it with `founder-value-gtm`.

**Stops being true when:** the founder sells self-serve to small businesses or
consumers, where an enterprise channel adds little.

## 5. Enterprise deal readiness

**Worth:** shorter security reviews and fewer lost deals on data residency.

**Evidence:** the regions the founder's buyers require, the services in those
regions (check the live region list), security questionnaire answers the
founder can now give, deals lost or delayed on these grounds (`stated`).

**Measure it as:** days from first security questionnaire to signed contract,
before and after. Do not convert it to dollars without the founder's own deal
data.

**Stops being true when:** buyers do not ask about residency or the founder's
current cloud already covers the required regions.

## 6. Fewer moving parts

**Worth:** engineering time. A database that handles relational, JSON and
vector data in one service can remove a separate vector store or search
cluster, with fewer things to secure, back up and pay for.

```text
time value = hours a month saved on operations x loaded hourly rate
```

**Evidence:** the services the founder runs today and the hours they spend
on them (`stated`), a working proof on the founder's own data.

**Stops being true when:** the team depends on features of the current
service that have no tested substitute.

## Counterweights (always check)

| Counterweight | How to count it |
|---|---|
| Migration effort | Engineering hours x loaded rate, as `migration.one_time_cost` |
| Dual running | Months both clouds are billed, as `migration.dual_run_months` |
| Founder attention | Weeks the core team is not shipping product; state it in words if not in dollars |
| Skills and tooling | Training, new runbooks, CI changes; add to the one-time cost |
| Ecosystem gaps | A managed service or integration the product needs that has no tested equivalent |
| Credits elsewhere | Credits or discounts the founder already holds on the current cloud |
| Reversibility | What it would cost to move back; keep data portable where cheap |
| Program discretion | Credits and go-to-market support are not guaranteed until confirmed in writing |
