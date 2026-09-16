/**
 * Tool result renderer dispatcher.
 *
 * Maps tool names to specialised React renderers + per-tool render hints.
 * Each tool type gets a purpose-built display component optimised for
 * its result shape and a `<ToolResultCard>` scaffold-conforming layout
 * (see ToolResultCard.tsx).
 *
 * Registries exposed:
 *   - TOOL_RENDERERS         → name → result renderer component
 *   - TOOL_ARGS_RENDERERS    → name → arguments renderer component
 *   - TOOL_PROMINENT_COLUMNS → name → ResultTable `prominentColumns` hint
 *   - JSON_FALLBACK_ALLOWLIST → tool names that are JSON-by-design (test invariant)
 *
 * Adding a renderer for a new tool:
 *   1. Create a component in this directory consuming `<ToolResultCard>`.
 *   2. Register it in TOOL_RENDERERS below.
 *   3. (optional) Add a TOOL_PROMINENT_COLUMNS entry to tag salient columns.
 *   4. (optional) Add a TOOL_ARGS_RENDERERS entry for a custom args view.
 *
 * Invariant (asserted by the registry-coverage vitest):
 *   Every tool name that ships in `control/agent_config.yaml` (the active
 *   surface) MUST resolve to a non-`JsonFallback` renderer unless it
 *   appears in `JSON_FALLBACK_ALLOWLIST`.
 */

import type { ComponentType } from "react";
import { TabularResult } from "./TabularResult";
import { MultiTableResult } from "./MultiTableResult";
import { GraphResult } from "./GraphResult";
import { GraphEnvelopeResult } from "./GraphEnvelopeResult";
import { SearchResultCards } from "./SearchResultCards";
import { DelegationResult } from "./DelegationResult";
import { SituationResult } from "./SituationResult";
import { AuditReportResult } from "./AuditReportResult";
import { JsonFallback } from "./JsonFallback";
import { PanelToolSummary } from "./PanelToolSummary";
import { StatusResult } from "./StatusResult";
import { EntityEventsResult } from "./EntityEventsResult";
import { SchemaContextResult, VerifyStateResult } from "./DocumentResult";
import { ClassificationResult } from "./ClassificationResult";
import { TimelineCausalResult } from "./TimelineCausalResult";
import { BusZoneAuditResult } from "./BusZoneAuditResult";
import { BreakerFailSignatureResult } from "./BreakerFailSignatureResult";
import { FrequencyDisturbanceResult } from "./FrequencyDisturbanceResult";

export { ArgumentsGrid } from "./ArgumentsGrid";
export { ToolResultCard } from "./ToolResultCard";
export { ResultTable } from "./ResultTable";

/** Props shared by all result renderers. */
export interface ToolResultProps {
  result: string;
  /**
   * Tool name as it appears in the SSE stream. Threaded by ToolCallDisplay
   * so renderers can resolve registry hints (e.g. PanelToolSummary's
   * label, ResultTable's prominent-column hint) without re-parsing the
   * envelope. Optional for backward compatibility.
   */
  toolName?: string;
}

/**
 * Registry mapping tool names to their result renderer component.
 */
