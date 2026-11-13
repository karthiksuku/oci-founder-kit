# OCI credentials without sharing secrets

Checked against official Oracle documentation on 13 November 2026. Installation,
sign-in and OCI tenancy enrollment have separate account requirements. The kit
does not create accounts, bypass verification or provide cloud credits.

## Choose the identity that fits

| Environment | Approach | Owner action |
| --- | --- | --- |
| Local computer with browser access | Temporary CLI session using `oci session authenticate`; pass `--auth security_token` explicitly | Complete browser sign-in and select the intended profile and region |
| Existing local automation profile | API signing key with a narrowly scoped IAM group | Use the official setup flow; upload only the public key to OCI |
| OCI Compute instance | Instance principal and scoped dynamic group/policy | Approve the exact IAM plan and verify the instance membership |
| Supported OCI managed workload | Resource principal and scoped policy | Confirm service support and the exact resource membership |

OCI Cloud Shell already supplies a pre-authenticated CLI. Its session may use
an authentication mechanism outside the doctor's four explicit modes. Do not
force an existing Cloud Shell identity into an API-key profile: inspect the
official Cloud Shell instructions and perform the same read-only checks using
its native CLI identity. Do not claim that an unrun doctor passed.

## Local setup

1. Install OCI CLI from the [official installation guide](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm).
2. Prefer an existing working profile. For a new interactive session use
   `oci session authenticate`, complete the browser flow yourself, then specify
   that profile and `--auth security_token` in subsequent CLI calls.
3. For API-key authentication use `oci setup config` and the official
   [key setup guide](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm).
   The API signing key is different from an instance SSH key. The private key
   never goes to GitHub, chat or browser code; OCI receives the public key only.
4. Keep config at `~/.oci/config` or a private explicit path outside the project.
   Use absolute key/token paths. Preserve unrelated profiles. On POSIX, set the
   private credential directory to mode 700 and config/key/token files to mode
   600 (400 is also accepted by the doctor). On Windows configure owner-only
   ACLs; POSIX mode checks do not establish Windows ACL safety.
5. Do not store a passphrase in config. Use an approved runtime secret source;
   never put a passphrase on a command line or in a saved agent prompt. If the
   chosen CLI flow cannot use that source, let the owner handle the interactive
   authentication instead of weakening key protection.
6. Run the doctor offline first, then with `--live` after privately supplying
   the target region and a dedicated non-root compartment. The report omits
   identity values and raw command output.

The doctor never modifies config, creates keys, uploads a public key or refreshes
a session. The agent can guide and perform explicitly authorized local setup;
identity or policy writes require the cloud approval workflow. Do not silently
overwrite profiles, rotate shared keys or add tenancy-wide administrator access.

## Recovery

- **Expired session:** validate or refresh through the official session workflow;
  interactive reauthentication may be required. Do not print the token.
- **Not authorized / not found:** OCI can hide resources the identity cannot
  read. Check identity, selected region and compartment with the owner before
  declaring that the compartment does not exist.
- **No compartment yet:** prepare a dedicated compartment and scoped role plan
  through the foundation workflow. The application must not use the tenancy root.
- **Readiness passes but deployment fails:** inspect required service limits,
  region availability, exact resource policy and capacity. Read-only access is
  not proof that writes will succeed.

## Sources

- [SDK/CLI config fields and profile inheritance](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)
- [CLI session authentication, validation and refresh](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm)
- [Instance principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm)
- [Cloud Shell](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro.htm)
