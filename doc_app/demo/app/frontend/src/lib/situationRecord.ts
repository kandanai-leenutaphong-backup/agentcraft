/**
 * lib/situationRecord — wire-decoder helpers for SituationRecord JSON fields.
 *
 * The detector emits SituationRecord rows where several fields are
 * JSON-encoded strings (`affected_equipment`, `alarm_signals`,
 * `scada_signals`, `affected_tags`). Pre-hygiene, every consumer
 * re-implemented `(() => { try { JSON.parse(...) } catch { return [] } })()`
 * with subtle drift — some forgot `Array.isArray`, some treated
 * `alarm_signals` as either an array or an object inconsistently,
 * some returned `[]` where `{}` was correct. This module centralises
 * the decoder so the wire-string handling can be reasoned about as a
 * single piece of code.
 *
 * Defensive design: every helper accepts `null | undefined | string`
 * and returns the typed fallback on any failure mode (parse error,
 * shape mismatch, falsy input). The detector pipeline is the source of
 * truth for emit shape; the helpers exist for hand-edited fixtures,
 * legacy records, and SSE mid-stream partial frames.
 */

import type { AffectedEquipment, SignalEvidence, SituationRecord } from "@/api/situationApi";

/** Slice the `HH:MM` portion out of an ISO-ish timestamp.
 *
 * Accepts `YYYY-MM-DD HH:MM`, `YYYY-MM-DDTHH:MM:SS`, and any other
 * shape that contains a space or `T` separator followed by an
 * `HH:MM[:SS][...]` time. Returns the original string when no time
 * delimiter is found (defensive for hand-edited fixtures), and the
 * empty string when input is falsy. */
export function hhmm(ts: string | null | undefined): string {
  if (!ts) return "";
  const t = ts.includes("T") ? ts.split("T")[1] : ts.split(" ")[1];
  if (!t) return ts;
  return t.slice(0, 5);
}

/** Generic typed JSON parser with caller-supplied shape guard.
 *
 * Returns `fallback` on any of: falsy input, parse error, guard
 * rejection. The guard runs against `JSON.parse`'s unknown output, so
 * a caller demanding `T = number[]` still gets `fallback` if the
 * payload decodes to `{ "0": 1 }`. */
export function parseSituationJsonField<T>(
  raw: string | null | undefined,
  fallback: T,
  guard: (v: unknown) => v is T,
): T {
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw) as unknown;
    return guard(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

/** Affected-equipment JSON shape guard — array of objects each carrying
 *  at minimum an `equipment_id`. The detector emits this field as a
 *  JSON-encoded array; legacy records and some hand-edited fixtures
 *  carried it as the empty string or as a single object. */
function isAffectedEquipmentArray(v: unknown): v is AffectedEquipment[] {
  return Array.isArray(v);
}

/** Parse the `affected_equipment` JSON field defensively. Returns `[]`
 *  on any failure mode (falsy, malformed, non-array). */
export function parseAffectedEquipment(
  raw: string | null | undefined,
): AffectedEquipment[] {
  return parseSituationJsonField<AffectedEquipment[]>(raw, [], isAffectedEquipmentArray);
}

/** First affected equipment id for a situation, or `"—"` when nothing
 *  decodes cleanly. Used by the alerts-panel row brief — the row
 *  always renders a single equipment slot, so the helper collapses
 *  the multi-equipment case to the first entry by definition. */
export function firstEquipmentId(sit: SituationRecord): string {
  const eq = parseAffectedEquipment(sit.affected_equipment);
  return eq[0]?.equipment_id ?? "—";
}

/** Signal-counts guard — `alarm_signals` / `scada_signals` are
 *  JSON-encoded objects of `string -> number`. The guard rejects
 *  arrays so a hand-edited `"[1,2]"` cannot render as
 *  `0=1, 1=2`. */
function isSignalCountsObject(v: unknown): v is Record<string, number> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/** Parse a `*_signals` JSON field defensively. Returns `{}` on any
 *  failure mode. Pre-hygiene the SituationCard used a bare
 *  `JSON.parse(...) catch { return {} }` that would happily accept an
 *  array payload and render its indices as keys. */
export function parseSignalCounts(
  raw: string | null | undefined,
): Record<string, number> {
  return parseSituationJsonField<Record<string, number>>(raw, {}, isSignalCountsObject);
}

/** Affected-tags shape guard — the legacy detector emitted this field
 *  as a JSON-encoded array of strings. New records prefer
 *  `affected_equipment`; tags remain as a fallback for older windows. */
function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === "string");
}

/** Parse the legacy `affected_tags` JSON field defensively. */
export function parseAffectedTags(raw: string | null | undefined): string[] {
  return parseSituationJsonField<string[]>(raw, [], isStringArray);
}

/** Signal-evidence shape guard. The decoded payload must be an object
 *  carrying `alarm`, `scada`, and `patterns` sub-objects; we accept
 *  records missing any of the three by filling with `{}` in the parser
 *  so older situations (pre-rollout) and partial frames render cleanly. */
function isSignalEvidenceObject(v: unknown): v is Partial<SignalEvidence> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/** Parse the `signal_evidence` JSON field defensively. Returns a fully
 *  shaped `SignalEvidence` with empty sub-maps when any branch is
 *  missing. Wire-payload contract: see backend
 *  `tools/situations/detector/layers/signal_evidence.py`. */
export function parseSignalEvidence(raw: string | null | undefined): SignalEvidence {
  const empty: SignalEvidence = { alarm: {}, scada: {}, patterns: {} };
  const parsed = parseSituationJsonField<Partial<SignalEvidence>>(
    raw,
    empty,
    isSignalEvidenceObject,
  );
  return {
    alarm: parsed.alarm ?? {},
    scada: parsed.scada ?? {},
    patterns: parsed.patterns ?? {},
  };
}
