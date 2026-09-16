/**
 * BreakerFailSignatureResult — renders `breaker_fail_signature` inside
 * the ToolResultCard scaffold.
 *
 * Envelope (see specs/T-C6_breaker_fail_signature_20260518.md §3): an
 * object with `candidates: [...]` (descending by `cbf_score`, capped
 * at 30) plus `scope`, `anchor_kind`, `primitives_used` metadata.
 * Each candidate:
 *   {
 *     "equipment":                "<bay id>",
 *     "scada_cid":                "<composite id>",
 *     "cbf_score":                <0..1>,
 *     "modelled_open":            bool,
 *     "normal_open":              bool,
 *     "has_open_alarm_in_window": bool,
 *     "in_tripped_zone":          bool,
 *     "anchor_ts":                "<iso>",
 *     "reasoning":                "<one line>",
 *     "primitives_used":          [...]
 *   }
 *
 * Empty candidates is a legal "no CBF candidate" result and renders as
 * an info note rather than an empty table.
 *
 * Pre-2026-05-19 the tool returned a top-level array directly; the
 * renderer here accepts both shapes for back-compat.
 *
 * Layout:
 *   - signal band — candidate count + top score (tone scales with score).
 *   - body — per-candidate compact card (equipment id + score chip +
 *     three boolean state chips + 1-line reasoning).
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import type { SignalChip, SignalTone } from "./ToolResultCard";
import { JsonFallback } from "./JsonFallback";
import { extractError } from "./helpers";

interface Candidate {
  equipment?: string;
  scada_cid?: string;
  cbf_score?: number;
  modelled_open?: boolean;
  normal_open?: boolean;
  has_open_alarm_in_window?: boolean;
  in_tripped_zone?: boolean;
  reasoning?: string;
}

export function BreakerFailSignatureResult({ result }: ToolResultProps) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(result);
  } catch {
    return <JsonFallback result={result} />;
  }

  let candidates: Candidate[] = [];
  if (Array.isArray(parsed)) {
    /* Back-compat: pre-2026-05-19 the tool returned a top-level array. */
    candidates = parsed as Candidate[];
  } else if (parsed && typeof parsed === "object") {
    const obj = parsed as Record<string, unknown>;
    /* Object-wrapped error envelope still wins over the candidates path. */
    const errDetail = extractError(obj);
    if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;
    const c = obj.candidates;
    if (Array.isArray(c)) candidates = c as Candidate[];
    else {
      /* Unexpected shape — no candidates key, not an error — fall through. */
      return <JsonFallback result={result} />;
    }
  }

  if (candidates.length === 0) {
    return (
      <ToolResultCard
        signal={[{ label: "candidates", value: 0, tone: "success" }]}
        note="No breaker-fail candidates — clean protection operation."
        noteTone="info"
      />
    );
  }

  const topScore = candidates[0]?.cbf_score ?? 0;
  const signal: SignalChip[] = [
    {
      label: "candidates",
      value: candidates.length,
      tone: candidates.length > 0 ? "warning" : "neutral",
    },
    { label: "top score", value: topScore.toFixed(2), tone: scoreTone(topScore) },
  ];

  return (
    <ToolResultCard signal={signal}>
      <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto">
        {candidates.map((c, i) => (
          <CandidateCard key={`${c.equipment ?? "c"}-${i}`} candidate={c} />
        ))}
      </div>
    </ToolResultCard>
  );
}

/* Single-candidate compact card. Equipment id is the primary signal;
   score chip is colour-coded; the three booleans summarise the
   reasoning chain (modelled state · alarm history · zone membership). */
function CandidateCard({ candidate }: { candidate: Candidate }) {
  const score = candidate.cbf_score ?? 0;
  const tone = scoreTone(score);
  const chipClass = toneToChipClass(tone);

  return (
    <div className="rounded border border-border/60 bg-neutral-bg2/40 px-2 py-1.5">
      <div className="flex flex-wrap items-baseline gap-1.5 text-label">
        <span className="font-mono font-semibold text-text-primary">
          {candidate.equipment ?? "—"}
        </span>
        <span className={`rounded px-1.5 py-0.5 font-mono ${chipClass}`}>
          score {score.toFixed(2)}
        </span>
        <BoolChip
          label="modelled open"
          value={candidate.modelled_open}
          positive
        />
        <BoolChip
          label="no OPEN alarm"
          value={candidate.has_open_alarm_in_window === false}
          positive
        />
        <BoolChip
          label="in tripped zone"
          value={candidate.in_tripped_zone}
          positive
        />
      </div>
      {candidate.reasoning && (
        <p className="mt-1 text-label text-text-secondary leading-snug">
          {candidate.reasoning}
        </p>
      )}
    </div>
  );
}

/* Boolean indicator. `positive=true` means "true" is the suspicious
   signal (i.e. the chip lights up in warning tone when true). */
function BoolChip({
  label,
  value,
  positive,
}: {
  label: string;
  value: boolean | undefined;
  positive: boolean;
}) {
  const isHot = value === positive;
  const cls = isHot
    ? "bg-status-warning/10 text-status-warning"
    : "bg-neutral-bg3 text-text-muted";
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-label ${cls}`}>
      {isHot ? "✓" : "·"} {label}
    </span>
  );
}

function scoreTone(score: number): SignalTone {
  if (score >= 0.9) return "error";
  if (score >= 0.6) return "warning";
  if (score > 0) return "accent";
  return "neutral";
}

function toneToChipClass(tone: SignalTone): string {
  switch (tone) {
    case "error":
      return "bg-status-error/10 text-status-error";
    case "warning":
      return "bg-status-warning/10 text-status-warning";
    case "success":
      return "bg-status-success/10 text-status-success";
    case "accent":
      return "bg-accent/10 text-accent";
    default:
      return "bg-neutral-bg3 text-text-secondary";
  }
}
