import { defineConfig } from "@playwright/test";

const APP_URL = process.env.APP_URL
  ?? "https://pathfinderiq-aemo.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io";

export default defineConfig({
  testDir: "./e2e",
  timeout: 300_000,
  expect: { timeout: 30_000 },
  retries: 0,
  /* Run benchmarks sequentially — parallel runs hit Azure OpenAI rate limits
     and compete for the same backend model, causing slower responses and
     false timeout failures. */
  workers: 1,
  /* Ops data protection: any screenshot / trace / video the Couturier
     R0 fixtures opt into MUST land here. `test-results/` is gitignored
     (see .gitignore frontend section). The Couturier globalSetup
     asserts this basename at startup — see
     app/frontend/e2e/fixtures/_globalSetup.ts. */
  outputDir: "test-results",
  /* Pre-flight: greps fixtures/ for `console.(log|debug|info)` and
     asserts outputDir resolves correctly. See R0 constraint 8 in
     specs/couturier_20260515_first_run_chat.md. */
  globalSetup: "./e2e/fixtures/_globalSetup.ts",
  /* Post-flight: scans e2e/ for storage-state JSON files. R0 constraint 5. */
  globalTeardown: "./e2e/fixtures/_globalTeardown.ts",
  use: {
    baseURL: APP_URL,
    headless: true,
    /* Defaults stay strict: no automatic screenshots, no traces, no
       video. Tests that need a single screenshot (e.g. R0 smoke spec)
       must opt in via `page.screenshot({path: testInfo.outputPath(...)})`
       which writes under outputDir above (gitignored). */
    screenshot: "off",
    trace: "off",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
  ],
});
