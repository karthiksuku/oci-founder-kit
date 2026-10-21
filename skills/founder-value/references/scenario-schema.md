# Scenario file: `founder-value-scenario/1`

One JSON file describes the business, a usage profile for AI, and two or more
options (for example `current` and `oci`). `scripts/value_model.py` validates
it and explains any error. Start from
[../assets/scenario.template.json](../assets/scenario.template.json).

## Top level

| Field | Required | Meaning |
|---|---|---|
| `schema` | yes | Always `founder-value-scenario/1` |
| `name` | no | Shown in the report title |
| `as_of` | no | Date the inputs describe, `YYYY-MM-DD` |
| `currency` | yes | Three-letter code; every amount and price uses it |
| `horizon_months` | yes | 1 to 120; 24 suits most seed and Series A decisions |
| `baseline` | no | Option key to compare against; default `current` |
| `notes` | no | List of strings printed in the report |
| `business` | yes | See below |
| `ai_usage` | no | See below; when present, every option needs `ai` prices |
| `options` | yes | Two or more options keyed by short names |

## `business`

| Field | Meaning |
|---|---|
| `customers_start` | Paying accounts in month 1 |
| `customer_growth_monthly` | Compound monthly growth, for example `0.06` |
| `arpa_monthly` | Average revenue per account per month |
| `other_cogs_per_customer_monthly` | Non-cloud cost of goods: support tools, payment fees, third-party APIs |
| `opex_monthly` | Operating spend outside cost of goods: salaries, rent, marketing |
| `cash_on_hand` | Cash at the start of month 1 |

## `ai_usage`

| Field | Meaning |
|---|---|
| `actions_per_customer_monthly` | Model calls (or user-visible AI actions) per account per month |
| `input_tokens_per_action` | Prompt plus context tokens |
| `cached_input_share` | Share of input tokens billed at the cached rate, 0 to 1 |
| `output_tokens_per_action` | Generated tokens |

## An option

| Field | Meaning |
|---|---|
| `label` | Name in the report |
| `lines` | Cost lines; see below |
| `ai` | Prices per million tokens: `input_per_mtok`, `cached_input_per_mtok` (optional; defaults to the input price), `output_per_mtok`; or part numbers `input_part`, `cached_input_part`, `output_part` for `price_lookup.py fill`; or `{"included_in_lines": true}` when AI cost is already a line |
| `credits` | `amount`, `start_month`, `valid_months`; applied to the option's bill until spent or expired |
| `migration` | Not on the baseline. `one_time_cost` (cash in `start_month`), `start_month`, `dual_run_months` (months the baseline bill is also paid) |

## A cost line

A line has **either** an `amount` (a monthly figure, typically from an
invoice) **or** a `quantity` with a `unit_price` or `tiers`.

| Field | Meaning |
|---|---|
| `id` | Unique within the option; `ai` is reserved |
| `label` | Name in the report |
| `group` | Cost group for the margin bridge, such as `compute`, `database`, `storage`, `network`, `observability`; ungrouped lines count as `other`, AI cost is always `ai` |
| `basis` | `fixed` (default) or `per_customer` (amount or quantity is per account) |
| `amount` | Monthly amount in the scenario currency |
| `quantity` | Units per month, or per hour when `hours_per_month` is set |
| `hours_per_month` | Multiplies `quantity`; Oracle's estimator uses 744 |
| `unit_price` | Price per unit; `null` means unpriced, which marks the result INCOMPLETE |
| `tiers` | `[{"from": 0, "to": 10240, "price": 0}, {"from": 10240, "to": null, "price": 0.025}]` priced on the monthly quantity |
| `part_number` | Oracle part number; `price_lookup.py fill` sets `unit_price` or `tiers`, `price_source` and `evidence: sourced` |
| `expected_metric` | Optional text the part's metric must contain; protects against a wrong part |
| `price_locked` | `true` stops `fill` from changing a negotiated price |
| `evidence` | `measured`, `stated`, `sourced` or `assumed`; missing means `assumed` |

## Example lines

```json
{"id": "compute", "label": "App servers", "amount": 620, "evidence": "stated"}
{"id": "per_seat", "basis": "per_customer", "amount": 7, "evidence": "stated"}
{"id": "ocpu", "part_number": "B97384", "expected_metric": "OCPU Per Hour",
 "quantity": 8, "hours_per_month": 744}
{"id": "egress", "part_number": "B93455", "quantity": 6000}
{"id": "db", "quantity": 1, "unit_price": null, "evidence": "assumed"}
```

## How the model counts

- Customers in month *m* = `customers_start x (1 + growth)^(m-1)`.
- The bill at list price is the sum of priced lines plus AI cost.
- Credits are applied to the bill inside their window until spent; whatever is
  left at the end of the window expires.
- Cash cloud cost = bill at list minus credits applied.
- Migration cash = one-time cost in its start month plus the baseline bill in
  each dual-running month.
- Net burn = operating spend + cash cloud cost + other COGS + migration cash
  minus revenue. Runway is the number of fully funded months.
- Payback is the first month in which cumulative cash kept, against the
  baseline, is zero or more and stays so. It is reported with and without
  credits.
