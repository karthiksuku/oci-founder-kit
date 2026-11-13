# Run Taskboard on your laptop

Create, edit and complete tasks with a real PostgreSQL database, before setting
up an OCI account. This is an unauthenticated local sandbox. File attachments
are unavailable because this preview does not connect to OCI Object Storage.

You need Python 3.11+, Docker Engine 28+ (or current Docker Desktop), and Docker
Compose with `up --wait`, `--wait-timeout` and `build --builder` support. Linux, macOS and WSL2 with a local Docker daemon
are supported by the helper. Host Node.js and OCI credentials are not required.
Docker must be running. The first start builds the existing app and can download
the public Node 22 and PostgreSQL 16 images and locked npm dependencies.

From the repository root:

```sh
python3 blueprints/fullstack-container/local_preview.py start
```

Open the URL printed after both services are healthy, normally
`http://127.0.0.1:8080`. Add a task, rename it and mark it complete.
The app is published on IPv4 loopback only; PostgreSQL has no published port.
The helper refuses remote Docker endpoints. Do not expose this sandbox through
a tunnel, public interface or production domain.

If port 8080 is occupied, select another unprivileged port:

```sh
python3 blueprints/fullstack-container/local_preview.py start --port 8081
```

The helper creates `.local-preview/` with private permissions and generates a
development database password. Its settings are ignored by Git and excluded from
kit installations. Keep that folder private; do not paste its contents, a Docker
inspection or expanded Compose configuration into chat or an issue.

## Status, edits and stopping

```sh
python3 blueprints/fullstack-container/local_preview.py status
python3 blueprints/fullstack-container/local_preview.py stop
```

`stop` removes this preview's containers and network. **It retains the named
database volume and private settings.** Run `start` again to keep working with
the same tasks. After editing `app/`, run `start` to rebuild the app; there is no
automatic cloud deployment or background file watcher.

Keep the private settings with the database volume. If settings are lost, restore
them; the helper refuses to generate a different password for an existing preview.
There is deliberately no reset command. Removing stored tasks is a separate,
explicit decision: identify and back up the exact preview volume before any
manual deletion. Avoid Docker-wide prune commands and `down --volumes` when you
intend to preserve data.

## If startup fails

- Check that Docker is running and uses a local context. SSH/TCP Docker endpoints
  are rejected so this command cannot silently create a remote preview.
- Upgrade an older Docker/Compose installation. Docker versions before 28 have
  limitations around loopback-published ports; the helper requires 28 or newer.
- Check available memory, disk space and the selected port. After initialization,
  detailed client failures are saved privately in `.local-preview/last-error.log`.
  Redact that file before sharing it.
- If Docker's address pools are exhausted, choose an unused private subnet that
  does not overlap your host, VPN or Docker networks. Stop an existing preview
  before changing its subnet, then use `start --subnet <unused-private-CIDR>`.
  The helper accepts RFC1918 IPv4 ranges with prefix /24 through /28 and never
  changes daemon-wide address pools.
- A failed start may leave this preview's containers or volume. Use `status`,
  then `stop` to remove its containers/network while keeping stored tasks.

This preview verifies local behavior only. Hosted sign-in, per-user authorization,
HTTPS, OCI storage, cloud backups and deployment still need their own configuration
and checks. Continue with the [blueprint guide](README.md) when the app works
locally; cloud changes keep their exact-plan approval requirement.

Compose behavior: [waiting for healthy services](https://docs.docker.com/reference/cli/docker/compose/up/),
[published ports](https://docs.docker.com/engine/network/port-publishing/), and
[what down removes](https://docs.docker.com/reference/cli/docker/compose/down/).
