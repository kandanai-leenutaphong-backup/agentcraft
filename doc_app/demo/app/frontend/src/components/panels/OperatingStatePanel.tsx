/**
 * OperatingStatePanel — Grid-wide situation summary.
 *
 * Bottom of left sidebar. Shows severity distribution from the situation
 * detector scan — how many stations have incidents at each severity level.
 * Falls back to the original panel-store-driven operating state checks
 * if an agent pushes them via update_operating_state.
 */

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { usePanelStore } from "@/stores/panelStore";
import { useSituationStore } from "@/stores/situationStore";
import { usePlaceholderStore } from "@/stores/placeholderStore";
import type { FreqSummary } from "@/api/situationApi";
/* Severity vocabulary lives in lib/severity. The distribution legend
   reads in the operator-facing 4-bucket vocabulary (Critical / Major /
   Minor / Suspect) so it matches the alerts-panel filter pills and
   per-row badges — fix-plan row 5, 2026-05-24. */
import { BUCKETS, BUCKET_SWATCH, bucketFor } from "@/lib/severity";
import { parseAffectedEquipment } from "@/lib/situationRecord";

/** Severity distribution bar for situation scan results. */
function SeverityDistribution() {
  const realSituations = useSituationStore((s) => s.situations);
  const placeholderEnabled = usePlaceholderStore((s) => s.enabled);
  const placeholderSituations = usePlaceholderStore((s) => s.situations);
  const situations = realSituations.length > 0 ? realSituations : (placeholderEnabled ? placeholderSituations : []);

  if (situations.length === 0) return null;

  /* Aggregate by operator-facing bucket — SERIOUS + INVESTIGATE fold
     into `Minor`, and `minor` becomes `Suspect`. The raw 5-band
     vocabulary survives only at the detector edge (sort rank in
     SituationAlertsPanel); every visible label on this panel is a
     bucket name so the legend matches the alerts-panel filter pills. */
  const counts: Record<string, number> = {};
  const stationSets: Record<string, Set<string>> = {};
  for (const s of situations) {
    const b = bucketFor(s.severity);
    counts[b] = (counts[b] || 0) + 1;
    if (!stationSets[b]) stationSets[b] = new Set();
    stationSets[b].add(s.station);
  }
  /* Unique stations across all severities */
  const allStations = new Set(situations.map((s) => s.station));

  return (
    <div className="space-y-1.5">
      <div className="text-micro text-text-muted">
        {allStations.size} stations · {situations.length} situations
      </div>
      {/* Distribution bar */}
      <div className="flex h-2 rounded overflow-hidden gap-px">
        {BUCKETS.map((b) => {
          const count = counts[b] || 0;
          if (count === 0) return null;
          const pct = (count / situations.length) * 100;
          return (
            <div
              key={b}
              className={`${BUCKET_SWATCH[b]} transition-all`}
              style={{ width: `${Math.max(pct, 3)}%` }}
              title={`${b}: ${count} (${(stationSets[b] || new Set()).size} stations)`}
            />
          );
        })}
      </div>
      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {BUCKETS.map((b) => {
          const count = counts[b] || 0;
          if (count === 0) return null;
          return (
            <span key={b} className="text-micro text-text-secondary">
              <span className={`inline-block w-2 h-2 rounded-sm mr-1 ${BUCKET_SWATCH[b]}`} />
              {b}: {count}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** Band badge styling per breach level. */
const BAND_BADGE: Record<string, { color: string; label: string }> = {
  none:       { color: "text-status-success", label: "OK" },
  normal:     { color: "text-status-warning", label: "NORM" },
  generation: { color: "text-status-warning font-bold", label: "GEN" },
  network:    { color: "text-status-error", label: "NET" },
  protected:  { color: "text-status-error font-bold", label: "PROT" },
};

/** System Frequency section — per-region freq summary. */
function FrequencySection({ freqSummary }: { freqSummary: FreqSummary }) {
  const [open, setOpen] = useState(false);

  const sortedRegions = Object.entries(freqSummary.regions).sort((a, b) => {
    const rankOrder = ["protected", "network", "generation", "normal", "none"];
    const ra = rankOrder.indexOf(a[1].band_breached);
    const rb = rankOrder.indexOf(b[1].band_breached);
    if (ra !== rb) return ra - rb;
    return a[0].localeCompare(b[0]);
  });

  return (
    <div data-testid="freq-summary" className="border-t border-border/30">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-left hover:bg-neutral-bg3/50 transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3 text-text-muted" /> : <ChevronRight className="h-3 w-3 text-text-muted" />}
        <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
          System Frequency
        </span>
        {freqSummary.total_excursions > 0 && (
          <span className="text-sm text-status-warning font-mono font-bold">({freqSummary.total_excursions})</span>
        )}
      </button>

      {open && (
        <div className="px-3 pb-2 space-y-1">
          {/* NEM summary line — the first number operators reach for when
              freq alarms fire. Numbers bumped to `text-sm` (14 px) mono so
              they’re glanceable while keeping the row compact. */}
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <span className="font-bold text-text-primary">NEM:</span>
            <span className="font-mono text-sm font-bold text-text-primary">{freqSummary.nem_freq_min.toFixed(2)} – {freqSummary.nem_freq_max.toFixed(2)} Hz</span>
            {freqSummary.total_excursions > 0 && (
              <span className="text-status-warning font-medium">{freqSummary.total_excursions} excursion windows</span>
            )}
          </div>

          {/* Per-region rows — region code, freq range, breach badge.
              Region code and numbers promoted so an operator scanning for
              the bad region sees the letter + the Hz reading in one pass. */}
          {sortedRegions.map(([reg, data]) => {
            const badge = BAND_BADGE[data.band_breached] ?? BAND_BADGE.none;
            return (
              <div key={reg} data-testid="freq-region-row" className="flex items-center gap-2 text-xs">
                <span className="font-mono font-bold text-sm text-text-primary w-8">{reg}</span>
                <span className="font-mono text-sm text-text-secondary">
                  {data.freq_min.toFixed(2)} – {data.freq_max.toFixed(2)} Hz
                </span>
                <span data-testid="freq-band-badge" className={`font-bold text-sm ${badge.color}`}>
                  {data.band_breached === "none" ? "●" : "▲"} {badge.label}
                </span>
                {data.excursion_count > 0 && (
                  <span className="text-text-muted font-mono">{data.excursion_count} exc</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Threat Breakdown — per-station + per-equipment drill-down. */
function ThreatBreakdown({ situations, nemLiveMw }: {
  situations: import("@/api/situationApi").SituationRecord[];
  nemLiveMw: number;
}) {
  const [open, setOpen] = useState(false);
  const [expandedStations, setExpandedStations] = useState<Set<string>>(new Set());

  /* Aggregate by station: sum total_mw_lost, collect region/live data. */
  const stationMap: Record<string, {
    mw: number; region: string; regionLive: number;
    situations: import("@/api/situationApi").SituationRecord[];
  }> = {};

  for (const s of situations) {
    if ((s.total_mw_lost ?? 0) <= 0) continue;
    if (!stationMap[s.station]) {
      stationMap[s.station] = {
        mw: 0, region: s.station_region ?? "UNKNOWN",
        regionLive: s.region_live_mw ?? 0, situations: [],
      };
    }
    stationMap[s.station].mw += s.total_mw_lost ?? 0;
    stationMap[s.station].situations.push(s);
  }

  const sortedStations = Object.entries(stationMap).sort((a, b) => b[1].mw - a[1].mw);
  if (sortedStations.length === 0) return null;

  const toggleStation = (stn: string) => {
    setExpandedStations((prev) => {
      const next = new Set(prev);
      if (next.has(stn)) next.delete(stn); else next.add(stn);
      return next;
    });
  };

  return (
    <div data-testid="threat-breakdown" className="border-t border-border/30">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-left hover:bg-neutral-bg3/50 transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3 text-text-muted" /> : <ChevronRight className="h-3 w-3 text-text-muted" />}
        <span className="text-micro font-bold uppercase tracking-wider text-text-muted">
          Threat Breakdown ({sortedStations.length})
        </span>
      </button>

      {open && (
        <div className="pb-1">
          {sortedStations.map(([stn, data]) => {
            const regionPct = data.regionLive > 0 ? (data.mw / data.regionLive * 100) : 0;
            const nemPct = nemLiveMw > 0 ? (data.mw / nemLiveMw * 100) : 0;
            const bgTint = regionPct > 10 ? "bg-status-error/10" : regionPct > 1 ? "bg-status-warning/10" : "";
            const isExpanded = expandedStations.has(stn);

            /* Collect equipment MW drops from affected_equipment SCADA.
               `parseAffectedEquipment` from lib/situationRecord supplies
               the Array.isArray guard the prior inline IIFE was missing
               (bug_hunter D-007, 2026-05-24) — a hand-edited record
               whose `affected_equipment` decoded to an object would
               previously fall through `for (const eq of ae)` as if it
               were an empty array, silently hiding the equipment
               breakdown. */
            const equipMap: Record<string, number> = {};
            for (const sit of data.situations) {
              const ae = parseAffectedEquipment(sit.affected_equipment);
              for (const eq of ae) {
                for (const sc of eq.scada ?? []) {
                  if (sc.measurement === "MW" && sc.abs_drop > 0) {
                    const key = eq.equipment_id;
                    equipMap[key] = Math.max(equipMap[key] ?? 0, sc.abs_drop);
                  }
                }
              }
            }
            const sortedEquip = Object.entries(equipMap).sort((a, b) => b[1] - a[1]);

            return (
              <div key={stn}>
                {/* Station row */}
                <button
                  data-testid="threat-station-row"
                  onClick={() => toggleStation(stn)}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-neutral-bg3/50 transition-colors ${bgTint}`}
                >
                  {isExpanded ? <ChevronDown className="h-2.5 w-2.5 text-text-muted shrink-0" /> : <ChevronRight className="h-2.5 w-2.5 text-text-muted shrink-0" />}
                  <span className="font-mono font-bold text-text-primary text-micro">{stn}</span>
                  <span className="text-micro font-mono text-text-muted">[{data.region}]</span>
                  <span className="font-mono text-text-secondary text-micro">{Math.round(data.mw)} MW</span>
                  <span className={`text-micro font-mono ${regionPct > 10 ? "text-status-error" : regionPct > 1 ? "text-status-warning" : "text-text-muted"}`}>
                    {regionPct.toFixed(1)}% {data.region}
                  </span>
                  <span className={`text-micro font-mono ${nemPct > 5 ? "text-status-error" : nemPct > 1 ? "text-status-warning" : "text-text-muted"}`}>
                    {nemPct.toFixed(1)}% NEM
                  </span>
                </button>

                {/* Equipment rows */}
                {isExpanded && (
                  <div className="pl-6 pb-1">
                    {sortedEquip.length === 0 ? (
                      <div className="text-micro text-text-muted italic px-3 py-1">No MW equipment data</div>
                    ) : (
                      sortedEquip.map(([eqId, drop]) => {
                        const eqStnPct = data.mw > 0 ? (drop / data.mw * 100) : 0;
                        const eqRegPct = data.regionLive > 0 ? (drop / data.regionLive * 100) : 0;
                        const eqNemPct = nemLiveMw > 0 ? (drop / nemLiveMw * 100) : 0;
                        const eqTint = eqRegPct > 10 ? "bg-status-error/5" : eqRegPct > 1 ? "bg-status-warning/5" : "";
                        return (
                          <div
                            key={eqId}
                            data-testid="threat-equipment-row"
                            className={`flex items-center gap-2 px-3 py-1 text-micro ${eqTint}`}
                          >
                            <span className="font-mono text-text-secondary truncate max-w-[140px]">{eqId}</span>
                            <span className="font-mono text-text-primary shrink-0">{drop.toFixed(1)} MW</span>
                            <span className="font-mono text-text-muted shrink-0">{eqStnPct.toFixed(0)}% stn</span>
                            <span className={`font-mono shrink-0 ${eqRegPct > 10 ? "text-status-error" : eqRegPct > 1 ? "text-status-warning" : "text-text-muted"}`}>
                              {eqRegPct.toFixed(1)}% {data.region}
                            </span>
                            <span className={`font-mono shrink-0 ${eqNemPct > 5 ? "text-status-error" : eqNemPct > 1 ? "text-status-warning" : "text-text-muted"}`}>
                              {eqNemPct.toFixed(1)}% NEM
                            </span>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function OperatingStatePanel() {
  const panelData = usePanelStore((s) => s.operatingState);
  const realSituations = useSituationStore((s) => s.situations);
  const freqSummary = useSituationStore((s) => s.freqSummary);
  const placeholderEnabled = usePlaceholderStore((s) => s.enabled);
  const placeholderSituations = usePlaceholderStore((s) => s.situations);
  const situations = realSituations.length > 0 ? realSituations : (placeholderEnabled ? placeholderSituations : []);
  const hasSituations = situations.length > 0;

  if (!hasSituations && !panelData) {
    return (
      <div className="space-y-2">
        <div className="border border-border rounded-lg p-3 bg-neutral-bg2">
          <h3 className="text-sm uppercase tracking-wider text-text-secondary font-bold">
            Grid Status
          </h3>
          <p className="text-text-tertiary text-sm mt-1 italic">Run a scan to assess</p>
        </div>
      </div>
    );
  }

  /* Derive NEM metrics from enriched situations. */
  const nemLiveMw = situations.length > 0 ? (situations[0]?.nem_live_mw ?? 0) : 0;

  /* Collect unique regions and their metrics. */
  const regionMap: Record<string, { rated: number; live: number; threatened: number; count: number }> = {};
  const allStations = new Set<string>();
  let totalAlarms = 0;
  let totalStepChanges = 0;
  let totalMwThreatened = 0;

  for (const s of situations) {
    allStations.add(s.station);
    totalAlarms += s.alarm_count ?? 0;
    totalStepChanges += s.step_changes ?? 0;
    totalMwThreatened += s.total_mw_lost ?? 0;

    const reg = s.station_region ?? "UNKNOWN";
    if (reg && reg !== "UNKNOWN") {
      if (!regionMap[reg]) {
        regionMap[reg] = { rated: s.region_rated_mw ?? 0, live: s.region_live_mw ?? 0, threatened: 0, count: 0 };
      }
      regionMap[reg].threatened += s.total_mw_lost ?? 0;
      regionMap[reg].count += 1;
    }
  }

  /* Total NEM rated = sum of all region rated values. */
  const nemRatedMw = Object.values(regionMap).reduce((sum, r) => sum + r.rated, 0);
  const nemUtilization = nemRatedMw > 0 ? (nemLiveMw / nemRatedMw * 100) : 0;
  const nemThreatenedPct = nemLiveMw > 0 ? (totalMwThreatened / nemLiveMw * 100) : 0;

  /* Sort regions by MW threatened descending. */
  const sortedRegions = Object.entries(regionMap).sort((a, b) => b[1].threatened - a[1].threatened);

  const hasCapacityData = nemLiveMw > 0;

  return (
    <div className="space-y-2">
      <div className="border border-border rounded-lg bg-neutral-bg2 overflow-hidden">
        <h3 className="text-sm uppercase tracking-wider text-text-secondary font-bold px-3 pt-3 pb-1">
          Grid Status
        </h3>

        {/* NEM Summary — hero telemetry. Numbers promoted to `text-xl` so the
            shift lead can read generation, capacity, and utilization from
            across the room. Labels sit at `text-xs` uppercase so the eye
            locks onto the value first, the caption second. */}
        {hasCapacityData && (
          <div data-testid="nem-summary" className="flex gap-4 px-3 py-2">
            <div>
              <div className="text-xl font-mono font-bold text-text-primary leading-tight">{Math.round(nemLiveMw).toLocaleString()} MW</div>
              <div className="text-xs text-text-muted uppercase tracking-wider">NEM Generation</div>
            </div>
            <div>
              <div className="text-xl font-mono font-bold text-text-primary leading-tight">{Math.round(nemRatedMw).toLocaleString()} MW</div>
              <div className="text-xs text-text-muted uppercase tracking-wider">NEM Capacity</div>
            </div>
            <div>
              <div className="text-xl font-mono font-bold text-text-primary leading-tight">{nemUtilization.toFixed(1)}%</div>
              <div className="text-xs text-text-muted uppercase tracking-wider">Utilization</div>
            </div>
          </div>
        )}

        {/* Situation Summary — secondary-tier telemetry. Counts use `text-lg`
            so they’re clearly subordinate to the NEM totals but still
            comfortably readable at arm’s length in a stressed room. */}
        <div data-testid="situation-summary" className="flex gap-4 px-3 py-2 border-t border-border/30">
          <div>
            <div className="text-lg font-mono font-bold text-text-primary leading-tight">{situations.length}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Situations</div>
          </div>
          <div>
            <div className="text-lg font-mono font-bold text-text-primary leading-tight">{allStations.size}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Stations</div>
          </div>
          <div>
            <div className="text-lg font-mono font-bold text-text-primary leading-tight">{totalAlarms}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Alarms</div>
          </div>
          <div>
            <div className="text-lg font-mono font-bold text-text-primary leading-tight">{totalStepChanges}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Step Changes</div>
          </div>
        </div>

        {/* Severity Distribution */}
        <div className="px-3 py-2 border-t border-border/30">
          <SeverityDistribution />
        </div>

        {/* Regional Breakdown — per-region capacity lines. Promoted from
            `text-micro` (10 px) to `text-xs` (12 px) with the numbers at
            `text-sm` (14 px) so MW values read clearly without dominating. */}
        {hasCapacityData && sortedRegions.length > 0 && (
          <div data-testid="regional-breakdown" className="border-t border-border/30">
            <div className="px-3 py-1.5 text-xs text-text-muted font-bold uppercase tracking-wider">
              Regional Capacity
            </div>
            {sortedRegions.map(([reg, data]) => {
              const utilPct = data.rated > 0 ? (data.live / data.rated * 100) : 0;
              const threatPct = data.live > 0 ? (data.threatened / data.live * 100) : 0;
              const bgTint = threatPct > 10 ? "bg-status-error/10" : threatPct > 1 ? "bg-status-warning/10" : "";
              return (
                <div key={reg} className={`flex items-center gap-2 px-3 py-1.5 text-xs ${bgTint}`}>
                  <span className="font-mono font-bold text-sm text-text-primary w-10">{reg}</span>
                  <span className="font-mono text-sm text-text-secondary">
                    {Math.round(data.live).toLocaleString()} / {Math.round(data.rated).toLocaleString()} MW
                  </span>
                  <span className="text-text-muted">({utilPct.toFixed(1)}%)</span>
                  {data.threatened > 0 && (
                    <span className={`font-mono font-bold ${threatPct > 10 ? "text-status-error" : threatPct > 1 ? "text-status-warning" : "text-text-muted"}`}>
                      ▲ {Math.round(data.threatened)} MW ({threatPct.toFixed(1)}%)
                    </span>
                  )}
                  <span className="text-text-muted ml-auto">{data.count} sit</span>
                </div>
              );
            })}
          </div>
        )}

        {/* System Frequency */}
        {freqSummary && (
          <FrequencySection freqSummary={freqSummary} />
        )}

        {/* MW Threatened — primary risk readout. Promoted to `text-base`
            bold so it reads as a warning banner rather than a footnote.
            The % subtitle lifts to `text-sm` with tabular numerals. */}
        {totalMwThreatened > 0 && hasCapacityData && (
          <div
            data-testid="mw-threatened"
            className={`flex items-center gap-3 px-3 py-2 border-t border-border/30 ${
              nemThreatenedPct > 5 ? "bg-status-error/10" : nemThreatenedPct > 1 ? "bg-status-warning/10" : ""
            }`}
          >
            <span className="text-base font-bold text-text-primary">
              {Math.round(totalMwThreatened)} MW Threatened
            </span>
            <span className={`text-sm font-mono font-bold ${nemThreatenedPct > 5 ? "text-status-error" : nemThreatenedPct > 1 ? "text-status-warning" : "text-text-muted"}`}>
              {nemThreatenedPct.toFixed(1)}% of NEM generation
            </span>
          </div>
        )}

        {/* No capacity data notice */}
        {!hasCapacityData && situations.length > 0 && (
          <div className="px-3 py-1.5 text-micro text-text-muted italic border-t border-border/30">
            Capacity data unavailable for this time window.
          </div>
        )}

        {/* Threat Breakdown — per-station + per-equipment drill-down */}
        {totalMwThreatened > 0 && hasCapacityData && (
          <ThreatBreakdown situations={situations} nemLiveMw={nemLiveMw} />
        )}
      </div>
    </div>
  );
}
