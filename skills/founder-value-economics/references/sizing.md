# Sizing the OCI side

The aim is the same service level at the smallest footprint that meets it,
priced from the public list. Sizing errors are the most common reason a
comparison is wrong in either direction.

## Principles

- **Start from utilization, not instance names.** Average and p95 CPU,
  memory in use, storage in use and monthly egress, ideally from the last 30
  days of monitoring. Label them `measured` or `stated`.
- **Keep parity.** The same environments (production, staging), the same
  replicas and the same backup retention on both sides.
- **Count units correctly.** On x86 flexible shapes an OCPU is one physical
  core (two hardware threads). On Arm shapes it is one core. CPU and memory
  are priced separately, so size each to what the workload uses. Check the
  compute shapes documentation linked in
  [the kit's facts file](../../founder-value/references/facts.md).
- **Use 744 hours a month** for always-on resources, the convention in
  Oracle's cost estimator, and say so.
- **Price tiers on the monthly total.** Egress, object storage, logging and
  load balancer bandwidth have free or tiered bands; enter monthly quantities
  and let the part's tiers do the work.

## Finding part numbers

Run these from the `founder-value` skill directory:

```bash
python3 scripts/price_lookup.py search "E5 - OCPU"
python3 scripts/price_lookup.py search "Outbound Data Transfer"
python3 scripts/price_lookup.py search "PostgreSQL"
python3 scripts/price_lookup.py part B93455 --currency AUD
```

Set `expected_metric` on each line to a word from the part's metric (for
example `OCPU Per Hour`). `fill` refuses a part whose metric does not match,
which catches a wrong part number before it reaches a report.

## Things that are easy to miss

| Item | Why it matters |
|---|---|
| Boot and block volumes | Billed while they exist, including when an instance is stopped |
| Volume performance units | Balanced and higher performance levels add a per-GB charge |
| Database storage | Priced separately from database compute |
| Load balancer bandwidth | Separate from base hours |
| Paid egress region | Rates differ between region groups |
| Non-production environments | Often a third of the bill |

## When sizing is uncertain

Run the expected case with your best sizing and a high case with 50% more
compute and memory. If the verdict holds in the high case, the sizing
uncertainty does not matter. If it flips, a short measured test on OCI is the
next step, ideally paid for with credits.
