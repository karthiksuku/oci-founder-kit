// Actual production HTTP/auth code over loopback TLS; synthetic stores/sessions only.
// This fixture proves runner behavior, not hosted OIDC, PostgreSQL or OCI services.
import https from 'node:https';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHmac, randomBytes } from 'node:crypto';
import { createApp } from '../../blueprints/fullstack-container/app/src/app.js';
import { createAuth, ownerKey } from '../../blueprints/fullstack-container/app/src/auth.js';
import { MemoryTaskStore, FakeAttachmentStore } from '../../blueprints/fullstack-container/app/test/fakes.js';

const require = createRequire(new URL('../../blueprints/fullstack-container/app/package.json', import.meta.url));
const session = require('express-session');
const oidc = await import(require.resolve('openid-client'));
const [keyPath, certPath, readyPath, finalPath, fault] = process.argv.slice(2);
const server = https.createServer({ key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) });
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `https://127.0.0.1:${server.address().port}`;
const secret = randomBytes(48).toString('base64url');
const issuer = 'https://synthetic-identity.example.invalid';
const config = { mode: 'production', publicOrigin: origin, sessionSecret: secret, maxUploadBytes: 1024, trustProxy: false };
const store = new session.MemoryStore();
const tasks = new MemoryTaskStore();
const attachments = new FakeAttachmentStore();
const foreign = await tasks.create('Synthetic untouched control', 'different-owner');
const auth = await createAuth({ config, store, oidcConfiguration: new oidc.Configuration({ issuer,
  authorization_endpoint: `${issuer}/authorize`, token_endpoint: `${issuer}/token`, jwks_uri: `${issuer}/jwks`,
  response_types_supported: ['code'], id_token_signing_alg_values_supported: ['RS256'],
  token_endpoint_auth_methods_supported: ['client_secret_post'] }, 'synthetic-client', randomBytes(32).toString('hex')) });
if (fault === 'missing-csrf-control') auth.csrf = (_req, _res, next) => next();
const users = {};
for (const name of ['a', 'b']) {
  const id = randomBytes(32).toString('hex');
  await new Promise((resolve, reject) => store.set(id, {
    cookie: { originalMaxAge: 1800000, expires: new Date(Date.now() + 1800000),
      secure: true, httpOnly: true, sameSite: 'lax', path: '/' },
    user: { owner: ownerKey(issuer, name), expiresAt: Date.now() + 1800000 },
    csrf: randomBytes(32).toString('base64url'),
  }, err => err ? reject(err) : resolve()));
  const signature = createHmac('sha256', secret).update(id).digest('base64').replace(/=+$/, '');
  users[name] = '__Host-taskboard=' + encodeURIComponent(`s:${id}.${signature}`);
}
const app = createApp({ tasks, attachments, config, auth });
server.on('request', (req, res) => {
  if (fault === 'redirect-ready' && req.url === '/readyz') {
    res.writeHead(302, { location: 'https://uncontacted.example.invalid/readyz' }); res.end(); return;
  }
  if (fault === 'oversize-ready' && req.url === '/readyz') {
    res.end('x'.repeat(70000)); return;
  }
  if (fault === 'slow-ready' && req.url === '/readyz') {
    const timer = setTimeout(() => res.end('{}'), 20000); timer.unref();
    res.on('close', () => clearTimeout(timer)); return;
  }
  app(req, res);
});
fs.writeFileSync(readyPath, JSON.stringify({ schema: 'oci-production-sessions/1', origin, users }), { mode: 0o600 });
process.stdin.resume();
process.stdin.once('end', async () => {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  fs.writeFileSync(finalPath, JSON.stringify({ remainingRows: tasks.rows.size,
    foreignUnchanged: (await tasks.get(foreign.id, 'different-owner'))?.title === foreign.title,
    retainedObjects: attachments.objects.size, parCreated: attachments.lastUpload !== null }), { mode: 0o600 });
});
