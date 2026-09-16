/**
 * Kiosk bootstrap configuration for the NGM busbar trip demo scenario.
 *
 * Module role:
 *   Exports the kiosk_bootstrap subtree: agent roster, dock agent with
 *   canned replies, and pre-seeded classifications. Consumed by the
 *   scenario index.ts and ultimately by kioskBootstrap.ts on app mount.
 *
 * Key collaborators:
 *   - index.ts — merges this into the Scenario object.
 *   - kioskBootstrap.ts — reads main_agents, dock_agents, classifications
 *     and seeds the respective Zustand stores.
 *
 * All content is fictional. No real power assets, market operators, or
 * regulatory references. See DEMO_SCENARIO_SPEC.md §8 for reply details.
 */

import type { KioskBootstrap } from "../../scenarioSchema";

/** Classification rationales keyed by situation_id. Each mirrors the
 *  GOR classification verdicts from the spec. The field name is
 *  ner_citation in the schema (historical naming) but the content
 *  references the fictional GOR rules. */
const CLASSIFICATIONS: KioskBootstrap["classifications"] = {
  "ngm-pre-1": {
    classification: "non_event",
    ner_citation: "Operating Code §4.7.2(a) — precursor advisory",
    rationale:
      "A 15-second voltage transient on the 275 kV Bus 275-1 (dip to 248.0 kV, 9.9% depression, recovered to nominal) does not meet the threshold for a reportable grid incident — no protection operated and no equipment was lost. However, the depth and shape of the transient are consistent with early-stage insulation breakdown on a connected primary plant element. GridIQ recommends an immediate thermal/insulation inspection of all bay equipment connected to the 275 kV Bus 275-1, prioritising bus section isolators. This is an early-warning advisory, not a contingency event.",
  },
  "ngm-crit-1": {
    classification: "non_credible",
    ner_citation: "Operating Code §4.3.1A(c)",
    rationale:
      "The simultaneous loss of two generating units connected to the same busbar section constitutes a non-credible contingency under the GOR, as credible contingency assessment considers the loss of a single generating unit or single network element. The busbar fault affected two independent units via shared protection, which exceeds the single-element boundary. The grid authority assessed reclassification under Operating Code §4.3.1A(c) and determined recurrence was not reasonably possible after the faulty isolator was identified and bypassed.",
  },
  "ngm-maj-1": {
    classification: "non_event",
    ner_citation: "Operating Code §4.7.2(a)(1)(i)",
    rationale:
      "The KETTERING interconnector loading surge is a consequential power system response to the MARRABEL_NX generation loss, not an independent contingency. No protection operated at KETTERING — the alarms are thermal loading advisories. The interconnector remained within its emergency rating. This does not meet the threshold for a reportable grid incident as no critical transmission element was lost or at risk of loss.",
  },
  "ngm-ser-1": {
    classification: "non_event",
    ner_citation: "Operating Code §4.7.2(a)",
    rationale:
      "GLENRIDGE_NX experienced automatic governor response to the NGM frequency excursion. Both units ramped from 165 MW to 178 MW (within rated capacity) as part of normal FRS fast-raise response. No protection operated. No equipment tripped. The SCADA step-changes reflect controlled frequency response, not a fault or contingency. Does not meet the definition of a reportable grid incident.",
  },
  "ngm-inv-1": {
    classification: "credible",
    ner_citation: "Operating Code §4.3.1(b)",
    rationale:
      "OAKBANK_NX 132/66 kV transformer T2 tripped on overcurrent protection following the redistribution of load after the MARRABEL_NX event. The loss of a single transformer constitutes a credible contingency under Operating Code §4.3.1(b). However, the trip occurred 8 minutes after the initiating event and was caused by load redistribution, not equipment failure. The transformer was tested and returned to service within 25 minutes. The grid authority determined the overcurrent condition was transient and not indicative of a persistent risk.",
  },
};

/* ── Dock agent canned replies ─────────────────────────────────────────── */

