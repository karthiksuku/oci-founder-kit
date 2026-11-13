# Curated source references

Reviewed 13 November 2026. These are design references, not dependencies installed
by the kit. Source-reviewed means the public documentation was inspected; none
of these projects was deployed as part of this release.

| Reference | Useful pattern | Evidence/limitations |
| --- | --- | --- |
| [OCI Starter](https://github.com/oracle-devrel/oci-starter) | Generated project, Cloud Shell setup and app URL | Source reviewed; evaluate a pinned configuration before adoption |
| [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) | Complete app, database, sign-in, local services and tests | Source reviewed; an OCI deployment requires separate adaptation |
| [Open SaaS](https://github.com/wasp-lang/open-saas) | App essentials, email, payments, jobs and agent guidance | Source reviewed; hosted deployment/storage choices need an OCI review |
| [MuShop](https://github.com/oracle-quickstart/oci-cloudnative) | Reference app with simple and Kubernetes deployment paths | Source reviewed; verify current costs and resource eligibility |
| [OCI AI Blueprints](https://github.com/oracle-quickstart/oci-ai-blueprints) | Advanced AI workloads and observability | Source reviewed; OKE/GPU infrastructure is not the default starter route |
| [Oracle Skills](https://github.com/oracle/skills) | Maintained Oracle procedures | Check installation and compatibility before delegating a procedure |

Launchpad Studio is an optional source of user-provided recipes and build briefs.
Its SDK-dependent exports require a compatible backend or an implemented
replacement. See the [handoff](../skills/oci-build/references/app-workflow.md).

Retain original licenses and attribution when reusing code. Listed capabilities
are maintainer-documented behavior, not independent operational verification.

See [lessons from AWS, Azure and Google Cloud starters](STARTER-PATTERNS.md) for
pinned public sources, license checks and the local-preview/blueprint patterns
adapted into this kit.

## Public skills worth composing

The following exact public sources were inspected on 13 November 2026. These are
optional references, not silently installed dependencies or permission to run
their mutating commands. Inspect the selected revision and preserve the kit's
approval, credential and data boundaries when composing a workflow.

| Public source | Useful fit | Reuse boundary |
|---|---|---|
| [Functions troubleshooting](https://github.com/oracle/skills/blob/0779f030fdee393ee418a3a76f6a4b09bf1408db/oci/functions/oci-functions-troubleshoot/SKILL.md) | Read-only classification of setup, deployment, invocation and observability failures | UPL-1.0; follow its linked references, redact logs and do not treat diagnosis as repair authorization |
| [Functions deployment](https://github.com/oracle/skills/blob/0779f030fdee393ee418a3a76f6a4b09bf1408db/oci/functions/oci-functions-deploy/SKILL.md) | Local Java/Python/Node prerequisites and staged function delivery | UPL-1.0; its documented local macOS/Linux scope does not establish Windows or Cloud Shell support. Keep tokens out of chat/arguments and review each deployment operation |
| [OKE cluster generation](https://github.com/oracle/skills/blob/0779f030fdee393ee418a3a76f6a4b09bf1408db/oci/oke/skills/oke-cluster-generator/SKILL.md) | Kubernetes design when the workload needs it | UPL-1.0; review generated infrastructure, IAM and cost. A generated stack is not verified production infrastructure |
| [OCI Agent Shipyard](https://github.com/luigisaetta/codex-4-oci-enterprise-ai-deployment/tree/f07d32d9f4fcf312fe4f0142e387114287ecd588) | Manifest-driven build, publish, deploy and verification of hosted AI agents | MIT; its target is OCI Enterprise AI Hosted Applications. Review the selected scripts and approvals before use; no runtime validation is claimed here |

Public license sources: [Oracle Skills UPL](https://github.com/oracle/skills/blob/0779f030fdee393ee418a3a76f6a4b09bf1408db/LICENSE.txt)
and [Agent Shipyard MIT](https://github.com/luigisaetta/codex-4-oci-enterprise-ai-deployment/blob/f07d32d9f4fcf312fe4f0142e387114287ecd588/LICENSE).
This kit links these projects; it does not vendor their implementations.
