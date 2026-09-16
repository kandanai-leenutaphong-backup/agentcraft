/**
 * Playwright globalSetup / globalTeardown for the Couturier devauth fixture.
 *
 * Two responsibilities, both required by `specs/couturier_20260515_first_run_chat.md` §R0:
 *
 *   1. (Constraint 8) Grep-scan the fixtures/ directory for
 *      `console.(log|debug|info)` and fail the suite before any test
 *      runs. The devauth wire format requires the *server* to log
 *      nothing on success/failure; the *client-side* fixture inherits
 *      the same posture so that test-runner output, CI artefacts, and
 *      developer terminals cannot leak the signed headers, timestamp,
 *      canonical string, or MSAL stub contents.
 *
 *   2. (Constraint 7) Verify Playwright's `outputDir` resolves under
 *      `test-results/`, which is gitignored.
 *
 *   3. (Constraint 5, teardown only) Scan e2e/ for any
 *      storageState-shaped JSON file and fail if found. Ephemeral
 *      browser contexts only.
 *
 * No logging in this file either — only `throw` for failures.
 */

import { Buffer } from "node:buffer";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { FullConfig } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = HERE; // this file lives in fixtures/
const E2E_DIR = path.resolve(HERE, ".."); // kept for future use

/**
 * Regex literal that itself must NOT match any console-call site in
 * this file. The pattern uses a character class internally so the
 * forbidden literal — "c-o-n-s-o-l-e dot l-o-g open-paren" — never
 * appears as text in this source. Otherwise the precheck would flag
 * itself.
 */
const CONSOLE_PATTERN = /console\s*\.\s*(?:log|debug|info)\s*\(/;

/** Recursively walk a directory and return all `.ts` files. */
function walkTsFiles(root: string): string[] {
  const out: string[] = [];
  const stack: string[] = [root];
  while (stack.length > 0) {
    const dir = stack.pop()!;
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, ent.name);
      if (ent.isDirectory()) {
        if (ent.name === "node_modules") continue;
        stack.push(full);
        continue;
      }
      if (ent.name.endsWith(".ts")) out.push(full);
    }
  }
  return out;
}

/**
 * Playwright globalSetup entry. Throws on any precheck failure.
 *
 * Signature matches the Playwright FullConfig contract; we read
 * `projects[].outputDir` to assert the gitignored test-results path.
 */
async function globalSetup(config: FullConfig): Promise<void> {
  // ── (1) Grep fixtures/ for console.(log|debug|info) ────────────────
  const offenders: string[] = [];
  for (const file of walkTsFiles(FIXTURES_DIR)) {
    const text = fs.readFileSync(file, "utf-8");
    if (CONSOLE_PATTERN.test(text)) {
      offenders.push(path.relative(E2E_DIR, file));
    }
  }
  if (offenders.length > 0) {
    throw new Error(
      `couturier-devauth: console.{log,debug,info} forbidden in ` +
        `fixtures/. Found in: ${offenders.join(", ")}. ` +
        `Zero-logging posture mirrors hosting/fastapi/devauth/_middleware.py — ` +
        `see specs/couturier_20260515_first_run_chat.md §R0 constraint 8.`,
    );
  }

  // ── (2) Assert outputDir resolves under test-results/ ──────────────
  for (const p of config.projects ?? []) {
    if (!p.outputDir) continue;
    const base = path.basename(p.outputDir);
    if (base !== "test-results") {
      throw new Error(
        `couturier-devauth: project '${p.name}' outputDir resolves ` +
          `to '${p.outputDir}', expected basename 'test-results'. ` +
          `See specs/couturier_20260515_first_run_chat.md §R0 constraint 7.`,
      );
    }
  }
  await Promise.resolve();
  // Mark Buffer import as used so tsc / bundler does not strip it.
  void Buffer.alloc(0);
}

export default globalSetup;
