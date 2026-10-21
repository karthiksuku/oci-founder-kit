# Founder value model: Illustrative seed-stage AI SaaS (not a real company)

Currency USD, horizon 24 months, inputs as of 2026-10-21.

## OCI compared with Current cloud

| Measure | Current cloud | OCI |
|---|---:|---:|
| Cloud bill at list, month 1 | USD 3,174 | USD 1,285 |
| Durable gross margin, month 1 | 82.6% | 90.5% |
| Cash gross margin, month 1 | 82.6% | 95.8% |
| Cloud bill at list, month 24 | USD 5,962 | USD 2,211 |
| Cloud cost per customer, month 24 | USD 39 | USD 14 |
| Durable gross margin, month 24 | 89.3% | 93.4% |
| Cash gross margin, month 24 | 89.3% | 93.4% |
| Runway | beyond 24 months | beyond 24 months |
| Cash at month 24 | USD 126,064 | USD 173,320 |
| AI cost per action | USD 0.01476 | USD 0.00399 |

- Durable gross margin change: +7.9 points in month 1, +4.1 points in month 24.
- Cash kept over the horizon is worth 1.2 months of the baseline's average net burn.
- Payback: month 10 with credits; month 15 without credits.
- Cumulative cash difference over 24 months: USD 47,256 (USD 30,235 without credits). Positive means the option keeps more cash.
- Durable monthly saving at month 24: USD 3,750 at list price. Negative means the option costs more once credits are gone.

Durable gross margin bridge, month 24 (points, positive favours OCI):

| Cost group | Points |
|---|---:|
| ai | +2.2 |
| compute | +1.0 |
| network | +0.6 |
| database | +0.3 |
| observability | +0.1 |
| storage | 0.0 |

## Credits and the credit cliff

- **OCI:** USD 25,000 granted, USD 17,022 used, USD 7,978 expired unused. Credit cliff in month 13: cash cloud cost goes from USD 0 to USD 1,618 a month.

## Largest cost drivers over 24 months

- **Current cloud:** `ai` USD 36,002, `compute_base` USD 14,880, `compute_per_customer` USD 14,228
- **OCI:** `ai` USD 9,732, `apm_vendor` USD 7,200, `postgres_ocpu` USD 7,000

## Selected months

**Current cloud**

| Month | Customers | Revenue | Cloud at list | Credits used | Cloud cash | Durable GM | Cash end |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 40 | USD 24,000 | USD 3,174 | USD 0 | USD 3,174 | 82.6% | USD 1,034,826 |
| 3 | 45 | USD 26,966 | USD 3,297 | USD 0 | USD 3,297 | 83.6% | USD 908,518 |
| 6 | 54 | USD 32,117 | USD 3,509 | USD 0 | USD 3,509 | 84.9% | USD 730,421 |
| 12 | 76 | USD 45,559 | USD 4,062 | USD 0 | USD 4,062 | 86.9% | USD 425,101 |
| 13 | 80 | USD 48,293 | USD 4,175 | USD 0 | USD 4,175 | 87.2% | USD 382,207 |
| 18 | 108 | USD 64,627 | USD 4,848 | USD 0 | USD 4,848 | 88.3% | USD 210,932 |
| 24 | 153 | USD 91,674 | USD 5,962 | USD 0 | USD 5,962 | 89.3% | USD 126,064 |

**OCI**

| Month | Customers | Revenue | Cloud at list | Credits used | Cloud cash | Durable GM | Cash end |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 40 | USD 24,000 | USD 1,285 | USD 1,285 | USD 0 | 90.5% | USD 1,008,426 |
| 3 | 45 | USD 26,966 | USD 1,326 | USD 1,326 | USD 0 | 90.9% | USD 885,415 |
| 6 | 54 | USD 32,117 | USD 1,396 | USD 1,396 | USD 0 | 91.5% | USD 717,624 |
| 12 | 76 | USD 45,559 | USD 1,580 | USD 1,580 | USD 0 | 92.4% | USD 435,200 |
| 13 | 80 | USD 48,293 | USD 1,618 | USD 0 | USD 1,618 | 92.5% | USD 394,863 |
| 18 | 108 | USD 64,627 | USD 1,841 | USD 0 | USD 1,841 | 93.0% | USD 237,672 |
| 24 | 153 | USD 91,674 | USD 2,211 | USD 0 | USD 2,211 | 93.4% | USD 173,320 |

## Evidence behind the inputs

Cost lines by evidence class: assumed 1, sourced 13, stated 8.

Confirm these assumed lines before using the result in a decision: `oci.apm_vendor`.

- Illustrative inputs only. Replace every 'stated' value with your own invoice and every 'assumed' value with a measured or agreed number.
- The current-cloud lines are a founder-stated invoice for a comparable footprint, not a measured price from any provider.
- OCI prices come from Oracle's public PAY_AS_YOU_GO list (744 billable hours a month, the convention in Oracle's cost estimator). They exclude discounts, commitments, taxes and support.
- The OCI AI line assumes a different model from the current provider. Run a quality evaluation before treating the saving as real.
- Credits of USD 25,000 are an assumption inside the published Startup Growth Engine range. Award, amount and timing are at Oracle's discretion.

Method: list-price bills per month, credits applied to the bill until spent or expired, migration and dual running charged as cash, runway counted in fully funded months. Durable margin ignores credits. This is a planning model, not a quote or financial advice.