/** Reply 1 — match: redcliff — full event summary with alarm + SCADA tables. */
const REPLY_MARRABEL =
  `**MARRABEL_NX — event window 11:13–11:28 AEST**\n\n` +
  `**Alarm log** (6 alarms in 16 seconds):\n\n` +
  `| Time (AEST) | Equipment | Label | Description | Pri |\n` +
  `|-------------|-----------|-------|-------------|-----|\n` +
  `| 11:15:14 | MARRABEL_NX::CB-031 | [CB-OPN] CB transition | MARRABEL_NX 275 kV CB-031 TRIPPED | 1 |\n` +
  `| 11:15:14 | MARRABEL_NX::CB-041 | [CB-OPN] CB transition | MARRABEL_NX 275 kV CB-041 TRIPPED | 1 |\n` +
  `| 11:15:14 | MARRABEL_NX::B275-1 | BUS DIFF | MARRABEL_NX 275 kV A BUSBAR DIFFERENTIAL PROTECTION OPERATED | 1 |\n` +
  `| 11:15:14 | MARRABEL_NX::DS-275-13 | EARTH FLT | MARRABEL_NX BUS SECTION ISOLATOR DS-275-13 [ISOEF] ground fault | 1 |\n` +
  `| 11:15:18 | MARRABEL_NX::G3 | [PROTOP] | MARRABEL_NX GEN 3 [REVPWR] backfeed event | 1 |\n` +
  `| 11:15:22 | MARRABEL_NX::G4 | [PROTOP] | MARRABEL_NX GEN 4 [UFREQ] freq band exit | 1 |\n\n` +
  `**SCADA snapshot** (post-event):\n\n` +
  "```\n" +
  `TagId                         Value    Prev     Drop\n` +
  `MARRABEL_NX::G3::pwr_real           0.0   241.0   100.0%\n` +
  `MARRABEL_NX::G4::pwr_real           0.0   189.0   100.0%\n` +
  `MARRABEL_NX::G1::pwr_real         248.0   248.0   stable\n` +
  `MARRABEL_NX::G2::pwr_real       offline       –        –\n` +
  `MARRABEL_NX::B275-1::volt_kv    0.0   275.5   100.0%\n` +
  `MARRABEL_NX::B275-2::volt_kv  217.8   275.4     1.0%\n` +
  `MARRABEL_NX::TX-T1::pwr_real        248.0   539.4    54.0%\n` +
  "```\n\n" +
  `Total generation lost: **412 MW** (Units 3 + 4). Unit 1 stable on Bus 275-2.`;

/** Reply 2 — match: frequency — NGM frequency profile for EHR region. */
const REPLY_FREQUENCY =
  `**NGM frequency — EHR region, 11:13–11:23 AEST**\n\n` +
  `| Metric | Value |\n` +
  `|--------|-------|\n` +
  `| Pre-event frequency | 50.02 Hz |\n` +
  `| Nadir | 49.71 Hz |\n` +
  `| Time below SOFEB (49.75 Hz) | 3.8 s |\n` +
  `| Time below SOFB (49.85 Hz) | 8.2 s |\n` +
  `| Recovery to SOFB | ~100 s |\n` +
  `| Post-recovery frequency | 49.93 Hz |\n` +
  `| FRS contingency raise | 412 MW |\n` +
  `| GFS containment band | 47–52 Hz |\n` +
  `| **GFS met?** | **Yes** |\n\n` +
  `Adjacent regions:\n` +
  `- NER (North-East Region): 49.82 Hz min — no band breach\n` +
  `- WER (West Region): 49.85 Hz min — at SOFB boundary, no breach\n` +
  `- NOR (North Region): 49.88 Hz min — within SOFB\n\n` +
  `Frequency was restored by FRS contingency raise dispatched across the NGM within 6 seconds of the event.`;

