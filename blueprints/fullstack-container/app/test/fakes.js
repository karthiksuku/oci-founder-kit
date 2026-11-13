// In-memory test doubles for the Taskboard stores. Used only by tests.

export class MemoryTaskStore {
  constructor() {
    this.rows = new Map();
    this.owners = new Map();
    this.uploads = new Map();
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

  async list(owner = "sandbox") {
    this.#maybeFail();
    return [...this.rows.values()].filter((t) => this.owners.get(t.id) === owner).map((t) => ({ ...t }));
  }

  async get(id, owner = "sandbox") {
    this.#maybeFail();
    const task = this.rows.get(id);
    if (!task || this.owners.get(id) !== owner) return null;
    const attachments = [...this.attachments.values()].filter((a) => a.taskId === id).map((a) => ({ ...a }));
    return { ...task, attachments };
  }

  async create(title, owner = "sandbox") {
    this.#maybeFail();
    const task = { id: this.nextId++, title, done: false, createdAt: new Date().toISOString() };
    this.rows.set(task.id, task);
    this.owners.set(task.id, owner);
    return { ...task };
  }

  async update(id, changes, owner = "sandbox") {
    this.#maybeFail();
    const task = this.rows.get(id);
    if (!task || this.owners.get(id) !== owner) return null;
    const updated = { ...task, ...changes };
    this.rows.set(id, updated);
    return { ...updated };
  }

  async remove(id, owner = "sandbox") {
    this.#maybeFail();
    return this.owners.get(id) === owner && this.rows.delete(id);
  }

  async addAttachment(taskId, { objectName, filename, size }, owner = "sandbox") {
    if (this.owners.get(taskId) !== owner) return null;
    this.#maybeFail();
    const attachment = { id: this.nextAttachmentId++, taskId, objectName, filename, size };
    this.attachments.set(attachment.id, attachment);
    return { ...attachment };
  }

  async getAttachment(id, owner = "sandbox") {
    this.#maybeFail();
    const attachment = this.attachments.get(id);
    return attachment && this.owners.get(attachment.taskId) === owner ? { ...attachment } : null;
  }
  async createUploadIntent(taskId, data, owner) {
    if (this.owners.get(taskId) !== owner) return false;
    this.uploads.set(data.uploadId, { ...data, taskId, owner, state: "pending" });
    return true;
  }
  async startUpload(id, owner) {
    const row = this.uploads.get(id);
    if (!row || row.owner !== owner || row.state !== "pending") return null;
    row.state = "uploading";
    return row;
  }
  async finishUpload(id, owner) {
    const row = this.uploads.get(id);
    if (!row || row.owner !== owner || row.state !== "uploading") return false;
    row.state = "uploaded";
    return true;
  }
  async claimUpload(taskId, data, owner) {
    const pair = [...this.uploads].find(([, row]) => row.objectName === data.objectName);
    if (!pair) return null;
    const [id, row] = pair;
    if (row.owner !== owner || row.taskId !== taskId || row.filename !== data.filename
        || row.size !== data.size || row.state !== "uploaded") return null;
    this.uploads.delete(id);
    return this.addAttachment(taskId, data, owner);
  }

}

export class FakeAttachmentStore {
  constructor() {
    this.lastUpload = null;
    this.objects = new Map();
  }

  async createUploadUrl(objectName, contentType) {
    this.lastUpload = { objectName, contentType };
    return { url: `https://objectstorage.example.invalid/p/upload/${encodeURIComponent(objectName)}`, expiresAt: new Date(Date.now() + 600000).toISOString() };
  }

  async createDownloadUrl(objectName) {
    return `https://objectstorage.example.invalid/p/download/${encodeURIComponent(objectName)}`;
  }
  async put(name, body) { this.objects.set(name, Buffer.from(body)); }
  async get(name) {
    const { Readable } = await import("node:stream");
    return Readable.from([this.objects.get(name)]);
  }

}
