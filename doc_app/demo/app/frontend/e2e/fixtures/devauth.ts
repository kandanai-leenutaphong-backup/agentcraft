/**
 * Ed25519 request-signing Playwright fixture (Couturier-grade).
 *
 * Module role:
 *   Mirrors the operator-side signer in
 *   [scripts/dev_sign.py](../../../../scripts/dev_sign.py), so that an
 *   automated Playwright run signs every same-origin `/api/*` request
 *   to the deployed app with the operator's Ed25519 private key. The
 *   server-side verifier in
 *   [hosting/fastapi/devauth/_verifier.py](../../../../hosting/fastapi/devauth/_verifier.py)
 *   accepts the signature; the SPA reaches the authenticated shell
 *   without ever hitting `login.microsoftonline.com`.
 *
 *   This is the second consumer of the devauth wire format (the first
 *   is `dev_sign.py`). Both sides MUST stay in lockstep — see the
 *   "Wire format" section of
 *   [hosting/fastapi/devauth/README.md](../../../../hosting/fastapi/devauth/README.md).
 *
 * Constraints honoured (see `specs/couturier_20260515_first_run_chat.md` §R0):
 *   1. Uses Node's built-in `node:crypto` only — no `@noble/*`, no new
 *      devDependencies. Raw 32-byte Ed25519 private keys are loaded
 *      via the fixed PKCS8-DER prefix trick (documented below) so we
 *      never need to derive the public key client-side.
 *   2. `page.route` is hostname-scoped: only requests whose URL
 *      hostname equals the deployed app's hostname are signed.
 *      Cross-origin requests (Microsoft login, fonts, CDNs) are passed
 *      through unmodified.
 *   3. Refuses to run in CI unless `GRIDIQ_TEST_ALLOW_CI=1` is set —
 *      CI environments are not a place to ship a signing key.
 *   4. Refuses to dispatch a chat query not in
 *      ./synthetic_queries.ts (NDA protection).
 *   5. Does not persist storage state, cookies, or any browser state
 *      to disk. Ephemeral contexts only.
 *   6. Registers every session id it creates so callers can issue a
 *      signed `DELETE /api/sessions/{id}` in `afterEach`.
 *   8. Zero logging. No console.* anywhere in this file. The
 *      globalSetup in ./_globalSetup.ts greps for that and fails the
 *      suite if violated.
 *
 * The PKCS8-DER prefix:
 *   An Ed25519 private key in PKCS8 v1 DER form has a fixed 16-byte
 *   prefix followed by the 32-byte raw key:
 *     30 2e 02 01 00 30 05 06 03 2b 65 70 04 22 04 20 <32 raw bytes>
 *   This is the canonical encoding per RFC 8410 §7. Node's
 *   `crypto.createPrivateKey({ key: <DER>, format: 'der', type: 'pkcs8' })`
 *   accepts it and yields a `KeyObject` usable with `crypto.sign(null, ...)`.
 *   This avoids the JWK-format detour that would require knowing the
 *   public key upfront.
 */

import { Buffer } from "node:buffer";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { BrowserContext, Page } from "@playwright/test";
import { isSyntheticQuery } from "./synthetic_queries";

// ── Wire constants (mirror dev_sign.py / _verifier.py) ───────────────

// Header names MUST match server-side lookup in
// hosting/fastapi/devauth/_middleware.py (lowercase ASCII).
const TS_HEADER = "x-request-timestamp";
const SIG_HEADER = "x-request-signature";
const CTX_HEADER = "x-request-context";

// PKCS8 v1 DER prefix for a raw 32-byte Ed25519 private key (RFC 8410 §7).
// 16 bytes; immediately followed by the 32-byte raw key. Total 48 bytes.
// Forbidden to change — any drift breaks key loading silently.
const PKCS8_ED25519_PREFIX = Buffer.from(
  "302e020100300506032b657004220420",
  "hex",
);

// Operator's local key location. Identical to scripts/dev_sign.py.
const KEY_FILE = path.join(os.homedir(), ".gridiq", "dev_signing_key");

// ── CI refusal (constraint 3) ────────────────────────────────────────

/**
 * Throws if the process is running under CI without an explicit override.
 *
 * Exported so the fixture-isolation spec can exercise it directly,
 * without spawning a child process. Pure function over `process.env`.
 */
