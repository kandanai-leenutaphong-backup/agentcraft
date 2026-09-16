/**
 * Phase 4b — Capability showcase.
 *
 * Module role:
 *   Inserted AFTER the classic investigator phase (04_investigate.ts)
 *   and BEFORE delegation (05_delegate.ts). Fires every modern tool
 *   family from the live GridIQ surface that the existing 04_investigate
 *   does not exercise — bringing the demo up to the 2026-05 production
 *   tool catalogue per MODERNIZATION.md §1.R10 + §2.3.
 *
 *   Tools added here (all on the existing investigator thread, no
 *   delegation):
 *     - find_alarm_by_mrid             (resolve a specific alarm body)
 *     - graph_equipment_connections    (CB-031 outward)
 *     - graph_bus_boundary             (Bus 275-1 boundary set)
 *     - graph_corridor_endpoints       (MARRABEL→KETTERING line corridor)
 *     - graph_breaker_neighbourhood    (CB-031 sympathetic-trip neighbourhood)
 *     - graph_common_mode_devices      (suspect isolator family)
 *     - graph_switch_state_snapshot    (TRUNCATED envelope — shows R12 banner)
 *     - reconstruct_event_timeline_causal  (Phase 1 compound tool)
 *     - bus_zone_audit                 (Phase 1 compound tool)
 *     - breaker_fail_signature         (Phase 1 compound tool)
 *     - frequency_disturbance_profile  (Phase 1 compound tool)
 *     - search_smirks                  (current AEMO OERs corpus)
 *
 *   Runtime: ~45 s across ~30 frames at default speed. All renderers
 *   fall through to TabularResult / GraphResult / SearchResultCards /
 *   JsonFallback in the current kiosk renderer registry; bespoke
 *   renderers for the four compound tools land in a follow-up turn.
 */

import type { Frame } from "../../../scenarioSchema";

/* ── Tool result envelopes ──────────────────────────────────────────── */

const ALARM_BY_MRID_RESULT = JSON.stringify({
  columns: ["mrid", "timestamp_aest", "equipment", "label", "text", "priority"],
  rows: [
    [
      "mrid-mb-bus-01",
      "2026-02-12 11:15:14",
      "MARRABEL_NX::B275-1",
      "BSDIF-SA",
      "MARRABEL 275 kV Bus 275-1 differential protection (Scheme A) operated — phase R-to-earth fault detected, trip signal issued to all CBs on Bus 275-1.",
      "Tier-1",
    ],
  ],
  count: 1,
});

const EQUIPMENT_CONNECTIONS_RESULT = JSON.stringify([
  {
    equipment: "MARRABEL_NX::CB-031",
    cim_class: "Breaker",
    voltage_kv: 275,
    connected_via_terminals: [
      { terminal: "T1", to: "MARRABEL_NX::DS-275-13", cim_class: "Disconnector" },
      { terminal: "T2", to: "MARRABEL_NX::G3-TX-WIND", cim_class: "TransformerWinding" },
    ],
    protection_zones: ["BUS-275-1-ZONE-A", "G3-DIFF"],
  },
]);

const BUS_BOUNDARY_RESULT = JSON.stringify({
  scope: { bus_section: "MARRABEL_NX::B275-1", voltage_kv: 275 },
  summary: {
    boundary_breakers: 4,
    boundary_disconnectors: 4,
    open_alarms_observed: 2,
    adjacency_gaps: 0,
  },
  list_boundary_breakers: [
    { mrid: "MARRABEL_NX::CB-031", normal_state: "CLOSED", current_state: "OPEN", open_alarm_at: "2026-02-12 11:15:14" },
    { mrid: "MARRABEL_NX::CB-041", normal_state: "CLOSED", current_state: "OPEN", open_alarm_at: "2026-02-12 11:15:14" },
    { mrid: "MARRABEL_NX::CB-021", normal_state: "CLOSED", current_state: "OPEN", open_alarm_at: null },
    { mrid: "MARRABEL_NX::CB-051", normal_state: "CLOSED", current_state: "OPEN", open_alarm_at: null },
  ],
  list_boundary_disconnectors: [
    { mrid: "MARRABEL_NX::DS-275-11", normal_state: "CLOSED", current_state: "CLOSED" },
    { mrid: "MARRABEL_NX::DS-275-12", normal_state: "CLOSED", current_state: "CLOSED" },
    { mrid: "MARRABEL_NX::DS-275-13", normal_state: "CLOSED", current_state: "FAULTED", note: "earth fault alarm 11:15:14" },
    { mrid: "MARRABEL_NX::DS-275-14", normal_state: "CLOSED", current_state: "CLOSED" },
  ],
});

