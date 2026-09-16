/**
 * Phase 5 — Dispatcher chat frames.
 *
 * Module role:
 *   The Dispatcher receives the delegation, runs its own tool sequence
 *   (search_paws → search_nearhit_reports → search_station_contacts ×3
 *   → search_participants), then streams a structured analysis with
 *   explicit confirmed-vs-clue separation, then pushes priority actions
 *   via push_action tool calls.
 *
 *   Tool names mirror the production agent_config.yaml dispatcher
 *   entry. Result shapes match the registered renderers.
 *
 * Cell collaborators:
 *   - phases/04_investigate.ts — delegate_to_agent fires at the end of
 *     phase 4. We pick up here by switching to the dispatcher tab and
 *     appending the delegation as a user message on its thread.
 *   - phases/06_actions.ts — separately dumps the panel.priority_action.append
 *     ops that populate the Operator Priorities panel. The push_action
 *     tool calls in this file are the chat-side audit trail; the panel
 *     ops in phase 6 are what the operator sees in the panel.
 *
 * Runtime: ~50 seconds across 25 frames.
 */

import type { Frame } from "../../../scenarioSchema";

/* ─── OPNET procedure search result. Full text excerpts mimic the real
 *     blob storage URLs the production agent returns. */
const OPNET_RESULT = JSON.stringify({
  results: [
    {
      title:
        "OP-NET-5520 — Regional Power System Operating Procedure (EHR region)",
      source:
        "https://stj5ftgzvnctax.blob.core.windows.net/docs/OPNET/OP-NET-5520%20-%20Regional%20Power%20System%20Operating%20Procedure%20-%20SER.pdf",
      score: 0.94,
      text:
        "12. Bus zone protection. The following EHR substations have duplicate bus zone protection: " +
        "MARRABEL 275 kV (Schemes A and B since 2021), KETTERING 275 kV, GLENRIDGE 275 kV (since 2024 " +
        "post-event upgrade), BIRRALEE 275 kV. OP-NET-3715 details the process to be followed when " +
        "no protection is available on a network element. EHRT will advise on alternative arrangements " +
        "when a bus zone protection is required out of service.\n\n" +
        "13. Auto reclose for line faults. All EHR 275 kV transmission lines are provided with " +
        "single phase auto reclose (SPAR) only. A phase-to-phase or earth fault on a 275 kV line " +
        "results in a lock-out. Bus section isolators are NOT subject to auto reclose under any " +
        "scheme — manual close authorised only after insulation resistance testing.\n\n" +
        "14. Contingency event classification (Operating Code §4.7.2). Loss of two or more generating units " +
        "from a single network event is classified as a non-credible contingency. Reclassification " +
        "assessment under Operating Code §4.3.1A(c) must be issued within 30 minutes of event detection.",
    },
    {
      title:
        "OP-NET-3120 — 275 kV Busbar Restoration After Protection Trip",
      source:
        "https://stj5ftgzvnctax.blob.core.windows.net/docs/OPNET/OP-NET-3120%20-%20Busbar%20Restoration.pdf",
      score: 0.91,
      text:
        "Following a busbar protection operation: (a) confirm the busbar is earthed and isolated; " +
        "(b) conduct visual inspection of all bus section equipment, with priority to bus section " +
        "isolators; (c) request insulation resistance testing on each bus section; (d) if a faulty " +
        "bus section isolator is identified, the busbar may be re-energised with the faulty section " +
        "bypassed, subject to network security assessment by Eastlink Operator. Re-energisation without " +
        "RTO confirmation of physical bus state is prohibited under any circumstance.",
    },
    {
      title:
        "OP-NET-4410 — Generator Resynchronisation After Forced Outage",
      source:
        "https://stj5ftgzvnctax.blob.core.windows.net/docs/OPNET/OP-NET-4410%20-%20Generator%20Resync.pdf",
      score: 0.87,
      text:
        "After a forced trip, confirm all protection has reset. Check AVR, governor, and excitation " +
        "system health. For units tripped by reverse-power or under-frequency protection (system " +
        "condition trips, not internal fault), resynchronisation may proceed once the network fault " +
        "is cleared. For units tripped by differential or overcurrent protection, an insulation " +
        "resistance test of the generator winding is required before restart. Ramp to target output " +
        "over 15 minutes minimum.",
    },
    {
      title:
        "OP-NET-2210 — Market Notice for Non-Credible Contingency Events",
      source:
        "https://stj5ftgzvnctax.blob.core.windows.net/docs/OPNET/OP-NET-2210%20-%20Market%20Notice.pdf",
      score: 0.83,
      text:
        "A market notice for a non-credible contingency event must be issued within 30 minutes of " +
        "the event under Operating Code §4.7.2(b). The notice must include: station, generation lost (MW), " +
        "frequency excursion, identified cause (or 'cause under investigation'), and reclassification " +
        "assessment under Operating Code §4.3.1A(c). Reclassification to 'credible' is required if the recurrence " +
        "of the event is reasonably possible — i.e. the cause cannot be remedied before re-energisation.",
    },
  ],
  count: 4,
});

