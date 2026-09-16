/**
 * EquipmentRow — one equipment entry inside a station node.
 *
 * Purpose:
 *   Render a single row (equipment code · CIM class · voltage · MW).
 *   Highlighted red when the station-level overlay marks this equipment
 *   as alarmed.
 *
 * Clicking the row opens the detail pane via topologyStore.selectEquipment.
 */

import { useTopologyStore } from "@/stores/topologyStore";
import { useVocab } from "@/stores/vocabularyStore";
import type { TopologyEquipment } from "@/api/topologyApi";

interface EquipmentRowProps {
  station: string;
  equipment: TopologyEquipment;
  /** True when this equipment is in the situation overlay (alarmed). */
  alarmed: boolean;
}

/** Build a DOM-safe testid fragment from an equipment code. */
function testidFragment(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]/g, "-");
}

/** Best-effort shorthand for a CIM class list — first class only. */
function primaryClass(classes: string[]): string {
  if (!classes || classes.length === 0) return "—";
  return classes[0];
}

export function EquipmentRow({ station, equipment, alarmed }: EquipmentRowProps) {
  const selected = useTopologyStore((s) => s.selectedEquipment);
  const selectEquipment = useTopologyStore((s) => s.selectEquipment);

  /* Domain units — the row shows throughput / oscillation / grouping in
     the scenario's vocabulary so it never hardcodes electrical units. */
  const primaryUnit = useVocab("primaryUnit");
  const frequencyUnit = useVocab("frequencyUnit");
  const frequencyNominal = useVocab("frequencyNominal");
  const equipmentGroupUnit = useVocab("equipmentGroupUnit");

  const isSelected =
    selected?.station === station && selected?.equipmentId === equipment.equipment;

  const eidFragment = testidFragment(equipment.equipment);

  /* Row styling: alarm-state wins over selected-state wins over neutral. */
  const rowClass = [
    "w-full flex items-center gap-1.5 px-2 py-1 text-left text-micro transition-colors",
    alarmed
      ? "topology-equipment-alarmed bg-situation-critical/15 text-situation-critical-text border-l-2 border-situation-critical"
      : isSelected
        ? "bg-brand/10 text-text-primary border-l-2 border-brand"
        : "text-text-secondary hover:bg-neutral-bg2/60 border-l-2 border-transparent",
  ].join(" ");

  return (
    <button
      type="button"
      data-testid={`topology-equipment-${station}-${eidFragment}`}
      data-alarmed={alarmed ? "true" : undefined}
      className={rowClass}
      onClick={(e) => {
        e.stopPropagation();
        selectEquipment({ station, equipmentId: equipment.equipment });
      }}
    >
      <span className="font-mono truncate flex-1" title={equipment.equipment}>
        {equipment.equipment}
      </span>
      <span className="shrink-0 text-text-muted font-mono" title={equipment.cim_classes.join(", ")}>
        {primaryClass(equipment.cim_classes)}
      </span>
      {/* Live MW reading — only rendered when present. Positive values
          render on-brand (generation / export); negative as a load-style
          tint. Absence does not leave a placeholder so the row stays
          compact when there is no telemetry. */}
      {equipment.live && typeof equipment.live.mw === "number" && (
        <span
          data-testid="equipment-live-mw"
          title={`Live ${primaryUnit} (tag ${equipment.live.tags?.mw ?? equipment.scada_composite_id})`}
          className={[
            "shrink-0 font-mono tabular-nums",
            equipment.live.mw < 0 ? "text-situation-investigate" : "text-brand",
          ].join(" ")}
        >
          {equipment.live.mw >= 0 ? "" : "−"}
          {Math.abs(equipment.live.mw).toFixed(1)}{primaryUnit}
        </span>
      )}
      {/* Rated MW capacity — greyed, separate from live so operators can
          compare live vs rated at a glance. */}
      {equipment.mw_max != null && equipment.mw_max > 0 && (
        <span
          data-testid="equipment-mw-cap"
          title="Rated MW capacity (mw_max from asset registry)"
          className="shrink-0 font-mono tabular-nums text-text-muted/80"
        >
          /{equipment.mw_max.toFixed(0)}
        </span>
      )}
      {equipment.nominal_kv != null && equipmentGroupUnit && (
        <span className="shrink-0 font-mono text-brand/80" data-testid="equipment-voltage">
          {equipment.nominal_kv.toFixed(0)}{equipmentGroupUnit}
        </span>
      )}
      {/* Live frequency reading — only shown when this equipment carries a
          HZ/FREQ tag, which is typically a handful of freq meters per
          station. Mildly tinted when drifting >0.15 Hz from 50. */}
      {equipment.live && typeof equipment.live.hz === "number" && (
        <span
          data-testid="equipment-live-hz"
          title={`Live oscillation (tag ${equipment.live.tags?.hz ?? equipment.scada_composite_id})`}
          className={[
            "shrink-0 font-mono tabular-nums",
            Math.abs(equipment.live.hz - frequencyNominal) > 0.15
              ? "text-situation-major"
              : "text-text-secondary",
          ].join(" ")}
        >
          {equipment.live.hz.toFixed(2)}{frequencyUnit}
        </span>
      )}
      {alarmed && (
        <span className="shrink-0 px-1 py-0.5 text-micro font-bold rounded bg-situation-critical text-situation-critical-text">
          ALARM
        </span>
      )}
    </button>
  );
}
