/**
 * Situation card payloads for the NGM busbar trip demo scenario.
 *
 * Module role:
 *   Exports the five situation objects that populate the situation panel
 *   after the scan completes. Each object mirrors the shape returned by
 *   the real situation detector API. All station names, equipment IDs,
 *   SCADA tags, and telemetry values are fictional.
 *
 * Key collaborators:
 *   - phases/01_scan.ts — references SITUATIONS in the panel.situations.set op.
 *   - bootstrap.ts — references classification data keyed by situation_id.
 *
 * Order: precursor first (oldest detected_at), then CRITICAL, MAJOR,
 * SERIOUS, INVESTIGATE. The UI sorts by severity — the precursor appears
 * at the bottom, which is the framing we want for the Phase 7 reveal.
 */

const PRECURSOR_SIGNAL_EVIDENCE = JSON.stringify({
  alarm: {},
  scada: {
    kv_transient: {
      rule: { id: "kv_transient", tag_contains: ["volt_kv"], meas: "KV", cond_type: "change_percent", threshold: 8, direction: "down", points: 3 },
      rows: [
        { timestamp_aest: "2026-02-12 10:38:30", TagId: "MARRABEL_NX::B275-1::volt_kv", measurement: "KV", Value: 248.0, prev_val: 275.5, abs_drop: 27.5, pct_change: 9.9 },
        { timestamp_aest: "2026-02-12 10:38:45", TagId: "MARRABEL_NX::B275-1::volt_kv", measurement: "KV", Value: 275.4, prev_val: 248.0, abs_drop: -27.4, pct_change: -10.9 },
      ],
      count: 2,
    },
  },
  patterns: {
    transient_kv_dip: { id: "transient_kv_dip", details: { duration_s: 15, depth_pct: 9.9, recovered: true, equipment: "MARRABEL_NX::B275-1" } },
  },
});

const CRITICAL_SIGNAL_EVIDENCE = JSON.stringify({
  alarm: {
    bus_diff: {
      rule: { id: "bus_diff", col: "alarm_text", op: "contains", val: "BUSBAR DIFFERENTIAL", points: 5, min_count: 1 },
      rows: [
        { timestamp_aest: "2026-02-12 11:15:14", alarm_label: "BUS DIFF", alarm_text: "MARRABEL_NX 275 kV A BUSBAR DIFFERENTIAL PROTECTION OPERATED", priority: 1, client_composite_id: "MARRABEL_NX::B275-1", mrid: "mrid-busdiff-01" },
      ],
      count: 1,
    },
    cb_trip: {
      rule: { id: "cb_trip", col: "alarm_label", op: "contains", val: "CB-OPN", points: 2, min_count: 2 },
      rows: [
        { timestamp_aest: "2026-02-12 11:15:14", alarm_label: "[CB-OPN] CB transition", alarm_text: "MARRABEL_NX 275 kV CB-031 TRIPPED", priority: 1, client_composite_id: "MARRABEL_NX::CB-031", mrid: "mrid-rc-cb031" },
        { timestamp_aest: "2026-02-12 11:15:14", alarm_label: "[CB-OPN] CB transition", alarm_text: "MARRABEL_NX 275 kV CB-041 TRIPPED", priority: 1, client_composite_id: "MARRABEL_NX::CB-041", mrid: "mrid-rc-cb041" },
      ],
      count: 2,
    },
  },
  scada: {
    gen_trip: {
      rule: { id: "gen_trip", tag_contains: ["::G", "pwr_real"], meas: "MW", cond_type: "drops_to_near_zero", threshold: 1, baseline: 50, points: 4 },
      rows: [
        { timestamp_aest: "2026-02-12 11:15:18", TagId: "MARRABEL_NX::G3::pwr_real", measurement: "MW", Value: 0.0, prev_val: 241.0, abs_drop: 241.0, pct_change: 100.0 },
        { timestamp_aest: "2026-02-12 11:15:22", TagId: "MARRABEL_NX::G4::pwr_real", measurement: "MW", Value: 0.0, prev_val: 189.0, abs_drop: 189.0, pct_change: 100.0 },
      ],
      count: 2,
    },
    bus_collapse: {
      rule: { id: "bus_collapse", tag_contains: [".BUS.", "B275"], meas: "KV", cond_type: "drops_below", threshold: 5, baseline: 200, points: 5 },
      rows: [
        { timestamp_aest: "2026-02-12 11:15:14", TagId: "MARRABEL_NX::B275-1::volt_kv", measurement: "KV", Value: 0.0, prev_val: 275.5, abs_drop: 275.5, pct_change: 100.0 },
      ],
      count: 1,
    },
  },
  patterns: {
    busbar_fault: { id: "busbar_fault", details: { protection: "bus differential", breakers_opened: ["CB-031", "CB-041"], isolated_bus: "B275-1" } },
    dual_unit_trip: { id: "dual_unit_trip", details: { units: ["GEN.3", "GEN.4"], total_mw_lost: 430 } },
  },
});

