// Rehearse the built standalone Next.js app on a private ephemeral loopback listener.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import net from 'node:net';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const mode = process.argv[2];
assert.ok(['a11y','browser'].includes(mode));
const portProbe = net.createServer().listen(0, '127.0.0.1');
await once(portProbe, 'listening');
const port = portProbe.address().port;
await new Promise(r => portProbe.close(r));
const root = fileURLToPath(new URL('../', import.meta.url));
const proc = spawn(process.execPath, ['.next/standalone/server.js'], {cwd:root,
  env:{PATH:process.env.PATH, NODE_ENV:'production', HOSTNAME:'127.0.0.1',
    NEXT_TELEMETRY_DISABLED:'1', PORT:String(port)}, stdio:'ignore'});
const origin = 'http://127.0.0.1:'+port;
let browser;
try {
  for (let i=0;i<100;i++) {
    if (proc.exitCode !== null) throw new Error('Build the standalone fixture before running its browser test.');
    if (await fetch(origin+'/healthz',{redirect:'error'}).then(r=>r.status===200).catch(()=>false)) break;
    await new Promise(r=>setTimeout(r,80));
  }
  browser = await chromium.launch();
  const context = await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*', r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  await page.goto(origin);
  await page.getByRole('article').filter({has:page.getByRole('heading',{name:'Build a useful prototype'})}).getByRole('link').click();
  const name = page.getByRole('textbox',{name:/Project name/});
  await name.fill('Example founder'); await name.press('Tab');
  assert.ok(await page.getByRole('button',{name:'Preview'}).evaluate(el=>document.activeElement===el));
  await page.keyboard.press('Enter');
  await page.waitForURL(url=>url.searchParams.get('project')==='Example founder');
  await page.reload();
  assert.equal(await page.locator('[data-project]').textContent(), 'Example founder');
  if (mode==='a11y') {
    await page.addScriptTag({path:createRequire(import.meta.url).resolve('axe-core/axe.min.js')});
    assert.deepEqual(await page.evaluate(async()=>(await axe.run(document,{runOnly:{type:'tag',
      values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})).violations.map(v=>v.id)), []);
  }
  console.log('Passed standalone local Next.js '+mode+' check.');
} finally {
  try { await browser?.close(); } finally {
    if (proc.exitCode===null && proc.signalCode===null) {
      const done=once(proc,'exit'); proc.kill('SIGTERM'); await done;
    }
  }
}
