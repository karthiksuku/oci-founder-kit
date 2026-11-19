# From your welcome email to your first OCI environment

Start here when your OCI account is new, or when you have an app but no deployment
environment. Claude Code or Codex can inspect the project, prepare the local kit
and work through missing prerequisites. Account activation, security verification
and access decisions stay with you and your authorized administrator.

This is a development preview. Local preparation is not a cloud deployment,
permission grant or Well-Architected certification. The
[capability registry](CAPABILITIES.md) records the current evidence scope.

## Start with one inspection

Open the intended application folder in your coding agent and use this prompt:

```text
Use OCI Founder Kit to get this project ready for OCI. Begin with onboard inspect,
even if there is no installation, credential profile or environment yet. Preserve
my app, existing services and uncommitted changes. Explain the current phase,
collect only its missing nonsecret choices together, and give me one next action.
Guide account activation and the administrator prerequisites where needed.
Prepare an explicitly selected rehearsal environment locally. Review the design
against OCI Well-Architected guidance and show each exact cloud plan and costs
for approval before running it. Keep passwords, keys and tokens out of chat.
```

Or inspect from a reviewed checkout outside your application:

```sh
git clone https://github.com/karthiksuku/oci-founder-kit.git
python3 oci-founder-kit/scripts/kit.py onboard inspect \
  --project /absolute/path/to/my-app
```