const CORRIDOR_ENDPOINTS_RESULT = JSON.stringify({
  scope: { line: "MARRABEL→KETTERING No. 1", voltage_kv: 275 },
  summary: { length_km: 142, endpoint_count: 2, bay_cn_paths: 2 },
  endpoints: [
    {
      station: "MARRABEL_NX",
      bay: "275-KTG-01",
      bay_cn_paths: [
        "MARRABEL_NX::B275-1 → MARRABEL_NX::CB-021 → MARRABEL_NX::DS-021A → MARRABEL_NX::CT-021 → LINE:KTG-01",
      ],
    },
    {
      station: "KETTERING_NX",
      bay: "275-MRB-01",
      bay_cn_paths: [
        "LINE:KTG-01 → KETTERING_NX::CT-101 → KETTERING_NX::DS-101A → KETTERING_NX::CB-101 → KETTERING_NX::B275-A",
      ],
    },
  ],
});

const BREAKER_NEIGHBOURHOOD_RESULT = JSON.stringify({
  scope: { breaker: "MARRABEL_NX::CB-031" },
  summary: { neighbour_count: 6, sympathetic_open_count: 1, in_same_bus_zone: 4 },
  list_neighbours: [
    { mrid: "MARRABEL_NX::CB-041", relation: "shares Bus 275-1", state: "OPEN", sympathetic: true },
    { mrid: "MARRABEL_NX::CB-021", relation: "shares Bus 275-1", state: "OPEN", sympathetic: false },
    { mrid: "MARRABEL_NX::CB-051", relation: "shares Bus 275-1", state: "OPEN", sympathetic: false },
    { mrid: "MARRABEL_NX::CB-011", relation: "Bus 275-2 (isolated)", state: "CLOSED", sympathetic: false },
    { mrid: "MARRABEL_NX::CB-022", relation: "Bus 275-2 (isolated)", state: "CLOSED", sympathetic: false },
    { mrid: "MARRABEL_NX::CB-012", relation: "Bus 275-2 (isolated)", state: "CLOSED", sympathetic: false },
  ],
});

const COMMON_MODE_RESULT = JSON.stringify({
  scope: { incident_window: "2026-02-12 11:13:00 → 11:28:00 AEST" },
  inputs: [
    { mrid: "MARRABEL_NX::CB-031", role: "tripped" },
    { mrid: "MARRABEL_NX::CB-041", role: "tripped" },
    { mrid: "MARRABEL_NX::DS-275-13", role: "fault origin" },
  ],
  summary: { shared_class_count: 1, family_population_ehr: 56 },
  shared: {
    cim_class: "Disconnector",
    sub_class: "BusSectionIsolator",
    model: "VENDOR-A 275 kV Mk-II",
    install_period: "2008-2014",
    silver_plate_wear_risk: "HIGH (per EHR-OERS-2022-Q4 review)",
  },
  verdict: {
    common_mode_identified: true,
    description: "Bus section isolator family — same manufacturer, same vintage, same documented failure mode.",
    recommended_followup: "Accelerate insulation inspection of all 56 same-family disconnectors across EHR 275 kV switchyards.",
  },
});

const SWITCH_STATE_SNAPSHOT_TRUNCATED = JSON.stringify({
  truncated: true,
  original_event: "tool_result",
  original_bytes: 421_837,
  preview:
    "[Truncated to first 4 KiB — modelled vs current state for 134 switches across MARRABEL_NX. Top rows: " +
    "CB-011 CLOSED/CLOSED, CB-012 OPEN/OPEN (planned outage), CB-021 CLOSED/OPEN ⚠, CB-031 CLOSED/OPEN ⚠, " +
    "CB-041 CLOSED/OPEN ⚠, CB-051 CLOSED/OPEN ⚠, CB-052 CLOSED/CLOSED, DS-275-11 CLOSED/CLOSED, " +
    "DS-275-12 CLOSED/CLOSED, DS-275-13 CLOSED/FAULTED ⚠, DS-275-14 CLOSED/CLOSED. … (124 more rows)]",
  note: "Envelope exceeded 64 KiB SSE frame cap (MAX_SSE_FRAME_BYTES). Frontend rendered the preview banner — operator can request the full envelope via download.",
});

