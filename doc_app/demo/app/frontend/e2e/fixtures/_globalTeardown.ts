/**
 * Playwright globalTeardown for the Couturier devauth fixture.
 *
 * Verifies (R0 constraint 5) that no test wrote a Playwright
 * `storageState`-shaped JSON anywhere under `e2e/` — ephemeral
 * browser contexts only. Throws if anything is found, which fails
 * the suite even after every test passed.
 *
 * No logging. Pure I/O check.
 */

import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { assertNoPersistedStorageState } from "./devauth";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const E2E_DIR = path.resolve(HERE, "..");

export default async function globalTeardown(): Promise<void> {
  assertNoPersistedStorageState(E2E_DIR);
  await Promise.resolve();
}
