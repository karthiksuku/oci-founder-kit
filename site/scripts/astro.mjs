import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Keep builds and local previews free of Astro usage telemetry as well as the site itself.
const child = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/astro/bin/astro.mjs', import.meta.url)), ...process.argv.slice(2)], {
  stdio: 'inherit',
  env: { ...process.env, ASTRO_TELEMETRY_DISABLED: '1' },
});
child.on('error', () => { process.stderr.write('Could not start Astro. Run npm ci with the supported Node version.\n'); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
