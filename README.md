# OCI Founder Kit

> Build, migrate and justify applications on Oracle Cloud Infrastructure
> (OCI) with the coding agent you already use.

The OCI Founder Kit is a set of agent skills and tested tools for Claude Code
(and Codex and Cursor). It helps three kinds of people get a real result on
OCI:

| Track | For | What it does |
|---|---|---|
| **Decide** | Founders, CEOs, boards | Is OCI worth it, by how much, and how to make the case: gross margin, payback with and without credits, the credit cliff, AI unit cost, Oracle go-to-market, a board brief |
| **Build** | Developers and technical founders | A full-stack application on OCI from a tested golden path: frontend, API, database, storage, auth, observability, deployed only after you approve the exact plan |
| **Migrate** | Teams on AWS, Azure or Google Cloud | Automated discovery of what runs today, a service-by-service map that names what does not match, data migration runbooks, cutover and rollback |

Everything that changes a cloud account goes through one gate: the agent shows
the exact Terraform plan, target compartment, region and estimated cost, and
applies only that plan after you approve it. Every deploy writes a receipt,
and every receipt can be torn down.

It builds on Oracle's official [`oracle/skills`](https://github.com/oracle/skills)
for OKE, Functions and database procedures instead of copying them.

## Status

| Track | State |
|---|---|
| Decide | **Available.** Five skills, a tested value model and a live price-list lookup. See [the business value](docs/BUSINESS-VALUE.md) |
| Migrate | **Assessment available.** Discovery for AWS, Azure and Google Cloud and a tested service map. Next: migration plan, data runbooks, cutover |
| Build | In progress: account readiness, the approval-gated deploy tool, the first full-stack golden path |

Start with [`oci-kit`](skills/oci-kit/SKILL.md): it routes a request to the
right track and carries the safety contract every skill follows.

**Name the skill when you ask.** In testing, a plain request ("we're on AWS,
what would it take to move to OCI?") was sometimes answered from the model's
general knowledge instead of the kit, especially on machines with many other
skills installed, and that answer missed facts the kit checks (for example
Cloudflare@OCI for CDN). Invoking the skill by name gave the evidence-based
result every time:

```text
/oci-founder-kit:oci-migrate-assess We run this app on AWS. What would it take to move it to OCI, and what first?
```

The [roadmap](docs/ROADMAP.md) lists each piece and the evidence it needs
before it is called done.

## Install

**Claude Code plugin** (all skills), from a checkout:

```bash
claude plugin marketplace add /absolute/path/to/oci-founder-kit
claude plugin install oci-founder-kit@oci-founder-kit-marketplace
```

**One skill into one project** with the Agent Skills CLI:

```bash
cd /absolute/path/to/your-project
npx --yes skills@1.7.0 add /absolute/path/to/oci-founder-kit \
  --skill founder-value -a claude-code --copy -y
```

Use `codex` or `cursor` instead of `claude-code`.

## Decide track: available now

| Skill | Founder question |
|---|---|
| [`founder-value`](skills/founder-value/SKILL.md) | Is OCI worth it for us? Verdict, deciding numbers, value case |
| [`founder-value-economics`](skills/founder-value-economics/SKILL.md) | Cost per customer, payback, credits and the cliff |
| [`founder-value-ai`](skills/founder-value-ai/SKILL.md) | What does one AI action cost, and can we protect margin? |
| [`founder-value-gtm`](skills/founder-value-gtm/SKILL.md) | Startup Growth Engine fit, Marketplace and enterprise readiness |
| [`founder-value-brief`](skills/founder-value-brief/SKILL.md) | A one-page board or investor brief |

Worked example: [a seed-stage AI SaaS company](examples/seed-ai-saas/README.md).
Prompts to paste: [founder playbook](docs/PLAYBOOK.md).

## Migrate track: assessment available

[`oci-migrate-assess`](skills/oci-migrate-assess/SKILL.md) scans a
repository read-only and maps every cloud resource to OCI:

- **Reads** Terraform resources and registry modules, CloudFormation and SAM,
  ARM and Bicep, Deployment Manager, Kubernetes manifests, Compose files, and
  SDK dependencies in npm, PyPI, Go, Maven/Gradle and NuGet projects.
- **Maps** each finding through a [service map](skills/oci-migrate-assess/assets/service-map.json)
  of 59 OCI target services and about 330 rules, with the fit (equivalent,
  partial, gap), what differs, how to migrate and a documentation link.
- **Proves the map** in tests: every OCI Terraform type is checked against the
  OCI provider schema (oracle/oci 9.10.0), every source type against the
  current AWS, azurerm and Google providers and the CloudFormation
  specification, and every documentation link was checked live on 2026-10-21.
- **Reports** partial fits and gaps first, cloud SDK calls that need code
  changes, self-hosted services that could become managed, Kubernetes
  settings tied to the old cloud, anything it did not recognise, and an S to
  XL effort signal.

```bash
python3 skills/oci-migrate-assess/scripts/iac_scan.py /path/to/repo --out migration-scan.md
```

Example: [scan of an AWS app](examples/migrate-aws-taskboard/migration-scan.md)
(ECS, RDS PostgreSQL, S3, ElastiCache, SQS, Cognito, CloudFront).

## Principles

- **Approve the exact plan.** No cloud change without a reviewed plan, a named
  target and explicit approval; apply refuses a plan that differs from the
  one approved.
- **Receipts and teardown.** Every deploy records what it created; teardown
  removes exactly that and checks nothing is left running.
- **Evidence over memory.** Prices from Oracle's public price list with
  dates; service facts linked to current Oracle documentation; unknowns marked
  as unknown.
- **Name the mismatches.** A migration map that hides non-equivalent services
  is worse than none.
- **Draft, never act on someone's behalf.** No sign-ups, applications or
  messages sent by the agent.

## Validate

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
claude plugin validate .
```

## Disclaimer and license

An independent project by Karthik Sukumar. It is not an Oracle product and is
not sponsored, endorsed or supported by Oracle. Oracle, OCI and Java are
trademarks of Oracle and/or its affiliates; AWS, Azure and Google Cloud are
trademarks of their owners and are named only to describe migration sources.
This is not a quote, and not tax, accounting, legal or investment advice.

Licensed under the [Universal Permissive License 1.0](LICENSE).