const TOOL_RENDERERS: Record<string, ComponentType<ToolResultProps>> = {
  /* Watcher KQL tools — return {columns: [{name,type}], rows: [{}]} */
  find_asset: TabularResult,
  find_station_assets: TabularResult,
  find_alarms: TabularResult,
  find_alerts: TabularResult,
  find_scada: MultiTableResult,
  find_surveillance: TabularResult,
  find_traffic: TabularResult,
  find_alarm_by_mrid: TabularResult,
  find_connected_stations: TabularResult,
  find_scada_changes: TabularResult,
  find_event_timeline: TabularResult,
  find_station_summary: TabularResult,
  pattern_history: TabularResult,

  /* Raw KQL fallback — same tabular shape */
  query_kql: TabularResult,

  /* KQL semantic-layer summary tools (R5: route to TabularResult). */
  get_scada_readings: TabularResult,
  get_scada_timeline: TabularResult,
  summarize_scada: TabularResult,
  get_scada_extremes: TabularResult,
  get_alarm_sequence: TabularResult,
  summarize_alarms: TabularResult,

  /* Graph CIM topology tools — return JSON arrays of objects */
  graph_node: GraphResult,
  graph_neighbors: GraphResult,
  graph_station_neighbors: GraphResult,

  /* Raw Gremlin fallback — returns JSON array */
  query_gremlin: GraphResult,

  /* GQL semantic-layer (R5: route to GraphResult). */
  get_nodes: GraphResult,
  get_neighbors: GraphResult,
  get_node_properties: GraphResult,
  find_path: GraphResult,
  count_nodes: GraphResult,
  get_edges: GraphResult,
  aggregate: GraphResult,
  lookup_entity: GraphResult,

  /* New graph primitives */
  graph_station_equipment: GraphResult,
  graph_equipment_properties: GraphResult,
  graph_equipment_connections: GraphResult,
  graph_bus_topology: GraphResult,
  graph_property_keys: JsonFallback,

  /* Graph extras — typed envelopes { scope, summary, lists… } */
  graph_bus_boundary: GraphEnvelopeResult,
  graph_corridor_endpoints: GraphEnvelopeResult,
  graph_breaker_neighbourhood: GraphEnvelopeResult,
  graph_common_mode_devices: GraphEnvelopeResult,
  graph_switch_state_snapshot: GraphEnvelopeResult,

  /* Situation detector — returns {situations: [...], count: N} */
  detect_situations: SituationResult,

  /* Search tools — return {results: [{title, source, score, text}], count} */
  search_operator_manual: SearchResultCards,
  search_knowledge_base: SearchResultCards,
  search_incident_reports: SearchResultCards,
  search_nearhit_reports: SearchResultCards,
  search_callide_lessons: SearchResultCards,
  search_investigation_clues: SearchResultCards,
  search_paws: SearchResultCards,
  search_participants: SearchResultCards,
  search_procedures: SearchResultCards,
  search_station_contacts: SearchResultCards,
  search_smirks: SearchResultCards,
  web_search: SearchResultCards,

  /* Delegation — specialist agent response with markdown body */
  delegate_to_agent: DelegationResult,

  /* Push action — confirmed via compact panel badge */
  push_action: PanelToolSummary,
  push_priority_action: PanelToolSummary,
  /* `classify` (grid_manager's NER 4.2.3 verdict, renamed from
     `push_classifier_verdict` on 2026-05-18) — typed verdict card
     wired by Couturier audit specs/couturier_20260518_tool_renderers_phase1_and_naming.md. */
  classify: ClassificationResult,
  set_investigation_plan: PanelToolSummary,
  summarize_situation: PanelToolSummary,

  /* GridIQ panel tools — show compact badge, data renders in panels */
  update_disturbance_summary: PanelToolSummary,
  update_operating_state: PanelToolSummary,
  update_priority_actions: PanelToolSummary,

  /* Auditor terminal write tool — compact inline summary; full report
     renders in the SessionAuditPanel (System Evaluations tab). */
  submit_audit_report: AuditReportResult,

  /* R5: action tools that signal status, not data → StatusResult. */
  dispatch_field_engineer: StatusResult,
  call_engineer: StatusResult,
  send_incident_report: StatusResult,
  report_normal: StatusResult,
  push_situation_alert: StatusResult,

  /* R5: entity-events correlation view. */
  get_entity_events: EntityEventsResult,

  /* R5: text-heavy document tools. */
  get_schema_context: SchemaContextResult,
  verify_state: VerifyStateResult,

  /* Phase 1 compound investigation tools (2026-05-18) — typed renderers
     authored by Couturier audit
     specs/couturier_20260518_tool_renderers_phase1_and_naming.md R2.
     Removed from JSON_FALLBACK_ALLOWLIST in the same change. */
  reconstruct_event_timeline_causal: TimelineCausalResult,
  bus_zone_audit: BusZoneAuditResult,
  breaker_fail_signature: BreakerFailSignatureResult,
  frequency_disturbance_profile: FrequencyDisturbanceResult,

  /* Legacy tools (kept for backward compatibility) */
  query_graph: TabularResult,
  query_graph_local: TabularResult,
  query_cosmos_graph: TabularResult,
  query_telemetry: TabularResult,

  present_options: JsonFallback,
};

