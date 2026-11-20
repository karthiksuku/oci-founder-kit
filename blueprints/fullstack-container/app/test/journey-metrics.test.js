import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import { taskListMetrics } from "../src/journey-metrics.js";

test("real authenticated handler completions, failures, closes, blanks and gaps stay distinct", () => {
  const windows = []; let time = 45000;
  const m = taskListMetrics(1000, w => windows.push(w), () => time);
  try {
    time = 60000; m.advance();
    function request(path, status, aborted = false) {
      const res = new EventEmitter(); res.statusCode = status;
      m.middleware({ method: "GET", path }, res, () => {});
      if (!aborted) res.emit("finish"); res.emit("close");
    }
    request("/healthz", 200); request("/api/tasks", 200); request("/api/tasks", 503); request("/api/tasks", 200, true);
    time += 60000; m.advance();
    assert.deepEqual([windows[0].EligibleRequests, windows[0].SuccessfulRequests, windows[0].WithinLatencyTarget], [3, 1, 1]);
    time += 60000; m.advance();
    assert.deepEqual([windows[1].EligibleRequests, windows[1].Heartbeat], [0, 1]);
    time += 180000; m.advance();
    assert.equal(windows.length, 2);
  } finally { m.close(); }
});