/** Reply 3 — match: alarm — causal chain view of the alarm sequence. */
const REPLY_ALARM =
  `**Alarm sequence — MARRABEL_NX, 11:15:14 → 11:15:30 AEST**\n\n` +
  `6 alarms received in 16 seconds. Sequence:\n\n` +
  `1. **11:15:14** — \`[CB-OPN] CB transition\` — MARRABEL_NX 275 kV CB-031 TRIPPED (Pri 1)\n` +
  `2. **11:15:14** — \`[CB-OPN] CB transition\` — MARRABEL_NX 275 kV CB-041 TRIPPED (Pri 1)\n` +
  `3. **11:15:14** — \`BUS DIFF\` — MARRABEL_NX 275 kV A BUSBAR DIFFERENTIAL PROTECTION OPERATED (Pri 1)\n` +
  `4. **11:15:14** — \`EARTH FLT\` — MARRABEL_NX BUS SECTION ISOLATOR DS-275-13 [ISOEF] ground fault (Pri 1)\n` +
  `5. **11:15:18** — \`[PROTOP]\` — MARRABEL_NX GEN 3 [REVPWR] backfeed event (Pri 1)\n` +
  `6. **11:15:22** — \`[PROTOP]\` — MARRABEL_NX GEN 4 [UFREQ] freq band exit (Pri 1)\n\n` +
  `**Causal chain:** DS-275-13 inter-phase flashover → bus differential protection (Scheme A) → CB-031 + CB-041 open → GEN.3 reverse-power trip → GEN.4 under-frequency trip.\n\n` +
  `No protection mis-operation detected. All protection elements operated within design parameters.`;

/** Reply 4 — match: scada — SCADA snapshot table. */
const REPLY_SCADA =
  `**SCADA snapshot — MARRABEL_NX post-event**\n\n` +
  "```\n" +
  `TagId                          Value    Prev     Change\n` +
  `MARRABEL_NX::G3::pwr_real            0.0   241.0   -241.0 (100%) TRIP\n` +
  `MARRABEL_NX::G4::pwr_real            0.0   189.0   -189.0 (100%) TRIP\n` +
  `MARRABEL_NX::G1::pwr_real          248.0   248.0      0.0  (0%)  STABLE\n` +
  `MARRABEL_NX::G2::pwr_real        offline       –         –       MAINT\n` +
  `MARRABEL_NX::B275-1::volt_kv     0.0   275.5   -275.5 (100%) COLLAPSED\n` +
  `MARRABEL_NX::B275-2::volt_kv   217.8   275.4     -2.2  (1%)  STABLE\n` +
  `MARRABEL_NX::TX-T1::pwr_real          248.0   539.4   -291.4 (54%)  REDUCED\n` +
  `MARRABEL_NX::TX-T1::pwr_react         38.5    81.0    -42.5 (52%)  REDUCED\n` +
  "```\n\n" +
  `Notes:\n` +
  `- T1 load dropped from 539 MW to 248 MW — now carrying only Unit 1 output via Bus 275-2.\n` +
  `- Bus 275-2 voltage at 217.8 kV (99% of nominal) — healthy.\n` +
  `- Bus 275-1 collapsed to 0 kV — isolated by protection.`;

/** Reply 5 — match: northvale — interconnector response detail. */
const REPLY_KETTERING =
  `**KETTERING_NX — interconnector response**\n\n` +
  `**Line loading:**\n\n` +
  `| Metric | Pre-event | Post-event | Change |\n` +
  `|--------|-----------|------------|--------|\n` +
  `| LINE.MARRABEL_1.MW | 320 MW | 710 MW | +390 MW |\n` +
  `| LINE.MARRABEL_1 thermal loading | 52% | 89% | +37 pp |\n` +
  `| ::B275-1::volt_kv | 219.8 kV | 214.2 kV | -5.6 kV (2.5%) |\n\n` +
  `**Alarms:**\n` +
  `- 11:15:48 — \`[KV-LO]\` — [KV-LO] KETTERING_NX::B275-1 volt 214.2 kV (Pri 3)\n` +
  `- 11:18:00 — \`[THRM]\` — [THRM] KETTERING_NX::L:MRB-01 loading 89 pct rated (Pri 2)\n\n` +
  `No protection operated at KETTERING. The interconnector loading increase is a consequential response to the 412 MW generation loss at MARRABEL_NX. The line remains within its emergency thermal rating (100% = ~800 MW).\n\n` +
  `**Recommendation:** Monitor 5-minute trend. If loading exceeds 95%, initiate generation redispatch.`;

