# Hosting first, data later

Keep the application source and its existing database, authentication and storage
providers. Move only the reviewed hosting workload first. Data migration has its
own semantic checks, recovery rehearsal and exact approval later. Never treat a
successful image build as proof of application compatibility.

The standard-library helper is `scripts/migration.py` at the kit root. It provides
three operations: `assess`, `verify` and `review`. None invokes shell commands,
application code, OCI APIs, data copy or traffic changes. `verify` makes the
selected GET/HEAD requests; review routes for side effects before selecting them.
Keep contracts and reports in the selected environment's private `.oci-kit`
directory. Use mode 600 and a new output filename for each run. Session files must
be outside any Git tree. No bodies, response values, cookie values, request paths
or raw origins are copied into reports.

## Review compatibility explicitly

```sh
python3 /path/to/kit/skills/oci-migrate-web/scripts/web_scan.py /path/to/app \
  --format json --out /private/path/scan.json
python3 /path/to/kit/scripts/migration.py assess \
  --scan /private/path/scan.json --out /private/path/compatibility.json
```

Every discovered feature starts `unknown`. The report includes `scan_sha256`.
After reviewing actual source and evidence, create an owner-only review file:

```json
{
  "schema": "oci-migration-reviews/1",
  "scan_sha256": "<64 lowercase hex characters from the current report>",
  "features": [
    {
      "feature": "next-runtime",
      "outcome": "adaptation-required",
      "evidence_sha256": "<SHA256 of the private reviewed evidence>"
    }
  ]
}
```

Pass that file with `assess --reviews /private/path/reviews.json`. Supported
outcomes are `supported`, `adaptation-required`, `unsupported` and `unknown`.
Non-unknown outcomes require an evidence hash. These are explicit owner reviews;
the helper does not authenticate their provenance or inspect linked evidence.
They bind the exact scan so source-scan changes invalidate old reviews. An
incomplete scan, no findings or even all reviewed findings never establishes
complete portability. Dashboard-only configuration, runtime behavior, framework
version support and undiscovered dependencies remain separate inventory work.

## Define application behavior before verification

A private contract has schema `oci-hosting-migration/1`. It is valid for at most
24 hours and binds one environment, two distinct origins, a source revision hash
and a target image digest. Origin selection is confirmed explicitly on the CLI.
Source revision and target digest are **selected bindings**, not independently
observed deployment identity. Verify the deployed image through OCI evidence
separately. The runner never copies, overwrites or starts the existing app.

Create a private JSON file with this structure; replace every angle-bracket value
locally. Example domains are fictional. Do not put credentials in this contract.

```json
{
  "schema": "oci-hosting-migration/1",
  "environment": "rehearsal",
  "created_at_utc": "<current UTC ISO timestamp>",
  "expires_at_utc": "<UTC ISO timestamp within 24 hours>",
  "transport": "https",
  "source": {
    "origin": "https://source.example.com",
    "revision_sha256": "<64 lowercase hex characters>"
  },
  "target": {
    "origin": "https://rehearsal.example.com",
    "image_digest": "sha256:<64 lowercase hex characters>"
  },
  "retained_services": {
    "database": "retained",
    "authentication": "retained",
    "storage": "retained"
  },
  "jobs": {
    "inventory": "unknown",
    "owner": "unknown",
    "source_enabled": null,
    "target_enabled": null,
    "evidence_sha256": null
  },
  "rollback": {
    "source_preserved": null,
    "restore_traffic_reviewed": null,
    "evidence_sha256": null
  },
  "checks": [
    {
      "id": "health",
      "method": "GET",
      "path": "/healthz",
      "status": 200,
      "headers": {"cache-control": {"contains": "no-store"}},
      "body": {
        "mode": "json",
        "pointers": ["/status"],
        "expected": {"/status": "ok"}
      }
    }
  ]
}
```

Change the checks to cover your app's meaningful read workflows. A health-only
pass verifies only that check. Retained-service choices are `retained`, `not-used`
or `unknown`; no setting migrates data. Test OCI access to retained providers,
certificate validation, egress restrictions, connection pooling, OAuth callback
allowlists and cross-cloud latency before cutover.

Each check has a unique short `id`, `method` (`GET` or `HEAD`), origin-relative
`path`, expected `status` and `body`. The fixed assertion language supports:

