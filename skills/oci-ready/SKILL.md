---
name: oci-ready
description: Set up and diagnose OCI access before building or migrating an application. Guides credential configuration, checks local tools and read-only region and compartment access, and hands missing cloud foundations to oci-foundation.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.3.2"
---

# Prepare OCI access

Use the user's existing authentication and compartment when suitable. Do not
replace working profiles or create another administrator credential. Ask only
for the missing target and authentication choice; account verification and
browser sign-in stay with the user.

1. Read [credentials](references/credentials.md) when authentication needs setup
   or repair. Keep keys, session archives, tokens and passphrases outside the
   repository and chat. Do not read key/token contents to diagnose them.
2. Run `python3 <kit>/skills/oci-ready/scripts/oci_doctor.py` for offline checks.
   Explain missing tools and fix within the user's authorized local scope.
3. For an existing target, run the doctor with `--live`, an explicit `--region`,
   `--compartment-id`, `--profile` and `--auth`. For principal authentication,
   also supply `--tenancy-id` privately. Supported auth choices are `api_key`,
   `security_token`, `instance_principal` and `resource_principal`. The doctor
   makes IAM read calls only. Never paste credential values into a prompt.
4. Explain each blocked or unknown check. A denied read can mean authentication
   or authorization failure: do not infer the account is invalid, create broad
   IAM policy, or keep retrying unchanged credentials. Ask the account owner to
   resolve the relevant access or use the approved foundation workflow.
5. If a dedicated compartment or policies are missing, use `oci-foundation` if
   installed, otherwise inspect the kit's foundation guidance. Creating them is
   a cloud change: show the exact plan and cost implications, obtain owner
   approval, then use `oci-deploy`. Never deploy the application into the root.
6. Continue the original build or migration after readiness, preserving target
   and authentication choice. Plan review still needs service availability,
   quotas, identity and network scope, and the Well-Architected decision review.

The doctor emits JSON with `--format json`, otherwise concise Markdown. Exit
codes: 0 checks passed, 1 blocked, 2 bad input, 3 incomplete. Offline reports are
incomplete because live access was not tested. Private config/key/token files
must be owned regular files without symlinks; POSIX mode is 600 or 400. Native
Windows users must verify restrictive ACLs separately.

A passed live report confirms the selected region subscription and active,
readable compartment. It does **not** prove resource creation permission,
available capacity, service quotas, production security or a working app.

Finish with the useful next step and remaining blockers. Do not print account
identifiers or raw credential/CLI error output in shared reports.

For failed build, image, network or runtime checks, follow the read-only
[troubleshooting guide](references/troubleshooting.md). Diagnose first; a
repair that changes IAM, resources or data needs its own reviewed plan.
