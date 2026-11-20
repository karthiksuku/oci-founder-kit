# Onboard your first business customer

Give a customer its own workspace. An administrator can invite a colleague, manage their role, and download the organization’s requests. Members can create and read requests. The included browser page lets you exercise that workflow with the existing Taskboard sign-in.

**Try this with Claude Code or Codex**

> Add the optional B2B workspace to my existing Taskboard app. Keep my account provider and application code. Show the proposed integration and database migration. Run the local two-business acceptance test, then tell me what needs a hosted rehearsal.

## Try the reference locally

Use Node 22+, Python 3.11+, PostgreSQL command-line tools, and the Taskboard dependencies in a reviewed kit checkout. From the kit root:

```sh
npm ci --prefix blueprints/fullstack-container/app --ignore-scripts --no-audit
blueprints/fullstack-container/app/node_modules/.bin/playwright install chromium
python3 blueprints/b2b-workspace/test_local.py --postgres-bin /usr/lib/postgresql/16/bin --browser
```

Provide the installed PostgreSQL binary directory on your machine. The runner creates a disposable cluster on a private Unix socket, with a separate schema owner and application database role. Chromium exercises the real portal at mobile width through two synthetic server-side sessions, including keyboard submission and automated accessibility checks. The API tests cover two organizations, unauthorized access and revocation. This is local Linux test evidence. Hosted login, mail delivery and OCI deployment require separate checks. Omit `--browser` to run the API scenarios alone.

## Attach to your own Taskboard

1. Choose the target project and review a diff. Copy `routes.mjs`, `portal.mjs`, `portal.css` and `portal.html` together into a **new** `app/src/b2b/` directory in your app. The integration uses the app’s existing Express and PostgreSQL dependencies. A founder using another web stack can adapt the same database operations and acceptance cases to their verified server identity.
2. In the app’s `src/server.js`, import `workspaceRoutes` from `"./b2b/routes.mjs"`. Pass `mountApi: workspaceRoutes({ pool, config })` to the existing `createApp({ ... })` call for the production-mode, OIDC-protected app. Preserve any existing API mounts by invoking both inside the `mountApi` callback. For a project that also starts in sandbox mode, set this option only when `config.mode === "production"`. The adapter reads Taskboard’s verified server session after its user and CSRF middleware. Use only the production middleware before mounting it. A portal participant needs an identity admitted by the app’s configured OIDC client.
3. Review [the schema](schema.sql) and apply it **once** through the intended deployment’s database migration process. This creates a dedicated schema with new tables. An existing schema of the same name causes the transaction to fail. Review backup, restore and rollback before a production migration. Use a migration owner separate from the runtime database role. For a runtime role named `workspace_app`, the required grants are:

   ```sql
   GRANT USAGE ON SCHEMA founder_workspace TO workspace_app;
   GRANT SELECT, INSERT, UPDATE(name) ON founder_workspace.organizations TO workspace_app;
   GRANT SELECT, INSERT, DELETE, UPDATE(role) ON founder_workspace.memberships TO workspace_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON founder_workspace.invitations TO workspace_app;
   GRANT SELECT, INSERT ON founder_workspace.requests TO workspace_app;
   ```

   The column update grant on organizations permits row locking for membership changes. This module authorizes queries inside the app. Keep the runtime database account private and restrict its use to the trusted backend. Database administrators retain their ordinary data access.

4. Sign in through `/auth/login` on the approved HTTPS rehearsal. Open **`/api/b2b/portal`**. Add a link to this path in your app wherever customers open their workspace. Test there before promoting the new release.

## The first-customer walkthrough

1. An admitted user selects **Create organization** and becomes its first administrator. The organization ID identifies this workspace even when display names match.
2. A colleague signs in to the same app and copies **Your invitation recipient ID** from the portal. This value derives from the OIDC issuer and subject. Identify the intended colleague through a trusted channel before inviting them.
3. The admin selects the organization, pastes the recipient ID, chooses **member** or **admin**, and creates an invitation. Share the organization ID and the one-time code privately with that colleague. The code appears once, stays out of URLs and is stored hashed in the database. It expires after 48 hours. Reissuing an invitation replaces its earlier code.
4. The colleague enters both values. Add a customer request as a member, then download it as the admin using **Download organization requests**. The JSON contains only this organization’s request IDs, titles and creation times. It excludes personal Taskboard tasks, attachments, identities and invitation data. The portal displays the 100 latest requests. A complete export over 1,000 requests returns an explicit size error.
5. Use **Remove** to offboard the colleague. Their next request to that workspace is denied, including from an already signed-in browser. Other memberships are independent. The portal also supports revoking an invitation and changing a member’s role. Removing or demoting an administrator invalidates their outstanding invitations. The last administrator must assign another before stepping down. Previously downloaded copies stay with the recipient.

Use synthetic data for a rehearsal. Have a second business create its own workspace and add a recognizable request. Each business must see only its own records and exports. In a hosted rehearsal, also verify invite expiry, two distinct hosted sign-ins, revoked access after reload, and storage/retention of exports before sharing with a customer.
