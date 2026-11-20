// Owned ephemeral UI with the real app and a disposable in-memory store. No cloud, identities or external hosts.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { once } from 'node:events';
import { chromium } from 'playwright';
import { createApp } from '../src/app.js';
import { MemoryTaskStore } from '../test/fakes.js';

const mode = process.argv[2];
assert.ok(['browser','a11y'].includes(mode));
const app = createApp({ tasks: new MemoryTaskStore(), attachments: null,
  config: {mode:'sandbox', maxUploadBytes:1024} });
const server = app.listen(0, '127.0.0.1');
await once(server, 'listening');
const origin = 'http://127.0.0.1:' + server.address().port;
let browser;
try {
  browser = await chromium.launch();
  const context = await browser.newContext({serviceWorkers:'block', bypassCSP:mode === 'a11y'});
  await context.route('**/*', route => new URL(route.request().url()).origin === origin
    ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  await page.goto(origin);
  const input = page.getByRole('textbox',{name:'New task'});
  await input.waitFor();
  await input.fill('Rehearsal task');
  await input.press('Tab');
  assert.equal(await page.getByRole('button',{name:'Add',exact:true}).evaluate(el => el === document.activeElement), true);
  await page.keyboard.press('Enter');
  const checkbox = page.getByRole('checkbox',{name:'Mark "Rehearsal task" done'});
  await checkbox.waitFor();
  await Promise.all([page.waitForResponse(r => r.request().method() === 'PATCH' && r.status() === 200), checkbox.check()]);
  await page.reload();
  await checkbox.waitFor();
  assert.equal(await checkbox.isChecked(), true);
  if (mode === 'a11y') {
    await page.addScriptTag({path:createRequire(import.meta.url).resolve('axe-core/axe.min.js')});
    const ids = await page.evaluate(async () => (await axe.run(document, {runOnly: {type:'tag',
      values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})).violations.map(issue => issue.id));
    assert.deepEqual(ids, [], 'Accessibility violations: '+ids.join(', '));
  }
  console.log('Passed local Taskboard '+mode+' rehearsal. Hosted identity and real storage were not tested.');
} finally {
  try { await browser?.close(); } finally { server.closeAllConnections(); await new Promise(r => server.close(r)); }
}
