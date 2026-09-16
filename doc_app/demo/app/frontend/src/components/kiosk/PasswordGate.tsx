/**
 * PasswordGate — kiosk-only client-side passcode gate.
 *
 * Module role:
 *   Wraps the kiosk app with a single-field passcode prompt. When
 *   VITE_KIOSK_PASSWORD is empty (default), the gate is bypassed and
 *   children render directly — preserves the current open-access build
 *   behaviour for non-kiosk targets and for kiosk builds that skip the
 *   `--password` flag.
 *
 *   Security model:
 *     - Client-side only. The passcode is baked into the JS bundle at
 *       build time and is therefore visible to anyone who reads the
 *       source. This is intentional — the gate exists to deter
 *       drive-by access, not to enforce confidentiality. For real
 *       authn use Easy Auth or MSAL.
 *     - On success, sets localStorage["kiosk_unlocked"] = expected
 *       hash so the prompt does not reappear per browser. Rotating
 *       the password invalidates all existing unlocks because the
 *       expected hash changes.
 *     - No network calls — all comparison is in-process.
 *
 * Key collaborators:
 *   - foundation/constants.ts — IS_KIOSK flag
 *   - App.tsx — wraps <App /> in <PasswordGate /> at the kiosk level
 *
 * Dependents:
 *   Rendered by main.tsx via App.tsx.
 */

import { useCallback, useMemo, useState, type ReactNode } from "react";

/* Build-time-injected expected password. Empty string disables the gate. */
const EXPECTED_PASSWORD: string = (import.meta.env.VITE_KIOSK_PASSWORD as string | undefined) ?? "";

/* localStorage key holding the SHA-256 hex of the password the user
   entered successfully. Re-checked on each load against the current
   build's EXPECTED_PASSWORD hash so password rotation auto-invalidates
   stale unlocks. */
const STORAGE_KEY = "kiosk_unlocked_v1";

/**
 * Compute SHA-256 hex of a string using the SubtleCrypto API.
 *
 * Returned hex is lowercase. Used to (a) compare against any stored
 * unlock token, (b) derive the value to persist on success — never
 * stores the raw password in localStorage.
 */
async function sha256Hex(input: string): Promise<string> {
  const enc = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function PasswordGate({ children }: { children: ReactNode }) {
  /* Memoise the expected hash so we compute it once per mount.
     Promise resolution drives the initial unlocked check. */
  const expectedHashPromise = useMemo(() => sha256Hex(EXPECTED_PASSWORD), []);

  /* Initial unlocked state: synchronous best-effort check against
     localStorage. The async hash compare runs in an effect-style
     resolver below — but since both this and the stored token are
     SHA-256 hex of the same string, simple equality is sufficient. */
  const [unlocked, setUnlocked] = useState<boolean>(() => {
    if (!EXPECTED_PASSWORD) return true; // gate disabled
    try {
      return Boolean(window.localStorage.getItem(STORAGE_KEY));
    } catch {
      return false;
    }
  });

  /* Re-validate the persisted token against the current build's
     expected hash. If the build's password changed, the stored
     value will mismatch and we re-show the prompt. */
  useMemo(() => {
    if (!EXPECTED_PASSWORD || !unlocked) return;
    expectedHashPromise.then((expected) => {
      try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        if (stored !== expected) {
          window.localStorage.removeItem(STORAGE_KEY);
          setUnlocked(false);
        }
      } catch {
        /* localStorage unavailable — treat as locked. */
        setUnlocked(false);
      }
    });
  }, [expectedHashPromise, unlocked]);

  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  /* Form submit handler — validates input against the build-time
     password by comparing SHA-256 hex digests, then persists the
     hash to skip the prompt on subsequent loads. */
  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!input) return;
      setSubmitting(true);
      setError(null);
      try {
        const [expected, actual] = await Promise.all([
          expectedHashPromise,
          sha256Hex(input),
        ]);
        if (actual === expected) {
          try {
            window.localStorage.setItem(STORAGE_KEY, expected);
          } catch {
            /* localStorage write failed (private browsing) — accept the
               unlock for this session only; no persistence. */
          }
          setUnlocked(true);
        } else {
          setError("Incorrect passcode");
        }
      } finally {
        setSubmitting(false);
      }
    },
    [expectedHashPromise, input],
  );

  /* Bypass when no password is configured or after successful unlock. */
  if (!EXPECTED_PASSWORD || unlocked) {
    return <>{children}</>;
  }

  return (
    <div className="flex items-center justify-center h-screen w-screen bg-neutral-bg1">
      <form
        onSubmit={handleSubmit}
        className="flex flex-col items-center gap-5 p-10 rounded-xl border border-border bg-neutral-bg2 shadow-lg max-w-sm w-full"
      >
        <h1 className="text-xl font-bold text-text-primary">Kiosk</h1>
        <p className="text-sm text-text-muted text-center">
          Enter the access code to continue.
        </p>
        <input
          type="password"
          autoFocus
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            if (error) setError(null);
          }}
          placeholder="Access code"
          className={[
            "w-full px-3 py-2 rounded-md text-sm",
            "bg-neutral-bg1 border border-border text-text-primary",
            "focus:outline-none focus:ring-2 focus:ring-brand",
          ].join(" ")}
        />
        <button
          type="submit"
          disabled={submitting || !input}
          className={[
            "w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-colors",
            "bg-brand hover:bg-brand-hover text-on-accent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          ].join(" ")}
        >
          {submitting ? "Checking…" : "Unlock"}
        </button>
        {error && (
          <p className="text-xs text-status-error text-center">{error}</p>
        )}
      </form>
    </div>
  );
}
