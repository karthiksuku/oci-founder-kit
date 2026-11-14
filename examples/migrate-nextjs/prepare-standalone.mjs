import { cpSync } from 'node:fs';

// Next.js intentionally leaves these assets out of its traced server output.
cpSync('public', '.next/standalone/public', { recursive: true });
cpSync('.next/static', '.next/standalone/.next/static', { recursive: true });