export function assertNotCiWithoutOverride(env: NodeJS.ProcessEnv): void {
  // The literal string "true" is what GitHub Actions / Azure DevOps /
  // most CI runners set CI to. We match that literal — not "1", not
  // "yes" — to keep the check narrow.
  if (env.CI === "true" && env.GRIDIQ_TEST_ALLOW_CI !== "1") {
    throw new Error(
      "couturier-devauth: refusing to run under CI without " +
        "GRIDIQ_TEST_ALLOW_CI=1. The fixture loads an Ed25519 private " +
        "key from the runner's filesystem; CI introduces the secret-in-" +
        "env vector that devauth was designed to retire. Run locally, " +
        "or set the override deliberately after reading the spec.",
    );
  }
}

// ── Key loading ──────────────────────────────────────────────────────

/**
 * Read the operator's private key from `~/.gridiq/dev_signing_key`,
 * validate file mode (0600 only — guards against accidental wide-open
 * copies, same posture as dev_sign.py), and return a Node KeyObject
 * usable with `crypto.sign(null, ...)`.
 *
 * Returns the KeyObject. Throws on any failure with a message that
 * names the file path and the next operator action — never logs.
 */
function loadPrivateKey(): crypto.KeyObject {
  if (!fs.existsSync(KEY_FILE)) {
    throw new Error(
      `couturier-devauth: no signing key at ${KEY_FILE}. ` +
        `Run \`python3 scripts/dev_sign.py init\` first, then re-push ` +
        `DEV_PUBLIC_KEY_ED25519 to the Container App (see AUTODEV.md §4.2).`,
    );
  }
  const st = fs.statSync(KEY_FILE);
  // Octal mask: world+group bits must be zero. Matches the dev_sign.py
  // (st.st_mode & 0o077) check.
  // eslint-disable-next-line no-bitwise
  if ((st.mode & 0o077) !== 0) {
    throw new Error(
      `couturier-devauth: refusing to read ${KEY_FILE}: mode is ` +
        `${(st.mode & 0o777).toString(8)}, expected 600. ` +
        `Fix with \`chmod 600 ${KEY_FILE}\`.`,
    );
  }
  const raw = fs.readFileSync(KEY_FILE);
  if (raw.length !== 32) {
    throw new Error(
      `couturier-devauth: ${KEY_FILE} is malformed ` +
        `(expected 32 bytes, got ${raw.length}).`,
    );
  }
  const der = Buffer.concat([PKCS8_ED25519_PREFIX, raw]);
  // `format: 'der', type: 'pkcs8'` is the documented path for raw
  // Ed25519 keys in Node 16+. No new dependency.
  return crypto.createPrivateKey({ key: der, format: "der", type: "pkcs8" });
}

// ── Canonical string + signing (mirror _verifier.py exactly) ─────────

/**
 * Build the canonical bytes to sign. Field order is fixed forever;
 * any change is a wire-incompatible break and requires rotating the
 * server-side public key in lockstep.
 *
 *   METHOD \n path_and_query \n timestamp \n context_slug \n sha256_hex(body)
 *
 * Both sides normalise `context_slug` to lowercase-stripped before
 * signing (see dev_sign.py `slug_norm` and _verifier.py).
 */
function canonical(args: {
  method: string;
  pathAndQuery: string;
  ts: string;
  contextSlug: string;
  body: Buffer;
}): Buffer {
  const bodySha = crypto.createHash("sha256").update(args.body).digest("hex");
  const text =
    `${args.method.toUpperCase()}\n` +
    `${args.pathAndQuery}\n` +
    `${args.ts}\n` +
    `${args.contextSlug}\n` +
    `${bodySha}`;
  return Buffer.from(text, "ascii");
}

/**
 * Produce the three (or two, if slug is empty) signing headers for
 * the given request shape. Returns lowercased header names — Playwright
 * normalises header names to lowercase on outgoing requests anyway, and
 * the server reads them case-insensitively.
 */
function signHeaders(args: {
  privateKey: crypto.KeyObject;
  method: string;
  pathAndQuery: string;
  body: Buffer;
  contextSlug: string;
}): Record<string, string> {
  // RFC 3339 UTC, second precision: `YYYY-MM-DDTHH:MM:SSZ`. Must
  // match `%Y-%m-%dT%H:%M:%SZ` from dev_sign.py exactly — including
  // the trailing `Z` and the absence of fractional seconds.
  const now = new Date();
  const ts = now.toISOString().replace(/\.\d{3}Z$/, "Z");
  const slug = (args.contextSlug ?? "").trim().toLowerCase();
  const msg = canonical({
    method: args.method,
    pathAndQuery: args.pathAndQuery,
    ts,
    contextSlug: slug,
    body: args.body,
  });
  // `null` algorithm for Ed25519: Node selects the curve from the key.
  const sig = crypto.sign(null, msg, args.privateKey);
  const headers: Record<string, string> = {
    [TS_HEADER]: ts,
    [SIG_HEADER]: sig.toString("base64"),
  };
  if (slug) {
    headers[CTX_HEADER] = slug;
  }
  return headers;
}

