import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const site = fileURLToPath(new URL('../', import.meta.url));
const repo = path.dirname(site.replace(/\/$/, ''));
const html = fs.readFileSync(path.join(site, 'dist/index.html'), 'utf8');

test('every generated link into the kit resolves to a real repository file', () => {
  const prefix = 'https://github.com/karthiksuku/oci-founder-kit/blob/main/';
  const links = [...html.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
  const docs = links.filter(link => link.startsWith(prefix));
  assert.ok(docs.length >= 20, 'Expected the generated documentation navigation');
  for (const link of docs) {
    const relative = decodeURIComponent(link.slice(prefix.length).split('#')[0]);
    const target = path.resolve(repo, relative);
    assert.ok(target.startsWith(repo + path.sep));
    assert.ok(fs.statSync(target).isFile(), `Missing linked file: ${relative}`);
  }
});

test('built static assets use the configured Pages base and carry the font license', () => {
  for (const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)) {
    const url = match[1];
    if (url.startsWith('http')) continue;
    assert.ok(url.startsWith('/oci-founder-kit/'), `Unexpected asset base: ${url}`);
    const local = url.slice('/oci-founder-kit/'.length);
    assert.ok(fs.statSync(path.join(site, 'dist', local)).isFile(), `Missing built asset: ${local}`);
  }
  const license = fs.readFileSync(path.join(site, 'dist/licenses/manrope-OFL.txt'), 'utf8');
  assert.match(license, /SIL OPEN FONT LICENSE/);
  assert.match(license, /Manrope Project Authors/);
});
