# What code cannot show

Ask only what changes the plan. Group the questions and accept ranges.

## Data

| Question | Why |
|---|---|
| Size of each database, and its growth per month | Chooses the migration method and cutover window |
| Object storage volume in TB, and number of objects | Transfer time and method |
| Acceptable downtime for the cutover, per workload | Dump and restore, or replication |
| Recovery point and recovery time objectives | Backup and standby design on OCI |
| Data residency or sovereignty requirements | Region choice; some services are not in every region |

## Traffic and operations

| Question | Why |
|---|---|
| Peak requests per second and monthly egress in GB | Sizing and the egress line of the cost model |
| Where users are | Region and latency |
| Who is on call, and the current runbooks | Operational readiness on OCI |
| CI/CD system and how deploys happen | Pipeline changes |

## Identity and integrations

| Question | Why |
|---|---|
| Identity provider for users and for staff | Sign-in migration and single sign-on |
| Third-party services called from the app (payments, email, search, analytics) | Network allow-lists and egress |
| Partners that allow-list your current IP addresses | Outbound IP changes on OCI |
| DNS registrar and who controls it | Cutover |

## Commercial

| Question | Why |
|---|---|
| Reserved capacity, savings plans or committed-spend agreements with the current provider, and their end dates | Timing: moving before a commitment ends can cost more |
| Credits on the current provider and their expiry | Fair comparison in `founder-value-economics` |
| Contracts that name the current provider or region | Legal review before moving data |

## Things that are often missed

- Resources created by hand in a console.
- Scheduled jobs on someone's laptop or a forgotten VM.
- Secrets that only exist in a CI system.
- Email sending reputation (sender domains, warm-up).
