/**
 * API client — typed fetch helpers + SSE streaming.
 *
 * Module role:
 *   The only module that makes HTTP requests to the backend. All API access
 *   goes through these exported functions. Provides:
 *     - Typed CRUD operations for session management
 *     - SSE streaming via fetch + ReadableStream (not EventSource)
 *     - AbortController support for user-initiated cancellation
 *
 * Design decisions:
 *   - All methods return typed responses or throw ApiError
 *   - Uses fetch + ReadableStream instead of EventSource because:
 *     (a) EventSource is GET-only; our chat endpoint requires POST
 *     (b) No native abort signal support in EventSource
 *     (c) Custom SSE event type parsing needed
 *   - Base URL from VITE_API_URL env var:
 *     dev:  http://localhost:9000/api (CORS handles cross-origin)
 *     prod: /api (same origin behind reverse proxy)
 *
 * Key collaborators:
 *   - api/types.ts           — all request/response types
 *   - stores/sessionStore.ts — calls session CRUD functions
 *   - stores/chatStore.ts    — calls streamChat for SSE streaming
 *
 * Dependents:
 *   Called by: sessionStore.ts, chatStore.ts exclusively
 */

import { getAccessToken } from "../auth";
import { BASE } from "@/foundation/constants";
import { msalInstance, authSetup } from "../auth/authConfig";

export { BASE };

// ── Auth session recovery ──────────────────────────────────────────────────

/**
 * Handle a 401 response by redirecting to the Entra login page.
 *
 * When the backend returns 401, the access token has expired and silent/popup
 * renewal already failed (getAccessToken tried both). Redirect the user to
 * the Entra login page so they can re-authenticate. After login, MSAL
 * redirects back to the app and restores the session.
 */
export function handleAuthExpired(): void {
  if (!msalInstance || !authSetup.useLogin) return;
  console.warn("[auth] Session expired — redirecting to login");
  msalInstance.loginRedirect({ scopes: authSetup.scopes ?? [] }).catch((err) => {
    console.error("[auth] loginRedirect failed:", err);
  });
}

// ── Auth + Context Headers ──────────────────────────────────────────────────

/**
 * Build auth + per-user identity headers for API requests.
 *
 * Attaches:
 *   - Authorization: Bearer <token>  (when Entra auth enabled)
 *   - X-User-Id: <uuid>             (when auth disabled — dev/demo identity)
 *   - X-User-Name: <name>           (when auth disabled — dev display name)
 *
 * In dev mode (no Entra auth), generates a random UUID per browser session
 * and stores it in sessionStorage. This gives each browser tab a distinct
 * user identity that persists across page navigations but clears on close.
 * When Entra auth is active, the real JWT provides identity instead.
 */
export async function authHeaders(): Promise<HeadersInit> {
  const headers: Record<string, string> = {};

  // Auth token (Entra ID)
  const token = await getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  } else {
    // No auth token — dev mode. Send a per-session user identity.
    // sessionStorage persists across navigations but clears on browser close.
    let devUserId = sessionStorage.getItem("dev_user_id");
    if (!devUserId) {
      devUserId = crypto.randomUUID();
      sessionStorage.setItem("dev_user_id", devUserId);
    }
    headers["X-User-Id"] = devUserId;
    headers["X-User-Name"] = `Dev-${devUserId.slice(0, 6)}`;
  }

  return headers;
}

// ── Error ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/**
 * Read a human-readable error message from a backend response body.
 *
 * R6 (inquisitor audit 2026-05-22) standardised the HTTP error envelope to
 * ``{detail: {error_code, message, ...extra}}``. Legacy router code (and a
 * handful of tests) still emit ``{detail: "<string>"}``. This helper accepts
 * either shape so the frontend toasts read correctly across the rollout.
 */
export function extractErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  }
  return fallback;
}

export async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401) {
      handleAuthExpired();
    }
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, extractErrorMessage(body, res.statusText));
  }
  return res.json();
}

// ── Barrel re-exports ───────────────────────────────────────────────────────
// Domain-specific API files. All endpoint functions live in their domain file.
// This barrel re-exports them so `import * as api from "@/api/client"` works.
export * from "./sessionApi";
export * from "./chatApi";
export * from "./agentApi";
export * from "./platformApi";
export * from "./summaryApi";
