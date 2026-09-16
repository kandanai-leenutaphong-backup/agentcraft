/**
 * Shared Playwright fixtures for GridIQ e2e tests.
 *
 * Handles auth bypass: intercepts /api/auth_setup to return useLogin=false,
 * and injects X-Dev-Key header on all /api/* requests.
 */

import { test as base, expect, Page } from "@playwright/test";

const DEV_API_KEY = process.env.DEV_API_KEY
  ?? "***REMOVED***";

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    // 1. Intercept auth_setup to disable MSAL login — must be first
    await page.route("**/api/auth_setup", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ useLogin: false }),
      }),
    );

    // 2. Inject X-Dev-Key header on ALL other /api/* requests
    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/api/auth_setup")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ useLogin: false }),
        });
      }
      const headers = { ...route.request().headers(), "X-Dev-Key": DEV_API_KEY };
      route.continue({ headers });
    });

    await use(page);
  },
});

export { expect };
/**
 Stub doc */

/**
 * Unlock the kiosk passcode gate if it is present.
 *
 * Internal builds (deploy_kiosk_internal.sh) ship a client-side passcode
 * gate; the public build does not. Calling this after page.goto("/")
 * makes a spec work against both — it fills the code when the gate is
 * showing and no-ops otherwise. Central so every spec stays gate-agnostic.
 */
export async function unlockKioskGate(page: Page): Promise<void> {
  const code = page.getByPlaceholder("Access code");
  if (await code.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await code.fill(process.env.KIOSK_PASSWORD ?? "");
    await code.press("Enter");
  }
}
