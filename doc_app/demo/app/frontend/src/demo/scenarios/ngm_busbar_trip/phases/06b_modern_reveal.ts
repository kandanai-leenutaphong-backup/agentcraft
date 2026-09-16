/**
 * Phase 6b — Modernized surface reveal (NGM).
 *
 * Module role:
 *   Inserted AFTER priority actions land (06_actions) and BEFORE the
 *   precursor reveal (07_precursor). Tours every modernized workspace
 *   surface at the dramatically correct moment — once the operator has
 *   the evidence pack AND the actions, the verdict, summary, audit,
 *   detector tuning, data search, and system status panels each get
 *   their narrative beat.
 *
 *   Each panel was pre-seeded in 01_scan / 02_classify so flipping the
 *   center tab here brings a fully-populated surface front-of-stage.
 *   Pure additive center_tab.set + narration; no new framework.
 *
 *   Runtime: ~30 s across 8 frames at default speed.
 */

import type { Frame } from "../../../scenarioSchema";

export const modernRevealFrames: Frame[] = [
  /* m01 — Anchor on the classify verdict banner above Priority Actions. */
  {
    id: "m01",
    chapter: "Modern surfaces — verdict",
    narration:
      "Before the precursor reveal, look across the workspace. The classify verdict banner is fixed " +
      "above Priority Actions: non-credible double-unit contingency, Operating Code §4.3.1A(c). The " +
      "agent's own NER 4.2.3 call, sourced and dated. This is the surface the duty manager screenshots " +
      "into a market notice.",
    annotation: {
      target: "center-tab-priorities",
      caption: "Classify verdict + five grounded actions sit on one panel. Operator-shareable as-is.",
      placement: "bottom",
    },
    transition_ms: 3500,
    patch: {
      "panel.center_tab.set": { tab: "priorities" },
    },
  },

  /* m02 — Pivot to the situation summary card. */
  {
    id: "m02",
    chapter: "Modern surfaces — summary",
    narration:
      "The live Situation Summary card aggregates the evidence into a one-screen narrative. Headline, " +
      "three evidence bullets, one open question. Confidence high. Source event ids cited. This is what " +
      "rolls into the post-event review without anyone re-typing it.",
    annotation: {
      target: "center-tab-situation",
      caption: "Situation Summary — auto-generated, evidence-cited, edit-tracked.",
      placement: "bottom",
    },
    transition_ms: 3500,
    patch: {
      "panel.center_tab.set": { tab: "situation" },
    },
  },

  /* m03 — Investigation audit. */
  {
    id: "m03",
    chapter: "Modern surfaces — audit",
    narration:
      "The Session Audit card scores the investigation: six rubric dimensions, weighted out of 21, " +
      "banded strong / adequate / weak. Evidence coverage, topology coverage, hypothesis quality, action " +
      "grounding, summary quality, and an absolute grounding gate that clamps the band if anything was " +
      "hallucinated. This audit ran while the investigation streamed.",
    annotation: {
      target: "center-tab-evaluations",
      caption: "Audit is not a post-mortem report — it watched the live session and scored as it went.",
      placement: "bottom",
    },
    transition_ms: 4000,
    patch: {
      "panel.center_tab.set": { tab: "evaluations" },
    },
  },

  /* m04 — Detector tuning. */
  {
    id: "m04",
    chapter: "Modern surfaces — detector tuning",
    narration:
      "Detector Tuning is the operator-owned policy surface. The signal rules, severity thresholds, and " +
      "alarm / SCADA rule rows are editable in plain English. The Apply diff shows how a draft would " +
      "have changed THIS event's situations — promote, demote, or leave alone. Tuning never blocks the " +
      "investigation; it shapes the next one.",
    annotation: {
      target: "center-tab-tuning",
      caption: "Detector Tuning — declarative rules, draft-vs-applied diff, no YAML required.",
      placement: "bottom",
    },
    transition_ms: 4000,
    patch: {
      "panel.center_tab.set": { tab: "tuning" },
    },
  },

  /* m05 — Data Search dock. */
  {
    id: "m05",
    chapter: "Modern surfaces — Data Search",
    narration:
      "Data Search is the operator's own investigator. Same tool library as the GridManager agent — " +
      "alarms, SCADA, topology graph, near-hit search, SMIRKS — but driven by free-text queries. The " +
      "thread on screen is the evidence pack the agent assembled, re-runnable on demand.",
    annotation: {
      target: "center-tab-data",
      caption: "Data Search shares one tool library with the agent. No mode-switch, no second product.",
      placement: "bottom",
    },
    transition_ms: 4000,
    patch: {
      "panel.center_tab.set": { tab: "data" },
    },
  },

  /* m06 — NGM Grid Status dashboard. */
  {
    id: "m06",
    chapter: "Modern surfaces — system view",
    narration:
      "NGM Grid Status is the always-on system view: every region, every threat band, every active " +
      "situation rolled into one ribbon. The SER region is currently CRITICAL because of MARRABEL_NX. " +
      "Resolve the situation, the ribbon goes green. The state belongs to the system, not the chat.",
    annotation: {
      target: "center-tab-status",
      caption: "Grid Status — five regions, live threat bands, deterministic.",
      placement: "bottom",
    },
    transition_ms: 4000,
    patch: {
      "panel.center_tab.set": { tab: "status" },
    },
  },

  /* m07 — Return to priorities, set up the precursor pivot. */
  {
    id: "m07",
    narration:
      "Back to Priority Actions to hold the verdict banner in frame while we pivot to the precursor.",
    transition_ms: 1800,
    patch: {
      "panel.center_tab.set": { tab: "priorities" },
    },
  },

  /* m08 — Pre-precursor topology focus. */
  {
    id: "m08",
    narration:
      "Now the camera moves to topology — same MARRABEL_NX 275 kV switchyard, but rewound 37 minutes " +
      "before the trip. The next phase is the precursor that GridIQ caught and a human would have missed.",
    transition_ms: 1500,
    patch: {
      "panel.center_tab.set": { tab: "topology" },
    },
  },
];
