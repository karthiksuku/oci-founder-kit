# 0.4.1 preview — safer local distribution

This patch strengthens private-file exclusions used by the project installer,
editable starter creator, generated Git ignores and optional public-content hook.
It also makes exported-app guidance platform-neutral.

## What changed

Known credential/configuration paths such as `.npmrc`, `.pypirc`,
`.git-credentials`, `.netrc`, `.docker/`, `.aws/`, `.ssh/`, `.azure/` and `.kube/`
are excluded. Terraform variable/backend/state backup variants and diagnostic
logs are excluded too. The public hook rejects these paths even if they were
force-added to Git. Example templates remain available and still receive the
hook's content checks.

The issue was reproduced with synthetic marker files in a private test copy.
This was a packaging weakness, not evidence that those files were present in
the public repository.

## Verification

Verified on Linux on **15 November 2026**:

- All **517 repository tests passed**, including the opt-in real Next.js
  packaging rehearsal. Repository and Claude plugin validation passed.
- The **70 focused installer, creator and hook tests** are included in that
  suite. Actual install/create regressions exclude 46 named private paths and
  preserve 11 example templates. Git's own ignore matcher verifies both the
  repository and generated-project rules, including mixed-case filenames.
- Independent review caught an intermediate exception that could admit a
  directory named `.env.example`. The corrected rules reject `.env*` ancestor
  directories and `.env.production.example`, while permitting a regular
  `.env.example` template file. All 24 independent edge-case probes passed.
- Source and freshly generated distributions were reviewed for private
  artifacts and credentials. Known fixture values remain explicitly synthetic;
  scanning is not a guarantee against every unknown credential format.

No OCI changes or credential validity tests were performed. The website and
application runtime source are unchanged by this patch. Existing tags retain
their original content; this patch does not rewrite historical releases.

## Boundaries

Filename rules cannot recognize arbitrary secret-bearing JSON or modified source.
The installer is not a Git-tracked-files allowlist or a content sanitizer. Use a
fresh, reviewed checkout and keep private operational data elsewhere. Review
installed/generated files before sharing them. Optional hooks supplement that
review; installation does not enable or trust them automatically.

This patch changes neither OCI resources nor production acceptance. The tested
local application, site and packaging behavior and their remaining deployment
limits are described in [0.4.0 evidence](RELEASE-0.4.0.md).