const CAUSAL_TIMELINE_RESULT = JSON.stringify({
  anchor: {
    ts: "2026-02-12 11:15:14",
    kind: "isolating",
    source_tag: "BSDIF-SA",
    source_label: "Bus 275-1 differential (Scheme A) operated",
  },
  tag_distribution: {
    ANCHOR: 1,
    initiating: 1,
    isolating: 2,
    responding: 4,
    "state-change": 2,
    "pre-anchor-flux": 1,
  },
  rows: [
    { dt_seconds: -14.0, ts: "2026-02-12 11:15:00", tag: "pre-anchor-flux", source: "SCADA", label: "MW drift", equipment: "MARRABEL_NX::G3::pwr_real", text: "Unit 3 MW drifted 241.0 → 248.0 (+2.9 %)." },
    { dt_seconds: -5.0, ts: "2026-02-12 11:15:09", tag: "state-change", source: "ALARM", label: "CB-OPN", equipment: "MARRABEL_NX::CB-031", text: "CB-031 transition pickup." },
    { dt_seconds: 0.0,  ts: "2026-02-12 11:15:14", tag: "ANCHOR", source: "ALARM", label: "BSDIF-SA", equipment: "MARRABEL_NX::B275-1", text: "Bus 275-1 differential (Scheme A) operated." },
    { dt_seconds: 0.0,  ts: "2026-02-12 11:15:14", tag: "initiating", source: "ALARM", label: "ISOEF", equipment: "MARRABEL_NX::DS-275-13", text: "DS-275-13 earth fault detected — root-cause asset." },
    { dt_seconds: 0.0,  ts: "2026-02-12 11:15:14", tag: "isolating", source: "ALARM", label: "CB-OPN", equipment: "MARRABEL_NX::CB-031", text: "CB-031 opened by Scheme A." },
    { dt_seconds: 0.0,  ts: "2026-02-12 11:15:14", tag: "isolating", source: "ALARM", label: "CB-OPN", equipment: "MARRABEL_NX::CB-041", text: "CB-041 opened by Scheme A." },
    { dt_seconds: 4.0,  ts: "2026-02-12 11:15:18", tag: "responding", source: "ALARM", label: "REVPWR", equipment: "MARRABEL_NX::G3", text: "G3 reverse-power protection — unit no longer feeding open bus." },
    { dt_seconds: 4.0,  ts: "2026-02-12 11:15:18", tag: "responding", source: "SCADA", label: "MW collapse", equipment: "MARRABEL_NX::G3::pwr_real", text: "G3 MW collapsed 248.0 → 0.0 (235 MW lost)." },
    { dt_seconds: 8.0,  ts: "2026-02-12 11:15:22", tag: "responding", source: "ALARM", label: "UFREQ", equipment: "MARRABEL_NX::G4", text: "G4 under-frequency protection at 49.71 Hz." },
    { dt_seconds: 8.0,  ts: "2026-02-12 11:15:22", tag: "responding", source: "SCADA", label: "MW collapse", equipment: "MARRABEL_NX::G4::pwr_real", text: "G4 MW collapsed 189.0 → 0.0 (177 MW lost)." },
    { dt_seconds: 16.0, ts: "2026-02-12 11:15:30", tag: "state-change", source: "SCADA", label: "Bus collapse", equipment: "MARRABEL_NX::B275-1", text: "Bus 275-1 voltage collapsed 275.5 → 0.0 kV." },
    { dt_seconds: 50.0, ts: "2026-02-12 11:16:04", tag: "responding", source: "SCADA", label: "freq nadir", equipment: "EHR::sys::freq_hz", text: "EHR frequency nadir 49.71 Hz — FRS responded within 6 s." },
  ],
  primitives_used: ["find_event_timeline", "find_scada_changes", "find_alarms"],
});

