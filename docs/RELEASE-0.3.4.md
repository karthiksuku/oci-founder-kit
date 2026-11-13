# 0.3.4 preview — synthetic backend recovery rehearsal

The kit now includes a fixed, separately approved native OCI backend rehearsal
and a separate exact-version cleanup operation. It uses synthetic outputs only:
write generation 1, verify real plan lock contention and normal release,
overwrite with generation 2, then restore the recorded first version into a
separate key. It creates no infrastructure resources and runs no Terraform apply.
See the [rehearsal guide](../skills/oci-deploy/references/backend-rehearsal.md).

The gate binds identity, source, target, binary, expiry and one attempt. A
constrained runtime transform handles native lineage and serial values. Private
receipts retain actual version IDs and outcomes. Native output is capped while
excess bytes are drained; timeouts and interrupted launches stop further work
without killing lock owners or permitting automatic cleanup.

Cleanup inventories and validates the rehearsal's exact state/lock versions.
After independent owner approval, it deletes only those version IDs, removes
historical data before markers, and checks current and version inventories.
There is no workspace/prefix deletion, forced unlock or arbitrary state repair.

## Verification

The full Python suite passed **494 tests**, including 98 focused backend tests.
The repository validator, Claude plugin validator, Terraform formatting and
Git whitespace checks passed. Local socket tests required permission to bind
loopback addresses. An earlier full run found four documentation links to the
not-yet-written release page; after adding that page, the complete suite passed.

Real local Terraform 1.16.6 checks used the production fixture and process
controller. A competing plan failed on the observed native lock without reaching
its data source, succeeded after normal release and left state unchanged.
Synthetic overwrite advanced the serial as expected; recovery preserved the
primary. A bounded fixture timeout caused native failure and normal unlock.
These checks used the **local backend**, not OCI storage.

Real harmless subprocess probes verified capped output, normal completion after
a controller timeout, no retry after failure, and expiry before launch. Review
reproduced an interrupted-launch bookkeeping bug before the fix: a native child
could be alive but untracked. Regression checks now require immediate tracking
and conservative cleanup refusal after an uncertain launch. No process-kill or
force-unlock shortcut was used.

The optional OCI SDK adapter was checked with SDK 2.167.2, synthetic signing
keys, real SDK models and fake service clients. A separate live **read-only**
check verified the selected existing bucket's identity, private visibility,
versioning and an empty unused rehearsal prefix. No OCI backend was initialized,
no state was uploaded and no retained version was deleted by this validation.

## Post-release hook verification — 13 November 2026

Three isolated Claude Code 2.1.251 probes exercised the published hook script
`7381dc1854dbf6dca7ade94e460ec7ce99ce576ed5476d1c53917e62d649c147`.
Host events verified SessionStart context, denials of fake Terraform init/plan
and Skopeo publication commands, a successful fake saved-plan inspection, and the
non-blocking Stop reminder. A separate literal Git commit attempt was blocked
specifically for a staged synthetic private backend file; no commit occurred.

One Write produced an invalid synthetic Python file and a matching fresh
validation-cache entry. Claude reported the expected syntax diagnostic. The
stream does not expose a raw PostToolUse response, so that warning text remains
model-reported, corroborated by the cache and exact Write/file evidence. All
temporary hooks were removed normally. No application code or OCI command ran.
The release tag and executable source were unchanged by this follow-up.

The isolated Codex review fixture was refreshed to the same published hook code.
Read-only discovery found four enabled but untrusted hooks and no configuration
errors. No trust setting was changed or hook executed. See [hook compatibility
and evidence](HOOKS.md) for the precise coverage and remaining limitations.

## Remaining acceptance

Live OCI write/overwrite, lock contention, historical-version restore and
permanent cleanup remain pending exact operation approvals. Effective IAM
isolation remains independent: private bucket visibility and a successful
synthetic test cannot establish confidentiality for credential-bearing state.
The full hosted application, identity, HTTPS, Vault, recovery, rollback and
teardown still need workload-specific live evidence.

The validation Actions workflow remains a template because the available
publication credential lacks workflow permission. Trusted Codex hook runtime
also remains unverified. The static founder website was unchanged by this patch.
