// The Python caller requires a new Linux network namespace before launching this
// process. Routing/CSP provide extra HTTP controls; they cannot contain WebRTC.
// No Node code from the evaluated app is imported or executed.
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const [modulePath, htmlPath] = process.argv.slice(2);
const { chromium } = await import(pathToFileURL(modulePath));
const browser = await chromium.launch({ headless: true });
const checks = [];
try {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const html = fs.readFileSync(htmlPath, 'utf8');
  await context.route('**/*', async route => {
    if (route.request().url() === 'https://founder-eval.invalid/' && route.request().isNavigationRequest()) {
      await route.fulfill({ status: 200, contentType: 'text/html', body: html, headers: {
        'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; form-action 'none'; frame-src 'none'; object-src 'none'",
      } });
    } else await route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  await page.goto('https://founder-eval.invalid/');
  const input = page.getByRole('textbox', { name: 'Task', exact: true });
  const add = page.getByRole('button', { name: 'Add', exact: true });
  await input.fill('Interview five founders');
  await add.click();
  await page.getByText('Interview five founders', { exact: true }).waitFor();
  checks.push('task-created');
  const checkbox = page.getByRole('checkbox', { name: 'Interview five founders', exact: true });
  await checkbox.check();
  if (!await checkbox.isChecked()) throw Error('completion failed');
  checks.push('task-completed');
  await page.reload();
  if (!await page.getByRole('checkbox', { name: 'Interview five founders', exact: true }).isChecked()) throw Error('persistence failed');
  checks.push('completion-persisted');
  const before = await page.getByRole('checkbox').count();
  await page.getByRole('textbox', { name: 'Task', exact: true }).fill('   ');
  await add.click();
  if (await page.getByRole('checkbox').count() !== before) throw Error('empty item accepted');
  checks.push('empty-task-rejected');
  await input.fill('<img src=x onerror=alert(1)>');
  await add.click();
  if (await page.locator('img').count()) throw Error('unsafe rendering');
  checks.push('input-rendered-as-text');
  process.stdout.write(JSON.stringify({ status: 'passed', checks, scope: 'isolated-local-browser' }));
} catch {
  process.stdout.write(JSON.stringify({ status: 'failed', checks, scope: 'isolated-local-browser' }));
  process.exitCode = 1;
} finally {
  await browser.close();
}
