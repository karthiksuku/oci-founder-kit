// In-memory test doubles for the Taskboard stores. Used only by tests.

export class MemoryTaskStore {
  constructor() {
    this.rows = new Map();
    this.attachments = new Map();
    this.nextId = 1;
    this.nextAttachmentId = 1;
    this.healthy = true;
    this.failNext = null;
  }

  #maybeFail() {
    if (this.failNext) {
      const err = this.failNext;
      this.failNext = null;
      throw err;
    }
  }

  async ping() {
    if (!this.healthy) throw new Error("database unreachable");
  }

  async list() {
    this.#maybeFail();
    return [...this.rows.values()].map((t) => ({ ...t }));
  }

  async get(id) {
    this.#maybeFail();
    const task = this.rows.get(id);
    if (!task) return null;
    const attachments = [...this.attachments.values()].filter((a) => a.taskId === id).map((a) => ({ ...a }));
    return { ...task, attachments };
  }

  async create(title) {
    this.#maybeFail();
    const task = { id: this.nextId++, title, done: false, createdAt: new Date().toISOString() };
    this.rows.set(task.id, task);
    return { ...task };
  }

  async update(id, changes) {
    this.#maybeFail();
    const task = this.rows.get(id);
    if (!task) return null;
    const updated = { ...task, ...changes };
    this.rows.set(id, updated);
    return { ...updated };
  }

  async remove(id) {
    this.#maybeFail();
    return this.rows.delete(id);
  }

  async addAttachment(taskId, { objectName, filename, size }) {
    this.#maybeFail();
    const attachment = { id: this.nextAttachmentId++, taskId, objectName, filename, size };
    this.attachments.set(attachment.id, attachment);
    return { ...attachment };
  }

  async getAttachment(id) {
    this.#maybeFail();
    const attachment = this.attachments.get(id);
    return attachment ? { ...attachment } : null;
  }
}

export class FakeAttachmentStore {
  constructor() {
    this.lastUpload = null;
  }

  async createUploadUrl(objectName, contentType) {
    this.lastUpload = { objectName, contentType };
    return { url: `https://objectstorage.example.invalid/p/upload/${encodeURIComponent(objectName)}`, expiresAt: new Date(Date.now() + 600000).toISOString() };
  }

  async createDownloadUrl(objectName) {
    return `https://objectstorage.example.invalid/p/download/${encodeURIComponent(objectName)}`;
  }
}
