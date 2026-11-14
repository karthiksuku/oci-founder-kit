# What we learned from other cloud starters

Reviewed 13 November 2026. AWS, Azure and Google Cloud have useful public
developer tools and application starters. This kit adapts selected workflow
ideas for OCI, with original implementation. These projects are references,
not dependencies installed by the kit, and were not deployed in this review.

Follow-up reviewed 14 November 2026: the 0.4.0 preview adds editable project
creation, task-specific start/resume prompts and a runnable stateless Next.js
packaging rehearsal. These extend the existing local preview and metadata
contract rather than introducing another framework or automatic deployment.

| Public reference | Pattern worth adopting | Where it fits in this kit |
| --- | --- | --- |
| [AWS SAM CLI](https://github.com/aws/aws-sam-cli/tree/25d628c6073b6baa5e5558ba746038e55340da72) and [app templates](https://github.com/aws/aws-sam-cli-app-templates/tree/db18bc9832f83ea519065b7e7ae24840d04c5a99) | A small runnable application, a local feedback loop, then deployment | [Local Taskboard preview](../blueprints/fullstack-container/LOCAL.md): start the app and PostgreSQL before configuring OCI |
| [Azure Developer CLI](https://github.com/Azure/azure-dev/tree/9194e6c86a89c92ecdc87c6d624def469fa2c8bc) | Explicit service paths, requirements and lifecycle stages | [Blueprint metadata](../blueprints/fullstack-container/blueprint.json) and the offline checker describe the app, commands and prerequisites for an agent |
| [Google Cloud three-tier blueprint](https://github.com/GoogleCloudPlatform/terraform-google-three-tier-web-app/tree/69885ccd8aaa9b2e9ab2307fbe6b7242aa1a2b17) | Documented infrastructure inputs, outputs and examples | The same blueprint contract identifies OCI infrastructure, operating modes, outputs and acceptance work |
| [AWS CDK agent guide](https://github.com/aws/aws-cdk/blob/beb206171b52bfeca5c5fdee78ba965ee5b33c25/AGENTS.md) | Commands with explicit working directories and focused verification | The contract and [maintainer guide](MAINTAINING.md) make local preview, tests and infrastructure review discoverable |

## Try the resulting workflow

From the kit's repository root, with Python 3.11+ and Docker Compose available:

```sh
python3 scripts/blueprint.py inspect fullstack-container
python3 scripts/blueprint.py check fullstack-container
python3 blueprints/fullstack-container/local_preview.py start
```

The checker reads the public contract and referenced files. It does not execute
commands, inspect credentials, query OCI or certify cloud readiness. The local
preview runs the real app and database; it is an unauthenticated loopback sandbox.
Uploads need OCI Object Storage and remain unavailable in this local mode.

Use `local_preview.py status` to inspect the preview and `local_preview.py stop`
to stop its containers. Stopping preserves the local database volume. Follow
the [local guide](../blueprints/fullstack-container/LOCAL.md) for requirements,
persistence and troubleshooting.

When the app is useful locally, continue through [access and foundation setup](START-HERE.md),
[image publication](../skills/oci-deploy/references/image-publication.md), a
reviewed infrastructure plan and [runtime acceptance](PROGRESS.md). Cloud
resources and IAM remain separate, explicit decisions.

## Boundaries and next improvements

The follow-up draws on these public patterns:

- [Azure Developer CLI templates](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-templates)
  keep application source, infrastructure and lifecycle instructions together.
  The kit's creator exports its own existing app and installs project-local
  agent skills; users can edit the application independently of the kit snapshot.
- [Google Agents CLI setup](https://google.github.io/agents-cli/setup.md)
  provides a short agent handoff and recognizes already-loaded skills. The kit's
  resume path inspects existing installation and project evidence before trying
  to install again. It retains project-local defaults and separate cloud approval.
- [Amplify's migration feature matrix](https://docs.amplify.aws/react/start/migrate-to-gen2/feature-matrix/)
  distinguishes supported features from work that still needs adaptation.
  The runnable Next.js example similarly names what its local HTTP checks cover
  and which provider, data and cloud behaviors remain unverified.
- [Awesome AZD's catalog schema](https://github.com/Azure/awesome-azd/blob/57c2a5146d18c2cc9ab0df56823ffc37c86a3304/docs/templates-schema.md)
  illustrates validated discovery metadata. A larger generated gallery remains
  future work; this release adds only the explicit included starter path.

The inspected [Amplify backend](https://github.com/aws-amplify/amplify-backend/tree/4d3d41c9470bf0c4256b99be4c4e0d6c3f9781e6)
and [Google Agents CLI](https://github.com/google/agents-cli/tree/6eedbdc2f44c388cbfc5f305eb83b9924cfefebb)
use Apache-2.0; [Azure Developer CLI](https://github.com/Azure/azure-dev/tree/03459efde709d92907b3b788fb20b3ecbbd122cd)
and [Awesome AZD](https://github.com/Azure/awesome-azd/tree/57c2a5146d18c2cc9ab0df56823ffc37c86a3304)
use MIT. These repositories were unarchived at the dated follow-up. Google's
older [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)
was archived and directs new users to Agents CLI. These are source/documentation
references, not independently deployed tools or copied implementation.

Service behavior, scaling, managed domains and prices do not transfer between
clouds. OCI claims need OCI-specific documentation and validation. The kit keeps
exact-plan approvals and scoped cleanup; it does not adopt automatic cloud
deployment, project-wide deletion or unrestricted administrator defaults.

Potential follow-ons are a production acceptance runner, more tested app
blueprints, and workload-specific data/cutover rehearsals beyond the small
stateless packaging example. They are not included capabilities until implemented
and verified. Named cloud environment management
and arbitrary manifest hooks are also outside the current metadata checker.

At review time, AWS SAM, CDK, Azure Developer CLI and Google's three-tier
Terraform repository were unarchived with recent source activity. AWS
[Copilot](https://github.com/aws/copilot-cli/blob/a0dbe68908e55c4292e5838bd6cfbaea38364879/README.md)
had reached end of support and was archived. The older
[Azure todo template](https://github.com/Azure-Samples/todo-nodejs-mongo/tree/16695b06631a166eb5dc90ea2f0d52b917578013)
was also archived. Neither is recommended here as a maintained dependency.

## License provenance

The pinned AWS [SAM](https://github.com/aws/aws-sam-cli/blob/25d628c6073b6baa5e5558ba746038e55340da72/LICENSE),
[templates](https://github.com/aws/aws-sam-cli-app-templates/blob/db18bc9832f83ea519065b7e7ae24840d04c5a99/LICENSE)
and [CDK](https://github.com/aws/aws-cdk/blob/beb206171b52bfeca5c5fdee78ba965ee5b33c25/LICENSE)
sources use Apache-2.0. [Azure Developer CLI](https://github.com/Azure/azure-dev/blob/9194e6c86a89c92ecdc87c6d624def469fa2c8bc/LICENSE)
uses MIT; [Google's blueprint](https://github.com/GoogleCloudPlatform/terraform-google-three-tier-web-app/blob/69885ccd8aaa9b2e9ab2307fbe6b7242aa1a2b17/LICENSE)
uses Apache-2.0. This comparison borrows patterns without copying source code,
branding or internal material. Preserve the applicable license and notices if
you later copy code from those projects.
