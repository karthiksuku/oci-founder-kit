# Real browser migration acceptance fixtures

This bounded runner uses Chromium against owned local fixtures. It does not read
an arbitrary app contract, execute user-supplied scripts, contact OCI or test a
founder's live account. Both example apps and Taskboard source are hashed before
and after execution; a source change fails the run. It starts and stops its own
servers, blocks browser requests to other origins, and removes temporary generated
certificates, synthetic sessions and downloaded content. Reports contain only
named outcomes and coverage, with no cookies, HTML, screenshots or raw origins.

Install the pinned test dependencies and prepare the existing example builds from
the kit root. Review dependency changes before running these commands:

```sh
npm ci --prefix tests/browser-migration --ignore-scripts --no-audit --no-fund
npm ci --prefix examples/migrate-nextjs --ignore-scripts --no-audit --no-fund
NEXT_TELEMETRY_DISABLED=1 npm run build --prefix examples/migrate-nextjs
npm ci --prefix blueprints/fullstack-container/app --ignore-scripts --no-audit --no-fund
```

Install Chromium in the browser test directory:

```sh
cd tests/browser-migration
npx --no-install playwright install chromium
cd ../..
node scripts/browser_migration.mjs
```

Use `playwright install --with-deps chromium` in a compatible CI environment that
needs browser system libraries. An existing reviewed browser can be selected with
`PLAYWRIGHT_CHROMIUM_EXECUTABLE`. The runner never downloads dependencies or a
browser on its own. Node.js, Python 3.11+, OpenSSL and local socket access are
required. Installed kit bundles include this pinned test package; a development
checkout may reuse the site's identical Playwright version if the test package
is not installed. The public site itself does not run these tests or accept
credentials.

The Python integration entrypoint is:

```sh
FOUNDER_KIT_MIGRATION_BROWSER=1 python3 -m unittest discover -s tests -p test_migration_browser.py
```

| Actual browser evidence | Scope |
| --- | --- |
| Next.js source production server and standalone package | Stage navigation, form submission, query-driven visible output, reload, redirect, escaped input and absence of JavaScript errors. A deliberately wrong visible expectation must be detected. |
| Ordinary catalogue source and target processes | Browser redirect, deep link and filtered JSON catalogue navigation. These are Python processes; Docker packaging and deployed OCI behavior require separate checks. |
| Taskboard's production browser client and HTTP/auth code | Two synthetic secure session cookies, separate user views, denied access to another user's task, task creation/update/reload, a 25-byte synthetic upload/download, deletion and logout. A fixture with CSRF protection removed must be detected. |

Taskboard uses **synthetic in-memory data/storage and pre-created test sessions**.
The positive flow removes its task and verifies an unrelated control remains
unchanged. Its fake uploaded object is discarded with the owned fixture process.
The negative control may create a synthetic row in that disposable process;
it never reaches a real provider. No real cloud resources are created or retained.

The Taskboard browser trusts only its locally generated loopback test certificate
through a fixture-scoped browser option. The separate HTTPS migration runner's
TLS-verification test remains mandatory and rejects untrusted certificates.

These checks establish actual local browser behavior, including executing the
bundled browser application. They do not establish hosted OIDC login/callbacks,
provider database or object-store semantics, deployed image identity, real
traffic rollback, isolated provider restore, production load or a founder's own
app acceptance. HTTP event streaming and repeated cache-read negative controls
are covered separately by `tests/test_migration.py`; browser hydration success
for this fixture does not certify every framework feature or multi-instance
cache invalidation.
