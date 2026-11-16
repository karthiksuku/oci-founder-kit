# Customer requests: optional SaaS essentials

A working reference for authenticated customer requests, private attachments,
background processing, signed inbound events and scheduled summaries. Use this
pack when those features fit your app. Existing projects opt into the adapters;
this pack never replaces their application, authentication, storage or queues.

**Preview evidence:** local PostgreSQL/HTTP tests and mocked infrastructure checks.
OCI Queue, worker permissions and hosted end-to-end behavior still require an
owner-approved sandbox acceptance run. Native Functions scheduling is blocked
behind its separate artifact/runtime acceptance; see [its contract](experimental/acceptance.json).

The web app reuses the kit's reviewed OIDC, server-side sessions, CSRF and private
attachment proxy. The durable runtime adds an inbox, outbox, job ledger and UTC
schedule cursor. Request classification and summaries write results into
PostgreSQL; this example sends no emails and makes no payments.

## Try the local reference

From a verified kit checkout, use Node 22, Docker Compose v2+ and Buildx/BuildKit.
Run `docker buildx version` first; install the supported Buildx plugin if absent.
Legacy Docker builds are unsupported because they can ignore the Dockerfile-specific
credential exclusions. The explicit BuildKit setting below must fail rather than
fall back when Buildx is unavailable. Create a private
`.env` alongside this README (never commit it) with independently generated
`PREVIEW_DB_PASSWORD` and `PREVIEW_WEBHOOK_SECRET` values. Use a URL-safe database
password and at least 32 random bytes for the webhook secret. Optionally set
`PREVIEW_PORT` (default 8088). Credentials stay in that private file.

```sh
DOCKER_BUILDKIT=1 docker compose -f blueprints/saas-essentials/compose.local.yaml --env-file blueprints/saas-essentials/.env up --build -d
```

Open `http://127.0.0.1:8088`. Add a customer request containing “urgent”; its
processing result appears in the page. The hourly summary runs from a durable
UTC cursor. This local demonstration uses one sandbox owner, a PostgreSQL volume
and an in-memory queue adapter. It does **not** prove hosted sign-in, OCI Queue or
Object Storage. Private OCI attachments become available only after the
production storage/authentication configuration is accepted.

```sh
docker compose -f blueprints/saas-essentials/compose.local.yaml --env-file blueprints/saas-essentials/.env stop
```

Stopping retains the local database volume. Review backups before requesting
volume deletion; this guide does not silently destroy your requests.

## Connect it to OCI

1. Keep the web app on the existing `web-container` target and retain the chosen
   external identity/database/storage during hosting migration. Build the image
   with Buildx (required), using `blueprints/` as its context:

   ```sh
   docker buildx build --load --platform linux/amd64 -f blueprints/saas-essentials/app/Dockerfile -t oci-saas-local:review blueprints
   ```

   This tag is local only; publication uses the reviewed immutable digest.
   The adjacent Dockerfile ignore file limits that context to reviewed source and
   package files. Run image health/credential checks, then the existing exact
   digest publication gate.
2. Review the database change with its authorized administrator. Apply the shared
   Taskboard schema using `PgTaskStore.migrate()`, then `app/src/schema.sql` under
   the approved change. Use a dedicated database per environment and separate
   restricted web and worker database roles. The web runtime must not administer
   `saas_ownership`, `saas_schedules` or `saas_replays`. Production startup does not
   run these migrations. Take and test the relevant backup first.
3. Create the environment's ownership row as **paused**. Retain the source worker
   until a separate reviewed transfer confirms it is quiesced. Migration never
   activates this worker by default.
4. Reuse or prepare a **separate dedicated worker compartment**, private subnet,
   worker registry, database credential secret and reviewed egress. The app's
   existing compartment-wide Container Instance group must exclude this worker.
   Inherited tenancy IAM and subnet security lists need independent review; the
   template cannot prove them safe.
5. Copy only this pack's reviewed `terraform/` sources into a new component root
   and add the canonical empty OCI backend declaration through the existing
   backend workflow. Configure `components.worker` with its own compartment,
   exact image digest, infrastructure directory and state destination. See
   [the component example](COMPONENTS.example.json). Configure via:

   ```sh
   python3 scripts/environments.py configure --project /path/to/app --name rehearsal --target-file /private/web-target.json --components-file /private/components.json
   ```

   Both files must be private. This keeps a configuration backup and invalidates
   old plans/evidence. Pass the **worker root**, `--project` and
   `--environment rehearsal` explicitly to every backend/deployment gate command.
   The gate verifies the reviewed source bytes, actual evaluated worker image,
   compartment and environment name. Web and worker never share approvals.
