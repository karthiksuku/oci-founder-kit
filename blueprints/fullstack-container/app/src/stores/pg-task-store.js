// Task and attachment storage in PostgreSQL. Every query is parameterised.

const SCHEMA = `
CREATE TABLE IF NOT EXISTS tasks (
  id          BIGSERIAL PRIMARY KEY,
  title       TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
  done        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'sandbox';
CREATE INDEX IF NOT EXISTS tasks_owner_id ON tasks (owner_id, id);
CREATE TABLE IF NOT EXISTS attachments (
  id           BIGSERIAL PRIMARY KEY,
  task_id      BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  object_name  TEXT NOT NULL UNIQUE,
  filename     TEXT NOT NULL,
  size_bytes   BIGINT NOT NULL CHECK (size_bytes > 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attachments_task_id ON attachments (task_id);
CREATE TABLE IF NOT EXISTS upload_intents (
  upload_id UUID PRIMARY KEY,
  task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  owner_id TEXT NOT NULL,
  object_name TEXT NOT NULL UNIQUE,
  filename TEXT NOT NULL,
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  state TEXT NOT NULL DEFAULT 'pending',
  expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '10 minutes'
);
`;

/** @param {{ id: string|number, title: string, done: boolean, created_at: Date }} row */
function toTask(row) {
  return { id: Number(row.id), title: row.title, done: row.done, createdAt: row.created_at.toISOString() };
}

/** @param {{ id: string|number, task_id: string|number, object_name: string, filename: string, size_bytes: string|number }} row */
function toAttachment(row) {
  return { id: Number(row.id), taskId: Number(row.task_id), objectName: row.object_name, filename: row.filename,
    size: Number(row.size_bytes) };
}

export class PgTaskStore {
  /** @param {import("pg").Pool} pool */
  constructor(pool) {
    this.pool = pool;
  }

  async migrate() {
    await this.pool.query(SCHEMA);
  }

  async ping() {
    await this.pool.query("SELECT 1");
  }

  async list(owner = "sandbox") {
    const { rows } = await this.pool.query("SELECT id, title, done, created_at FROM tasks WHERE owner_id = $1 ORDER BY id", [owner]);
    return rows.map(toTask);
  }

  /** @param {number} id */
  async get(id, owner = "sandbox") {
    const { rows } = await this.pool.query("SELECT id, title, done, created_at FROM tasks WHERE id = $1 AND owner_id = $2", [id, owner]);
    if (rows.length === 0) return null;
    const attachments = await this.pool.query(
      "SELECT id, task_id, object_name, filename, size_bytes FROM attachments WHERE task_id = $1 ORDER BY id", [id]);
    return { ...toTask(rows[0]), attachments: attachments.rows.map(toAttachment) };
  }

  /** @param {string} title */
  async create(title, owner = "sandbox") {
    const { rows } = await this.pool.query(
      "INSERT INTO tasks (title, owner_id) VALUES ($1, $2) RETURNING id, title, done, created_at", [title, owner]);
    return toTask(rows[0]);
  }

  /** @param {number} id @param {{ title?: string, done?: boolean }} changes */
  async update(id, changes, owner = "sandbox") {
    const { rows } = await this.pool.query(
      `UPDATE tasks SET title = COALESCE($2, title), done = COALESCE($3, done)
       WHERE id = $1 AND owner_id = $4 RETURNING id, title, done, created_at`,
      [id, changes.title ?? null, changes.done ?? null, owner]);
    return rows.length ? toTask(rows[0]) : null;
  }

  /** @param {number} id */
  async remove(id, owner = "sandbox") {
    const { rowCount } = await this.pool.query("DELETE FROM tasks WHERE id = $1 AND owner_id = $2", [id, owner]);
    return rowCount > 0;
  }

  /** @param {number} taskId @param {{ objectName: string, filename: string, size: number }} attachment */
  async addAttachment(taskId, { objectName, filename, size }, owner = "sandbox") {
    const { rows } = await this.pool.query(
      `INSERT INTO attachments (task_id, object_name, filename, size_bytes)
       SELECT id, $2, $3, $4 FROM tasks WHERE id = $1 AND owner_id = $5
       RETURNING id, task_id, object_name, filename, size_bytes`,
      [taskId, objectName, filename, size, owner]);
    return rows.length ? toAttachment(rows[0]) : null;
  }

  /** @param {number} id */
  async getAttachment(id, owner = "sandbox") {
    const { rows } = await this.pool.query(
      `SELECT a.id, a.task_id, a.object_name, a.filename, a.size_bytes FROM attachments a
       JOIN tasks t ON t.id = a.task_id WHERE a.id = $1 AND t.owner_id = $2`, [id, owner]);
    return rows.length ? toAttachment(rows[0]) : null;
  }

  async createUploadIntent(taskId, { uploadId, objectName, filename, size }, owner) {
    const { rowCount } = await this.pool.query(
      `INSERT INTO upload_intents (upload_id, task_id, owner_id, object_name, filename, size_bytes)
       SELECT $1, id, owner_id, $3, $4, $5 FROM tasks WHERE id = $2 AND owner_id = $6`,
      [uploadId, taskId, objectName, filename, size, owner]);
    return rowCount > 0;
  }

  async startUpload(uploadId, owner) {
    const { rows } = await this.pool.query(
      `UPDATE upload_intents u SET state = 'uploading' FROM tasks t
       WHERE u.upload_id = $1 AND u.owner_id = $2 AND t.id = u.task_id AND t.owner_id = $2
       AND u.state = 'pending' AND u.expires_at > now()
       RETURNING u.object_name, u.filename, u.size_bytes`, [uploadId, owner]);
    return rows.length ? { objectName: rows[0].object_name, filename: rows[0].filename, size: Number(rows[0].size_bytes) } : null;
  }

  async finishUpload(uploadId, owner) {
    const { rowCount } = await this.pool.query(
      "UPDATE upload_intents SET state = 'uploaded' WHERE upload_id = $1 AND owner_id = $2 AND state = 'uploading'",
      [uploadId, owner]);
    return rowCount > 0;
  }

  async claimUpload(taskId, { objectName, filename, size }, owner) {
    const { rows } = await this.pool.query(
      `WITH claimed AS (
        DELETE FROM upload_intents u USING tasks t
        WHERE u.task_id = $1 AND u.object_name = $2 AND u.filename = $3 AND u.size_bytes = $4
          AND u.owner_id = $5 AND t.id = u.task_id AND t.owner_id = $5
          AND u.state = 'uploaded' AND u.expires_at > now()
        RETURNING u.task_id, u.object_name, u.filename, u.size_bytes)
       INSERT INTO attachments (task_id, object_name, filename, size_bytes)
       SELECT task_id, object_name, filename, size_bytes FROM claimed
       RETURNING id, task_id, object_name, filename, size_bytes`,
      [taskId, objectName, filename, size, owner]);
    return rows.length ? toAttachment(rows[0]) : null;
  }

}
