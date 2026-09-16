/**
 * Situation API — fetch detected grid incidents from the backend.
 */

import { BASE, authHeaders, handleResponse } from "./client";

/** Parameters for the situation detector scan. */
export interface SituationParams {
  start: string;
  end: string;
  station?: string;
  window_minutes?: number;
  max_hours?: number;
  /** Cap on raw alarm/SCADA rows pulled into scoring (latest N by
   *  timestamp_aest desc). Threaded into the detector's signal-layer
   *  KQL as ``| top N by timestamp_aest desc``. Driven by the
   *  control-bar slider. */
  input_row_cap?: number;
  /** 2026-05-24 split: per-stream alarm row cap. Overrides
   *  `input_row_cap` for the alarm-table KQL `| top N` clause. */
  max_alarm_rows?: number;
  /** 2026-05-24 split: per-stream SCADA row cap. Overrides
   *  `input_row_cap` for the SCADA-table KQL `| top N` clause. */
  max_scada_rows?: number;
}

/** A single alarm row attached to an affected equipment entry. */
export interface EquipmentAlarm {
  timestamp_aest: string;
  alarm_label: string;
  alarm_text: string;
  priority: number;
  mrid: string;
}

/** A single SCADA step-change row attached to an affected equipment entry. */
export interface EquipmentScada {
  timestamp_aest: string;
  TagId: string;
  measurement: string;
  Value: number;
  prev_val: number;
  abs_drop: number;
  pct_change: number;
}

/** Per-equipment evidence bundle — alarms and SCADA sorted by severity/magnitude. */
export interface AffectedEquipment {
  equipment_id: string;
  alarms: EquipmentAlarm[];
  scada: EquipmentScada[];
}

/** A single detected situation record. */
export interface SituationRecord {
  situation_id: string;
  window_start: string;
  window_end: string;
  station: string;
  severity: string;
  total_score: number;
  alarm_score: number;
  scada_score: number;
  mw_boost: number;
  total_mw_lost: number;
  max_mw_drop: number;
  alarm_count: number;
  step_changes: number;
  alarm_signals: string;
  scada_signals: string;
  alarm_mrids: string;
  affected_tags: string;
  affected_equipment: string;
  patterns: string;
  pattern_details: string;
  /** Per-signal evidence map, JSON-encoded. Decoded shape carries
   *  `{alarm, scada, patterns}` buckets, each keyed by signal_id with
   *  `{rule, rows, count}` entries. Empty `"{}"` on partial frames
   *  (the evidence layer runs after the partial event) and on
   *  records that fired no signals. See
   *  [specs/signal_evidence_2026-05-24_proposal.md]. */
  signal_evidence?: string;
  /** Per-station rollup for the unit_unplanned_offline pattern.
   *  Empty object when the pattern did not match. */
  unit_offline_summary?: {
    trip_count?: number;
    cb_count?: number;
    mwcc_count?: number;
    kv_emer_count?: number;
    score_contribution_total?: number;
  };
  detected_at: string;
  detector_version: string;
  config_hash: string;
  station_region: string;
  station_rated_mw: number;
  station_unit_count: number;
  region_rated_mw: number;
  region_live_mw: number;
  nem_live_mw: number;
  impact_station_pct: number;
  impact_region_pct: number;
  impact_nem_pct: number;
  score_contributions?: ScoreContribution[];
}

export interface ScoreContribution {
  group: "alarm" | "scada" | "mw" | "pattern" | "frequency";
  signal_id: string;
  label: string;
  points: number;
  count?: number;
  evidence?: string[];
}

/** Per-signal evidence wire shape — the decoded form of
 *  `SituationRecord.signal_evidence`. Mirrors the backend payload
 *  produced by `tools/situations/detector/layers/signal_evidence.py`. */
export interface AlarmSignalEvidenceRule {
  id: string;
  col: string;
  op: "==" | "contains";
  val: string;
  points: number;
  min_count?: number;
  extra_col?: string;
  extra_op?: string;
  extra_val?: string;
}

