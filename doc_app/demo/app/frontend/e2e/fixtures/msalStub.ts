/**
 * MSAL client-side stub for Playwright fixtures.
 *
 * Module role:
 *   The GridIQ SPA's [AuthProvider.tsx](../../src/auth/AuthProvider.tsx)
 *   short-circuits the MSAL wrapper when `authSetup.useLogin === false`:
 *
 *       if (!authSetup.useLogin || !msalInstance) { return <>{children}</>; }
 *
 *   `authSetup` is populated by a fetch to `/api/auth_setup` (see
 *   [authConfig.ts](../../src/auth/authConfig.ts)). Therefore the minimal
 *   stub that bypasses LoginScreen is: intercept that one request and
 *   return `{ useLogin: false }`. No localStorage seeding, no token
 *   minting, no MSAL state injection — the provider never instantiates
 *   MSAL in this mode, so there is nothing to seed.
 *
 *   This stub is paired with the Ed25519 signing fixture in
 *   ./devauth.ts; together they let an automated UI run reach the
 *   authenticated shell and send signed `/api/*` requests, without ever
 *   touching `login.microsoftonline.com` or storing a real bearer token.
 *
 * Why a separate file:
 *   Keeps the auth-bypass surface visible as its own primitive. A
 *   reviewer can see "MSAL bypass" and "request signing" as two
 *   independent moves, and a future test that needs only one can import
 *   only that one.
 *
 * No logging:
 *   Mirrors the zero-logging discipline of
 *   [hosting/fastapi/devauth/_middleware.py](../../../../hosting/fastapi/devauth/_middleware.py).
 *   No console.log / debug / info / warn / error anywhere in this file.
 */

import type { Page } from "@playwright/test";

/**
 * Install the MSAL stub on a Playwright page.
 *
 * Must be called BEFORE `page.goto()` — Playwright `page.route`
 * handlers only apply to subsequent navigation requests, not in-flight
 * ones.
 *
 * Idempotent: calling twice on the same page leaves a single effective
 * handler (the second route handler shadows the first in LIFO order;
 * both fulfill the same body).
 */
export async function installMsalStub(page: Page): Promise<void> {
  // Glob matches the relative `/api/auth_setup` path on the app
  // hostname and the absolute form the SPA may emit. We do not scope
  // by hostname here because `/api/auth_setup` is only ever called by
  // the SPA against its own origin; any external domain hitting that
  // path is suspicious and we let it pass to the network where it
  // will fail naturally.
  await page.route("**/api/auth_setup", async (route) => {
    // Fulfill directly — no need to round-trip the backend; the SPA
    // only reads `useLogin`. We omit the optional `msalConfig` field
    // because `useLogin=false` causes AuthProvider to skip MSAL
    // entirely (see file header).
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ useLogin: false }),
    });
  });
}
