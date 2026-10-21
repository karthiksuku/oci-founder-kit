# Dated facts and their sources

Every time-sensitive claim this kit relies on is listed here with the date it
was checked. Re-check a fact before using it in a decision when it is more
than 30 days old, when a founder is in a different country, or when money is
about to be committed. If a source has changed, the source wins and this file
is out of date.

Last full check: **2026-10-21**.

## Oracle Startup Growth Engine

Source: program page and terms, checked 2026-10-21.
<https://www.oracle.com/de/artificial-intelligence/startup-growth-engine/> and
<https://www.oracle.com/de/artificial-intelligence/startup-growth-engine/terms/>.
Oracle announced the expansion of Oracle PartnerNetwork with the program on
2026-10-15:
<https://www.oracle.com/il-en/news/announcement/oracle-expands-oracle-partner-network-with-startup-growth-engine-2026-10-15/>.
The release targets "high-growth, venture-backed technology companies" and
says Marketplace publication can reach "tens of thousands of Oracle customers
around the world".

| Topic | What the source says | How to use it |
|---|---|---|
| Who it is for | Startups and digital natives with a validated product, a defined workload that can be built or migrated to OCI, and room to scale | Use as a fit check, not a promise of acceptance |
| Review criteria | Oracle reviews the company, product, proposed workload, commercial readiness and growth opportunity | The value case is the evidence for "workload" and "growth opportunity" |
| Credits | Universal Credits from USD 5,000 to USD 60,000 in the terms checked | Model the low end until an award is confirmed in writing |
| Credit life | Available for 12 months from when they are made available; unused credits expire with no cash value | This is the credit cliff the model reports |
| After credits | The tenancy moves to Pay As You Go at OCI list price plus taxes | Durable margin must be calculated at list price |
| Credit use | Non-transferable, no cash value, not for resale or crypto mining | Do not plan to resell credit-funded capacity |
| Existing OCI customers | Not automatically excluded; may be included with a substantial growth case | Say "possible with a growth case", never "eligible" |
| Excluded | Public entities; applicants with regulatory, sanctions, financial-crime or reputational risk; possibly applicants with debts to Oracle | Stop the fit check if one applies |
| Extra diligence | Financial services, crypto-asset platforms, betting or gaming, prediction markets, digital exchanges | Warn about a longer review |
| Geography | Only in countries or territories Oracle designates; scope can change | Check the founder's country on the live page |
| Go to market | For selected companies with commercially ready products: positioning, Marketplace readiness, private offers where applicable, joint go-to-market and co-selling where there is mutual fit | Illustrative and at Oracle's discretion; never promise introductions |
| Other benefits named | Technical guidance from Oracle engineers, Oracle MyLearn onboarding, a no-cost one-year OPN membership for eligible companies, OCI credits or funding for technical and business assessments; customer engagement only "at certain OPN levels" | Treat as possible, not guaranteed |
| Brand use | Participants may not use Oracle's name, trademarks or logos without prior written authorization | Applies to decks, websites and press |
| Discretion | Oracle selects participants at its sole discretion and may change or end the program | Never present selection as likely |

The terms page checked is the German-site English version. Terms can differ
by country. A third-party guide quoted "up to USD 100,000"; that figure is not
in the Oracle terms checked and must not be used.

## Network pricing

Source: <https://www.oracle.com/cloud/networking/virtual-cloud-network/pricing/>,
checked 2026-10-21, and the price list API below.

- The first 10 TB of internet egress each month is not charged. In the price
  list this is the 0 to 10,240 GB tier of the outbound data transfer parts.
- Paid egress rates differ by originating region group. On 2026-10-21 the
  APAC, Japan and South America part (B93455) and the North America, Europe
  and UK part (B88327) had different paid-tier prices. Look them up; do not
  reuse one region's rate for another.
- Data movement within a region, including across availability domains, is
  not charged.

## Price list API

Source: <https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/>,
queried 2026-10-21 (`lastUpdated` 2026-10-08T14:38:16Z).

- Public, no authentication. Supports `partNumber` and `currencyCode` query
  parameters. Returns PAY_AS_YOU_GO list prices per currency.
- Tiered parts carry `rangeMin` and `rangeMax`; a very large `rangeMax` marks
  the open top tier.
- Generative AI parts are priced several ways: per 1,000,000 tokens for many
  current models, per 10,000 transactions for some older models, and per AI
  unit hour for dedicated clusters. The kit only auto-fills per-token prices.
- Oracle's cost estimator uses 744 hours for a month. State the hours you use.

Use `scripts/price_lookup.py` to read it. Do not type prices from memory.

## Compute units

Source: <https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm>.
On x86 shapes an OCPU is one physical core with two hardware threads, so it
is roughly two vCPUs on clouds that count threads. On Arm (Ampere) shapes an
OCPU is one core. Size by measured utilization, not by counting vCPUs.
CPU and memory are billed separately on flexible shapes.
