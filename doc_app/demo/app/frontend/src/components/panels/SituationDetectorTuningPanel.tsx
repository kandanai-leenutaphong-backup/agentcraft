/**
 * SituationDetectorTuningPanel \u2014 operator UI for the situation detector
 * config draft, sensitivity sliders, and dry-run comparison.
 *
 * Role:
 *   Renders the editable view of `situationStore.detectorDraft`: lists alarm
 *   patches and SCADA patches, exposes per-category sensitivity pills
 *   (conservative / balanced / sensitive) that scale thresholds and counts,
 *   and triggers `runDetectorComparison()` to preview the draft against the
 *   current situation set without saving.
 *
 *   Edits stage onto the draft via `setDetectorDraft`; `saveDetectorConfig`
 *   commits, `resetDetectorConfig` reverts. The panel never mutates a
 *   detector run directly \u2014 it is a thin editor over the store.
 *
 * Key collaborators:
 *   - stores/situationStore.ts        \u2014 detectorConfig / detectorDraft state +
 *                                       saveDetectorConfig / runDetectorComparison
 *   - api/situationApi.ts             \u2014 AlarmSignalPatch / ScadaSignalPatch types
 *   - components/panels/Workspace.tsx — sole consumer (renders inside the
 *                                       "Detector Tuning" workspace mode;
 *                                       replaced CenterTabs in C1, 2026-05-17)
 *
 * Notes:
 *   - SENSITIVITY_OPTIONS scaling rules live at the top of this file; the
 *     `tunedThreshold` and `tunedCount` helpers are the source of truth for
 *     what each sensitivity pill does.
 */

import { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Plus, RotateCcw, SlidersHorizontal, Trash2 } from "lucide-react";
import type { AlarmSignalPatch, ScadaSignalPatch } from "@/api/situationApi";
import { useSituationStore } from "@/stores/situationStore";

const ALARM_COLUMNS = ["alarm_label", "alarm_text", "client_composite_id", "priority"] as const;
const ALARM_OPS = ["==", "contains"] as const;
const SCADA_MEASUREMENTS = ["MW", "MVAR", "KV", "MVA", "HZ", "FREQ"] as const;

type SignalKind = "alarm" | "scada";
type Sensitivity = "conservative" | "balanced" | "sensitive";
type CategoryId = "bus_voltage" | "generator" | "line_transformer" | "alarm_evidence" | "overall_severity";
type ScadaConditionType = NonNullable<ScadaSignalPatch["cond_type"]>;

interface CategoryDefinition {
  id: CategoryId;
  label: string;
  summary: string;
}

interface ScadaConditionDefinition {
  value: ScadaConditionType;
  label: string;
  sentence: string;
  thresholdLabel: string;
  defaultThreshold: number;
  usesDirection?: boolean;
  baselineLabel?: string;
  defaultBaseline?: number;
}

const CATEGORIES: CategoryDefinition[] = [
  { id: "bus_voltage", label: "Bus / voltage", summary: "Voltage collapse and bus movement" },
  { id: "generator", label: "Generator", summary: "Trips, derating, and motoring" },
  { id: "line_transformer", label: "Line / transformer", summary: "Network flows and loading" },
  { id: "alarm_evidence", label: "Alarm evidence", summary: "Alarm count and impact" },
  { id: "overall_severity", label: "Overall severity", summary: "Investigation, serious, major, critical" },
];

const SENSITIVITY_OPTIONS: { value: Sensitivity; label: string }[] = [
  { value: "conservative", label: "Conservative" },
  { value: "balanced", label: "Balanced" },
  { value: "sensitive", label: "Sensitive" },
];

const SCADA_CONDITION_TYPES: ScadaConditionDefinition[] = [
  { value: "change_percent", label: "Percent change", sentence: "changes by", thresholdLabel: "Change %", defaultThreshold: 30, usesDirection: true },
  { value: "change_absolute", label: "Absolute change", sentence: "changes by", thresholdLabel: "Change amount", defaultThreshold: 5, usesDirection: true },
  { value: "drops_below", label: "Drops below threshold", sentence: "drops below", thresholdLabel: "Below", defaultThreshold: 1, baselineLabel: "from at least", defaultBaseline: 5 },
  { value: "rises_above", label: "Rises above threshold", sentence: "rises above", thresholdLabel: "Above", defaultThreshold: 100, baselineLabel: "from at most", defaultBaseline: 10 },
  { value: "drops_to_near_zero", label: "Drops to near zero", sentence: "drops to near zero", thresholdLabel: "Near zero", defaultThreshold: 1, baselineLabel: "from at least", defaultBaseline: 10 },
];

