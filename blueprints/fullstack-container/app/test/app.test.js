// Behavioural tests for the Taskboard API, run with `node --test`.
// The stores are in-memory test doubles from ./fakes.js; nothing here needs
// a database, a network or an OCI account.

import { test, describe, before, after } from "node:test";
import assert from "node:assert/strict";
import { createApp } from "../src/app.js";
import { loadConfig } from "../src/config.js";
import { MemoryTaskStore, FakeAttachmentStore } from "./fakes.js";

function startServer(overrides = {}) {
  const tasks = overrides.tasks ?? new MemoryTaskStore();
  const attachments = "attachments" in overrides ? overrides.attachments : new FakeAttachmentStore();
  const app = createApp({ tasks, attachments, config: { maxUploadBytes: 1024, ...overrides.config } });
  return new Promise((resolve) => {
    const server = app.listen(0, "127.0.0.1", () => {
      const base = `http://127.0.0.1:${server.address().port}`;
      resolve({ server, base, tasks, attachments });
    });
  });
}

async function json(res) {
  const body = await res.json();
  return { status: res.status, body };
}

describe("health", () => {
  let ctx;
  before(async () => { ctx = await startServer(); });
  after(() => ctx.server.close());

  test("liveness answers without touching dependencies", async () => {
    const { status, body } = await json(await fetch(`${ctx.base}/healthz`));
    assert.equal(status, 200);
    assert.equal(body.status, "ok");
  });

  test("readiness checks the database", async () => {
    assert.equal((await fetch(`${ctx.base}/readyz`)).status, 200);
    ctx.tasks.healthy = false;
    const { status, body } = await json(await fetch(`${ctx.base}/readyz`));
    assert.equal(status, 503);
    assert.equal(body.status, "unavailable");
    ctx.tasks.healthy = true;
  });
});

describe("tasks", () => {
  let ctx;
  before(async () => { ctx = await startServer(); });
  after(() => ctx.server.close());

  test("create, list, update and delete", async () => {
    const created = await json(await fetch(`${ctx.base}/api/tasks`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "Write the migration plan" }),
    }));
    assert.equal(created.status, 201);
    assert.equal(created.body.title, "Write the migration plan");
    assert.equal(created.body.done, false);

    const list = await json(await fetch(`${ctx.base}/api/tasks`));
    assert.deepEqual(list.body.map((t) => t.id), [created.body.id]);

    const updated = await json(await fetch(`${ctx.base}/api/tasks/${created.body.id}`, {
      method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ done: true }),
    }));
    assert.equal(updated.body.done, true);

    assert.equal((await fetch(`${ctx.base}/api/tasks/${created.body.id}`, { method: "DELETE" })).status, 204);
    assert.equal((await fetch(`${ctx.base}/api/tasks/${created.body.id}`)).status, 404);
  });

  test("validates input", async () => {
    for (const body of [{}, { title: "" }, { title: "x".repeat(201) }, { title: 42 }]) {
      const res = await fetch(`${ctx.base}/api/tasks`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      assert.equal(res.status, 400, JSON.stringify(body));
      assert.match((await res.json()).error, /title/);
    }
    const bad = await fetch(`${ctx.base}/api/tasks/not-a-number`);
    assert.equal(bad.status, 404);
  });

  test("unknown routes return JSON 404", async () => {
    const { status, body } = await json(await fetch(`${ctx.base}/api/nope`));
    assert.equal(status, 404);
    assert.equal(body.error, "Not found");
  });

  test("store failures return 500 without leaking details", async () => {
    ctx.tasks.failNext = new Error("connection refused at 10.0.2.15:5432");
    const { status, body } = await json(await fetch(`${ctx.base}/api/tasks`));
    assert.equal(status, 500);
    assert.equal(body.error, "Something went wrong. Try again.");
    assert.doesNotMatch(JSON.stringify(body), /10\.0\.2\.15/);
  });
});

