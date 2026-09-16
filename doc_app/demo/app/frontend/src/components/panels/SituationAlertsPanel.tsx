/**
 * SituationAlertsPanel — station-grouped situation feed (2026-05-24).
 *
 * Layout per user spec:
 *   1. One collapsible per station (default OPEN).
 *   2. Inside: a compact one-row-per-situation table — time window,
 *      equipment, severity badge, score.
 *   3. Click a row → expands the full `SituationCard` inline below.
 *
 * Filter bar: full-label severity toggle pills + station text filter.
 * Demo-data ribbon: shown when the rendered list is the placeholder
 * fixture so seeded situations cannot masquerade as live results.
 */

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Pin, ZoomIn } from "lucide-react";
import {
  useSituationStore,
  buildClusterInvestigatePrompt,
  buildStationInvestigatePrompt,
} from "@/stores/situationStore";
import { usePlaceholderStore } from "@/stores/placeholderStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { usePanelStore } from "@/stores/panelStore";
import { SituationCard } from "./SituationCard";
import { ScanProgressBar, ScanProgressPanel } from "@/components/shared/ScanProgress";
import type { SituationRecord } from "@/api/situationApi";
/* Severity vocabulary + Tailwind class maps live in lib/severity so the
   panel cannot drift from SituationCard + OperatingStatePanel. The
   panel works in the operator-facing 4-bucket vocabulary; the raw
   5-band rank is only used for sort order. */
import {
  BUCKETS,
  BUCKET_BADGE,
  BUCKET_FILTER_ACTIVE,
  bucketFor,
  rankFor,
  type Bucket,
} from "@/lib/severity";
/* Wire-decoder + row-brief helpers — single source of truth. */
import { firstEquipmentId, hhmm } from "@/lib/situationRecord";

/* Group situations by station and sort. Stations are ordered by their
   worst-severity row (rank ASC), then by max total_score DESC, then
   alphabetically. Within a station the rows are ordered by
   `window_start` DESC (latest first) per the operator brief
   2026-05-24 — the freshest situation belongs at the top of the
   table; severity is already legible via the per-row badge. */
function groupByStation(
  sits: SituationRecord[],
): Array<{ station: string; situations: SituationRecord[] }> {
  const byStation = new Map<string, SituationRecord[]>();
  for (const s of sits) {
    const list = byStation.get(s.station);
    if (list) list.push(s);
    else byStation.set(s.station, [s]);
  }
  for (const list of byStation.values()) {
    list.sort((a, b) => {
      /* Latest window first. localeCompare on ISO-shaped strings
         keeps the comparison cheap and avoids Date parsing. */
      const t = b.window_start.localeCompare(a.window_start);
      if (t !== 0) return t;
      /* Tie-break on severity then score so two simultaneous rows
         still surface the worst one above the other. */
      const r = rankFor(a.severity) - rankFor(b.severity);
      if (r !== 0) return r;
      return b.total_score - a.total_score;
    });
  }
  const groups = Array.from(byStation.entries()).map(([station, situations]) => ({
    station,
    situations,
  }));
  /* Sort station groups by their WORST-severity row (rank ASC), then
     by that row's score DESC, then alphabetically. We compute the
     worst row explicitly because the in-group sort is now time-DESC,
     so `situations[0]` is the latest, not the worst. */
  groups.sort((a, b) => {
    const worstA = a.situations.reduce(
      (acc, s) => (rankFor(s.severity) < rankFor(acc.severity) ? s : acc),
      a.situations[0],
    );
    const worstB = b.situations.reduce(
      (acc, s) => (rankFor(s.severity) < rankFor(acc.severity) ? s : acc),
      b.situations[0],
    );
    const ra = rankFor(worstA.severity);
    const rb = rankFor(worstB.severity);
    if (ra !== rb) return ra - rb;
    if (worstB.total_score !== worstA.total_score) return worstB.total_score - worstA.total_score;
    return a.station.localeCompare(b.station);
  });
  return groups;
}

