/**
 * Playwright drives the production build through the backend, never the Vite
 * dev server: the artefact under test has to be the one that ships.
 *
 * The backend runs in fixture mode with the AZDATA coordinates stripped, so a
 * screenshot cannot pick up a real subscription's names from the shell. The
 * fixture estate is chosen so every status, every content kind and the 500
 * clamp are all reachable without a network.
 */
import { defineConfig, devices } from "@playwright/test";
import { env } from "node:process";

const PYTHON = env.RESOURCE_EXPLORER_PYTHON ?? "../.venv/bin/python";
const PORT = Number(env.RESOURCE_EXPLORER_TEST_PORT ?? 8099);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: BASE_URL,
    extraHTTPHeaders: { "X-MS-CLIENT-PRINCIPAL-ID": "fixture-operator" },
    trace: "off",
    colorScheme: "light",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "tablet",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "mobile",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        isMobile: false,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    command: `"${PYTHON}" -B ../scripts/fixture_server.py --port ${PORT}`,
    url: `${BASE_URL}/health/ready`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
