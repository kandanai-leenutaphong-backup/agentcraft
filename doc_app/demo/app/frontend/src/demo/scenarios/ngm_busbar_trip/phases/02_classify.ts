/**
 * Phase 2 — Classification frames (f000d–f000e).
 *
 * Module role:
 *   Shows the "Classifying per Operating Code §4.3.1..." spinner, then reveals
 *   classification badges on all 5 situation cards.
 *
 * Runtime: ~4 seconds.
 */

import type { Frame } from "../../../scenarioSchema";

export const classifyFrames: Frame[] = [
  /* f000d — Classification spinner: narration while badges are computing. */
  {
    id: "f000d",
    narration:
      "Each card is being classified against the Grid Operating Rules.",
    transition_ms: 3000,
    patch: {},
  },

  /* f000e — Classifications appear: injects all 5 classification verdicts. */
  {
    id: "f000e",
    chapter: "Classifications",
    narration:
      "The CRITICAL is non-credible: two generating units lost from one busbar, beyond a single credible contingency under the rules.",
    annotation: {
      target: "situation-card-ngm-crit-1",
      caption:
        "Classification badge under each card: credible / non-credible / non-event, with the GOR citation. Click for the full rationale.",
      placement: "right",
    },
    transition_ms: 1000,
    patch: {
      "panel.summary.set": {
        summary: {
          status: "idle",
          current: {
            headline: "MARRABEL_NX busbar fault drove 430 MW threatened/lost generation and regional frequency stress.",
            bullets: [
              "275 kV Bus 275-1 de-energised after bus differential and DS-275-13 earth-fault indications.",
              "Units 3 and 4 disconnected from Bus 275-1; Unit 1 remained stable on Bus 275-2.",
              "KETTERING loading and OAKBANK transformer trip are downstream consequences, not independent initiating events.",
            ],
            open_questions: [
              "Confirm DS-275-13 physical mechanism through protection records and field inspection.",
            ],
            confidence: "high",
            source_event_ids: ["ngm-crit-1", "ngm-maj-1", "ngm-inv-1"],
            updated_at: "2026-02-12T11:28:00+10:00",
          },
          revisions: [],
          processed_event_ids: ["ngm-crit-1", "ngm-maj-1", "ngm-inv-1"],
          pending_event_ids: [],
          last_error: null,
        },
      },
      "panel.classify_verdict.set": {
        verdict: {
          verdict: "non_credible_event",
          justification:
            "Simultaneous loss of two generating units through a shared 275 kV busbar fault exceeds the single-element credible-contingency boundary; classify as non-credible pending reclassification review.",
          sources: ["Operating Code §4.3.1A(c)", "bus differential event", "unit trip evidence"],
          updated_at: "2026-02-12T11:28:00+10:00",
        },
      },
      "panel.situations.classify": {
        classifications: [
          {
            situation_id: "ngm-pre-1",
            classification: "non_event",
            ner_citation: "Operating Code §4.7.2(a) — precursor advisory",
            rationale:
              "A 15-second voltage transient on the 275 kV Bus 275-1 (dip to 248.0 kV, 9.9% depression, " +
              "recovered to nominal) does not meet the threshold for a reportable grid incident — no " +
              "protection operated and no equipment was lost. However, the depth and shape of the transient " +
              "are consistent with early-stage insulation breakdown on a connected primary plant element. " +
              "GridIQ recommends an immediate thermal/insulation inspection of all bay equipment connected " +
              "to the 275 kV Bus 275-1, prioritising bus section isolators. This is an early-warning advisory, " +
              "not a contingency event.",
          },
          {
            situation_id: "ngm-crit-1",
            classification: "non_credible",
            ner_citation: "Operating Code §4.3.1A(c)",
            rationale:
              "The simultaneous loss of two generating units connected to the same busbar section constitutes " +
              "a non-credible contingency under the GOR, as credible contingency assessment considers the loss " +
              "of a single generating unit or single network element. The busbar fault affected two independent " +
              "units via shared protection, which exceeds the single-element boundary. The grid authority assessed " +
              "reclassification under Operating Code §4.3.1A(c) and determined recurrence was not reasonably possible after " +
              "the faulty isolator was identified and bypassed.",
          },
          {
            situation_id: "ngm-maj-1",
            classification: "non_event",
            ner_citation: "Operating Code §4.7.2(a)(1)(i)",
            rationale:
              "The KETTERING interconnector loading surge is a consequential power system response to the " +
              "MARRABEL_NX generation loss, not an independent contingency. No protection operated at KETTERING — " +
              "the alarms are thermal loading advisories. The interconnector remained within its emergency rating. " +
              "This does not meet the threshold for a reportable grid incident as no critical transmission element " +
              "was lost or at risk of loss.",
          },
          {
            situation_id: "ngm-ser-1",
            classification: "non_event",
            ner_citation: "Operating Code §4.7.2(a)",
            rationale:
              "GLENRIDGE_NX experienced automatic governor response to the NGM frequency excursion. Both units " +
              "ramped from 165 MW to 178 MW (within rated capacity) as part of normal FRS fast-raise response. " +
              "No protection operated. No equipment tripped. The SCADA step-changes reflect controlled frequency " +
              "response, not a fault or contingency. Does not meet the definition of a reportable grid incident.",
          },
          {
            situation_id: "ngm-inv-1",
            classification: "credible",
            ner_citation: "Operating Code §4.3.1(b)",
            rationale:
              "OAKBANK_NX 132/66 kV transformer T2 tripped on overcurrent protection following the " +
              "redistribution of load after the MARRABEL_NX event. The loss of a single transformer constitutes " +
              "a credible contingency under Operating Code §4.3.1(b). However, the trip occurred 8 minutes after the " +
              "initiating event and was caused by load redistribution, not equipment failure. The transformer " +
              "was tested and returned to service within 25 minutes. The grid authority determined the overcurrent " +
              "condition was transient and not indicative of a persistent risk.",
          },
        ],
      },
    },
  },
];