export interface ScadaSignalEvidenceRule {
  id: string;
  tag_contains: string[];
  meas: string;
  cond_type: string;
  threshold?: number;
  baseline?: number;
  direction?: string;
  points: number;
}

export interface AlarmEvidenceRow {
  timestamp_aest: string;
  alarm_label: string;
  alarm_text: string;
  priority: number;
  client_composite_id?: string;
  mrid?: string;
}

export interface ScadaEvidenceRow {
  timestamp_aest: string;
  TagId: string;
  measurement: string;
  Value: number;
  prev_val: number;
  abs_drop: number;
  pct_change: number;
}

export interface AlarmSignalEvidence {
  rule: AlarmSignalEvidenceRule;
  rows: AlarmEvidenceRow[];
  count: number;
}

export interface ScadaSignalEvidence {
  rule: ScadaSignalEvidenceRule;
  rows: ScadaEvidenceRow[];
  count: number;
}

export interface PatternEvidence {
  id: string;
  details: Record<string, unknown>;
}

export interface SignalEvidence {
  alarm: Record<string, AlarmSignalEvidence>;
  scada: Record<string, ScadaSignalEvidence>;
  patterns: Record<string, PatternEvidence>;
}

/** Per-region frequency summary from the detector. */
export interface FreqRegionSummary {
  freq_min: number;
  freq_max: number;
  freq_avg: number;
  band_breached: string;
  band_label: string;
  excursion_count: number;
}

/** NEM-wide frequency summary from the detector. */
export interface FreqSummary {
  nem_freq_min: number;
  nem_freq_max: number;
  total_excursions: number;
  regions: Record<string, FreqRegionSummary>;
}

/** Response from GET /api/situations. */
export interface SituationResponse {
  situations: SituationRecord[];
  count: number;
  query_time_ms: number;
  freq_summary: FreqSummary | null;
  grid_status?: GridStatus | null;
  config_hash?: string;
  config_source?: "default" | "saved" | "preview";
}

export interface GridStatusMetric {
  tag_id: string | null;
  avg: number | null;
  min: number | null;
  max: number | null;
  latest: number | null;
  latest_ts: string | null;
  sample_count: number;
}

export interface GridStatusRegionFrequency {
  min_hz: number | null;
  max_hz: number | null;
  avg_hz: number | null;
  band_breached: string;
  band_label: string;
  excursion_count: number;
}

export interface GridStatusRegion {
  generation_mw: GridStatusMetric;
  demand_mw: GridStatusMetric;
  reserve_mw: GridStatusMetric;
  wind_mw: GridStatusMetric;
  solar_mw: GridStatusMetric;
  storage_mw: GridStatusMetric;
  renewable_mw: number | null;
  renewable_pct_generation: number | null;
  frequency: GridStatusRegionFrequency;
  threatened_mw: number;
  threatened_pct_generation: number | null;
  situation_count: number;
  station_count: number;
}

export interface GridStatusNemFrequency {
  min_hz: number | null;
  max_hz: number | null;
  total_excursion_windows: number;
  worst_band: string;
  worst_region: string | null;
}

export interface GridStatusNemAggregate {
  value: number | null;
  components?: string;
}

export interface GridStatusNem {
  generation_mw: GridStatusNemAggregate;
  demand_mw: GridStatusNemAggregate;
  reserve_mw: GridStatusMetric;
  renewable_mw: GridStatusNemAggregate;
  renewable_pct_generation: number | null;
  frequency: GridStatusNemFrequency;
  threatened_mw: number;
  threatened_pct_generation: number | null;
}

export interface GridStatusThreatRow {
  station: string;
  region: string;
  mw: number;
  situation_count: number;
  worst_severity: string;
}

export interface GridStatusSituations {
  count: number;
  station_count: number;
  severity_counts: Record<string, number>;
  threatened_mw: number;
  top_threats: GridStatusThreatRow[];
}

