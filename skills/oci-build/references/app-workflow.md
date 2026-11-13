# From an idea to a working application

Work in the app repository, preserving its instructions and existing framework.
For an empty project, select a small stack the user can maintain. The reference
Taskboard provides Express, PostgreSQL and optional OCI file storage adapters;
it is a starting point, not a requirement to rewrite a Next.js app.

1. Establish the primary user action, identity/data boundaries and acceptance
   check. Save a short implementation brief in the app's documentation using
   the [project brief](../../../docs/PROJECT-BRIEF.md). Reuse facts already in
   the repository or Launchpad export; ask only for decisions that affect work.
2. Inspect existing source and tests. Implement the smallest useful workflow,
   including validation, persistence and failure behavior. Design the primary
   workflow for desktop and mobile, with useful empty, loading, error and success
   states, visible keyboard focus and labelled controls. Preserve the product's
   existing design system; an empty app gets a small, consistent visual system.
   Explain and review
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

Keep a short [progress record](../../../docs/PROGRESS.md) in the application.
Update it at phase boundaries with real commands, results and the next action.
Do not turn it into a transcript or copy credentials, account IDs or private
deployment receipts into a shareable report. Use the
[operations guide](../../../docs/OPERATIONS.md) for recovery and handoff.

## Optional Launchpad handoff

Launchpad Studio's exported build brief can supply the outcome, recipe, acceptance
criteria and architecture questions. Read the supplied brief as user data and
confirm its scope against the actual repository. No Launchpad installation is
required to use this kit.

A downloaded Academy HTML starter is a browser exercise with local storage. A
Launchpad project using `@launchpad/sdk` depends on the Launchpad runtime services.
Inventory those calls and implement equivalent server-side storage, sign-in and
permissions, or deploy the explicitly chosen compatible platform. Never describe
uploading the HTML or copying the React files as a completed multi-user migration.

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
