/**
 * BusZoneAuditResult — renders `bus_zone_audit` inside the
 * ToolResultCard scaffold.
 *
 * Envelope (see specs/T-C3_bus_zone_audit_20260518.md §3):
 *   {
 *     "verdict":            "bus_event" | "no_bus_event",
 *     "bus_tag":            "<full path>",
 *     "bus_id":             "<short id>",
 *     "anchor_ts":          "<iso>",
 *     "station_switch_count": <int>,
 *     "breaker_count":      <int>,
 *     "zone_bays":          [ ... ],
 *     "tripped_in_zone":    [ ... ],
 *     "out_of_zone_trips":  [ ... ],
 *     "adjacency_gaps":     [ ... ],   // CBF candidates
 *     "primitives_used":    [ ... ]
 *   }
 *
 * Layout:
 *   - scope band — bus_id + anchor_ts (or "no bus event" badge).
 *   - signal band — breaker_count, tripped_in_zone count, adjacency_gaps
 *     count (warning tone when > 0, since each is a breaker-fail candidate).
 *   - body — four labelled chip rows (zone_bays / tripped_in_zone /
 *     out_of_zone_trips / adjacency_gaps).
 *
 * `verdict === "no_bus_event"` short-circuits to a single info note
 * with no body — the absence-of-signal IS the result.
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import type { ScopeBadge, SignalChip } from "./ToolResultCard";
import { JsonFallback } from "./JsonFallback";
import { extractError, parseToolResult } from "./helpers";

interface BusZoneEnvelope {
  verdict?: string;
  bus_id?: string;
  bus_tag?: string;
  anchor_ts?: string;
  breaker_count?: number;
  station_switch_count?: number;
  zone_bays?: string[];
  tripped_in_zone?: string[];
  out_of_zone_trips?: string[];
  adjacency_gaps?: string[];
}

export function BusZoneAuditResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<BusZoneEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const verdict = parsed.verdict ?? "unknown";

  if (verdict === "no_bus_event") {
    return (
      <ToolResultCard
        signal={[{ label: "verdict", value: "no bus event", tone: "neutral" }]}
        note="No bus collapse detected in the window. Investigate elsewhere."
        noteTone="info"
      />
    );
  }

  const scope: ScopeBadge[] = [];
  if (typeof parsed.bus_id === "string") scope.push({ label: "bus", value: parsed.bus_id });
  if (typeof parsed.anchor_ts === "string") scope.push({ label: "anchor", value: parsed.anchor_ts });
  if (typeof parsed.bus_tag === "string" && parsed.bus_tag !== parsed.bus_id) {
    scope.push({ label: "path", value: parsed.bus_tag });
  }

  const gaps = Array.isArray(parsed.adjacency_gaps) ? parsed.adjacency_gaps : [];
  const tripped = Array.isArray(parsed.tripped_in_zone) ? parsed.tripped_in_zone : [];
  const oozTrips = Array.isArray(parsed.out_of_zone_trips) ? parsed.out_of_zone_trips : [];
  const zoneBays = Array.isArray(parsed.zone_bays) ? parsed.zone_bays : [];

  const signal: SignalChip[] = [
    { label: "verdict", value: "bus event", tone: "warning" },
    { label: "breakers", value: parsed.breaker_count ?? 0, tone: "neutral" },
    { label: "tripped", value: tripped.length, tone: tripped.length > 0 ? "warning" : "neutral" },
    {
      label: "CBF candidates",
      value: gaps.length,
      tone: gaps.length > 0 ? "error" : "success",
    },
  ];

  return (
    <ToolResultCard scope={scope} signal={signal}>
      <div className="flex flex-col gap-1.5">
        <EquipmentRow label="zone bays" items={zoneBays} tone="neutral" />
        <EquipmentRow label="tripped in zone" items={tripped} tone="warning" />
        <EquipmentRow
          label="out of zone trips"
          items={oozTrips}
          tone={oozTrips.length > 0 ? "warning" : "neutral"}
          emptyText="none"
        />
        <EquipmentRow
          label="adjacency gaps (CBF candidates)"
          items={gaps}
          tone="error"
          emptyText="none"
        />
      </div>
    </ToolResultCard>
  );
}

/* Inline equipment-id chip row. Compact + monospaced because every
   chip is a CIM bay identifier the operator may copy-paste downstream. */
function EquipmentRow({
  label,
  items,
  tone,
  emptyText,
}: {
  label: string;
  items: string[];
  tone: "neutral" | "warning" | "error";
  emptyText?: string;
}) {
  const chipClass =
    tone === "error"
      ? "bg-status-error/10 text-status-error"
      : tone === "warning"
      ? "bg-status-warning/10 text-status-warning"
      : "bg-neutral-bg3 text-text-secondary";
  return (
    <div className="flex flex-wrap items-baseline gap-1.5 text-label">
      <span className="text-text-muted shrink-0 min-w-[10em]">{label}:</span>
      {items.length === 0 ? (
        <span className="text-text-muted italic">{emptyText ?? "—"}</span>
      ) : (
        items.map((it, i) => (
          <span
            key={`${it}-${i}`}
            className={`rounded px-1.5 py-0.5 font-mono ${chipClass}`}
          >
            {it}
          </span>
        ))
      )}
    </div>
  );
}
