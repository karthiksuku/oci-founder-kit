import { setTimeout as sleep } from "node:timers/promises";
import { JobStore } from "./store.js";
import { workerPool } from "./runtime.js";
import { publishOne, processOne } from "./processor.js";
import { transferOwnership } from "./administration.js";
import { randomUUID } from "node:crypto";

if (process.env.APP_MODE !== "sandbox" || process.env.SAAS_LOCAL_ENABLE_JOBS !== "true") throw new Error("Explicit local synthetic jobs opt-in required");
const pool = await workerPool(process.env);
const store = new JobStore(pool, process.env.SAAS_ENVIRONMENT);
let stop = false;
process.on("SIGTERM", () => { stop = true; }); process.on("SIGINT", () => { stop = true; });
const messages = [];
const queue = { async send(content) { messages.push({ content, receipt: randomUUID() }); }, async remove() {}, async renew() {} };
try {
  const current = await pool.query("SELECT owner,generation FROM saas_ownership WHERE environment=$1", [store.environment]);
  if (current.rows[0]?.owner === "paused") await transferOwnership(store, { from: "paused", to: "oci", generation: current.rows[0].generation, evidenceSha256: "0".repeat(64) });
  await pool.query(`INSERT INTO saas_schedules(environment,id,version,owner_id,period_seconds,anchor,enabled)
    VALUES($1,'local-hourly',1,'sandbox',3600,date_trunc('hour',now()),true) ON CONFLICT DO NOTHING`, [store.environment]);
  while (!stop) {
    // This in-memory transport is local simulation; the durable ledger recovers unpublished work.
    await pool.query(`UPDATE saas_outbox o SET published_at=NULL,lease=NULL,lease_until=NULL FROM saas_jobs j
      WHERE o.job_id=j.id AND j.environment=$1 AND j.state IN ('pending','running') AND (j.lease_until IS NULL OR j.lease_until<now()) AND o.published_at<now()-interval '10 seconds'`, [store.environment]);
    await store.scheduleTick();
    for (let i = 0; i < 20 && await publishOne(store, queue); i++) { /* bounded */ }
    for (const message of messages.splice(0)) await processOne(store, queue, message);
    await sleep(1000);
  }
} finally { await pool.end(); }
