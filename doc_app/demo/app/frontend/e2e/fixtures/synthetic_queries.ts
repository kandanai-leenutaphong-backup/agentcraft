/**
 * Synthetic-query allowlist for Couturier Playwright fixtures.
 *
 * Module role:
 *   The devauth fixture (./devauth.ts) refuses to dispatch any chat query
 *   that is not in this list. The allowlist exists to prevent automated
 *   UI runs from sending operator-typed queries containing real station
 *   codes, equipment ids, customer terms, or other NDA-restricted text
 *   into Playwright screenshots / traces / Azure OpenAI logs.
 *
 *   Every entry must be deliberately generic. If a future Couturier run
 *   needs a more specific query, add it here under review — do not
 *   bypass the allowlist.
 *
 * Why a frozen array, not a Set or a function:
 *   Membership is value-equality on the canonical string. The fixture
 *   compares verbatim — no normalisation, no trimming on the caller
 *   side. Operators see exactly what is sent.
 *
 * Enforcement:
 *   ./devauth.ts → askQuery(page, q) → throws if q ∉ SYNTHETIC_QUERIES.
 *   ../fixture_isolation.spec.ts exercises the refusal path.
 */

export const SYNTHETIC_QUERIES: readonly string[] = Object.freeze([
  // Architectural / topological questions phrased in pure abstract terms.
  "Describe the high-level shape of the grid topology data model in general terms.",
  "What categories of constraints does a generic RIT-T process consider, in textbook form?",
  // Process / methodology questions; no entity references.
  "Explain in general terms how a network service provider distinguishes credible from non-credible contingencies.",
  "Summarise the standard purpose of a situation-detector pipeline in a control-room support tool.",
  // Self-referential UX questions about the agent itself; cannot leak data.
  "List the broad categories of tools an agentic assistant in this product can call, without naming specific tools.",
  "What is the difference between a planning agent and an execution agent at a conceptual level?",
]);

/**
 * Predicate used by ./devauth.ts. Pure value-equality; no normalisation.
 * Callers MUST pass the exact string they pulled from SYNTHETIC_QUERIES.
 */
export function isSyntheticQuery(q: string): boolean {
  return SYNTHETIC_QUERIES.includes(q);
}
