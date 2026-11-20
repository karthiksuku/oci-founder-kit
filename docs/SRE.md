# From a working app to a production decision

At your app root, ask Claude Code or Codex: **“Use OCI Founder Kit to plan tests
for the one thing my customers must be able to do. Run the local checks,
tell me what still needs rehearsal, and stop before a cloud write.”**

Start with:

```sh
.oci-founder-kit/scripts/oci-kit sre plan --environment rehearsal
```

The planner inspects the selected environment's packaging descriptor, known
package scripts, dependency files and existing GitHub workflows without running
their contents. It proposes four stages. For Taskboard, start with sign-in,
create a task, reload, and confirm a second account cannot read it. For a
Next.js hosting migration, test a meaningful existing action with the original
database, identity provider and storage, plus callback, cache, redirect and
worker ownership behavior. For a new Next.js web app, use the separate launch
profile below. Other workloads receive a diagnostic plan only.

Save the critical journey, if desired, in the **owner-only** file
`.oci-kit/environments/rehearsal/sre-journey.json` (mode 0600), e.g.
`{"schema":"oci-sre-journey/1","journey":"create-task","assertions":["The task survives reload","The other account cannot read it"]}`.
The plan reports the assertion count; this declaration is neither executable
nor proof. Keep private identifiers, credentials and real customer data out
of test definitions, screenshots and prompts.

## Launch your own Next.js application

Follow the [own-app launch walkthrough](OWN-APP-LAUNCH.md) from the founder's Git
repository. In rehearsal, `doctor` and `journey` identify the launch profile and
return its `sre plan` command. For a nested app, select its directory in the
private [packaging descriptor](../recipes/README.md). Commit that app's
`package.json` declaring Next.js and its `package-lock.json`. Declare its existing
test command. The protected verifier binds that app selection to its signed results.

When a live doctor read fails, its private `permission_review` identifies the
OCI API operation, the permission to verify, the scope and a recheck command.
Check the selected identity, resource and region before requesting any change.
These operations use Oracle's [IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/iampolicyreference.htm),
[network](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm),
[certificate](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/certificatespolicyreference.htm),
[registry](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/registrypolicyreference.htm) and
[capacity](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm) permissions.

| When | Evidence to collect | Where to start |
|---|---|---|
| Pull request | Build and types, unit boundaries, negative cases, integration with disposable DB, API contract, accessible names/keyboard and browser checks for UI. Scan source, lockfiles, IaC and secrets. | Keep app-owned commands; see the application CI recipe under `recipes/sre-ci`. Untrusted PR jobs must never receive cloud or signing credentials. |
| Candidate | Test **one built digest** rather than rebuilding for each target. Verify its software inventory, image packages and settings, actual startup, direct HTTP 200, graceful shutdown and the agreed customer journey. | [Packaging](../recipes/README.md) and [two-user Taskboard checks](../blueprints/fullstack-container/PRODUCTION.md). Use test identities and private disposable data. |
| Rehearsal | Time-bounded load, timeouts and dependency recovery, positive and deny tests, rollback and isolated restore. Record recovery duration and age of restored data; compare both with business objectives. | [Migration acceptance](MIGRATION-ACCEPTANCE.md), [release/rollback](RELEASE-LIFECYCLE.md), [operations](OPERATIONS.md). Test retries/duplicates on queues; old/new readers on schema change. |
| After deployment | Read back the image on OCI, test anonymous HTTPS and a read-only business operation, inspect service signals, compare errors/latency, check alarm delivery and close the incident. | `observe --live`, `sre monitor`, and the environment's private dashboard. Track retained resources and continuing costs. |

**Try a bounded load check** on a separately started, digest-verified local candidate:
`python3 .oci-founder-kit/scripts/sre_latency_drill.py --port 18080 --route /healthz --latency-ms 250`.
It sends 12 loopback reads, checks the first response, and reports counts plus
time to headers. Choose a reviewed dependency-backed read and agreed threshold
for meaningful rehearsal. This small local sample does not predict capacity.

**Run a local restore rehearsal:** `python3 .oci-founder-kit/scripts/sre_restore_drill.py --postgres-bin /path/to/postgresql/bin`.
It starts two temporary Unix-socket-only databases, backs up synthetic records,
changes the source, restores into the second database, and checks restored
contents and the backup boundary. This demonstrates local PostgreSQL tooling.
It cannot satisfy the production restore check for the application's real backup.
Hosted sign-in, data writes, load, fault injection, notifications and restores
need a separately approved rehearsal, explicit limits and cleanup. Keep normal
production probes read-only.

