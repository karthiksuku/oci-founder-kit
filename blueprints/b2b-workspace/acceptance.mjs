// Local acceptance only. Synthetic signed server sessions exercise Taskboard's actual middleware.
// No issuer login, OCI call, production table or existing database is used.
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { createRequire } from "node:module";
import { createHmac, randomBytes, randomUUID } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import { createApp } from "../fullstack-container/app/src/app.js";
import { createAuth, ownerKey, COOKIE_NAME } from "../fullstack-container/app/src/auth.js";
import { workspaceRoutes } from "./routes.mjs";

const require = createRequire(new URL("../fullstack-container/app/package.json", import.meta.url));
const { Pool } = require("pg");
const session = require("express-session");
const { Configuration } = await import(require.resolve("openid-client"));
const publicOrigin = "https://workspace.example.test";
const socket = process.env.FOUNDER_B2B_SOCKET;
const users = {};
let database, runtime, server, origin;
const base = "/api/b2b";
const orgPath = (id) => base + "/organizations/" + id;

before(async () => {
  assert.match(socket ?? "", /^\/[^']*\/founder-b2b-[\w-]+\/socket$/);
  assert.equal((await stat(socket)).mode & 0o777, 0o700);
  const db = { host: socket, port: 55439, database: "postgres", password: null };
  database = new Pool({ ...db, user: "fixture_owner" });
  await database.query(await readFile(new URL("schema.sql", import.meta.url), "utf8"));
  await database.query(`CREATE ROLE fixture_app LOGIN;
    GRANT USAGE ON SCHEMA founder_workspace TO fixture_app;
    GRANT SELECT,INSERT,UPDATE(name) ON founder_workspace.organizations TO fixture_app;
    GRANT SELECT,INSERT,DELETE,UPDATE(role) ON founder_workspace.memberships TO fixture_app;
    GRANT SELECT,INSERT,UPDATE,DELETE ON founder_workspace.invitations TO fixture_app;
    GRANT SELECT,INSERT ON founder_workspace.requests TO fixture_app;`);
  runtime = new Pool({ ...db, user: "fixture_app" });
  const issuer = "https://identity.example.test/";
  const secret = randomBytes(48).toString("hex");
  const config = { mode: "production", publicOrigin, trustProxy: "loopback", sessionSecret: secret, maxUploadBytes: 1024 };
  const store = new session.MemoryStore();
  const auth = await createAuth({ config, store, oidcConfiguration: new Configuration({ issuer }, "workspace-test") });
  for (const name of ["one", "two", "member", "other", "unjoined", "expired"]) {
    const id = randomUUID(), csrf = randomBytes(32).toString("hex");
    const owner = ownerKey(issuer, name);
    await new Promise((resolve, reject) => store.set(id, { cookie: {}, user: {
      owner, expiresAt: Date.now() + (name === "expired" ? -1000 : 3600000) }, csrf
    }, (err) => err ? reject(err) : resolve()));
    const signature = createHmac("sha256", secret).update(id).digest("base64").replace(/=+$/, "");
    users[name] = { owner, csrf, cookie: COOKIE_NAME + "=" + encodeURIComponent("s:" + id + "." + signature) };
  }
  const app = createApp({ tasks: { ping: async () => true }, attachments: null, config, auth,
    mountApi: workspaceRoutes({ config, pool: runtime }) });
  server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  origin = "http://127.0.0.1:" + server.address().port;
});
after(async () => {
  if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  await runtime?.end();
  await database?.end();
});

async function call(who, method, path, data, options = {}) {
  const user = users[who];
  const headers = { "X-Forwarded-Proto": "https", origin: publicOrigin,
    "content-type": "application/json", ...(user ? { cookie: user.cookie, "x-csrf-token": user.csrf } : {}), ...options };
  const response = await fetch(origin + path, { method, headers, body: data ? JSON.stringify(data) : undefined });
  const value = await response.json();
  assert.equal(response.headers.get("cache-control"), "no-store");
  return { status: response.status, value };
}
async function ok(who, method, path, data) {
  const result = await call(who, method, path, data);
  assert.ok(result.status === 200 || result.status === 201, JSON.stringify(result));
  return result.value;
}
async function org(who) { return (await ok(who, "POST", base + "/organizations", { name: "Synthetic " + who })).id; }
async function invite(who, id, to, role = "member") {
  return ok(who, "POST", orgPath(id) + "/invitations", { recipient: users[to].owner, role });
}
async function accept(who, id, token) { return call(who, "POST", orgPath(id) + "/accept", { token }); }

test("protected session, CSRF and account-selected organization creation", async () => {
  assert.throws(() => workspaceRoutes({ config: { mode: "sandbox" }, pool: runtime }), /production/);
  assert.equal((await call(null, "GET", base + "/me")).status, 401);
  assert.equal((await call("expired", "GET", base + "/me")).status, 401);
  assert.equal((await call("one", "POST", base + "/organizations", { name: "No" }, { "x-csrf-token": "" })).status, 403);
  assert.equal((await call("one", "POST", base + "/organizations", { name: "No" }, { origin: "https://other.example.test" })).status, 403);
  const created = await ok("one", "POST", base + "/organizations", { name: "Alpha", ownerId: users.two.owner });
  assert.equal((await ok("one", "GET", base + "/me")).organizations.find(o => o.id === created.id).role, "admin");
  assert.equal((await call("two", "GET", orgPath(created.id) + "/access")).status, 404);
});

test("tenant isolation includes list, object read, write, export, access and cancellation", async () => {
  const a = await org("one"), b = await org("two");
  const reqA = await ok("one", "POST", orgPath(a) + "/requests", { title: "Alpha document" });
  const reqB = await ok("two", "POST", orgPath(b) + "/requests", { title: "Beta document" });
  for (const [who, own, theirs, ownRecord, otherRecord] of [
    ["one", a, b, reqA, reqB], ["two", b, a, reqB, reqA]
  ]) {
    assert.equal((await ok(who, "GET", orgPath(own) + "/requests/" + ownRecord.id)).id, ownRecord.id);
    assert.equal((await call(who, "GET", orgPath(own) + "/requests/" + otherRecord.id)).status, 404);
    for (const route of ["/requests", "/export", "/access", "/requests/" + otherRecord.id]) {
      assert.equal((await call(who, "GET", orgPath(theirs) + route)).status, 404);
    }
    assert.equal((await call(who, "POST", orgPath(theirs) + "/requests", { title: "Wrong company" })).status, 404);
    const data = await ok(who, "GET", orgPath(own) + "/export");
    assert.equal(data.organization, own);
    assert.deepEqual(data.requests.map(r => r.title), [ownRecord.title]);
    assert.deepEqual(Object.keys(data.requests[0]).sort(), ["created_at", "id", "title"]);
    assert.equal(JSON.stringify(data).includes(otherRecord.title), false);
  }
  const pending = await invite("two", b, "member");
  assert.equal((await call("one", "DELETE", orgPath(a) + "/invitations/" + pending.id)).status, 404);
  assert.equal((await accept("member", b, pending.token)).status, 201);
  assert.equal((await call("member", "GET", orgPath(b) + "/export")).status, 403);
});

test("recipient-bound invitations expire, rotate, revoke and admit one concurrent redemption", async () => {
  const a = await org("one"), b = await org("two");
  const original = await invite("one", a, "member");
  const rotated = await invite("one", a, "member", "admin");
  assert.equal((await accept("member", a, original.token)).status, 404);
  assert.equal((await accept("other", a, rotated.token)).status, 404);
  assert.equal((await accept("member", b, rotated.token)).status, 404);
  const listed = await ok("one", "GET", orgPath(a) + "/access");
  assert.deepEqual(Object.keys(listed.invitations[0]).sort(), ["expires_at", "id", "recipient", "role"]);
  const revoked = await ok("one", "DELETE", orgPath(a) + "/invitations/" + rotated.id);
  assert.equal(revoked.revoked, true);
  assert.equal((await accept("member", a, rotated.token)).status, 404);
  const expired = await invite("one", a, "member");
  await database.query("UPDATE founder_workspace.invitations SET expires_at=now()-interval '1 minute' WHERE id=$1", [expired.id]);
  assert.equal((await accept("member", a, expired.token)).status, 404);
  const only = await invite("one", a, "member");
  const responses = await Promise.all([accept("member", a, only.token), accept("member", a, only.token)]);
  assert.deepEqual(responses.map(r => r.status).sort(), [201, 404]);
});

test("an invitation expiring while redemption waits on the organization lock cannot grant membership", async () => {
  const id = await org("one");
  const invitation = await invite("one", id, "member");
  const holder = await database.connect();
  let redemption;
  try {
    await holder.query("BEGIN");
    const lock = await holder.query("SELECT pg_backend_pid() AS pid FROM founder_workspace.organizations WHERE id=$1 FOR UPDATE", [id]);
    redemption = accept("member", id, invitation.token);
    const deadline = Date.now() + 5000;
    while (true) {
      const waiting = await database.query(
        "SELECT 1 FROM pg_stat_activity WHERE usename='fixture_app' AND $1=ANY(pg_blocking_pids(pid))", [lock.rows[0].pid]);
      if (waiting.rowCount) break;
      assert.ok(Date.now() < deadline, "Redemption did not reach the organization lock");
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    // Set a deadline after the observed wait began, and release only after PostgreSQL passes it.
    await holder.query("UPDATE founder_workspace.invitations SET expires_at=clock_timestamp()+interval '100 milliseconds' WHERE id=$1", [invitation.id]);
    await holder.query("SELECT pg_sleep_until(expires_at) FROM founder_workspace.invitations WHERE id=$1", [invitation.id]);
  } finally {
    try { await holder.query("COMMIT"); } finally { holder.release(); }
  }
  assert.equal((await redemption).status, 404);
  assert.equal((await call("member", "GET", orgPath(id) + "/requests")).status, 404);
});

test("role updates and offboarding apply to existing sessions and keep one administrator", async () => {
  const a = await org("one"), b = await org("two");
  for (const [issuer, id] of [["one", a], ["two", b]]) {
    const invitation = await invite(issuer, id, "member");
    assert.equal((await accept("member", id, invitation.token)).status, 201);
  }
  const member = orgPath(a) + "/members/" + users.member.owner;
  assert.equal((await call("member", "PATCH", member, { role: "admin" })).status, 403);
  assert.equal((await call("member", "POST", orgPath(a) + "/invitations", { recipient: users.other.owner, role: "member" })).status, 403);
  assert.equal((await call("one", "PATCH", orgPath(a) + "/members/" + users.one.owner, { role: "member" })).status, 409);
  assert.equal((await call("one", "DELETE", orgPath(a) + "/members/" + users.one.owner)).status, 409);
  await ok("one", "PATCH", member, { role: "admin" });
  const stale = await invite("member", a, "unjoined");
  await ok("one", "PATCH", member, { role: "member" });
  assert.equal((await accept("unjoined", a, stale.token)).status, 404);
  assert.equal((await call("member", "GET", orgPath(a) + "/export")).status, 403);
  await ok("one", "DELETE", member);
  assert.equal((await call("member", "GET", orgPath(a) + "/requests")).status, 404);
  assert.equal((await call("member", "POST", orgPath(a) + "/requests", { title: "late" })).status, 404);
  assert.equal((await call("member", "GET", orgPath(b) + "/requests")).status, 200);
});

test("simultaneous offboarding cannot remove the final administrator", async () => {
  const a = await org("one");
  const invitation = await invite("one", a, "other", "admin");
  assert.equal((await accept("other", a, invitation.token)).status, 201);
  const calls = await Promise.all([call("one", "DELETE", orgPath(a) + "/members/" + users.other.owner),
    call("other", "DELETE", orgPath(a) + "/members/" + users.one.owner)]);
  assert.deepEqual(calls.map(r => r.status).sort(), [200, 404]);
  const active = await database.query("SELECT role FROM founder_workspace.memberships WHERE organization_id=$1", [a]);
  assert.deepEqual(active.rows, [{ role: "admin" }]);
});

test("oversized exports fail explicitly, including when the user supplies another limit", async () => {
  const a = await org("one");
  await database.query(`INSERT INTO founder_workspace.requests(id,organization_id,title)
    SELECT gen_random_uuid(),$1,'synthetic' FROM generate_series(1,1001)`, [a]);
  const response = await call("one", "GET", orgPath(a) + "/export?limit=1");
  assert.equal(response.status, 409);
  assert.equal(response.value.requests, undefined);
});

// Intercept the synthetic HTTPS origin and run its requests only against our loopback app.
async function openPortal(browser, who, beforeResponse) {
  const context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 390, height: 844 } });
  await context.route("**/*", async route => {
    const r = route.request(), url = new URL(r.url());
    if (url.origin !== publicOrigin) return route.abort();
    const headers = { ...r.headers(), "x-forwarded-proto": "https", cookie: users[who].cookie };
    const response = await fetch(origin + url.pathname + url.search, { method: r.method(),
      headers, body: r.postDataBuffer() || undefined, redirect: "manual" });
    if (beforeResponse) await beforeResponse(r.method(), url.pathname);
    await route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(6500);
  await page.goto(publicOrigin + base + "/portal");
  await page.waitForFunction(() => document.getElementById("recipient")?.value);
  return page;
}

test("two local browser sessions create a workspace, join, share a request, export and offboard",
  { skip: process.env.FOUNDER_B2B_BROWSER !== "1" }, async () => {
    const browser = await require("playwright").chromium.launch();
    try {
      const admin = await openPortal(browser, "one"), member = await openPortal(browser, "other");
      const recipientId = await member.getByLabel("Your invitation recipient ID").inputValue();
      await admin.getByLabel("Organization name").fill("Browser workflow");
      await admin.getByRole("button", { name: "Create organization", exact: true }).click();
      await admin.getByRole("heading", { name: "Browser workflow", exact: true }).waitFor();
      const id = await admin.locator("#org-id").textContent();
      await admin.getByLabel("Recipient ID", { exact: true }).fill(recipientId);
      await admin.getByRole("button", { name: "Create invitation" }).click();
      await admin.getByLabel("One-time code").waitFor();
      const token = await admin.getByLabel("One-time code").inputValue();
      await member.getByLabel("Organization ID", { exact: true }).fill(id);
      await member.getByLabel("Invitation code").fill(token);
      await member.getByRole("button", { name: "Accept invitation" }).click();
      await member.getByRole("heading", { name: "Browser workflow", exact: true }).waitFor();
      assert.equal(await member.getByRole("button", { name: "Download organization requests" }).isVisible(), false);
      await member.getByLabel("Request title").fill("Customer approval");
      await member.getByLabel("Request title").press("Tab");
      assert.equal(await member.getByRole("button", { name: "Add request" }).evaluate(el => el === document.activeElement), true);
      await member.keyboard.press("Enter");
      await member.getByText("Customer approval", { exact: true }).waitFor();
      const download = admin.waitForEvent("download");
      await admin.getByRole("button", { name: "Download organization requests" }).click();
      const data = JSON.parse(await readFile(await (await download).path(), "utf8"));
      assert.equal(data.organization, id); assert.deepEqual(data.requests.map(r => r.title), ["Customer approval"]);
      await admin.reload();
      await admin.getByLabel("Open organization").selectOption(id);
      const entry = admin.locator("#members li").filter({ hasText: recipientId });
      await entry.waitFor();
      assert.equal(await admin.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
      await admin.evaluate(await readFile(require.resolve("axe-core/axe.min.js"), "utf8"));
      const violations = await admin.evaluate(async () => (await axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }
      })).violations.map(item => item.id));
      assert.deepEqual(violations, []);
      admin.once("dialog", dialog => dialog.accept());
      await entry.getByRole("button", { name: "Remove", exact: true }).click();
      await entry.waitFor({ state: "detached" });
      assert.equal((await call("other", "GET", orgPath(id) + "/requests")).status, 404);
    } finally { await browser.close(); }
  });

