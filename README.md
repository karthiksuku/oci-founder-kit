# OCI Founder Kit

**Point Claude Code or Codex at your app. Set up OCI, build it, or migrate it.**

An installable agent toolkit for founders and developers. It helps your coding
agent inspect the project, configure OCI access, prepare compartments and scoped
IAM, build or adapt the application, and plan a deployment using OCI
Well-Architected guidance. Cloud changes happen only after you approve the exact
plan and its costs. Independent project; not an Oracle product.

## Start with your coding agent

Paste this into Claude Code or Codex in your application project:

> Read https://github.com/karthiksuku/oci-founder-kit and its README. Install the
> kit into this project with scripts/install.py. Use oci-kit to build my app on
> OCI. Inspect the project, guide any credential setup, prepare the compartment
> and security foundation, and test locally. Show the exact infrastructure plan
> and costs before making cloud changes. Never ask me to paste private keys.

For an existing hosted app, replace the goal with:

> Migrate this Vercel application to OCI. Inventory its platform dependencies,
> implement and test the required changes, prepare the OCI foundation, and show
> the deployment and cutover plans. Keep the source running until I approve cutover.

## Install in an application project

Requires Git, Python 3.11+ and your own Claude Code or Codex installation/account.
Clone the kit outside the application directory; choose an existing app directory
(or create an empty one for a new app).

```sh
git clone https://github.com/karthiksuku/oci-founder-kit.git
python3 oci-founder-kit/scripts/install.py --project /absolute/path/to/my-app --agent both
cd /absolute/path/to/my-app
```

Choose `--agent codex` or `--agent claude` to install for one tool. Windows users
can use `py -3` with Python 3.11+. The installer copies a self-contained kit into
`.oci-founder-kit/` and adds local skill entries to `.agents/skills/` and/or
`.claude/skills/`. No symlinks, global settings, network calls or cloud operations;
existing skills and files are never overwritten. `--dry-run` previews the install.
Open a fresh coding-agent session after installing if skills do not appear.

**Codex:**

```text
$oci-kit Build my app on OCI. Help me set up access and the required foundation.
```

**Claude Code:**

```text
/oci-kit Migrate this Vercel app to OCI, starting with a repository assessment.
```

Alternatively, install the complete Claude Code plugin:

```sh
claude plugin marketplace add karthiksuku/oci-founder-kit
claude plugin install oci-founder-kit@oci-founder-kit-marketplace
```

Then use `/oci-founder-kit:oci-kit`. Do not install both delivery methods in the
same scope unless you want duplicate entries. No OCI credentials are bundled.

[Start guide and troubleshooting](docs/START-HERE.md) ·
[Capabilities and validation status](docs/ROADMAP.md) ·
[Prompts and business case](docs/PLAYBOOK.md)

## What the agent can do

| Workflow | Entry skill | What is included |
| --- | --- | --- |
| Start or continue a project | [oci-kit](skills/oci-kit/SKILL.md) | Route the request, continue local work, preserve approval boundaries |
| Set up credentials and diagnose access | [oci-ready](skills/oci-ready/SKILL.md) | Credential guide, offline tool checks, opt-in read-only live diagnostics |
| Prepare compartments and security | [oci-foundation](skills/oci-foundation/SKILL.md) | Dedicated compartment/scoped policy Terraform and five-pillar design review |
| Build an application | [oci-build](skills/oci-build/SKILL.md) | App implementation workflow and container/PostgreSQL/storage reference |
| Migrate Vercel or Netlify workloads | [oci-migrate-web](skills/oci-migrate-web/SKILL.md) | Static repository scan, platform dependency report, adaptation/test/cutover workflow |
| Assess other cloud infrastructure | [oci-migrate-assess](skills/oci-migrate-assess/SKILL.md) | Terraform, CloudFormation, ARM/Bicep, Kubernetes, Compose and SDK discovery |
| Review/apply infrastructure | [oci-deploy](skills/oci-deploy/SKILL.md) | Saved-plan hash, expiry, one-use apply, IAM summary, receipts and cleanup checks |
| Evaluate OCI economics | [founder-value](skills/founder-value/SKILL.md) | Dated price lookup, cost scenarios, AI unit economics and board brief |

The agent guides account signup, MFA, local CLI authentication and public-key
registration. Those steps use your account or an authorized administrator;
private keys stay on your machine. It does not bypass identity verification or
silently grant itself administrator access. The foundation uses an existing
approved parent compartment and developer group; its guide covers initial
administrator bootstrap when those do not exist.

For migration, the agent edits and tests your actual app. Discovery is a static
assessment, not proof of runtime compatibility. Source-provider services,
production data movement, DNS cutover and decommissioning require separate review.

## Current release: 0.2.0 preview

Local tools, installation and safety contracts are tested. The reference
`fullstack-container` remains a **sandbox**: HTTPS, application sign-in, production
secret handling and remote state must be implemented and verified for your
workload before real users. No live deployment or universal Vercel migration is
claimed by this release. See the [release evidence](docs/RELEASE-0.2.0.md).

The optional [Launchpad Studio handoff](skills/oci-build/references/app-workflow.md)
uses your build brief and templates. Launchpad is not required. Its browser
learning starters and platform-dependent exports are not independent OCI apps.

## Security and operation

- The agent shows the target, resources, IAM changes, cost basis and saved plan
  before asking to apply. A plan hash alone is not evidence of human consent.
- Credential files, environment values, Terraform state and plan receipts stay
  outside Git. Use workload principals instead of distributing user API keys.
- Least privilege, private network boundaries, HTTPS, authorization, backups,
  monitoring and recovery are workload acceptance checks, not automatic claims.
- Budgets alert on soft spending limits; they are not hard cost caps. Region,
  service access and capacity must be checked for your account.
- Keep a rollback path and verify cleanup. A failed apply can leave resources;
  inspect its private receipt before planning recovery.

## Develop and validate the kit

```sh
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
claude plugin validate .
terraform fmt -check -recursive blueprints
```

The [reference app](blueprints/fullstack-container/README.md) has its own locked
Node dependencies and tests. The [curated references](docs/ECOSYSTEM.md) distinguish
source review from verified deployment. Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[UPL-1.0](LICENSE). Oracle and OCI are trademarks of Oracle and/or its affiliates.
Vercel, Netlify, AWS, Azure and Google Cloud are named factually as migration
sources. No endorsement, guaranteed credits, compatibility, pricing or compliance
certification is implied.