describe("attachments", () => {
  let ctx;
  let taskId;
  before(async () => {
    ctx = await startServer();
    taskId = (await ctx.tasks.create("Upload the architecture diagram")).id;
  });
  after(() => ctx.server.close());

  test("upload URL is scoped to the task and a safe object name", async () => {
    const { status, body } = await json(await fetch(`${ctx.base}/api/tasks/${taskId}/attachments/upload-url`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "../../etc/diagram v2.png", size: 200 }),
    }));
    assert.equal(status, 201);
    assert.match(body.objectName, new RegExp(`^tasks/${taskId}/[0-9a-f-]{36}-diagram_v2\\.png$`));
    assert.ok(body.uploadUrl.startsWith("https://"));
    assert.equal(ctx.attachments.lastUpload.objectName, body.objectName);
  });

  test("rejects files over the size limit", async () => {
    const res = await fetch(`${ctx.base}/api/tasks/${taskId}/attachments/upload-url`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "big.bin", size: 4096 }),
    });
    assert.equal(res.status, 413);
  });

  test("records an uploaded attachment and redirects downloads to a short-lived URL", async () => {
    const { body: upload } = await json(await fetch(`${ctx.base}/api/tasks/${taskId}/attachments/upload-url`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "notes.txt", size: 10 }),
    }));
    const recorded = await json(await fetch(`${ctx.base}/api/tasks/${taskId}/attachments`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ objectName: upload.objectName, filename: "notes.txt", size: 10 }),
    }));
    assert.equal(recorded.status, 201);
    const download = await fetch(`${ctx.base}/api/attachments/${recorded.body.id}/download`, { redirect: "manual" });
    assert.equal(download.status, 302);
    assert.ok(download.headers.get("location").startsWith("https://"));
    const task = await json(await fetch(`${ctx.base}/api/tasks/${taskId}`));
    assert.equal(task.body.attachments.length, 1);
  });

  test("refuses to record an object outside the task's prefix", async () => {
    const res = await fetch(`${ctx.base}/api/tasks/${taskId}/attachments`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ objectName: "tasks/999/x.txt", filename: "x.txt", size: 1 }),
    });
    assert.equal(res.status, 400);
  });

  test("attachments are unavailable when storage is not configured", async () => {
    const plain = await startServer({ attachments: null });
    try {
      const res = await fetch(`${plain.base}/api/tasks/${taskId}/attachments/upload-url`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ filename: "a.txt", size: 1 }),
      });
      assert.equal(res.status, 501);
    } finally {
      plain.server.close();
    }
  });
});

describe("config", () => {
  test("requires a database URL and reads optional storage settings", () => {
    assert.throws(() => loadConfig({}), /DATABASE_URL/);
    const config = loadConfig({ DATABASE_URL: "postgres://u:p@db:5432/app", PORT: "9090",
      OCI_BUCKET: "uploads", OCI_NAMESPACE: "ns", OCI_REGION: "ap-melbourne-1" });
    assert.equal(config.port, 9090);
    assert.deepEqual(config.storage, { bucket: "uploads", namespace: "ns", region: "ap-melbourne-1", auth: "resource-principal" });
  });

  test("database TLS verifies certificates, with an optional CA bundle", () => {
    const base = { DATABASE_URL: "postgres://u:p@db.example/app" };
    assert.deepEqual(loadConfig(base).databaseTls, { rejectUnauthorized: true });
    const ca = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----";
    assert.deepEqual(loadConfig({ ...base, DATABASE_CA_CERT: ca }).databaseTls, { rejectUnauthorized: true, ca });
    assert.equal(loadConfig({ ...base, DATABASE_SSL: "false" }).databaseTls, false);
  });

  test("listens on loopback unless HOST says otherwise", () => {
    assert.equal(loadConfig({ DATABASE_URL: "postgres://u:p@db/app" }).host, "127.0.0.1");
    assert.equal(loadConfig({ DATABASE_URL: "postgres://u:p@db/app", HOST: "10.20.2.10" }).host, "10.20.2.10");
  });

  test("storage stays off unless bucket and namespace are both set", () => {
    const config = loadConfig({ DATABASE_URL: "postgres://u:p@db/app", OCI_BUCKET: "uploads" });
    assert.equal(config.storage, null);
  });

  test("rejects a bad port and never echoes the database URL", () => {
    assert.throws(() => loadConfig({ DATABASE_URL: "postgres://u:secretpw@db/app", PORT: "x" }), (err) => {
      assert.match(err.message, /PORT/);
      assert.doesNotMatch(err.message, /secretpw/);
      return true;
    });
  });
});
