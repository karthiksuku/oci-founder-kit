#!/usr/bin/env node
// Fixed local fixture acceptance. No arbitrary app/URL/script arguments, cloud or real credentials.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const nextRoot = path.join(root, 'examples/migrate-nextjs');
const appRoot = path.join(root, 'blueprints/fullstack-container/app');
const catalogueRoot = path.join(root, 'examples/migrate-container');
const localRequire = createRequire(path.join(root, 'tests/browser-migration/package.json'));
let playwright;
try { playwright = localRequire('@playwright/test'); }
catch { playwright = createRequire(path.join(root, 'site/package.json'))('@playwright/test'); }
const { chromium, expect } = playwright;
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'oci-browser-migration-'));
fs.chmodSync(temporary, 0o700);
const children = new Set();
const childEnv = { PATH: process.env.PATH, NODE_ENV: 'production', NEXT_TELEMETRY_DISABLED: '1', PYTHONDONTWRITEBYTECODE: '1' };
const hash = value => createHash('sha256').update(value).digest('hex');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { schema: 'oci-browser-migration-fixtures/1', scope: 'owned-loopback-fixtures-only',
  cloud_calls: false, hosted_sign_in_verified: false, provider_data_verified: false,
  deployed_image_identity_verified: false, production_readiness_established: false,
  checks: [], negative_controls: [], retained_cloud_resources: 0,
  not_covered: ['hosted-oidc-and-callback', 'real-database-and-storage', 'cloud-network-and-iam',
    'real-traffic-cutover-and-rollback', 'isolated-provider-restore', 'deployed-image-rollback', 'production-load'] };

function snapshot(folder) {
  const values = [];
  function walk(selected, prefix = '') {
    for (const entry of fs.readdirSync(selected, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (['node_modules', '.next', '.next-reference', '__pycache__', '.local-preview'].includes(entry.name)) continue;
      if (entry.name.startsWith('.env') && entry.name !== '.env.example') throw new Error('Private example configuration refused');
      assert(!entry.isSymbolicLink());
      const current = path.join(selected, entry.name);
      if (entry.isDirectory()) walk(current, prefix + entry.name + '/');
      else if (entry.isFile()) {
        const info = fs.statSync(current); assert(info.size < 4 * 1024 * 1024);
        values.push([prefix + entry.name, hash(fs.readFileSync(current))]);
      }
      assert(values.length <= 3000);
    }
  }
  walk(folder);
  return hash(JSON.stringify(values));
}

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

function child(command, args, cwd, extraEnv = {}) {
  const proc = spawn(command, args, { cwd, env: { ...childEnv, ...extraEnv }, stdio: ['pipe', 'ignore', 'ignore'] });
  children.add(proc);
  proc.on('error', () => {}); // Readiness detects unavailable tools without reflecting commands or inputs.
  return proc;
}

async function stop(proc, { stdin = false } = {}) {
  if (proc.exitCode !== null || proc.signalCode !== null) { children.delete(proc); return; }
  if (stdin) proc.stdin.end(); else proc.kill('SIGTERM');
  const deadline = Date.now() + 5000;
  while (proc.exitCode === null && proc.signalCode === null && Date.now() < deadline) await pause(30);
  if (proc.exitCode === null && proc.signalCode === null) {
    proc.kill('SIGKILL');
    await new Promise(resolve => proc.once('exit', resolve));
  }
  children.delete(proc);
}

async function health(origin, proc) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline && proc.exitCode === null) {
    const ok = await new Promise(resolve => {
      const req = http.get(origin + '/healthz', { timeout: 1000 }, res => { res.resume(); resolve(res.statusCode === 200); });
      req.on('error', () => resolve(false)); req.on('timeout', () => { req.destroy(); resolve(false); });
    });
    if (ok) return;
    await pause(100);
  }
  throw new Error('Owned fixture did not become ready');
}

