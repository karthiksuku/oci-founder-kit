# Migration acceptance record

Use this in the application repository before changing hosting. Keep the source
working until target behavior and rollback are accepted. A scanner supplies
leads; it cannot see dashboard-only configuration or establish parity by itself.

## Scope and source baseline

Record the source revision, runtime/framework versions, current build/test
commands, baseline failures and the named target. List each service as **move**,
**retain**, **replace** or **unknown**. Include identity, database, file storage,
queues, schedules, email, payments, AI APIs and provider-managed configuration.
Record configuration names and scopes only; transfer values privately.

## Behavior matrix

For each applicable row, record the actual source observation, target observation,
test command, result and accepted differences. Use two independent test users.

| Area | Required evidence |
|---|---|
| Routing | Deep links, redirects/status codes, rewrites, missing pages, headers |
| Identity | Sign-in/callback/logout, expiry, denied requests, no cross-user reads or writes |
| Data | Create/read/update/delete, concurrent writes, restart persistence, schema compatibility |
| Files | Upload/download, ownership, content limits, expired links and checksum checks |
| Framework runtime | Server routes, streaming, image transformation, cache/revalidation where used |
| Jobs | Time zone, authorization, idempotency, retry and missed-run behavior |
| Integrations | Approved test webhooks, signatures, duplicates, failure/retry handling |
| Operations | Health, redacted logs, metrics, TLS, update/rollback and restore |

## Data rehearsal

Agree the datasets, nonproduction destination, encryption, transfer method,
retention and allowed loss/downtime. Identify the authoritative writer during
each step. Rehearse initial transfer and incremental synchronization; measure
duration. Compare record counts, representative queries, file hashes and
application-level behavior. Do not treat equal counts alone as data equivalence.

Keep the source snapshot and approved backup privately. A database migration is
separate from moving application hosting. No production export/import follows
from a general request to package the app.

## Cutover and rollback

Before requesting traffic-switch approval, provide:

1. Exact DNS/routing/callback changes and the expected propagation window.
2. Final data synchronization and write-freeze sequence, with named ownership.
3. Success thresholds and the observation period for health, errors, latency and data.
4. Rollback trigger, previous routing/image and how post-switch writes are retained.
5. An explicit stop condition when rollback would lose or diverge data.
6. Source retention window and a separate future decision for decommissioning.

Rehearse rollback with nonproduction data before the live switch. Record actual
results in the [progress record](PROGRESS.md). Keep **local adaptation**, **staged
deployment**, **data transfer** and **traffic cutover** as separate outcomes.