/** Reply 6 — match: history — protection event history for MARRABEL equipment. */
const REPLY_HISTORY =
  `**MARRABEL_NX — protection event history (12 months)**\n\n` +
  `**GEN.3 events:**\n\n` +
  `| Date | Time | Event | MW Impact |\n` +
  `|------|------|-------|-----------|\n` +
  `| 2026-02-12 | 11:15 | Reverse power protection — current event | -235 MW |\n` +
  `| 2024-12-14 | 03:18 | Excitation system fault — AVR runback | -80 MW |\n` +
  `| 2024-08-03 | 10:00 | Scheduled insulation resistance test — planned | 0 MW |\n\n` +
  `**GEN.4 events:**\n\n` +
  `| Date | Time | Event | MW Impact |\n` +
  `|------|------|-------|-----------|\n` +
  `| 2026-02-12 | 11:15 | Under-frequency protection — current event | -177 MW |\n` +
  `| 2024-11-20 | 16:45 | Governor instability — AGC removal | 0 MW |\n\n` +
  `**DS-275-13 events:**\n\n` +
  `| Date | Event |\n` +
  `|------|-------|\n` +
  `| 2026-02-12 | Inter-phase flashover — **first recorded failure since commissioning (2014)** |\n\n` +
  `No prior fault history on DS-275-13. OEM has been notified for root cause analysis of the insulation failure.`;

/** Reply 7 — match: wentworth — transformer T2 trip detail. */
const REPLY_OAKBANK =
  `**OAKBANK_NX — transformer T2 trip**\n\n` +
  `| Metric | Value |\n` +
  `|--------|-------|\n` +
  `| Equipment | 132/66 kV Transformer T2 |\n` +
  `| Rated capacity | 60 MVA |\n` +
  `| Pre-event loading | 38 MW (63% rated) |\n` +
  `| Post-redistribution load | 52.4 MW (87% rated) |\n` +
  `| Overcurrent pickup | 50 MW |\n` +
  `| Trip time | 11:23:12 AEST |\n` +
  `| Time after MARRABEL event | +8 minutes |\n` +
  `| Cause | Overcurrent (load redistribution) |\n` +
  `| Equipment fault? | No — tested OK |\n` +
  `| Return to service | 15:05 AEST (25 min outage) |\n` +
  `| Load lost | 12.4 MW (downstream 66 kV) |\n\n` +
  `**Alarms:**\n` +
  `- 11:23:12 — \`[PROTOP]\` — [OVRCUR] OAKBANK_NX::TX-T2 overcurrent op (Pri 1)\n` +
  `- 11:23:12 — \`[TX-OPN]\` — [TX-OPN] OAKBANK_NX::TX-T2 transition (132/66 kV) (Pri 1)\n\n` +
  `The overcurrent was caused by load redistribution following the MARRABEL_NX event, not by an equipment fault. T2 was tested and returned to service at 15:05.`;

/** Reply 8 — match: "" (fallback) — usage hints. */
const REPLY_FALLBACK =
  `I can pull alarms, SCADA snapshots, frequency summaries, or historical pattern data for any station in the EHR region. Try:\n\n` +
  `- *"Show MARRABEL alarms around 11:15"*\n` +
  `- *"What's the NGM frequency profile for EHR?"*\n` +
  `- *"KETTERING interconnector loading"*\n` +
  `- *"GEN.3 protection history"*\n` +
  `- *"OAKBANK transformer details"*\n` +
  `- *"SCADA snapshot for MARRABEL"*`;

/* ── Generic operational replies (not tied to the busbar trip) ─────────
   These exist so a viewer can poke at the data-search agent without
   knowing the scenario assets and still get plausible, GridIQ-flavoured
   responses. All values are synthetic. */