// ── Fixture surface ──────────────────────────────────────────────────

/**
 * Per-page fixture handle returned by `installDevauthFixture`. Tests
 * use it to (a) drive signed requests via `page.request` if they need
 * an out-of-band call, (b) register sessions for teardown, and
 * (c) dispatch the one synthetic query the smoke test exercises.
 */
export interface DevauthHandle {
  /** The signing context slug. Used by tests to filter sessions for cleanup. */
  readonly contextSlug: string;
  /** Session ids the fixture created or the test registered. */
  readonly registeredSessionIds: string[];
  /** Add a session id for `afterEach` teardown. */
  registerSession(id: string): void;
  /**
   * Issue a signed, out-of-band request via Playwright's `page.request`.
   * Bypasses the page route handler — uses the same private key, same
   * canonical string. Intended for `afterEach` cleanup of sessions
   * created during the test.
   */
  signedFetch(args: {
    method: string;
    path: string;
    body?: object;
  }): Promise<{ status: number; body: string }>;
  /**
   * Dispatch a chat query against an existing session id. Refuses if
   * the query is not in ./synthetic_queries.ts. Returns a summary of
   * the response surface (status, content-type, length of first SSE
   * chunk). Body is intentionally not returned — keeps NDA-restricted
   * answer text out of the test runner's report.
   */
  askQuery(args: {
    page: Page;
    sessionId: string;
    query: string;
  }): Promise<{ status: number; contentType: string; firstChunkLen: number }>;
}

/**
 * Install the devauth signing fixture on a Playwright page.
 *
 * Side effects:
 *   - Registers `page.route('**\u002fapi/**', ...)` that signs
 *     same-host requests via `route.fallback({ headers })`. Using
 *     `fallback` (not `continue`) lets a separately-registered
 *     observer route (e.g. in fixture_isolation.spec.ts) inspect the
 *     mutated headers before they go to the network.
 *   - Calls ./msalStub.ts is the caller's job (kept independent so a
 *     test can use one without the other).
 *
 * Returns a DevauthHandle.
 *
 * `appBaseUrl` defaults to Playwright's configured baseURL but tests
 * may pass an explicit URL.
 */