/* ─── Near-hit report search result. Strong match against GLENRIDGE 2022
 *     — same fault mechanism, same equipment class. */
const NEARHIT_RESULT = JSON.stringify({
  results: [
    {
      title:
        "GLENRIDGE_NX 275 kV Bus 275-1 trip — 08 October 2022 (post-event review)",
      source: "NEARHIT-2022-GLENRIDGE-1-BUS",
      score: 0.96,
      text:
        "Inter-phase flashover on bus section isolator DS-275-12 caused tripping of 275 kV Bus 275-1. " +
        "Two units (188 MW and 152 MW) disconnected from the Bus 275-1. Mechanism: insulation " +
        "degradation on the open red-phase contact of DS-275-12, traced to silver-plating wear at the " +
        "contact interface — a known failure mode for the same isolator type installed at MARRABEL, " +
        "KETTERING, and GLENRIDGE. Lessons: (1) accelerate the bus section isolator inspection " +
        "programme; (2) integrate sub-threshold voltage transient detection into the situations " +
        "scanner; (3) replace DS-275-11 through DS-275-14 at affected stations during next outage. " +
        "Recovery: Bus 275-1 re-energised with DS-275-12 bypassed in 4h 20m. Units returned to service " +
        "within 6h. CBF protection cleared the fault in 412 ms.",
    },
    {
      title:
        "BIRRALEE_NX 275 kV bus zone trip — 4 May 2021 (near-hit)",
      source: "NEARHIT-2021-BIRRALEE",
      score: 0.74,
      text:
        "Bus zone protection operated correctly for a phase-to-earth fault on a connected feeder. " +
        "Delayed CB indication (~3 minutes) via RTU gateway momentarily confused the timeline. " +
        "Lessons: confirm RTU buffering health during post-event review; bus alarm timestamps are " +
        "authoritative — CB timestamps may lag.",
    },
  ],
  count: 2,
});

/* ─── Station contact search results. SearchResultCards renders these
 *     as cards; each entry surfaces a contact name, role, and how to
 *     reach them. Three calls because three stations are in scope. */
const CONTACTS_MARRABEL = JSON.stringify({
  results: [
    {
      title: "MARRABEL_NX Station Manager",
      source: "CONTACT-MARRABEL-MGR",
      score: 1.0,
      text:
        "Name: Tom Brennan. Role: Station Manager (24/7 on-call). Phone: +61 8 5500 1100. " +
        "Mobile: +61 4 8100 2255. Teams channel: marrabel-station-ops. Authority: switching, " +
        "isolation, restoration coordination on station bus.",
    },
    {
      title: "MARRABEL_NX Generation Controller",
      source: "CONTACT-MARRABEL-GEN",
      score: 0.98,
      text:
        "Name: Linh Park. Role: Unit Controller — Units 1–4. Phone: +61 8 5500 1101. Authority: " +
        "unit start/stop, AVR/governor configuration, resynchronisation. Subscribes to all " +
        "MARRABEL SCADA alarms.",
    },
    {
      title: "MARRABEL_NX Protection Engineer (RTO duty)",
      source: "CONTACT-MARRABEL-PROT",
      score: 0.95,
      text:
        "Name: EHRT Protection Duty Engineer (rotating roster). Phone: +61 8 0000 9120 (24/7 " +
        "duty line). Authority: retrieve relay event records, disturbance recorder downloads, " +
        "fault analysis, CBF assessment.",
    },
  ],
  count: 3,
});

