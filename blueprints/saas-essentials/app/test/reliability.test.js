import assert from "node:assert/strict";
import { test, before, after, beforeEach } from "node:test";
import { randomBytes, randomUUID, createHmac } from "node:crypto";
import pg from "pg";
import { JobStore, RequestStore } from "../src/store.js";
import { publishOne, processOne } from "../src/processor.js";
import { verifyWebhook, parseEvent } from "../src/webhook.js";
import { transferOwnership, replayDeadJob } from "../src/administration.js";
import { createApp } from "../../../fullstack-container/app/src/app.js";
import { FakeAttachmentStore } from "../../../fullstack-container/app/test/fakes.js";
import { webhookRoutes } from "../src/webhook.js";
import { enqueueWakeup } from "../../experimental/enqueue.mjs";
import { OciQueue } from "../src/queue.js";

const secret = randomBytes(32).toString("hex");
const raw = Buffer.from(JSON.stringify({ id: "event_1", type: "request.upsert", data: { externalId: "external_1", version: 2, title: "New title", done: false } }));
const stamp = Math.floor(Date.now() / 1000);
const header = `t=${stamp},v1=${createHmac("sha256", secret).update(`${stamp}.`).update(raw).digest("hex")}`;
test("signatures bind exact bytes and expire; unsupported payloads are refused", () => {
  assert(verifyWebhook(raw, header, secret));
  assert(!verifyWebhook(Buffer.concat([raw, Buffer.from(" ")]), header, secret));
  assert(!verifyWebhook(raw, header, secret, Date.now() + 301000));
  assert(!verifyWebhook(raw, header, "wrong"));
  assert.equal(parseEvent(raw).type, "request.upsert");
  assert.throws(() => parseEvent(Buffer.from('{"type":"payment"}')));
});
test("OCI adapter uses bounded delivery, renewal and exact receipts", async () => {
  const calls = [];
  const queue = new OciQueue({
    putMessages: async (input) => { calls.push(input); return { putMessages: { messages: [{ id: "accepted" }] } }; },
    getMessages: async (input) => { calls.push(input); return { getMessages: { messages: [] } }; },
    updateMessage: async (input) => calls.push(input), deleteMessage: async (input) => calls.push(input),
  }, "fixture");
  await queue.send("payload"); await queue.receive(); await queue.renew("receipt", 60); await queue.remove("receipt");
  assert.equal(calls[1].limit, 1); assert.equal(calls[1].visibilityInSeconds, 60);
  assert.equal(calls[2].messageReceipt, "receipt"); assert.equal(calls[3].queueId, "fixture");
});