/** Reply 9 — match: "load profile" — 24-hour rolling demand profile. */
const REPLY_LOAD_PROFILE =
  `**Grid demand — last 24 hours (rolling)**\n\n` +
  `| Window (local) | Avg MW | Peak MW | Min MW |\n` +
  `|----------------|--------|---------|--------|\n` +
  `| 00:00 – 06:00 | 18,420 | 19,150 | 17,680 |\n` +
  `| 06:00 – 09:00 | 22,810 | 24,300 | 19,550 |\n` +
  `| 09:00 – 17:00 | 24,120 | 25,640 | 22,980 |\n` +
  `| 17:00 – 22:00 | 26,930 | **28,210** | 24,500 |\n` +
  `| 22:00 – 24:00 | 21,150 | 22,800 | 19,420 |\n\n` +
  `- **Daily peak:** 28,210 MW at 18:42 (evening ramp).\n` +
  `- **Daily minimum:** 17,680 MW at 04:18 (overnight trough).\n` +
  `- **Load factor:** 82.7%.\n\n` +
  `Forecast error vs actual: **+1.4%** (under-forecast).`;

/** Reply 10 — match: "by region" — generation-mix snapshot. */
const REPLY_GEN_BY_REGION =
  `**Generation by region — current dispatch**\n\n` +
  `| Region | Live MW | Capacity MW | Utilisation | Top fuel mix |\n` +
  `|--------|---------|-------------|-------------|--------------|\n` +
  `| EHR | 7,820 | 11,400 | 68.6% | Coal 54%, Gas 19%, Wind 18%, Hydro 9% |\n` +
  `| NER | 4,310 | 6,200 | 69.5% | Coal 61%, Gas 12%, Solar 17%, Wind 10% |\n` +
  `| WER | 5,140 | 7,650 | 67.2% | Gas 38%, Wind 31%, Coal 21%, Solar 10% |\n` +
  `| NOR | 3,290 | 4,850 | 67.8% | Hydro 47%, Wind 28%, Gas 18%, Solar 7% |\n` +
  `| **Total** | **20,560** | **30,100** | **68.3%** | – |\n\n` +
  `Net inter-regional flows: EHR → NER **+820 MW**, WER → EHR **+340 MW**, NOR → NER **+150 MW**.`;

/** Reply 11 — match: "capacity headroom" — reserve margin breakdown. */
const REPLY_CAPACITY =
  `**Capacity headroom — all regions, 5-minute snapshot**\n\n` +
  `| Region | Demand MW | Avail MW | Reserve MW | Reserve % |\n` +
  `|--------|-----------|----------|------------|-----------|\n` +
  `| EHR | 7,820 | 9,610 | 1,790 | 22.9% |\n` +
  `| NER | 4,310 | 5,440 | 1,130 | 26.2% |\n` +
  `| WER | 5,140 | 6,920 | 1,780 | 34.6% |\n` +
  `| NOR | 3,290 | 4,470 | 1,180 | 35.9% |\n\n` +
  `- **System-wide spinning reserve:** 5,880 MW (28.6% of demand).\n` +
  `- **FCAS contingency raise enabled:** 1,200 MW.\n` +
  `- **FCAS contingency lower enabled:** 950 MW.\n\n` +
  `Reserve is comfortably above the 8% statutory minimum. No reserve trader notices active.`;

/** Reply 12 — match: "equipment status" — fleet-wide availability. */
const REPLY_EQUIPMENT_STATUS =
  `**Equipment status — fleet overview (last sync 30 s ago)**\n\n` +
  `| Asset class | In service | Planned outage | Forced outage | Standby |\n` +
  `|-------------|-----------|----------------|---------------|---------|\n` +
  `| Generators (≥30 MW) | 142 | 9 | 3 | 6 |\n` +
  `| 275 kV transformers | 218 | 4 | 1 | – |\n` +
  `| 132 kV transformers | 391 | 7 | 2 | – |\n` +
  `| Transmission lines | 612 | 11 | 0 | – |\n` +
  `| HV reactive plant | 87 | 3 | 1 | 4 |\n\n` +
  `**Active forced outages:**\n` +
  `1. **HOLLINS_NX::G2** — boiler tube leak — ETR tomorrow 09:00.\n` +
  `2. **DAVENPORT_TX::T3** — gas-in-oil DGA flag — ETR Friday 14:00.\n` +
  `3. **WHITLEIGH_NX::G1** — turbine vibration — ETR pending OEM advice.\n\n` +
  `Total forced-outage MW: **480 MW** (1.6% of installed capacity).`;

