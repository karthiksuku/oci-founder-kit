# Validation and release artifacts

The kit ships reviewed GitHub Actions templates here:
[checks.workflow.yml](checks.workflow.yml),
[validate.workflow.yml](validate.workflow.yml) and
[release.workflow.yml](release.workflow.yml), plus
[dependency-review.workflow.yml](dependency-review.workflow.yml). These templates are not active
workflows. This release does not claim hosted CI runs or artifact attestations.
A maintainer credential permitted to manage workflows must publish them before
GitHub can run them. Do not bypass that permission or claim provenance before a
successful trusted run and independent artifact verification.

After reviewing the templates, copy them together into a checkout:

```sh
mkdir -p .github/workflows
cp docs/ci/checks.workflow.yml .github/workflows/checks.yml
cp docs/ci/validate.workflow.yml .github/workflows/validate.yml
cp docs/ci/release.workflow.yml .github/workflows/release.yml
cp docs/ci/dependency-review.workflow.yml .github/workflows/dependency-review.yml
cp docs/ci/dependabot.yml .github/dependabot.yml
```

The commands above replace files at those exact destinations; compare existing
workflow files before copying. Publish through the repository's normal reviewed
change process using the authorized workflow credential. Configure required
checks, release environment review and protected release tags separately.

## Credential-free validation

`validate.yml` calls the same checks used by the release workflow. Pull requests
and main pushes use hosted runners, read-only repository permission and checkout
with persisted credentials disabled. No OCI credentials, cloud deployment,
registry uploads, traffic changes or long-lived agent credentials are used.
There is no `pull_request_target`, privileged `workflow_run`, secret inheritance
or reusable artifact cache crossing the validation/publication boundary.

The checks cover:

- Manifest integrity, source privacy checks and Python tests, including local
  synthetic HTTPS checks, built Next.js reference/standalone parity, and actual
  browser migration workflows using the pinned Chromium test dependency.
- Real OCI SDK API-key and SecurityToken signer construction with synthetic
  credentials and the SDK's actual HTTP transport blocked. The pinned
  [test requirements](requirements-sdk.txt) are installed explicitly; failed
  SDK/cryptography imports fail the job before optional tests could skip.
- Taskboard's tests against an ephemeral loopback PostgreSQL service, plus an
  ordinary container's filtering, redirect, access denial and streaming behavior.
- Terraform formatting, pinned-provider validation and mock-provider tests.
- Site build, unit tests and Chromium/accessibility tests.
- Linux/Python 3.11 and macOS/Python 3.13 artifact installation, attachment and
  upgrade from the reviewed v0.5.0 commit
  `91af893a6ffd631ea98fd1c0727371083a5e6025`, preserving existing app source.

The runtime tests are local evidence. They do not prove OCI capacity, actual
cloud sign-in, cross-user authorization in a deployed app, recovery, or agent
success. These remain separately recorded acceptance exercises. The platform
matrix is a verification target until its hosted jobs have actually passed;
Windows users use WSL2, which needs its own recorded runtime evidence.

The old [template entry point](validate.workflow.yml) remains for existing links.
It requires the companion reusable `checks.yml`; copying that entry point alone
is insufficient. Configure required checks in the repository's settings after
publishing and observing the first successful run.

## Deterministic release files

From a verified checkout, choose a new directory outside the checkout:

```sh
python3 scripts/release_archive.py --output-dir /tmp/founder-kit-release
```

This creates the versioned `.tar.gz`, `release-manifest.json`,
`BUILD-METADATA.json`, `SBOM.spdx.json` and `SHA256SUMS`. Only verified manifest-listed source files
enter the archive. Unlisted local files, credentials, plans and state are never
discovered for packaging. Changed listed bytes, symlinks and existing output
paths are refused. A failed write leaves partial assets for review.

Archive paths, ownership, permissions and timestamps are normalized. Rebuilding
the same verified source with the same Python/gzip implementation yields the
same bytes even if source locations or modification times differ. Checksums
establish byte identity; they do not authenticate the publisher or establish
that every listed source file is safe. Review and privacy scanning remain
necessary before regenerating a manifest.

