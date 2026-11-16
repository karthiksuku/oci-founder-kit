# Record releases and prepare rollback

Release records are private observations of a selected environment. They link
the application source fingerprint, immutable image digest, latest bound apply
receipt, live read-only image observation and selected passed runtime or migration
checks. A source fingerprint is not a Git commit. Anonymous HTTPS health is
recorded as limited acceptance; it never establishes hosted sign-in, two-user
isolation, persistence, restore or full production readiness.

Run the project-local facade from the application folder with the selected
environment. After an approved deployment, collect actual runtime behavior and
the current live image observation:

```sh
python3 .oci-founder-kit/scripts/kit.py verify --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py observe --project . --environment rehearsal --live
```

For a migration, use `verify --kind migration --contract` with the reviewed
private contract instead of relying on the anonymous health check. Review the
returned reports. Only when behavior passes and the live observation establishes
the deployed image, record the release using the exact `evidence` path returned
by `verify`:

```sh
python3 .oci-founder-kit/scripts/kit.py release record --project . --environment rehearsal \
  --evidence '<verify-evidence-path>'
python3 .oci-founder-kit/scripts/kit.py release list --project . --environment rehearsal
```

Replace the quoted placeholder with the actual report path under
`.oci-kit/environments/rehearsal/evidence/`. No example evidence is a passing
result. Record each accepted deployment before adopting another image. The
Python integration remains `scripts/releases.py`.

`record` requires the explicit selected-environment behavior report and the most
recent read-only observation. Both must match current source, kit, configuration
and image, and be no more than 24 hours old. Injected test clients, mismatched
image identity, a failed observation, stale evidence and interrupted/latest failed
deployment receipts cannot create an accepted release record. Unknown cost or
monitoring metadata remains unknown; it is not converted into production success.
Multiple observations with the same latest timestamp require a fresh observation.

The append-only ledger lives under `.oci-kit/environments/NAME/releases/`, uses
private owned files and links records by content hash. It preserves historical
evidence across target updates and rejects missing/replaced sequence entries.
Like other local receipts it is not a cryptographically authenticated external
audit log; another process with the same operating-system account can modify
local state. Nothing is uploaded automatically.

Rollback preparation selects the previous different accepted digest. The current
environment must still identify the latest accepted deployment. Supply existing
private JSON Terraform variables whose `app_image` uses the current OCIR
`repository@sha256:digest` form. The helper copies those variables into private
state and changes only that image digest. It never replaces application files,
changes a database, transfers job ownership or runs cloud commands.

Prepare the local rollback proposal using the selected stack's actual private
JSON variable file:

```sh
python3 .oci-founder-kit/scripts/kit.py release rollback --project . --environment rehearsal \
  --variables deploy/rehearsal/terraform/terraform.tfvars.json
```

Review the generated private proposal, copied variables and expiry. Approving
its exact hash permits only local target adoption. Adoption rechecks the source,
kit, environment, receipt, ledger and variable hashes; it backs up the old
configuration and makes previous evidence stale. Approval is consumed before
adoption, so an interrupted attempt cannot silently reuse it. A result file
records completed local adoption; an attempt without a result needs review.
Only after the owner approves that exact local proposal, adopt it using its hash:

```sh
python3 .oci-founder-kit/scripts/kit.py release rollback --project . --environment rehearsal \
  --approve '<approved-local-proposal-sha256>'
```

This approval changes private local configuration only; no cloud rollback has
run. Adoption also creates the proposal's named new private `*.tfvars.json` directly
inside the selected stack. Use the returned `var_file` basename for the next
`release plan --var-file` call: the backend gate accepts stack-local variable
files only. Existing variable files are never overwritten. If copying is
interrupted after target adoption, inspect the private attempt and configuration
backup before preparing a replacement proposal.

After local adoption, substitute its returned `var_file` basename below to
prepare a **new** backend planning request:

```sh
python3 .oci-founder-kit/scripts/kit.py release plan --project . --environment rehearsal \
  --var-file '<returned-var-file-basename>'
```

Review that backend request's private scope, costs and expiry. Only after its
exact approval, execute it once:

```sh
python3 .oci-founder-kit/scripts/kit.py release run --project . --environment rehearsal \
  --approve '<approved-backend-operation-sha256>'
```

The completed planning operation returns a separate resource plan. Review its
changes and obtain its own exact approval before applying:

```sh
python3 .oci-founder-kit/scripts/kit.py release apply --project . --environment rehearsal \
  --approve '<approved-resource-plan-sha256>'
```

All quoted placeholders mean the actual reviewed values, not reusable approvals.
Prior deployment approvals never transfer. Recheck image availability, database/schema compatibility and actual
application behavior after applying the reviewed rollback. The single-instance
topology may interrupt service; rollback is not a promise of zero downtime.
If a deployment failed or is interrupted, inspect its private receipt and current
state first instead of skipping the latest attempt to select an older success.
