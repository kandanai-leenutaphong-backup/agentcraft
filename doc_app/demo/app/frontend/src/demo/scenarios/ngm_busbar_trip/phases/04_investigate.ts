/**
 * Phase 4 — Investigator chat frames.
 *
 * Module role:
 *   The Investigator agent runs a realistic tool sequence to characterise
 *   the MARRABEL_NX busbar event. Tools mirror the production agent_config
 *   (find_station_summary → find_event_timeline → find_scada_changes →
 *   search_investigation_clues → search_participants → graph_bus_topology),
 *   then a streamed analysis, then a delegate_to_agent hand-off.
 *
 * Cell collaborators:
 *   - phases/05_delegate.ts — picks up where the delegate_to_agent call
 *     completes. The dispatcher tab is switched there, not here.
 *
 * Authoring notes:
 *   Every tool name in this file appears in
 *   ``control/agent_config.yaml`` under the Investigator agent. Result
 *   shapes match the renderers registered in
 *   ``components/chat/tool-renderers/index.ts``:
 *     - find_*           → TabularResult ({columns, data} or {columns, rows})
 *     - search_*         → SearchResultCards ({results:[{title,source,score,text}], count})
 *     - graph_*          → GraphResult (JSON array of objects)
 *     - delegate_to_agent → DelegationResult (markdown body)
 *   Adjusting a result shape without checking the renderer will fall
 *   back to JsonFallback and look broken.
 *
 * Runtime: ~55 seconds across 30 frames.
 */

import type { Frame } from "../../../scenarioSchema";

/* ─── Result payloads kept above the frames array so the timing
 *     scaffolding stays scannable. Each is a JSON.stringify-ready
 *     object whose shape matches the registered renderer. */

/* find_station_summary — equipment inventory + alarm/SCADA roll-up.
 * Renderer: TabularResult ({columns, data}). */
const STATION_SUMMARY_RESULT = JSON.stringify({
  columns: ["category", "equipment_class", "count", "alarms", "scada_changes"],
  data: [
    ["primary_plant", "BusBarSection", 2, 4, 3],
    ["primary_plant", "Switch (CB / Isolator)", 25, 4, 0],
    ["primary_plant", "TransformerWinding", 3, 0, 1],
    ["primary_plant", "Generator", 4, 2, 4],
    ["primary_plant", "Terminal", 1, 0, 0],
    ["secondary", "GenericEquipment (relays / instr.)", 18, 0, 0],
  ],
  station: "MARRABEL_NX",
  region: "EHR",
  rated_mw: 1000,
  unit_count: 4,
});

/* find_event_timeline — unified alarm + SCADA timeline. Same shape as
 * the standard investigator reference shape: each row is one chronological event with a
 * type (ALARM | SCADA) so the operator sees the causal chain in one
 * pass. */