const SCADA_DIRECTIONS = [
  { value: "any", label: "Either" },
  { value: "up", label: "Up" },
  { value: "down", label: "Down" },
] as const;

const DEFAULT_ALARM_SIGNAL: AlarmSignalPatch = {
  id: "new_alarm_signal",
  col: "alarm_label",
  op: "contains",
  val: "",
  points: 1,
};

const DEFAULT_SCADA_SIGNAL: ScadaSignalPatch = {
  id: "new_scada_signal",
  tag_contains: [".BUS."],
  meas: "MW",
  cond_type: "change_percent",
  direction: "any",
  threshold: 30,
  points: 1,
};

const FALLBACK_ALARM_SIGNALS: AlarmSignalPatch[] = [
  { id: "cb_trip", col: "alarm_label", op: "==", val: "CB", points: 1 },
  { id: "kv_emer_bus", col: "alarm_label", op: "contains", val: "KV-EMER", points: 2, extra_col: "client_composite_id", extra_op: "contains", extra_val: ".BUS." },
  { id: "br_ldsh", col: "alarm_label", op: "contains", val: "BR-LDSH", points: 3 },
];

const FALLBACK_SCADA_SIGNALS: ScadaSignalPatch[] = [
  { id: "bus_collapse", tag_contains: [".BUS."], meas: "KV", cond_type: "drops_below", threshold: 2, baseline: 10, points: 4 },
  { id: "gen_trip", tag_contains: [".GEN.", ".UNIT."], meas: "MW", cond_type: "drops_to_near_zero", threshold: 1, baseline: 5, points: 3 },
  { id: "line_overload", tag_contains: [".LINE."], meas: "MVA", cond_type: "change_percent", direction: "up", threshold: 30, points: 1 },
  { id: "transformer_trip", tag_contains: [".TRANS."], meas: "MW", cond_type: "drops_to_near_zero", threshold: 1, baseline: 10, points: 3 },
];

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function asAlarmSignals(value: unknown): AlarmSignalPatch[] {
  return asRecordArray(value)
    .filter((item) => typeof item.id === "string")
    .map((item) => ({ ...item })) as unknown as AlarmSignalPatch[];
}

function asScadaSignals(value: unknown): ScadaSignalPatch[] {
  return asRecordArray(value)
    .filter((item) => typeof item.id === "string")
    .map((item) => ({ ...item })) as unknown as ScadaSignalPatch[];
}

function upsertById<T extends { id: string }>(items: T[] | undefined, next: T): T[] {
  const current = items ?? [];
  const index = current.findIndex((item) => item.id === next.id);
  if (index === -1) return [...current, next];
  return current.map((item, itemIndex) => (itemIndex === index ? next : item));
}

function applyPatches<T extends { id: string; enabled?: boolean }>(base: T[], patches: T[] | undefined): T[] {
  const byId = new Map(base.map((item) => [item.id, { ...item }]));
  const order = base.map((item) => item.id);
  for (const patch of patches ?? []) {
    if (patch.enabled === false) {
      byId.delete(patch.id);
      continue;
    }
    const existing = byId.get(patch.id);
    if (!existing) order.push(patch.id);
    byId.set(patch.id, { ...(existing ?? {}), ...patch });
  }
  return order.map((id) => byId.get(id)).filter((item): item is T => Boolean(item));
}

function signalId(base: string, signals: { id: string }[]): string {
  const ids = new Set(signals.map((signal) => signal.id));
  if (!ids.has(base)) return base;
  let index = 2;
  while (ids.has(`${base}_${index}`)) index += 1;
  return `${base}_${index}`;
}

function scadaConditionType(signal: ScadaSignalPatch): ScadaConditionType {
  if (signal.cond_type) return signal.cond_type;
  if (signal.cond?.includes("Value > prev_val")) return "change_percent";
  if (signal.cond?.includes("abs(Value)")) return "drops_to_near_zero";
  if (signal.cond?.includes("Value <")) return "drops_below";
  if (signal.cond?.includes("Value >")) return "rises_above";
  return "change_percent";
}