async function context(browser, origin, { tls = false } = {}) {
  assert(/^https?:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(origin));
  const selected = await browser.newContext({ serviceWorkers: 'block', ignoreHTTPSErrors: tls,
    viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  // TLS bypass is only for this runner's generated loopback fixture certificate.
  // The production migration HTTP runner always validates TLS independently.
  selected.setDefaultTimeout(8000);
  await selected.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.origin === origin ? route.continue() : route.abort('blockedbyclient');
  });
  await selected.routeWebSocket('**/*', socket => socket.close());
  return selected;
}

async function nextFlow(browser, origin, expectedProject = 'Orbit & Co') {
  const selected = await context(browser, origin);
  try {
    const page = await selected.newPage(); const errors = [];
    page.on('pageerror', () => errors.push(true));
    await page.goto(origin, { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { name: 'Your next app. One clear step.' })).toBeVisible();
    await page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Build a useful prototype' }) }).getByRole('link').click();
    await expect(page).toHaveURL(origin + '/checklist/prototype');
    await page.getByRole('textbox', { name: /Project name/ }).fill('Orbit & Co');
    await page.getByRole('button', { name: 'Preview' }).click();
    await expect(page.locator('[data-project]')).toHaveText('Orbit & Co');
    assert.equal(await page.locator('[data-project]').textContent(), expectedProject, 'fixed-visible-result-negative-control');
    await expect(page.locator('.checklist li')).toHaveCount(3);
    await expect(page.locator('.checklist li').first()).toHaveText('Build the smallest useful flow');
    await page.reload({ waitUntil: 'networkidle' });
    await expect(page.locator('[data-project]')).toHaveText('Orbit & Co');
    await page.goto(origin + '/start?project=Redirected', { waitUntil: 'networkidle' });
    await expect(page).toHaveURL(origin + '/checklist/idea?project=Redirected');
    await expect(page.locator('[data-project]')).toHaveText('Redirected');
    const escaped = '<img src=x onerror="alert(1)">';
    await page.getByRole('textbox', { name: /Project name/ }).fill(escaped);
    await page.getByRole('button', { name: 'Preview' }).click();
    await expect(page.locator('[data-project]')).toHaveText(escaped);
    await expect(page.locator('[data-project] img')).toHaveCount(0);
    await page.getByRole('link', { name: 'All stages' }).click();
    await expect(page.getByRole('region', { name: 'Choose a stage' })).toBeVisible();
    assert.equal(errors.length, 0);
    return { workflow: 'navigation-form-preview-reload-redirect-escaping', javascript_errors: 0 };
  } finally { await selected.close(); }
}

async function catalogueFlow(browser, origin) {
  const selected = await context(browser, origin);
  try {
    const page = await selected.newPage();
    await page.goto(origin + '/start');
    await expect(page).toHaveURL(origin + '/catalogue');
    await expect(page.getByRole('heading', { name: 'Small catalogue' })).toBeVisible();
    await page.getByRole('link', { name: 'Browse work items' }).click();
    await expect(page).toHaveURL(origin + '/api/items?category=work');
    await expect(page.locator('body')).toContainText('Field notebook');
    await expect(page.locator('body')).not.toContainText('Studio mug');
    return { workflow: 'redirect-deep-link-filtered-catalogue' };
  } finally { await selected.close(); }
}

async function taskboardFixture(fault) {
  const folder = path.join(temporary, 'taskboard-' + fault); fs.mkdirSync(folder, { mode: 0o700 });
  const key = path.join(folder, 'key.pem'), cert = path.join(folder, 'cert.pem');
  const issued = spawnSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
    '-keyout', key, '-out', cert, '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
    { env: childEnv, stdio: 'ignore', timeout: 30000 });
  assert.equal(issued.status, 0); fs.chmodSync(key, 0o600); fs.chmodSync(cert, 0o600);
  const ready = path.join(folder, 'ready.json'), final = path.join(folder, 'final.json');
  const proc = child(process.execPath, [path.join(root, 'tests/fixtures/production_check_server.mjs'), key, cert, ready, final, fault], root);
  const deadline = Date.now() + 10000;
  while (!fs.existsSync(ready) && proc.exitCode === null && Date.now() < deadline) await pause(50);
  assert(fs.existsSync(ready));
  const data = JSON.parse(fs.readFileSync(ready, 'utf8'));
  assert(/^https:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(data.origin));
  return { proc, data, final };
}