const EVENT_TIMELINE_RESULT = JSON.stringify({
  columns: ["timestamp_aest", "type", "equipment", "description", "priority"],
  data: [
    ["2026-02-12 11:15:00", "SCADA", "MARRABEL_NX::G3::pwr_real", "MW dropped 241.0 → 248.0 (-17.7%)", null],
    ["2026-02-12 11:15:09", "ALARM", "MARRABEL_NX::CB-031", "[CB-OPN] G3 line CB transition", "Tier-1"],
    ["2026-02-12 11:15:14", "ALARM", "MARRABEL_NX::B275-1", "[BSDIF-SA] bus diff op (scheme A)", "Tier-1"],
    ["2026-02-12 11:15:14", "ALARM", "MARRABEL_NX::DS-275-13", "[ISOEF] DS-275-13 ground fault", "Tier-1"],
    ["2026-02-12 11:15:14", "ALARM", "MARRABEL_NX::CB-041", "[CB-OPN] G4 line CB transition", "Tier-1"],
    ["2026-02-12 11:15:18", "ALARM", "MARRABEL_NX::G3", "[REVPWR] backfeed event", "Tier-1"],
    ["2026-02-12 11:15:18", "SCADA", "MARRABEL_NX::G3::pwr_real", "MW collapsed 248.0 → 0.0 (TRIP, 235 MW lost)", null],
    ["2026-02-12 11:15:20", "ALARM", "MARRABEL_NX::B275-1", "[UNREAS-F] freq sample out of band (45.1 Hz)", "Tier-4"],
    ["2026-02-12 11:15:20", "ALARM", "MARRABEL_NX::B275-1", "[KV-LO-D] bus volt 0.0 kV", "Tier-6"],
    ["2026-02-12 11:15:22", "ALARM", "MARRABEL_NX::G4", "[UFREQ] freq band exit (49.71 Hz)", "Tier-1"],
    ["2026-02-12 11:15:22", "SCADA", "MARRABEL_NX::G4::pwr_real", "MW collapsed 189.0 → 0.0 (TRIP, 177 MW lost)", null],
    ["2026-02-12 11:15:30", "SCADA", "MARRABEL_NX::B275-1::volt_kv", "Voltage collapsed 275.5 → 0.0 kV", null],
    ["2026-02-12 11:15:30", "SCADA", "KETTERING_NX::L:MRB-01::pwr_real", "Inter-regional flow surged 320 → 710 MW (89% rated)", null],
    ["2026-02-12 11:15:42", "ALARM", "MARRABEL_NX::CB-031", "[BWFL-DLY] buswire diag (delayed indication)", "Tier-3"],
    ["2026-02-12 11:16:04", "SCADA", "EHR::sys::freq_hz", "Regional frequency reached nadir 49.71 Hz", null],
    ["2026-02-12 11:16:08", "SCADA", "MARRABEL_NX::G1::pwr_real", "Stable at 248 MW — Unit 1 unaffected (Bus 275-2)", null],
  ],
  count: 16,
  window: "2026-02-12 11:13 → 11:28 AEST",
});

/* find_scada_changes — significant-change-only subset. Highlights the
 * MW losses and the inter-regional surge. Different lens, same evidence
 * — the agent uses this to confirm the magnitude. */
const SCADA_CHANGES_RESULT = JSON.stringify({
  columns: ["timestamp_aest", "TagId", "prev_val", "new_val", "abs_drop", "pct_change", "interpretation"],
  data: [
    ["2026-02-12 11:15:18", "MARRABEL_NX::G3::pwr_real", 241.0, 0.0, 241.0, "-100.0%", "TRIP"],
    ["2026-02-12 11:15:22", "MARRABEL_NX::G4::pwr_real", 189.0, 0.0, 189.0, "-100.0%", "TRIP"],
    ["2026-02-12 11:15:30", "MARRABEL_NX::B275-1::volt_kv", 275.5, 0.0, 275.5, "-100.0%", "BUS COLLAPSE"],
    ["2026-02-12 11:15:18", "MARRABEL_NX::G3::pwr_react", 96.0, 0.0, 96.0, "-100.0%", "REACTIVE LOSS"],
    ["2026-02-12 11:15:22", "MARRABEL_NX::G4::pwr_react", 75.0, 0.0, 75.0, "-100.0%", "REACTIVE LOSS"],
    ["2026-02-12 11:15:30", "KETTERING_NX::L:MRB-01::pwr_real", 320.0, 710.0, -390.0, "+121.9%", "POST-CONTINGENT SURGE"],
    ["2026-02-12 11:15:30", "OAKBANK_NX::L:MRB-02::pwr_real", 145.0, 318.0, -173.0, "+119.3%", "POST-CONTINGENT SURGE"],
    ["2026-02-12 11:16:04", "EHR::sys::freq_hz", 50.02, 49.71, 0.34, "-0.7%", "FREQUENCY NADIR"],
    ["2026-02-12 11:16:08", "MARRABEL_NX::G1::pwr_real", 248.0, 248.0, 0.0, "0.0%", "STABLE (Bus 275-2)"],
  ],
  count: 9,
  threshold: "abs_drop > 50 MW or pct_change > 10%",
});

/* search_investigation_clues — historical pattern match. The killer
 * tool: a near-identical near-hit from the same equipment class.
 * Renderer: SearchResultCards ({results:[{title,source,score,text}],count}).
 *
 * The match is fictional but the structure mirrors the real near-hit
 * library shape — title, source citation, similarity score, body. */