| Field | Meaning and limit |
| --- | --- |
| `body.mode: none` | Check status and selected headers; no body parity claim. Required for HEAD. |
| `body.mode: sha256` | Compare complete response bytes; optional `expected_sha256` also establishes a known baseline. |
| `body.mode: json` | Compare only explicit JSON `pointers`; optional `expected` values check source and target independently. Values never appear in reports. |
| `headers` | `equals` or `contains` predicates on content-type, cache-control, vary, content-encoding, HSTS and nosniff headers. No arbitrary request headers or expressions. |
| `location` | Exact relative redirect destination, or the same destination under that side's origin. Redirects are never followed. |
| `cookies` | `{ "present": true, "secure": true, "httponly": true, "samesite": "Lax" }` checks flags without retaining cookie values. |
| `session` | `anonymous` by default; `a` or `b` selects an existing private test-session cookie. |
| `repeat: 2` | Repeat the same read and require stable selected projections on both sides. This does not establish cache invalidation correctness. |
| `streaming` | Example `{ "first_byte_ms_max": 2000, "span_ms_min": 80, "completion_ms_max": 4000 }` requires an early first body byte and observable delivery span. Select a deliberately delayed test stream; network timing alone is not proof of production streaming behavior. |

At most sixteen checks, two reads per check per origin, 256 KiB per response and
a 90-second shared deadline are permitted. No proxies, redirect following,
retries, unverified TLS, arbitrary code or mutating request methods are available.
Transport errors or interrupted execution produce unknown evidence. A failed
source baseline is shown separately from a target failure. Contracts expiring
during execution cannot pass. A non-passing verification exits 1; invalid input
exits 2. Reports identify the runner hash and exact contract/environment binding.

```sh
python3 /path/to/kit/scripts/migration.py verify \
  --contract /private/path/contract.json --environment rehearsal \
  --source https://source.example.com --target https://rehearsal.example.com \
  --out /private/path/parity.json
```

`local-loopback` transport accepts numeric loopback HTTP origins only and refuses
session cookies. Reports clearly label that scope. `--ca-file` accepts a private
trusted-CA file for selected HTTPS endpoints; it does not disable TLS checks.

## Authenticated reads and browser acceptance

For checks selecting `a` and/or `b`, use existing test sessions obtained through
the application's normal hosted sign-in. Store exactly the selected users in a
mode-600 JSON file **outside Git**, with schema `oci-migration-sessions/1`, and
`source` and `target` objects containing each exact `origin` and `users` mapping.
Each mapping contains `a` and/or `b` cookie-header strings. Different users must
have different cookie values. Bind cookies separately to the selected source and
target; the runner never forwards a source cookie to the target automatically.
Pass its private path as `--sessions-file`; never paste session values into chat,
command-line arguments, reports or a public issue. Responses cannot update the
session jar. An expired session should fail the selected application's assertions.

Read-only HTTP checks cannot establish hosted login/callback behavior, browser
hydration, navigation, uploads, writes, multi-instance revalidation or recovery.
Test these in the browser with independent expected outcomes. Use two users for
access isolation and include denied-access expectations. Keep destructive or
synthetic write workflows in separately reviewed, bounded tests with cleanup.

The [Next.js example](../../../examples/migrate-nextjs/README.md) and
[ordinary-container example](../../../examples/migrate-container/README.md)
exercise local HTTP packaging and negative controls. Neither is evidence that a
user's hosted migration or their OCI deployment passed.

The [real Chromium fixture suite](../../../tests/browser-migration/README.md)
also tests source/standalone Next.js navigation and form previews, catalogue
navigation, and Taskboard's actual browser client with synthetic user isolation,
uploads, downloads and logout. Its negative controls must fail, and app sources
must remain unchanged. This is bounded local browser evidence; provider sign-in,
data semantics and the founder's own browser acceptance still require their
separate tests.

## One job owner, separate cutover and rollback

Inventory schedules, queues, workers, webhook consumers, retry policies, time
zones and idempotency. During rehearsal keep target jobs disabled. Once runtime
evidence has been reviewed, set `jobs.inventory` to `attested`, `owner` to
`source`, `target` or `none`, and record explicit boolean enablement for both
sides plus the evidence hash. Both sides enabled is a conflict. A consistent
attestation remains an attestation; the helper never queries running schedulers.
Unknown inventory never passes as “no jobs.”

Capture source-preservation and traffic-restore review evidence in `rollback`.
Generate a summary after parity checks:

```sh
python3 /path/to/kit/scripts/migration.py review \
  --contract /private/path/contract.json --environment rehearsal \
  --parity /private/path/parity.json --out /private/path/cutover-review.json
```

Wrong-environment, wrong-digest, changed-runner or mismatched-contract parity
reports are refused. Reports are local evidence and are not signed deployment
receipts. Review still requires separate browser acceptance, observed deployment
identity, isolated restore and traffic-rollback rehearsal. Approve exact traffic
change and rollback plans through the existing gate; this summary is never an
approval. Transfer scheduled-job ownership once, verify the former owner has
stopped, and retain the source until hosting acceptance. Report overlap costs and
retained resources. Shutdown, cleanup and all data migration remain separate
approved operations.