/**
 * Tools that are JSON-by-design (no specialised renderer needed).
 * The registry-coverage test consults this list to decide whether a
 * fall-through to JsonFallback is a bug or intentional.
 */
export const JSON_FALLBACK_ALLOWLIST: ReadonlySet<string> = new Set([
  "graph_property_keys",
  "present_options",
  // The four Phase 1 compound investigation tools were removed from
  // this allowlist on 2026-05-18 — each now has a bespoke renderer
  // (TimelineCausalResult, BusZoneAuditResult,
  // BreakerFailSignatureResult, FrequencyDisturbanceResult) per
  // specs/couturier_20260518_tool_renderers_phase1_and_naming.md R2.
]);

/**
 * Per-tool prominent-column hints consumed by ResultTable. Columns not
 * in this list render in muted text behind a "metadata" toggle. Tools
 * without an entry render every column at equal weight (preserves the
 * pre-R6 visual shape for any unclassified tool).
 */
const TOOL_PROMINENT_COLUMNS: Record<string, string[]> = {
  find_asset: ["asset_name", "asset_type", "voltage_kv", "station", "operating_status"],
  find_station_assets: ["asset_name", "asset_type", "voltage_kv", "operating_status"],
  find_alarms: ["timestamp_aest", "alarm_text", "severity", "station"],
  find_alerts: ["timestamp_aest", "alarm_text", "alert", "facility", "severity"],
  find_alarm_by_mrid: ["timestamp_aest", "alarm_text", "severity"],
  find_scada: ["timestamp_aest", "TagId", "measurement", "Value"],
  find_surveillance: ["timestamp_aest", "system", "track", "event", "truth"],
  find_traffic: ["callsign", "runway", "state", "impact", "action"],
  find_scada_changes: ["timestamp_aest", "asset_name", "measurement", "value_before", "value_after"],
  find_event_timeline: ["timestamp_aest", "event_type", "asset_name", "detail"],
  find_station_summary: ["station", "equipment", "alarms", "scada", "mw"],
  find_connected_stations: ["station", "voltage_kv", "via"],
  pattern_history: ["timestamp_aest", "TagId", "Value", "event"],
  graph_node: ["name", "type", "station", "voltage_kv"],
  graph_neighbors: ["name", "type", "station", "voltage_kv"],
  graph_station_equipment: ["name", "type", "voltage_kv"],
  graph_equipment_connections: ["from", "to", "via"],
  /* graph_* extras (GraphEnvelopeResult) — union of columns across each
     tool's list sections AND its per-row sub-tables. Columns absent on a
     given section are simply not in its header set; hints are
     position-independent. */
  graph_bus_boundary: [
    "name", "type", "normal_open", "current_open", "abnormal",      // directly_on_bus / adjacent_bays rows
    "bay_path",                                                      // adjacent_bays
    "bus_name", "abnormal_switch_count",                             // companion_buses
  ],
  graph_switch_state_snapshot: [
    "ems", "name", "type", "normal_open", "current_open", "abnormal", "bay_path",
  ],
  graph_breaker_neighbourhood: [
    "side", "neighbour_count",                                       // parent terminals row
    "type", "name", "normal_open", "current_open",                   // nested neighbours sub-table
  ],
  graph_corridor_endpoints: [
    "station", "bay_cn_paths",                                       // endpoints
    "line_path", "name",                                             // segments / parallel_circuits
  ],
  graph_common_mode_devices: [
    "name_a", "name_b", "shared_dimensions",                         // by_pair
    "mrid", "label", "name", "path", "bay",                          // input_devices
    "input", "resolved_via",                                         // inputs side panel
  ],
  /* Phase 1 timeline tool — keep the operator-facing causal columns
     visible; raw `source`/`label` toggle in via the metadata chip. */
  reconstruct_event_timeline_causal: ["dt_seconds", "ts", "tag", "equipment", "text"],
};

