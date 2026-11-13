// Integration test for PgTaskStore against a real PostgreSQL.
// Runs only when TEST_DATABASE_URL is set, for example:
//   docker run -d --rm --name taskboard-pg -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=test postgres:16-alpine
//   TEST_DATABASE_URL=postgres://postgres:test@127.0.0.1:55432/postgres npm test

import { test, describe, before, after } from "node:test";
import assert from "node:assert/strict";
import pg from "pg";
import session from "express-session";
import connectPgSimple from "connect-pg-simple";
import { randomUUID } from "node:crypto";
import { PgTaskStore } from "../src/stores/pg-task-store.js";

const url = process.env.TEST_DATABASE_URL;

describe("PgTaskStore against PostgreSQL", { skip: url ? false : "TEST_DATABASE_URL is not set" }, () => {
  let pool;
  let store;
  let sessions;

  before(async () => {
    pool = new pg.Pool({ connectionString: url });
    await pool.query("DROP TABLE IF EXISTS web_sessions; DROP TABLE IF EXISTS upload_intents; DROP TABLE IF EXISTS attachments; DROP TABLE IF EXISTS tasks;");
    store = new PgTaskStore(pool);
    await store.migrate();
    await store.migrate(); // idempotent
    sessions = new (connectPgSimple(session))({ pool, tableName: "web_sessions", createTableIfMissing: true });
  });

  after(async () => {
    sessions.close();
    await pool.query("DROP TABLE IF EXISTS web_sessions; DROP TABLE IF EXISTS upload_intents; DROP TABLE IF EXISTS attachments; DROP TABLE IF EXISTS tasks;");
    await pool.end();
  });

  test("ping", async () => {
    await store.ping();
  });

  test("task lifecycle with attachments and cascade delete", async () => {
    const task = await store.create("Rehearse the cutover");
    assert.equal(task.done, false);
    assert.match(task.createdAt, /^\d{4}-\d{2}-\d{2}T/);

    const updated = await store.update(task.id, { done: true });
    assert.equal(updated.done, true);
    assert.equal(updated.title, "Rehearse the cutover");
    assert.equal(await store.update(999999, { done: true }), null);

    const attachment = await store.addAttachment(task.id, {
      objectName: `tasks/${task.id}/00000000-0000-0000-0000-000000000000-plan.pdf`, filename: "plan.pdf", size: 1234 });
    assert.equal(attachment.size, 1234);
    assert.deepEqual(await store.getAttachment(attachment.id), attachment);

    const full = await store.get(task.id);
    assert.equal(full.attachments.length, 1);

    assert.equal(await store.remove(task.id), true);
    assert.equal(await store.get(task.id), null);
    assert.equal(await store.getAttachment(attachment.id), null);
    assert.equal(await store.remove(task.id), false);
  });

  test("the database enforces the title limit too", async () => {
    await assert.rejects(store.create("x".repeat(201)));
  });

  test("parameters are never interpolated", async () => {
    const title = "x'); DROP TABLE tasks; --";
    const task = await store.create(title);
    assert.equal((await store.get(task.id)).title, title);
    assert.ok((await store.list()).length >= 1);
  });

  test("database queries isolate two owners and atomically claim completed upload metadata", async () => {
    const task = await store.create("Private task", "owner-a");
    assert.equal(await store.get(task.id, "owner-b"), null);
    assert.equal(await store.update(task.id, { title: "stolen" }, "owner-b"), null);
    assert.equal(await store.remove(task.id, "owner-b"), false);
    assert.deepEqual(await store.list("owner-b"), []);
    const upload = { uploadId: randomUUID(), objectName: `tasks/${task.id}/${randomUUID()}-file.txt`, filename: "file.txt", size: 3 };
    assert.equal(await store.addAttachment(task.id, upload, "owner-b"), null);
    assert.equal(await store.createUploadIntent(task.id, upload, "owner-b"), false);
    assert.equal(await store.createUploadIntent(task.id, upload, "owner-a"), true);
    assert.equal(await store.startUpload(upload.uploadId, "owner-b"), null);
    assert.equal(await store.claimUpload(task.id, upload, "owner-a"), null);
    assert.equal((await store.startUpload(upload.uploadId, "owner-a")).size, 3);
    assert.equal(await store.startUpload(upload.uploadId, "owner-a"), null);
    assert.equal(await store.finishUpload(upload.uploadId, "owner-a"), true);
    assert.equal(await store.claimUpload(task.id, { ...upload, size: 4 }, "owner-a"), null);
    assert.equal(await store.claimUpload(task.id, upload, "owner-b"), null);
    const claimed = (await Promise.all([
      store.claimUpload(task.id, upload, "owner-a"), store.claimUpload(task.id, upload, "owner-a"),
    ])).filter(Boolean);
    assert.equal(claimed.length, 1);
    assert.equal(await store.getAttachment(claimed[0].id, "owner-b"), null);
    const restartedStore = new PgTaskStore(pool);
    assert.equal((await restartedStore.getAttachment(claimed[0].id, "owner-a")).filename, "file.txt");
    const expired = { ...upload, uploadId: randomUUID(), objectName: `tasks/${task.id}/${randomUUID()}-expired.txt` };
    await store.createUploadIntent(task.id, expired, "owner-a");
    await pool.query("UPDATE upload_intents SET expires_at = now() - interval '1 minute'");
    assert.equal(await store.startUpload(expired.uploadId, "owner-a"), null);
    await store.remove(task.id, "owner-a");
    assert.equal(await store.getAttachment(claimed[0].id, "owner-a"), null);
  });

  test("Postgres sessions persist across store instances, expire, and are revoked on logout", async () => {
    const invoke = (target, method, ...args) => new Promise((resolve, reject) => target[method](...args,
      (error, value) => error ? reject(error) : resolve(value)));
    const key = randomUUID();
    await invoke(sessions, "set", key, { cookie: { expires: new Date(Date.now() + 60000) }, user: { owner: "owner-a" } });
    const reopened = new (connectPgSimple(session))({ pool, tableName: "web_sessions" });
    try {
      assert.equal((await invoke(reopened, "get", key)).user.owner, "owner-a");
      await invoke(reopened, "destroy", key);
      assert.equal(await invoke(sessions, "get", key), undefined);
      await invoke(sessions, "set", key, { cookie: { expires: new Date(1) }, user: { owner: "owner-a" } });
      assert.equal(await invoke(reopened, "get", key), undefined);
    } finally { reopened.close(); }
  });
});
