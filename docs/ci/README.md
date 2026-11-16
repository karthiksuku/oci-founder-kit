# Validation and release artifacts

The kit ships three reviewed GitHub Actions templates here:
[checks.workflow.yml](checks.workflow.yml),
[validate.workflow.yml](validate.workflow.yml) and
[release.workflow.yml](release.workflow.yml). These templates are not active
workflows. This release does not claim hosted CI runs or artifact attestations.
A maintainer credential permitted to manage workflows must publish them before
GitHub can run them. Do not bypass that permission or claim provenance before a
successful trusted run and independent artifact verification.

After reviewing all three templates, copy them together into a checkout:

```sh
mkdir -p .github/workflows
cp docs/ci/checks.workflow.yml .github/workflows/checks.yml
cp docs/ci/validate.workflow.yml .github/workflows/validate.yml
cp docs/ci/release.workflow.yml .github/workflows/release.yml
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
`BUILD-METADATA.json` and `SHA256SUMS`. Only verified manifest-listed source files
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

`release.yml` runs on publication of a tagged GitHub release. It runs all checks,
then requires an exact `vMAJOR.MINOR.PATCH` tag matching the plugin version and a
commit in main's reviewed history. Configure the **release** environment with
required reviewers and protected release tags. Creating an environment name in
YAML does not create those protections for you.

Only the publication job receives `contents: write`, `attestations: write` and
`id-token: write`. It builds the assets once from the verified manifest, generates
GitHub provenance for each exact file, verifies the signer workflow/source
commit/tag using `gh attestation verify`, uploads those bytes without overwrite,
then downloads them to compare their digests. It does not create or move tags,
create another release, rebuild during upload, alter a latest-release pointer,
or delete/replace assets after a failure. A partial upload needs owner review.
Forked repositories do not publish through the supplied release entry point.

To verify a downloaded archive, select the exact tag and commit, check
`SHA256SUMS`, then run a command with the real version and commit substituted:

```sh
gh attestation verify oci-founder-kit-VERSION.tar.gz \
  --repo karthiksuku/oci-founder-kit \
  --signer-workflow karthiksuku/oci-founder-kit/.github/workflows/release.yml \
  --source-ref refs/tags/vVERSION --source-digest COMMIT_SHA \
  --deny-self-hosted-runners
```

Do not run the literal placeholders. Extract into a fresh directory only after
verification, then run its `scripts/release_manifest.py check` before installing.
A local archive or an uploaded checksum file must never be described as attested
unless this verification succeeds for that artifact and expected source.

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

Actions execute from their publishers; their source is not copied into this kit.
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
