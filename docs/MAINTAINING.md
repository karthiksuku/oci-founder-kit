# Develop and verify the toolkit

Work from a source checkout and read [AGENTS.md](../AGENTS.md) before editing.
The project installer creates a snapshot for application work; it does not
replace the source repository's development workflow.

Run the repository checks:

```sh
python3 scripts/release_manifest.py check
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
claude plugin validate .
terraform fmt -check -recursive blueprints
python3 scripts/blueprint.py check fullstack-container
```

Some checks require their corresponding local tool or installed app dependencies.
Report skipped checks explicitly. The reference application's locked dependencies
and tests are separate:

```sh
npm --prefix blueprints/fullstack-container/app ci
npm --prefix blueprints/fullstack-container/app test
```

The hardened checker has a real local HTTPS integration test using the app's
production routes, signed sessions and CSRF middleware with synthetic backing
stores. After installing the locked app dependencies, run:

```sh
FOUNDER_KIT_PRODUCTION_CHECK_LOCAL=1 python3 -m unittest discover -s tests -p test_production_check.py
```

This does not connect to OCI or an identity provider. TLS keys are generated
privately at runtime; no private key fixture is distributed.

## Distribution manifest

Installation uses only files listed in release-manifest.json and checks their
SHA-256 hashes. Unknown files, including untracked eligible JSON, are not copied.
This is integrity checking, not publisher authentication or content sanitization.
Obtain the source from the intended repository/release and review its contents.

After source changes, stage only reviewed public paths, then regenerate the
manifest from those Git-indexed paths and the current worktree bytes:

```sh
python3 scripts/release_manifest.py create
python3 scripts/release_manifest.py check
git add release-manifest.json
```

Regenerate after any listed byte changes, including versions and release notes.
Check that index and worktree agree before publication. Do not add private files
to the index merely to include them. Keep audit reports and operational evidence
outside the source tree. Verify installation and update from a clean release
archive as well as the working checkout.

The real PostgreSQL integration suite requires a deliberately selected test
database through `TEST_DATABASE_URL`. It drops and recreates its fixture tables;
never point it at production or an existing shared database by inference.

For editable project creation, run `test_blueprint_create.py` through unittest
discovery. Its refusal tests cover occupied targets, symlink changes, partial
publication and no-write dry runs. In a disposable created project, verify that
editing `app/` changes the preview and data persists across stop/start. Stop
retains its database volume; review removal separately and never prune shared
Docker resources to clean up a test.

The stateless [Next.js packaging rehearsal](../examples/migrate-nextjs/README.md)
has its own locked dependencies and real HTTP checks:

```sh
cd examples/migrate-nextjs
npm ci --ignore-scripts --no-audit --no-fund
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run test:parity
```

After building, the root suite can include that rehearsal with
`FOUNDER_KIT_NEXTJS_PARITY=1`. Without that explicit opt-in it reports a skip and
installs nothing. Its passing local HTTP contract does not establish hosted
Vercel behavior or OCI deployment.

For changed Terraform, validate the relevant blueprint with its committed lockfile
and supported provider. Provider validation does not create resources. Keep local
validation isolated from remote backend initialization. A remote plan can write
lock objects as well as read account metadata, so it needs a prior
backend-operation approval; apply still needs separate approval of the exact
saved resource plan. Follow [the deployment workflow](../skills/oci-deploy/SKILL.md)
and [native OCI state operations](../skills/oci-deploy/references/backend-state.md).

The backend gate's focused offline tests are:

```sh
python3 -m unittest discover -s tests -p 'test_backend*.py' -v
```

`backend-plan --operation init --backend-config PRIVATE_JSON` prepares an offline
packet. After exact owner approval, `backend-run` initializes the selected backend.
An initialized stack then uses an approved `backend-plan --operation plan` /
`backend-run` pair to generate a resource plan. Do not invoke remote Terraform
initialization or planning directly, even to test the gate. Its current contract
is a canonical empty OCI declaration, the reviewed private settings, an existing
APIKey or SecurityToken profile and the default workspace. Temporary sessions
must remain valid for the approved operation; expiry, reauthentication or changed
identity requires a fresh check and invalidates affected plans. Migration, arbitrary state push,
workspace changes and version cleanup are outside this general backend operation.
The separate synthetic rehearsal supports only its generated state and exact
version cleanup.

Changes to this contract need negative tests for source/cache ambiguity, stale
metadata, alternate workspace/data directories, destination or input drift,
expired/reused approvals and failure receipts. Do not weaken checks to make a
live test pass. Review module/provider implementations independently; the root
source/lockfile snapshot is not an execution sandbox or a recursive integrity
check of installed dependencies.

Use realistic consumer requests to verify skill changes. Check what the coding
agent actually reads, edits and runs; independently exercise generated runtime
behavior where practical. Keep local build, offline preparation, remote planning,
cloud deployment and traffic cutover results distinct. Do not turn a static scan or local unit-test
pass into a deployed-app claim.

One live synthetic OCI run verified state writes, plan lock contention and
historical-version recovery on 14 November 2026, with independent readback.
Its separately approved exact-version cleanup also passed, with fresh readback
confirming an empty test prefix. IAM isolation and application recovery remain
pending.
A private/versioned bucket and passing mocked commands do not establish effective
IAM or restore behavior. Never publish account-specific policy/group details as
fixtures; use synthetic examples and link public primary documentation.

[Release evidence](RELEASE-0.9.0.md) records the current preview's checks and limits.
The [CI and provenance guide](ci/README.md) describes the prepared validation,
platform and release workflows. Their definitions and local results do not imply
a successful GitHub run or an authenticated release artifact.

For the hardened reference, run mocked infrastructure contracts without OCI calls:

```sh
terraform -chdir=blueprints/fullstack-container/terraform test
```

For the static website, use Node 22.23.4 or a compatible newer version:

```sh
cd site
npm ci --ignore-scripts
npm run build
npm test
npx --no-install playwright install chromium
npm run test:browser
```

Publish only the built `site/dist/` output to the Pages branch with `.nojekyll`.
Keep test reports and screenshots outside the public source. Before release,
stage the intended source and run `python3 scripts/hooks.py public --project .`;
review Git history and generated artifacts as well.

Keep credentials, customer data, state, plans and unredacted receipts out of Git.
Use fictional test fixtures and scoped temporary processes with cleanup. See
[CONTRIBUTING.md](../CONTRIBUTING.md) and [SECURITY.md](../SECURITY.md) for contribution
and reporting boundaries.
