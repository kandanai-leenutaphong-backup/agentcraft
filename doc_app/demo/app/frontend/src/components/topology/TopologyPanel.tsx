/**
 * TopologyPanel — host for the topology tab in the center column.
 *
 * Composes:
 *   - Top:    Breadcrumb + active-station title.
 *   - Middle: TopologyMap (radial canvas).
 *   - Right:  TopologyDetailPane (hidden on narrow layouts).
 *
 * Auto-loads the top-severity situation's station when mounted with no
 * active station. This gives the tab meaningful content immediately —
 * operators never see an empty "click to load" state during an incident.
 */

import { useEffect, useMemo } from "react";
import { ChevronRight, Network, X, RefreshCw } from "lucide-react";
import { useTopologyStore } from "@/stores/topologyStore";
import { useSituationStore } from "@/stores/situationStore";
import type { SituationRecord } from "@/api/situationApi";
import { TopologyMap } from "./TopologyMap";
import { TopologyDetailPane } from "./TopologyDetailPane";
import { rankFor } from "@/lib/severity";

function pickTopSituation(situations: SituationRecord[]): SituationRecord | null {
  if (!situations || situations.length === 0) return null;
  return [...situations].sort((a, b) => {
    const ra = rankFor(a.severity);
    const rb = rankFor(b.severity);
    if (ra !== rb) return ra - rb;
    return b.total_score - a.total_score;
  })[0];
}

export function TopologyPanel() {
  const graph = useTopologyStore((s) => s.graph);
  const loading = useTopologyStore((s) => s.loading);
  const error = useTopologyStore((s) => s.error);
  const activeStation = useTopologyStore((s) => s.activeStation);
  const overlay = useTopologyStore((s) => s.overlay);
  const breadcrumb = useTopologyStore((s) => s.breadcrumb);
  const loadStation = useTopologyStore((s) => s.loadStation);
  const truncateBreadcrumbTo = useTopologyStore((s) => s.truncateBreadcrumbTo);
  const clear = useTopologyStore((s) => s.clear);
  /* Selection drives whether the detail sidebar mounts at all. An empty
     sidebar would otherwise eat 240px of horizontal space from the map. */
  const selection = useTopologyStore((s) => s.selectedEquipment);
  const situations = useSituationStore((s) => s.situations);

  /* Auto-load the top-severity situation when no active station is set yet.
     Fires once per mount — safe to re-run because loadStation no-ops on
     empty input and replaces breadcrumb on fresh loads. */
  useEffect(() => {
    if (activeStation) return;
    const top = pickTopSituation(situations);
    if (top) {
      /* Preload without an overlay — operator hasn't clicked a specific
         situation. Alarm highlighting comes from explicit View topology. */
      void loadStation(top.station);
    }
  }, [activeStation, situations, loadStation]);

  /* Resolve the overlay into a Set for cheap lookup inside StationNode. */
  const alarmedIds = useMemo(
    () => new Set(overlay?.equipmentIds ?? []),
    [overlay],
  );

  /* If we have a graph, render it. Otherwise show the empty / loading /
     error state. */
  const body = (() => {
    if (loading && !graph) {
      return (
        <div
          data-testid="topology-loading"
          className="flex items-center justify-center h-full text-xs text-text-muted"
        >
          <RefreshCw className="h-4 w-4 animate-spin mr-2" />
          Loading topology for {activeStation}…
        </div>
      );
    }
    if (error) {
      return (
        <div
          data-testid="topology-error"
          className="flex flex-col items-center justify-center h-full text-xs text-status-error p-4 text-center"
        >
          <p className="font-semibold mb-1">Failed to load topology</p>
          <p className="text-text-muted">{error}</p>
          {activeStation && (
            <button
              onClick={() => loadStation(activeStation)}
              className="mt-3 px-3 py-1 rounded bg-brand/15 text-brand border border-brand/30 hover:bg-brand/25"
            >
              Retry
            </button>
          )}
        </div>
      );
    }
    if (!graph) {
      return (
        <div
          data-testid="topology-empty-state"
          className="flex flex-col items-center justify-center h-full text-xs text-text-muted italic p-6 text-center"
        >
          <Network className="h-8 w-8 mb-3 text-text-muted/60" />
          <p className="mb-1">No station selected.</p>
          <p>Click <span className="font-semibold">View topology</span> on a situation alert to explore its connectivity.</p>
        </div>
      );
    }
    return <TopologyMap graph={graph} alarmedIds={alarmedIds} overlaySeverity={overlay?.severity ?? null} />;
  })();

  return (
    <div
      data-testid="topology-panel"
      className="h-full flex flex-col border border-border rounded-lg bg-neutral-bg overflow-hidden"
    >
      {/* Header — breadcrumb + clear button. */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-neutral-bg2 shrink-0">
        <Network className="h-3.5 w-3.5 text-brand" />
        <h3 className="text-xs font-semibold text-text-primary">Topology</h3>

        <div data-testid="topology-breadcrumb" className="flex items-center gap-1 flex-1 overflow-x-auto">
          {breadcrumb.map((code, idx) => (
            <div key={`${code}-${idx}`} className="flex items-center gap-1 shrink-0">
              {idx > 0 && <ChevronRight className="h-3 w-3 text-text-muted" />}
              <button
                data-testid={`topology-breadcrumb-item-${code}`}
                onClick={() => void truncateBreadcrumbTo(code)}
                className={[
                  /* Breadcrumb pills: fully rounded, brand-filled for the
                     active station (the centre of the current graph),
                     neutral surface for history stops. Border keeps the
                     pill shape readable when the background blends in. */
                  "px-2.5 py-0.5 text-xs font-mono font-semibold rounded-full border transition-colors",
                  idx === breadcrumb.length - 1
                    ? "bg-brand text-on-accent border-brand"
                    : "bg-neutral-bg2 text-text-secondary border-border hover:text-text-primary hover:bg-neutral-bg3",
                ].join(" ")}
              >
                {code}
              </button>
            </div>
          ))}
        </div>

        {overlay && (
          <span
            data-testid="topology-overlay-badge"
            className="shrink-0 text-micro font-bold px-1.5 py-0.5 rounded bg-situation-critical/20 text-situation-critical border border-situation-critical/40"
          >
            {overlay.severity} overlay
          </span>
        )}

        {graph && (
          <button
            onClick={clear}
            title="Clear topology"
            className="shrink-0 p-1 rounded text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Body — map takes the full width until something is selected;
          the detail pane only mounts when there is content to show so
          an empty sidebar never intrudes on the map. */}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 min-h-0 min-w-0">{body}</div>
        {graph && selection && (
          <div className="w-[240px] shrink-0 border-l border-border bg-neutral-bg1 overflow-hidden hidden md:block">
            <TopologyDetailPane />
          </div>
        )}
      </div>
    </div>
  );
}
