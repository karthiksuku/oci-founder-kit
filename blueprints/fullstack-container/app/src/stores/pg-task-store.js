// Task and attachment storage in PostgreSQL. Every query is parameterised.

const SCHEMA = `
CREATE TABLE IF NOT EXISTS tasks (
  id          BIGSERIAL PRIMARY KEY,
  title       TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
  done        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS attachments (
  id           BIGSERIAL PRIMARY KEY,
  task_id      BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  object_name  TEXT NOT NULL UNIQUE,
  filename     TEXT NOT NULL,
  size_bytes   BIGINT NOT NULL CHECK (size_bytes > 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attachments_task_id ON attachments (task_id);
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

  async list() {
    const { rows } = await this.pool.query("SELECT id, title, done, created_at FROM tasks ORDER BY id");
    return rows.map(toTask);
  }

  /** @param {number} id */
  async get(id) {
    const { rows } = await this.pool.query("SELECT id, title, done, created_at FROM tasks WHERE id = $1", [id]);
    if (rows.length === 0) return null;
    const attachments = await this.pool.query(
      "SELECT id, task_id, object_name, filename, size_bytes FROM attachments WHERE task_id = $1 ORDER BY id", [id]);
    return { ...toTask(rows[0]), attachments: attachments.rows.map(toAttachment) };
  }

  /** @param {string} title */
  async create(title) {
    const { rows } = await this.pool.query(
      "INSERT INTO tasks (title) VALUES ($1) RETURNING id, title, done, created_at", [title]);
    return toTask(rows[0]);
  }

  /** @param {number} id @param {{ title?: string, done?: boolean }} changes */
  async update(id, changes) {
    const { rows } = await this.pool.query(
      `UPDATE tasks SET title = COALESCE($2, title), done = COALESCE($3, done)
       WHERE id = $1 RETURNING id, title, done, created_at`,
      [id, changes.title ?? null, changes.done ?? null]);
    return rows.length ? toTask(rows[0]) : null;
  }

  /** @param {number} id */
  async remove(id) {
    const { rowCount } = await this.pool.query("DELETE FROM tasks WHERE id = $1", [id]);
    return rowCount > 0;
  }

  /** @param {number} taskId @param {{ objectName: string, filename: string, size: number }} attachment */
  async addAttachment(taskId, { objectName, filename, size }) {
    const { rows } = await this.pool.query(
      `INSERT INTO attachments (task_id, object_name, filename, size_bytes) VALUES ($1, $2, $3, $4)
       RETURNING id, task_id, object_name, filename, size_bytes`,
      [taskId, objectName, filename, size]);
    return toAttachment(rows[0]);
  }

  /** @param {number} id */
  async getAttachment(id) {
    const { rows } = await this.pool.query(
      "SELECT id, task_id, object_name, filename, size_bytes FROM attachments WHERE id = $1", [id]);
    return rows.length ? toAttachment(rows[0]) : null;
  }
}
