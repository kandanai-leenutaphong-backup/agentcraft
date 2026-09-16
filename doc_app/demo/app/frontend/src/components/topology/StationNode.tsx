/**
 * StationNode — one station card in the topology map.
 *
 * Layout:
 *   Header row:   severity dot / station code / region / neighbor badge.
 *   Equipment:    grouped by nominal_kv descending, collapsible.
 *   Click header: re-centers the map on this station (via onRecenter).
 *
 * The center vs neighbor distinction is purely visual — both variants use
 * the same component with a `variant` prop.
 */

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Network, MapPin, GitBranch, Loader2 } from "lucide-react";
import type { TopologyStation } from "@/api/topologyApi";
import { useVocab } from "@/stores/vocabularyStore";
import { EquipmentRow } from "./EquipmentRow";

interface StationNodeProps {
  station: TopologyStation;
  variant: "center" | "neighbor";
  /** Set of equipment IDs currently alarmed. Matching rows get red styling. */
  alarmedIds: Set<string>;
  /** Severity label used to drive the halo ring around the center. */
  overlaySeverity: string | null;
  /** Called when the operator clicks the station header on a neighbor. */
  onRecenter?: (stationCode: string) => void;
  /** Called when the operator clicks the "expand neighbors" button on a
   *  neighbor card. Fetches the station's own 1-hop neighbors and merges
   *  them into the current graph without changing the center. */
  onExpand?: (stationCode: string) => void;
  /** True once the station's 1-hop fan-out has been merged into the
   *  graph — the button becomes a passive marker and no longer fires. */
  isExpanded?: boolean;
  /** True while the expand request is in flight. Shows a spinner instead
   *  of the branch icon and disables the button. */
  isExpanding?: boolean;
}

const SEVERITY_RING: Record<string, string> = {
  CRITICAL: "ring-2 ring-situation-critical/70",
  MAJOR: "ring-2 ring-situation-major/70",
  SERIOUS: "ring-2 ring-situation-serious/70",
  INVESTIGATE: "ring-2 ring-situation-investigate/70",
  minor: "ring-2 ring-neutral-bg3",
};

/** Group equipment by the domain grouping dimension (energy: voltage
 *  tier) for collapsible display. When `groupUnit` is empty the domain
 *  has no grouping concept, so all equipment falls into a single
 *  header-less bucket. */
function groupByVoltage(station: TopologyStation, groupUnit: string) {
  const groups = new Map<string, typeof station.equipment>();
  for (const equip of station.equipment) {
    const key = !groupUnit
      ? ""
      : equip.nominal_kv != null ? `${equip.nominal_kv.toFixed(0)} ${groupUnit}` : `unknown ${groupUnit}`;
    const bucket = groups.get(key) ?? [];
    bucket.push(equip);
    groups.set(key, bucket);
  }
  /* Order by voltage descending. Unknown last. */
  return Array.from(groups.entries()).sort((a, b) => {
    const av = parseFloat(a[0]) || -1;
    const bv = parseFloat(b[0]) || -1;
    return bv - av;
  });
}

