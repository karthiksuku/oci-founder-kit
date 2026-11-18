# Capability and platform support

Generated from [capabilities.json](capabilities.json). Evidence checked 2026-11-18.

An evidence label applies only to the scope described. Local tests do not establish OCI deployment, effective IAM or recovery.

| Capability | Evidence | Prerequisites | Limitations |
|---|---|---|---|
| [New OCI account](../docs/NEW-OCI-ACCOUNT.md) | preview | Python 3.11+; A reviewed kit checkout or project-local installation; before installation use the checkout command in the guide | No cloud requests or automatic account activation, human enrollment or IAM grants.; Onboarding configuration preserves other selections and refuses region or profile changes for bound resources.; Local inspection is not token validity, permission, capacity or deployment evidence. |
| [Continue the right environment](../docs/WORKFLOW.md) | local-tested | Existing project record; Explicit environment | Progress is not approval or live verification. |
| [Package your application](../recipes/README.md) | local-tested | Reviewed application commands; Application runtime; Docker with Buildx for generated builds; reviewed Skopeo v2s2 layout | Container success does not establish migration compatibility. |
| [Connect OCI prerequisites](../blueprints/workload-foundation/README.md) | local-tested | OCI account; Authorized parent compartment; Administrator for IAM changes | No automatic tenancy-wide grants or certificate private keys in state.; Output handoff is owner-supplied configuration; live IAM and resource acceptance remain required. |
| [Understand a running application](../docs/OPERATIONS.md) | local-tested | Bound deployment receipt; Read access to selected resources | Missing permissions and delayed costs remain unknown.; Service-contract and refusal tests are local; live workload readback acceptance is pending. |
| [Update with a recovery path](../docs/RELEASE-LIFECYCLE.md) | local-tested | Current bound deployment and behavior evidence; Previous accepted digest for rollback | Rollback needs new exact cloud plans; a single-instance update may interrupt service. |
| [Add durable background work](../blueprints/saas-essentials/README.md) | local-tested | PostgreSQL; Separate worker identity; Reviewed ownership transfer | Native scheduling remains experimental until its exact cloud path is accepted.; PostgreSQL/HTTP and local containers exercised; OCI Queue and IAM acceptance are pending. |
| [Share a safe support summary](../docs/OPERATIONS.md) | local-tested | Explicit environment; Private local reports | Allowlisted summary only; never automatically uploads. |

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