function scadaConditionDefinition(type: ScadaConditionType) {
  return SCADA_CONDITION_TYPES.find((condition) => condition.value === type) ?? SCADA_CONDITION_TYPES[0];
}

function defaultConditionPatch(type: ScadaConditionType): Partial<ScadaSignalPatch> {
  const definition = scadaConditionDefinition(type);
  return {
    cond_type: type,
    direction: definition.usesDirection ? "any" : undefined,
    threshold: definition.defaultThreshold,
    baseline: definition.defaultBaseline,
  };
}

function signalText(signal: ScadaSignalPatch): string {
  const tags = `${signal.id} ${(signal.tag_contains ?? []).join(" ")}`.toLowerCase();
  if (tags.includes("bus") || tags.includes(".bus.") || tags.includes("kv")) return "bus voltage";
  if (tags.includes("gen") || tags.includes("unit")) return "generator output";
  if (tags.includes("trans")) return "transformer flow";
  if (tags.includes("line")) return "line flow";
  return "SCADA value";
}

function signalCategory(signal: ScadaSignalPatch): CategoryId {
  const tags = `${signal.id} ${(signal.tag_contains ?? []).join(" ")}`.toLowerCase();
  if (tags.includes("bus") || tags.includes(".bus.") || tags.includes("kv")) return "bus_voltage";
  if (tags.includes("gen") || tags.includes("unit")) return "generator";
  if (tags.includes("line") || tags.includes("trans")) return "line_transformer";
  return "line_transformer";
}

function impactFromPoints(points?: number): "low" | "medium" | "high" | "critical" {
  const value = points ?? 1;
  if (value >= 5) return "critical";
  if (value >= 3) return "high";
  if (value >= 2) return "medium";
  return "low";
}

function pointsFromImpact(impact: string): number {
  if (impact === "critical") return 5;
  if (impact === "high") return 4;
  if (impact === "medium") return 2;
  return 1;
}

function tunedPoints(points: number | undefined, sensitivity: Sensitivity): number {
  const current = points ?? 1;
  if (sensitivity === "sensitive") return Math.min(8, current + 1);
  if (sensitivity === "conservative") return Math.max(1, current - 1);
  return current;
}

function tunedThreshold(threshold: number | undefined, sensitivity: Sensitivity): number | undefined {
  if (threshold == null) return threshold;
  if (sensitivity === "sensitive") return Number(Math.max(0, threshold * 0.8).toFixed(2));
  if (sensitivity === "conservative") return Number((threshold * 1.25).toFixed(2));
  return threshold;
}