test("changing organizations clears customer drafts and ignores old responses, including after offboarding",
  { skip: process.env.FOUNDER_B2B_BROWSER !== "1", timeout: 25000 }, async () => {
    const a = (await ok("two", "POST", base + "/organizations", { name: "Draft workspace A" })).id;
    const b = (await ok("unjoined", "POST", base + "/organizations", { name: "0 Draft workspace B" })).id;
    const admission = await invite("two", a, "unjoined", "admin");
    assert.equal((await accept("unjoined", a, admission.token)).status, 201);
    const browser = await require("playwright").chromium.launch();
    const waiting = new Set([orgPath(a) + "/requests", orgPath(a) + "/invitations"]);
    const release = Promise.withResolvers(), submitted = Promise.withResolvers();
    try {
      const page = await openPortal(browser, "unjoined", async (method, path) => {
        if (method !== "POST" || !waiting.delete(path)) return;
        if (!waiting.size) submitted.resolve();
        await release.promise;
      });
      const chooser = page.getByLabel("Open organization");
      const title = page.getByLabel("Request title");
      const recipient = page.getByLabel("Recipient ID", { exact: true });
      const role = page.getByRole("combobox", { name: /^Role\b/ });
      const switchTo = async (id, heading) => {
        await chooser.selectOption(id);
        await page.getByRole("heading", { name: heading, exact: true }).waitFor();
      };
      const emptyDrafts = async () => {
        assert.equal(await title.inputValue(), "");
        assert.equal(await recipient.inputValue(), "");
        assert.equal(await role.inputValue(), "member");
        assert.equal(await page.getByLabel("One-time code").isVisible(), false);
      };

      await switchTo(a, "Draft workspace A");
      await title.fill("A private request");
      await page.getByRole("button", { name: "Add request" }).click();
      await recipient.fill(users.member.owner);
      await role.selectOption("admin");
      await page.getByRole("button", { name: "Create invitation" }).click();
      await submitted.promise;  // Both writes committed to A. Their browser responses are still pending.
      await switchTo(b, "0 Draft workspace B");
      await emptyDrafts();
      await title.fill("B private draft");
      await recipient.fill(users.other.owner);
      await role.selectOption("admin");
      const replies = ["requests", "invitations"].map(path => page.waitForResponse(
        response => response.request().method() === "POST" && response.url().endsWith(orgPath(a) + "/" + path)));
      release.resolve();
      await Promise.all((await Promise.all(replies)).map(response => response.finished()));
      await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
      assert.equal(await title.inputValue(), "B private draft");
      assert.equal(await recipient.inputValue(), users.other.owner);
      assert.equal(await role.inputValue(), "admin");
      assert.equal(await page.getByLabel("One-time code").isVisible(), false);
      assert.deepEqual((await ok("unjoined", "GET", orgPath(b) + "/requests")).requests, []);

      await switchTo(a, "Draft workspace A");
      await emptyDrafts();
      await title.fill("Removed workspace draft");
      await recipient.fill(users.member.owner);
      await role.selectOption("admin");
      await ok("two", "DELETE", orgPath(a) + "/members/" + users.unjoined.owner);
      // Re-select the still-displayed workspace. The real membership read now selects B.
      await switchTo(a, "0 Draft workspace B");
      assert.equal(await chooser.inputValue(), b);
      await emptyDrafts();
    } finally {
      release.resolve();
      await browser.close();
    }
  });