async function taskboardFlow(browser, data, { csrfOnly = false } = {}) {
  const contexts = [];
  try {
    for (const user of ['a', 'b']) {
      const selected = await context(browser, data.origin, { tls: true });
      contexts.push(selected);
      const [name, ...rest] = data.users[user].split('=');
      assert.equal(name, '__Host-taskboard');
      await selected.addCookies([{ name, value: rest.join('='), url: data.origin, secure: true, httpOnly: true, sameSite: 'Lax' }]);
      const stored = await selected.cookies(data.origin);
      assert.equal(stored.length, 1); assert(stored[0].secure && stored[0].httpOnly && stored[0].sameSite === 'Lax');
    }
    const [a, b] = contexts;
    // The fixture endpoint is owned and synthetic. This bounded negative write
    // must be rejected; the whole in-memory fixture is discarded after the test.
    const csrf = await a.request.post(data.origin + '/api/tasks', { data: { title: 'Synthetic forbidden CSRF probe' }, maxRedirects: 0 });
    assert.equal(csrf.status(), 403, 'fixed-csrf-negative-control');
    if (csrfOnly) return;
    const page = await a.newPage(), other = await b.newPage();
    const errors = []; page.on('pageerror', () => errors.push(true));
    await page.goto(data.origin, { waitUntil: 'networkidle' });
    await other.goto(data.origin, { waitUntil: 'networkidle' });
    await expect(page.locator('#account-state')).toHaveText('Your private workspace');
    await expect(other.locator('#tasks .task')).toHaveCount(0);
    await page.locator('#title').fill('Browser workflow fixture');
    await page.locator('#new-task button[type=submit]').click();
    await expect(page.locator('#tasks .task')).toHaveCount(1);
    await expect(page.locator('#tasks .title')).toHaveText('Browser workflow fixture');
    const tasks = await (await a.request.get(data.origin + '/api/tasks', { maxRedirects: 0 })).json();
    assert.equal(tasks.length, 1); assert(Number.isSafeInteger(tasks[0].id));
    assert.equal((await b.request.get(data.origin + '/api/tasks/' + tasks[0].id, { maxRedirects: 0 })).status(), 404);
    await other.reload({ waitUntil: 'networkidle' });
    await expect(other.locator('#tasks .task')).toHaveCount(0);
    await page.getByRole('checkbox').check();
    await expect(page.locator('#tasks .task')).toHaveClass(/done/);
    await page.reload({ waitUntil: 'networkidle' });
    await expect(page.getByRole('checkbox')).toBeChecked();
    const upload = Buffer.from('Synthetic browser upload\n');
    await page.locator('input[type=file]').setInputFiles({ name: 'fixture.txt', mimeType: 'text/plain', buffer: upload });
    await expect(page.getByRole('link', { name: 'fixture.txt' })).toBeVisible();
    const downloaded = page.waitForEvent('download');
    await page.getByRole('link', { name: 'fixture.txt' }).click();
    const stream = await (await downloaded).createReadStream();
    let contents = Buffer.alloc(0);
    for await (const chunk of stream) { contents = Buffer.concat([contents, chunk]); assert(contents.length <= 1024); }
    assert.equal(hash(contents), hash(upload));
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(page.locator('#tasks .task')).toHaveCount(0);
    await page.locator('#sign-out').click();
    await expect(page.locator('#account-state')).toHaveText('Sign in to see your tasks.');
    assert.equal((await a.request.get(data.origin + '/api/tasks', { maxRedirects: 0 })).status(), 401);
    assert.equal(errors.length, 0);
    return { workflow: 'session-cookie-two-user-isolation-task-update-reload-upload-download-delete-logout',
      upload_bytes: upload.length, javascript_errors: 0, stores: 'synthetic-memory-only' };
  } finally { for (const selected of contexts) await selected.close(); }
}