export function StationNode({
  station, variant, alarmedIds, overlaySeverity, onRecenter,
  onExpand, isExpanded, isExpanding,
}: StationNodeProps) {
  const anyAlarmed = useMemo(
    () => station.equipment.some((e) =>
      alarmedIds.has(e.scada_composite_id) || alarmedIds.has(e.equipment),
    ),
    [station.equipment, alarmedIds],
  );

  /* Domain vocabulary — units and the equipment-grouping dimension are
     fully scenario-controlled so the map reads natively per industry. */
  const primaryUnit = useVocab("primaryUnit");
  const frequencyUnit = useVocab("frequencyUnit");
  const frequencyNominal = useVocab("frequencyNominal");
  const equipmentGroupUnit = useVocab("equipmentGroupUnit");

    /* Center station starts open because its equipment and voltage groups are
      the primary map payload; neighbors remain collapsed until inspected. */
    const [open, setOpen] = useState(variant === "center");

  /* Alarm halo only applies when the situation overlay is active and some
     equipment on this station matched. Non-center stations also show a
     halo when any of their equipment is alarmed. */
  const halo = anyAlarmed && overlaySeverity
    ? (SEVERITY_RING[overlaySeverity] ?? "ring-2 ring-situation-investigate/60")
    : "";

  const voltageGroups = groupByVoltage(station, equipmentGroupUnit);

  const Icon = variant === "center" ? Network : MapPin;

  /* Live-summary badges — only rendered when the backend attached a
     live_summary block and at least one field is non-null. Each metric
     is independently optional so a station with only MW cap still shows
     its capacity without pretending to have live output or frequency. */
  const live = station.live_summary ?? null;
  const hasLive = !!live && (
    live.mw_output != null || live.mw_cap != null || live.freq != null
  );

  const headerIsButton = variant === "neighbor" && !!onRecenter;

  const headerContent = (
    <>
      <Icon className="h-3.5 w-3.5 shrink-0 text-brand" />
      <span className="font-mono font-bold text-sm text-text-primary truncate">
        {station.station}
      </span>
      {station.region && station.region !== "UNKNOWN" && (
        <span className="shrink-0 text-micro font-mono text-text-muted">
          [{station.region}]
        </span>
      )}
      {variant === "neighbor" && station.hops != null && (
        <span className="shrink-0 text-micro font-mono text-text-muted">
          {station.hops}h
        </span>
      )}
      <div className="flex-1" />
      <span className="shrink-0 text-micro text-text-muted">
        {station.equipment.length} eq
      </span>
      {open
        ? <ChevronDown className="h-3 w-3 text-text-muted shrink-0" />
        : <ChevronRight className="h-3 w-3 text-text-muted shrink-0" />}
    </>
  );

  return (
    <div
      /* Multiple testids — Playwright looks for each via `getByTestId`.
         Playwright matches data-testid with exact equality, so we rely on
         the individual `data-testid-*` attrs below and pass the primary
         one via data-testid. */
      data-testid={variant === "center" ? "topology-station-center" : `topology-station-${station.station}`}
      data-station={station.station}
      data-variant={variant}
      data-alarmed={anyAlarmed ? "true" : undefined}
      className={[
        "rounded-lg border border-border/60 bg-neutral-bg1 shadow-lg overflow-hidden",
        "w-[280px]",
        /* Center station hierarchy: brand-accent ring + faint inner glow so
           the eye snaps to the centred station immediately after a load,
           even against a busy alarm overlay. Neighbours keep the default
           border so they feel subordinate. */
        variant === "center"
          ? "border-brand/60 ring-1 ring-brand/60 shadow-[inset_0_0_24px_rgba(26,156,133,0.15)]"
          : "",
        halo,
      ].join(" ")}
    >
      {/* Secondary testid marker for neighbor lookups. Playwright's
          data-testid selector matches exact equality on the attribute;
          to let tests locate a node by its station code, we emit an empty
          element with the station-specific testid. Avoids multiple
          data-testid collisions on a single element. */}
      {variant === "center" && (
        <span data-testid={`topology-station-${station.station}`} className="sr-only" aria-hidden="true">
          {station.station}
        </span>
      )}
      {variant === "neighbor" && (
        <span data-testid={`topology-station-neighbor-${station.station}`} className="sr-only" aria-hidden="true">
          {station.station}
        </span>
      )}

      {/* Header row — click toggles collapse; on neighbors, double-click or
          the dedicated recenter button triggers re-centering. */}
      <div className="flex items-stretch border-b border-border/40 bg-neutral-bg2">
        <button
          type="button"
          className="flex-1 flex items-center gap-1.5 px-2 py-1.5 hover:bg-neutral-bg3/50 transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(!open);
          }}
          aria-label={`Toggle equipment list for ${station.station}`}
        >
          {headerContent}
        </button>
        {headerIsButton && (
          <button
            type="button"
            data-testid={`topology-recenter-${station.station}`}
            onClick={(e) => {
              e.stopPropagation();
              onRecenter?.(station.station);
            }}
            title={`Re-center on ${station.station}`}
            className="shrink-0 px-2 border-l border-border/40 text-text-muted hover:text-brand hover:bg-neutral-bg3/50 transition-colors"
          >
            <Network className="h-3.5 w-3.5" />
          </button>
        )}
        {variant === "neighbor" && onExpand && (
          <button
            type="button"
            data-testid={`topology-expand-${station.station}`}
            data-topology-expand-station={station.station}
            data-expanded={isExpanded ? "true" : undefined}
            data-expanding={isExpanding ? "true" : undefined}
            disabled={isExpanded || isExpanding}
            onPointerDown={(e) => {
              e.stopPropagation();
              if (e.button !== 0) return;
              if (isExpanded || isExpanding) return;
              onExpand(station.station);
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (isExpanded || isExpanding) return;
              onExpand(station.station);
            }}
            title={
              isExpanded
                ? `${station.station}'s neighbors already loaded`
                : isExpanding
                ? `Loading ${station.station}'s neighbors…`
                : `Load ${station.station}'s neighbors`
            }
            className={[
              "shrink-0 px-2 border-l border-border/40 transition-colors",
              isExpanded
                ? "text-brand/60 cursor-default"
                : isExpanding
                ? "text-text-muted cursor-wait"
                : "text-text-muted hover:text-brand hover:bg-neutral-bg3/50",
            ].join(" ")}
          >
            {isExpanding ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <GitBranch className="h-3.5 w-3.5" />
            )}
          </button>
        )}
      </div>

      {/* Live-telemetry badge strip — always visible on the station card
          so the operator can see station-level MW / capacity / frequency
          at a glance without expanding the equipment list. Hidden when
          the backend produced no live_summary at all (older response, or
          a backend in which the live query returned nothing matchable). */}
      {hasLive && (
        <div
          data-testid={`topology-station-live-${station.station}`}
          className="flex flex-wrap items-center gap-1 px-2 py-1 border-b border-border/20 bg-neutral-bg2/40 text-micro font-mono"
        >
          {live?.mw_cap != null && (
            <span
              title={`Total rated capacity across station equipment (Σ mw_max), ${primaryUnit}`}
              className="px-1 py-0.5 rounded bg-neutral-bg3/60 text-text-muted"
            >
              cap {live.mw_cap.toFixed(0)} {primaryUnit}
            </span>
          )}
          {live?.mw_output != null && (
            <span
              title={`Sum of latest live readings across equipment, ${primaryUnit}`}
              className="px-1 py-0.5 rounded bg-brand/15 text-brand"
            >
              {live.mw_output >= 0 ? "out" : "in"} {Math.abs(live.mw_output).toFixed(0)} {primaryUnit}
            </span>
          )}
          {live?.freq != null && (
            <span
              title={`Latest oscillation reading at this station (${frequencyUnit})`}
              className={[
                "px-1 py-0.5 rounded",
                Math.abs(live.freq - frequencyNominal) > 0.15
                  ? "bg-situation-major/20 text-situation-major"
                  : "bg-neutral-bg3/60 text-text-secondary",
              ].join(" ")}
            >
              {live.freq.toFixed(2)} Hz
            </span>
          )}
        </div>
      )}

      {/* Equipment list — grouped by voltage, empty-state fallback. */}
      {open && (
        <div className="max-h-[260px] overflow-y-auto">
          {/* Station info block — always rendered when the card is open
              so the operator sees a consistent summary before the
              equipment table. Reports voltage levels covered, equipment
              count, and live-telemetry values with em-dash placeholders
              for anything the backend could not attach. */}
          <div
            data-testid={`topology-station-info-${station.station}`}
            className="border-b border-border/40 bg-neutral-bg2/60 px-2 py-1.5 text-micro font-mono leading-tight"
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-text-secondary">
              {equipmentGroupUnit && (
                <>
                  <span className="text-text-muted">{equipmentGroupUnit}:</span>
                  <span>
                    {voltageGroups.length > 0
                      ? voltageGroups.map(([v]) => v).join(", ")
                      : "—"}
                  </span>
                  <span className="text-text-muted">· eq:</span>
                </>
              )}
              {!equipmentGroupUnit && <span className="text-text-muted">eq:</span>}
              <span>{station.equipment.length}</span>
              {station.hops != null && (
                <>
                  <span className="text-text-muted">· hops:</span>
                  <span>{station.hops}</span>
                </>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
              <span className="text-text-muted">cap:</span>
              <span className="tabular-nums">
                {live?.mw_cap != null ? `${live.mw_cap.toFixed(0)} ${primaryUnit}` : "—"}
              </span>
              <span className="text-text-muted">· out:</span>
              <span
                className={[
                  "tabular-nums",
                  live?.mw_output != null && live.mw_output < 0
                    ? "text-situation-investigate"
                    : "text-brand",
                ].join(" ")}
              >
                {live?.mw_output != null
                  ? `${live.mw_output >= 0 ? "" : "−"}${Math.abs(live.mw_output).toFixed(0)} ${primaryUnit}`
                  : "—"}
              </span>
              <span className="text-text-muted">· freq:</span>
              <span
                className={[
                  "tabular-nums",
                  live?.freq != null && Math.abs(live.freq - frequencyNominal) > 0.15
                    ? "text-situation-major"
                    : "text-text-secondary",
                ].join(" ")}
              >
                {live?.freq != null ? `${live.freq.toFixed(2)} ${frequencyUnit}` : "—"}
              </span>
            </div>
          </div>

          {voltageGroups.length === 0 && (
            <p className="px-2 py-1.5 text-micro italic text-text-muted">No equipment data</p>
          )}
          {voltageGroups.map(([voltage, items]) => (
            <div key={voltage || "all"} className="border-b border-border/20 last:border-b-0">
              {voltage && (
                <div className="px-2 py-0.5 text-micro font-bold tracking-wide uppercase text-text-muted bg-neutral-bg2/40">
                  {voltage}
                </div>
              )}
              {items.map((equip) => (
                <EquipmentRow
                  key={equip.equipment}
                  station={station.station}
                  equipment={equip}
                  alarmed={
                    alarmedIds.has(equip.scada_composite_id)
                    || alarmedIds.has(equip.equipment)
                  }
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
