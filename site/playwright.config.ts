import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  workers: 2,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4321/oci-founder-kit/',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
  },
  webServer: {
    command: 'npm run preview -- --port 4321 --ignore-lock',
    url: 'http://127.0.0.1:4321/oci-founder-kit/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