const BUS_ZONE_AUDIT_RESULT = JSON.stringify({
  verdict: "bus_event",
  bus_id: "B275-1",
  bus_tag: "MARRABEL_NX::B275-1",
  anchor_ts: "2026-02-12 11:15:14",
  station_switch_count: 25,
  breaker_count: 4,
  zone_bays: [
    "MARRABEL_NX::CB-031 (G3 bay)",
    "MARRABEL_NX::CB-041 (G4 bay)",
    "MARRABEL_NX::CB-021 (KTG-01 line bay)",
    "MARRABEL_NX::CB-051 (OAK-02 line bay)",
    "MARRABEL_NX::DS-275-11",
    "MARRABEL_NX::DS-275-12",
    "MARRABEL_NX::DS-275-13",
    "MARRABEL_NX::DS-275-14",
  ],
  tripped_in_zone: [
    "MARRABEL_NX::CB-031",
    "MARRABEL_NX::CB-041",
    "MARRABEL_NX::CB-021",
    "MARRABEL_NX::CB-051",
  ],
  out_of_zone_trips: [],
  adjacency_gaps: [],
  primitives_used: ["graph_bus_boundary", "find_alarms", "find_scada_changes"],
});

const BREAKER_FAIL_SIGNATURE_RESULT = JSON.stringify({
  scope: { bus: "MARRABEL_NX::B275-1", anchor_ts: "2026-02-12 11:15:14" },
  anchor_kind: "isolating",
  candidates: [
    {
      equipment: "MARRABEL_NX::CB-031",
      scada_cid: "MARRABEL_NX.CB-031.BKR",
      cbf_score: 0.05,
      modelled_open: true,
      normal_open: false,
      has_open_alarm_in_window: true,
      in_tripped_zone: true,
      anchor_ts: "2026-02-12 11:15:14",
      reasoning: "Fast clear — 16 ms pickup-to-open. No CBF backup operated. Modelled-open and OPEN alarm align.",
    },
    {
      equipment: "MARRABEL_NX::CB-041",
      scada_cid: "MARRABEL_NX.CB-041.BKR",
      cbf_score: 0.04,
      modelled_open: true,
      normal_open: false,
      has_open_alarm_in_window: true,
      in_tripped_zone: true,
      anchor_ts: "2026-02-12 11:15:14",
      reasoning: "Fast clear — 14 ms pickup-to-open. No CBF backup.",
    },
    {
      equipment: "MARRABEL_NX::CB-021",
      scada_cid: "MARRABEL_NX.CB-021.BKR",
      cbf_score: 0.03,
      modelled_open: true,
      normal_open: false,
      has_open_alarm_in_window: true,
      in_tripped_zone: true,
      anchor_ts: "2026-02-12 11:15:14",
      reasoning: "Fast clear — 22 ms pickup-to-open.",
    },
    {
      equipment: "MARRABEL_NX::CB-051",
      scada_cid: "MARRABEL_NX.CB-051.BKR",
      cbf_score: 0.03,
      modelled_open: true,
      normal_open: false,
      has_open_alarm_in_window: true,
      in_tripped_zone: true,
      anchor_ts: "2026-02-12 11:15:14",
      reasoning: "Fast clear — 24 ms pickup-to-open.",
    },
  ],
  primitives_used: ["bus_zone_audit", "find_alarms"],
});

const FREQUENCY_PROFILE_RESULT = JSON.stringify({
  verdict: "system_disturbance",
  fos_classification: "BELOW_OPERATIONAL",
  anchor_ts: "2026-02-12 11:15:14",
  pre_event_baseline_hz: 50.02,
  nem_wide_nadir_hz: 49.71,
  max_delta_f_hz: 0.31,
  recovery_time_s: 100.0,
  regional_spread: [
    {
      cluster_label: "EHR (event-region)",
      n_stations: 12,
      median_nadir_hz: 49.71,
      median_delta_f_hz: 0.31,
      clamped_at_band_edge: false,
      stations: ["MARRABEL_NX", "KETTERING_NX", "OAKBANK_NX", "NORTHVALE_SS"],
    },
    {
      cluster_label: "NER (adjacent)",
      n_stations: 8,
      median_nadir_hz: 49.82,
      median_delta_f_hz: 0.20,
      clamped_at_band_edge: false,
      stations: ["HARROWBRIDGE_TS", "GLENRIDGE_NX"],
    },
    {
      cluster_label: "WER (far)",
      n_stations: 6,
      median_nadir_hz: 49.88,
      median_delta_f_hz: 0.14,
      clamped_at_band_edge: false,
      stations: ["ELDERMOUNT_WF", "KILBARRA_DS"],
    },
  ],
  caveats: [
    "FRS contingency raise dispatched within 6 s of nadir.",
    "Recovery to SOFB within 100 s — GFS containment band 47–52 Hz met.",
  ],
  hz_alarms_in_window: [
    { ts: "2026-02-12 11:16:04", station: "EHR", label: "HZ-NORM" },
    { ts: "2026-02-12 11:15:58", station: "EHR", label: "HZ-EMER" },
  ],
  primitives_used: ["find_scada", "find_alarms"],
});

