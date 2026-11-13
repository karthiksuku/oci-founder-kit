# Publish a reviewed image to OCI Container Registry

The primary flow publishes an exact image **by digest, without assigning a remote
tag**. Image upload is a cloud write: create the private registry through the
deploy gate, then obtain separate owner approval of the image plan before
`image-push`. Registry creation does not approve upload or application deployment.

Local checks cover artifact binding, approval handling and real Skopeo transfer
to a synthetic TLS registry. Live OCI digest publication is still unverified;
record the actual result in your account before claiming a successful upload.

## Prerequisites

- A locally built and tested single-platform Linux `amd64` or `arm64` image.
  Build from reviewed source without private files in the context. Keep the
  tested Docker image ID; a local tag alone does not identify the reviewed bytes.
- Trusted Docker, OCI CLI and Skopeo clients on a POSIX host. Local checks used
  Linux; other hosts have not been verified. The gate fingerprints the selected
  client executables and refuses a changed executable after approval.
- The original successful registry **creation** apply receipt from this kit,
  identifying the repository in the selected non-root compartment and region.
  An update-only receipt cannot replace this identity anchor.
- An available private standard OCIR repository, not a top-level prefix or
  pull-through repository. The gate supports commercial-realm (`oc1`)
  registries at the selected region's `ocir.io` endpoint.
- OCI CLI read permissions for the exact repository and its images, and existing
  authorized registry credentials in a private auth JSON file. The file must
  contain `auths` with an `auth` entry for the exact registry host. Credential
  helpers, `credsStore` and identity-token-only entries are unsupported. Keep
  the file owned by the operator, mode `0600`, outside Git, with no links.
  Do not paste or print its base64 credentials; base64 does not protect a secret.

The gate never logs in, creates an auth token, changes IAM or retrieves a secret
value. Missing registry authentication requires a separate approved private
setup; do not put credentials in command arguments or chat.

## Create the empty private repository

Use the blueprint's `registry/` stack with `immutable_tags = false`. Prepare its
plan through `oci-deploy`, review the scope and cost, obtain approval of that
exact hash, then apply it. Retain the original creation receipt privately.

Digest publication does not require changing `immutable_tags`: the destination
is the content digest and the client must preserve it. It never assigns or
replaces a tag. A digest does not prevent an authorized identity from deleting an
image; retention and deletion permissions still need review.

## Prepare the image locally

After running the image's local acceptance checks, use its exact Docker ID.
Replace the placeholder below. Run these local commands in one shell:

```sh
umask 077
image_id='sha256:<tested-local-image-id>'
publication_dir="$(mktemp -d /tmp/oci-image-publication.XXXXXXXX)"
docker image save --output "$publication_dir/image.tar" "$image_id"
mkdir -m 700 "$publication_dir/layout"
skopeo copy --format v2s2 --dest-compress --dest-compress-format gzip \
  "docker-archive:$publication_dir/image.tar" "dir:$publication_dir/layout"
chmod 600 "$publication_dir"/layout/*
```

This Docker archive conversion avoids relying on Skopeo compatibility with the
host's Docker daemon API. The [Skopeo copy options](https://github.com/podman-container-tools/skopeo/blob/main/docs/skopeo-copy.1.md)
select Docker schema 2 and gzip layers. These commands prepare local files only;
they do not upload an image. Allow disk space for the archive, compressed layout
and the gate's private copy during publication.

Keep this private directory until the attempt is resolved. Use a stable private
directory instead of `/tmp` if your host removes temporary files during that
period. Paths must have no symlink components. The gate accepts only the prepared
manifest, version file and their blobs; extra files, signatures, foreign URLs,
manifest lists, links and unsupported compression are rejected. It checks the
configuration digest against the tested Docker ID and each layer against the
configuration's uncompressed rootfs digest.

## Review the exact upload plan

From the kit root, using the same shell and your existing private paths:

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py image-plan \
  --dir /absolute/path/to/registry-stack \
  --registry-receipt /absolute/path/to/registry-stack/.gate/receipts/original-create.json \
  --repository-id '<repository-ocid>' \
  --image "$image_id" \
  --layout "$publication_dir/layout" \
  --registry-auth-file /absolute/private/path/registry-auth.json
```

The command performs local inspection and OCI reads. It derives the destination
from verified repository metadata and saves a private `.gate/image-plan.json`.
The plan binds the original receipt, account/region/repository, exact digest,
platform, artifact sizes and hashes, auth-file hash, client executables, workspace
and expiry. Changing any bound input requires a new plan.

The default `--max-image-bytes` is 1 GiB; the maximum is 10 GiB. The gate separately
bounds the local image size, stored artifact bytes and the sum of uncompressed
layer occurrences. This is not a billing estimate or a guarantee about registry
deduplication. Review storage, transfer, retained images and failed-upload cost
with dated sources. `--max-age-minutes` can set an approval lifetime of 1–1440
minutes. The owner must approve the displayed plan hash in the current conversation.

## Execute once after approval

```sh
python3 skills/oci-deploy/scripts/deploy_gate.py image-push \
  --dir /absolute/path/to/registry-stack \
  --approve '<approved-image-plan-sha256>'
```

The gate rechecks the exact repository, source, clients, credentials and expiry;
copies the approved layout into a private runtime; and consumes approval before
the remote write. Skopeo uses verified TLS, an isolated registry configuration,
the exact host's auth entry and `--preserve-digests`. It copies to
`<registry>/<namespace>/<repository>@sha256:<digest>` without creating a tag.

Success requires an scoped OCI image listing followed by retrieval by image ID and a raw registry manifest
whose digest matches the approved artifact. Only a receipt with `status: verified`
establishes this publication check. Use its immutable image URI as `app_image`
in a separately reviewed workload plan. Publication does not prove deployment,
application readiness or recovery.

Attempt receipts remain in `.gate/image-receipts/`. A timeout, partial upload or
unavailable verification can leave blobs or an image. Retain the receipt, inspect
the selected repository read-only and report uncertainty. An attempted write
consumes approval even if it fails. Correct prerequisites privately, prepare a
fresh plan and obtain fresh approval; do not retry with a direct push.

## Legacy tag publication

`--tag` is a separate legacy mode, mutually exclusive with `--layout`. It uses
the existing Docker login and requires the gate to confirm **immutable tags are
already enabled**. An absence check alone cannot prevent another publisher from
claiming a tag between inspection and upload.

OCI's [create documentation](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/create.html)
says setting immutability at creation is unsupported. The
[update documentation](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/update.html)
exposes the setting, but that does not establish availability in a particular
service deployment. These references were checked on 13 November 2026.
If legacy tags are required, separately plan and approve an update of the same
repository and verify read-back. Keep its original creation receipt. If the
service refuses the setting or the gate cannot confirm it, this mode remains
unsupported; do not bypass it or imply tag safety from an empty repository.

## Retention and cleanup

The registry, published image and previous rollback digests are retained until
their owner approves cleanup. Deleting local preparation files does not delete
cloud artifacts; destroying the app stack does not destroy its separate registry.
Inventory images, failed-upload residue, object versions, backups and shared
resources before any separately reviewed deletion. Keep the state and receipts
needed to identify those resources. Never delete a shared repository or another
workload's retained image merely to make cleanup succeed.

The gate cannot prove human consent or defend against a process controlling the
same OS account, Docker daemon or installed libraries. Keep normal agent
permissions and scoped OCI access. Hook checks complement these controls and
do not authorize upload.