Use your intended path. Inspection does not require a named environment or OCI
credentials. It performs local checks and provides the next step; it does not
install tools, sign in, run app commands or contact OCI. Add `--json
--non-interactive` for an agent-readable result. If a kit is already installed,
use its supported commands or the [reviewed update path](INSTALL.md#update-or-remove-a-project-installation).

## Prepare your local environment

After inspection, use an explicit name and role. For an existing application or
an empty existing setup folder, preview the additive local changes first:

```sh
python3 oci-founder-kit/scripts/kit.py onboard prepare \
  --project /absolute/path/to/my-app --mode existing \
  --environment rehearsal --role rehearsal --task build \
  --agent both --stack custom --dry-run
```

Review the proposed installation, deployment directory and environment. Then run
the same command without `--dry-run` to prepare the local files:

```sh
python3 oci-founder-kit/scripts/kit.py onboard prepare \
  --project /absolute/path/to/my-app --mode existing \
  --environment rehearsal --role rehearsal --task build \
  --agent both --stack custom
cd /absolute/path/to/my-app
python3 .oci-founder-kit/scripts/kit.py onboard inspect \
  --project . --environment rehearsal
```

This composes the existing installer, deployment attachment and environment
helpers. It adds the kit, a private project record and a generic web-container
target; it preserves application files. The environment points at the actual
Terraform directory, `deploy/rehearsal/terraform`. Existing targets are inspected
and conflicting or partial work is preserved for review, not overwritten.
Preparation never creates OCI resources or transfers old approvals.

For a new app, choose `--mode new --task build --stack nextjs` or `--stack fastapi`
and a new folder under an existing parent, or an empty existing folder. Your agent
still builds the application. Use `--task migrate` for hosting-first migration;
keep the existing data, identity, storage and background services initially.
Use `--task setup` when preparing access without building an app. The optional
Taskboard example has its own [explicit creation path](INSTALL.md#create-a-new-editable-starter).

When the context is already known, add `--target-file /private/target.json` to
both preview and preparation to supply the environment's initial nonsecret
target fields using the [existing schema](ENVIRONMENTS.md). This is for first
creation; changing an existing environment uses `environment configure` as
described in the advanced configuration path below. For the initial profile,
authentication method and region, use `onboard configure`. Keep account
identifiers and local configuration private.
Saved choices are not evidence that authentication or deployment permissions work.

## Work through the next phase

| Phase | Founder or administrator | Agent and kit | Evidence before moving on |
|---|---|---|---|
| Activate | Open the welcome email, complete sign-in and required verification; retain a recovery method | Explain the steps without receiving passwords or MFA codes | Owner confirms account access; this is not a deployment-permission check |
| Local access | Choose the OCI profile and workload region; complete browser sign-in | Inspect tools and selected profile safely | Local configuration checks, then explicitly requested read checks |
| Initial administration | Establish the parent compartment, intended human group and membership | Prepare the scoped administrator handoff below | Administrator review and observed allowed/denied access |
| Foundation | Approve the exact compartment, network, state and registry plans | Reuse approved resources or prepare separate plans; import outputs privately | Exact plan receipts plus resource and access checks |
| First deployment | Confirm hostname, certificate responsibility and exact deployment plan | Package and test the app, publish the approved digest, deploy and verify | Actual HTTPS, sign-in, isolation, persistence and recovery results |

An absent certificate should not prevent building the app locally. An unreadable
resource stays unknown; do not infer that it is absent or change identities to
bypass an access restriction.

## Authenticate without sharing credentials

First complete Oracle's [first-sign-in flow](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingin_topic-Signing_In_for_the_First_Time.htm).
Install the CLI through its [official instructions](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm).
Reuse a suitable existing profile. For browser-based access, run the official
session command yourself and choose an unused profile when creating a new one:

```sh
oci session authenticate
```

Afterward, explicitly select that profile, region and authentication method in
the inspection. Replace the uppercase placeholders with your nonsecret choices:

```sh
python3 .oci-founder-kit/scripts/kit.py onboard inspect --project . \
  --environment rehearsal --profile PROFILE --region REGION --auth security_token
```

These inspection flags apply to this invocation only. They do **not** save or
change the environment's profile, authentication method or region.

### Save the selected context

Save these three nonsecret choices together without assembling a JSON file.
Replace the placeholders with the same selected profile and region:

```sh
python3 .oci-founder-kit/scripts/kit.py onboard configure --project . \
  --environment rehearsal --profile PROFILE --region REGION --auth security_token
python3 .oci-founder-kit/scripts/kit.py onboard inspect --project . --environment rehearsal
```

`onboard configure` merges only profile, authentication method and region into
the named environment. It preserves resource selections, backend and component
bindings, keeps a private backup before changes and makes affected evidence
stale. It neither creates credentials nor contacts OCI. Old approval hashes do
not transfer. The next inspection reads the saved choices without requiring
those three flags again.

If resources are already bound, a different profile or region requires the
reviewed full-configuration path; this shortcut refuses to retarget them.
A nondefault OCI config file needs explicit `--config-file /private/config`
on configure and inspection. The returned next command carries that path, but
it is not a saved environment field. Use `--auth api_key` only when that is
the selected profile's method.

For broader changes, use a new owner-only target file under ignored `.oci-kit/`
with the [existing environment schema](ENVIRONMENTS.md#3-configure-the-private-target-and-run-the-doctor).
Keep the complete target object, change only the intended fields and use
`environment configure --project . --environment rehearsal --target-file
.oci-kit/rehearsal-target.json`. Unlike `onboard configure`, **environment
configure replaces the complete target object; it does not merge it**.
Preserve existing references and never put credential values in this file.

An offline inspection cannot prove token validity. Validate or refresh sessions
through [Oracle's session workflow](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm),
which may require browser reauthentication. API signing keys remain supported
when appropriate; follow the [credential guide](../skills/oci-ready/references/credentials.md).
Keep key and token files outside the repository. Do not paste the welcome email,
activation link, config contents or session archive into the agent.

## Administrator handoff for an empty tenancy

The kit's workload foundation requires an existing, authorized non-root parent.
A new tenancy may not have one. Do this initial review before asking the agent
to prepare workload resources; the agent does not automate these Console writes.

1. **Confirm the boundary.** Identify the intended tenancy, identity domain,
   home region and workload region privately. Keep normal administrator recovery
   access. The tenancy home region and workload region may differ; the kit's
   compartment and IAM policy plans use the home region.
2. **Establish human access.** In the chosen identity domain, reuse or create the
   intended developer group and enroll only the selected people. Review user
   creation and each membership change separately. Human groups are different
   from runtime dynamic groups. Follow Oracle's [group guide](https://docs.oracle.com/en-us/iaas/Content/Identity/groups/create-groups.htm)
   and [user-creation guide](https://docs.oracle.com/en-us/iaas/Content/Identity/users/create-user-accounts.htm).
3. **Establish the parent.** If missing, review the exact name and root-parent
   placement, then have the authorized administrator create the initial parent
   using [Oracle's compartment instructions](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm).
   Pass its identifier privately to the kit. Application and state compartments
   are separate children created through subsequent reviewed kit plans.
4. **Review permissions for the selected work.** Use existing authorized roles
   where possible. The legacy foundation's inspection grant cannot deploy an app.
   Select specific resource permissions for foundation provisioning, application
   deployment and runtime identities separately. Review attachment scope and
   inherited policies using [Oracle's policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingpolicies.htm).
   Never substitute a tenancy-wide administrator grant for a missing permission.
   The optional [workload-access templates](../blueprints/workload-access/README.md)
   prepare an explicit foundation-provisioner, observer, app-deployer,
   state-operator or image-publisher role for existing groups and compartments.
   Roles remain separate; runtime identity and human enrollment are prerequisites.
   State and publication permissions have documented collateral authority. Review
   each role's remaining powers and exclusions before using it.
5. **Verify and hand back.** Check the intended operator can inspect the selected
   target; verify access to an unrelated target is denied unless separately
   authorized. Review state access with a separate identity. A private bucket
   flag and a successful Terraform plan do not establish effective isolation.

Keep the administrator packet in private project storage. Include selected
resource identifiers there, the requested operations, current denial codes,
the exact proposed policy statements, the reviewer and the required access
checks. Do not send it automatically. If the current operator cannot inspect
inherited access, the administrator must resolve that unknown.

## Continue into the existing workflow

Once a named environment exists:

```sh
python3 .oci-founder-kit/scripts/kit.py foundation inspect --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py doctor --project . --environment rehearsal
```

Follow the returned phase and administrator instructions. The
[foundation guide](../blueprints/workload-foundation/README.md) prepares components
one at a time and passes their outputs into private configuration. Use
`doctor --live` only when ready for its documented read-only requests; successful
reads do not prove regional capacity or permission to create every resource.

Then follow [packaging](../recipes/README.md) and the
[deployment workflow](WORKFLOW.md). Hostname ownership, certificate issuance and
renewal responsibility must be established before HTTPS acceptance. DNS changes,
IAM changes, state tests and deployment each keep their exact-plan boundaries.

Use the [Well-Architected review](../skills/oci-foundation/references/well-architected.md)
to record the required control, selected implementation, evidence, remaining
risk and owner. Terraform establishes infrastructure configuration; recovery,
effective permissions and application behavior require actual checks. Review
retained resources and dated costs after failures or teardown; budget alerts
are not spending caps.

Research and scope: [public-source decisions](ONBOARDING-RESEARCH.md).
