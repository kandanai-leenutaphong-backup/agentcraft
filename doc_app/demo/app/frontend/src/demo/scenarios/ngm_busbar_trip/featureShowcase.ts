/**
 * Full UI showcase payloads for the NGM kiosk scenario.
 *
 * These values intentionally exercise backend-driven UI panels in kiosk mode:
 * Data Search, Detector Tuning, and System Evaluations. All content is
 * fictional and mirrors the existing MARRABEL_NX demo facts.
 */

import type { AuditReport, AuditStreamEvent } from "@/api/auditApi";
import type { DetectorConfigPatch, DetectorConfigResponse } from "@/api/situationApi";
import type { ApiMessage } from "@/api/types";
import type { DetectorComparisonResult } from "@/stores/situationStore";

const DETECTOR_PATCH: DetectorConfigPatch = {
  window_minutes: 5,
  severity_thresholds: { investigate: 4, serious: 8, major: 13, critical: 20 },
  mw_boost: { per_mw: 0.012, cap: 5 },
  alarm_signals: [
    { id: "bus_diff", col: "alarm_text", op: "contains", val: "BUSBAR DIFFERENTIAL", points: 5, min_count: 1 },
    { id: "cb_trip", col: "alarm_label", op: "contains", val: "CB-OPN", points: 2, min_count: 2 },
    { id: "prot_op", col: "alarm_label", op: "contains", val: "PROTOP", points: 2, min_count: 1 },
    { id: "earth_fault", col: "alarm_text", op: "contains", val: "ground fault", points: 4, min_count: 1 },
  ],
  scada_signals: [
    { id: "bus_collapse", tag_contains: [".BUS.", "B275"], meas: "KV", cond_type: "drops_below", threshold: 5, baseline: 200, points: 5 },
    { id: "gen_trip", tag_contains: ["::G", "pwr_real"], meas: "MW", cond_type: "drops_to_near_zero", threshold: 1, baseline: 50, points: 4 },
    { id: "line_overload", tag_contains: ["::L:", "pwr_real"], meas: "MW", cond_type: "change_percent", direction: "up", threshold: 30, points: 2 },
    { id: "kv_transient", tag_contains: ["volt_kv"], meas: "KV", cond_type: "change_percent", direction: "down", threshold: 8, points: 3 },
  ],
  patterns: {
    busbar_fault: { bus_diff: 1, cb_trip: 2, bus_collapse: 1 },
    dual_unit_trip: { gen_trip: 2, prot_op: 1 },
  },
};

export const NGM_DETECTOR_CONFIG: DetectorConfigResponse = {
  patch: DETECTOR_PATCH,
  effective_config: { ...DETECTOR_PATCH },
  config_hash: "ngm-demo-full-ui-9f3c",
  source: "saved",
  updated_at: "2026-05-25T10:10:00Z",
};

export const NGM_DETECTOR_DRAFT: DetectorConfigPatch = {
  ...DETECTOR_PATCH,
  severity_thresholds: { investigate: 3, serious: 7, major: 12, critical: 19 },
  scada_signals: [
    ...(DETECTOR_PATCH.scada_signals ?? []),
    { id: "tx_overload", tag_contains: ["TX", "pwr_real"], meas: "MW", cond_type: "change_percent", direction: "up", threshold: 25, points: 2 },
  ],
};

export const NGM_DETECTOR_COMPARISON: DetectorComparisonResult = {
  matched: 5,
  missed: 0,
  severity_mismatches: 1,
  rows: [
    { id: "ngm-crit-1", label: "MARRABEL_NX busbar fault", current: "CRITICAL score 25", draft: "CRITICAL score 27" },
    { id: "ngm-pre-1", label: "MARRABEL_NX voltage precursor", current: "INVESTIGATE score 4", draft: "SERIOUS score 7" },
    { id: "ngm-maj-1", label: "KETTERING_NX line loading", current: "MAJOR score 14", draft: "MAJOR score 15" },
  ],
};