const SMIRKS_RESULT = JSON.stringify({
  results: [
    {
      title:
        "OER-2025-Q4-018 — EHR 275 kV bus section isolator silver-plating wear advisory",
      source: "SMIRKS-OER-2025-Q4-018",
      score: 0.92,
      text:
        "Following four bus section isolator failures across EHR 275 kV switchyards in 2024–2025, NGA " +
        "issues a standing advisory: inspect silver-plated contact surfaces on VENDOR-A Mk-II " +
        "disconnectors at next scheduled outage. Recurrence risk classified MEDIUM until inspection " +
        "programme complete. Direction reports: NGA-DR-2025-Q4-014, NGA-DR-2025-Q4-022.",
    },
    {
      title:
        "Direction Report NGA-DR-2025-Q4-022 — accelerated inspection of EHR 275 kV bay equipment",
      source: "SMIRKS-DR-2025-Q4-022",
      score: 0.88,
      text:
        "NGA directs EHRT to accelerate the inspection of all 56 VENDOR-A Mk-II bus section " +
        "disconnectors at EHR 275 kV switchyards. Target completion: 31 March 2026. Interim mitigation: " +
        "thermal scan at six-month intervals; report any contact temperature > 60 °C above ambient.",
    },
    {
      title:
        "OER-2026-Q1-003 — precursor scanner threshold tuning for transient voltage dips",
      source: "SMIRKS-OER-2026-Q1-003",
      score: 0.81,
      text:
        "NGA recommends operators consider lowering the sub-threshold KV transient detection floor " +
        "(currently 5 % depression for ≥ 60 s sustained) to 5 % for ≥ 5 s sustained, after the " +
        "GLENRIDGE 2024-03 incident review confirmed a 12 s transient went undetected.",
    },
  ],
  count: 3,
});

/* ── Frames ─────────────────────────────────────────────────────────── */