const CLUES_RESULT = JSON.stringify({
  results: [
    {
      title:
        "Trip of the GLENRIDGE_NX 275 kV Bus 275-1 on 08 October 2022 — bus section isolator flashover",
      source: "CLUE-2024-GLENRIDGE-BUSBAR",
      score: 0.94,
      text:
        "GLENRIDGE_NX 275 kV Bus 275-1 tripped after an inter-phase flashover on bus section isolator " +
        "DS-275-12. Two units (188 MW and 152 MW) disconnected from the Bus 275-1, leaving the Bus 275-2 " +
        "intact. Root cause was tracked to insulation degradation on the open red-phase contact of " +
        "DS-275-12 — a 12-second voltage transient was logged 28 minutes before the trip but did not " +
        "raise an alarm because the duration was below the 60 s sustained-low threshold. " +
        "Recommendation in the post-event review: add transient-dip detection to the precursor " +
        "scanner. RTO advised they would inspect adjacent ISO bays at the next scheduled outage; " +
        "DS-275-12 had not yet been inspected at the time of failure. CBF protection cleared the fault " +
        "in 412 ms. Recovery: Bus 275-1 re-energised after 4h 20m with DS-275-12 isolated.",
    },
    {
      title:
        "Trip of the BIRRALEE_NX 275 kV bus zone on 4 May 2021 — sympathetic CB operation",
      source: "CLUE-2023-BIRRALEE-CBF",
      score: 0.71,
      text:
        "BIRRALEE_NX 275 kV bus zone tripped following a phase-to-earth fault on a connected " +
        "circuit. Bus zone protection operated as designed but a delayed CB indication arrived 3 " +
        "minutes later via the RTU gateway, momentarily confusing the control room timeline. Lessons " +
        "logged: (1) confirm RTU buffering health during post-event review; (2) bus alarm timestamps " +
        "are authoritative, breaker timestamps may lag.",
    },
    {
      title:
        "Bus section isolator failure modes — internal review 2022",
      source: "CLUE-INSULATION-DEGRADATION",
      score: 0.62,
      text:
        "Survey of 14 bus section isolator failures across the EHR region 2018-2022. Common " +
        "precursor signature: 5–20 second voltage transient at the connected busbar, depth 5–15 % " +
        "of nominal, recovering before any sustained-low alarm fires. Recommended detection: " +
        "sub-threshold transient scanner with 5 second resolution.",
    },
  ],
  count: 3,
});

/* search_participants — NEM participant lookup for the asset owner.
 * Identifies the responsible RTO / generator party so the dispatcher
 * knows who to call. */
const PARTICIPANTS_RESULT = JSON.stringify({
  results: [
    {
      title: "South-East Regional Transmission (EHRT) — RTO for EHR region",
      source: "PARTICIPANT-EHRT",
      score: 0.96,
      text:
        "South-East Regional Transmission is the RTO for the EHR region under GOR 4.3.1. " +
        "Responsible for transmission asset switching, protection setting, alarm response, and " +
        "advising the National Grid Authority of threats to power system security. Owner of MARRABEL_NX " +
        "275 kV switchyard infrastructure including all bus sections, isolators, and bus zone " +
        "protection. Duplicate bus zone protection installed at MARRABEL 275 kV (Schemes A and B) " +
        "since 2021. Control room: EHRT Regional Operations, +61 8 0000 9000, 24/7.",
    },
    {
      title: "Marrabel Power Holdings — registered generator",
      source: "PARTICIPANT-MARRABEL-GEN",
      score: 0.88,
      text:
        "Operator of the four 250 MW combined-cycle units at MARRABEL_NX. Connection point: " +
        "MARRABEL_NX 275 kV Buses A (Units 1–2 + 3) and B (Units 4 + spare). Note connection arrangement " +
        "differs from the as-built diagram retained on file: Unit 1 was reassigned to the Bus 275-2 in " +
        "the 2024 outage. Operator dispatch desk: +61 8 0000 9100. Standing market notice subscriber " +
        "for EHR regional events.",
    },
  ],
  count: 2,
});

/* graph_bus_topology — CIM bus-section graph. Renderer: GraphResult
 * (JSON array of objects). Each entry is a bus + the connected
 * equipment, so the operator can see at a glance which units sat on
 * which bus. */
