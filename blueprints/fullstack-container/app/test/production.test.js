// Synthetic identity provider and secrets only; no cloud access or real user data.
import { test, describe, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { generateKeyPairSync, sign, createHash, randomUUID } from "node:crypto";
import session from "express-session";
import * as oidc from "openid-client";
import { loadConfig } from "../src/config.js";
import { resolveRuntimeConfig, secretReaderForClient } from "../src/secrets.js";
import { createAuth, ownerKey } from "../src/auth.js";
import { createApp } from "../src/app.js";
import { MemoryTaskStore, FakeAttachmentStore } from "./fakes.js";

const secretId = (name) => `ocid1.vaultsecret.oc1..${name}`;
const environment = () => ({ APP_MODE: "production", PUBLIC_ORIGIN: "https://app.example.test",
  OIDC_ISSUER: "https://identity.example.test", OIDC_CLIENT_ID: "synthetic-client",
  OIDC_CLIENT_SECRET_OCID: secretId("oidc"), SESSION_SECRET_OCID: secretId("session"),
  DATABASE_PASSWORD_SECRET_OCID: secretId("database"), DATABASE_PASSWORD_SECRET_VERSION: "3",
  DATABASE_HOST: "db.example.test", DATABASE_USER: "app", DATABASE_NAME: "app",
  DATABASE_CA_CERT: "synthetic-ca", TRUST_PROXY_CIDRS: "127.0.0.1/32" });

describe("production configuration and secret loading", () => {
  test("refuses implicit mode and insecure or plaintext production settings", () => {
    assert.throws(() => loadConfig({}), /APP_MODE/);
    for (const patch of [{ PUBLIC_ORIGIN: "http://app.example.test" }, { PUBLIC_ORIGIN: "https://app.example.test/path" },
      { OIDC_ISSUER: "http://id.example.test" }, { DATABASE_SSL: "false" }, { DATABASE_URL: "synthetic" },
      { OCI_AUTH: "config-file" }, { DATABASE_CA_CERT: "" }, { TRUST_PROXY_CIDRS: "0.0.0.0/0" },
      { TRUST_PROXY_CIDRS: "true" }, { SESSION_SECRET: "synthetic" }]) {
      assert.throws(() => loadConfig({ ...environment(), ...patch }));
    }
    assert.throws(() => createApp({ tasks: {}, config: loadConfig(environment()) }), /authentication/);
  });
  test("fetches secrets server-side, pins the database version, and redacts failure", async () => {
    const config = loadConfig(environment());
    const calls = [];
    const runtime = await resolveRuntimeConfig(config, async (id, version) => {
      calls.push([id, version]);
      return id === config.secretIds.session ? "s".repeat(48) : "synthetic-runtime-value";
    });
    assert.equal(runtime.database.password, "synthetic-runtime-value");
    assert.deepEqual(calls.find(([id]) => id === config.secretIds.database), [config.secretIds.database, 3]);
    assert.equal(config.database.password, undefined);
    await assert.rejects(resolveRuntimeConfig(config, async () => { throw new Error("synthetic-sensitive-diagnostic"); }),
      (err) => !err.message.includes("synthetic-sensitive-diagnostic") && /startup refused/.test(err.message));
    await assert.rejects(resolveRuntimeConfig(config, async () => "short"));
  });
  test("owner keys separate issuer and subject and do not use email", () => {
    assert.notEqual(ownerKey("https://a", "one"), ownerKey("https://b", "one"));
    assert.notEqual(ownerKey("https://a", "one"), ownerKey("https://a", "two"));
    assert.equal(ownerKey("https://a", "one"), ownerKey("https://a", "one"));
  });
  test("OCI secret requests use the intended version and reject malformed bundle contents", async () => {
    const calls = [];
    let content = { contentType: "BASE64", content: Buffer.from("synthetic-value").toString("base64") };
    const reader = secretReaderForClient({ async getSecretBundle(request) {
      calls.push(request); return { secretBundle: { secretBundleContent: content } };
    } });
    assert.equal(await reader(secretId("database"), 3), "synthetic-value");
    assert.deepEqual(calls[0], { secretId: secretId("database"), versionNumber: 3 });
    await reader(secretId("session"));
    assert.deepEqual(calls[1], { secretId: secretId("session"), stage: "CURRENT" });
    for (const bad of [{ contentType: "PLAIN", content: "synthetic" }, { contentType: "BASE64", content: "%%%" },
      { contentType: "BASE64", content: "/w==" }]) {
      content = bad;
      await assert.rejects(reader(secretId("session")));
    }
  });
});

async function startProvider() {
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const key = { ...publicKey.export({ format: "jwk" }), kid: "test-key", use: "sig", alg: "RS256" };
  const codes = new Map();
  const controls = { claims: null, badSignature: false };
  let issuer;
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, issuer);
    res.setHeader("Content-Type", "application/json");
    if (url.pathname === "/jwks") return res.end(JSON.stringify({ keys: [key] }));
    if (url.pathname === "/authorize") {
      const params = url.searchParams;
      assert.equal(params.get("code_challenge_method"), "S256");
      assert.ok(params.get("state") && params.get("nonce"));
      const code = randomUUID();
      codes.set(code, { nonce: params.get("nonce"), challenge: params.get("code_challenge"),
        redirect: params.get("redirect_uri"), sub: params.get("subject") || "alice" });
      res.writeHead(302, { location: `${params.get("redirect_uri")}?code=${code}&state=${params.get("state")}` });
      return res.end();
    }
    if (url.pathname === "/token") {
      let body = "";
      for await (const chunk of req) body += chunk;
      const form = new URLSearchParams(body);
      const record = codes.get(form.get("code"));
      codes.delete(form.get("code"));
      if (!record || createHash("sha256").update(form.get("code_verifier") || "").digest("base64url") !== record.challenge
          || form.get("redirect_uri") !== record.redirect) {
        res.writeHead(400); return res.end(JSON.stringify({ error: "invalid_grant" }));
      }
      const now = Math.floor(Date.now() / 1000);
      const claims = { iss: issuer, sub: record.sub, aud: "synthetic-client", iat: now, exp: now + 300,
        nonce: record.nonce, email: "same-address@example.test", ...(controls.claims || {}) };
      const encode = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");
      const input = `${encode({ alg: "RS256", kid: "test-key" })}.${encode(claims)}`;
      const signature = sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url");
      const idToken = `${input}.${controls.badSignature ? "a".repeat(signature.length) : signature}`;
      controls.claims = null; controls.badSignature = false;
      return res.end(JSON.stringify({ access_token: "<synthetic-access>", token_type: "Bearer", expires_in: 300, id_token: idToken }));
    }
    res.writeHead(404); res.end("{}");
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  issuer = `http://127.0.0.1:${server.address().port}`;
  const config = new oidc.Configuration({ issuer, authorization_endpoint: `${issuer}/authorize`,
    token_endpoint: `${issuer}/token`, jwks_uri: `${issuer}/jwks`, response_types_supported: ["code"],
    id_token_signing_alg_values_supported: ["RS256"], token_endpoint_auth_methods_supported: ["client_secret_post"] },
  "synthetic-client", "synthetic-client-value");
  // Deliberately confined to this test provider. Runtime config requires HTTPS.
  oidc.allowInsecureRequests(config);
  return { server, config, controls };
}