/** Reply 13 — match: "open switching" — recent switching activity log. */
const REPLY_OPEN_SWITCHING =
  `**Open switching operations — last 60 minutes**\n\n` +
  `| Time | Asset | Operation | Reason | Authorised by |\n` +
  `|------|-------|-----------|--------|---------------|\n` +
  `| 11:48 | BRENTON_NX::CB-118 | Open | Bay isolation for line patrol | NCC-S |\n` +
  `| 11:32 | LITTLEMORE::DS-72 | Open | Earth switch closure prep | Field crew #41 |\n` +
  `| 11:14 | OAKBANK_NX::TX-T2 | Closed (return) | RTS after testing | NCC-S |\n` +
  `| 10:58 | EVERLEIGH::CB-204 | Open | Reactive plant SVC swap-in | NCC-N |\n` +
  `| 10:41 | MARRABEL_NX::CB-031 | Open | Protection trip — see incident | Auto |\n\n` +
  `**Pending switching schedules in next 60 min:** 3.\n` +
  `**Switching forms requiring NCC concurrence:** 1 (BRENTON line patrol return).`;

/* ── Assembled bootstrap object ────────────────────────────────────────── */

export const bootstrap: KioskBootstrap = {
  main_agents: [
    {
      // Single GridManager agent — mirrors live control/agent_config.yaml.
      // The legacy two-agent split (Investigator + Dispatcher) is retired:
      // investigation, action synthesis, and verdict classification all
      // run on the same thread. The `investigator` id is retained so
      // saved sessions + e2e selectors continue to resolve.
      id: "investigator",
      name: "GridManager",
      description:
        "Investigates alarms, telemetry, topology, then synthesises grounded operator actions and a verdict in one flow.",
      is_default: true,
    },
  ],
  dock_agents: [
    {
      id: "data_search",
      name: "Data Search",
      description:
        "Pulls alarms, SCADA snapshots, frequency profiles, and historical patterns on demand. Use this to dig deeper into anything the investigator surfaces.",
      tools: ["find_alarms", "find_scada", "frequency_summary", "pattern_history"],
      welcome:
        "**Data Search agent — ready.**\n\n" +
        "I can pull operational data for the MARRABEL_NX event and related stations:\n\n" +
        "- Alarm queries (`find_alarms` — by station + time window)\n" +
        "- SCADA telemetry snapshots (`find_scada` — any TagId)\n" +
        "- Frequency excursion profiles (`frequency_summary` — per region)\n" +
        "- Historical pattern data (`pattern_history` — by equipment)\n\n" +
        'Try *"Show MARRABEL alarms around 11:15"* or *"Frequency profile for EHR region"*.',
      replies: [
        { match: "redcliff", text: REPLY_MARRABEL },
        { match: "frequency", text: REPLY_FREQUENCY },
        { match: "alarm", text: REPLY_ALARM },
        { match: "scada", text: REPLY_SCADA },
        { match: "northvale", text: REPLY_KETTERING },
        { match: "history", text: REPLY_HISTORY },
        { match: "wentworth", text: REPLY_OAKBANK },
        /* Generic operational needles — exercised by the kiosk
           suggested-query pills so a casual viewer can poke the
           data-search agent without scenario knowledge. */
        { match: "load profile", text: REPLY_LOAD_PROFILE },
        { match: "by region", text: REPLY_GEN_BY_REGION },
        { match: "capacity headroom", text: REPLY_CAPACITY },
        { match: "equipment status", text: REPLY_EQUIPMENT_STATUS },
        { match: "open switching", text: REPLY_OPEN_SWITCHING },
        { match: "", text: REPLY_FALLBACK },
      ],
    },
  ],
  classifications: CLASSIFICATIONS,
};
