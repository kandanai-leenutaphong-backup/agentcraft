/**
 * Phase 6 — Priority action cards.
 *
 * Module role:
 *   Five panel.priority_action.append ops drop the actions onto the
 *   Operator Priorities panel. Each card mirrors a push_action tool
 *   call from phase 5 — same step, same priority, same headline action
 *   — and adds the full reasoning block with explicit confirmed-vs-clue
 *   separation, the step-by-step guide, the cited sources, and the
 *   named contacts.
 *
 *   The chat-side push_action tool calls (phase 5) are the audit
 *   trail; these panel ops are what the operator actually reads in
 *   the right-hand column.
 *
 * Cell collaborators:
 *   - phases/05_delegate.ts — the dispatcher chat-thread audit trail.
 *   - components/panels/PriorityActionsPanel.tsx — renders the cards.
 *
 * Runtime: ~10 seconds.
 */

import type { Frame } from "../../../scenarioSchema";

export const actionFrames: Frame[] = [
  /* f200 — Action 1 (P5 critical): confirm Bus 275-1 isolation. */
  {
    id: "f200",
    transition_ms: 700,
    patch: {
      "panel.priority_action.append": {
        action:
          "Confirm MARRABEL_NX 275 kV Bus 275-1 is de-energised, isolated, and locked out from " +
          "re-energisation pending physical inspection",
        reasoning:
          "**Confirmed evidence**\n" +
          "- Bus differential protection operated at 11:15:14 AEST (event timeline row 3).\n" +
          "- Bus 275-1 voltage collapsed 275.5 → 0.0 kV at 11:15:30 (SCADA changes row 3).\n" +
          "- Bus 275-1 has remained de-energised in subsequent SCADA polls — no evidence of immediate " +
          "restoration.\n\n" +
          "**Why this action is needed**\n" +
          "- OPNET OP-NET-3120 mandates that re-energisation of a busbar after protection operation " +
          "requires confirmation of physical bus state by the RTO. Re-energisation without RTO " +
          "confirmation is prohibited.\n" +
          "- Until a physical inspection of DS-275-13 is completed, the cause of the earth fault " +
          "remains unverified — re-energising Bus 275-1 risks repeating the fault.\n\n" +
          "**What is not yet proven (clue-based mechanism)**\n" +
          "- The likely mechanism is inter-phase flashover on DS-275-13 open red-phase contact (GLENRIDGE " +
          "2024 match, 0.94 similarity). This is corroborative only — the earth fault alarm proves " +
          "a fault, not its physical mechanism. Inspection is required to confirm.",
        guide:
          "1. Contact MARRABEL Station Manager (Tom Brennan, +61 8 5500 1100). Confirm 275 kV Bus 275-1 " +
          "is earthed and all associated CBs (CB-031, CB-041, CB-021, CB-051) are locked open.\n" +
          "2. Contact EHRT Regional Control (+61 8 0000 9000) and confirm no switching, " +
          "auto-isolation, or field actions have been initiated since 11:15 without your knowledge.\n" +
          "3. Issue formal hold-off: no re-energisation of Bus 275-1 until protection assessment and " +
          "physical inspection of DS-275-11 through DS-275-14 are complete.\n" +
          "4. Record the confirmed network configuration in the incident log.\n" +
          "5. If MARRABEL Station Manager advises any mismatch between field state and SCADA, " +
          "treat SCADA indications as potentially incomplete and request immediate reconciliation.",
        priority: 5,
        contacts: [
          { name: "Tom Brennan", role: "MARRABEL Station Manager", phone: "+61 8 5500 1100", teams: "marrabel-station-ops" },
          { name: "EHRT Regional Control", role: "Duty Operator", phone: "+61 8 0000 9000", teams: "ehrt-regional-control" },
        ],
        sources: ["OP-NET-3120", "OP-NET-5520 §12", "event_timeline row 3"],
      },
    },
  },

  /* f201 — Action 2 (P4 urgent): retrieve protection records. */
  {
    id: "f201",
    transition_ms: 700,
    patch: {
      "panel.priority_action.append": {
        action:
          "Request EHRT Protection retrieve and analyse MARRABEL 275 kV Bus 275-1, CB-031, CB-041, " +
          "and DS-275-13 fault and disturbance records for 11:15 AEST event",
        reasoning:
          "**Confirmed evidence**\n" +
          "- Bus differential protection (Scheme A) operated correctly at 11:15:14.\n" +
          "- DS-275-13 earth fault alarm fired in the same second.\n" +
          "- CB-031 and CB-041 opened within ~16 ms of the differential pickup.\n\n" +
          "**Why this action is needed**\n" +
          "- OPNET OP-NET-5520 §12 notes MARRABEL 275 kV has duplicate bus zone protection " +
          "(Schemes A and B since 2021). Protection records, disturbance records, station SER, " +
          "and relay targets are the authoritative means to confirm which scheme operated, the " +
          "fault clearance time, and whether CBF was involved.\n" +
          "- The GLENRIDGE 2022 near-hit (NEARHIT-2022-GLENRIDGE-1-BUS) cleared a comparable fault in " +
          "412 ms via CBF; comparing MARRABEL's clearance time to that benchmark will indicate " +
          "whether protection performance was nominal.\n\n" +
          "**Clue-based likely mechanism**\n" +
          "- The GLENRIDGE 2022 match suggests insulation degradation on DS-275-13's open red-phase " +
          "contact (silver-plating wear, known failure mode for this isolator type). This is " +
          "plausible but **must not** be treated as proven until the protection records and " +
          "physical inspection corroborate.",
        guide:
          "1. Contact EHRT Protection Duty Engineer (+61 8 0000 9120, 24/7 line).\n" +
          "2. Request immediate retrieval of:\n" +
          "   - Bus differential Scheme A and Scheme B event records.\n" +
          "   - CB-031 and CB-041 protection/event records.\n" +
          "   - DS-275-13 earth fault alarm trace and any associated disturbance recorder file.\n" +
          "   - Breaker failure (CBF) records.\n" +
          "   - Station SER/SOE files for 11:14–11:17 AEST.\n" +
          "3. Ask for confirmation of: first protection element to pick up, whether bus zone " +
          "protection operated, fault clearance time, trip fan-out.\n" +
          "4. Request verbal preliminary findings to control room within 60 minutes; formal records " +
          "to follow.\n" +
          "5. Log all requested files and expected delivery times in the incident record.",
        priority: 4,
        contacts: [
          { name: "EHRT Protection Duty Engineer", role: "Protection Engineer", phone: "+61 8 0000 9120", teams: "ehrt-protection" },
        ],
        sources: ["OP-NET-5520 §12", "NEARHIT-2022-GLENRIDGE-1-BUS"],
      },
    },
  },

  /* f202 — Action 3 (P4 urgent): KETTERING interconnector loading. */
  {
    id: "f202",
    transition_ms: 700,
    patch: {
      "panel.priority_action.append": {
        action:
          "Monitor KETTERING–MARRABEL No. 1 interconnector loading; arrange runback or generation " +
          "reduction if thermal headroom further degrades",
        reasoning:
          "**Confirmed evidence**\n" +
          "- KETTERING_NX::L:MRB-01::pwr_real surged from 320 → 710 MW (+121.9 %) at 11:15:30, " +
          "reaching 89 % of normal rating (SCADA changes row 6).\n" +
          "- OAKBANK_NX::L:MRB-02::pwr_real surged from 145 → 318 MW in the same second (row 7).\n" +
          "- These are the network's automatic response to the 412 MW MARRABEL generation loss.\n\n" +
          "**Why this action is needed**\n" +
          "- OPNET OP-NET-5520 §13 requires the EHR region to maintain N-1 secure post-contingent. " +
          "At 89 % rating, KETTERING No. 1 has limited headroom for an additional credible " +
          "contingency.\n" +
          "- The procedure indicates that if only generation reduction can relieve loading, EHRT " +
          "advises Eastlink / generator operators to reduce output as required.\n\n" +
          "**What is not yet known**\n" +
          "- Whether emergency rating (typically ~120 % of normal) was approached.\n" +
          "- Whether further redispatch will return loading to a secure margin within the " +
          "subsequent 30 minutes.",
        guide:
          "1. Contact KETTERING Control Room (+61 8 5500 2200). Confirm current real-time loading " +
          "on MARRABEL No. 1 and No. 2 lines.\n" +
          "2. Request current normal and emergency ratings; confirm the 89 % figure.\n" +
          "3. If loading exceeds 95 %, request immediate runback or arrange generation reduction " +
          "with EHRT and the affected generator.\n" +
          "4. Continue monitoring at 5-minute intervals until loading is restored to a secure " +
          "margin (target < 80 % of normal).\n" +
          "5. Coordinate with Eastlink dispatch to ensure adequate inter-regional headroom for the " +
          "next credible contingency.",
        priority: 4,
        contacts: [
          { name: "EHRT KETTERING Operations", role: "Control Room", phone: "+61 8 5500 2200", teams: "ehrt-kettering" },
        ],
        sources: ["OP-NET-5520 §13", "scada_changes row 6"],
      },
    },
  },

  /* f203 — Action 4 (P3 standard): Unit 4 resync. */
  {
    id: "f203",
    transition_ms: 700,
    patch: {
      "panel.priority_action.append": {
        action:
          "Prepare Unit 4 for resynchronisation to Bus 275-2; defer Unit 3 restart pending insulation " +
          "resistance test",
        reasoning:
          "**Confirmed evidence**\n" +
          "- Unit 4 tripped on under-frequency protection at 11:15:22 (49.71 Hz) — a system-condition " +
          "trip, not an internal fault.\n" +
          "- Unit 3 tripped on reverse-power protection at 11:15:18 — this may indicate backfeed " +
          "through the generator transformer during the bus collapse, which is a candidate marker " +
          "for stator winding stress.\n" +
          "- Bus 275-2 is intact; Unit 1 is generating 248 MW stably on Bus 275-2 (CIM topology " +
          "confirmed).\n\n" +
          "**Why this action is needed**\n" +
          "- OPNET OP-NET-4410 distinguishes system-condition trips (under-frequency, reverse-power " +
          "from network) from internal-fault trips (differential, overcurrent). Under-frequency = " +
          "safe to resynchronise once the network fault is cleared.\n" +
          "- Reverse-power may be a system condition or internal fault — an insulation resistance " +
          "test is the documented gate before restart.\n\n" +
          "**Clue-based mechanism**\n" +
          "- GLENRIDGE 2022 also tripped two units; both were system-condition trips and resynchronised " +
          "within 6 hours. This is precedent, not proof.",
        guide:
          "1. Contact MARRABEL Generation Controller (Linh Park, +61 8 5500 1101).\n" +
          "2. Confirm Unit 4 protection has reset — check reverse-power, under-frequency, and " +
          "differential relays.\n" +
          "3. Verify AVR and governor health on Unit 4.\n" +
          "4. Synchronise Unit 4 via CB-042 to 275 kV Bus 275-2 once EHRT confirms Bus 275-1 is isolated " +
          "and Bus 275-2 is secure.\n" +
          "5. Ramp to 180 MW over 15 minutes per OP-NET-4410.\n" +
          "6. Unit 3 restart: defer until insulation resistance test confirms no winding damage. " +
          "Schedule the test within 4 hours.",
        priority: 3,
        contacts: [
          { name: "Linh Park", role: "MARRABEL Generation Controller", phone: "+61 8 5500 1101", teams: "marrabel-generation" },
        ],
        sources: ["OP-NET-4410", "event_timeline rows 6, 10"],
      },
    },
  },

  /* f204 — Action 5 (P3 standard): market notice. */
  {
    id: "f204",
    transition_ms: 1200,
    patch: {
      "panel.priority_action.append": {
        action:
          "Issue market notice for non-credible contingency event by 11:45 AEST; include " +
          "reclassification assessment under Operating Code §4.3.1A(c)",
        reasoning:
          "**Confirmed evidence**\n" +
          "- Two generating units (Units 3 and 4) disconnected from a single network event at " +
          "MARRABEL_NX 275 kV Bus 275-1 at 11:15:14 AEST. Total: 412 MW.\n" +
          "- This satisfies the Operating Code §4.7.2(a)(1)(i) definition of a non-credible contingency event.\n\n" +
          "**Why this action is needed**\n" +
          "- OPNET OP-NET-2210 mandates issue within 30 minutes of event detection — deadline " +
          "**11:45 AEST**.\n" +
          "- The reclassification assessment under Operating Code §4.3.1A(c) determines whether the event " +
          "should be treated as 'credible' for forward dispatch — i.e. whether recurrence is " +
          "reasonably possible.\n\n" +
          "**Reclassification recommendation**\n" +
          "- Recommend NOT reclassified as credible: faulty bus section isolator identified " +
          "(DS-275-13) and will be bypassed/replaced before Bus 275-1 re-energisation. Recurrence is " +
          "not reasonably possible while DS-275-13 remains isolated.\n" +
          "- If physical inspection reveals damage to multiple isolators, reassess.",
        guide:
          "1. Draft market notice covering: MARRABEL_NX, 412 MW lost (Units 3 and 4), frequency " +
          "nadir 49.71 Hz in EHR, identified cause = inter-phase flashover on DS-275-13 (subject to " +
          "physical confirmation), reclassification under Operating Code §4.3.1A(c) = NOT credible.\n" +
          "2. Cite NEARHIT-2022-GLENRIDGE-1-BUS as comparable precedent in the cause section.\n" +
          "3. Submit via Eastlink market systems before 11:45 AEST.\n" +
          "4. If physical inspection later contradicts the identified cause, issue an updated " +
          "notice within 30 minutes of revised assessment.",
        priority: 3,
        contacts: [
          { name: "Eastlink Market Operator", role: "Market Notice Recipient", phone: "+61 8 0000 0100", teams: "eastlink-market-ops" },
        ],
        sources: ["OP-NET-2210", "Operating Code §4.7.2(b)", "Operating Code §4.3.1A(c)"],
      },
    },
  },
];
