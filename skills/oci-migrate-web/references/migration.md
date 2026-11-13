# Web migration checks

Reviewed against primary documentation on 13 November 2026. Recheck the installed
framework version and current service documentation for each real migration.

| Finding | Adaptation and acceptance evidence |
| --- | --- |
| Next.js | Inspect the installed version, build output and runtime requirements. A standalone Node build can be a container packaging option; confirm static/public assets and traced monorepo files are included. Do not use static export when the app requires server features. |
| Middleware or edge runtime | Inventory platform APIs and assumptions about geography and request lifecycle. Test authorization, redirects, cookies and bypass attempts after adapting the runtime. |
| Images and caching | Test image transformations, allowed origins, dependencies, memory use, cache persistence and revalidation. Multiple instances can require coordinated caches and consistent configuration. |
| Functions and routes | Exercise request sizes, timeouts, streaming, cookies, uploads, concurrency and background tasks against the chosen target. Provider-specific invocation and lifecycle helpers need replacement or deliberate retention. |
| Cron and asynchronous jobs | Record schedule time zone and missed-run behavior. Authenticate triggers, make work idempotent and bound retries. A running web server is not evidence that scheduled jobs run. |
| Redirects, rewrites and headers | Preserve status codes, precedence, deep links, SPA fallbacks and security headers. Test app and edge rules together. |
| Blob/object storage | Inventory objects, permissions, signed links, CORS and retention. Copy only approved data, validate checksums and application access, and rehearse incremental sync and rollback. |
| PostgreSQL or external backend | Check extensions, server version, TLS, pooling, auth and backup compatibility. Move hosting independently if appropriate; do not silently migrate database or identity. |
| KV and edge configuration | Validate command compatibility, consistency, TTL, latency and atomicity before choosing a target. Design data export/import and missing-key behavior explicitly. |
| Environment and secrets | Inventory names, build-time versus runtime injection and per-environment scopes. Browser-visible variables are public. Transfer secrets through approved credential stores, never through a report, source file or chat. |
| Preview deployments | Decide which environments and domains are actually required; design isolated data and permissions for each. A single production stack does not recreate automatic preview environments. |
| Domains and identity | Verify DNS ownership, certificates, OAuth callbacks, cookies and webhook destinations. Rehearse rollback before a separately approved traffic switch. |

Set acceptance criteria from observed source behavior. Record intended differences
and get the owner's agreement where parity cannot be retained. Measure performance
from the intended client regions; do not promise matching edge latency from a
single-region deployment.

## Primary references

- [Next.js self-hosting](https://nextjs.org/docs/app/guides/self-hosting): runtime operations, reverse proxy, caching, multi-instance behavior and streaming.
- [Next.js output configuration](https://nextjs.org/docs/app/api-reference/config/next-config-js/output): output tracing and standalone packaging.
- [Vercel project configuration](https://vercel.com/docs/project-configuration): inspect the features used by the source project.
- [Netlify file-based configuration](https://docs.netlify.com/build/configure-builds/file-based-configuration/): build, functions and routing configuration.
- [OCI Container Instances](https://docs.oracle.com/en-us/iaas/Content/container-instances/home.htm): evaluate fit and constraints for a container runtime.

The scanner detects a bounded subset of configuration and source patterns. It
does not parse full JavaScript/TypeScript semantics, resolve workspace dependencies,
inspect live accounts or prove that all dependencies were found. Review unsupported
frameworks and dashboard-only features explicitly.
