// These functions are deliberately not exposed over HTTP or run by the worker.
// Production invocation belongs to an authorized, exact-plan-reviewed DB change.
import { transaction } from "./store.js";

function evidence(value) {
  if (!/^[0-9a-f]{64}$/.test(value)) throw new Error("Reviewed evidence digest required");
}
export async function transferOwnership(store, { from, to, generation, evidenceSha256 }) {
  evidence(evidenceSha256);
  if (!["source", "paused", "oci"].includes(from) || !["source", "paused", "oci"].includes(to)
      || from === to || (from !== "paused" && to !== "paused")) throw new Error("Pause and verify the old owner before activating another owner");
  return transaction(store.pool, async (client) => {
    const { rows } = await client.query(`UPDATE saas_ownership SET owner=$4,generation=generation+1,evidence_sha256=$5
      WHERE environment=$1 AND owner=$2 AND generation=$3 RETURNING generation`, [store.environment, from, generation, to, evidenceSha256]);
    if (rows.length !== 1) throw new Error("Stale ownership plan");
    return rows[0].generation;
  });
}
export async function replayDeadJob(store, { id, replayCount, evidenceSha256 }) {
  evidence(evidenceSha256);
  return transaction(store.pool, async (client) => {
    const { rows } = await client.query(`UPDATE saas_jobs SET state='pending',attempts=0,replay_count=replay_count+1,
      lease=NULL,lease_until=NULL,error_code=NULL WHERE id=$1 AND environment=$2 AND state='dead' AND replay_count=$3 RETURNING replay_count`, [id, store.environment, replayCount]);
    if (rows.length !== 1) throw new Error("Replay scope changed or job is not dead");
    await client.query("INSERT INTO saas_replays(environment,job_id,replay_count,evidence_sha256) VALUES($1,$2,$3,$4)", [store.environment, id, rows[0].replay_count, evidenceSha256]);
    await client.query("UPDATE saas_outbox SET published_at=NULL,available_at=now(),lease=NULL,lease_until=NULL WHERE job_id=$1", [id]);
  });
}