let browser;
let currentStep = 'browser-prerequisites';
const baseline = new Map([[nextRoot, snapshot(nextRoot)], [catalogueRoot, snapshot(catalogueRoot)], [appRoot, snapshot(appRoot)]]);
let aborting = false;
async function abort() {
  if (aborting) return;
  aborting = true;
  report.status = 'unknown'; report.interrupted = true;
  for (const proc of children) await stop(proc);
  if (browser) await browser.close().catch(() => {});
  fs.rmSync(temporary, { recursive: true, force: true });
  console.log(JSON.stringify(report, null, 2));
  process.exit(2);
}
process.once('SIGTERM', abort);
process.once('SIGINT', abort);
const watchdog = setTimeout(abort, 180000);
try {
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}) });
  report.browser = 'Chromium'; report.browser_version = browser.version();
  for (const mode of ['source', 'standalone']) {
    currentStep = 'nextjs-' + mode;
    const port = await freePort(), origin = 'http://127.0.0.1:' + port;
    const args = mode === 'source' ? [path.join(nextRoot, 'node_modules/next/dist/bin/next'), 'start', '--hostname', '127.0.0.1', '--port', String(port)] : [path.join(nextRoot, '.next/standalone/server.js')];
    const proc = child(process.execPath, args, nextRoot, { HOSTNAME: '127.0.0.1', PORT: String(port), ...(mode === 'source' ? { OCI_KIT_REFERENCE: '1' } : {}) });
    try {
      await health(origin, proc);
      report.checks.push({ id: 'nextjs-' + mode, status: 'passed', ...await nextFlow(browser, origin) });
      if (mode === 'standalone') {
        let caught = false;
        try { await nextFlow(browser, origin, 'Incorrect expected project'); }
        catch (error) { caught = error.code === 'ERR_ASSERTION' && error.message.includes('fixed-visible-result-negative-control'); }
        assert(caught); report.negative_controls.push({ id: 'nextjs-wrong-visible-result', detected: true });
      }
    } finally { await stop(proc); }
  }
  for (const mode of ['source', 'target']) {
    currentStep = 'catalogue-' + mode;
    const port = await freePort(), origin = 'http://127.0.0.1:' + port;
    const proc = child('python3', [path.join(catalogueRoot, 'server.py'), '--port', String(port)], catalogueRoot);
    try { await health(origin, proc); report.checks.push({ id: 'catalogue-' + mode, status: 'passed', ...await catalogueFlow(browser, origin) }); }
    finally { await stop(proc); }
  }
  for (const fault of ['none', 'missing-csrf-control']) {
    currentStep = 'taskboard-' + fault;
    const fixture = await taskboardFixture(fault);
    try {
      if (fault === 'none') report.checks.push({ id: 'taskboard-browser-workflow', status: 'passed', ...await taskboardFlow(browser, fixture.data) });
      else {
        let caught = false;
        try { await taskboardFlow(browser, fixture.data, { csrfOnly: true }); }
        catch (error) { caught = error.code === 'ERR_ASSERTION' && error.message.includes('fixed-csrf-negative-control'); }
        assert(caught); report.negative_controls.push({ id: 'taskboard-missing-csrf', detected: true });
      }
    } finally {
      await stop(fixture.proc, { stdin: true });
      const final = JSON.parse(fs.readFileSync(fixture.final, 'utf8'));
      assert(final.foreignUnchanged);
      if (fault === 'none') { assert.equal(final.remainingRows, 1); assert.equal(final.retainedObjects, 1); }
      // Fake storage disappears when the fixture process exits; no cloud resources exist.
    }
  }
  report.source_preserved = [...baseline].every(([folder, before]) => snapshot(folder) === before);
  assert(report.source_preserved);
  report.status = 'passed';
} catch {
  report.status = aborting ? 'unknown' : 'failed';
  report.failed_step = currentStep;
  report.failure = 'A fixed local browser assertion or prerequisite failed; no private browser details are emitted.';
} finally {
  for (const proc of children) await stop(proc);
  if (browser) await browser.close();
  clearTimeout(watchdog);
  report.source_preserved = [...baseline].every(([folder, before]) => snapshot(folder) === before);
  fs.rmSync(temporary, { recursive: true, force: true });
}
if (!aborting) {
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.status === 'passed' ? 0 : 1;
}
