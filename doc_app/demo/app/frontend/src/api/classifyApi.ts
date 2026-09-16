/**
 * classifyApi — POST /api/situations/classify
 *
 * Background NER 4.2.3 classifier. The frontend fires this once per
 * situation card on first mount; the backend caches results by
 * situation_id so repeated mounts are free.
 *
 * Returns:
 *   - classification: "credible" | "non_credible" | "non_event"
 *   - confidence:     integer 0–100 (classifier's self-assessed certainty)
 *   - ner_citation:   "NER 4.2.3(b)" | "NER 4.2.3(e)" | null
 *   - rationale:      one-sentence explanation
 *   - cached:         true if served from server cache
 *   - duration_ms:    end-to-end LLM call time
 */

import { BASE, authHeaders, handleResponse } from "./client";

export type SituationClassification = "credible" | "non_credible" | "non_event";

export interface ClassificationResult {
  situation_id: string;
  classification: SituationClassification;
  confidence: number;
  ner_citation: string | null;
  rationale: string;
  cached: boolean;
  duration_ms?: number;
  error?: string;
}

/** Request body matches the SituationRecord subset the backend reads. */
export interface ClassificationRequest {
  situation_id: string;
  severity?: string;
  station?: string;
  station_region?: string;
  total_score?: number;
  total_mw_lost?: number;
  alarm_signals?: string;
  scada_signals?: string;
  affected_equipment?: string;
  window_start?: string;
  window_end?: string;
}

export async function classifySituation(req: ClassificationRequest): Promise<ClassificationResult> {
  const res = await fetch(`${BASE}/situations/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify(req),
  });
  return handleResponse<ClassificationResult>(res);
}
