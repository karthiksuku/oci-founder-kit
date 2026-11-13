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
