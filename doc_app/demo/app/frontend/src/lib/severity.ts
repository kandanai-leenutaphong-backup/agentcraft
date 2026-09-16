/**
 * lib/severity — single source of truth for situation severity vocabulary.
 *
 * Two vocabularies live here, in this order:
 *   1. Raw 5-band detector output (`RawSeverity`): CRITICAL · MAJOR ·
 *      SERIOUS · INVESTIGATE · minor. Drives sort rank + per-record
 *      colour wash on the situation card.
 *   2. Operator-facing 4-bucket fold (`Bucket`): Critical · Major ·
 *      Minor · Suspect. Drives the alerts-panel filter pills and badges
 *      and the operating-state distribution legend.
 *
 * Before this module the same maps + ranks were duplicated across
 * SituationCard, SituationAlertsPanel, OperatingStatePanel,
 * situationStore, TopologyPanel, and escalationWatcher with subtle
 * drift in the unknown-band fallback (`?? 4`, `?? 99`, silent drop).
 * Hygiene candidate #1 collapsed them here so adding a new severity
 * band touches exactly one file.
 *
 * Unknown-band policy: an incoming raw string that does not match any
 * known band is treated as `minor` for rank purposes and as `Suspect`
 * for bucket purposes. The detector pipeline only ever emits the five
 * known bands, so the fallback exists for defensive UI rendering
 * (hand-edited fixtures, stale localStorage, future bands not yet
 * mapped client-side) — never as a normal code path.
 */

// Detector raw band — typed union, replaces `string` at consumer sites
// so the compiler catches typos at the consumer site instead of letting
// them silently fall through the unknown-band branch.
export type RawSeverity = "CRITICAL" | "MAJOR" | "SERIOUS" | "INVESTIGATE" | "minor";

// Canonical worst-first ordering. Sort key + iteration order both derive
// from this so the legend and the rank cannot drift out of sync.
export const SEVERITIES_BY_RANK: readonly RawSeverity[] = [
  "CRITICAL",
  "MAJOR",
  "SERIOUS",
  "INVESTIGATE",
  "minor",
] as const;

// Numeric rank (lower == worse). Derived from the tuple above so a
// re-ordering in one place propagates everywhere.
export const SEVERITY_RANK: Record<RawSeverity, number> = Object.fromEntries(
  SEVERITIES_BY_RANK.map((s, i) => [s, i]),
) as Record<RawSeverity, number>;

/** Resolve a rank for an arbitrary string. Unknown bands fall back to
 *  the last-rank slot (`minor`) — see the module-level note for the
 *  rationale. Use this everywhere a comparator previously wrote
 *  `SEVERITY_RANK[x] ?? 99` or `?? 4`. */
export function rankFor(raw: string): number {
  return SEVERITY_RANK[raw as RawSeverity] ?? SEVERITY_RANK.minor;
}

// Operator-facing 4-bucket fold. Collapses SERIOUS + INVESTIGATE into
// the single `Minor` bucket because operators framed the two as "look
// at it but not now" with no decision-shaping difference between them.
export type Bucket = "Critical" | "Major" | "Minor" | "Suspect";
export const BUCKETS: readonly Bucket[] = ["Critical", "Major", "Minor", "Suspect"] as const;

export const BUCKET_FROM_RAW: Record<RawSeverity, Bucket> = {
  CRITICAL: "Critical",
  MAJOR: "Major",
  SERIOUS: "Minor",
  INVESTIGATE: "Minor",
  minor: "Suspect",
};

/** Resolve the operator-facing bucket for any raw band string.
 *  Unknown raw bands collapse to `Suspect` — the same slot the legacy
 *  `minor` band occupies — so the operator never sees an unlabelled
 *  pill. */
export function bucketFor(raw: string): Bucket {
  return BUCKET_FROM_RAW[raw as RawSeverity] ?? "Suspect";
}

/* ── Tailwind class maps ──────────────────────────────────────────────
 * Naming convention (do not rename without updating consumers):
 *   SEVERITY_PILL          — strong fill, head-row severity pill.
 *                            `bg-situation-X text-situation-X-text`.
 *   SEVERITY_SURFACE       — `/10` wash for the card surface.
 *   SEVERITY_SWATCH        — solid bg only, distribution bar segment.
 *   BUCKET_FILTER_ACTIVE   — filter-pill styling when the bucket is
 *                            currently selected.
 *   BUCKET_BADGE           — per-row badge styling keyed by bucket.
 *   BUCKET_SWATCH          — solid bg only, bucket-grained distribution
 *                            bar segment (operating-state panel).
 * The strongest opinion across the four pre-merge panels:
 *   SituationCard.head pill — solid fill (SEVERITY_PILL preserves it).
 *   SituationCard.surface   — `/10` wash (SEVERITY_SURFACE preserves it).
 *   OperatingStatePanel bar — solid swatch (SEVERITY_SWATCH preserves it).
 *   SituationAlertsPanel    — `/20` bucket badge + filter pill.
 * All other variants the panels invented are dropped.
 */

export const SEVERITY_PILL: Record<RawSeverity, string> = {
  CRITICAL: "bg-situation-critical text-situation-critical-text",
  MAJOR: "bg-situation-major text-situation-major-text",
  SERIOUS: "bg-situation-serious text-situation-serious-text",
  INVESTIGATE: "bg-situation-investigate text-situation-investigate-text",
  minor: "bg-neutral-bg3 text-text-muted",
};

export const SEVERITY_SURFACE: Record<RawSeverity, string> = {
  CRITICAL: "bg-situation-critical/10",
  MAJOR: "bg-situation-major/10",
  SERIOUS: "bg-situation-serious/10",
  INVESTIGATE: "bg-situation-investigate/10",
  minor: "bg-neutral-bg2",
};

export const SEVERITY_SWATCH: Record<RawSeverity, string> = {
  CRITICAL: "bg-situation-critical",
  MAJOR: "bg-situation-major",
  SERIOUS: "bg-situation-serious",
  INVESTIGATE: "bg-situation-investigate",
  minor: "bg-neutral-bg3",
};

export const BUCKET_FILTER_ACTIVE: Record<Bucket, string> = {
  Critical: "bg-situation-critical/20 text-situation-critical border-situation-critical/40",
  Major: "bg-situation-major/20 text-situation-major border-situation-major/40",
  Minor: "bg-situation-serious/20 text-situation-serious border-situation-serious/40",
  Suspect: "bg-neutral-bg3 text-text-muted border-border",
};

export const BUCKET_BADGE: Record<Bucket, string> = {
  Critical: "bg-situation-critical/20 text-situation-critical",
  Major: "bg-situation-major/20 text-situation-major",
  Minor: "bg-situation-serious/20 text-situation-serious",
  Suspect: "bg-neutral-bg3 text-text-muted",
};

/** Bucket-keyed solid swatch — used by the operating-state distribution
 *  bar after the 2026-05-24 bucket-vocabulary migration. Inherits the
 *  same colour anchors as the raw `SEVERITY_SWATCH` so the eye still
 *  reads red→amber→yellow→neutral. */
export const BUCKET_SWATCH: Record<Bucket, string> = {
  Critical: "bg-situation-critical",
  Major: "bg-situation-major",
  Minor: "bg-situation-serious",
  Suspect: "bg-neutral-bg3",
};
