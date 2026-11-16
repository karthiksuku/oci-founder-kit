import { setTimeout as sleep } from "node:timers/promises";
import { JobStore } from "./store.js";
import { workerPool } from "./runtime.js";
import { OciQueue } from "./queue.js";
import { publishOne, processOne } from "./processor.js";
import { logger } from "../../../fullstack-container/app/src/logger.js";

async function main() {
  if (process.env.APP_MODE !== "production") throw new Error("OCI worker requires explicit production configuration; use local tests for sandbox delivery");
  const pool = await workerPool(process.env);
  const store = new JobStore(pool, process.env.SAAS_ENVIRONMENT);
  const queue = await OciQueue.create(process.env);
  let stop = false, tick = 0;
  process.on("SIGTERM", () => { stop = true; });
  process.on("SIGINT", () => { stop = true; });
  try {
    while (!stop) {
      try {
        // Ownership defaults paused. No inherited scheduler or worker is taken over automatically.
        const active = await pool.query("SELECT 1 FROM saas_ownership WHERE environment=$1 AND owner='oci'", [store.environment]);
        if (!active.rowCount) { await sleep(5000); continue; }
        if (Date.now() - tick > 60000) {
          await store.scheduleTick();
          // Recover accepted work stranded by transport expiry, without changing its identity.
          await pool.query(`UPDATE saas_outbox o SET published_at=NULL,available_at=now(),lease=NULL,lease_until=NULL
            FROM saas_jobs j WHERE o.job_id=j.id AND j.environment=$1 AND j.state IN ('pending','running')
            AND (j.lease_until IS NULL OR j.lease_until<now()) AND o.published_at<now()-interval '10 minutes'`, [store.environment]);
          tick = Date.now();
        }
        for (let i = 0; i < 20 && await publishOne(store, queue); i++) { /* bounded drain */ }
        const messages = await queue.receive();
        for (const message of messages) await processOne(store, queue, message);
      } catch { logger.warn("worker operation failed; durable work retained"); await sleep(5000); }
    }
  } finally { await pool.end(); }
}
main().catch(() => { logger.error("worker startup failed; inspect private configuration"); process.exitCode = 1; });