export function getProminentColumns(toolName?: string | null): string[] | undefined {
  if (!toolName) return undefined;
  return TOOL_PROMINENT_COLUMNS[toolName];
}

/**
 * Get the appropriate renderer component for a tool name.
 * Returns JsonFallback if no specialised renderer is registered.
 */
export function getToolResultRenderer(
  toolName: string,
): ComponentType<ToolResultProps> {
  return TOOL_RENDERERS[toolName] ?? JsonFallback;
}

/** Exposed for the registry-coverage test. */
export function listRegisteredTools(): string[] {
  return Object.keys(TOOL_RENDERERS);
}

/** Props for custom arguments renderers. */
export interface ToolArgsProps {
  args: Record<string, unknown>;
}

import {
  SearchQueryArgsRenderer,
  DelegationArgsRenderer,
  PanelActionArgsRenderer,
// ClassifierVerdictArgsRenderer import removed 2026-05-18 — classifier retired.
  NoArgumentsRenderer,
  GraphLookupArgsRenderer,
  GraphPathArgsRenderer,
  EdgeArgsRenderer,
  EntityTimeRangeArgsRenderer,
  SummaryArgsRenderer,
  PriorityActionsArgsRenderer,
  OperatingStateArgsRenderer,
  DisturbanceSummaryArgsRenderer,
} from "./ToolArgsRenderers";

/**
 * Registry mapping tool names to custom arguments renderers.
 * Tools not listed here use the default ArgumentsGrid.
 */
const TOOL_ARGS_RENDERERS: Record<string, ComponentType<ToolArgsProps>> = {
  /* Search tools — display query in bordered box */
  search_operator_manual: SearchQueryArgsRenderer,
  search_knowledge_base: SearchQueryArgsRenderer,
  search_incident_reports: SearchQueryArgsRenderer,
  search_nearhit_reports: SearchQueryArgsRenderer,
  search_investigation_clues: SearchQueryArgsRenderer,
  search_paws: SearchQueryArgsRenderer,
  search_smirks: SearchQueryArgsRenderer,

  /* Delegation — agent ID + task */
  delegate_to_agent: DelegationArgsRenderer,

  /* Push action — action + reasoning + guide */
  push_action: PanelActionArgsRenderer,
  push_priority_action: PanelActionArgsRenderer,
  /* push_classifier_verdict args renderer removed 2026-05-18 — classifier retired. */

  /* R5: wire previously-orphan args renderers so the active tool
     surface gets purpose-built args views instead of the generic grid. */
  get_schema_context: NoArgumentsRenderer,
  get_nodes: GraphLookupArgsRenderer,
  get_neighbors: GraphLookupArgsRenderer,
  get_node_properties: GraphLookupArgsRenderer,
  lookup_entity: GraphLookupArgsRenderer,
  count_nodes: GraphLookupArgsRenderer,
  find_path: GraphPathArgsRenderer,
  get_edges: EdgeArgsRenderer,
  get_scada_readings: EntityTimeRangeArgsRenderer,
  get_scada_timeline: EntityTimeRangeArgsRenderer,
  get_scada_extremes: EntityTimeRangeArgsRenderer,
  get_alarm_sequence: EntityTimeRangeArgsRenderer,
  get_entity_events: EntityTimeRangeArgsRenderer,
  summarize_scada: SummaryArgsRenderer,
  summarize_alarms: SummaryArgsRenderer,
  update_priority_actions: PriorityActionsArgsRenderer,
  update_operating_state: OperatingStateArgsRenderer,
  update_disturbance_summary: DisturbanceSummaryArgsRenderer,
};

/**
 * Get a custom arguments renderer for a tool, or null for default grid.
 */
export function getToolArgsRenderer(
  toolName: string,
): ComponentType<ToolArgsProps> | null {
  return TOOL_ARGS_RENDERERS[toolName] ?? null;
}