const CONTACTS_KETTERING = JSON.stringify({
  results: [
    {
      title: "KETTERING_NX Control Room",
      source: "CONTACT-KETTERING-CTL",
      score: 0.99,
      text:
        "Name: EHRT KETTERING Operations. Phone: +61 8 5500 2200 (24/7). Authority: monitor and " +
        "control KETTERING_NX bus configuration, manage MARRABEL–KETTERING No. 1 line loading, " +
        "request runback or generation reduction if thermal limits approached.",
    },
  ],
  count: 1,
});

const CONTACTS_SCADA = JSON.stringify({
  results: [
    {
      title: "EHRT SCADA / RTU Comms Support",
      source: "CONTACT-SCADA-SUPPORT",
      score: 0.97,
      text:
        "Name: EHRT SCADA Duty Tech. Phone: +61 8 0000 9170. Authority: RTU gateway diagnostics, " +
        "ICCP/telemetry buffering checks, alarm latency investigation. Required for any timeline " +
        "annotation involving suspected delayed indications.",
    },
  ],
  count: 1,
});

/* ─── push_action tool result — confirms the action was pushed to the
 *     panel. PanelToolSummary renders this as a compact green badge. */
const pushActionResult = (step: number, summary: string): string =>
  JSON.stringify({
    panel: "priority_actions",
    step,
    pushed_at: new Date().toISOString(),
    summary,
  });