describe("OIDC sessions, CSRF and user isolation", () => {
  let provider, server, base, sessionStore, tasks, attachments;
  before(async () => {
    provider = await startProvider();
    const config = { ...loadConfig(environment()), sessionSecret: "synthetic-session-".repeat(4), maxUploadBytes: 1024 };
    sessionStore = new session.MemoryStore();
    tasks = new MemoryTaskStore(); attachments = new FakeAttachmentStore();
    const auth = await createAuth({ config, store: sessionStore, oidcConfiguration: provider.config });
    server = createApp({ tasks, attachments, config, auth }).listen(0, "127.0.0.1");
    await new Promise((resolve) => server.once("listening", resolve));
    base = `http://127.0.0.1:${server.address().port}`;
  });
  after(async () => { server?.closeAllConnections(); provider?.server.closeAllConnections();
    await Promise.all([new Promise((r) => server?.close(r)), new Promise((r) => provider?.server.close(r))]); });
  function browser() {
    return { cookie: "", csrf: null, async request(path, options = {}) {
      const response = await fetch(base + path, { ...options, redirect: "manual", headers: {
        "x-forwarded-proto": "https", ...(this.cookie ? { cookie: this.cookie } : {}),
        ...(this.csrf ? { "x-csrf-token": this.csrf, origin: "https://app.example.test" } : {}),
        ...options.headers } });
      const cookie = response.headers.get("set-cookie");
      if (cookie) this.cookie = cookie.split(";", 1)[0];
      return response;
    } };
  }
  async function begin(client, subject = "alice") {
    const start = await client.request("/auth/login");
    assert.equal(start.status, 302);
    assert.match(start.headers.get("set-cookie"), /HttpOnly/);
    assert.match(start.headers.get("set-cookie"), /Secure/);
    assert.match(start.headers.get("set-cookie"), /SameSite=Lax/);
    const authorization = new URL(start.headers.get("location"));
    authorization.searchParams.set("subject", subject);
    const response = await fetch(authorization, { redirect: "manual" });
    const callback = new URL(response.headers.get("location"));
    return callback.pathname + callback.search;
  }
  async function login(subject) {
    const client = browser();
    const callback = await begin(client, subject);
    const beforeCookie = client.cookie;
    const response = await client.request(callback);
    assert.equal(response.status, 303, await response.text());
    assert.notEqual(client.cookie, beforeCookie);
    const state = await (await client.request("/auth/session")).json();
    assert.equal(state.authenticated, true);
    client.csrf = state.csrfToken;
    return client;
  }
  const jsonRequest = (method, body) => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

  test("anonymous API denied; HTTPS and CSRF required", async () => {
    assert.equal((await browser().request("/api/tasks")).status, 401);
    assert.equal((await fetch(`${base}/api/tasks`)).status, 400);
    const client = await login("alice");
    assert.equal((await client.request("/api/tasks", { ...jsonRequest("POST", { title: "blocked" }),
      headers: { "content-type": "application/json", "x-csrf-token": "wrong" } })).status, 403);
    assert.equal((await client.request("/api/tasks", { ...jsonRequest("POST", { title: "blocked" }),
      headers: { "content-type": "application/json", origin: "https://other.example.test" } })).status, 403);
  });
  test("wrong state, nonce, audience, expiry and signature are rejected; callback cannot replay", async () => {
    for (const kind of ["state", "nonce", "aud", "exp", "signature"]) {
      const client = browser();
      let callback = await begin(client);
      if (kind === "state") callback = callback.replace(/state=[^&]+/, "state=wrong");
      else if (kind === "signature") provider.controls.badSignature = true;
      else provider.controls.claims = { [kind]: kind === "exp" ? 1 : "wrong" };
      assert.equal((await client.request(callback)).status, 401, kind);
      assert.equal((await client.request("/api/tasks")).status, 401);
      assert.equal((await client.request(callback)).status, 400);
    }
  });
  test("two users cannot read, edit, delete or attach to each other's tasks", async () => {
    const alice = await login("alice"); const bob = await login("bob");
    const task = await (await alice.request("/api/tasks", jsonRequest("POST", { title: "Alice task" }))).json();
    const path = `/api/tasks/${task.id}`;
    assert.equal((await bob.request(path)).status, 404);
    assert.equal((await bob.request(path, jsonRequest("PATCH", { title: "stolen" }))).status, 404);
    assert.equal((await bob.request(path, { method: "DELETE" })).status, 404);
    assert.deepEqual(await (await bob.request("/api/tasks")).json(), []);
    assert.equal((await bob.request(`${path}/attachments/upload-url`, jsonRequest("POST", { filename: "a.txt", size: 3 }))).status, 404);
    const upload = await (await alice.request(`${path}/attachments/upload-url`, jsonRequest("POST", { filename: "a.txt", size: 3 }))).json();
    assert.equal((await bob.request(upload.uploadUrl, { method: "PUT", body: "abc", headers: { "content-type": "application/octet-stream" } })).status, 404);
    const claim = { objectName: upload.objectName, filename: "a.txt", size: 3 };
    assert.equal((await alice.request(`${path}/attachments`, jsonRequest("POST", claim))).status, 409);
    assert.equal((await alice.request(upload.uploadUrl, { method: "PUT", body: "abc", headers: { "content-type": "application/octet-stream" } })).status, 204);
    assert.equal((await alice.request(`${path}/attachments`, jsonRequest("POST", { ...claim, size: 2 }))).status, 409);
    const response = await alice.request(`${path}/attachments`, jsonRequest("POST", claim));
    assert.equal(response.status, 201);
    const attachment = await response.json();
    assert.equal((await alice.request(`${path}/attachments`, jsonRequest("POST", claim))).status, 409);
    assert.equal((await bob.request(`/api/attachments/${attachment.id}/download`)).status, 404);
    const download = await alice.request(`/api/attachments/${attachment.id}/download`);
    assert.match(download.headers.get("content-disposition"), /^attachment;/);
    assert.equal(await download.text(), "abc");
    assert.equal(attachments.lastUpload, null, "production must never issue write PARs");
  });
  test("logout destroys server session and absolute expiry rejects an existing cookie", async () => {
    const client = await login("logout-user");
    const oldCookie = client.cookie;
    assert.equal((await client.request("/auth/logout", { method: "POST" })).status, 204);
    client.cookie = oldCookie;
    assert.equal((await client.request("/api/tasks")).status, 401);
    const expired = await login("expired-user");
    await new Promise((resolve, reject) => sessionStore.all((err, sessions) => {
      if (err) return reject(err);
      const [id, value] = Object.entries(sessions).find(([, value]) => value.user?.owner === ownerKey(provider.config.serverMetadata().issuer, "expired-user"));
      value.user.expiresAt = 1;
      sessionStore.set(id, value, (error) => error ? reject(error) : resolve());
    }));
    assert.equal((await expired.request("/api/tasks")).status, 401);
  });
});