/** Precursor — 37 minutes before the busbar trip. INVESTIGATE severity.
 *  The headline "AI win" of the demo: GridIQ flagged a 15-second voltage
 *  transient that no SCADA alarm caught. */
export const SITUATION_PRECURSOR = {
  situation_id: "ngm-pre-1",
  window_start: "2026-02-12 10:38:00",
  window_end: "2026-02-12 10:43:00",
  station: "MARRABEL_NX",
  severity: "INVESTIGATE",
  total_score: 4,
  alarm_score: 0,
  scada_score: 4,
  mw_boost: 0,
  total_mw_lost: 0,
  max_mw_drop: 0,
  alarm_count: 0,
  step_changes: 2,
  alarm_signals: "{}",
  scada_signals: '{"kv_transient": 1, "sub_threshold": 1}',
  alarm_mrids: "[]",
  affected_tags: '["MARRABEL_NX::B275-1"]',
  affected_equipment:
    '[{"equipment_id":"MARRABEL_NX::B275-1","alarms":[],"scada":[{"timestamp_aest":"2026-02-12 10:38:30","TagId":"MARRABEL_NX::B275-1::volt_kv","measurement":"KV","Value":248.0,"prev_val":275.5,"abs_drop":27.5,"pct_change":9.9},{"timestamp_aest":"2026-02-12 10:38:45","TagId":"MARRABEL_NX::B275-1::volt_kv","measurement":"KV","Value":275.4,"prev_val":248.0,"abs_drop":-27.4,"pct_change":-10.9}]}]',
  patterns: "transient_kv_dip,sub_alarm_threshold",
  pattern_details:
    '[{"pattern":"transient_kv_dip","duration_s":15,"depth_pct":9.9,"recovered":true}]',
  detected_at: "2026-02-12 10:39:00",
  detector_version: "v4",
  config_hash: "demo",
  station_region: "EHR",
  station_rated_mw: 1000,
  station_unit_count: 4,
  region_rated_mw: 8100,
  region_live_mw: 6200,
  nem_live_mw: 23400,
  impact_station_pct: 0,
  impact_region_pct: 0,
  impact_nem_pct: 0,
  signal_evidence: PRECURSOR_SIGNAL_EVIDENCE,
  unit_offline_summary: {},
  score_contributions: [],
} as const;

/** CRITICAL — 275 kV Bus 275-1 fault at MARRABEL_NX. 412 MW generation lost. */
export const SITUATION_CRITICAL = {
  situation_id: "ngm-crit-1",
  window_start: "2026-02-12 11:13:00",
  window_end: "2026-02-12 11:23:00",
  station: "MARRABEL_NX",
  severity: "CRITICAL",
  total_score: 25,
  alarm_score: 8,
  scada_score: 12,
  mw_boost: 5,
  total_mw_lost: 430,
  max_mw_drop: 241,
  alarm_count: 6,
  step_changes: 8,
  alarm_signals: '{"bus_diff": 1, "cb_trip": 2, "prot_op": 2, "earth_fault": 1}',
  scada_signals:
    '{"gen_trip": 2, "gen_major_loss": 1, "bus_collapse": 1, "line_overload": 1}',
  alarm_mrids: "[]",
  affected_tags: '["MARRABEL_NX::G3", "MARRABEL_NX::G4"]',
  affected_equipment:
    '[{"equipment_id":"MARRABEL_NX::G3","alarms":[{"timestamp_aest":"2026-02-12 11:15:18","alarm_label":"[PROTOP]","alarm_text":"MARRABEL_NX GEN 3 [REVPWR] backfeed event","priority":1,"mrid":"mrid-rc-g3-01"},{"timestamp_aest":"2026-02-12 11:15:14","alarm_label":"[CB-OPN] CB transition","alarm_text":"MARRABEL_NX 275 kV CB-031 TRIPPED","priority":1,"mrid":"mrid-rc-cb031"}],"scada":[{"timestamp_aest":"2026-02-12 11:15:18","TagId":"MARRABEL_NX::G3::pwr_real","measurement":"MW","Value":0.0,"prev_val":241.0,"abs_drop":241.0,"pct_change":100.0}]},{"equipment_id":"MARRABEL_NX::G4","alarms":[{"timestamp_aest":"2026-02-12 11:15:22","alarm_label":"[PROTOP]","alarm_text":"MARRABEL_NX GEN 4 [UFREQ] freq band exit","priority":1,"mrid":"mrid-rc-g4-01"},{"timestamp_aest":"2026-02-12 11:15:14","alarm_label":"[CB-OPN] CB transition","alarm_text":"MARRABEL_NX 275 kV CB-041 TRIPPED","priority":1,"mrid":"mrid-rc-cb041"}],"scada":[{"timestamp_aest":"2026-02-12 11:15:22","TagId":"MARRABEL_NX::G4::pwr_real","measurement":"MW","Value":0.0,"prev_val":189.0,"abs_drop":189.0,"pct_change":100.0}]}]',
  patterns: "busbar_fault,dual_unit_trip",
  pattern_details: "[]",
  detected_at: "2026-02-12 11:24:00",
  detector_version: "v4",
  config_hash: "demo",
  station_region: "EHR",
  station_rated_mw: 1000,
  station_unit_count: 4,
  region_rated_mw: 8100,
  region_live_mw: 6200,
  nem_live_mw: 23400,
  impact_station_pct: 43.0,
  impact_region_pct: 6.9,
  impact_nem_pct: 1.8,
  signal_evidence: CRITICAL_SIGNAL_EVIDENCE,
  unit_offline_summary: {},
  score_contributions: [],
} as const;

