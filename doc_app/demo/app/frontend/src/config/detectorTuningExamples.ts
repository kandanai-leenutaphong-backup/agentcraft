/**
 * Detector-tuning preset examples for the Detector Tuning panel.
 *
 * Hard rule (per data-boundary mandate, 2026-05-01): no real station
 * codes, dates, or operational signal payloads in this file. The
 * tuning panel ships with an empty preset list by default; operators
 * may add their own scoped presets at runtime through the panel UI.
 */

export type ExpectedSeverity = "minor" | "investigate" | "serious" | "major" | "critical" | null;

export interface DetectorTuningExample {
  id: string;
  label: string;
  station?: string;
  start: string;
  end: string;
  expected_detected: boolean;
  expected_min_severity: ExpectedSeverity;
  expected_patterns: string[];
  description: string;
}

export const DETECTOR_TUNING_EXAMPLES: DetectorTuningExample[] = [];
