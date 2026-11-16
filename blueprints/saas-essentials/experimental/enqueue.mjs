// Pure adapter logic. Binding to an OCI Functions runtime is intentionally blocked
// until the pinned provider, image format and exact invocation permissions pass.
export async function enqueueWakeup(queue, environment) {
  if (!/^[a-z][a-z0-9-]{0,39}$/.test(environment)) throw new Error("Explicit environment required");
  await queue.send(JSON.stringify({ schema: "oci-kit-schedule-wakeup/1", environment }));
  return { accepted: true };
}
