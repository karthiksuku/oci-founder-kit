import { spawnSync } from 'node:child_process';

const result = spawnSync(process.execPath, ['node_modules/next/dist/bin/next', 'build', '--webpack'], {
  env: { ...process.env, OCI_KIT_REFERENCE: '1', NEXT_TELEMETRY_DISABLED: '1' },
  stdio: 'inherit',
});
process.exit(result.status ?? 1);
