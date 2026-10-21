// The Taskboard HTTP application: web UI, task API and attachment API.

import express from "express";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "./logger.js";

const PUBLIC_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public");
const OBJECT_NAME = /^tasks\/\d+\/[0-9a-f-]{36}-[A-Za-z0-9._-]{1,100}$/;

class HttpError extends Error {
  /** @param {number} status @param {string} message */
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** @param {string} raw @returns {number} */
function parseId(raw) {
  if (!/^\d{1,15}$/.test(raw)) throw new HttpError(404, "Not found");
  return Number(raw);
}

/** @param {unknown} title @returns {string} */
function validTitle(title) {
  if (typeof title !== "string" || title.trim().length === 0 || title.trim().length > 200) {
    throw new HttpError(400, "title must be text of 1 to 200 characters");
  }
  return title.trim();
}

/** @param {unknown} name @returns {string} */
export function safeFilename(name) {
  if (typeof name !== "string" || name.length === 0 || name.length > 200) {
    throw new HttpError(400, "filename must be text of 1 to 200 characters");
  }
  const base = path.posix.basename(name.replaceAll("\\", "/"));
  const cleaned = base.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^\.+/, "").slice(0, 100);
  return cleaned || "file";
}

/** @param {unknown} size @param {number} max @returns {number} */
function validSize(size, max) {
  if (!Number.isInteger(size) || size < 1) throw new HttpError(400, "size must be a positive whole number of bytes");
  if (size > max) throw new HttpError(413, `Files can be at most ${max} bytes`);
  return size;
}

function securityHeaders(_req, res, next) {
  res.set({
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; connect-src 'self' https://*.oraclecloud.com; "
      + "img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'",
  });
  next();
}

/**
 * Build the Express app around its stores, so tests can supply doubles.
 * @param {{ tasks: object, attachments: object | null, config: { maxUploadBytes: number } }} deps
 */
export function createApp({ tasks, attachments, config }) {
  const app = express();
  app.disable("x-powered-by");
  app.use(securityHeaders);
  app.use(express.json({ limit: "16kb" }));

  app.get("/healthz", (_req, res) => res.json({ status: "ok" }));
  app.get("/readyz", async (_req, res) => {
    try {
      await tasks.ping();
      res.json({ status: "ready" });
    } catch (err) {
      logger.warn("readiness check failed", { error: err.message });
      res.status(503).json({ status: "unavailable" });
    }
  });

  app.get("/api/tasks", async (_req, res) => res.json(await tasks.list()));

  app.post("/api/tasks", async (req, res) => {
    res.status(201).json(await tasks.create(validTitle(req.body?.title)));
  });

  app.get("/api/tasks/:id", async (req, res) => {
    const task = await tasks.get(parseId(req.params.id));
    if (!task) throw new HttpError(404, "Not found");
    res.json(task);
  });

  app.patch("/api/tasks/:id", async (req, res) => {
    const changes = {};
    if (req.body?.title !== undefined) changes.title = validTitle(req.body.title);
    if (req.body?.done !== undefined) {
      if (typeof req.body.done !== "boolean") throw new HttpError(400, "done must be true or false");
      changes.done = req.body.done;
    }
    const task = await tasks.update(parseId(req.params.id), changes);
    if (!task) throw new HttpError(404, "Not found");
    res.json(task);
  });

  app.delete("/api/tasks/:id", async (req, res) => {
    if (!(await tasks.remove(parseId(req.params.id)))) throw new HttpError(404, "Not found");
    res.status(204).end();
  });

  app.post("/api/tasks/:id/attachments/upload-url", async (req, res) => {
    if (!attachments) throw new HttpError(501, "File storage is not configured");
    const id = parseId(req.params.id);
    const filename = safeFilename(req.body?.filename);
    validSize(req.body?.size, config.maxUploadBytes);
    if (!(await tasks.get(id))) throw new HttpError(404, "Not found");
    const objectName = `tasks/${id}/${randomUUID()}-${filename}`;
    const upload = await attachments.createUploadUrl(objectName, req.body?.contentType);
    res.status(201).json({ objectName, uploadUrl: upload.url, expiresAt: upload.expiresAt });
  });

  app.post("/api/tasks/:id/attachments", async (req, res) => {
    if (!attachments) throw new HttpError(501, "File storage is not configured");
    const id = parseId(req.params.id);
    const objectName = req.body?.objectName;
    if (typeof objectName !== "string" || !OBJECT_NAME.test(objectName) || !objectName.startsWith(`tasks/${id}/`)) {
      throw new HttpError(400, "objectName must come from this task's upload URL");
    }
    const filename = safeFilename(req.body?.filename);
    const size = validSize(req.body?.size, config.maxUploadBytes);
    if (!(await tasks.get(id))) throw new HttpError(404, "Not found");
    res.status(201).json(await tasks.addAttachment(id, { objectName, filename, size }));
  });

  app.get("/api/attachments/:id/download", async (req, res) => {
    if (!attachments) throw new HttpError(501, "File storage is not configured");
    const attachment = await tasks.getAttachment(parseId(req.params.id));
    if (!attachment) throw new HttpError(404, "Not found");
    res.redirect(302, await attachments.createDownloadUrl(attachment.objectName));
  });

  app.use("/api", (_req, _res, next) => next(new HttpError(404, "Not found")));
  app.use(express.static(PUBLIC_DIR, { index: "index.html", maxAge: "5m" }));

  app.use((err, _req, res, _next) => {
    if (err instanceof HttpError) {
      res.status(err.status).json({ error: err.message });
      return;
    }
    if (err?.type === "entity.parse.failed" || err?.type === "entity.too.large") {
      res.status(400).json({ error: "The request body must be valid JSON of at most 16 KB" });
      return;
    }
    logger.error("request failed", { error: err?.message, name: err?.name });
    res.status(500).json({ error: "Something went wrong. Try again." });
  });

  return app;
}