export const capabilityShowcaseFrames: Frame[] = [
  {
    id: "fc01",
    chapter: "Capability showcase — modern tool surface",
    narration:
      "Before handing off, the investigator runs the modern compound + topology + market-knowledge tools. " +
      "Every new tool that landed in the live product in the 2026-05 sweep fires here, all on the same thread, " +
      "no delegation. Watch the result cards stack.",
    annotation: {
      target: "panel-chat",
      caption:
        "Same investigator thread — modern tool surface. Causal timeline, bus-zone audit, breaker-fail check, " +
        "frequency profile, four extended graph tools, and the SMIRKS knowledge base.",
      placement: "left",
    },
    transition_ms: 700,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-causal",
            name: "reconstruct_event_timeline_causal",
            arguments: { station: "MARRABEL_NX", start: "2026-02-12 11:15:00", end: "2026-02-12 11:18:00" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc02",
    narration:
      "The causal timeline reconstructs the chain in relative-seconds: DS-275-13 flashover at t=0, bus " +
      "differential pickup at t=0.04 s, both CBs open by t=0.12 s, unit consequences at t=4–8 s, frequency " +
      "nadir at t=50 s. Every row carries a causal note — proven, not guessed.",
    transition_ms: 2000,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-causal",
        status: "complete",
        duration_ms: 950,
        result: CAUSAL_TIMELINE_RESULT,
      },
    },
  },
  {
    id: "fc03",
    narration:
      "Bus zone audit next — was every modelled-open element actually accompanied by an OPEN alarm? " +
      "Adjacency gaps are how silent breaker failures hide. Watch the verdict.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-bza",
            name: "bus_zone_audit",
            arguments: { bus_section: "MARRABEL_NX::B275-1", start: "2026-02-12 11:15:00", end: "2026-02-12 11:16:00" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc04",
    narration:
      "Clean audit. Four modelled-open breakers, four OPEN alarms — one-to-one. No adjacency gaps. The protection " +
      "operated exactly as designed. That eliminates an entire class of follow-up investigation.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-bza",
        status: "complete",
        duration_ms: 720,
        result: BUS_ZONE_AUDIT_RESULT,
      },
    },
  },
  {
    id: "fc05",
    narration:
      "Breaker-fail signature next — would breaker-failure protection have operated if a CB stuck? Scoring across " +
      "every CB in the zone.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-cbf",
            name: "breaker_fail_signature",
            arguments: { bus_section: "MARRABEL_NX::B275-1", incident_time: "2026-02-12 11:15:14" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc06",
    narration:
      "Every CB scored 0.03–0.05 — no breaker-failure pattern. Trip times all within 24 ms of pickup. CBF backup did " +
      "not operate because it did not need to. The Scheme A primary did the job.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-cbf",
        status: "complete",
        duration_ms: 700,
        result: BREAKER_FAIL_SIGNATURE_RESULT,
      },
    },
  },
  {
    id: "fc07",
    narration:
      "Frequency disturbance profile — quantifies the system-wide consequence. Nadir, time below band, recovery, GFS " +
      "compliance.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-freq",
            name: "frequency_disturbance_profile",
            arguments: { region: "EHR", start: "2026-02-12 11:15:14", end: "2026-02-12 11:18:00" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc08",
    narration:
      "Nadir 49.71 Hz, 3.8 s below SOFEB, 8.2 s below SOFB, recovered to nominal in 100 s. GFS met. FRS dispatched 412 " +
      "MW within 6 s. That entire line item is now closed without an operator opening the SCADA frequency app.",
    transition_ms: 2000,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-freq",
        status: "complete",
        duration_ms: 820,
        result: FREQUENCY_PROFILE_RESULT,
      },
    },
  },
  {
    id: "fc09",
    narration:
      "Now the extended graph family. Bus-boundary first — full set of breakers and disconnectors that ring the faulted " +
      "Bus 275-1.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-busb",
            name: "graph_bus_boundary",
            arguments: { bus_section: "MARRABEL_NX::B275-1" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc10",
    narration:
      "Four boundary breakers — two raised OPEN alarms (the protection-driven ones), two opened silently. Four boundary " +
      "disconnectors — one shows the FAULTED state on DS-275-13. The agent now has the exact perimeter to restore.",
    transition_ms: 1800,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-busb",
        status: "complete",
        duration_ms: 680,
        result: BUS_BOUNDARY_RESULT,
      },
    },
  },
  {
    id: "fc11",
    narration:
      "Corridor endpoints — full bay-CN path of the MARRABEL → KETTERING line so the dispatcher knows exactly which bay " +
      "to open at each end.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-corr",
            name: "graph_corridor_endpoints",
            arguments: { line: "MARRABEL→KETTERING No. 1", voltage_kv: 275 },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc12",
    narration:
      "Two endpoints, full bay-CN paths on both sides. The corridor view is what protects the dispatcher from issuing " +
      "instructions that assume the wrong bay arrangement.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-corr",
        status: "complete",
        duration_ms: 700,
        result: CORRIDOR_ENDPOINTS_RESULT,
      },
    },
  },
  {
    id: "fc13",
    narration:
      "Breaker neighbourhood — which CBs share electrical proximity to CB-031, and which of those moved sympathetically?",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-bn",
            name: "graph_breaker_neighbourhood",
            arguments: { breaker: "MARRABEL_NX::CB-031", hops: 2 },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc14",
    narration:
      "Six neighbours surveyed. CB-041 moved sympathetically — same bus, same trip signal. Bus 275-2 neighbours all stayed " +
      "closed, confirming the isolation barrier held.",
    transition_ms: 1800,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-bn",
        status: "complete",
        duration_ms: 680,
        result: BREAKER_NEIGHBOURHOOD_RESULT,
      },
    },
  },
  {
    id: "fc15",
    narration:
      "Common-mode devices — does this incident's equipment share a class with prior failures? This is what links the " +
      "event to the wider fleet risk picture.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-cmd",
            name: "graph_common_mode_devices",
            arguments: { mrids: ["MARRABEL_NX::CB-031", "MARRABEL_NX::CB-041", "MARRABEL_NX::DS-275-13"] },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc16",
    narration:
      "VENDOR-A Mk-II bus section isolators — 56 same-family units across EHR 275 kV switchyards. The OER 2022-Q4 review " +
      "already flagged this class for silver-plating wear. The follow-up is institutional, not just local.",
    transition_ms: 2200,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-cmd",
        status: "complete",
        duration_ms: 920,
        result: COMMON_MODE_RESULT,
      },
    },
  },
  {
    id: "fc17",
    narration:
      "Equipment connections — CIM-level adjacency for CB-031 itself, so the agent has the protection-zone membership " +
      "and the connected transformer winding on file.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-eqc",
            name: "graph_equipment_connections",
            arguments: { mrid: "MARRABEL_NX::CB-031" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc18",
    narration:
      "CB-031 sits between DS-275-13 and the G3 transformer winding, and participates in two protection zones — the bus " +
      "zone and the G3 differential. That's the exact pair of protections that operated.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-eqc",
        status: "complete",
        duration_ms: 620,
        result: EQUIPMENT_CONNECTIONS_RESULT,
      },
    },
  },
  {
    id: "fc19",
    narration:
      "Find alarm by mrid — drill into the bus differential alarm body itself so the analysis cites the raw text, not a " +
      "paraphrase.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-abm",
            name: "find_alarm_by_mrid",
            arguments: { mrid: "mrid-mb-bus-01" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc20",
    narration:
      "The raw alarm body confirms phase-R-to-earth fault, Scheme A trip-all to every CB on Bus 275-1. Verbatim — the " +
      "evidence in its original form.",
    transition_ms: 1600,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-abm",
        status: "complete",
        duration_ms: 480,
        result: ALARM_BY_MRID_RESULT,
      },
    },
  },
  {
    id: "fc21",
    narration:
      "Switch state snapshot — every modelled vs current switch state across MARRABEL_NX. This envelope exceeds the 64 KiB " +
      "SSE frame cap. Watch the truncation banner.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-sss",
            name: "graph_switch_state_snapshot",
            arguments: { station: "MARRABEL_NX", at_time: "2026-02-12 11:18:00" },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc22",
    narration:
      "Truncated to 4 KiB preview — the operator can request the full envelope on demand. Note the bundled summary still " +
      "highlighted every state mismatch up front so the investigation does not lose signal to the size cap.",
    transition_ms: 1900,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-sss",
        status: "complete",
        duration_ms: 850,
        result: SWITCH_STATE_SNAPSHOT_TRUNCATED,
      },
    },
  },
  {
    id: "fc23",
    chapter: "Market knowledge — SMIRKS",
    narration:
      "Last tool of the showcase: SMIRKS — the current AEMO OERs and Direction Reports corpus. This complements the older " +
      "investigation-clues library by surfacing what the regulator has said about this equipment class in the last six " +
      "months.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-smk",
            name: "search_smirks",
            arguments: {
              query:
                "EHR 275 kV bus section isolator silver-plating wear failure VENDOR-A Mk-II disconnector inspection " +
                "programme accelerated outage",
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "fc24",
    narration:
      "Three hits. The top hit is an OER from Q4 last year already calling out this exact equipment class with a standing " +
      "advisory. The Direction Report names a 31 March 2026 inspection deadline. The third hit recommends tightening the " +
      "precursor-scanner threshold — directly relevant to the 10:38 transient the radar caught. The dispatcher now has " +
      "regulator-cited grounding for every action it pushes.",
    transition_ms: 2400,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-smk",
        status: "complete",
        duration_ms: 1100,
        result: SMIRKS_RESULT,
      },
    },
  },
  {
    id: "fc25",
    narration:
      "Capability showcase complete. The investigator has now exercised every modern tool family: compound investigation " +
      "tools, extended graph topology, market knowledge. Handing back to the existing flow.",
    transition_ms: 600,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "\n\n— end capability showcase —\n\nProceeding to dispatcher delegation with the full modern evidence pack.",
      },
    },
  },
];
