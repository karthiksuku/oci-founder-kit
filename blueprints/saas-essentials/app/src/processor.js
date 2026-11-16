const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export async function publishOne(store, queue) {
  const job = await store.claimOutbox();
  if (!job) return false;
  // A lost successful response leaves the outbox unmarked. Retry sends the SAME job ID.
  await queue.send(JSON.stringify({ schema: "oci-kit-job/1", environment: job.environment, id: job.id }));
  await store.published(job);
  return true;
}
export async function processOne(store, queue, message, { heartbeatMs = 20000 } = {}) {
  let body;
  try { body = JSON.parse(message.content); } catch { return "invalid"; }
  if (body?.schema === "oci-kit-schedule-wakeup/1" && body.environment === store.environment
      && Object.keys(body).sort().join() === "environment,schema") {
    await store.scheduleTick();
    await queue.remove(message.receipt);
    return "schedule-wakeup";
  }
  if (!body || body.schema !== "oci-kit-job/1" || !UUID.test(body.id) || body.environment !== store.environment
      || Object.keys(body).sort().join() !== "environment,id,schema") return "foreign-or-invalid";
  const job = await store.claim(body.id);
  if (job.state === "done") { await queue.remove(message.receipt); return "duplicate"; }
  // Dead/invalid deliveries remain for the queue's configured DLQ; no automatic redrive.
  if (job.state !== "claimed") return job.state;
  let heartbeat = Promise.resolve(), lost = false;
  const timer = setInterval(() => {
    heartbeat = heartbeat.then(async () => {
      if (!await store.renew(job)) { lost = true; return; }
      await queue.renew(message.receipt, 60);
    }).catch(() => { lost = true; });
  }, heartbeatMs);
  timer.unref();
  try {
    await heartbeat;
    if (lost) throw new Error("LEASE_LOST");
    await store.perform(job);
    // Persist effects and completion before acknowledging transport. Delete failure is safe to retry.
    await queue.remove(message.receipt);
    return "done";
  } catch {
    await store.failed(job);
    return "retry";
  } finally { clearInterval(timer); await heartbeat; }
}
