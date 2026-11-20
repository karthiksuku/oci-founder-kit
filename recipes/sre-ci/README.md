# Test and scan a founder application

Start with `oci-kit sre plan --environment rehearsal` in the installed project. These are opt-in application recipes. Review them with the application owner before copying; they are not active workflows or evidence of a hosted run. The production verifier runs outside the application checkout. A hash, a scanner exit code, or a PR artifact cannot sign a promotion.

## Pull requests

Copy [the PR recipe](founder-pr.workflow.yml) to the founder app's `.github/workflows/`, retaining the ordinary `pull_request` event, minimal permission, hosted disposable runner, and no persisted checkout credentials. Set `FOUNDER_APP_DIR` to the Node application directory. Connect the actual build, lint/types, unit, API, browser and accessibility commands for the selected app: the example expects `test`, `test:browser` and `test:a11y` npm scripts and installs Chromium via the application lockfile’s own Playwright CLI. If that executable is missing the job fails; no unpinned CLI is fetched. Provide route-specific keyboard, accessible-name and error-state assertions in addition to automated accessibility rules. Set up a disposable database and test identities where required. An absent browser/accessibility suite needs implementation, not a dummy command. Lint/types/build scripts are discovered opportunistically here; protected CI must verify their required coverage separately. The reference Next.js project runs its parity checks with npm test after the build; both reference apps provide browser and accessibility scripts. For an existing founder app adapt those scripts to its actual critical journey.

Lockfile vulnerability scanning, secret scanning and Dockerfile/Terraform configuration checks run in a separate job from application commands. No raw findings or package inventories are uploaded. Add the application's reviewed static code/security analysis to the protected hardening control: a dependency scan is not application code analysis. Require these jobs through the founder repository's branch protections. See [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).

## Candidate image