export function SituationDetectorTuningPanel() {
  const loadDetectorConfig = useSituationStore((s) => s.loadDetectorConfig);
  const detectorConfig = useSituationStore((s) => s.detectorConfig);
  const detectorDraft = useSituationStore((s) => s.detectorDraft);
  const detectorDirty = useSituationStore((s) => s.detectorDirty);
  const detectorSaving = useSituationStore((s) => s.detectorSaving);
  const setDetectorDraft = useSituationStore((s) => s.setDetectorDraft);
  const saveDetectorConfig = useSituationStore((s) => s.saveDetectorConfig);
  const resetDetectorConfig = useSituationStore((s) => s.resetDetectorConfig);
  const detectorComparison = useSituationStore((s) => s.detectorComparison);
  const runDetectorComparison = useSituationStore((s) => s.runDetectorComparison);
  const situations = useSituationStore((s) => s.situations);
  const error = useSituationStore((s) => s.error);
  const [activeSignalKind, setActiveSignalKind] = useState<SignalKind>("alarm");
  const [activeCategory, setActiveCategory] = useState<CategoryId>("bus_voltage");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  /* Track the most-recently-applied sensitivity per category so the
     pill that was clicked stays visibly selected. Without this the
     operator cannot tell which sensitivity is currently shaping the
     draft (audit F-008). */
  const [activeSensitivity, setActiveSensitivity] = useState<Record<CategoryId, Sensitivity | null>>({
    overall_severity: null,
    alarm_evidence: null,
    bus_voltage: null,
    generator: null,
    line_transformer: null,
  });

  useEffect(() => {
    if (!detectorConfig) void loadDetectorConfig();
  }, [detectorConfig, loadDetectorConfig]);

  const loadedAlarmSignals = asAlarmSignals(detectorConfig?.effective_config.alarm_signals);
  const loadedScadaSignals = asScadaSignals(detectorConfig?.effective_config.scada_signals);
  const baseAlarmSignals = loadedAlarmSignals.length ? loadedAlarmSignals : FALLBACK_ALARM_SIGNALS;
  const baseScadaSignals = loadedScadaSignals.length ? loadedScadaSignals : FALLBACK_SCADA_SIGNALS;
  const alarmSignals = applyPatches(baseAlarmSignals, detectorDraft.alarm_signals);
  const scadaSignals = applyPatches(baseScadaSignals, detectorDraft.scada_signals);
  const activeScadaSignals = scadaSignals.filter((signal) => signalCategory(signal) === activeCategory);
  const severityThresholds = detectorConfig?.effective_config.severity_thresholds as Record<string, number> | undefined;

  const updateAlarmSignal = (signal: AlarmSignalPatch) => {
    setDetectorDraft({ alarm_signals: upsertById(detectorDraft.alarm_signals, signal) });
  };

  const updateScadaSignal = (signal: ScadaSignalPatch) => {
    setDetectorDraft({ scada_signals: upsertById(detectorDraft.scada_signals, signal) });
  };

  const removeAlarmSignal = (signal: AlarmSignalPatch) => {
    setDetectorDraft({ alarm_signals: upsertById(detectorDraft.alarm_signals, { id: signal.id, enabled: false }) });
  };

  const removeScadaSignal = (signal: ScadaSignalPatch) => {
    setDetectorDraft({ scada_signals: upsertById(detectorDraft.scada_signals, { id: signal.id, enabled: false }) });
  };

  const addAlarmSignal = () => {
    updateAlarmSignal({ ...DEFAULT_ALARM_SIGNAL, id: signalId("new_alarm_signal", alarmSignals), enabled: true });
    setActiveSignalKind("alarm");
  };

  const addScadaSignal = () => {
    updateScadaSignal({ ...DEFAULT_SCADA_SIGNAL, id: signalId("new_scada_signal", scadaSignals), enabled: true });
    setActiveSignalKind("scada");
  };

  const applyCategorySensitivity = (categoryId: CategoryId, sensitivity: Sensitivity) => {
    setActiveSensitivity((prev) => ({ ...prev, [categoryId]: sensitivity }));
    if (categoryId === "overall_severity") {
      const defaults = { investigate: 5, serious: 8, major: 12, critical: 20, ...(severityThresholds ?? {}) };
      const factor = sensitivity === "sensitive" ? 0.85 : sensitivity === "conservative" ? 1.15 : 1;
      setDetectorDraft({
        severity_thresholds: {
          investigate: Math.max(1, Math.round(defaults.investigate * factor)),
          serious: Math.max(1, Math.round(defaults.serious * factor)),
          major: Math.max(1, Math.round(defaults.major * factor)),
          critical: Math.max(1, Math.round(defaults.critical * factor)),
        },
      });
      return;
    }

    if (categoryId === "alarm_evidence") {
      const next = alarmSignals.map((signal) => ({ ...signal, points: tunedPoints(signal.points, sensitivity) }));
      setDetectorDraft({ alarm_signals: next });
      return;
    }

    const next = scadaSignals
      .filter((signal) => signalCategory(signal) === categoryId)
      .map((signal) => ({
        ...signal,
        enabled: true,
        points: tunedPoints(signal.points, sensitivity),
        threshold: tunedThreshold(signal.threshold, sensitivity),
      }));
    setDetectorDraft({ scada_signals: next.reduce((patches, signal) => upsertById(patches, signal), detectorDraft.scada_signals ?? []) });
  };

  return (
    <div data-testid="situation-detector-tuning-panel" className="h-full flex flex-col bg-neutral-bg1">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-neutral-bg2 shrink-0">
        <SlidersHorizontal className="h-4 w-4 text-brand" />
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-text-primary">Situation Detector Tuning</h2>
          <p className="text-xs text-text-muted truncate">
            cfg {detectorConfig?.config_hash ?? "loading"} · {detectorConfig?.source ?? "default"}
            {detectorDirty ? " · not applied" : " · applied"}
          </p>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <section data-testid="tuning-editor-region" className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
          {error && <div className="px-3 py-2 rounded bg-status-error-surface text-status-error text-xs">{error}</div>}

          <section className="border border-border rounded p-3" data-testid="outcome-tuning-overview">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Outcome tuning</h3>
                <p className="text-xs text-text-muted">Tune operational categories first; technical fields live under Advanced.</p>
              </div>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-5 gap-2">
              {CATEGORIES.map((category) => {
                const active = activeCategory === category.id;
                const count = category.id === "alarm_evidence" ? alarmSignals.length : category.id === "overall_severity" ? 4 : scadaSignals.filter((signal) => signalCategory(signal) === category.id).length;
                return (
                  <button
                    key={category.id}
                    type="button"
                    onClick={() => setActiveCategory(category.id)}
                    className={`text-left rounded border px-3 py-2 ${active ? "border-brand bg-brand/10" : "border-border hover:bg-neutral-bg2"}`}
                  >
                    <span className="block text-xs font-semibold text-text-primary">{category.label}</span>
                    <span className="block text-label text-text-muted mt-0.5">{category.summary}</span>
                    <span className="block text-label text-text-secondary mt-1">{count} controls</span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 flex items-center gap-2 rounded bg-neutral-bg2 p-1 w-fit" data-testid="category-sensitivity-controls">
              {SENSITIVITY_OPTIONS.map((option) => {
                const isActive = activeSensitivity[activeCategory] === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    data-testid={`sensitivity-option-${option.value}`}
                    data-active={isActive ? "true" : "false"}
                    aria-pressed={isActive}
                    onClick={() => applyCategorySensitivity(activeCategory, option.value)}
                    className={`px-3 py-1.5 rounded text-xs transition-colors ${
                      isActive ? "bg-brand/15 text-brand" : "text-text-secondary hover:bg-neutral-bg1 hover:text-text-primary"
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="border border-border rounded p-3" data-testid="plain-english-rule-editor">
            <div className="flex items-center justify-between gap-2 mb-2">
              <h3 className="text-sm font-semibold text-text-primary">{CATEGORIES.find((category) => category.id === activeCategory)?.label} rules</h3>
              <span className="text-xs text-text-muted">Plain-English editing</span>
            </div>

            {activeCategory === "overall_severity" ? (
              <div className="grid grid-cols-4 gap-2">
                {(["investigate", "serious", "major", "critical"] as const).map((threshold) => (
                  <label key={threshold} className="text-xs text-text-secondary capitalize">
                    {threshold}
                    <input
                      type="number"
                      value={detectorDraft.severity_thresholds?.[threshold] ?? severityThresholds?.[threshold] ?? 0}
                      onChange={(event) => setDetectorDraft({ severity_thresholds: { ...(detectorDraft.severity_thresholds ?? {}), [threshold]: Number(event.target.value) } })}
                      className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none"
                    />
                  </label>
                ))}
              </div>
            ) : activeCategory === "alarm_evidence" ? (
              <div className="space-y-2">
                {alarmSignals.map((signal) => (
                  <div key={signal.id} className="flex flex-wrap items-center gap-2 rounded bg-neutral-bg2 px-3 py-2 text-xs" data-testid={`plain-alarm-rule-${signal.id}`}>
                    <span>When alarm {signal.col === "alarm_text" ? "text" : signal.col === "priority" ? "priority" : "label"}</span>
                    <span className="font-medium text-text-primary">{signal.op === "==" ? "matches" : "contains"}</span>
                    <input value={signal.val ?? ""} onChange={(event) => updateAlarmSignal({ ...signal, val: event.target.value })} className="w-28 px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={`Alarm value ${signal.id}`} />
                    <span>at least</span>
                    <input type="number" value={signal.min_count ?? 1} onChange={(event) => updateAlarmSignal({ ...signal, min_count: Number(event.target.value) })} className="w-16 px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={`Alarm count ${signal.id}`} />
                    <span>time, mark as</span>
                    <select value={impactFromPoints(signal.points)} onChange={(event) => updateAlarmSignal({ ...signal, points: pointsFromImpact(event.target.value) })} className="px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={`Alarm impact ${signal.id}`}>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="critical">Critical</option>
                    </select>
                    <span>impact.</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {activeScadaSignals.map((signal) => {
                  const conditionType = scadaConditionType(signal);
                  const definition = scadaConditionDefinition(conditionType);
                  return (
                    <div key={signal.id} className="flex flex-wrap items-center gap-2 rounded bg-neutral-bg2 px-3 py-2 text-xs" data-testid={`plain-scada-rule-${signal.id}`}>
                      <span>When</span>
                      <span className="font-medium text-text-primary">{signalText(signal)}</span>
                      <select value={signal.meas ?? "MW"} onChange={(event) => updateScadaSignal({ ...signal, meas: event.target.value })} className="px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={`Measurement ${signal.id}`}>
                        {SCADA_MEASUREMENTS.map((measurement) => <option key={measurement} value={measurement}>{measurement}</option>)}
                      </select>
                      <select value={conditionType} onChange={(event) => updateScadaSignal({ ...signal, ...defaultConditionPatch(event.target.value as ScadaConditionType) })} className="px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={`Condition ${signal.id}`}>
                        {SCADA_CONDITION_TYPES.map((condition) => <option key={condition.value} value={condition.value}>{condition.sentence}</option>)}
                      </select>
                      <input type="number" value={signal.threshold ?? definition.defaultThreshold} onChange={(event) => updateScadaSignal({ ...signal, threshold: Number(event.target.value) })} className="w-20 px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={definition.thresholdLabel} />
                      {definition.baselineLabel && (
                        <>
                          <span>{definition.baselineLabel}</span>
                          <input type="number" value={signal.baseline ?? definition.defaultBaseline ?? 0} onChange={(event) => updateScadaSignal({ ...signal, baseline: Number(event.target.value) })} className="w-20 px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={definition.baselineLabel} />
                        </>
                      )}
                      <span>mark as</span>
                      <select value={impactFromPoints(signal.points)} onChange={(event) => updateScadaSignal({ ...signal, points: pointsFromImpact(event.target.value) })} className="px-2 py-1 rounded bg-neutral-bg1 text-text-primary focus:outline-none" aria-label={`Impact ${signal.id}`}>
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="critical">Critical</option>
                      </select>
                      <span>impact.</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="border border-border rounded" data-testid="advanced-detector-editor">
            <button type="button" onClick={() => setAdvancedOpen((open) => !open)} className="w-full flex items-center justify-between px-3 py-2 text-sm font-semibold text-text-primary">
              <span>Advanced</span>
              {advancedOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
            {advancedOpen && (
              <div className="border-t border-border">
                <div className="px-3 py-2 text-xs text-warning bg-warning/10">Advanced detector fields affect matching and scoring directly. Reset defaults if tuning drifts too far.</div>
                <div className="border-t border-border" data-testid="detector-signal-editor">
                  <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
                    <div className="flex items-center gap-1 rounded bg-neutral-bg2 p-1">
                      <button type="button" onClick={() => setActiveSignalKind("alarm")} className={`px-2 py-1 rounded text-xs ${activeSignalKind === "alarm" ? "bg-neutral-bg1 text-text-primary" : "text-text-muted"}`}>Alarm signals ({alarmSignals.length})</button>
                      <button type="button" onClick={() => setActiveSignalKind("scada")} className={`px-2 py-1 rounded text-xs ${activeSignalKind === "scada" ? "bg-neutral-bg1 text-text-primary" : "text-text-muted"}`}>SCADA signals ({scadaSignals.length})</button>
                    </div>
                    <button type="button" onClick={activeSignalKind === "alarm" ? addAlarmSignal : addScadaSignal} className="flex items-center gap-1 px-2 py-1 rounded bg-brand/15 text-brand text-xs font-medium">
                      <Plus className="h-3.5 w-3.5" />
                      Add {activeSignalKind === "alarm" ? "alarm" : "SCADA"}
                    </button>
                  </div>

                  <div className="divide-y divide-border/60">
                    {activeSignalKind === "alarm" ? alarmSignals.map((signal) => (
                      <div key={signal.id} className="p-3 space-y-2" data-testid={`alarm-signal-${signal.id}`}>
                        <div className="grid grid-cols-[1.1fr_0.8fr_0.8fr_1.4fr_0.6fr_0.7fr_auto] gap-2 items-end">
                          <label className="text-xs text-text-secondary">ID<input value={signal.id} onChange={(event) => updateAlarmSignal({ ...signal, id: event.target.value })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded font-mono text-text-primary focus:outline-none" /></label>
                          <label className="text-xs text-text-secondary">Column<select value={signal.col ?? "alarm_label"} onChange={(event) => updateAlarmSignal({ ...signal, col: event.target.value as AlarmSignalPatch["col"] })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none">{ALARM_COLUMNS.map((column) => <option key={column} value={column}>{column}</option>)}</select></label>
                          <label className="text-xs text-text-secondary">Op<select value={signal.op ?? "contains"} onChange={(event) => updateAlarmSignal({ ...signal, op: event.target.value as AlarmSignalPatch["op"] })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none">{ALARM_OPS.map((op) => <option key={op} value={op}>{op}</option>)}</select></label>
                          <label className="text-xs text-text-secondary">Value<input value={signal.val ?? ""} onChange={(event) => updateAlarmSignal({ ...signal, val: event.target.value })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label>
                          <label className="text-xs text-text-secondary">Points<input type="number" value={signal.points ?? 0} onChange={(event) => updateAlarmSignal({ ...signal, points: Number(event.target.value) })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label>
                          <label className="text-xs text-text-secondary">Min count<input type="number" value={signal.min_count ?? ""} onChange={(event) => updateAlarmSignal({ ...signal, min_count: event.target.value ? Number(event.target.value) : undefined })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label>
                          <button type="button" onClick={() => removeAlarmSignal(signal)} className="h-7 w-7 flex items-center justify-center rounded text-text-muted hover:text-status-error hover:bg-status-error-surface" aria-label={`Remove ${signal.id}`}><Trash2 className="h-3.5 w-3.5" /></button>
                        </div>
                      </div>
                    )) : scadaSignals.map((signal) => {
                      const conditionType = scadaConditionType(signal);
                      const definition = scadaConditionDefinition(conditionType);
                      return (
                        <div key={signal.id} className="p-3 space-y-2" data-testid={`scada-signal-${signal.id}`}>
                          <div className="grid grid-cols-[1.1fr_1.4fr_0.7fr_0.6fr_auto] gap-2 items-end">
                            <label className="text-xs text-text-secondary">ID<input value={signal.id} onChange={(event) => updateScadaSignal({ ...signal, id: event.target.value })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded font-mono text-text-primary focus:outline-none" /></label>
                            <label className="text-xs text-text-secondary">Tag contains<input value={(signal.tag_contains ?? []).join(", ")} onChange={(event) => updateScadaSignal({ ...signal, tag_contains: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label>
                            <label className="text-xs text-text-secondary">Meas<select value={signal.meas ?? "MW"} onChange={(event) => updateScadaSignal({ ...signal, meas: event.target.value })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none">{SCADA_MEASUREMENTS.map((measurement) => <option key={measurement} value={measurement}>{measurement}</option>)}</select></label>
                            <label className="text-xs text-text-secondary">Points<input type="number" value={signal.points ?? 0} onChange={(event) => updateScadaSignal({ ...signal, points: Number(event.target.value) })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label>
                            <button type="button" onClick={() => removeScadaSignal(signal)} className="h-7 w-7 flex items-center justify-center rounded text-text-muted hover:text-status-error hover:bg-status-error-surface" aria-label={`Remove ${signal.id}`}><Trash2 className="h-3.5 w-3.5" /></button>
                          </div>
                          <div className="grid grid-cols-[1.4fr_0.8fr_0.8fr_0.8fr] gap-2 items-end">
                            <label className="text-xs text-text-secondary">Condition<select value={conditionType} onChange={(event) => updateScadaSignal({ ...signal, ...defaultConditionPatch(event.target.value as ScadaConditionType) })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none">{SCADA_CONDITION_TYPES.map((condition) => <option key={condition.value} value={condition.value}>{condition.label}</option>)}</select></label>
                            {definition.usesDirection ? <label className="text-xs text-text-secondary">Direction<select value={signal.direction ?? "any"} onChange={(event) => updateScadaSignal({ ...signal, direction: event.target.value as ScadaSignalPatch["direction"] })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none">{SCADA_DIRECTIONS.map((direction) => <option key={direction.value} value={direction.value}>{direction.label}</option>)}</select></label> : <div />}
                            <label className="text-xs text-text-secondary">{definition.thresholdLabel}<input type="number" value={signal.threshold ?? definition.defaultThreshold} onChange={(event) => updateScadaSignal({ ...signal, threshold: Number(event.target.value) })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label>
                            {definition.baselineLabel ? <label className="text-xs text-text-secondary">{definition.baselineLabel}<input type="number" value={signal.baseline ?? definition.defaultBaseline ?? 0} onChange={(event) => updateScadaSignal({ ...signal, baseline: Number(event.target.value) })} className="mt-1 w-full px-2 py-1 bg-neutral-bg2 rounded text-text-primary focus:outline-none" /></label> : <div />}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </section>

          <div data-testid="detector-comparison-panel" className="border border-border rounded p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <h3 className="text-sm font-semibold text-text-primary">Draft impact</h3>
              {/* Preview-impact button — wires the previously-orphaned
                  `runDetectorComparison` store action to a visible affordance
                  (audit F-014). Disabled when there is no draft to compare. */}
              <button
                type="button"
                data-testid="preview-impact-button"
                disabled={!detectorDirty}
                onClick={() => void runDetectorComparison()}
                className="px-2 py-1 text-xs font-medium rounded bg-brand/15 text-brand hover:bg-brand/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Preview impact
              </button>
            </div>
            {detectorComparison ? (
              <div className="space-y-2 text-xs">
                <div className="grid grid-cols-3 gap-2 text-text-muted">
                  <span>Matched {detectorComparison.matched}</span>
                  <span>Missed {detectorComparison.missed}</span>
                  <span>Severity shifts {detectorComparison.severity_mismatches}</span>
                </div>
                {detectorComparison.rows.map((row) => (
                  <div key={row.id} className="grid grid-cols-3 gap-2 border-t border-border/50 pt-2">
                    <span className="font-medium text-text-primary">{row.label}</span>
                    <span>{row.current}</span>
                    <span>{row.draft}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-text-muted">Impact details appear here when detector results are available for the active scan window.</p>
            )}
          </div>

          <div data-testid="score-explanation-panel" className="border border-border rounded p-3">
            <h3 className="text-sm font-semibold text-text-primary mb-2">Why detected</h3>
            {situations[0] ? (
              <div className="grid grid-cols-4 gap-2 text-xs">
                <div>Alarm<br /><span className="font-mono text-text-primary">{situations[0].alarm_score}</span></div>
                <div>SCADA<br /><span className="font-mono text-text-primary">{situations[0].scada_score}</span></div>
                <div>MW<br /><span className="font-mono text-text-primary">{situations[0].mw_boost}</span></div>
                <div>Pattern<br /><span className="font-mono text-text-primary">{situations[0].patterns || "none"}</span></div>
              </div>
            ) : (
              <p className="text-xs text-text-muted">Scan results populate score contributors after detector output is available.</p>
            )}
          </div>
        </section>
      </div>

      <div className="flex items-center justify-end gap-2 px-4 py-2 border-t border-border bg-neutral-bg2 shrink-0">
        {detectorDirty && (
          <span className="mr-auto text-xs text-text-muted">Apply settings before scanning to update the detector config.</span>
        )}
        <button type="button" disabled={detectorSaving} onClick={() => void resetDetectorConfig()} className="flex items-center gap-1 px-3 py-1.5 rounded bg-neutral-bg1 text-xs text-text-secondary hover:text-text-primary disabled:opacity-50"><RotateCcw className="h-3.5 w-3.5" />Reset defaults</button>
        <button
          data-testid="apply-detector-config-button"
          type="button"
          disabled={detectorSaving || !detectorDirty}
          onClick={() => void saveDetectorConfig()}
          className="flex items-center gap-1 px-3 py-1.5 rounded bg-brand text-on-accent text-xs font-semibold hover:bg-brand/80 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          {detectorSaving ? "Applying" : "Apply settings"}
        </button>
      </div>
    </div>
  );
}