export interface GridStatusDataQuality {
  severity: "info" | "warning" | "error";
  code: string;
  message: string;
  tag_id?: string | null;
}

export interface GridStatus {
  window: { start: string; end: string; source: "scan_window" };
  tag_dict_version: string;
  nem: GridStatusNem;
  regions: Record<string, GridStatusRegion>;
  situations: GridStatusSituations;
  data_quality: GridStatusDataQuality[];
}

export interface SeverityThresholdPatch {
  investigate?: number;
  serious?: number;
  major?: number;
  critical?: number;
}

export interface MwBoostPatch {
  per_mw?: number;
  cap?: number;
}

export interface AlarmSignalPatch {
  id: string;
  enabled?: boolean;
  col?: "alarm_label" | "alarm_text" | "client_composite_id" | "priority";
  op?: "==" | "contains";
  val?: string;
  points?: number;
  min_count?: number;
  extra_col?: "alarm_label" | "alarm_text" | "client_composite_id" | "priority";
  extra_op?: "==" | "contains";
  extra_val?: string;
}

export interface ScadaSignalPatch {
  id: string;
  enabled?: boolean;
  tag_contains?: string[];
  meas?: string;
  cond?: string;
  cond_type?: "change_percent" | "change_absolute" | "drops_below" | "rises_above" | "drops_to_near_zero";
  direction?: "any" | "up" | "down";
  threshold?: number;
  baseline?: number;
  points?: number;
}

export interface DetectorConfigPatch {
  window_minutes?: number;
  max_hours?: number;
  severity_thresholds?: SeverityThresholdPatch;
  mw_boost?: MwBoostPatch;
  alarm_signals?: AlarmSignalPatch[];
  scada_signals?: ScadaSignalPatch[];
  patterns?: Record<string, Record<string, number>>;
}

export interface DetectorConfigResponse {
  patch: DetectorConfigPatch;
  effective_config: Record<string, unknown>;
  config_hash: string;
  source: "default" | "saved";
  updated_at: string | null;
}

export interface DetectorScanRequest extends SituationParams {
  preview_patch?: DetectorConfigPatch;
}

