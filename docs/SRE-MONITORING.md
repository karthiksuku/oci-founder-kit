# Know when a user journey is failing

Start by naming the action users depend on (for example, listing their saved tasks), its primary responder, a backup, and an agreed success and latency target. The dashboard distinguishes real requests, synthetic probes, and infrastructure symptoms. A working probe or an idle CPU cannot establish that customer requests succeed.

## Rehearse notification delivery first

The generic web-container and hardened Taskboard load-balancer blueprints accept this **optional** monitoring variable. Keep the actual email addresses and private configuration outside Git. Select valid OCI vantage points that the reviewed ingress permits; do not broaden ingress automatically. For web-container, provide it under `variables.monitoring` in the private `release configure` input. For Taskboard, pass it in the private reviewed stack variables alongside a matching `sre_latency_ms`; use journey `list-tasks`, a hardened HTTPS load balancer, and leave the legacy `alert_email` empty. The optional SRE pack does not support Taskboard gateway or HTTP sandbox ingress.

~~~json
{
  "primary_email": "primary@example.test",
  "backup_email": "backup@example.test",
  "journey": "list-tasks",
  "vantage_points": ["azr-sat"]
}
~~~

Before approving the exact plan, review the deployment scope and estimated costs: one probe a minute per selected vantage point (1,440 scheduled probes per day **per location**), three monitoring alarms, one Notifications topic, and two email subscriptions. Taskboard reuses its existing backend alarm and topic. Provisioning may send confirmation messages and initiates recurring requests and charges; removing a local file does not stop them. Review current regional pricing for Health Checks, Monitoring/custom metrics and Notifications and obtain a separate cleanup plan. The kit does not change DNS, grant new permissions or publish metrics automatically.

The following are separate operator actions, not implied by enabling a Terraform variable:

1. Confirm the exact public origin, DNS, TLS chain and nonsecret read-only health path. Review the external probe IP ranges. Choose primary and backup who can actually receive and acknowledge messages. An administrator must review the scoped permissions for the deployer (monitor, alarm and subscriptions), the observer (metrics, probe metadata and results), and the telemetry publisher separately.
2. In the approved rehearsal environment, approve a bounded failure and recovery plan that cannot affect customer traffic. Record: alarm transitioned to firing, primary received it, backup route was tested, recovery returned the alarm to OK, the actual times, and a digest of the private evidence. A subscription marked active does not demonstrate receipt. No test message, drill, or traffic change is sent by the kit.
3. Keep a short private runbook: verify the public path, confirm current deployment digest and alerts, review certificate/dependency status and saturation, then choose a separately approved recovery operation. Record impact, time to recover and one preventive action with an owner. Demonstrate the alert paths again after changing responders, monitors, or routing.

The alarm set covers an unhealthy backend, consecutive failing intervals from an external location, and absence of application heartbeat. Real traffic SLOs are displayed separately. Review metrics and firing/recovery in the actual environment before claiming monitoring works. [OCI external checks](https://docs.oracle.com/en-us/iaas/Content/HealthChecks/Tasks/create-http-monitor.htm) · [External metrics](https://docs.oracle.com/en-us/iaas/Content/HealthChecks/Reference/metricsalarms-reference.htm) · [Monitoring absence alarms](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-absence.htm).

## Instrument the app and read the dashboard

Publish one delta per **completed UTC minute** to OCI Monitoring namespace `founder_app` through a separately reviewed exporter/identity. Use dimensions `resourceId` (Container Instance), `journey` (one bounded slug) and, for request counts only, `latencyMs` (the configured threshold as a decimal string). Do not include raw URLs, identities, account identifiers other than the selected OCI resource dimension, or payloads. Agree what counts as a real eligible request at the application boundary. For Taskboard the selected action is the authenticated task list; separate test identities or endpoints for production probes rather than mixing them into application counts.

| Metric | Each minute |
|---|---|
| EligibleRequests | Number of real requests for the agreed user journey. |
| SuccessfulRequests | Eligible requests that completed successfully. |
| WithinLatencyTarget | Successful requests within the agreed end-to-end application threshold. An upstream/backend average cannot establish this count. |
| Heartbeat | Exactly 1 per completed minute whether traffic occurred or not. Emit zero **request counts** for an observed idle minute; omit unavailable samples instead of manufacturing zeroes. |

Use one exporter per monitored instance/journey. It must deduplicate timestamped minute deltas and never backfill unavailable minutes with estimates. Reuse original interval timestamps for delayed data; do not label backlog as new traffic. For Next.js, instrument the corresponding server route with the same counters; exclude health probes, static assets and known synthetic checks. For Taskboard the example emits opt-in aggregate deltas; the launch operator must connect its exporter to the selected Monitoring namespace. A cumulative counter, multiple reporters with identical dimensions, or a changed measurement boundary needs a new validated integration. SLO windows are scoped to the selected instance and latency threshold; on replacement, history may start anew.

Prepare a private mode-0600 contract; use actual agreed objectives and the actual hash of the private runbook:

~~~json
{
  "schema": "oci-sre-monitor-input/1",
  "environment": "rehearsal",
  "journey": "list-tasks",
  "primary_role": "oncall",
  "backup_role": "backup",
  "runbook_sha256": "<64 lowercase hex characters>",
  "availability_bps": 9990,
  "latency_bps": 9900,
  "latency_ms": 500
}
~~~

~~~sh
.oci-founder-kit/scripts/oci-kit sre monitor --environment rehearsal \
  --monitor-input /private/rehearsal-monitor.json --live --write --json
.oci-founder-kit/scripts/oci-kit observe --environment rehearsal
~~~

`--live` makes bounded, read-only OCI queries using the selected private profile, current receipt and environment. Use `--config-file` for a nondefault private profile location. The output includes the actual observed digest when it matches, certificate metadata/expiry, backend and instance state, CPU samples, and external probe status. It looks at the last five minutes of the selected external monitor. Three consecutive, recent failures at one vantage point are flagged; a single failure is degraded. Missing/stale samples or mismatched monitor metadata remain unknown. Probe successes are never added to the real-user denominator.

The real-user window is the last 28 days through the previous UTC hour boundary. Report completed hourly counts and sample volume. The live reader requires all minute-delta metrics and a heartbeat count/sum of 60 per included hour. A new history, missing telemetry, no traffic, or fewer than 100 eligible requests in a complete window cannot yield a met objective. A separate heartbeat check covers recent minutes. Current live telemetry and alarm delivery can be demonstrated on day one without claiming 28 days of achieved service. Review the kit's separate release checks before promotion.

Without `--live`, a contract can include `hours`: an array of owner-recorded aggregates with fields `end` (UTC epoch seconds at an hour boundary), `minutes`, `eligible`, `successful` and `within`. These samples are rejected as input to live mode. An optional `drill` object records `environment`, `primary_role`, `runbook_sha256`, `evidence_sha256` and four ordered epoch timestamps: `fired_at`, `received_at`, `recovered_at`, `cleared_at`. This is an owner record, never independent proof of delivery or production approval. Preserve the original private evidence.

`--write` saves a private aggregate snapshot. The static dashboard expires the monitor snapshot after 15 minutes and checks the live report against the current deployment receipt. Re-run the command to refresh; the kit never starts background polling or publishes the dashboard. A local/injected result stays labeled as such. Customer data, raw logs and domains are not included in the monitor dashboard projection.