The public installation archive intentionally follows the installer allowlist.
It is not the entire Git repository and does not contain the site build or
GitHub workflow execution configuration. Source snapshots on GitHub remain
separate artifacts with different bytes and different verification requirements.

## Trusted release provenance

`release.yml` runs on a push of an already reviewed version tag. All tests run
before building the archive. The version must match the plugin metadata, and
the source commit must be in main's reviewed history. Configure protected release
tags and the **release** environment with required reviewers before activation;
naming an environment in YAML does not configure these protections.

The sequence is **reviewed tag → tests → build → empty draft → attest → attach →
download and authenticate → publish**. The publication job alone receives
`contents: write`, `attestations: write` and `id-token: write`. It rechecks remote
tag identity, refuses existing/partly populated releases, never overwrites an
asset, and verifies every downloaded asset against the expected source commit,
tag, repository, signer workflow and its local SHA-256. It publishes a preview
without changing the latest-release pointer, then verifies public metadata and
tag identity again. A failed run leaves its draft and assets for owner review;
it never deletes or replaces evidence to make a rerun pass.

[Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
lock assets and tags when the draft is published. Enable that setting only after
the complete draft sequence passes in the authorized repository. Existing
releases do not retroactively receive these guarantees. The template does not
change repository settings or claim a SLSA level.

Use a trusted checkout's consumer verifier with independently selected source
identity and archive digest. Do not execute a verifier extracted from an
unverified download. Replace all placeholders before running:

```sh
python3 scripts/verify_release.py --assets /path/to/downloads \
  --repo karthiksuku/oci-founder-kit --workflow .github/workflows/release.yml \
  --tag vVERSION --commit COMMIT_SHA --archive-sha256 ARCHIVE_SHA256
```

The verifier requires exactly the versioned archive, manifest, build metadata,
SPDX inventory and checksum file. It checks byte identity and authenticated
provenance for every asset using `gh attestation verify`, with the repository,
workflow, source ref, source commit and signer commit bound explicitly. Missing
attestations fail; there is no checksum-only fallback. The CLI's normal trusted
root and network configuration are used. GitHub credentials remain under normal
CLI management; do not put tokens in arguments or release files.

Extract only after verification, into a fresh directory, then run the extracted
`scripts/release_manifest.py check` before installation. GitHub's automatically
generated source tarballs have different bytes and are not these uploaded
artifacts. Where immutable release attestations are available, GitHub's
[release integrity check](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity)
provides an additional release-level check.

## Dependency inventory and review

`SBOM.spdx.json` is deterministic SPDX 2.3 generated from the exact archived
file bytes. Every file has a SHA-256 entry; the archive package carries the
archive digest. npm lock declarations, directly pinned Python requirements and
Terraform lock declarations are identified separately from bundled files.
Unresolved Python transitives, unlocked dependencies, Docker base layers and OS
packages are explicitly outside this source inventory. The fixed inventory
creation timestamp supports reproducibility and is not a claimed build date.
The release workflow creates both build provenance for the inventory and an
SBOM attestation binding the inventory to the actual archive.

The credential-free image job builds the public Taskboard and ordinary web
reference images, selects each exact local image ID, then scans it with pinned
Syft. These separate SPDX inventories include discoverable installed language
and OS packages and are retained as CI artifacts for 14 days. An image scan is
neither an OCIR publication nor a deployed-workload inventory. Catalogers can miss
packages; a source SBOM must never be substituted for this runtime scan. The kit
does not scan or upload a founder's application inventory automatically.

Dependency review checks PR diffs for known high/critical vulnerabilities in
runtime, development and unknown scopes. It needs GitHub dependency graph/review
availability. It does not silently pass missing service access and does not
post PR comments. License acceptance remains a separate source review; the
vulnerability check does not establish license clearance or comprehensive
vulnerability coverage.

The [Dependabot template](dependabot.yml) proposes weekly action, npm, CI Python,
Terraform and Docker updates. Review each PR, source, license, changed behavior
and tests; there is no automatic merge. Pinning direct SDK requirements does
not lock Python transitive resolution. New recipes with additional manifests
need explicit update coverage rather than an assumed repository-wide guarantee.

## Platform and agent evidence

| Combination | Recorded evidence | Remaining gate |
| --- | --- | --- |
| Linux, Python 3.12 | Candidate clean installation and v0.5/v0.6 upgrade checks; exact completed results in the [preview record](https://github.com/karthiksuku/oci-founder-kit/releases/tag/v0.7.0) | Preserve application and saved-record bytes on each frozen candidate |
| Linux, Python 3.11 | Hosted validation target in the template | Successful hosted run required |
| macOS, Python 3.13 | Hosted installation/upgrade target in the template | Successful hosted run required |
| Windows / WSL2 | No runtime acceptance recorded | Dedicated installation, permissions and agent trials required |
| Claude Code and Codex, restricted local harness | Three-trial core matrices, individual attempts and separate manual outcomes are recorded in the [preview record](https://github.com/karthiksuku/oci-founder-kit/releases/tag/v0.7.0) | A machine pass is not founder-success acceptance; review reporting defects and scope limits |
| Ordinary Claude Code / Codex sessions on OCI | No complete new-app or hosting-first acceptance recorded | Approved sandbox, HTTPS/sign-in/isolation/persistence/restore/rollback |

Installed CLI versions are not a tested support claim. New evaluation results
record exact kit, CLI, requested/observed model, platform and grader identities.
Unknown model identity remains unknown. [Evaluation instructions](../AGENT-EVALUATIONS.md)
keep restricted harness, ordinary agent and live-cloud results separate.

## Reviewed public dependencies

Official GitHub tag APIs and action metadata were checked on 2026-11-16. Actions
are pinned to these immutable commits; updates require another source review.
The hosted runner images, Python patch distributions, npm dependency downloads
and container base tags remain external inputs. The archive's source-only
reproducibility claim does not claim those test environments are reproducible.

| Action | Reviewed version | Commit |
| --- | --- | --- |
| [Checkout](https://github.com/actions/checkout/tree/v7.0.1) | 7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| [Setup Python](https://github.com/actions/setup-python/tree/v7.1.0) | 7.1.0 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| [Setup Node](https://github.com/actions/setup-node/tree/v7.1.0) | 7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| [Setup Terraform](https://github.com/hashicorp/setup-terraform/tree/v4.0.1) | 4.0.1 | `dfe3c3f87815947d99a8997f908cb6525fc44e9e` |
| [Build provenance](https://github.com/actions/attest-build-provenance/tree/v4.2.2) | 4.2.2 | `4d101475d8b20a2381f78447822ac1eab6504dd8` |
| [Attest / SBOM](https://github.com/actions/attest/tree/v4.1.0) | 4.1.0 | `59d89421af93a897026c735860bf21b6eb4f7b26` |
| [Dependency review](https://github.com/actions/dependency-review-action/tree/v5.0.0) | 5.0.0 | `a1d282b36b6f3519aa1f3fc636f609c47dddb294` |
| [Image SBOM](https://github.com/anchore/sbom-action/tree/v0.24.3) | 0.24.3 | `66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c` |

The image cataloger is [Syft 1.57.1](https://github.com/anchore/syft/releases/tag/v1.57.1);
its version is explicitly pinned in addition to the SBOM action. Actions execute from their publishers; their source is not copied into this kit.
The signer-test pins are [OCI SDK 2.191.0](https://pypi.org/project/oci/2.191.0/),
[cryptography 50.0.2](https://pypi.org/project/cryptography/50.0.2/) and
[pyOpenSSL 26.4.0](https://pypi.org/project/pyOpenSSL/26.4.0/), checked against
public package metadata on the same date. They are CI-only dependencies. Their
transitive dependencies still resolve from the package index; this is not a
fully locked test environment. Local signer verification used Linux/Python 3.12;
the hosted Python 3.11 job remains a separate validation target.

See [GitHub artifact attestation documentation](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
for the distinction between a signed provenance statement and application or
security acceptance. No cloud deployment or publication result is implied by
this documentation.
