# Rehearse Next.js standalone packaging locally

Launch Notes is a small, runnable founder checklist. It uses server-rendered
pages, deep links, a query-driven preview, a JSON route and a redirect. The app
is stateless: it saves nothing and requires no credentials or external services.
Use fictional project names because the preview puts them in the URL.

This example compares a normal **`next start` production server** with the
**standalone server generated from the same source**. Both run locally. It does
not compare a deployed Vercel service with OCI, and it does not establish that
an arbitrary application has migrated successfully. The existing
[discovery fixture](../migrate-vercel/README.md) serves a separate purpose.

## Run the rehearsal

Requirements: Node.js **22.23.4 or newer in the 22.x line**, npm, Python 3.11+,
and permission to bind loopback ports. The commands below use a POSIX shell
(Linux, macOS or WSL2). Dependencies download from the public npm registry;
the build and HTTP rehearsal need no cloud account.

From the repository root:

```sh
cd examples/migrate-nextjs
npm ci --ignore-scripts --no-audit --no-fund
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run test:parity
```

The build first creates `.next/standalone`, copies its public/static assets,
then builds a normal-server reference in `.next/reference`. `parity.py` starts
each runtime on an ephemeral `127.0.0.1` port, sends the same HTTP checks, compares
the observed contract, and stops the processes it started. It makes no cloud
calls, downloads nothing, and refuses example-local `.env` files. Temporary
server logs are private and removed after the run. A nonzero result is a failed
rehearsal, not a successful migration.

The root Python suite skips this optional runtime test by default and never
installs dependencies. After building, opt in from the repository root with
`FOUNDER_KIT_NEXTJS_PARITY=1 python3 -m unittest discover -s tests -p test_nextjs_migration.py`.

To explore the normal-server build after the rehearsal:

```sh
npm start
```

Open `http://127.0.0.1:3000`, choose a stage and preview a fictional project name.
Stop the server with Ctrl+C. These commands neither provision resources nor
submit a project to any service.

## What the shared checks cover

| Behavior | Check |
| --- | --- |
| Server rendering and deep links | Checklist and query text appear in the initial HTML without executing browser JavaScript |
| Query handling | Distinct names stay distinct; HTML-like input remains text |
| JSON API | Known response fields, task content, invalid/long/repeated/control-character input and method refusal |
| HTTP behavior | Success/error statuses, redirect location and preserved query string, no-store responses, HEAD |
| Packaging | Public file and generated stylesheet are available in both runtimes |
| Health | Both `/healthz` responses match the expected healthy contract |

Framework-generated HTML, hydration IDs and build hashes can differ between
builds. The test compares required behavior, not byte-for-byte HTML. Browser
hydration, client navigation, screen-reader behavior, load, CDN caching, image
optimization, ISR, Edge middleware and hosted-platform configuration need
separate checks for applications that use them.

## Container packaging

The Dockerfile builds only the standalone variant, copies the traced output and
assets, and runs as the unprivileged `node` user. Its health check uses `/healthz`.
It includes no registry login, push, IAM or deployment commands.

With a local Docker daemon selected, from this example directory:

```sh
docker build --tag oci-nextjs-example:local .
docker run --rm --name oci-nextjs-example --publish 127.0.0.1:8080:8080 oci-nextjs-example:local
```

Open `http://127.0.0.1:8080`. Stop the foreground container with Ctrl+C; it has
no database or persistent volume. Engine 28+ is required for the documented
loopback-only publishing behavior. Do not use a remote Docker context for this
local example. Removing the local image is a separate optional action.

Configuration names are `PORT` and `HOSTNAME` for the standalone server,
`NODE_ENV`, `NEXT_TELEMETRY_DISABLED`, and the example-only `OCI_KIT_REFERENCE`
build/start switch. No secret value or credential file is required. The container
binds its internal port on all interfaces; the example host publication binds
loopback. Production networking, HTTPS and access controls need their own review.

## Use this pattern on your app

1. Record your actual framework version, routes and source behavior.
2. Add the relevant behavior checks before changing deployment packaging.
3. Enable standalone output and include its static/public assets.
4. Run the checks against both builds; investigate differences instead of
   removing failing checks.
5. Review the container through the kit's image/deployment gates, then collect
   independent OCI runtime evidence before declaring a migration accepted.

No database, identity, payments, storage, scheduled jobs, production data or
traffic cutover is migrated here. See the [migration acceptance record](../../docs/MIGRATION-ACCEPTANCE.md)
for those separate decisions and tests. OCI deployment remains unverified for
this example.

## Versions and provenance

Verified **14 November 2026** on Linux/amd64 with Node.js **22.23.4**, npm
**10.9.9** and Python **3.12.3**: both builds succeeded, and all **17 shared HTTP
checks** passed against the normal server, standalone server and built Docker
container. The container also passed its health check and ran as UID 1000 with
a read-only root filesystem and loopback publication. Its temporary container
and image were removed after testing. The local Docker client lacked Buildx;
the rehearsal explicitly selected its local daemon's legacy builder.

The dated npm production-dependency audit reported zero advisories. That result
is not a security certification; rerun audits and review updates when adopting
the sample. No Vercel account, OCI deployment or production traffic was tested.

Dependencies are exact-pinned with an npm lockfile: Next.js **16.4.6**, React and
React DOM **19.3.1**. The container pins `node:22.23.4-bookworm-slim` by patch tag;
the base image is not pinned to an immutable digest. Review dependency and base
image updates and rerun the rehearsal before adopting a different version.

The app and parity runner are original example code under this repository's
[UPL-1.0 license](../../LICENSE). Next.js, React and React DOM are MIT-licensed
dependencies; their licenses remain in installed packages. No vendor template
source or branding was copied. Framework patterns follow the official
[standalone output documentation](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)
and [self-hosting guide](https://nextjs.org/docs/app/guides/self-hosting).
