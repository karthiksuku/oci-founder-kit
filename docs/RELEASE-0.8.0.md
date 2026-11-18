# 0.8.0 preview: a faster first OCI setup

This release connects a new founder's local preparation, selected OCI profile,
administrator prerequisites and existing foundation workflow. Start with the
[new-account guide](NEW-OCI-ACCOUNT.md). Public research and design choices are
recorded in [ONBOARDING-RESEARCH.md](ONBOARDING-RESEARCH.md).

## What changed

- `oci-kit onboard inspect` works before installation, credentials or environments.
  It inventories local prerequisites, shows the current phase and returns a
  runnable next command without executing app code or cloud requests.
- `onboard prepare --dry-run` previews additive preparation. `prepare` composes
  the existing installer, project record, generic deployment attachment and
  explicit named environment while preserving the application. Existing or
  partial work is inspected or refused, never silently replaced.
- `onboard configure` saves explicit profile, region and authentication choices
  through the existing private, backed-up environment update. It preserves other
  target fields and invalidates affected evidence; it does not create credentials.
- Blocked foundation diagnostics now retain safe administrator instructions,
  unknown checks and environment-specific recheck commands in JSON and readable
  output. Arbitrary service/input text is excluded.
- Standalone [workload-access templates](../blueprints/workload-access/README.md)
  prepare explicit foundation-provisioner or observer policies for an existing
  human group and separate app/state compartments. Their grant boundaries and
  sensitive metadata access are documented. They grant neither bucket/repository
  updates nor complete application deployment or Terraform-state object access.
- The public site and agent instructions expose a New OCI account entry while
  retaining Build, Migrate and Continue.

## Acceptance and evidence scope

The [published preview record](https://github.com/karthiksuku/oci-founder-kit/releases/tag/v0.8.0)
contains the exact source identity, check results, distribution hashes and remaining
limitations. Local onboarding tests exercise fresh and existing apps, dry runs,
returned commands from an external directory, private configuration backups,
agent installation compatibility, wrong/source environments, occupied paths,
partial preparation, redaction and preservation of existing application files.
Terraform mock plans exercise both access roles and invalid boundaries. These
checks are local evidence, not tests of OCI authorization decisions.

## Boundaries retained

Account activation, MFA, initial root-child parent creation and human enrollment
remain explicit owner/administrator steps. These are not hidden in a workload
plan. Exact owner approval is still required for each cloud operation. Saved
configuration, successful local checks and older approvals authorize no writes.

The complete fresh-tenancy HTTPS deployment, effective IAM isolation, quotas and
actual capacity, two-user access, persistence, isolated recovery and rollback
still require approved live OCI acceptance. This preview makes no new live-cloud,
ordinary-agent founder-success, macOS/WSL2 or unattended-production claim.
Earlier agent-evaluation limitations remain documented in the
[0.7.0 preview](https://github.com/karthiksuku/oci-founder-kit/releases/tag/v0.7.0).

Hosted CI and authenticated release attestations remain pending workflow-authorized
GitHub access. Checksums establish byte identity, not publisher provenance.
Prepared workflow templates are not evidence that hosted workflows have run.
The kit uses public Oracle guidance and original code; it is not an Oracle
product, a complete enterprise landing zone or a certification of compliance.