Linux AMD64, Python 3.11+, Git and a separately installed [Trivy 0.76.2](https://github.com/aquasecurity/trivy/releases/tag/v0.76.2) are required. Pin/review the version and Linux binary rather than downloading a mutable action. The archive and binary SHA-256 are in the PR recipe; the CLI verifies the binary on each run. Trivy is a separate [Apache-2.0 tool](https://github.com/aquasecurity/trivy/blob/v0.76.2/LICENSE); no scanner, database, or account configuration is distributed with this kit.

1. Use a protected verifier with a reviewed kit copy **outside** the candidate checkout. Use a dedicated trusted scanner cache. Update the database using the verified binary: `trivy image --config '' --disable-telemetry --cache-dir /private/trivy-cache --download-db-only`. This step contacts a public vulnerability feed; it does not send the project or scan results. Never share writable caches with PR jobs.
2. Commit the candidate. Use the [packaging recipe](../README.md) once and retain its private single-platform directory layout and manifest digest. Scanning takes the tracked Git tree, a verified private snapshot of the exact image bytes, and no OCI credentials. Preinstalled package bytes and the tool's built-in rules are used offline. The image must contain at least one version-matched direct production dependency outside package-manager tooling. Bundled dependencies need the production lock scan even when their metadata is absent from the image; a tooling-only inventory is unknown. The initial profile requires Node/npm, a supported Linux OS with package inventory, a Dockerfile, and Terraform in the reviewed source tree. A scratch image, separate unbound infrastructure repository, unsupported package manager, or indeterminate coverage remains unknown.
3. Run the command below. `--output` must name a **new** directory outside the app under a private parent. The raw files can contain matched secret material, software inventories, and identifiers. Limit access and retention; **never publish them, send them to a model or attach them to an issue**. The helper never uploads an artifact.

```sh
python3 -I /trusted/oci-founder-kit/scripts/sre_scan.py scan \
  --project /work/clean-app --layout /private/tested-image-layout \
  --image-digest 'sha256:<tested-manifest-hex>' --trivy /trusted/trivy \
  --cache-dir /private/trivy-cache --output /private/new-local-result
```

For a founder-owned Next.js launch add `--app-directory .` to that command, or pass the reviewed
project-relative application directory, such as `--app-directory apps/web`. The scanner binds its
relative npm lockfile path and committed contents to the source revision, selects that exact Trivy
npm result and matches its direct Next.js version to the runtime image inventory. The resulting v3
summary is mandatory for the `new-app-nextjs` profile. A workspace lockfile outside the app, an
unavailable package inventory or an unmatched version leaves coverage unknown. Repo-wide findings
are still included. The original unscoped scan remains available for earlier profiles.

The private output includes `source.json` (production lockfile), `including-development.json`, `runtime.json`, the exact image's SPDX inventory and a projected `summary.json`. Only the summary belongs in the protected verifier's `security_scan` observation. Record lower-severity runtime issues and development-only findings in private remediation tracking with owner and due date. High/Critical vulnerabilities in the final image or the production lockfile, secrets, an end-of-life OS or failed hardening rules block; unsupported inputs, UNKNOWN severity, or a scan/database older than 24 hours are unknown. Both block promotion. Unchanged PR history, fixture allowances, ignore files or a previous image verdict do not transfer to the new image. [Trivy vulnerability coverage](https://trivy.dev/latest/docs/scanner/vulnerability/)

## Post-publication OCI registry scan

Registry scanning is a separate cloud operation. First reuse an approved configured target; otherwise, have an authorized administrator inspect [the standalone Terraform recipe](registry-scan/main.tf) pinned to the kit's OCI provider. It creates a scan recipe and a target for **one named repository in one non-root compartment**, scanning one existing image initially. It creates no IAM. Verify that there is no conflicting existing target, that repository, region, effective service permissions and cost estimate are correct, and that protected state is already available. Prepare a separate saved plan through the existing approved deployment process. Registry creation or image-upload approval does not authorize the scan resources, role changes, or eventual cleanup. This preview recipe is not a registered `foundation` component.

[OCI registry scanning](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryscanningimagesforvulnerabilities.htm) runs asynchronously. After separate digest publication, perform the read-only verification with a named environment:

```sh
python3 -I /trusted/oci-founder-kit/scripts/sre_scan.py registry \
  --project /work/clean-app --environment rehearsal --image-id '<private-image-id>' \
  --output /private/new-registry-result
```

The reader checks the selected environment's region/profile, private registry, compartment, repository and actual image digest. It compares the latest matching VSS scan summary and result, including scan timestamps. A specific latest result can alternatively be selected with `--scan-id`. The [VSS result contract](https://docs.oracle.com/en-us/iaas/Content/scanning/using/get_image_scan.htm) describes an image name, not guaranteed immutable digest metadata. A tag-only response, missing immutable identity, stale, denied or partial results remain **unknown**; do not substitute a tag or state that OCI passed. Record `summary.json` as `oci_registry_scan` in the protected verifier. Positive service behavior needs a real sandbox run; a synthetic result is not a service attestation.

## Monitor the released digest

Install [the daily rescan](deployed-rescan.workflow.yml) only on a dedicated, protected runner with validated tools, trusted outside-project kit, isolated cache and private read-only OCI profile. Populate the runner's `FOUNDER_*` environment **from the currently accepted deployment receipt**. Set `FOUNDER_RELEASE_PROFILE` to the signed profile. For `new-app-nextjs` also set
`FOUNDER_APP_DIR` from the reviewed application selection and `FOUNDER_SELECTED_LOCK_SHA256`
from the accepted signed binding. Keep the clean checkout, private layout and scan evidence outside the workflow checkout. The additional `--require-deployed` performs a fresh, receipt-bound runtime read: the selected, scanned, registry and actually running digests must all match. A missing or replaced revision fails the scheduled job. The workflow does not stop or patch an app and does not use a signing or deployment credential.

Route failures **and missed schedules** to the named responders via their approved notification integration. Confirm delivery using a rehearsal failure and have the responder acknowledge it; a red job or an unconfirmed subscription is not evidence of notification delivery. Review resource retention and costs with the owner. Schedule installation and hosted runner behavior remain unverified until tested with the founder's account.