/** MAJOR — KETTERING_NX interconnector thermal stress from load redistribution. */
export const SITUATION_MAJOR = {
  situation_id: "ngm-maj-1",
  window_start: "2026-02-12 11:13:00",
  window_end: "2026-02-12 11:23:00",
  station: "KETTERING_NX",
  severity: "MAJOR",
  total_score: 14,
  alarm_score: 5,
  scada_score: 8,
  mw_boost: 1,
  total_mw_lost: 0,
  max_mw_drop: 0,
  alarm_count: 4,
  step_changes: 5,
  alarm_signals: '{"line_loading": 2, "thermal_advisory": 1, "flow_reversal": 1}',
  scada_signals: '{"line_overload": 1, "flow_surge": 1, "kv_depression": 1}',
  alarm_mrids: "[]",
  affected_tags: '["KETTERING_NX::L:MRB-01", "KETTERING_NX::B275-1"]',
  affected_equipment:
    '[{"equipment_id":"KETTERING_NX::L:MRB-01","alarms":[{"timestamp_aest":"2026-02-12 11:18:00","alarm_label":"[THRM]","alarm_text":"[THRM] KETTERING_NX::L:MRB-01 loading 89 pct rated","priority":2,"mrid":"mrid-nv-ln1-01"}],"scada":[{"timestamp_aest":"2026-02-12 11:15:50","TagId":"KETTERING_NX::L:MRB-01::pwr_real","measurement":"MW","Value":710.0,"prev_val":320.0,"abs_drop":-390.0,"pct_change":-121.9}]},{"equipment_id":"KETTERING_NX::B275-1","alarms":[{"timestamp_aest":"2026-02-12 11:15:48","alarm_label":"[KV-LO]","alarm_text":"[KV-LO] KETTERING_NX::B275-1 volt 214.2 kV","priority":3,"mrid":"mrid-nv-bus-01"}],"scada":[{"timestamp_aest":"2026-02-12 11:15:48","TagId":"KETTERING_NX::B275-1::volt_kv","measurement":"KV","Value":214.2,"prev_val":219.8,"abs_drop":5.6,"pct_change":2.5}]}]',
  patterns: "",
  pattern_details: "[]",
  detected_at: "2026-02-12 11:24:30",
  detector_version: "v4",
  config_hash: "demo",
  station_region: "EHR",
  station_rated_mw: 0,
  station_unit_count: 0,
  region_rated_mw: 8100,
  region_live_mw: 6200,
  nem_live_mw: 23400,
  impact_station_pct: 0,
  impact_region_pct: 0,
  impact_nem_pct: 0,
  signal_evidence: "{}",
  unit_offline_summary: {},
  score_contributions: [],
} as const;