/* Display buckets — the panel collapses the 5-band detector output
   (CRITICAL / MAJOR / SERIOUS / INVESTIGATE / minor) into 4 operator-
   facing buckets (2026-05-24). The vocabulary itself lives in
   `lib/severity` so the SituationCard surface, the alerts panel, and
   the operating-state distribution legend all read the same labels
   for the same raw band. The raw severity is still what the detector
   emits and what drives the per-row sort rank; only the filter pills
   and the visible badge label use the bucket name. */

export function SituationAlertsPanel() {
  const realSituations = useSituationStore((s) => s.situations);
  const isScanning = useSituationStore((s) => s.loading);
  const placeholderEnabled = usePlaceholderStore((s) => s.enabled);
  const placeholderSituations = usePlaceholderStore((s) => s.situations);
  const allSituations = isScanning ? realSituations : (realSituations.length > 0 ? realSituations : (placeholderEnabled ? placeholderSituations : []));
  /* True when the rendered list is the placeholder fixture rather than
     a live scan result. Drives the demo-data ribbon so the operator
     cannot mistake seeded situations for real ones (audit F-011). */
  const showingPlaceholders = !isScanning && realSituations.length === 0 && placeholderEnabled && placeholderSituations.length > 0;
  const createSession = useSessionStore((s) => s.createSession);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const setActiveAgent = useAgentStore((s) => s.setActiveAgent);
  /* Pin action — single source of truth in panelStore. Used both for
     manual pin clicks (switchTab: true) and auto-pin-on-investigate
     (switchTab: false) per operator brief 2026-05-25. */
  const pinStation = usePanelStore((s) => s.pinStation);

  /* Filter state — the operator-facing 4-bucket scheme. ALL buckets
     active by default (2026-05-24) — the "Suspect" bucket (formerly
     `minor`) is no longer hidden on first paint. */
  const [activeBuckets, setActiveBuckets] = useState<Set<Bucket>>(
    new Set<Bucket>(BUCKETS),
  );
  const [stationFilter, setStationFilter] = useState("");

  /* Station accordion state. Default = OPEN for every station, so we
     track the CLOSED set instead of the open set; a brand-new station
     coming back from a scan is open without any extra wiring. */
  const [closedStations, setClosedStations] = useState<Set<string>>(new Set());
  const toggleStation = (station: string) => {
    setClosedStations((prev) => {
      const next = new Set(prev);
      if (next.has(station)) next.delete(station);
      else next.add(station);
      return next;
    });
  };

  /* Per-row expansion state — keyed by situation_id so a row's open
     state survives re-renders driven by store updates. */
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const toggleRow = (sid: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(sid)) next.delete(sid);
      else next.add(sid);
      return next;
    });
  };

  /* Toggle bucket filter. */
  const toggleBucket = (bucket: Bucket) => {
    setActiveBuckets((prev) => {
      const next = new Set(prev);
      if (next.has(bucket)) next.delete(bucket);
      else next.add(bucket);
      return next;
    });
  };

  /* Apply filters. */
  const filteredSituations = allSituations.filter((s) => {
    if (!activeBuckets.has(bucketFor(s.severity))) return false;
    if (stationFilter.trim()) {
      const tokens = stationFilter.toLowerCase().split(/\s+/).filter(Boolean);
      const stn = s.station.toLowerCase();
      if (!tokens.some((t) => stn.includes(t))) return false;
    }
    return true;
  });

  /* Group filtered situations by station — one accordion per station,
     one row per situation inside. Memoised on the filter result so
     row-click expansion does not rebuild the group structure. */
  const stationGroups = useMemo(
    () => groupByStation(filteredSituations),
    [filteredSituations],
  );

  /* Reconcile `closedStations` + `expandedRows` against the current
     keyset whenever the underlying store list changes (bug_hunter
     D-005, 2026-05-24). Pre-hygiene, the two Sets accumulated
     monotonically across scans: a station that disappeared from the
     store left a stale entry behind, and the next scan that re-
     introduced the same station name silently rendered it pre-
     collapsed against the documented "default OPEN" contract. We
     intersect on `allSituations` rather than `filteredSituations` so
     a filter toggle does not drop a station the operator has only
     temporarily hidden. */
  useEffect(() => {
    const liveStations = new Set(allSituations.map((s) => s.station));
    const liveSituationIds = new Set(allSituations.map((s) => s.situation_id));
    setClosedStations((prev) => {
      let changed = false;
      const next = new Set<string>();
      for (const stn of prev) {
        if (liveStations.has(stn)) next.add(stn);
        else changed = true;
      }
      return changed ? next : prev;
    });
    setExpandedRows((prev) => {
      let changed = false;
      const next = new Set<string>();
      for (const sid of prev) {
        if (liveSituationIds.has(sid)) next.add(sid);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [allSituations]);

  /* Per-situation investigate — single-row Investigate routed through
     the configured DEFAULT agent. Re-uses the cluster prompt builder
     with a one-element list so the prompt shape stays identical
     whether one or many situations are passed forward. Operator brief
     2026-05-25: investigating any row auto-pins that row's whole
     station group into the centre Situation tab, silently (no tab
     switch — the chat surface is the foreground action). */
  const handleInvestigate = async (sit: SituationRecord) => {
    /* Auto-pin the row's station with every situation currently in
       the same group (look-up by station code on the filtered list).
       Falls back to a single-element list if the group is somehow
       absent (defensive against the row pre-dating the latest scan). */
    const groupSits = allSituations.filter((s) => s.station === sit.station);
    pinStation(sit.station, groupSits.length > 0 ? groupSits : [sit], { switchTab: false });
    const session = await createSession();
    if (!session) return;
    const prompt = buildClusterInvestigatePrompt([sit]);
    const agents = useAgentStore.getState().agents;
    const defaultAgentId = agents.find((a) => a.is_default)?.id ?? agents[0]?.id ?? "investigator";
    setActiveAgent(defaultAgentId);
    await sendMessage(session.id, prompt, defaultAgentId);
  };

  /* Station-level investigate — "These situations are happening at
     {station}. Investigate." Triggered by the magnifier-plus button
     on the group header; concatenates every situation in the group
     into a single prompt. Auto-pins silently (operator stays on
     chat). Same default-agent routing as the per-row handler so any
     future cutover (e.g. to a new triage agent) does not require
     touching this code path. */
  const handleInvestigateStation = async (
    station: string,
    sits: SituationRecord[],
  ) => {
    if (sits.length === 0) return;
    pinStation(station, sits, { switchTab: false });
    const session = await createSession();
    if (!session) return;
    const prompt = buildStationInvestigatePrompt(station, sits);
    const agents = useAgentStore.getState().agents;
    const defaultAgentId = agents.find((a) => a.is_default)?.id ?? agents[0]?.id ?? "investigator";
    setActiveAgent(defaultAgentId);
    await sendMessage(session.id, prompt, defaultAgentId);
  };

  /* Manual pin — Pin icon on a station-group header. Surfaces the
     centre Situation tab (operator wants to view the pin) without
     firing an investigation. Bulk-pins the entire group's situation
     snapshot. */
  const handlePinStation = (station: string, sits: SituationRecord[]) => {
    if (sits.length === 0) return;
    pinStation(station, sits, { switchTab: true });
  };

  return (
    <div data-testid="situation-alerts-panel" className="flex flex-col h-full border border-border rounded-lg bg-neutral-bg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-neutral-bg2 shrink-0">
        <AlertTriangle className="w-4 h-4 text-watcher-icon" />
        <h3 className="text-sm font-bold text-foreground">Situation Alerts</h3>
        <span className="text-xs text-text-secondary font-mono font-bold">({filteredSituations.length})</span>
        <div className="flex-1" />
      </div>

      {/* Scan progress strip — slim time-based bar that animates against
          the rolling-average estimate from situationStore. Renders nothing
          when no scan is in flight. */}
      <ScanProgressBar />

      {/* Demo-data ribbon — shown when the rendered list is the
          placeholder fixture so seeded situations cannot masquerade as
          a live scan result (audit F-011). */}
      {showingPlaceholders && (
        <div
          data-testid="demo-data-ribbon"
          className="px-3 py-1.5 text-xs font-medium text-status-warning bg-status-warning/15 border-b border-status-warning/30 shrink-0"
        >
          Demo data — run a scan to see live situations
        </div>
      )}

      {/* Filter bar — full-label severity pills (audit F-005). On very
          narrow viewports the row gracefully wraps; the monogram fallback
          (`C`/`M`/`S`/`I`) is kept as the `aria-label` short form for
          screen readers via `aria-label` and as a `data-monogram` for
          future responsive use. */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border/30 bg-neutral-bg2/50 shrink-0 flex-wrap">
        {BUCKETS.map((bucket) => {
          const isActive = activeBuckets.has(bucket);
          return (
            <button
              key={bucket}
              data-testid={`severity-filter-${bucket}`}
              aria-label={`Toggle ${bucket} filter`}
              onClick={() => toggleBucket(bucket)}
              className={`px-2 py-0.5 text-xs font-black tracking-wide rounded border whitespace-nowrap transition-colors ${
                isActive ? BUCKET_FILTER_ACTIVE[bucket] : "border-border text-text-muted hover:text-text-secondary"
              }`}
            >
              {bucket}
            </button>
          );
        })}
        <input
          data-testid="station-text-filter"
          type="text"
          value={stationFilter}
          onChange={(e) => setStationFilter(e.target.value)}
          placeholder="Filter stations..."
          className="ml-auto px-2 py-0.5 text-micro rounded border border-border bg-neutral-bg1 text-text-primary placeholder:text-text-muted focus:border-brand/50 focus:outline-none w-24"
        />
      </div>

      {/* Situation feed — flat list by default, station-grouped on toggle. */}
      <div className="flex-1 p-2 space-y-1 overflow-y-auto min-h-0">
        {/* In-flight scan: replace the empty-state placeholder with a
            dedicated crunching panel. We keep this BEFORE the no-results
            check so an empty result list during a scan still shows
            progress instead of "no situations". */}
        {isScanning && filteredSituations.length === 0 && <ScanProgressPanel />}
        {!isScanning && filteredSituations.length === 0 && (
          <p className="text-xs text-text-muted italic text-center py-4">
            {allSituations.length === 0 ? "Click Scan to detect situations" : "No situations match filters"}
          </p>
        )}

        {/* Station-grouped feed. One collapsible per station (default
            OPEN), inside which a one-row-per-situation table renders
            a brief window+equipment+severity+score view; clicking the
            row expands the full SituationCard inline below it. */}
        {stationGroups.map((group) => {
          const isOpen = !closedStations.has(group.station);
          /* Worst-severity row drives the header badge so the eye
             still hits CRITICAL/MAJOR even though the in-group sort
             is by time. group.situations[0] is the LATEST row, not
             the worst, so compute it explicitly. */
          const worst = group.situations.reduce(
            (acc, s) => (rankFor(s.severity) < rankFor(acc.severity) ? s : acc),
            group.situations[0],
          );
          return (
            <div
              key={group.station}
              data-testid="station-group"
              className="rounded border border-border bg-neutral-bg1 overflow-hidden"
            >
              <div className="flex items-center bg-neutral-bg2 hover:bg-neutral-bg3">
                <button
                  type="button"
                  data-testid="station-group-header"
                  aria-expanded={isOpen}
                  onClick={() => toggleStation(group.station)}
                  className="flex-1 min-w-0 flex items-center gap-2 px-2 py-1.5 text-left"
                >
                  {isOpen ? (
                    <ChevronDown className="w-3.5 h-3.5 text-text-muted shrink-0" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-text-muted shrink-0" />
                  )}
                  <span
                    className={`px-1.5 py-0.5 text-micro font-black tracking-wide rounded ${
                      BUCKET_BADGE[bucketFor(worst.severity)]
                    }`}
                  >
                    {bucketFor(worst.severity)}
                  </span>
                  <span className="text-sm font-bold text-text-primary">{group.station}</span>
                </button>
                {/* Pin station — manual pin without investigation.
                    Operator brief 2026-05-25: pin granularity is the
                    station; clicking promotes the whole group into the
                    centre Situation tab and surfaces the tab.
                    stopPropagation so the click does not also collapse
                    the accordion. */}
                <button
                  type="button"
                  data-testid={`pin-station-${group.station}`}
                  aria-label={`Pin ${group.situations.length} situations at ${group.station}`}
                  title="Pin station situations"
                  onClick={(e) => {
                    e.stopPropagation();
                    handlePinStation(group.station, group.situations);
                  }}
                  className="shrink-0 px-2 py-1.5 text-brand hover:text-brand hover:bg-brand/15 border-l border-border/50"
                >
                  <Pin className="w-4 h-4" strokeWidth={2.5} />
                </button>
                {/* Station-level investigate — magnifier-plus, orange.
                    Fires "These situations are happening at {station}.
                    Investigate." with every row in the group
                    concatenated. Auto-pins the station silently (no
                    tab switch — investigation is the foreground
                    action). stopPropagation so the click does
                    not also collapse the accordion. */}
                <button
                  type="button"
                  data-testid={`investigate-station-${group.station}`}
                  aria-label={`Investigate all ${group.situations.length} situations at ${group.station}`}
                  title="Investigate all situations at this station"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleInvestigateStation(group.station, group.situations);
                  }}
                  className="shrink-0 px-2 py-1.5 text-status-warning hover:text-status-warning hover:bg-status-warning/15 border-l border-border/50"
                >
                  <ZoomIn className="w-4 h-4" strokeWidth={2.5} />
                </button>
              </div>

              {isOpen && (
                <div data-testid="situation-window-table" className="divide-y divide-border/40">
                  {group.situations.map((sit) => {
                    const open = expandedRows.has(sit.situation_id);
                    const equip = firstEquipmentId(sit);
                    return (
                      <div
                        key={sit.situation_id}
                        data-testid="situation-card-wrapper"
                      >
                        <button
                          type="button"
                          data-testid={`situation-row-${sit.situation_id}`}
                          aria-expanded={open}
                          onClick={() => toggleRow(sit.situation_id)}
                          className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-neutral-bg2/60"
                        >
                          {open ? (
                            <ChevronDown className="w-3 h-3 text-text-muted shrink-0" />
                          ) : (
                            <ChevronRight className="w-3 h-3 text-text-muted shrink-0" />
                          )}
                          <span className="text-micro font-mono text-text-secondary shrink-0 w-[88px]">
                            {hhmm(sit.window_start)} → {hhmm(sit.window_end)}
                          </span>
                          <span className="text-micro font-mono text-text-primary truncate flex-1 min-w-0">
                            {equip}
                          </span>
                          <span
                            className={`px-1 py-px text-micro font-black tracking-wide rounded shrink-0 ${
                              BUCKET_BADGE[bucketFor(sit.severity)]
                            }`}
                          >
                            {bucketFor(sit.severity)}
                          </span>
                          <span className="text-micro font-mono text-text-secondary shrink-0 w-10 text-right">
                            {sit.total_score.toFixed(1)}
                          </span>
                        </button>
                        {open && (
                          <div className="px-1 pb-1">
                            <SituationCard
                              situation={sit}
                              onInvestigate={handleInvestigate}
                              embedded
                              defaultExpanded
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
