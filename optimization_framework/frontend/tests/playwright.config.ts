import { defineConfig } from '@playwright/test';

const fixture = process.env.UI_FIXTURE === '1';
const baseURL = fixture ? 'http://127.0.0.1:19027' : process.env.TEST_BASE_URL;
if (!baseURL) throw new Error('Set TEST_BASE_URL to the parent-started integrated server, or run npm run test:fixture for labeled fixture coverage.');

export default defineConfig({
  testDir: '.',
  testMatch: fixture ? ['smoke.spec.ts', 'fixture.spec.ts'] : ['smoke.spec.ts'],
  outputDir: '../test-results',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 12000 },
  reporter: 'list',
  use: {
    baseURL,
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: fixture ? {
    command: 'node tests/fixture-server.mjs',
    cwd: new URL('..', import.meta.url).pathname,
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    timeout: 10000,
  } : undefined,
});