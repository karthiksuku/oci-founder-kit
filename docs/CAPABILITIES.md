# Capability and platform support

Generated from [capabilities.json](capabilities.json). Evidence checked 2026-11-20.

An evidence label applies only to the scope described. Local tests do not establish OCI deployment, effective IAM or recovery.

| Capability | Evidence | Prerequisites | Limitations |
|---|---|---|---|
| [New OCI account](../docs/NEW-OCI-ACCOUNT.md) | preview | Python 3.11+; A reviewed kit checkout or project-local installation; before installation use the checkout command in the guide | No cloud requests or automatic account activation, human enrollment or IAM grants.; Onboarding configuration preserves other selections and refuses region or profile changes for bound resources.; Local inspection is not token validity, permission, capacity or deployment evidence. |
| [Prepare deployment inputs](../docs/DEPLOYMENT-CONFIGURATION.md) | local-tested | Explicit web-container environment; Reviewed infrastructure and private nonsecret application choices | Local configuration only; runtime IAM, image publication and each cloud operation remain separately reviewed.; Existing selections and automatic Terraform inputs are never overwritten. |
| [Well-Architected evidence](../docs/WELL-ARCHITECTED-REPORT.md) | local-tested | Explicit OCI environment; Existing private reports for observed controls | Read-only projection of local reports, not certification or authenticated proof.; Unknown IAM, stale observations and missing recovery evidence remain incomplete. |
| [Your launch acceptance map](../docs/FOUNDER-JOURNEY.md) | local-tested | Explicit OCI environment | Missing hosted sign-in, persistence, isolated restore and rollback evidence cannot become a passing journey.; Restricted harness, ordinary agent and live OCI evidence remain separate. |
| [Continue the right environment](../docs/WORKFLOW.md) | local-tested | Existing project record; Explicit environment | Progress is not approval or live verification. |
| [Package your application](../recipes/README.md) | local-tested | Reviewed application commands; Application runtime; Docker with Buildx for generated builds; reviewed Skopeo v2s2 layout | Container success does not establish migration compatibility. |
| [Connect OCI prerequisites](../blueprints/workload-foundation/README.md) | local-tested | OCI account; Authorized parent compartment; Administrator for IAM changes | No automatic tenancy-wide grants or certificate private keys in state.; Output handoff is owner-supplied configuration; live IAM and resource acceptance remain required. |
| [Understand a running application](../docs/OPERATIONS.md) | local-tested | Bound deployment receipt; Read access to selected resources | Missing permissions and delayed costs remain unknown.; Service-contract and refusal tests are local; live workload readback acceptance is pending. |
| [Update with a recovery path](../docs/RELEASE-LIFECYCLE.md) | local-tested | Current bound deployment and behavior evidence; Previous accepted digest for rollback | Rollback needs new exact cloud plans; a single-instance update may interrupt service. |
| [Add durable background work](../blueprints/saas-essentials/README.md) | local-tested | PostgreSQL; Separate worker identity; Reviewed ownership transfer | Native scheduling remains experimental until its exact cloud path is accepted.; PostgreSQL/HTTP and local containers exercised; OCI Queue and IAM acceptance are pending. |
| [Share a safe support summary](../docs/OPERATIONS.md) | local-tested | Explicit environment; Private local reports | Allowlisted summary only; never automatically uploads. |
| [Test and operate your app](../docs/SRE.md) | preview | Named rehearsal environment for planning; separate production environment and exact saved plan for promotion. | Agent summaries and local drills do not authorize production.; Live monitoring, hosted CI and OCI deployment require separate setup and acceptance. |
| [Launch your own Next.js app](../docs/OWN-APP-LAUNCH.md) | preview | Named web-container build environment and a Next.js application; Existing tests, identity and data providers | Hosted sign-in, isolation, rollback and an independently operated verifier require a live rehearsal. |
| [Preview launch costs](../docs/LAUNCH-COST.md) | local-tested | Reviewed web-container footprint and dated rates | Totals can be incomplete. Delayed or inaccessible billing evidence stays unknown. |
| [Try the app with a customer](../docs/CUSTOMER-TRIAL.md) | preview | Named rehearsal, current image readback and externally enforced tester access | The owner operates the identity provider and verifies session revocation. No messages are sent. |

| Platform | Evidence | Scope |
|---|---|---|
| linux | local-tested | Installation and upgrade; individual runtime checks carry separate evidence. |
| macos | unverified | POSIX implementation; clean-machine acceptance pending. |
| wsl2 | unverified | Linux environment required; clean-machine acceptance pending. |

| Runtime or compatibility | Reviewed scope |
|---|---|
| python_required | >=3.11 |
| terraform_tested | 1.16.6 |
| oci_provider_tested | 9.10.0 |
| compatibility | Existing v0.5/v0.6 commands and records; reviewed local upgrade with private backups. |