/** SERIOUS — GLENRIDGE_NX governor frequency response. Normal system behaviour. */
export const SITUATION_SERIOUS = {
  situation_id: "ngm-ser-1",
  window_start: "2026-02-12 11:13:00",
  window_end: "2026-02-12 11:23:00",
  station: "GLENRIDGE_NX",
  severity: "SERIOUS",
  total_score: 9,
  alarm_score: 4,
  scada_score: 4,
  mw_boost: 1,
  total_mw_lost: 0,
  max_mw_drop: 0,
  alarm_count: 3,
  step_changes: 3,
  alarm_signals: '{"gov_response": 1, "agc_override": 1, "mw_ramp": 1}',
  scada_signals: '{"gen_ramp": 2, "freq_deviation": 1}',
  alarm_mrids: "[]",
  affected_tags: '["GLENRIDGE_NX::G1", "GLENRIDGE_NX::G2"]',
  affected_equipment:
    '[{"equipment_id":"GLENRIDGE_NX::G1","alarms":[{"timestamp_aest":"2026-02-12 11:15:50","alarm_label":"[GOVRSP]","alarm_text":"[GOVRSP] GLENRIDGE_NX::G1 governor response active","priority":3,"mrid":"mrid-bk-g1-01"}],"scada":[{"timestamp_aest":"2026-02-12 11:15:50","TagId":"GLENRIDGE_NX::G1::pwr_real","measurement":"MW","Value":178.0,"prev_val":165.0,"abs_drop":-13.0,"pct_change":-7.9}]},{"equipment_id":"GLENRIDGE_NX::G2","alarms":[],"scada":[{"timestamp_aest":"2026-02-12 11:15:52","TagId":"GLENRIDGE_NX::G2::pwr_real","measurement":"MW","Value":178.0,"prev_val":164.0,"abs_drop":-14.0,"pct_change":-8.5}]}]',
  patterns: "",
  pattern_details: "[]",
  detected_at: "2026-02-12 11:25:00",
  detector_version: "v4",
  config_hash: "demo",
  station_region: "EHR",
  station_rated_mw: 360,
  station_unit_count: 2,
  region_rated_mw: 8100,
  region_live_mw: 6200,
  nem_live_mw: 23400,
  impact_station_pct: 0,
  impact_region_pct: 0,
  impact_nem_pct: 0,
  signal_evidence: "{}",
  unit_offline_summary: {},
  score_contributions: [],
} as const;

/** INVESTIGATE — OAKBANK_NX transformer T2 overcurrent trip. Credible contingency. */
export const SITUATION_INVESTIGATE = {
  situation_id: "ngm-inv-1",
  window_start: "2026-02-12 11:21:00",
  window_end: "2026-02-12 14:48:00",
  station: "OAKBANK_NX",
  severity: "INVESTIGATE",
  total_score: 5,
  alarm_score: 2,
  scada_score: 2,
  mw_boost: 1,
  total_mw_lost: 12.4,
  max_mw_drop: 12.4,
  alarm_count: 2,
  step_changes: 2,
  alarm_signals: '{"prot_op": 1, "tx_trip": 1}',
  scada_signals: '{"tx_overload": 1, "load_shed": 1}',
  alarm_mrids: "[]",
  affected_tags: '["OAKBANK_NX::TX-T2"]',
  affected_equipment:
    '[{"equipment_id":"OAKBANK_NX::TX-T2","alarms":[{"timestamp_aest":"2026-02-12 11:23:12","alarm_label":"[PROTOP]","alarm_text":"[OVRCUR] OAKBANK_NX::TX-T2 overcurrent op","priority":1,"mrid":"mrid-ww-tx2-01"},{"timestamp_aest":"2026-02-12 11:23:12","alarm_label":"[TX-OPN]","alarm_text":"[TX-OPN] OAKBANK_NX::TX-T2 transition (132/66 kV)","priority":1,"mrid":"mrid-ww-tx2-02"}],"scada":[{"timestamp_aest":"2026-02-12 11:23:12","TagId":"OAKBANK_NX::TX-T2::pwr_real","measurement":"MW","Value":0.0,"prev_val":52.4,"abs_drop":52.4,"pct_change":100.0}]}]',
  patterns: "",
  pattern_details: "[]",
  detected_at: "2026-02-12 14:49:00",
  detector_version: "v4",
  config_hash: "demo",
  station_region: "EHR",
  station_rated_mw: 0,
  station_unit_count: 0,
  region_rated_mw: 8100,
  region_live_mw: 6200,
  nem_live_mw: 23400,
  impact_station_pct: 0,
  impact_region_pct: 0.2,
  impact_nem_pct: 0.1,
  signal_evidence: "{}",
  unit_offline_summary: {},
  score_contributions: [],
} as const;

/** All five situations in display order: precursor first, then by severity desc. */
export const ALL_SITUATIONS = [
  SITUATION_PRECURSOR,
  SITUATION_CRITICAL,
  SITUATION_MAJOR,
  SITUATION_SERIOUS,
  SITUATION_INVESTIGATE,
];