const BUS_TOPOLOGY_RESULT = JSON.stringify([
  {
    bus_section: "MARRABEL_NX::B275-1",
    voltage_kv: 220,
    status: "DE-ENERGISED (post-event)",
    connected_equipment: [
      "MARRABEL_NX::G3 (CB-031, DS-275-13)",
      "MARRABEL_NX::G4 (CB-041, DS-275-14)",
      "MARRABEL_NX::L:KTG-01 (CB-021)",
      "MARRABEL_NX::L:OAK-02 (CB-051)",
    ],
    bus_section_isolators: ["DS-275-11", "DS-275-12", "DS-275-13", "DS-275-14"],
    fault_indicator: "DS-275-13 — earth fault alarm 11:15:14",
  },
  {
    bus_section: "MARRABEL_NX::B275-2",
    voltage_kv: 220,
    status: "ENERGISED — nominal 275.4 kV",
    connected_equipment: [
      "MARRABEL_NX::G1 (CB-011) — STABLE 248 MW",
      "MARRABEL_NX::G2 (CB-012) — OFFLINE (planned outage)",
      "MARRABEL_NX::L:KTG-02 (CB-022)",
      "MARRABEL_NX::L:OAK-01 (CB-052)",
    ],
    bus_section_isolators: ["ISO-B1", "ISO-B2", "ISO-B3", "ISO-B4"],
    fault_indicator: null,
  },
  {
    bus_section: "MARRABEL_NX::TIE:B275-1-B275-2",
    voltage_kv: 220,
    status: "OPEN (normal operating state)",
    connected_equipment: ["CB-TIE-AB (open)", "ISO-TIE-A", "ISO-TIE-B"],
    note: "Bus tie open — A and B operate independently",
  },
]);

/* R1 (2026-05-26): delegation tool call removed — single-agent
 * GridManager flow per MODERNIZATION.md. The DELEGATION_RESULT
 * envelope previously rendered here is retired. */