test("durable PostgreSQL reliability and isolation", { skip: !process.env.SAAS_TEST_DATABASE_URL }, async (t) => {
  const schema = `saas_test_${randomBytes(8).toString("hex")}`;
  const admin = new pg.Pool({ connectionString: process.env.SAAS_TEST_DATABASE_URL });
  await admin.query(`CREATE SCHEMA ${schema}`);
  const pool = new pg.Pool({ connectionString: process.env.SAAS_TEST_DATABASE_URL, options: `-c search_path=${schema}`, max: 8 });
  const store = new JobStore(pool, "rehearsal");
  const requests = new RequestStore(pool, store);
  try {
    await requests.migrate(); await store.migrate();
    async function reset(owner = "oci") {
      await pool.query("TRUNCATE saas_replays,saas_schedule_runs,saas_schedules,saas_external_requests,saas_inbox,saas_outbox,saas_jobs,saas_ownership,attachments,upload_intents,tasks CASCADE");
      await pool.query("INSERT INTO saas_ownership(environment,owner,evidence_sha256) VALUES($1,$2,$3)", [store.environment, owner, "a".repeat(64)]);
    }
    const envelope = (id, environment = store.environment) => ({ content: JSON.stringify({ schema: "oci-kit-job/1", id, environment }), receipt: randomUUID() });
    const queue = { sent: [], deleted: [], async send(content) { this.sent.push(content); }, async remove(receipt) { this.deleted.push(receipt); }, async renew() {} };
    await t.test("request and outbox commit atomically and stay private to their owner", async () => {
      await reset();
      const request = await requests.create("Urgent request", "owner-a");
      assert.equal((await requests.list("owner-b")).length, 0);
      assert.equal(await requests.get(request.id, "owner-b"), null);
      const jobs = await store.jobs("owner-a"); assert.equal(jobs.length, 1);
      assert.equal((await store.jobs("owner-b")).length, 0);
      assert.equal((await pool.query("SELECT count(*)::integer AS count FROM saas_outbox")).rows[0].count, 1);
    });
    await t.test("HTTP webhook acknowledges committed work; authenticated requests and attachments stay private", async () => {
      await reset();
      const auth = {
        middleware: (req, res, next) => { req.ownerId = req.get("x-test-owner"); next(); },
        sessionState: (_req, _res, next) => next(), mount() {},
        requireUser: (req, res, next) => req.ownerId ? next() : res.status(401).end(),
        csrf: (req, res, next) => req.method === "GET" || req.get("x-test-csrf") === "valid" ? next() : res.status(403).end(),
      };
      const app = createApp({ tasks: requests, attachments: new FakeAttachmentStore(), auth,
        config: { mode: "production", trustProxy: ["127.0.0.1/32"], maxUploadBytes: 1000 },
        mountBeforeBody: webhookRoutes({ jobs: store, secret, owner: "owner-a" }),
        mountApi: (router) => router.get("/api/jobs", async (req, res) => res.json(await store.jobs(req.ownerId))) });
      const server = await new Promise((resolve) => { const listening = app.listen(0, "127.0.0.1", () => resolve(listening)); });
      const origin = `http://127.0.0.1:${server.address().port}`;
      const call = (path, method = "GET", body, owner, headers = {}) => fetch(origin + path, { method,
        headers: { "x-forwarded-proto": "https", ...(owner ? { "x-test-owner": owner, "x-test-csrf": "valid" } : {}),
          ...(body ? { "content-type": "application/json" } : {}), ...headers }, body });
      try {
        assert.equal((await call("/api/jobs")).status, 401);
        assert.equal((await call("/api/tasks", "POST", JSON.stringify({ title: "private" }), "owner-a", { "x-test-csrf": "bad" })).status, 403);
        const accepted = await call("/webhooks/requests", "POST", raw, undefined, { "x-kit-webhook-signature": header });
        assert.equal(accepted.status, 202);
        assert.equal((await store.jobs("owner-a")).length, 1);
        assert.equal((await call("/webhooks/requests", "POST", Buffer.concat([raw, Buffer.from(" ")]), undefined, { "x-kit-webhook-signature": header })).status, 400);
        const created = await call("/api/tasks", "POST", JSON.stringify({ title: "private" }), "owner-a");
        const task = await created.json(); assert.equal(created.status, 201);
        const upload = await (await call(`/api/tasks/${task.id}/attachments/upload-url`, "POST", JSON.stringify({ filename: "note.txt", size: 4 }), "owner-a")).json();
        assert.equal((await call(upload.uploadUrl, "PUT", "test", "owner-b", { "content-type": "application/octet-stream" })).status, 404);
        assert.equal((await call(upload.uploadUrl, "PUT", "test", "owner-a", { "content-type": "application/octet-stream" })).status, 204);
        const attachment = await (await call(`/api/tasks/${task.id}/attachments`, "POST", JSON.stringify({ objectName: upload.objectName, filename: "note.txt", size: 4 }), "owner-a")).json();
        assert.equal((await call(`/api/attachments/${attachment.id}/download`, "GET", undefined, "owner-b")).status, 404);
        assert.equal(await (await call(`/api/attachments/${attachment.id}/download`, "GET", undefined, "owner-a")).text(), "test");
        assert.deepEqual(await (await call("/api/jobs", "GET", undefined, "owner-b")).json(), []);
      } finally { await new Promise((resolve) => server.close(resolve)); }
    });
    await t.test("duplicate webhook deliveries create exactly one job; changed bytes conflict", async () => {
      await reset();
      const accepted = await Promise.all(Array.from({ length: 8 }, () => store.accept(parseEvent(raw), raw, "owner-a")));
      assert.equal(accepted.filter((item) => !item.duplicate).length, 1);
      assert.equal(new Set(accepted.map((item) => item.id)).size, 1);
      await assert.rejects(store.accept(parseEvent(raw), Buffer.concat([raw, Buffer.from(" ")]), "owner-a"), /EVENT_ID_CONFLICT/);
    });
    await t.test("lost enqueue response republishes the same identity without losing accepted work", async () => {
      await reset(); queue.sent = [];
      await requests.create("Request", "owner-a");
      const lost = { async send(content) { queue.sent.push(content); throw new Error("response lost"); } };
      await assert.rejects(publishOne(store, lost));
      await pool.query("UPDATE saas_outbox SET lease_until=now()-interval '1 second'");
      await publishOne(store, queue);
      assert.equal(queue.sent.length, 2); assert.equal(queue.sent[0], queue.sent[1]);
      const message = { content: queue.sent[0], receipt: "first" };
      assert.equal(await processOne(store, queue, message), "done");
      assert.equal(await processOne(store, queue, { ...message, receipt: "second" }), "duplicate");
    });
    await t.test("crashed worker lease expires and stale worker cannot commit effects", async () => {
      await reset(); await requests.create("Request", "owner-a");
      const id = (await store.jobs("owner-a"))[0].id;
      const old = await store.claim(id); assert.equal((await store.claim(id)).state, "busy");
      await pool.query("UPDATE saas_jobs SET lease_until=now()-interval '1 second' WHERE id=$1", [id]);
      const replacement = await store.claim(id); await assert.rejects(store.perform(old), /LEASE_LOST/);
      await store.perform(replacement); assert.equal((await store.jobs("owner-a"))[0].attempts, 2);
    });
    await t.test("lost delete response leaves completed work safe for redelivery", async () => {
      await reset(); await requests.create("Request", "owner-a"); const id = (await store.jobs("owner-a"))[0].id;
      assert.equal(await processOne(store, { ...queue, async remove() { throw new Error("lost"); } }, envelope(id)), "retry");
      assert.equal((await store.jobs("owner-a"))[0].state, "done");
      assert.equal(await processOne(store, queue, envelope(id)), "duplicate");
      assert.equal((await store.jobs("owner-a"))[0].attempts, 1);
    });
    await t.test("poisoned job stops after five attempts; reviewed replay keeps exact identity", async () => {
      await reset();
      const accepted = await store.accept(parseEvent(raw), raw, "owner-a");
      await pool.query("UPDATE saas_jobs SET payload='{}'::jsonb WHERE id=$1", [accepted.id]);
      for (let i = 0; i < 5; i++) assert.equal(await processOne(store, queue, envelope(accepted.id)), "retry");
      assert.equal(await processOne(store, queue, envelope(accepted.id)), "dead");
      const before = queue.deleted.length;
      await processOne(store, queue, envelope(accepted.id)); assert.equal(queue.deleted.length, before);
      const other = new JobStore(pool, "production");
      await assert.rejects(replayDeadJob(other, { id: accepted.id, replayCount: 0, evidenceSha256: "b".repeat(64) }));
      await replayDeadJob(store, { id: accepted.id, replayCount: 0, evidenceSha256: "b".repeat(64) });
      await assert.rejects(replayDeadJob(store, { id: accepted.id, replayCount: 0, evidenceSha256: "b".repeat(64) }));
      assert.equal((await store.jobs("owner-a"))[0].id, accepted.id);
    });
    await t.test("out-of-order events cannot overwrite a newer request snapshot", async () => {
      await reset();
      const newer = await store.accept(parseEvent(raw), raw, "owner-a");
      await processOne(store, queue, envelope(newer.id));
      const olderEvent = parseEvent(raw); olderEvent.id = "older"; olderEvent.data.version = 1; olderEvent.data.title = "Old title";
      const old = await store.accept(olderEvent, Buffer.from(JSON.stringify(olderEvent)), "owner-a");
      await processOne(store, queue, envelope(old.id));
      assert.equal((await requests.list("owner-a"))[0].title, "New title");
      assert.equal((await requests.list("owner-a")).length, 1);
    });
    await t.test("missed UTC schedules coalesce once and report skipped occurrences", async () => {
      await reset();
      await pool.query("INSERT INTO saas_schedules(environment,id,version,owner_id,period_seconds,anchor,enabled) VALUES($1,'hourly',1,'owner-a',3600,'2026-01-01T00:00:00Z',true)", [store.environment]);
      const outcomes = await Promise.all([store.scheduleTick(new Date("2026-01-01T05:30:00Z")), store.scheduleTick(new Date("2026-01-01T05:30:00Z"))]);
      assert.equal(outcomes.reduce((n, row) => n + row.enqueued, 0), 1);
      assert.equal(outcomes.reduce((n, row) => n + row.skipped, 0), 5);
      assert.equal((await store.scheduleTick(new Date("2026-01-01T05:59:59Z"))).enqueued, 0);
      assert.equal((await store.scheduleTick(new Date("2026-01-01T06:00:00Z"))).enqueued, 1);
    });
    await t.test("interrupted ownership transfer stays paused and fences prior worker claims", async () => {
      await reset(); await requests.create("Request", "owner-a"); const id = (await store.jobs("owner-a"))[0].id;
      const old = await store.claim(id);
      await transferOwnership(store, { from: "oci", to: "paused", generation: 1, evidenceSha256: "c".repeat(64) });
      await assert.rejects(store.perform(old), /OWNERSHIP_CHANGED/);
      assert.equal((await store.claim(id)).state, "paused");
      assert.equal((await store.scheduleTick()).state, "paused");
      await assert.rejects(transferOwnership(store, { from: "source", to: "oci", generation: 1, evidenceSha256: "c".repeat(64) }));
      await assert.rejects(transferOwnership(store, { from: "paused", to: "oci", generation: 1, evidenceSha256: "c".repeat(64) }));
    });
    await t.test("restricted worker grants permit cursor progress but deny ownership and schedule administration", async () => {
      await reset();
      const role = `worker_${randomBytes(8).toString("hex")}`;
      await pool.query(`CREATE ROLE ${role}`);
      let restricted;
      try {
        await pool.query(`GRANT USAGE ON SCHEMA ${schema} TO ${role}`);
        await pool.query(`GRANT SELECT ON saas_ownership,saas_schedules TO ${role}`);
        await pool.query(`GRANT UPDATE(lock_guard) ON saas_ownership TO ${role}`);
        await pool.query(`GRANT UPDATE(last_due,skipped) ON saas_schedules TO ${role}`);
        await pool.query(`GRANT SELECT,INSERT ON saas_schedule_runs,saas_jobs,saas_outbox TO ${role}`);
        await pool.query("INSERT INTO saas_schedules(environment,id,version,owner_id,period_seconds,anchor,enabled) VALUES($1,'hourly',1,'owner-a',3600,date_trunc('hour',now()),true)", [store.environment]);
        restricted = new pg.Pool({ connectionString: process.env.SAAS_TEST_DATABASE_URL, options: `-c search_path=${schema} -c role=${role}` });
        const runtime = new JobStore(restricted, store.environment);
        assert.equal((await runtime.scheduleTick()).enqueued, 1);
        for (const sql of ["UPDATE saas_ownership SET owner='source'", "UPDATE saas_ownership SET generation=99", "UPDATE saas_ownership SET evidence_sha256=repeat('f',64)", "UPDATE saas_schedules SET enabled=false", "UPDATE saas_schedules SET period_seconds=7200"]) {
          await assert.rejects(restricted.query(sql), (error) => error.code === "42501");
        }
        await assert.rejects(restricted.query("UPDATE saas_ownership SET lock_guard=true"), (error) => error.code === "23514");
      } finally {
        if (restricted) await restricted.end();
        await pool.query(`DROP OWNED BY ${role}`); await pool.query(`DROP ROLE ${role}`);
      }
    });
    await t.test("duplicate scheduler wakeups use the durable cursor", async () => {
      await reset();
      await pool.query("INSERT INTO saas_schedules(environment,id,version,owner_id,period_seconds,anchor,enabled) VALUES($1,'hourly',1,'owner-a',3600,date_trunc('hour',now()),true)", [store.environment]);
      queue.sent = [];
      await enqueueWakeup(queue, store.environment); await enqueueWakeup(queue, store.environment);
      for (const content of queue.sent) assert.equal(await processOne(store, queue, { content, receipt: randomUUID() }), "schedule-wakeup");
      assert.equal((await store.jobs("owner-a")).length, 1);
    });
    await t.test("cross-environment and unknown jobs are never acknowledged or executed", async () => {
      await reset(); await requests.create("Request", "owner-a"); const id = (await store.jobs("owner-a"))[0].id;
      const before = queue.deleted.length;
      assert.equal(await processOne(store, queue, envelope(id, "production")), "foreign-or-invalid");
      assert.equal(await processOne(store, queue, envelope(randomUUID())), "foreign");
      assert.equal(queue.deleted.length, before); assert.equal((await store.jobs("owner-a"))[0].attempts, 0);
    });
  } finally {
    await pool.end(); await admin.query(`DROP SCHEMA ${schema} CASCADE`); await admin.end();
  }
});