export async function installDevauthFixture(args: {
  page: Page;
  appBaseUrl: string;
  contextSlug?: string;
}): Promise<DevauthHandle> {
  // Constraint 3: refuse CI before doing anything else.
  assertNotCiWithoutOverride(process.env);

  const baseUrl = new URL(args.appBaseUrl);
  const appHost = baseUrl.hostname;
  // ISO 8601 with seconds, no colons (colons are fine for slug but we
  // strip them defensively for filename-safety in downstream tools).
  const slug =
    args.contextSlug ?? `couturier-${new Date().toISOString().replace(/[:.]/g, "-").toLowerCase()}`;
  const privateKey = loadPrivateKey();
  const registeredSessionIds: string[] = [];

  // ── Page-level signing route ──────────────────────────────────────
  await args.page.route("**/api/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    // Hostname-only scope (constraint 2). Anything that isn't the
    // deployed app — `login.microsoftonline.com`, fonts, CDNs, the
    // local Vite dev server if a test is misconfigured — passes
    // through unsigned.
    if (url.hostname !== appHost) {
      await route.fallback();
      return;
    }
    const method = req.method();
    // pathAndQuery: ASGI server reconstructs as `scope.path + "?" +
    // query_string`. For pure-ASCII paths (which is all of GridIQ's
    // /api surface) `url.pathname + url.search` is byte-equivalent.
    const pathAndQuery = url.pathname + url.search;
    // postDataBuffer() returns null for GET/DELETE with no body.
    const bodyBuf = req.postDataBuffer() ?? Buffer.alloc(0);
    const signed = signHeaders({
      privateKey,
      method,
      pathAndQuery,
      body: bodyBuf,
      contextSlug: slug,
    });
    // Preserve existing headers (Accept, Content-Type, etc.) and add
    // ours. Playwright lowercases header names on outgoing requests,
    // matching the server's lowercase lookup in _middleware.py.
    const merged = { ...req.headers(), ...signed };
    // `fallback` instead of `continue` lets observer routes registered
    // earlier (= run later in LIFO) see the mutated headers. In
    // production runs no such observer exists; fallback then goes to
    // the network unchanged.
    await route.fallback({ headers: merged });
  });

  // ── Out-of-band signed fetch (for afterEach DELETE etc.) ──────────
  const signedFetch: DevauthHandle["signedFetch"] = async ({
    method,
    path: p,
    body,
  }) => {
    const bodyBuf = body
      ? Buffer.from(JSON.stringify(body), "utf-8")
      : Buffer.alloc(0);
    const headers = signHeaders({
      privateKey,
      method,
      pathAndQuery: p,
      body: bodyBuf,
      contextSlug: slug,
    });
    const init: {
      method: string;
      headers: Record<string, string>;
      data?: Buffer;
    } = {
      method,
      headers: { "Content-Type": "application/json", ...headers },
    };
    if (body) {
      init.data = bodyBuf;
    }
    const res = await args.page.request.fetch(`${args.appBaseUrl}${p}`, init);
    const text = await res.text();
    return { status: res.status(), body: text };
  };

  // ── Synthetic-query dispatcher (constraint 4) ─────────────────────
  const askQuery: DevauthHandle["askQuery"] = async ({
    page,
    sessionId,
    query,
  }) => {
    if (!isSyntheticQuery(query)) {
      throw new Error(
        "couturier-devauth: refusing to dispatch a query not in the " +
          "synthetic allowlist. Add it to e2e/fixtures/synthetic_queries.ts " +
          "under review, or pick an existing entry. This guards against " +
          "NDA-restricted text leaking into screenshots and traces.",
      );
    }
    // Dispatch via the page so the signing route handler runs. We use
    // the page's `evaluate(fetch)` rather than `page.request.fetch` so
    // the request originates from the document context — matches how
    // the real SPA emits chat requests. We return a serialisable
    // summary (not a Response object — Response is not transferable
    // out of page.evaluate).
    return await page.evaluate(
      async ({ url, payload }) => {
        const r = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(payload),
        });
        const reader = r.body?.getReader();
        let firstChunkLen = 0;
        if (reader) {
          const { value } = await reader.read();
          firstChunkLen = value?.byteLength ?? 0;
          try {
            await reader.cancel();
          } catch {
            // best-effort; ignored
          }
        }
        return {
          status: r.status,
          contentType: r.headers.get("content-type") ?? "",
          firstChunkLen,
        };
      },
      {
        url: `/api/chat/${sessionId}`,
        payload: { content: query },
      },
    );
  };

  const handle: DevauthHandle = {
    contextSlug: slug,
    registeredSessionIds,
    registerSession(id: string): void {
      registeredSessionIds.push(id);
    },
    signedFetch,
    askQuery,
  };
  return handle;
}

// ── Storage-state persistence guard (constraint 5) ───────────────────

/**
 * Throws if a Playwright context has been persisted to disk under the
 * e2e/ directory. Called by ./_globalSetup.ts at suite teardown via
 * a globalTeardown hook. Pure I/O check — does not depend on any
 * particular fixture instance.
 *
 * Heuristic: storageState() JSON has `cookies` and `origins` top-level
 * keys. We scan only e2e/ — not test-results/, which is the gitignored
 * output dir where Playwright's own snapshot diffs may live.
 */
export function assertNoPersistedStorageState(e2eDir: string): void {
  const stack: string[] = [e2eDir];
  while (stack.length > 0) {
    const dir = stack.pop()!;
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const ent of entries) {
      const full = path.join(dir, ent.name);
      if (ent.isDirectory()) {
        // Skip node_modules and test-results — neither is part of the
        // e2e source tree and both are gitignored.
        if (ent.name === "node_modules" || ent.name === "test-results") {
          continue;
        }
        stack.push(full);
        continue;
      }
      if (!ent.name.endsWith(".json")) continue;
      // Cheap read — any storageState file is small (<10KB).
      let txt: string;
      try {
        txt = fs.readFileSync(full, "utf-8");
      } catch {
        continue;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(txt);
      } catch {
        continue;
      }
      if (
        parsed !== null &&
        typeof parsed === "object" &&
        "cookies" in parsed &&
        "origins" in parsed
      ) {
        throw new Error(
          `couturier-devauth: storageState-shaped JSON found at ${full}. ` +
            `Ephemeral browser contexts only — see R0 constraint 5.`,
        );
      }
    }
  }
}

// Re-export for tests / inspection. `BrowserContext` import kept so
// downstream test files can type their context arguments without
// pulling Playwright types again.
export type { BrowserContext };
