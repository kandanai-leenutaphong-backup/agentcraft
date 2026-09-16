/**
 * Phase 4c — Differential diagnosis.
 *
 * Module role:
 *   The reasoning spine of the demo. The agent names three candidate causes,
 *   then eliminates two with evidence before converging on the third. Runs
 *   between the opening station summary and the historical corroboration.
 *
 *   Order matters: elimination comes BEFORE the historical pattern match, so
 *   the match corroborates a conclusion already reached rather than producing
 *   it.
 *
 *   Tool result envelopes are the ones authored for 04b_capability_showcase.
 *
 * Narration:
 *   Voice lines written by GPT-5.6 Sol against a fixed beat plan.
 */

import type { Frame } from "../../../scenarioSchema";

/* ── Tool result envelopes ──────────────────────────────────────────── */

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

/* ── Frames ──────────────────────────────────────────── */

export const differentialFrames: Frame[] = [
  {
    id: "d001",
    chapter: "Differential",
    narration:
      "Three candidate causes: busbar fault, breaker failure, or protection miscoordination. The agent will test and eliminate, not guess.",
    transition_ms: 1700,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text:
          "Three candidate causes are consistent with what we have so far: a busbar fault, a breaker failure, or protection miscoordination. I will test each against the record and eliminate rather than guess.",
      },
    },
  },

  {
    id: "d002",
    narration:
      "Causal chain: BSDIF-SA anchors at 11:15:14. Fourteen seconds earlier, Unit 3 drifts 241.0 to 248.0 MW, up 2.9%; CB-031 transition pickup follows.",
    transition_ms: 200,
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
    id: "d003",
    narration:
      "The drift and pickup precede the trip. This is a causal chain with an origin, not an event list.",
    transition_ms: 2400,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-causal",
        status: "complete",
        duration_ms: 800,
        result: CAUSAL_TIMELINE_RESULT,
      },
    },
  },

  {
    id: "d004",
    narration:
      "Breaker-failure scores: CB-031 at 0.05, CB-041 at 0.04. Clear times: 16 ms and 14 ms. No circuit-breaker-fail backup operates.",
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
    id: "d005",
    narration:
      "Breaker failure eliminated. Both breakers clear in milliseconds. They do their job, fast.",
    transition_ms: 2300,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-cbf",
        status: "complete",
        duration_ms: 800,
        result: BREAKER_FAIL_SIGNATURE_RESULT,
      },
    },
  },

  {
    id: "d006",
    narration:
      "Bus-zone verdict: bus_event. All four tripped breakers sit inside the protection zone. Zero out-of-zone trips. Zero adjacency gaps.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-zone",
            name: "bus_zone_audit",
            arguments: { bus_section: "MARRABEL_NX::B275-1", start: "2026-02-12 11:15:00", end: "2026-02-12 11:16:00" },
            status: "running",
          },
        ],
      },
    },
  },

  {
    id: "d007",
    narration:
      "Protection miscoordination eliminated. Nothing trips that should not. One candidate remains.",
    transition_ms: 2300,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-zone",
        status: "complete",
        duration_ms: 800,
        result: BUS_ZONE_AUDIT_RESULT,
      },
    },
  },

];

/** Convergence on the surviving candidate, plus system impact. */
export const rootCauseFrames: Frame[] = [
  {
    id: "d008",
    narration:
      "The tripped breakers and fault-origin disconnector share one class: bus section isolators, VENDOR-A 275 kV Mk-II, installed 2008-2014, with documented HIGH silver-plate wear risk.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-common",
            name: "graph_common_mode_devices",
            arguments: { mrids: ["MARRABEL_NX::CB-031", "MARRABEL_NX::CB-041", "MARRABEL_NX::DS-275-13"] },
            status: "running",
          },
        ],
      },
    },
  },

  {
    id: "d009",
    narration:
      "That same family includes 56 disconnectors across EHR. This is a regional exposure, not one station's problem.",
    transition_ms: 2600,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-common",
        status: "complete",
        duration_ms: 900,
        result: COMMON_MODE_RESULT,
      },
    },
  },

  {
    id: "d010",
    narration:
      "Frequency falls from a 50.02 Hz baseline to 49.71 Hz, a 0.31 Hz deviation, then recovers in 100 seconds.",
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
    id: "d011",
    narration:
      "The disturbance is measurable across three regional clusters, deepest in the event region.",
    transition_ms: 2200,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-freq",
        status: "complete",
        duration_ms: 800,
        result: FREQUENCY_PROFILE_RESULT,
      },
    },
  },
];