/** Fetch detected situations for a time window. */
export async function getSituations(params: SituationParams): Promise<SituationResponse> {
  const qs = new URLSearchParams();
  qs.set("start", params.start);
  qs.set("end", params.end);
  if (params.station) qs.set("station", params.station);
  if (params.window_minutes != null) qs.set("window_minutes", String(params.window_minutes));
  if (params.max_hours != null) qs.set("max_hours", String(params.max_hours));

  const res = await fetch(`${BASE}/situations/?${qs.toString()}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<SituationResponse>(res);
}

export async function getDetectorConfig(): Promise<DetectorConfigResponse> {
  const res = await fetch(`${BASE}/situations/config`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<DetectorConfigResponse>(res);
}

export async function saveDetectorConfig(patch: DetectorConfigPatch): Promise<DetectorConfigResponse> {
  const res = await fetch(`${BASE}/situations/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handleResponse<DetectorConfigResponse>(res);
}

export async function resetDetectorConfig(): Promise<DetectorConfigResponse> {
  const res = await fetch(`${BASE}/situations/config/reset`, {
    method: "POST",
    headers: { ...await authHeaders() },
  });
  return handleResponse<DetectorConfigResponse>(res);
}

/** Derive a safe max_hours from the requested window so the detector
 *  never silently drops a multi-hour or multi-day range against its
 *  hard time-range guard. The +1 hour pad covers rounding plus the
 *  detector's tumbling-window overhang; clamped to the backend ceiling
 *  (720h = 30d, per tools/situations/config.py). */
function deriveMaxHours(start: string, end: string): number {
  const t0 = Date.parse(start.replace(" ", "T"));
  const t1 = Date.parse(end.replace(" ", "T"));
  if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return 168;
  const hours = Math.ceil((t1 - t0) / 3_600_000) + 1;
  return Math.min(Math.max(hours, 1), 720);
}

export async function scanSituations(body: DetectorScanRequest): Promise<SituationResponse> {
  /* The detector returns [] when (end - start) > max_hours. Frontends that
     forget to pass max_hours therefore lose every multi-hour scan to the
     backend default. Auto-derive from the requested window unless the
     caller has explicitly set one. */
  const payload: DetectorScanRequest = {
    ...body,
    max_hours: body.max_hours ?? deriveMaxHours(body.start, body.end),
  };
  const res = await fetch(`${BASE}/situations/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleResponse<SituationResponse>(res);
}


// ── Streaming variant ────────────────────────────────────────────────────
//
// `streamSituations` drives `POST /api/situations/scan/stream`, parsing
// the SSE wire format with the same fetch + ReadableStream + line
// buffer pattern used by chatApi. Callbacks fire as events arrive so the
// store can append provisional situations on the first frame and patch
// in place when enrichment lands.

/** Event payloads delivered by the situation scan SSE stream. */
export type StreamEvent =
  | { type: "start"; data: { config_hash: string; config_source: string } }
  | { type: "phase"; data: { phase: string; count?: number; elapsed_ms: number } }
  | { type: "situation_partial"; data: SituationRecord }
  | { type: "situation"; data: SituationRecord }
  | { type: "freq_summary"; data: { freq_summary: FreqSummary | null; elapsed_ms: number } }
  | { type: "done"; data: { count: number; config_hash: string; elapsed_ms: number } }
  | { type: "error"; data: { error_code?: string; message?: string; detail?: string; code?: string } };

export interface StreamCallbacks {
  onStart?: (data: { config_hash: string; config_source: string }) => void;
  onPhase?: (data: { phase: string; count?: number; elapsed_ms: number }) => void;
  onSituationPartial?: (sit: SituationRecord) => void;
  onSituation?: (sit: SituationRecord) => void;
  onFreqSummary?: (data: { freq_summary: FreqSummary | null; elapsed_ms: number }) => void;
  onDone?: (data: { count: number; config_hash: string; elapsed_ms: number }) => void;
  onError?: (detail: string, code?: string) => void;
}

export async function streamSituations(
  body: DetectorScanRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const payload: DetectorScanRequest = {
    ...body,
    max_hours: body.max_hours ?? deriveMaxHours(body.start, body.end),
  };

  let res: Response;
  try {
    res = await fetch(`${BASE}/situations/scan/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...await authHeaders(),
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (fetchErr) {
    callbacks.onError?.((fetchErr as Error).message);
    return;
  }

  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    callbacks.onError?.(errBody || `HTTP ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError?.("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      // SSE frames are delimited by a blank line.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        if (!frame.trim()) continue;
        let eventType: string | null = null;
        const dataLines: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
        }
        if (!eventType) continue;
        let parsed: Record<string, unknown> = {};
        try {
          parsed = JSON.parse(dataLines.join("\n") || "{}");
        } catch {
          continue;
        }
        switch (eventType) {
          case "start": callbacks.onStart?.(parsed as never); break;
          case "phase": callbacks.onPhase?.(parsed as never); break;
          case "situation_partial": callbacks.onSituationPartial?.(parsed as never); break;
          case "situation": callbacks.onSituation?.(parsed as never); break;
          case "freq_summary": callbacks.onFreqSummary?.(parsed as never); break;
          case "done": callbacks.onDone?.(parsed as never); return;
          case "error": {
            // Canonical envelope after hygiene 2026-05-24 §A6:
            // ``{error_code, message}``. ``detail``/``code`` retained as
            // fallback for any cached client / legacy frame.
            const err = parsed as { error_code?: string; message?: string; detail?: string; code?: string };
            callbacks.onError?.(err.message ?? err.detail ?? "stream error", err.error_code ?? err.code);
            return;
          }
        }
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      callbacks.onError?.((err as Error).message);
    }
  }
}
