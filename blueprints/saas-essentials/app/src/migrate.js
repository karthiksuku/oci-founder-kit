import { workerPool } from "./runtime.js";
import { JobStore, RequestStore } from "./store.js";
// Only local setup is directly executable. Production SQL must enter the owner's reviewed DB change process.
if (process.env.APP_MODE !== "sandbox") throw new Error("Review schema.sql and the existing task schema with your authorized database administrator");
const pool = await workerPool(process.env);
try {
  const jobs = new JobStore(pool, process.env.SAAS_ENVIRONMENT);
  await new RequestStore(pool, jobs).migrate();
  await jobs.migrate();
  await pool.query("INSERT INTO saas_ownership(environment,owner,evidence_sha256) VALUES($1,'paused',$2) ON CONFLICT DO NOTHING", [jobs.environment, "0".repeat(64)]);
} finally { await pool.end(); }
