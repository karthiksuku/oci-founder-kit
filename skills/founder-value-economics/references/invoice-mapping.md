# Mapping a cloud invoice to scenario lines

Work from a monthly billing export where possible; a PDF invoice total hides
the lines that matter. Use one recent, typical month and note anything
unusual in it (a one-off migration, a load test, a spike).

## Steps

1. Group charges into the categories below. Keep the founder's own numbers;
   mark them `stated` (or `measured` when taken straight from a billing
   export you read in this task).
2. Split each category into a `fixed` part and a `per_customer` part when the
   founder can say what grows with accounts. If they cannot, keep it `fixed`
   and note that the model will understate growth.
3. Record credits and discounts on the current bill separately, as `credits`
   on the `current` option, with their expiry.
4. List anything left over as its own line rather than dropping it.

## Categories

| Category | Typical invoice lines | Notes for the OCI side |
|---|---|---|
| Compute | Virtual machines, containers, serverless compute time | Size from CPU and memory utilization; CPU and memory are separate meters on flexible shapes |
| Database | Managed relational database, read replicas, IOPS, backups | Keep the same engine unless there is a reason to change; replicas count |
| Object storage | Storage per GB-month, requests, retrieval | Use average stored GB, not peak |
| Network | Internet egress, inter-region transfer, NAT, public IPs | Note where traffic originates; the OCI paid rate depends on region group |
| Load balancing | Load balancer hours, capacity units | Price base hours and bandwidth separately |
| Logs and monitoring | Log ingestion and storage, metrics, traces | Third-party tools often stay; keep them on both sides |
| AI | Model API spend, per token | Move to `ai_usage` and option `ai` prices instead of a line |
| Support | Support plan percentage or fee | Compare the support level the founder actually needs |
| Everything else | Marketplace software, DNS, email delivery | Keep as-is on both sides unless it changes |

## When the founder only has a total

Model a single line: `{"id": "bill", "amount": <total>, "evidence": "stated"}`.
Say that the comparison is directional and that a line-level export would
change it. Do not invent a split.
