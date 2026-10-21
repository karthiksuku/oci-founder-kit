// Integration test for PgTaskStore against a real PostgreSQL.
// Runs only when TEST_DATABASE_URL is set, for example:
//   docker run -d --rm --name taskboard-pg -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=test postgres:16-alpine
//   TEST_DATABASE_URL=postgres://postgres:test@127.0.0.1:55432/postgres npm test

import { test, describe, before, after } from "node:test";
import assert from "node:assert/strict";
import pg from "pg";
import { PgTaskStore } from "../src/stores/pg-task-store.js";

const url = process.env.TEST_DATABASE_URL;

describe("PgTaskStore against PostgreSQL", { skip: url ? false : "TEST_DATABASE_URL is not set" }, () => {
  let pool;
  let store;

  before(async () => {
    pool = new pg.Pool({ connectionString: url });
    await pool.query("DROP TABLE IF EXISTS attachments; DROP TABLE IF EXISTS tasks;");
    store = new PgTaskStore(pool);
    await store.migrate();
    await store.migrate(); // idempotent
  });

  after(async () => {
    await pool.query("DROP TABLE IF EXISTS attachments; DROP TABLE IF EXISTS tasks;");
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
});
