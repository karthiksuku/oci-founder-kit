# Develop and verify the toolkit

Work from a source checkout and read [AGENTS.md](../AGENTS.md) before editing.
The project installer creates a snapshot for application work; it does not
replace the source repository's development workflow.

Run the repository checks:

```sh
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

The real PostgreSQL integration suite requires a deliberately selected test
database through `TEST_DATABASE_URL`. It drops and recreates its fixture tables;
never point it at production or an existing shared database by inference.

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
is a canonical empty OCI declaration, exactly seven private settings, an existing
APIKey profile and the default workspace. Migration, state push, workspace
changes and version cleanup are not implemented.

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
IAM isolation, application recovery and retained-version cleanup remain pending.
A private/versioned bucket and passing mocked commands do not establish effective
IAM or restore behavior. Never publish account-specific policy/group details as
fixtures; use synthetic examples and link public primary documentation.

[Release evidence](RELEASE-0.3.4.md) records the current preview's checks and limits.
The [optional CI template](ci/validate.workflow.yml) is not installed as an Actions
workflow, so there is no GitHub Actions pass to infer from local results.

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
