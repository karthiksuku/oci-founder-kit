import { createHmac, timingSafeEqual } from "node:crypto";
import express from "express";

// Reference protocol, not a Stripe adapter: HMAC-SHA256(timestamp + '.' + original bytes).
export function verifyWebhook(raw, header, secret, now = Date.now()) {
  if (!Buffer.isBuffer(raw) || raw.length > 16384 || typeof secret !== "string" || Buffer.byteLength(secret) < 32) return false;
  const match = typeof header === "string" && /^t=(\d{10}),v1=([a-f0-9]{64})$/.exec(header);
  if (!match || Math.abs(Math.floor(now / 1000) - Number(match[1])) > 300) return false;
  const signature = createHmac("sha256", secret).update(`${match[1]}.`).update(raw).digest();
  return timingSafeEqual(signature, Buffer.from(match[2], "hex"));
}
export function parseEvent(raw) {
  const event = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw));
  const data = event?.data;
  if (!event || Object.keys(event).sort().join() !== "data,id,type" || event.type !== "request.upsert"
      || !/^[A-Za-z0-9_-]{1,100}$/.test(event.id) || !data || Object.keys(data).sort().join() !== "done,externalId,title,version"
      || !/^[A-Za-z0-9_-]{1,100}$/.test(data.externalId) || !Number.isSafeInteger(data.version) || data.version < 1
      || typeof data.title !== "string" || !data.title.trim() || data.title.length > 200 || typeof data.done !== "boolean") {
    throw new Error("INVALID_EVENT");
  }
  return event;
}
export function webhookRoutes({ jobs, secret, owner }) {
  if (!owner || Buffer.byteLength(secret ?? "") < 32) throw new Error("Explicit webhook binding and secret required");
  // Bounded per-process admission; configure ingress rate limits for production as well.
  let window = 0, count = 0;
  return (app) => app.post("/webhooks/requests", (req, res, next) => {
    const current = Math.floor(Date.now() / 60000);
    if (current !== window) { window = current; count = 0; }
    if (++count > 120) return res.status(429).json({ error: "Rate limit exceeded" });
    next();
  }, express.raw({ type: "application/json", limit: "16kb", inflate: false }), async (req, res) => {
    res.set("Cache-Control", "no-store");
    if (!verifyWebhook(req.body, req.get("x-kit-webhook-signature"), secret)) return res.status(400).json({ error: "Invalid signature" });
    let event;
    try { event = parseEvent(req.body); } catch { return res.status(400).json({ error: "Unsupported event" }); }
    try {
      const result = await jobs.accept(event, req.body, owner);
      return res.status(202).json({ accepted: true, duplicate: result.duplicate });
    } catch (error) {
      return res.status(error.message === "EVENT_ID_CONFLICT" ? 409 : 503).json({ error: "Event could not be accepted" });
    }
  });
}
