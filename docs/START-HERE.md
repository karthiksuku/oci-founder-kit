# Start here: let your agent build or migrate

Install the kit as described in the root [README](../README.md), then open Claude
Code or Codex in your application repository. You can also tell the agent to read
the repository URL and perform that installation locally. The kit is source code
and skills, not a hosted service. Your coding-tool account and OCI account are separate.

## New application

```text
Use oci-kit. Build a small app for my team to track customer requests.
Inspect this repository first. Implement a useful local version with tests,
help me authenticate to OCI, prepare a dedicated compartment and scoped IAM,
and review the design against OCI's Well-Architected Framework.
Show the exact deployment plan and recurring cost before making cloud changes.
```

The agent starts local development while you complete any account enrollment or
administrator steps. It chooses a maintainable architecture based on the workload,
not Kubernetes by default. Expect a working local project, readiness results,
a deployment plan and explicit unfinished acceptance checks.

## Existing Vercel or Netlify application

```text
Use oci-kit to migrate this app to OCI. Identify framework/runtime versions,
functions, edge middleware, image handling, scheduled jobs, storage, database,
identity, environment variable names and other hosted-service dependencies.
Preserve existing behavior, implement local changes and test them. Prepare an
OCI staging deployment and a data/cutover/rollback plan. Do not modify the source
account, migrate production data or switch DNS without my explicit approval.
```

The scan cannot see console-only settings, provider-managed data, traffic or
service contracts. The agent must ask for the missing facts without requesting
secret values. Keeping an external database or identity service can be a valid
first migration stage; show what remains external and why.

## OCI credentials and initial setup

Use [oci-ready](../skills/oci-ready/SKILL.md) and its
[credential guide](../skills/oci-ready/references/credentials.md). Existing local
profiles, temporary sessions and workload principals are preferable to copying
credentials. A new tenancy requires user enrollment and possibly an administrator
to register the public key and prepare a parent compartment and group. Never paste
private key material or tokens into chat. No personal tenancy defaults ship here.

The doctor defaults to offline checks. `--live` authorizes the documented read
probes, not cloud writes. Successful authentication does not establish permission
to deploy every resource or confirm regional capacity.

After access is understood, use [oci-foundation](../skills/oci-foundation/SKILL.md)
for a scoped foundation plan. New IAM grants are reviewed separately from app
resources. Do not solve insufficient permissions with tenancy-wide administration.

## Deploy, verify and operate

1. Run the application's tests and the relevant infrastructure validators.
2. Review the five-pillar decisions, resource selection, external providers,
   dated recurring costs, access changes, recovery objectives and rollout plan.
3. Inspect the saved Terraform plan through `oci-deploy`. Explicitly approve that
   exact plan only when its target and consequences are correct.
4. Verify the running app: HTTPS, sign-in, permission isolation, persistence,
   health, logs and backup recovery. A unit-test pass is not a deployment receipt.
5. Retain update/rollback and approved cleanup instructions. Check for residual
   resources after partial failures or teardown. Review running costs separately.

The bundled full-stack blueprint is a restricted sandbox. The agent must implement
and validate the missing production controls before exposing it to real users.

## Troubleshooting and updates

- Skill missing: restart the agent session, check installation.json in
  `.oci-founder-kit`, or open the source `skills/oci-kit/SKILL.md` directly.
- Existing install: the installer refuses overwrites. In a clean version-controlled
  app, review the new kit release, remove only its installed bundle and matching
  generated entry folders, then reinstall. Preserve app code and other skills.
- Login or region failure: use the doctor's redacted result and official credential
  instructions. Do not send config files, token files or Terraform state to issues.
- Denied or unknown checks: the agent should explain the specific administrator
  action or unverified capability; it must not claim full readiness.
- Invalid app build: keep cloud deployment stopped and resolve local failures.
- Failed infrastructure apply: preserve the private receipt, inspect state and
  produce a recovery plan. Never automatically destroy shared resources.

The installer preserves your existing AGENTS.md, CLAUDE.md, agent settings and
skills. It does not install either coding tool or connect their accounts.
