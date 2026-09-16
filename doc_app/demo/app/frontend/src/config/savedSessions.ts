/**
 * Saved sessions configuration — historical sessions available for replay.
 *
 * The actual demo session content is stored in Cosmos DB (TTL=-1) and
 * referenced here only by opaque session id. Hard rule (per data-boundary
 * mandate, 2026-05-01): no real station codes, dates, or operational
 * descriptors in this file. Labels and descriptions must be neutral; the
 * underlying Cosmos session may have any content but the demo dropdown
 * must not advertise it.
 *
 * To add a new saved session:
 *   1. Run a benchmark or use the app to create a session.
 *   2. Copy the session id from the benchmark output or Cosmos.
 *   3. Add an entry below with a generic label (`Scenario A`, `Scenario B`, …).
 */

export interface SavedSession {
  label: string;
  sessionId: string;
  description?: string;
  /** Situation scan parameters to auto-run when loading this session. */
  scanParams?: { start: string; end: string; station?: string };
}

// The placeholder list is empty by default. Operators populate it with
// generically-labelled entries pointing at Cosmos session ids; never
// embed real station codes / event times / descriptions here.
export const SAVED_SESSIONS: SavedSession[] = [];

/** Scan-only scenarios — populate situation alerts without loading a session. */
export interface ScanScenario {
  label: string;
  scanParams: { start: string; end: string };
}

export const SCAN_SCENARIOS: ScanScenario[] = [];