6. The template creates one Queue and a private E4 worker instance; it creates no
   ingress rule. OCI provider **9.10.0** is pinned. IAM creation defaults off;
   enabling it is visible in the exact reviewed plan. Its policies grant the
   worker only selected Queue push/pull, repository read and its database secret.
   The web service has no Queue permission: it persists the outbox instead.
7. Follow [OPERATIONS.md](OPERATIONS.md) for schema permissions, ownership transfer,
   poison jobs, scoped replay and acceptance. Domain/certificates, hosted sign-in,
   external database TLS and private attachments use the web target's existing
   reviewed setup. Every OCI write, SQL change, traffic change and cleanup needs
   the owner's exact reviewed operation.

The worker is a separate artifact role even when its bytes match the web image.
Bind and verify its image independently. Both use the same image entry point
source; Terraform selects `worker.js` explicitly. The worker reads only its
DB credential through resource principals and verified database TLS. The web
runtime uses the Taskboard production configuration plus:

| Setting | Purpose |
| --- | --- |
| `SAAS_ENVIRONMENT` | Exact selected environment name |
| `WEBHOOK_SECRET_OCID` | Vault reference to the inbound signing secret |
| `WEBHOOK_OWNER_ID` | Reviewed mapping to the provider's intended app owner; never accept an owner from event input |

The example binds one webhook integration to one owner. Multi-customer provider
integrations need a separately reviewed account-to-owner mapping and secrets;
do not reuse a single secret across unrelated customers.

## Signed event contract

POST `/webhooks/requests` as `application/json`. The reference protocol uses
`x-kit-webhook-signature: t=<Unix seconds>,v1=<hex HMAC-SHA256>`, computed over
`<timestamp>.` followed by the **unchanged request bytes**. The receiver accepts
five minutes of clock skew, limits bodies to 16 KB, rejects compression, verifies
before JSON parsing and acknowledges only after the durable inbox/outbox commit.
It is a reference protocol, **not** a drop-in Stripe endpoint or billing system.

```json
{"id":"event_123","type":"request.upsert","data":{"externalId":"request_123","version":2,"title":"Update my workspace","done":false}}
```

IDs identify a provider event and request. A repeated event with changed bytes is
rejected. A strictly newer request version supersedes an older version. Accepted
work keeps its job ID through Queue redelivery, process crashes and scoped replay.
A user-deleted external request stays tombstoned rather than being recreated by a
later delivery. Keep inbox/tombstone retention longer than the provider's replay
window; pruning is a separate reviewed data operation.

## Verification and limits

```sh
npm ci --ignore-scripts --prefix blueprints/fullstack-container/app
npm ci --ignore-scripts --prefix blueprints/saas-essentials/app
node --test blueprints/saas-essentials/app/test/reliability.test.js
terraform -chdir=blueprints/saas-essentials/terraform init -backend=false
terraform -chdir=blueprints/saas-essentials/terraform test
python3 -m unittest discover -s tests -p test_saas_components.py
```

The Node suite clearly skips PostgreSQL scenarios without
`SAAS_TEST_DATABASE_URL`; use an isolated disposable local database for full
coverage. Tests create and delete only a uniquely named synthetic schema there.
Use `scripts`-level release verification for the broader kit checks.

There is one worker instance and one web instance by default. Updates can
interrupt service. Queue provides at-least-once delivery; database transactions
prevent duplicate reference effects, **not arbitrary exactly-once external
side effects**. Use provider idempotency keys or reconciliation before adding
outbound actions. Transport delivery, database acceptance, processing completion
and successful external effects are distinct observations.

Public design references reviewed 16 November 2026: [OCI Queue consumption](https://docs.oracle.com/en-us/iaas/Content/queue/consume-messages.htm),
[Queue policy scopes](https://docs.oracle.com/en-us/iaas/Content/queue/policy-reference.htm),
[message endpoint](https://docs.oracle.com/en-us/iaas/Content/queue/messages.htm),
[Stripe webhook guidance](https://docs.stripe.com/webhooks), and
[Functions resource contract](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/functions_function.html).
These are source reviews, not independent cloud deployments. The kit's shared
code is UPL-1.0; the pinned OCI SDK is dual UPL-1.0/Apache-2.0. No third-party
reference implementation was copied.
