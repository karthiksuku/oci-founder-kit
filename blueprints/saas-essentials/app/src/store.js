import { randomUUID, createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { PgTaskStore } from "../../../fullstack-container/app/src/stores/pg-task-store.js";

export async function transaction(pool, work) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const value = await work(client);
    await client.query("COMMIT");
    return value;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally { client.release(); }
}

export class JobStore {
  constructor(pool, environment) {
    if (!/^[a-z][a-z0-9-]{0,39}$/.test(environment)) throw new Error("Explicit SaaS environment required");
    this.pool = pool;
    this.environment = environment;
  }
  async migrate() {
    await this.pool.query(await readFile(new URL("./schema.sql", import.meta.url), "utf8"));
  }
  async enqueue(client, kind, owner, payload, id = randomUUID()) {
    await client.query("INSERT INTO saas_jobs(id,environment,owner_id,kind,payload) VALUES($1,$2,$3,$4,$5)",
      [id, this.environment, owner, kind, payload]);
    await client.query("INSERT INTO saas_outbox(job_id) VALUES($1)", [id]);
    return id;
  }
  async accept(event, raw, owner) {
    return transaction(this.pool, async (client) => {
      // Serialize duplicate event IDs before creating the associated job.
      await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", [`${this.environment}:${event.id}`]);
      const hash = createHash("sha256").update(raw).digest("hex");
      const existing = await client.query("SELECT payload_sha256,job_id FROM saas_inbox WHERE environment=$1 AND event_id=$2", [this.environment, event.id]);
      if (existing.rows.length) {
        if (existing.rows[0].payload_sha256 !== hash) throw new Error("EVENT_ID_CONFLICT");
        return { duplicate: true, id: existing.rows[0].job_id };
      }
      const id = await this.enqueue(client, "webhook", owner, event.data);
      await client.query("INSERT INTO saas_inbox(environment,event_id,payload_sha256,job_id) VALUES($1,$2,$3,$4)", [this.environment, event.id, hash, id]);
      return { duplicate: false, id };
    });
  }
  async claimOutbox() {
    return transaction(this.pool, async (client) => {
      const { rows } = await client.query(`SELECT o.job_id FROM saas_outbox o JOIN saas_jobs j ON j.id=o.job_id
        WHERE j.environment=$1 AND o.published_at IS NULL AND o.available_at<=now()
        AND (o.lease_until IS NULL OR o.lease_until<now()) ORDER BY o.available_at
        FOR UPDATE OF o SKIP LOCKED LIMIT 1`, [this.environment]);
      if (!rows.length) return null;
      const lease = randomUUID();
      await client.query("UPDATE saas_outbox SET lease=$2,lease_until=now()+interval '60 seconds' WHERE job_id=$1", [rows[0].job_id, lease]);
      return { id: rows[0].job_id, lease, environment: this.environment };
    });
  }
  async published(job) {
    await this.pool.query("UPDATE saas_outbox SET published_at=now(),lease=NULL,lease_until=NULL WHERE job_id=$1 AND lease=$2", [job.id, job.lease]);
  }
  async claim(id) {
    return transaction(this.pool, async (client) => {
      // Ownership transfers lock this same row, fencing in-flight database effects.
      const ownership = await client.query("SELECT generation FROM saas_ownership WHERE environment=$1 AND owner='oci' FOR SHARE", [this.environment]);
      if (!ownership.rows.length) return { state: "paused" };
      const { rows } = await client.query("SELECT * FROM saas_jobs WHERE id=$1 AND environment=$2 FOR UPDATE", [id, this.environment]);
      if (!rows.length) return { state: "foreign" };
      const row = rows[0];
      if (["done", "dead"].includes(row.state)) return { state: row.state };
      if (row.state === "running" && row.lease_until > new Date()) return { state: "busy" };
      if (row.attempts >= 5) {
        await client.query("UPDATE saas_jobs SET state='dead',error_code='RETRY_EXHAUSTED' WHERE id=$1", [id]);
        return { state: "dead" };
      }
      const lease = randomUUID();
      await client.query("UPDATE saas_jobs SET state='running',attempts=attempts+1,lease=$2,lease_until=now()+interval '60 seconds' WHERE id=$1", [id, lease]);
      return { state: "claimed", id, lease, generation: ownership.rows[0].generation };
    });
  }
  async renew(job) {
    const result = await this.pool.query(`UPDATE saas_jobs SET lease_until=now()+interval '60 seconds'
      WHERE id=$1 AND environment=$2 AND lease=$3 AND state='running' AND lease_until>now()
      AND EXISTS(SELECT 1 FROM saas_ownership WHERE environment=$2 AND owner='oci' AND generation=$4)`,
    [job.id, this.environment, job.lease, job.generation]);
    return result.rowCount === 1;
  }
  async perform(job) {
    return transaction(this.pool, async (client) => {
      const ownership = await client.query("SELECT generation FROM saas_ownership WHERE environment=$1 AND owner='oci' AND generation=$2 FOR SHARE", [this.environment, job.generation]);
      if (!ownership.rows.length) throw new Error("OWNERSHIP_CHANGED");
      const { rows } = await client.query("SELECT * FROM saas_jobs WHERE id=$1 AND environment=$2 AND lease=$3 AND lease_until>now() AND state='running' FOR UPDATE", [job.id, this.environment, job.lease]);
      if (!rows.length) throw new Error("LEASE_LOST");
      const row = rows[0];
      let result;
      if (row.kind === "request") {
        const request = await client.query("SELECT id,title FROM tasks WHERE id=$1 AND owner_id=$2", [row.payload.taskId, row.owner_id]);
        result = request.rows.length ? { status: "processed", category: /urgent|blocked/i.test(request.rows[0].title) ? "priority" : "normal" } : { status: "removed" };
      } else if (row.kind === "summary") {
        const count = await client.query("SELECT count(*)::integer AS total,count(*) FILTER(WHERE done)::integer AS completed FROM tasks WHERE owner_id=$1", [row.owner_id]);
        result = { ...count.rows[0], dueAt: row.payload.dueAt, skipped: row.payload.skipped };
      } else if (row.kind === "webhook") {
        const data = row.payload;
        // The producer validates this shape; validate again at the trust boundary.
        if (!data || !Number.isSafeInteger(data.version) || data.version < 1 || typeof data.externalId !== "string" || typeof data.title !== "string") throw new Error("INVALID_JOB");
        await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", [`${this.environment}:${row.owner_id}:${data.externalId}`]);
        const previous = await client.query("SELECT version,task_id FROM saas_external_requests WHERE environment=$1 AND owner_id=$2 AND external_id=$3 FOR UPDATE", [this.environment, row.owner_id, data.externalId]);
        if (previous.rows.length && Number(previous.rows[0].version) >= data.version) result = { status: "superseded" };
        else if (previous.rows.length && previous.rows[0].task_id === null) {
          await client.query("UPDATE saas_external_requests SET version=$4 WHERE environment=$1 AND owner_id=$2 AND external_id=$3", [this.environment, row.owner_id, data.externalId, data.version]);
          result = { status: "removed" };
        } else {
          let taskId;
          if (previous.rows.length) {
            taskId = previous.rows[0].task_id;
            await client.query("UPDATE tasks SET title=$1,done=$2 WHERE id=$3 AND owner_id=$4", [data.title, data.done, taskId, row.owner_id]);
          } else {
            const inserted = await client.query("INSERT INTO tasks(title,done,owner_id) VALUES($1,$2,$3) RETURNING id", [data.title, data.done, row.owner_id]);
            taskId = inserted.rows[0].id;
          }
          await client.query(`INSERT INTO saas_external_requests(environment,owner_id,external_id,version,task_id) VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(environment,owner_id,external_id) DO UPDATE SET version=EXCLUDED.version,task_id=EXCLUDED.task_id`,
          [this.environment, row.owner_id, data.externalId, data.version, taskId]);
          result = { status: "applied", taskId };
        }
      } else throw new Error("INVALID_JOB");
      await client.query("UPDATE saas_jobs SET state='done',result=$2,lease=NULL,lease_until=NULL,error_code=NULL WHERE id=$1", [job.id, result]);
      return result;
    });
  }
  async failed(job) {
    await this.pool.query(`UPDATE saas_jobs SET state=CASE WHEN attempts>=5 THEN 'dead' ELSE 'pending' END,
      error_code='PROCESSING_FAILED',lease=NULL,lease_until=NULL WHERE id=$1 AND environment=$2 AND lease=$3 AND state='running'`, [job.id, this.environment, job.lease]);
  }
  async jobs(owner) {
    const { rows } = await this.pool.query(`SELECT id,kind,state,attempts,result,error_code,created_at FROM saas_jobs
      WHERE environment=$1 AND owner_id=$2 ORDER BY created_at DESC LIMIT 50`, [this.environment, owner]);
    return rows;
  }
  async scheduleTick(now = new Date()) {
    return transaction(this.pool, async (client) => {
      const active = await client.query("SELECT generation FROM saas_ownership WHERE environment=$1 AND owner='oci' FOR SHARE", [this.environment]);
      if (!active.rows.length) return { enqueued: 0, skipped: 0, state: "paused" };
      const { rows } = await client.query("SELECT * FROM saas_schedules WHERE environment=$1 AND enabled FOR UPDATE", [this.environment]);
      let enqueued = 0, skipped = 0;
      for (const schedule of rows) {
        const period = schedule.period_seconds * 1000, anchor = schedule.anchor.getTime();
        const index = Math.floor((now.getTime() - anchor) / period);
        if (index < 0) continue;
        const due = new Date(anchor + index * period);
        if (schedule.last_due && due <= schedule.last_due) continue;
        const missed = schedule.last_due ? Math.max(0, Math.round((due - schedule.last_due) / period) - 1) : index;
        const id = await this.enqueue(client, "summary", schedule.owner_id, { dueAt: due.toISOString(), skipped: missed });
        await client.query("INSERT INTO saas_schedule_runs(environment,schedule_id,version,due_at,job_id) VALUES($1,$2,$3,$4,$5)", [this.environment, schedule.id, schedule.version, due, id]);
        await client.query("UPDATE saas_schedules SET last_due=$3,skipped=skipped+$4 WHERE environment=$1 AND id=$2", [this.environment, schedule.id, due, missed]);
        enqueued++; skipped += missed;
      }
      return { enqueued, skipped, state: "active" };
    });
  }
}

export class RequestStore extends PgTaskStore {
  constructor(pool, jobs) { super(pool); this.jobs = jobs; }
  async create(title, owner = "sandbox") {
    return transaction(this.pool, async (client) => {
      const request = await new PgTaskStore(client).create(title, owner);
      await this.jobs.enqueue(client, "request", owner, { taskId: request.id });
      return request;
    });
  }
}
