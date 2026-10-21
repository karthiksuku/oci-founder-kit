# Reading the model's results

Read the report in this order. Each step can change what you tell the founder.

1. **Status.** INCOMPLETE means some lines are unpriced and left out. Name
   them before any other number, and do not present totals as a full estimate.
2. **Durable gross margin change.** The list-price comparison, which survives
   the end of credits. If it is negative, OCI is more expensive for this
   footprint and the case rests on other drivers.
3. **Payback without credits.** If it is outside 12 months or outside the
   runway, the migration does not pay for itself; credits can fund a pilot,
   not justify the move.
4. **Credit cliff.** The month credits stop and the monthly cash jump that
   follows. Check that the founder's plan funds it.
5. **Credits expiring unused.** Suggest work that would otherwise cost cash:
   migration rehearsal, load tests, AI evaluations, a staging environment.
6. **Cash kept as months of runway.** The founder's currency is time. Small
   numbers here are normal; margin is usually the bigger prize.
7. **Largest drivers.** Where to optimise first on either cloud. An `assumed`
   line among the top drivers is the next thing to confirm.

## Formulas, for checking by hand

```text
customers(m)        = customers_start x (1 + growth)^(m - 1)
revenue(m)          = customers(m) x ARPA
bill_list(m)        = sum(priced lines) + AI cost
credits_applied(m)  = min(credits remaining, bill_list(m)) while in window
cloud_cash(m)       = bill_list(m) - credits_applied(m)
migration_cash(m)   = one-time cost in start month + baseline bill while dual running
durable_GM(m)       = (revenue - bill_list - other COGS) / revenue
cash_GM(m)          = (revenue - cloud_cash - other COGS) / revenue
net_burn(m)         = opex + cloud_cash + other COGS + migration_cash - revenue
runway              = months before cash first goes below zero
cash kept           = sum over months of (baseline cash cost - option cash cost)
runway equivalent   = cash kept / baseline average net burn (burning months only)
payback month       = first month cumulative cash kept is >= 0 and stays so
```

## Wording the result

- "At list price, OCI improves gross margin by X points" is a fair sentence
  when the inputs are mostly `stated` and `sourced`.
- "OCI extends runway by N months" is only fair when the payback without
  credits is inside the horizon. Otherwise say "credits fund N months of
  cloud cost".
- Round to the precision of the inputs. An invoice-based comparison does not
  support cents.
