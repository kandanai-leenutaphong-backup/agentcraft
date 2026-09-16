/**
 * helpers — the shared utilities every renderer needs, defined once.
 *
 * These four functions were each hand-rolled three or four times across the
 * renderer set before being pulled here, and every copy had drifted: one
 * formatted numbers with `toFixed(2)` and another with `toLocaleString`, one
 * treated `null` as an empty string and another as `"null"`. A table whose
 * cells format differently depending on which renderer drew it is a table
 * nobody trusts.
 */

/**
 * Parse a tool result string. Returns null when it is not JSON.
 *
 * Never throws: a renderer that throws takes the whole chat transcript with
 * it, and a malformed tool result is an expected event, not an exceptional
 * one.
 */
export function parseToolResult<T = Record<string, unknown>>(result: string): T | null {
  try {
    return JSON.parse(result) as T;
  } catch {
    return null;
  }
}

/**
 * Format one table cell.
 *
 * The canonical implementation. Integers get thousands separators because
 * counts are read at a glance; floats get four places because a rounded
 * measurement that hides its precision is worse than a long one; `null` gets
 * an em dash so an absent value is visibly absent rather than blank.
 */
export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "string") return value;
  const serialised = JSON.stringify(value);
  return serialised.length > 80 ? `${serialised.slice(0, 77)}…` : serialised;
}

/**
 * Extract the detail from a failure envelope, or null when there is none.
 *
 * Recognises the canonical `{error: true, detail}` plus two shapes that
 * predate it — a string `error`, and `status: "error"` — because a renderer
 * that misses a failure envelope renders it as an empty result, and an empty
 * result is the one thing an operator will not investigate.
 */
export function extractError(parsed: Record<string, unknown> | null): string | null {
  if (!parsed) return null;
  const status = typeof parsed.status === "string" ? parsed.status : null;
  const hasErrorFlag =
    parsed.error === true || (typeof parsed.error === "string" && parsed.error.length > 0);
  if (!hasErrorFlag && status !== "error") return null;
  if (typeof parsed.detail === "string" && parsed.detail.length > 0) return parsed.detail;
  if (typeof parsed.error === "string" && parsed.error.length > 0) return parsed.error;
  if (typeof parsed.note === "string" && parsed.note.length > 0) return parsed.note;
  return "The tool reported an error.";
}

/**
 * Extract a refusal, or null. Refusals are their own state: the call was
 * rejected at the input boundary and the caller was told what would work.
 *
 * Rendered as an amber note rather than a red banner, because a refusal is
 * the interface behaving correctly and an operator watching a transcript
 * should not read it as a fault (GOTCHAS.md G13).
 */
export function extractRefusal(
  parsed: Record<string, unknown> | null,
): { parameter: string; problem: string; accepted: string } | null {
  if (!parsed || parsed.refused !== true) return null;
  return {
    parameter: typeof parsed.parameter === "string" ? parsed.parameter : "input",
    problem: typeof parsed.problem === "string" ? parsed.problem : "rejected",
    accepted: typeof parsed.accepted === "string" ? parsed.accepted : "",
  };
}

/**
 * Extract a duplicate-call notice, or null. Also its own state: the answer
 * exists earlier in the transcript, and rendering it as an error would
 * suggest a retry — which is exactly what the guard prevented.
 */
export function extractDuplicate(
  parsed: Record<string, unknown> | null,
): { tool: string; detail: string } | null {
  if (!parsed || parsed.duplicate !== true) return null;
  return {
    tool: typeof parsed.tool === "string" ? parsed.tool : "tool",
    detail:
      typeof parsed.detail === "string"
        ? parsed.detail
        : "This call already ran with these arguments.",
  };
}

/** Scope entries, in declaration order, skipping the derived row count. */
export function scopeBadges(
  parsed: Record<string, unknown> | null,
): { label: string; value: string }[] {
  const scope = parsed?.scope;
  if (!scope || typeof scope !== "object" || Array.isArray(scope)) return [];
  return Object.entries(scope as Record<string, unknown>)
    .filter(([key, value]) => key !== "row_count" && value !== null && value !== "")
    .map(([label, value]) => ({ label, value: String(value) }));
}