## Scan before promotion

Use the pinned scanner with the exact private v2s2 image layout from packaging.
See [scan setup and limitations](../recipes/sre-ci/README.md). A source-only PR scan
and an SBOM are useful, but neither proves the final image was scanned.
Use the separate, reviewed OCI registry scan-target plan if the existing
registry does not already have one. Scanner/registry reports and the SBOM stay
private. Investigate High/Critical shipped findings, secrets, missing coverage
or stale data before promotion; assign a remediation owner and due date to
lower severity findings. Schedule the supplied deployed-image recheck on a
protected runner; connect failed jobs to the responder and test actual delivery.

## Check the exact production candidate

```sh
.oci-founder-kit/scripts/oci-kit sre check --environment production \
  --rehearsal rehearsal --plan-sha256 <reviewed-resource-plan-hash> --json
```

Use the SHA-256 printed for the **actual pending production Terraform plan**.
The rehearsal name selects the separate rehearsal deployment and its successful
receipt for the tested image. Do not substitute a rehearsal plan or receipt
hash for the production plan hash. `SRE_CHECK_INPUT` means the command stopped
at its input check; it has not evaluated the production plan or signed evidence.

In a restricted agent evaluation, the local app test exercises a static
checklist in a browser or the known original service on loopback. Neither
builds or runs the candidate image or verifies live OCI. Keep these limits
in the founder handoff even when every local test passed.

For the first production launch, use two reviewed image revisions in rehearsal
so that an image rollback can actually be tested. Bootstrap monitoring and the
private registry independently; a rehearsal is not a production promotion.
Use the signed verifier contract described in [the production gate guide](SRE-VERIFIER.md).
A protected verifier independent of the PR must verify the source, image,
target and observed customer behavior. Keep the signing key outside the repo
and the agent workspace. A signed unverified job result is still bad evidence;
do not let the candidate define, alter or run the protected signing job.
Missing, failed, stale or unsigned mandatory checks block named production
workload promotion. Replacing the image, target, policy or plan requires a new
decision. Bootstrap is separate; success never substitutes for owner approval
of that exact cloud plan. A local project gate cannot restrict direct actions
a tenancy administrator could independently perform outside the kit.

## Operate the service

Use the [monitoring guide](SRE-MONITORING.md) to select a primary and backup
responder, connect OCI alarms and notifications, and measure a specific
real-user operation. For Taskboard, `sre_latency_ms` optionally enables
aggregate counters for authenticated task-list reads. It emits closed-minute
deltas, skips incomplete intervals and includes explicit idle intervals; it
does not send any metrics to OCI itself. An approved collector must publish
the app dimensions described in the guide. Do not direct synthetic probes at
this authenticated task-list operation or pool synthetic successes with customer
traffic. Authentication failures and non-list paths are outside that handler
SLI and need their own coverage.

When paged: confirm the affected customer action from outside the platform;
then check DNS/TLS, backend health, the deployed revision, dependency failures
and resource saturation. Record impact, start/end, cause and remaining risks.
Notify the owner before changing traffic or rolling back; verify recovery from
the same customer boundary and confirm the alert cleared. Assign a follow-up
with a due date. At launch you can prove telemetry and paging work; an SLO
over 28 days remains **collecting history** until sufficient data exists.

## Evidence scope

This preview covers Taskboard, a founder-owned Next.js launch and hosting-first Next.js. Local tests, signed
CI evidence, an independently observed OCI rehearsal and actual production SLOs
are separate. No compliance certification, vulnerability-free claim or
high-availability claim is implied. Single-instance updates may interrupt
service. Never publish app inventories, raw security findings or private logs.

Design references: [Google SRE testing](https://sre.google/sre-book/testing-reliability/),
[alerting on SLOs](https://sre.google/workbook/alerting-on-slos/),
[NIST SSDF](https://doi.org/10.6028/NIST.SP.800-218), [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/),
[Anthropic's browser verification experience](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents),
and [OpenAI's Codex engineering report](https://openai.com/index/harness-engineering/).
