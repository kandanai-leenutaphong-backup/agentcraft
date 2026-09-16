/** Phase 8 — Full UI surface showcase for seeded kiosk-only panels. */

import type { Frame } from "../../../scenarioSchema";

export const fullUiShowcaseFrames: Frame[] = [
  {
    id: "f080a",
    chapter: "Data search evidence",
    narration:
      "The same investigation data is available outside the guided chat. Data Search opens with a preloaded evidence thread: alarms, SCADA changes, frequency context, and precursor history.",
    annotation: {
      target: "center-tab-data",
      caption: "Data Search is now a populated investigation surface, not an empty helper tab.",
      placement: "bottom",
    },
    transition_ms: 4500,
    patch: {
      "panel.center_tab.set": { tab: "data" },
    },
  },
  {
    id: "f080b",
    chapter: "Detector tuning controls",
    narration:
      "Detector Tuning shows the actual control surface: severity thresholds, alarm rules, SCADA rules, sensitivity controls, and draft-impact comparison against this event.",
    annotation: {
      target: "center-tab-tuning",
      caption: "The controls are spoofed, but the UI path is the real tuning panel.",
      placement: "bottom",
    },
    transition_ms: 4500,
    patch: {
      "panel.center_tab.set": { tab: "tuning" },
    },
  },
  {
    id: "f080c",
    chapter: "System evaluation",
    narration:
      "The audit surface is also seeded. It scores whether the investigation used enough evidence, covered topology, avoided unsupported claims, and produced grounded actions.",
    annotation: {
      target: "center-tab-evaluations",
      caption: "System Evaluations carries a completed synthetic audit report plus the audit tool trace.",
      placement: "bottom",
    },
    transition_ms: 5000,
    patch: {
      "panel.center_tab.set": { tab: "evaluations" },
    },
  },
  {
    id: "f080d",
    chapter: "Operational status",
    narration:
      "The demo closes back on Grid Status, with the situation list, topology, data search, tuning controls, and audit all populated from the same scenario state.",
    annotation: {
      target: "center-tab-status",
      caption: "Grid Status closes the loop: every panel is populated from the same scenario state.",
      placement: "bottom",
    },
    transition_ms: 3500,
    patch: {
      "panel.center_tab.set": { tab: "status" },
    },
  },
];
