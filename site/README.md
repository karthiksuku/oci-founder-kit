# Founder start site

A static, responsive entry point for OCI Founder Kit. The public site explains
the build, migrate and setup paths and generates prompts for Claude Code or
Codex. The Python toolkit installer does not require this site's dependencies.

## Develop and verify

Use Node.js 22.23.4 or newer and npm. Dependency versions and their integrity
hashes are pinned in `package-lock.json`.

```sh
cd site
npm ci
npm run dev
```

Open the URL shown by Astro, including `/oci-founder-kit/`.

```sh
npm run build
npm test
npx playwright install chromium
npm run test:browser
npm audit
```

The build includes Astro's TypeScript check. Browser tests exercise all task and
agent combinations, clipboard success/fallback, mobile navigation, keyboard
access, light/dark layout, local-only brief handling and automated accessibility
checks. Automated checks supplement visual and assistive-technology review.

Browser tests start the built site's preview on loopback port 4321. Environments
that block local HTTP listeners need loopback permission. A preinstalled Chromium
can be selected using `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; otherwise use Playwright's
matching browser installation.

## Build and hosting

`npm run build` writes static files to `dist/`. GitHub Pages defaults are:

- Site origin: `https://karthiksuku.github.io`
- Base path: `/oci-founder-kit/`

Set `SITE_URL` and `SITE_BASE` at build time for a different public host. Use `/`
as the base for a root domain. No server adapter or runtime secret is required.
The [Astro GitHub Pages guide](https://docs.astro.build/en/guides/deploy/github/)
describes Pages deployment. Publishing is managed at repository level; a local
build alone does not establish a live deployment.

## Privacy and behavior

- The site makes no API calls and has no analytics, sign-up, repository access
  or credential collection. Fonts and interface assets are served locally.
- The project brief exists only in the current page. It is not placed in URLs,
  local storage, session storage or network requests. Copying explicitly writes
  it to the user's clipboard. Do not enter credentials in a project brief.
- Only the selected display theme is saved in local storage. Storage failures
  are harmless and do not prevent use of the site.
- The prompt is plain text. User text is assigned to a textarea value, never
  interpreted as markup. Clipboard denial selects the text for manual copying.
- The workflow illustration explains a sequence; it does not report a real
  deployment. Example cards state their actual verification level.
- Without JavaScript the default prompt, terminal commands, path content and
  documentation links remain available.
- The local Astro runner disables Astro telemetry for builds and previews.

## Content and attribution

The page, diagrams, icons and styles are original work under the repository's
UPL-1.0 license. No official Oracle logo or proprietary icon set is included.
Manrope is self-hosted from the pinned Fontsource package under the SIL Open
Font License; its copyright and license ship in
[`public/licenses/manrope-OFL.txt`](public/licenses/manrope-OFL.txt).

Community projects are linked as source references, not copied into this site:

| Project | Public license/source | Review boundary |
|---|---|---|
| Full Stack FastAPI Template | [MIT](https://github.com/fastapi/full-stack-fastapi-template/blob/master/LICENSE) | Public source reviewed; OCI deployment not verified here |
| Open SaaS | [MIT](https://github.com/wasp-lang/open-saas/blob/main/LICENSE) | Public source reviewed; OCI adaptation not verified here |
| OCI Starter | [Repository and its license](https://github.com/oracle-devrel/oci-starter) | Public source reviewed; review the selected generated configuration |

See the repository's [ecosystem notes](../docs/ECOSYSTEM.md) before reusing a
reference. Keep each project's license and attribution with any code you adopt.
