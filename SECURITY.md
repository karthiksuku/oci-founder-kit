# Security

The kit includes offline repository tools, credential setup guidance, opt-in
read-only OCI diagnostics and approval-gated infrastructure deployment. Local
price lookup calls Oracle's public price API without credentials. Other live
OCI operations use the user's privately configured authentication; no credentials
are bundled or collected by a hosted kit service.

- Review the kit before installation. Skills and scripts run with the coding
  agent's user permissions. The installer adds project-local files only and
  refuses overwrites; it does not configure accounts or call cloud APIs.
- Never paste keys, tokens, passwords, customer records, Terraform state or
  credential configuration into chat, GitHub issues or shared reports. Keep
  credential files outside the repository with restrictive permissions.
- Prefer temporary sessions or workload principals where appropriate. Keep
  human deployment identity separate from application runtime permissions.
- Every cloud write requires approval of its exact plan, target and cost. The
  deploy tool binds saved plan bytes and expiry; it does not prove a person
  consented or stop another process with the same OS account from bypassing it.
  Retain coding-agent approval prompts and never use bypass-permission modes.
- Provider failure logs under .gate are private and can contain sensitive
  diagnostics. Public output omits raw Terraform and OCI stderr. Inspect and
  redact evidence locally before sharing. Failed applies can leave resources.
- A static scanner does not execute source, prove compatibility or authorize
  a data transfer/cutover. Inspect untrusted package lifecycle scripts before
  running application builds. Preserve the original service and rollback path.
- Sandbox blueprints do not establish production security. Validate identity,
  authorization, HTTPS, secret handling, state, backups and recovery per workload.

Report a vulnerability privately through the maintainer's GitHub profile contact
or GitHub private vulnerability reporting if enabled. Do not open an issue
containing exploit credentials, customer data or unredacted state/receipts.
