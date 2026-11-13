# Publish a reviewed image to OCI Container Registry

Image upload is a cloud write. Use the deploy tool's `image-plan` and
`image-push` commands, with a separate owner approval after the registry has
been created. A registry creation approval does not approve an image upload.

## Prerequisites

- A locally built and tested image. Build from reviewed source without private
  files in the build context. Keep the resulting immutable Docker image ID.
  This path supports a single-platform Linux `amd64` or `arm64` image; a
  multi-platform manifest list is not accepted as verified publication.
- The original successful registry **creation** Terraform apply receipt from
  this kit, identifying the intended non-root compartment, region and repository
  resource. An update-only receipt is not accepted as the identity anchor.
- A private OCI registry with **immutable tags enabled**. An absence check alone
  cannot prevent a different publisher from creating the same tag concurrently;
  the server must reject tag replacement. Follow the two-stage setup below.
  The current gate supports commercial-realm (`oc1`) registries using the
  selected region's `ocir.io` endpoint; other realms need a separately supported
  and tested implementation.
- OCI CLI read access to the selected repository and its images, and an existing
  authorized Docker registry login. Configure authentication privately. The gate
  never logs in, creates an auth token, changes IAM or requests a secret value.
- A new, unique tag, such as a source revision plus a release identifier. Retain
  the previous image digest for a separately reviewed rollback.

The helper requires a POSIX host and has been tested on Linux. Native Windows
and other host operating systems have not been verified.

## Prepare the empty repository, then enable immutable tags

OCI's [create documentation](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/create.html)
says immutability cannot be set during creation. Its
[update documentation](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/update.html)
exposes that setting. These were checked on 13 November 2026; this sequence has
not yet been exercised against a live OCI repository.

1. Copy the registry's example variables into a private ignored file. Keep
   `immutable_tags = false`. Use `oci-deploy` to plan creation of the empty,
   private repository, obtain approval of the exact plan and apply it. Keep its
   original creation receipt; do not push any image yet.
2. Change only `immutable_tags = true` in that file. Generate a new Terraform
   plan against the same state. Review the actual attribute change: it should
   update the same repository, without creation, replacement, deletion or IAM
   changes. Obtain approval of this distinct plan before applying it.
3. Keep both receipts. Supply the original creation receipt to `image-plan`;
   its OCI reads must confirm that immutability is now enabled. If the service
   refuses the update or the read-back cannot confirm it, stop publication and
   report the unsupported path. Do not bypass the check with a direct push.

For an existing repository, the same requirement for an original creation
receipt applies. Do not disable immutability to get a conflicting tag through
the gate.

## Prepare the upload request

From the kit root, using your private receipt path and repository identifier:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py image-plan \
  --dir /absolute/path/to/registry-stack \
  --registry-receipt /absolute/path/to/registry-stack/.gate/receipts/approved-apply.json \
  --repository-id '<repository-ocid>' \
  --image 'sha256:<locally-built-image-id>' \
  --tag 'sha-<source-revision>'
```

This performs local inspection and OCI reads. It derives the destination from
the repository metadata rather than accepting an arbitrary registry host. The
saved request binds the source image identity and size, exact repository/tag,
target, Docker executable and expiry. The default image-size limit is 1 GiB;
`--max-image-bytes` can set an explicitly reviewed bound. The limit uses local
image bytes, not a guarantee about total registry storage, transfer or billing.

Review the source/image identity, platform, target, new tag, size, dated storage
and transfer estimate, and approval hash. The private request lives in
`.gate/image-plan.json`; it is not a public release artifact. The owner must
approve this exact hash in the current conversation.

## Execute once after approval

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py image-push \
  --dir /absolute/path/to/registry-stack \
  --approve '<approved-image-plan-sha256>'
```

The tool rechecks its prerequisites and consumes the approval before the first
tag/push attempt. It checks the resulting OCI image and its registry manifest,
including the source image's configuration digest and platform, before reporting
a verified receipt. Use the receipt's immutable
image URI as `app_image` in the separate workload Terraform plan; do not replace
it with a mutable tag.

Attempt receipts are private files under `.gate/image-receipts/`. Inspect the
actual `status`: only `verified` establishes the image publication check. A
failed push or unavailable verification can leave uploaded layers or an image.
Keep the receipt, inspect the selected repository read-only, and report that
uncertainty. Fix access or other prerequisites privately, then prepare a fresh
request and obtain fresh approval; do not reuse an approval or retry a direct push.

## Boundaries and cleanup

The gate cannot prove that a person consented or protect against a malicious
process controlling the same OS account or Docker daemon. Keep normal coding
agent permission prompts and scoped OCI permissions. Hook checks complement
these controls; they do not authorize upload.

The upload does not deploy the app, change DNS, establish production readiness
or approve deletion. Image retention, failed-upload residue and repository
teardown require an explicit inventory and a separately reviewed cleanup plan.
Do not delete a shared repository or another workload's retained image merely
to make cleanup succeed.
