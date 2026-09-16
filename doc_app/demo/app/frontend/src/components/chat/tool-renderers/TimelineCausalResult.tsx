/**
 * TimelineCausalResult — renders `reconstruct_event_timeline_causal`
 * inside the ToolResultCard scaffold.
 *
 * Envelope (see specs/T-C1_reconstruct_event_timeline_causal_20260518.md §3):
 *   {
 *     "anchor":           { "ts", "kind", "source_tag", "source_label" }
 *                         | { "kind": "no_anchor" },
 *     "tag_distribution": { "<tag>": <count>, ... },
 *     "rows":             [ { "dt_seconds", "ts", "tag", "source",
 *                              "label", "equipment", "text" }, ... ],
 *     "primitives_used":  [ ... ]
 *   }
 *
 * Layout:
 *   - scope band — anchor.kind + anchor.ts (or "no_anchor" badge).
 *   - signal band — top 3 tag counts, tone-mapped to causal severity
 *     (`ANCHOR`/`isolating`/`initiating` = warning; `unreasonability` =
 *     error; rest = neutral or accent).
 *   - note — info banner when anchor.kind === "no_anchor".
 *   - body — `ResultTable` over rows, with the `tag` column made
 *     prominent so the eye lands on the causal classification first.
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import type { ScopeBadge, SignalChip, SignalTone } from "./ToolResultCard";
import { JsonFallback } from "./JsonFallback";
import { ResultTable } from "./ResultTable";
import { extractError, parseToolResult } from "./helpers";

interface TimelineRow {
  dt_seconds?: number;
  ts?: string;
  tag?: string;
  source?: string;
  label?: string;
  equipment?: string;
  text?: string;
}

interface TimelineEnvelope {
  anchor?: {
    ts?: string;
    kind?: string;
    source_tag?: string;
    source_label?: string;
  };
  tag_distribution?: Record<string, number>;
  rows?: TimelineRow[];
}

/* Tag → tone. Drives both the signal-band chip tone AND the row-level
   cell tone (consumed by the prominent-column table). Tags absent from
   this map fall through to "neutral". */
const TAG_TONE: Record<string, SignalTone> = {
  ANCHOR: "warning",
  initiating: "warning",
  isolating: "warning",
  "pre-anchor-flux": "accent",
  "state-change": "accent",
  responding: "accent",
  unreasonability: "error",
  "pre-event-state": "neutral",
  restoration: "success",
  "pre-event": "neutral",
  observation: "neutral",
};

/* Columns shown by default in the body table. Anything else (e.g. raw
   labels, internal source) toggles in behind the "show metadata" chip. */
const PROMINENT_TIMELINE_COLUMNS = ["dt_seconds", "ts", "tag", "equipment", "text"];

export function TimelineCausalResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<TimelineEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const anchor = parsed.anchor ?? {};
  const kind = typeof anchor.kind === "string" ? anchor.kind : "unknown";
  const isNoAnchor = kind === "no_anchor";

  const scope: ScopeBadge[] = [];
  scope.push({ label: "anchor", value: humanizeKind(kind) });
  if (!isNoAnchor && typeof anchor.ts === "string") {
    scope.push({ label: "at", value: anchor.ts });
  }
  if (!isNoAnchor && typeof anchor.source_tag === "string") {
    scope.push({ label: "tag", value: anchor.source_tag });
  }

  /* Signal — top 3 tag counts by magnitude. Ordering by count, not by
     dictionary order, so the operator's eye lands on whatever the
     timeline is dominated by. */
  const dist = parsed.tag_distribution ?? {};
  const topTags = Object.entries(dist)
    .filter(([, v]) => typeof v === "number" && v > 0)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .slice(0, 3);
  const signal: SignalChip[] = topTags.map(([tag, count]) => ({
    label: tag,
    value: count as number,
    tone: TAG_TONE[tag] ?? "neutral",
  }));

  const rows = Array.isArray(parsed.rows) ? parsed.rows : [];
  const note = isNoAnchor
    ? "No anchor event found in window — every row tagged 'observation'."
    : null;

  if (rows.length === 0) {
    return (
      <ToolResultCard scope={scope} signal={signal} note={note} noteTone="info">
        <div className="text-xs text-text-muted italic py-1">No timeline rows.</div>
      </ToolResultCard>
    );
  }

  /* Flatten rows into the table-primitive shape. Preserve ordering. */
  const headers = ["dt_seconds", "ts", "tag", "source", "label", "equipment", "text"];
  const tableRows = rows.map((r) => headers.map((h) => (r as Record<string, unknown>)[h]));

  return (
    <ToolResultCard scope={scope} signal={signal} note={note} noteTone="info">
      <ResultTable
        headers={headers}
        rows={tableRows}
        previewRows={6}
        prominentColumns={PROMINENT_TIMELINE_COLUMNS}
      />
    </ToolResultCard>
  );
}

function humanizeKind(kind: string): string {
  if (kind === "voltage_alarm") return "voltage alarm";
  if (kind === "first_cb_open") return "first CB open";
  if (kind === "no_anchor") return "none";
  return kind;
}