export const NGM_DATA_SEARCH_MESSAGES: ApiMessage[] = [
  {
    id: "ngm-data-user-1",
    role: "user",
    content: "Show the alarm and SCADA evidence for MARRABEL_NX around 11:15.",
    parts: null,
    status: "complete",
    tool_calls: [],
    agent_name: "Operator",
    created_at: "2026-05-25T10:11:00Z",
  },
  {
    id: "ngm-data-assistant-1",
    role: "assistant",
    content:
      "MARRABEL_NX shows a tight protection sequence at 11:15:14 followed by two unit MW drops. Bus 275-1 voltage collapsed from 275.5 kV to 0.0 kV while GEN.3 and GEN.4 fell to zero output.",
    parts: null,
    status: "complete",
    tool_calls: [
      { id: "ngm-data-tool-1", name: "find_alarms", arguments: { station: "MARRABEL_NX", start: "2026-02-12 11:13", end: "2026-02-12 11:23" }, status: "complete", result: "6 priority alarms: BUS DIFF, CB-031 trip, CB-041 trip, DS-275-13 earth fault, GEN.3 reverse power, GEN.4 UFREQ.", duration_ms: 640 },
      { id: "ngm-data-tool-2", name: "find_scada_changes", arguments: { tags: ["MARRABEL_NX::B275-1::volt_kv", "MARRABEL_NX::G3::pwr_real", "MARRABEL_NX::G4::pwr_real"] }, status: "complete", result: "B275-1 voltage 275.5 -> 0.0 kV; GEN.3 241 -> 0 MW; GEN.4 189 -> 0 MW.", duration_ms: 710 },
    ],
    agent_name: "Data Search",
    created_at: "2026-05-25T10:11:04Z",
  },
  {
    id: "ngm-data-user-2",
    role: "user",
    content: "Was the 10:38 voltage dip related?",
    parts: null,
    status: "complete",
    tool_calls: [],
    agent_name: "Operator",
    created_at: "2026-05-25T10:11:18Z",
  },
  {
    id: "ngm-data-assistant-2",
    role: "assistant",
    content:
      "Likely yes. The earlier 15-second dip has the same bus section and a compatible recovery signature. It did not trip protection, but it is strong precursor evidence for insulation degradation before the bus differential event.",
    parts: null,
    status: "complete",
    tool_calls: [
      { id: "ngm-data-tool-3", name: "pattern_history", arguments: { equipment: "MARRABEL_NX::B275-1", pattern: "transient_kv_dip" }, status: "complete", result: "One precursor in the preceding hour: 10:38:30, 248.0 kV nadir, recovered after 15 seconds.", duration_ms: 540 },
    ],
    agent_name: "Data Search",
    created_at: "2026-05-25T10:11:22Z",
  },
];

export const NGM_AUDIT_REPORT: AuditReport = {
  id: "audit-ngm-full-ui",
  session_id: "demo-session",
  started_at: "2026-05-25T10:12:00Z",
  finished_at: "2026-05-25T10:12:18Z",
  duration_seconds: 18,
  iteration_count: 4,
  tool_call_count: 12,
  headline: "Investigation grounded the busbar fault, precursor, topology, classification, and operator action with complete evidence.",
  markdown:
    "### Audit finding\n\nThe run correctly separated the initiating MARRABEL_NX busbar fault from consequential KETTERING and OAKBANK events. Tool usage covered alarms, SCADA, topology, procedures, history, and classification. The final operator actions were specific, timed, and evidence-backed.\n\n### Residual risk\n\nThe precursor is advisory rather than reportable, but should still be escalated for maintenance inspection because it points at the same bus section as the main trip.",
  rubric: [
    { dimension: "evidence_completeness", score: 3, band: "excellent", note: "Alarm and SCADA rows were cited for each major claim." },
    { dimension: "topology_coverage", score: 3, band: "excellent", note: "Bus section, breakers, generators, and interconnector consequence were traced." },
    { dimension: "hypothesis_quality", score: 3, band: "excellent", note: "Precursor and initiating fault were handled as separate hypotheses." },
    { dimension: "action_grounding", score: 3, band: "excellent", note: "Actions map to isolation, dispatch, comms, and maintenance owners." },
    { dimension: "summary_quality", score: 2, band: "strong", note: "Executive summary is accurate; could quantify KETTERING margin earlier." },
    { dimension: "grounding", score: 3, band: "excellent", note: "No unsupported root-cause claim was made." },
  ],
  gaps: ["OEM isolator inspection evidence is pending.", "Protection relay oscillography is referenced but not displayed in the kiosk dataset."],
  improvements: [
    { category: "process", text: "Add a maintenance handoff card for the 10:38 precursor inspection." },
    { category: "data", text: "Include relay oscillography thumbnails when the backend audit has access to files." },
  ],
  confidence: "high",
  weighted_score: 17,
  score_pct: 0.81,
  band: "strong",
  auditor_model: "synthetic-kiosk-auditor",
  context_prompt: "Investigate MARRABEL_NX busbar trip and recommend operator actions.",
  synthetic: true,
};

export const NGM_AUDIT_STREAM_EVENTS: AuditStreamEvent[] = [
  { kind: "started", auditId: NGM_AUDIT_REPORT.id, startedAt: NGM_AUDIT_REPORT.started_at },
  { kind: "token", token: "Checking evidence coverage across alarms, SCADA, topology, and actions. " },
  { kind: "tool_call_start", id: "audit-ngm-tool-1", name: "find_alarms" },
  { kind: "tool_result", id: "audit-ngm-tool-1", name: "find_alarms", result: "MARRABEL_NX alarm sequence contains six priority rows in 16 seconds." },
  { kind: "tool_call_start", id: "audit-ngm-tool-2", name: "graph_bus_topology" },
  { kind: "tool_result", id: "audit-ngm-tool-2", name: "graph_bus_topology", result: "Bus 275-1 connects CB-031, CB-041, GEN.3, GEN.4, and DS-275-13." },
  { kind: "report", report: NGM_AUDIT_REPORT },
  { kind: "done", persisted: true },
];
