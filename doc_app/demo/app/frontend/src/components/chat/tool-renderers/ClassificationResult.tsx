/**
 * ClassificationResult — renders the `classify` panel-write tool result
 * inside the ToolResultCard scaffold.
 *
 * Envelope (see [tools/panels/_classify.py](../../../../../tools/panels/_classify.py)):
 *   {
 *     "tool": "classify",
 *     "panel": "event_classification",
 *     "status": "updated",
 *     "classification": {
 *       "verdict": "credible_event" | "non_credible_event"
 *                 | "non_event" | "indeterminate",
 *       "justification": "<1–3 sentences>",
 *       "sources": ["paws://...", "smirks://...", ...],
 *       "updated_at": "<iso>"
 *     }
 *   }
 *
 * Layout:
 *   - scope band — source identifiers (compact badges, max 4 visible).
 *   - signal band — single verdict chip, tone mapped to NER 4.2.3 severity
 *     (`non_credible_event`=error, `credible_event`=warning,
 *     `non_event`=success, `indeterminate`=neutral).
 *   - body — justification (muted secondary text) + sources overflow chip
 *     (if > 4 sources).
 *
 * Replaces the JsonFallback that previously rendered this envelope —
 * see specs/couturier_20260518_tool_renderers_phase1_and_naming.md R1.
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import type { ScopeBadge, SignalChip, SignalTone } from "./ToolResultCard";
import { JsonFallback } from "./JsonFallback";
import { extractError, parseToolResult } from "./helpers";

/* Verdict → human label + tone. Operator-facing strings stay short so
   the chip never wraps in the signal band. The tone mapping is set by
   NER 4.2.3 severity, not by alphabetical or arbitrary order. */
const VERDICT_PRESENT: Record<
  string,
  { label: string; tone: SignalTone }
> = {
  non_credible_event: { label: "Non-credible event", tone: "error" },
  credible_event: { label: "Credible event", tone: "warning" },
  non_event: { label: "Non-event", tone: "success" },
  indeterminate: { label: "Indeterminate", tone: "neutral" },
};

interface ClassificationEnvelope {
  classification?: {
    verdict?: string;
    justification?: string;
    sources?: unknown;
    updated_at?: string;
  };
}

export function ClassificationResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<ClassificationEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  /* Typed-error envelope short-circuit — pre-empts any partial parse
     of an `{error: true, detail}` payload from the tool guard. */
  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const cls = parsed.classification ?? {};
  const verdict = typeof cls.verdict === "string" ? cls.verdict : "";
  const present =
    VERDICT_PRESENT[verdict] ?? { label: verdict || "unknown", tone: "neutral" as SignalTone };
  const justification =
    typeof cls.justification === "string" ? cls.justification.trim() : "";
  const sources = Array.isArray(cls.sources)
    ? (cls.sources as unknown[]).filter((s): s is string => typeof s === "string" && s.length > 0)
    : [];

  /* Scope band — up to 4 sources as compact identifier badges so the
     operator can audit grounding at a glance. Overflow surfaces as a
     trailing chip rather than truncating silently. */
  const VISIBLE_SOURCES = 4;
  const scope: ScopeBadge[] = sources.slice(0, VISIBLE_SOURCES).map((s, i) => ({
    label: `src ${i + 1}`,
    value: s,
  }));
  if (sources.length > VISIBLE_SOURCES) {
    scope.push({ label: "more", value: `+${sources.length - VISIBLE_SOURCES}` });
  }

  const signal: SignalChip[] = [
    { label: "verdict", value: present.label, tone: present.tone },
  ];

  return (
    <ToolResultCard scope={scope.length > 0 ? scope : undefined} signal={signal}>
      {justification && (
        <p className="text-xs text-text-secondary leading-snug">{justification}</p>
      )}
      {!justification && (
        <p className="text-xs text-text-muted italic">No justification recorded.</p>
      )}
    </ToolResultCard>
  );
}
