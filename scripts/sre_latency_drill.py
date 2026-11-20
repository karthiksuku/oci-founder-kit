#!/usr/bin/env python3
"""Small bounded rehearsal against an explicitly selected local candidate listener.

One GET path, at most two clients and 30 attempts. No credentials, redirects,
proxy, response-body retention, automatic retries or remote addresses.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import math
import re
import time


def measure(*, port, route, attempts, clients, latency_ms, good_percent):
    if (not 1024 <= port <= 65535 or not re.fullmatch(r"/[A-Za-z0-9/_-]{0,120}", route)
            or not 1 <= attempts <= 30 or not 1 <= clients <= min(2, attempts)
            or not 1 <= latency_ms <= 5000 or not 1 <= good_percent <= 100):
        raise ValueError("Select a loopback port, bounded route and explicit objectives.")
    def sample(_):
        start = time.monotonic()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            c.request("GET", route, headers={"User-Agent": "oci-founder-local-rehearsal"})
            r = c.getresponse()
            # Time to headers for this selected read, not browser rendering or streaming latency.
            return (r.status == 200, (time.monotonic() - start) * 1000)
        except (OSError, http.client.HTTPException):
            return (False, None)
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        observations = list(pool.map(sample, range(attempts)))
    healthy = sum(ok for ok, _ in observations)
    timely = sum(ok and ms is not None and ms <= latency_ms for ok, ms in observations)
    times = sorted(ms for ok, ms in observations if ok)
    return {"schema": "oci-sre-local-load/1", "scope": "loopback-selected-read-time-to-headers",
            "attempts": attempts, "concurrency": clients, "status_200": healthy, "within_threshold": timely,
            "latency_threshold_ms": latency_ms, "required_good_percent": good_percent,
            "successful_response_p95_ms": round(times[math.ceil(.95 * len(times))-1], 2) if times else None,
            "status": "passed" if 100 * timely >= good_percent * attempts else "failed",
            "candidate_identity_verified": False, "production_ready": False}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--port", type=int, required=True)
    cli.add_argument("--route", required=True)
    cli.add_argument("--attempts", type=int, default=12)
    cli.add_argument("--clients", type=int, default=1)
    cli.add_argument("--latency-ms", type=int, required=True)
    cli.add_argument("--good-percent", type=int, default=100)
    try:
        result = measure(**vars(cli.parse_args()))
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["status"] == "passed" else 3)
    except ValueError:
        cli.exit(3, "Invalid local rehearsal bounds. No test was run.\n")
