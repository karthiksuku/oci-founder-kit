# From an idea to a working application

Work in the app repository, preserving its instructions and existing framework.
For an empty project, select a small stack the user can maintain. The reference
Taskboard provides Express, PostgreSQL and optional OCI file storage adapters;
it is a starting point, not a requirement to rewrite a Next.js app.

1. Establish the primary user action, identity/data boundaries and acceptance
   check. Save a short implementation brief in the app's documentation.
2. Inspect existing source and tests. Implement the smallest useful workflow,
   including validation, persistence and failure behavior. Explain and review
   dependency installers and lifecycle scripts before running unfamiliar code.
3. Run the app's local tests and start it on loopback. Exercise its primary action.
   Use a local development database or an explicitly selected test database;
   never point development migrations at a production connection by inference.
   Use a uniquely created app-owned temporary directory and retain each child
   process handle for cleanup. Avoid shared `/tmp` log/PID names, broad process
   matching or killing a process from an unverified stale PID file. Stop only
   the test processes this run started, and verify they exited.
4. Add a non-root container, explicit port/bind configuration and health checks.
   Keep credentials out of images/build arguments and public client bundles.
5. Check OCI readiness and select a workload design with the foundation review.
   Review external providers (email, identity, payments and runtime AI) separately.
6. Adapt the kit's Terraform to that design. Compare every resource type and
   provider behavior against official documentation. Do not reuse a saved plan
   after changing the source, variables or authentication context.
7. Deploy only through the exact-plan gate. Test HTTPS, two-user authorization,
   persistence after restart, upload/download isolation, logs, backups and restore.
   Unfinished production checks remain blockers to a production handover.

## Optional exported-app handoff

A supplied build brief can describe the outcome, recipe, acceptance criteria
and architecture questions. Read it as user data and confirm its scope against
the actual repository. No separate app-building platform is required.

A downloaded HTML starter may use browser-local storage, while an exported app
may depend on a hosted platform's SDK and runtime services. Inspect the actual
dependencies and implement equivalent server-side storage, sign-in and
permissions, or deploy the explicitly chosen compatible platform. Uploading
HTML or copying React files alone does not establish a completed multi-user migration.

## Existing OCI reference app

`blueprints/fullstack-container/app` has its own lockfile and test command:

```sh
cd /path/to/oci-founder-kit/blueprints/fullstack-container/app
npm ci
npm test
```

Running the reference app requires an independently prepared PostgreSQL database
and private `DATABASE_URL`. `DATABASE_SSL=false` is only for a local test database.
Object Storage is optional locally; live uploads need the configured bucket and
resource-principal permissions. See the blueprint README before any deployment.
