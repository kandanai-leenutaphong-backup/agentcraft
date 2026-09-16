/**
 * TopologyDetailPane — side pane that shows the currently selected equipment.
 *
 * Displays the full equipment record from the topology response plus any
 * overlay information (alarm severity, matching flag). Non-critical — the
 * map still works if this pane is collapsed or empty.
 */

import { useMemo } from "react";
import { X } from "lucide-react";
import { useTopologyStore } from "@/stores/topologyStore";
import { useVocab } from "@/stores/vocabularyStore";

export function TopologyDetailPane() {
  const graph = useTopologyStore((s) => s.graph);
  const selection = useTopologyStore((s) => s.selectedEquipment);
  const overlay = useTopologyStore((s) => s.overlay);
  const selectEquipment = useTopologyStore((s) => s.selectEquipment);

  /* Domain vocabulary — the detail pane is fully relabelled per industry
     (facility/identifier/class wording and the stat-grid columns). */
  const facilityTermSingular = useVocab("facilityTermSingular");
  const equipmentTerm = useVocab("equipmentTerm");
  const identifierLabel = useVocab("identifierLabel");
  const equipmentClassLabel = useVocab("equipmentClassLabel");
  const topologyStats = useVocab("topologyStats");

  /* Resolve the selected equipment record from the loaded graph. */
  const record = useMemo(() => {
    if (!graph || !selection) return null;
    const pool = [graph.center, ...graph.neighbors];
    for (const station of pool) {
      if (station.station !== selection.station) continue;
      const hit = station.equipment.find((e) => e.equipment === selection.equipmentId);
      if (hit) return { station: station.station, region: station.region, equipment: hit };
    }
    return null;
  }, [graph, selection]);

  if (!record) {
    return (
      <div
        data-testid="topology-detail-pane"
        className="h-full flex items-center justify-center text-xs text-text-muted italic p-4 text-center"
      >
        Click an equipment row to see details.
      </div>
    );
  }

  const alarmed = overlay
    ? overlay.equipmentIds.includes(record.equipment.scada_composite_id)
      || overlay.equipmentIds.includes(record.equipment.equipment)
    : false;

  return (
    <div data-testid="topology-detail-pane" className="h-full flex flex-col text-xs">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-neutral-bg2">
        <span className="font-semibold text-text-primary flex-1 truncate">
          {equipmentTerm} Details
        </span>
        <button
          onClick={() => selectEquipment(null)}
          className="p-1 rounded hover:bg-neutral-bg3 text-text-muted hover:text-text-primary"
          title="Close"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        <div>
          <div className="text-micro uppercase tracking-wide text-text-muted">{facilityTermSingular}</div>
          <div className="font-mono text-text-primary">{record.station} <span className="text-text-muted">[{record.region}]</span></div>
        </div>
        <div>
          <div className="text-micro uppercase tracking-wide text-text-muted">{equipmentTerm}</div>
          <div className="font-mono text-text-primary break-all">{record.equipment.equipment}</div>
        </div>
        {record.equipment.scada_composite_id && (
          <div>
            <div className="text-micro uppercase tracking-wide text-text-muted">{identifierLabel}</div>
            <div className="font-mono text-text-secondary break-all">{record.equipment.scada_composite_id}</div>
          </div>
        )}
        <div>
          <div className="text-micro uppercase tracking-wide text-text-muted">{equipmentClassLabel}</div>
          <div className="font-mono text-text-secondary">
            {record.equipment.cim_classes.length > 0
              ? record.equipment.cim_classes.join(", ")
              : "—"}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {topologyStats.map((stat) => (
            <Stat key={stat.field} label={stat.label} value={record.equipment[stat.field]} />
          ))}
        </div>
        {alarmed && overlay && (
          <div className="mt-2 rounded border border-situation-critical/40 bg-situation-critical/10 p-2">
            <div className="text-micro font-bold text-situation-critical">
              ALARMED — {overlay.severity}
            </div>
            <p className="text-text-secondary mt-1">
              This equipment is tagged as affected by the active situation.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded border border-border/40 bg-neutral-bg2/40 px-2 py-1">
      <div className="text-micro text-text-muted">{label}</div>
      <div className="font-mono text-text-primary">
        {value != null ? value.toFixed(1) : "—"}
      </div>
    </div>
  );
}
