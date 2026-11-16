# Ordinary container: hosting rehearsal

This synthetic catalogue is a small Python web service with no package dependencies,
database, credentials or background jobs. Its JSON workflow, deep link, redirect,
anonymous denial, cache header and event stream provide an executable migration
contract. It does not replace an existing founder application.

From the kit root:

```sh
python3 examples/migrate-container/rehearse.py
```

Two owned loopback servers run the same read-only HTTP checks. The baseline must
pass, changed response data and cache headers must fail, and the original source
must remain unchanged. Both servers stop afterward. This is local Python HTTP
evidence; it does not claim a Docker build, browser behavior or deployed OCI parity.
The all-zero image digest in this local rehearsal is synthetic, not an artifact.

For a separate local container build and run:

```sh
docker build -t founder-catalogue:local examples/migrate-container
docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --publish 127.0.0.1:8080:8080 founder-catalogue:local
```

The container runs as UID 10001 and contains only the server. Review the base image
and record the built digest before OCI promotion. Use Docker Engine 28 or later
for this loopback publishing recipe. Publishing an image and creating cloud
resources require their own approved plans. Configure HTTPS at the selected OCI
load balancer; this service accepts HTTP only behind that reviewed boundary.

For an actual migration, keep your app and existing database, storage and identity
provider. Create a private contract against the selected source and OCI origins
using [hosting-first verification](../../skills/oci-migrate-web/references/hosting-first.md).
Verify provider connectivity, TLS, callback allowlists and latency separately.
Authenticated browser workflows, uploads, data writes, cache invalidation, recovery,
job ownership and real traffic rollback remain additional acceptance work.
