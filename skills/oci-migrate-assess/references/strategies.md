# Choosing a strategy per workload

Decide per workload (an app, a service, a job), not per resource.

| Strategy | Use when | Typical services |
|---|---|---|
| **Rehost** | VMs or containers that run unchanged; the goal is speed | `compute-vm`, `self-hosted`, `container-registry`, `kubernetes` |
| **Replatform** | The same app on an equivalent managed service, with configuration changes | `managed-postgres`, `managed-mysql`, `cache-redis`, `object-storage` through the S3 Compatibility API |
| **Refactor** | Code must change: SDKs, serverless handlers, identity, NoSQL access | `serverless-functions`, `key-value-nosql`, `identity-users`, `cloud-sdk`, `workflow-orchestration` |
| **Retain** | A gap with no acceptable workaround, or a commitment that ends later | Any `gap`; anything tied to a contract |
| **Retire** | Nobody can name an owner or a user for it | Resources found only in the live inventory |

## Picking the first wave

Choose a workload that is:

1. low risk (internal users, or a non-critical service);
2. representative (it exercises the network, identity, database and deploy
   path the rest will use);
3. reversible (old and new can run side by side).

A stateless API with a PostgreSQL database and object storage is usually a
good first wave. Leave identity migration, NoSQL rewrites and anything with
`gap` fit for later waves, once the platform and runbooks exist.

## Data migration method by downtime tolerance

| Downtime allowed | PostgreSQL | MySQL | Object storage |
|---|---|---|---|
| Hours | `pg_dump` and `pg_restore` | MySQL Shell dump and load | Bulk copy, then a final sync |
| Minutes | Logical replication, then switch | Inbound replication, then switch | Continuous sync, then switch |

Rehearse every method on a copy before the real cutover, and time it.