export const delegateFrames: Frame[] = [
  /* R1 — delegation retired. The frames below used to run on the
   * `dispatcher` thread after an `agent.set_active` tab switch and a
   * forwarded-task user message. Both have been removed: the entire
   * action-synthesis sequence now lives on the same `investigator`
   * thread as the investigation, mirroring the live single-agent
   * GridManager flow per MODERNIZATION.md §1.R1. */

  /* f101 (formerly the dispatcher hand-off user message) — retained
   * as an investigator-thread continuation note so the audience sees
   * the agent visibly framing the action-synthesis pivot. */
  {
    id: "f101",
    chapter: "Action synthesis",
    narration:
      "Same thread. The agent pivots from investigation to action synthesis.",
    annotation: {
      target: "panel-chat",
      caption:
        "Single thread. Investigation evidence is summarised, then the agent moves into procedure search and operator-action push — no tab switch.",
      placement: "left",
    },
    transition_ms: 1200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text:
          "**Pivoting to action synthesis on the same thread.**\n\n" +
          "**Confirmed evidence:**\n" +
          "- Initiating event 11:15:14: bus differential operated, DS-275-13 earth fault.\n" +
          "- 412 MW lost (Unit 3 = 235 MW, Unit 4 = 177 MW). Unit 1 stable on Bus 275-2.\n" +
          "- Bus 275-1 de-energised (275.5 → 0.0 kV at 11:15:30).\n" +
          "- EHR frequency nadir 49.71 Hz at 11:16:04, recovered within 100 s.\n" +
          "- KETTERING interconnector surge 320 → 710 MW (89 % rated).\n" +
          "- Unit 1 confirmed on Bus 275-2 via CIM topology.\n\n" +
          "**Clue-based likely mechanism (NOT confirmed):**\n" +
          "- GLENRIDGE_NX October 2022 historical match (0.94 similarity): inter-phase flashover on " +
          "DS-275-12 open red-phase contact. Same equipment class.\n" +
          "- Internal review (CLUE-INSULATION-DEGRADATION): consistent transient-dip precursor " +
          "across 14 EHR bus section isolator failures (2018–2022).\n\n" +
          "**Responsible parties:** EHRT (RTO) + Marrabel Power Holdings.\n\n" +
          "Searching OPNET procedures and near-hit reports now — every pushed action will cite " +
          "the source it came from and explicitly tag confirmed-evidence vs clue-based mechanism.",
      },
    },
  },

  /* f102 — search_paws call. */
  {
    id: "f102",
    narration:
      "Procedure before action. The library returns four procedures, including busbar restoration.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-paws",
            name: "search_paws",
            arguments: {
              query:
                "MARRABEL 275 kV busbar trip operator procedure busbar restoration generator " +
                "resynchronisation market notice non-credible contingency reclassification " +
                "Operating Code §4.7.2 Operating Code §4.3.1A insulation resistance test bus section isolator",
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f103 — OPNET result. Four procedures, each with a real-looking blob URL. */
  {
    id: "f103",
    narration:
      "Four procedures back, including the busbar restoration step-by-step.",
    transition_ms: 2000,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-paws",
        status: "complete",
        duration_ms: 1100,
        result: OPNET_RESULT,
      },
    },
  },

  /* f104 — search_nearhit_reports call. */
  {
    id: "f104",
    narration:
      "Now the formal post-event review for the same failure mode.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-nearhit",
            name: "search_nearhit_reports",
            arguments: {
              query:
                "275 kV bus section isolator inter-phase flashover busbar trip insulation " +
                "degradation precursor transient dip remediation",
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f105 — nearhit result. */
  {
    id: "f105",
    narration:
      "GLENRIDGE again. The logged lesson: accelerate the inspection programme.",
    transition_ms: 1700,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-nearhit",
        status: "complete",
        duration_ms: 800,
        result: NEARHIT_RESULT,
      },
    },
  },

  /* f106 — search_station_contacts (MARRABEL). */
  {
    id: "f106",
    narration:
      "The responsible control room and SCADA comms support contact are identified.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-contacts-rc",
            name: "search_station_contacts",
            arguments: {
              station: "MARRABEL_NX",
              roles: ["station_manager", "generation_controller", "protection_engineer"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f107",
    transition_ms: 1300,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-contacts-rc",
        status: "complete",
        duration_ms: 500,
        result: CONTACTS_MARRABEL,
      },
    },
  },

  /* f108 — search_station_contacts (KETTERING). */
  {
    id: "f108",
    narration:
      "KETTERING next: the interconnector running at 89% rating.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-contacts-nv",
            name: "search_station_contacts",
            arguments: {
              station: "KETTERING_NX",
              roles: ["control_room"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f109",
    transition_ms: 1100,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-contacts-nv",
        status: "complete",
        duration_ms: 400,
        result: CONTACTS_KETTERING,
      },
    },
  },

  /* f110 — search_station_contacts (SCADA support). */
  {
    id: "f110",
    narration:
      "And SCADA comms support, for the breaker indication check.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-contacts-sc",
            name: "search_station_contacts",
            arguments: {
              role: "scada_comms_support",
              region: "EHR",
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f111",
    transition_ms: 1100,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-contacts-sc",
        status: "complete",
        duration_ms: 400,
        result: CONTACTS_SCADA,
      },
    },
  },

  /* f112 — Dispatcher streams its synthesis preface. The actual action
   * cards drop into the panel via phase 6's panel.priority_action.append
   * ops; the chat thread shows the audit trail of push_action tool
   * calls plus this prose summary. */
  {
    id: "f112",
    chapter: "Operator actions",
    narration:
      "Two actions are pushed. Both cards land directly on the operator's panel.",
    annotation: {
      target: "panel-center",
      caption:
        "Centre column shows the Priority Actions panel. Each push_action tool call from the Dispatcher lands here as a numbered card with rationale, guide, and contacts.",
      placement: "left",
    },
    transition_ms: 90,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
      },
    },
  },
  {
    id: "f113",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "## Key distinction applied\n\n" +
          "- **Confirmed from evidence:** MARRABEL_NX 275 kV Bus 275-1 de-energised at 11:15:30, " +
          "Units 3 and 4 disconnected (412 MW), Unit 1 stable on Bus 275-2, frequency nadir 49.71 Hz, " +
          "KETTERING interconnector at 89 % rating.\n" +
          "- **Not confirmed, clue-based only:** likely mechanism (DS-275-13 inter-phase flashover) " +
          "is supported by the 0.94 GLENRIDGE 2022 match and the internal isolator-failure review " +
          "but is **not proven** until physical inspection and insulation-resistance testing " +
          "complete. Used here only to shape the priority and sequence of follow-up checks.\n\n",
      },
    },
  },
  {
    id: "f114",
    transition_ms: 80,
    patch: {
      "chat.append_token": {
        agent: "investigator",
        text:
          "## Action plan\n\n" +
          "Five prioritised actions follow. Each cites the procedure (OPNET), the responsible " +
          "party, and the rationale separately for confirmed evidence and clue-based mechanism.\n\n",
      },
    },
  },

  /* f115–f119 — Five push_action tool calls. The actual panel cards
   * appear in phase 6 via panel.priority_action.append. The push_action
   * calls here render the chat-side audit badge. */
  {
    id: "f115",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-push-1",
            name: "push_action",
            arguments: {
              step: 1,
              priority: 5,
              action:
                "Confirm MARRABEL_NX 275 kV Bus 275-1 is de-energised, isolated, and locked out " +
                "from re-energisation pending physical inspection",
              contacts: ["MARRABEL Station Manager", "EHRT Regional Control"],
              sources: ["OP-NET-3120", "OP-NET-5520 §12"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f116",
    transition_ms: 600,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-push-1",
        status: "complete",
        duration_ms: 300,
        result: pushActionResult(1, "Confirm Bus 275-1 isolation — MARRABEL Station Manager"),
      },
    },
  },
  {
    id: "f117",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-push-2",
            name: "push_action",
            arguments: {
              step: 2,
              priority: 4,
              action:
                "Request EHRT Protection retrieve and analyse MARRABEL 275 kV Bus 275-1, CB-031, " +
                "CB-041, and DS-275-13 fault and disturbance records",
              contacts: ["EHRT Protection Duty Engineer"],
              sources: ["OP-NET-5520 §12", "NEARHIT-2022-GLENRIDGE-1-BUS"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f118",
    transition_ms: 600,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-push-2",
        status: "complete",
        duration_ms: 300,
        result: pushActionResult(2, "Retrieve protection records — EHRT Protection"),
      },
    },
  },
  {
    id: "f119",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-push-3",
            name: "push_action",
            arguments: {
              step: 3,
              priority: 4,
              action:
                "Monitor KETTERING–MARRABEL No. 1 interconnector loading; arrange runback if " +
                "thermal headroom further degrades",
              contacts: ["KETTERING Control Room"],
              sources: ["OP-NET-5520 §13", "scada change row 6"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f120",
    transition_ms: 600,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-push-3",
        status: "complete",
        duration_ms: 300,
        result: pushActionResult(3, "Monitor KETTERING 89 % loading — KETTERING Control Room"),
      },
    },
  },
  {
    id: "f121",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-push-4",
            name: "push_action",
            arguments: {
              step: 4,
              priority: 3,
              action:
                "Prepare Unit 4 for resynchronisation to Bus 275-2; defer Unit 3 restart pending " +
                "insulation resistance test (reverse-power trip)",
              contacts: ["MARRABEL Generation Controller"],
              sources: ["OP-NET-4410"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f122",
    transition_ms: 600,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-push-4",
        status: "complete",
        duration_ms: 300,
        result: pushActionResult(4, "Prepare Unit 4 resync — MARRABEL Generation Controller"),
      },
    },
  },
  {
    id: "f123",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "GridManager",
        text: "",
        tool_calls: [
          {
            id: "tc-push-5",
            name: "push_action",
            arguments: {
              step: 5,
              priority: 3,
              action:
                "Issue market notice for non-credible contingency event by 11:45 AEST; include " +
                "reclassification assessment under Operating Code §4.3.1A(c)",
              contacts: ["Eastlink Market Operator"],
              sources: ["OP-NET-2210", "Operating Code §4.7.2(b)"],
            },
            status: "running",
          },
        ],
      },
    },
  },
  {
    id: "f124",
    transition_ms: 1500,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-push-5",
        status: "complete",
        duration_ms: 300,
        result: pushActionResult(5, "Market notice deadline 11:45 — Eastlink Market Operator"),
      },
    },
  },
];
