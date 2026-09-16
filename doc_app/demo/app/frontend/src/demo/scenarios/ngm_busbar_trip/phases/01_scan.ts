/**
 * Phase 1 — Situation scan frames (f000a–f000c).
 *
 * Module role:
 *   Starts the scan spinner, waits 10 seconds, then populates the
 *   situation panel with the 5 detected situations.
 *
 * Runtime: ~12 seconds.
 */

import type { Frame } from "../../../scenarioSchema";
import { ALL_SITUATIONS } from "../situations";
import { NGM_GRID_STATUS } from "../gridStatus";
import {
  NGM_AUDIT_REPORT,
  NGM_AUDIT_STREAM_EVENTS,
  NGM_DATA_SEARCH_MESSAGES,
  NGM_DETECTOR_COMPARISON,
  NGM_DETECTOR_CONFIG,
  NGM_DETECTOR_DRAFT,
} from "../featureShowcase";

export const scanFrames: Frame[] = [
  /* f000a — Scan start: triggers the radar/spinner animation. */
  {
    id: "f000a",
    chapter: "Situation scan",
    narration:
      "Every station, person, procedure and incident in this scenario is fictional.",
    annotation: {
      target: "panel-situations",
      caption:
        "This is the Situations column. Every five minutes GridIQ scans the grid and ranks what it finds here.",
      placement: "right",
    },
    transition_ms: 200,
    patch: {
      "panel.situations.scan_start": { estimate_ms: 10000 },
    },
  },

  /* f000b — Scan wait: empty frame, holds for the 10-second scan animation. */
  {
    id: "f000b",
    narration:
      "The scan is processing roughly 40,000 SCADA tags and the last hour of alarm history.",
    transition_ms: 10000,
    patch: {},
  },

  /* f000c — Situations detected: populates the 5 situation cards. */
  {
    id: "f000c",
    chapter: "Situations detected",
    narration:
      "Five situations detected, ranked by severity: one CRITICAL, one MAJOR, one SERIOUS, two INVESTIGATE.",
    annotation: {
      target: "situation-card-ngm-crit-1",
      caption:
        "CRITICAL at the top: 412 MW lost at MARRABEL_NX. Severity, station, score, and impact — all at a glance.",
      placement: "right",
    },
    transition_ms: 1500,
    patch: {
      "panel.situations.set": {
        situations: [...ALL_SITUATIONS],
        grid_status: NGM_GRID_STATUS,
      },
      "panel.detector_config.set": {
        detectorConfig: NGM_DETECTOR_CONFIG,
        detectorDraft: NGM_DETECTOR_DRAFT,
        detectorDirty: true,
        detectorComparison: NGM_DETECTOR_COMPARISON,
        windowMinutes: 5,
        maxAlarmRows: 80000,
        maxScadaRows: 120000,
      },
      "dock.thread.set": {
        agent: "data_search",
        messages: NGM_DATA_SEARCH_MESSAGES,
      },
      "panel.audit.set": {
        status: "completed",
        auditId: NGM_AUDIT_REPORT.id,
        report: NGM_AUDIT_REPORT,
        streamEvents: NGM_AUDIT_STREAM_EVENTS,
      },
    },
  },
];