export const investigateFrames: Frame[] = [
  /* f001 — User message: a substantive prompt that mirrors the standard
   * reference. The operator hands the situation context up front so
   * the agent doesn't have to re-derive it from the alarm log. */
  {
    id: "f001",
    chapter: "Investigation",
    narration:
      "The operator hands the case to the Investigator agent with the full situation context attached.",
    annotation: {
      target: "panel-chat",
      caption:
        "Right column is the chat panel. The Investigator agent will work the case here, calling tools and surfacing what it finds.",
      placement: "left",
    },
    transition_ms: 800,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "user",
        text:
          "Investigate MARRABEL_NX, 2026-02-12 11:13:00 → 11:28:00. Alarm signals: cb_trip=2, " +
          "bus_diff=1, prot_op=2, earth_fault=1. SCADA signals: gen_trip=2, bus_collapse=1, " +
          "line_overload=1. MW impact: 412 MW lost (43% of station rated, 1.8% of NGM live).",
      },
    },
  },

  /* f002 — find_station_summary call. Standard opener. */
  {
    id: "f002",
    narration:
      "Opening wide before drilling in: a high-level station summary.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-summary",
            name: "find_station_summary",
            arguments: {
              station: "MARRABEL_NX",
              start: "2026-02-12 11:13",
              end: "2026-02-12 11:28",
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f003 — station_summary result. */
  {
    id: "f003",
    narration:
      "Wide-angle picture: 2 busbars, 4 generators, 25 switches, plus instrumentation.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-summary",
        status: "complete",
        duration_ms: 700,
        result: STATION_SUMMARY_RESULT,
      },
    },
  },

  /* f004 — find_event_timeline call. */
  {
    id: "f004",
    narration:
      "Now the unified timeline — alarms and SCADA on one chronological axis. The agent is " +
      "trying to pin the initiating sequence. Watch what arrives.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-timeline",
            name: "find_event_timeline",
            arguments: {
              station: "MARRABEL_NX",
              start: "2026-02-12 11:13",
              end: "2026-02-12 11:28",
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f005 — event_timeline result. The full causal chain in one table. */
  {
    id: "f005",
    narration:
      "Sixteen events across thirteen seconds. The first significant SCADA change at 11:15:00 " +
      "is the Unit 3 MW dropping below nominal — a quiet leading indicator. Then at 11:15:14 " +
      "the bus differential operated and DS-275-13 raised an earth fault in the same second — " +
      "that is the protection picking up the fault and the location it picked it up at. The " +
      "two CB-trip alarms follow as the protection isolates Units 3 and 4. This is the answer.",
    transition_ms: 2200,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-timeline",
        status: "complete",
        duration_ms: 1200,
        result: EVENT_TIMELINE_RESULT,
      },
    },
  },

  /* f006 — find_scada_changes call to confirm magnitude. */
  {
    id: "f006",
    narration:
      "Cross-check the magnitude. The agent calls find_scada_changes — the significant-change " +
      "subset — to quantify the loss and confirm the inter-regional response.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-changes",
            name: "find_scada_changes",
            arguments: {
              station: "MARRABEL_NX",
              include_neighbours: true,
              start: "2026-02-12 11:15",
              end: "2026-02-12 11:17",
              min_drop_mw: 50,
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f007 — scada_changes result. */
  {
    id: "f007",
    narration:
      "Magnitude confirmed: 235 MW from Unit 3, 177 MW from Unit 4 — 412 MW total. The two " +
      "inter-regional surges at the bottom — KETTERING and OAKBANK each picking up an extra " +
      "~190 MW within a second — are the network compensating for the loss. KETTERING hit 89% " +
      "of its rating. That's a follow-up the dispatcher needs to know about.",
    transition_ms: 2000,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-changes",
        status: "complete",
        duration_ms: 900,
        result: SCADA_CHANGES_RESULT,
      },
    },
  },

  /* f008 — graph_bus_topology call to confirm bus assignment. */
  {
    id: "f008",
    narration:
      "Now the CIM graph: which units sat on which busbar.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-graph",
            name: "graph_bus_topology",
            arguments: {
              station: "MARRABEL_NX",
              voltage_kv: 220,
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f009 — graph_bus_topology result. */
  {
    id: "f009",
    narration:
      "Units 3 and 4 both connect to Bus 275-1 through disconnectors DS-275-13 and DS-275-14.",
    transition_ms: 1800,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-graph",
        status: "complete",
        duration_ms: 800,
        result: BUS_TOPOLOGY_RESULT,
      },
    },
  },

  /* f010 — search_investigation_clues call. The clue tool is the one
   * that turns this from a slow-grind investigation into something
   * that beats the human. */
  {
    id: "f010",
    chapter: "Pattern matching",
    narration:
      "Now the historical near-hit and post-event library.",
    annotation: {
      target: "panel-chat",
      caption:
        "Each tool the agent calls renders its result inline as a card here. Look for the high-score historical match.",
      placement: "left",
    },
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-clues",
            name: "search_investigation_clues",
            arguments: {
              query:
                "MARRABEL 275 kV Bus 275-1 trip with bus section isolator earth fault, two-unit " +
                "loss, voltage transient precursor — pattern match against historical near-hits",
              filters: { equipment_class: "BusSectionIsolator", voltage_kv: 220 },
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f011 — clues result. The 0.94 GLENRIDGE match is the punchline. */
  {
    id: "f011",
    narration:
      "Historical search returns GLENRIDGE_NX, March 2024: similarity 0.94, same failure mode.",
    transition_ms: 2200,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-clues",
        status: "complete",
        duration_ms: 1100,
        result: CLUES_RESULT,
      },
    },
  },

  /* f012 — search_participants call to identify the responsible RTO. */
  {
    id: "f012",
    narration:
      "Last call: the participant registry, for the responsible parties.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-parties",
            name: "search_participants",
            arguments: {
              query: "MARRABEL_NX RTO transmission operator generator owner EHR region",
              region: "EHR",
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f013 — participants result. */
  {
    id: "f013",
    narration:
      "South-East Regional Transmission is the RTO; Marrabel Power Holdings the registered generator.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-parties",
        status: "complete",
        duration_ms: 600,
        result: PARTICIPANTS_RESULT,
      },
    },
  },

  /* f014 — Open the streamed analysis bubble. */
  {
    id: "f014",
    chapter: "Analysis",
    narration:
      "The agent structures the analysis: what is established, what is inferred, and what remains unknown.",
    annotation: {
      target: "panel-chat",
      caption:
        "Streamed analysis: confirmed facts vs. clue-based hypotheses are kept separate so the operator knows what is proven and what is inference.",
      placement: "left",
    },
    transition_ms: 90,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
      },
    },
  },

  /* f015–f024 — Streamed analysis. Each chunk is a coherent paragraph
   * fragment so the operator can read along as it arrives. */
  {
    id: "f015",
    transition_ms: 80,
    patch: { "chat.append_token": { agent: "investigator", text: "## What happened\n\n" } },
  },
  {
    id: "f016",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "**Initiating event:** at **11:15:14 AEST**, the 275 kV Bus 275-1 at MARRABEL_NX tripped " +
          "after an earth fault on bus section isolator **DS-275-13**. Bus differential protection " +
          "(Scheme A) operated correctly, opening CB-031 and CB-041 within ~16 ms.\n\n",
      },
    },
  },
  {
    id: "f017",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "**Confirmed consequences:**\n" +
          "- Unit 3 disconnected — 235 MW lost (reverse-power protection at 11:15:18).\n" +
          "- Unit 4 disconnected — 177 MW lost (under-frequency at 49.71 Hz, 11:15:22).\n" +
          "- 275 kV Bus 275-1 de-energised (275.5 → 0.0 kV at 11:15:30).\n" +
          "- Inter-regional flows compensated: KETTERING 320 → 710 MW (89 % rated), OAKBANK " +
          "145 → 318 MW.\n" +
          "- EHR frequency nadir **49.71 Hz** at 11:16:04, recovered within 100 s.\n" +
          "- Unit 1 unaffected — confirmed via CIM graph as connected through Bus 275-2.\n\n",
      },
    },
  },
  {
    id: "f018",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "## Most likely mechanism\n\n" +
          "Inter-phase flashover on the open red-phase contact of bus section isolator **DS-275-13**, " +
          "triggering bus differential protection on the Bus 275-1. Mechanism is supported by:\n" +
          "- Historical near-hit at GLENRIDGE_NX, March 2024 — **0.94 similarity** — same " +
          "equipment class, same protection response, same precursor signature.\n" +
          "- Internal review of 14 EHR bus section isolator failures (2018–2022) — same " +
          "transient-dip precursor profile.\n\n",
      },
    },
  },
  {
    id: "f019",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "## What is not yet proven\n\n" +
          "- Direct evidence of insulation degradation on DS-275-13 requires physical inspection " +
          "and insulation-resistance testing. The earth-fault alarm proves a fault, not its " +
          "physical mechanism.\n" +
          "- Whether the GLENRIDGE precursor signature also fired here. The situations panel " +
          "showed an INVESTIGATE-grade transient at 10:38 — that is a separate evidence trail " +
          "the operator may want me to pull (see precursor follow-up).\n\n",
      },
    },
  },
  {
    id: "f020",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "## Responsible parties\n\n" +
          "- **South-East Regional Transmission (EHRT)** — RTO, owns the busbar and protection.\n" +
          "- **Marrabel Power Holdings** — generator operator, owns Units 1–4.\n\n",
      },
    },
  },
  {
    id: "f021",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "## Bottom line\n\n" +
          "MARRABEL_NX 275 kV Bus 275-1 experienced a **non-credible double-unit contingency** " +
          "(Operating Code §4.7.2(a)(1)(i)). Generation lost: 412 MW. Frequency nadir 49.71 Hz. Cause " +
          "identified to **DS-275-13 earth fault**, mechanism corroborated by a strong historical " +
          "match. Unit 1 confirmed safe on Bus 275-2.\n\n",
      },
    },
  },
  {
    id: "f022",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "Handing this to the **Dispatcher** for grounded operator actions. The Dispatcher will " +
          "search OPNET, near-hit reports, and station contacts, then push prioritised actions to " +
          "the operator panel.",
      },
    },
  },

  /* R1 — delegate_to_agent retired. Investigation, action synthesis,
   * and verdict classification now run on the same investigator
   * thread, mirroring the live GridManager flow. The dispatcher tab
   * is no longer registered in bootstrap; the f023/f024 delegation
   * frames were removed. The unified action-synthesis frames
   * continue in 05_delegate.ts (kept its original name to avoid
   * needless churn). */
];
