// Opt-in aggregate instrumentation. No request paths, users or identifiers leave the app.
export function taskListMetrics(latencyMs, emit, clock = Date.now) {
  if (!Number.isInteger(latencyMs) || latencyMs < 1 || latencyMs > 60000) throw new Error("Invalid SRE latency objective");
  const bucket = () => Math.floor(clock() / 60000);
  let minute = bucket(), complete = false, eligible = 0, successful = 0, within = 0;
  function advance() {
    const next = bucket();
    if (next === minute) return;
    // Never report the first partial minute or invent samples across stalled timers.
    if (complete && next === minute + 1) emit({ schema: "oci-sre-minute/1", journey: "list-tasks",
      timestamp: new Date(minute * 60000).toISOString(), latencyMs,
      EligibleRequests: eligible, SuccessfulRequests: successful, WithinLatencyTarget: within, Heartbeat: 1 });
    complete = next > minute;
    minute = next; eligible = 0; successful = 0; within = 0;
  }
  const timer = setInterval(advance, 1000);
  timer.unref();
  return {
    close() { clearInterval(timer); },
    advance,
    middleware(req, res, next) {
      if (req.method === "GET" && req.path === "/api/tasks") {
        const start = performance.now();
        let recorded = false;
        function record(ok) {
          if (recorded) return;
          recorded = true; advance(); eligible++;
          if (ok) { successful++; if (performance.now() - start <= latencyMs) within++; }
        }
        res.once("finish", () => record(res.statusCode === 200));
        res.once("close", () => record(false));
      }
      next();
    },
  };
}
