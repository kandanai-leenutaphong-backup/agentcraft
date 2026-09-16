/**
 * Situation store — manages situation detector results + scan parameters.
 *
 * Fetches situations via POST /api/situations/scan. Detector tuning drafts
 * must be applied first so the backend cache becomes the scan source of truth.
 * Stores results for the
 * SituationAlertsPanel and OperatingStatePanel. Also handles the
 * "Investigate" flow: creates a new chat session and injects the
 * situation summary as the first user message. When the background
 * NER 4.2.3 classifier has returned a verdict for the situation, the
 * Investigate prompt appends an "advisory hypothesis only" block
 * carrying the classifier's verdict + rationale; the agent is
 * instructed to confirm or refute it, never to accept it. When the
 * classifier is still loading, errored, or idle, the block is omitted
 * entirely.
 */

import { create } from "zustand";
import type {
  DetectorConfigPatch,
  DetectorConfigResponse,
  FreqSummary,
  SituationParams,
  SituationRecord,
} from "@/api/situationApi";
import {
  getDetectorConfig,
  resetDetectorConfig as resetDetectorConfigApi,
  saveDetectorConfig as saveDetectorConfigApi,
  scanSituations,
  streamSituations,
} from "@/api/situationApi";
import { classifySituation, type ClassificationResult, type SituationClassification } from "@/api/classifyApi";
/* Wire-decoder helpers — single source of truth for the JSON-encoded
   SituationRecord fields. The store needs them for cluster-prompt
   building (representative equipment + alarm/SCADA signal counts).
   Pre-hygiene the same parse logic was duplicated here with subtle
   drift; the lib helpers carry explicit shape guards. */
import {
  parseAffectedEquipment,
  parseSignalCounts,
  hhmm as hhmmSlice,
} from "@/lib/situationRecord";
import { IS_KIOSK } from "@/foundation/constants";

/* Per-situation classification state. The card uses ``status`` to decide
   whether to render a spinner ("loading"), a coloured badge ("ready"),
   a retry hint ("error"), or nothing yet ("idle"). */
export interface ClassificationState {
  status: "idle" | "loading" | "ready" | "error";
  classification?: SituationClassification;
  /** Classifier's self-assessed certainty, integer 0–100. Undefined
   *  while the request is in flight; the backend defaults missing
   *  model output to 50 (neutral mid-scale) so this is always a
   *  number once `status === "ready"`. */
  confidence?: number;
  ner_citation?: string | null;
  rationale?: string;
  error?: string;
}

export interface DetectorComparisonResult {
  matched: number;
  missed: number;
  severity_mismatches: number;
  rows: Array<{
    id: string;
    label: string;
    current: string;
    draft: string;
  }>;
}

interface SituationStore {
  /** Raw situations from the last scan (uncapped). */
  rawSituations: SituationRecord[];
  /** Situations after applying the result-limit slider (latest N by
   *  window_start desc). This is the list every consumer reads. */
  situations: SituationRecord[];
  /** Whether a scan is in progress. */
  loading: boolean;
  /** Error message from the last scan failure. */
  error: string | null;
  /** Query time from the last scan (ms). */
  queryTimeMs: number | null;
  /** Frequency summary from the last scan. */
  freqSummary: FreqSummary | null;
  /** Grid Status dashboard payload from the last scan. */
  gridStatus: import("@/api/situationApi").GridStatus | null;
  /** Config provenance from the last scan. */
  configHash: string | null;
  configSource: "default" | "saved" | "preview" | null;
  /** Current scan parameters. */
  params: SituationParams;
  /** Per-situation NER 4.2.3 classification results, keyed by situation_id. */
  classifications: Record<string, ClassificationState>;

  /** Wall-clock ms timestamp when the in-flight scan started. null when idle.
   *  Drives the elapsed counter in the progress UI. */
  scanStartedAt: number | null;
  /** Estimated total duration (ms) for the in-flight scan, derived from the
   *  rolling average of recent successful scans. Used to render an ETA. */
  scanEstimateMs: number | null;
  /** Rolling EWMA of recent successful scan durations (ms). Persisted to
   *  localStorage under STORAGE_KEY_DURATION so estimates survive reloads. */
  rollingDurationMs: number;

  detectorConfig: DetectorConfigResponse | null;
  detectorDraft: DetectorConfigPatch;
  detectorDirty: boolean;
  detectorSaving: boolean;
  detectorComparison: DetectorComparisonResult | null;

  /** Per-stream alarm row cap. 2026-05-24 split of the legacy combined
   *  `inputRowCap` into two operator knobs so the UI can read
   *  "Maximum Total Alarms" / "Maximum Total SCADA" as separate
   *  sliders. Threaded into the scan request as `max_alarm_rows`;
   *  backend uses it at `_score_alarms` `| top N by timestamp_aest desc`. */
  maxAlarmRows: number;
  /** Per-stream SCADA row cap. Symmetric pair to `maxAlarmRows`. */
  maxScadaRows: number;
  /** Update the alarm-stream slider and persist. Takes effect on the
   *  next scan. */
  setMaxAlarmRows: (n: number) => void;
  /** Update the SCADA-stream slider and persist. Takes effect on the
   *  next scan. */
  setMaxScadaRows: (n: number) => void;

  /** Detector bucket size in minutes (the inner window the detector
   *  uses to aggregate signals + classify patterns — NOT the operator's
   *  scan range). Driven by the dial in SituationControlBar and threaded
   *  into the scan request body as `window_minutes`. Backend default is
   *  10 (see `tools/situations/config.py#L33`); we surface it as a
   *  cute fun dial so operators can dial finer (5 min for fast
   *  cascades) or coarser (30 min for slow degradation). */
  windowMinutes: number;
  /** Update the dial value and persist. Takes effect on the next
   *  scan — does not retroactively re-scan. */
  setWindowMinutes: (n: number) => void;

  /** Update scan parameters (partial). */
  setParams: (partial: Partial<SituationParams>) => void;
  /** Execute the situation detector scan. */
  fetchSituations: () => Promise<void>;
  loadDetectorConfig: () => Promise<void>;
  setDetectorDraft: (partial: DetectorConfigPatch) => void;
  runDetectorComparison: () => Promise<void>;
  saveDetectorConfig: () => Promise<void>;
  resetDetectorConfig: () => Promise<void>;
  previewDetectorConfig: () => Promise<void>;
  /** Build a natural-language prompt from a situation record for the Investigator. */
  buildInvestigatePrompt: (situation: SituationRecord) => string;
  /** Fire the background NER 4.2.3 classifier for a single situation.
   *  Idempotent — skips the call if status is already loading or ready. */
  classifySituation: (situation: SituationRecord) => Promise<void>;
}

/* localStorage key for the rolling-average scan duration. Keeps the
   ETA accurate across reloads — a fresh tab still has a sensible
   estimate from the last session. */
const STORAGE_KEY_DURATION = "situation.scan.rollingDurationMs";

/* Default scan window — randomised per page load across the
 * July → October 2025 demo corpus with a one-hour aperture. The
 * historical scenarios are concentrated in this band, so a random
 * pick lands the operator on real activity more often than a fixed
 * default would, without committing to any single scenario.
 *
 * The randomisation runs once at module init; subsequent setParams
 * calls (Historical Test Scenario picker, manual date picker) replace
 * it. */
function _randomDefaultWindow(): { start: string; end: string } {
  // Inclusive-of-Jul-1, exclusive-of-Nov-1 → 4 calendar months.
  const start = new Date(2025, 6, 1, 0, 0, 0, 0).getTime(); // 2025-07-01
  const end = new Date(2025, 10, 1, 0, 0, 0, 0).getTime();  // 2025-11-01
  const ms = start + Math.random() * (end - start);
  // Snap to the nearest 5-minute bin so the time looks operator-natural.
  const snapped = Math.round(ms / (5 * 60_000)) * (5 * 60_000);
  const t0 = new Date(snapped);
  const t1 = new Date(snapped + 60 * 60_000);
  const fmt = (d: Date): string => {
    const pad = (n: number) => String(n).padStart(2, "0");
    return (
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  };
  return { start: fmt(t0), end: fmt(t1) };
}

const _DEFAULT_WINDOW = _randomDefaultWindow();

/* Default scan estimate (ms) for the very first scan after install,
   when no history exists. Tuned from observed cold-cache scans of
   ~1.5h windows: ~25 s. */
const DEFAULT_SCAN_ESTIMATE_MS = 25_000;
/* Smoothing factor for the rolling-average — favours recent scans
   while still being resistant to one outlier. */
const EWMA_ALPHA = 0.4;

/* Read the persisted rolling duration on module load. Returns the
   default when the value is missing or malformed (e.g. user cleared
   storage, or first run). */
function readRollingDuration(): number {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY_DURATION) : null;
    if (!raw) return DEFAULT_SCAN_ESTIMATE_MS;
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return DEFAULT_SCAN_ESTIMATE_MS;
    return n;
  } catch {
    return DEFAULT_SCAN_ESTIMATE_MS;
  }
}

function mergeSignalPatches<T extends { id: string }>(current: T[] | undefined, incoming: T[] | undefined): T[] | undefined {
  if (!incoming) return current;
  const byId = new Map((current ?? []).map((item) => [item.id, { ...item }]));
  const order = (current ?? []).map((item) => item.id);
  for (const item of incoming) {
    if (!byId.has(item.id)) order.push(item.id);
    byId.set(item.id, { ...(byId.get(item.id) ?? {}), ...item });
  }
  return order.map((id) => byId.get(id)).filter((item): item is T => Boolean(item));
}

function mergeDetectorDraft(current: DetectorConfigPatch, incoming: DetectorConfigPatch): DetectorConfigPatch {
  return {
    ...current,
    ...incoming,
    severity_thresholds: incoming.severity_thresholds ? { ...(current.severity_thresholds ?? {}), ...incoming.severity_thresholds } : current.severity_thresholds,
    mw_boost: incoming.mw_boost ? { ...(current.mw_boost ?? {}), ...incoming.mw_boost } : current.mw_boost,
    alarm_signals: mergeSignalPatches(current.alarm_signals, incoming.alarm_signals),
    scada_signals: mergeSignalPatches(current.scada_signals, incoming.scada_signals),
    patterns: incoming.patterns ? { ...(current.patterns ?? {}), ...incoming.patterns } : current.patterns,
  };
}

/* Persisted key + default for the input-row-cap slider. The slider
 * controls how many raw alarm + SCADA rows the detector pulls into
 * scoring (latest N by timestamp_aest desc) — NOT how many situations
 * are surfaced. This is the primary lever for keeping multi-day scans
 * inside cluster memory bounds and shortening wall-clock. */
const STORAGE_KEY_INPUT_CAP = "situation.scan.inputRowCap"; // legacy; read once for migration only
const STORAGE_KEY_MAX_ALARM = "situation.scan.maxAlarmRows";
const STORAGE_KEY_MAX_SCADA = "situation.scan.maxScadaRows";
const DEFAULT_INPUT_ROW_CAP = 50_000;
export const INPUT_ROW_CAP_MIN = 1_000;
export const INPUT_ROW_CAP_MAX = 500_000;
export const INPUT_ROW_CAP_STEP = 1_000;

/* 2026-05-24 split: the legacy combined `inputRowCap` is read ONCE
   for migration so existing operator sessions don't lose their tuned
   value, then the per-stream keys take over. Both sliders share the
   same min/max/step — the range cap (CHAOS-006/007/021) applies to
   each stream independently. */
function readLegacyRowCap(): number | null {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY_INPUT_CAP) : null;
    if (!raw) return null;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < INPUT_ROW_CAP_MIN) return null;
    return Math.min(Math.max(Math.round(n), INPUT_ROW_CAP_MIN), INPUT_ROW_CAP_MAX);
  } catch {
    return null;
  }
}

function readMaxAlarmRows(): number {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY_MAX_ALARM) : null;
    if (raw) {
      const n = Number(raw);
      if (Number.isFinite(n) && n >= INPUT_ROW_CAP_MIN) {
        return Math.min(Math.max(Math.round(n), INPUT_ROW_CAP_MIN), INPUT_ROW_CAP_MAX);
      }
    }
    return readLegacyRowCap() ?? DEFAULT_INPUT_ROW_CAP;
  } catch {
    return DEFAULT_INPUT_ROW_CAP;
  }
}

function readMaxScadaRows(): number {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY_MAX_SCADA) : null;
    if (raw) {
      const n = Number(raw);
      if (Number.isFinite(n) && n >= INPUT_ROW_CAP_MIN) {
        return Math.min(Math.max(Math.round(n), INPUT_ROW_CAP_MIN), INPUT_ROW_CAP_MAX);
      }
    }
    return readLegacyRowCap() ?? DEFAULT_INPUT_ROW_CAP;
  } catch {
    return DEFAULT_INPUT_ROW_CAP;
  }
}

/* Detector bucket window. Backend default is 10 minutes
   (tools/situations/config.py#L33). Range 1..120 covers the practical
   operator span: 1 min for sub-minute cascades, 120 for slow drift.
   Step is 1 (the dial snaps visually but the underlying control allows
   fine resolution). Persisted to localStorage. */
const STORAGE_KEY_WINDOW_MINUTES = "situation.scan.windowMinutes";
const DEFAULT_WINDOW_MINUTES = 10;
export const WINDOW_MINUTES_MIN = 1;
export const WINDOW_MINUTES_MAX = 120;
export const WINDOW_MINUTES_STEP = 1;

function readWindowMinutes(): number {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY_WINDOW_MINUTES) : null;
    if (!raw) return DEFAULT_WINDOW_MINUTES;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < WINDOW_MINUTES_MIN) return DEFAULT_WINDOW_MINUTES;
    return Math.min(Math.max(Math.round(n), WINDOW_MINUTES_MIN), WINDOW_MINUTES_MAX);
  } catch {
    return DEFAULT_WINDOW_MINUTES;
  }
}

export const useSituationStore = create<SituationStore>((set, get) => ({
  rawSituations: [],
  situations: [],
  loading: false,
  error: null,
  queryTimeMs: null,
  freqSummary: null,
  gridStatus: null,
  configHash: null,
  configSource: null,
  params: {
    start: _DEFAULT_WINDOW.start,
    end: _DEFAULT_WINDOW.end,
  },
  classifications: {},
  scanStartedAt: null,
  scanEstimateMs: null,
  rollingDurationMs: readRollingDuration(),
  detectorConfig: null,
  detectorDraft: {},
  detectorDirty: false,
  detectorSaving: false,
  detectorComparison: null,
  maxAlarmRows: readMaxAlarmRows(),
  maxScadaRows: readMaxScadaRows(),

  setMaxAlarmRows: (n) => {
    const clamped = Math.min(Math.max(Math.round(n), INPUT_ROW_CAP_MIN), INPUT_ROW_CAP_MAX);
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY_MAX_ALARM, String(clamped));
      }
    } catch {
      /* localStorage disabled; in-memory value still applies. */
    }
    set({ maxAlarmRows: clamped });
  },

  setMaxScadaRows: (n) => {
    const clamped = Math.min(Math.max(Math.round(n), INPUT_ROW_CAP_MIN), INPUT_ROW_CAP_MAX);
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY_MAX_SCADA, String(clamped));
      }
    } catch {
      /* localStorage disabled; in-memory value still applies. */
    }
    set({ maxScadaRows: clamped });
  },

  windowMinutes: readWindowMinutes(),

  setWindowMinutes: (n) => {
    const clamped = Math.min(Math.max(Math.round(n), WINDOW_MINUTES_MIN), WINDOW_MINUTES_MAX);
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY_WINDOW_MINUTES, String(clamped));
      }
    } catch {
      /* localStorage disabled; in-memory value still applies. */
    }
    set({ windowMinutes: clamped });
  },

  setParams: (partial) =>
    set((s) => ({ params: { ...s.params, ...partial } })),

  fetchSituations: async () => {
    if (IS_KIOSK) return;
    /* Prime the progress UI: stamp the start time and freeze the current
       rolling-average duration as the estimate. We snapshot the estimate
       at scan-start so the ETA does not jitter mid-scan as future scans
       update the average. */
    const startedAt = Date.now();
    const estimate = get().rollingDurationMs;
    set({
      loading: true,
      error: null,
      rawSituations: [],
      situations: [],
      classifications: {},
      queryTimeMs: null,
      freqSummary: null,
      gridStatus: null,
      configHash: null,
      configSource: null,
      scanStartedAt: startedAt,
      scanEstimateMs: estimate,
    });
    try {
      // Streaming path. Provisional situations land within ~5-15s on
      // a 2-day window; final records patch in place as enrichment
      // completes. Index map keyed by situation_id so the patch is O(1)
      // per record and the existing render order is preserved.
      const collected: SituationRecord[] = [];
      const idIndex = new Map<string, number>();
      let firstFrameAt = 0;
      let finalCount = 0;
      let configHash: string | null = null;
      let configSource: "default" | "saved" | "preview" | null = null;
      let freqSummary: FreqSummary | null = null;
      let streamError: string | null = null;

      const commit = () => {
        // Snapshot the accumulating array so React reconciler sees a
        // new reference each render — Zustand otherwise short-circuits.
        const snap = collected.slice();
        set({ rawSituations: snap, situations: snap });
      };

      await streamSituations(
        {
          ...get().params,
          max_alarm_rows: get().maxAlarmRows,
          max_scada_rows: get().maxScadaRows,
          window_minutes: get().windowMinutes,
        },
        {
          onStart: ({ config_hash, config_source }) => {
            configHash = config_hash;
            configSource = (config_source as typeof configSource) ?? null;
            set({ configHash, configSource });
          },
          onSituationPartial: (sit) => {
            if (!firstFrameAt) firstFrameAt = Date.now();
            const idx = idIndex.get(sit.situation_id);
            if (idx == null) {
              idIndex.set(sit.situation_id, collected.length);
              collected.push(sit);
            } else {
              collected[idx] = sit;
            }
            commit();
          },
          onSituation: (sit) => {
            // Final enriched record. Patch in place by situation_id.
            const idx = idIndex.get(sit.situation_id);
            if (idx == null) {
              idIndex.set(sit.situation_id, collected.length);
              collected.push(sit);
            } else {
              collected[idx] = sit;
            }
            commit();
          },
          onFreqSummary: ({ freq_summary }) => {
            freqSummary = freq_summary;
            set({ freqSummary });
          },
          onDone: ({ count, config_hash }) => {
            finalCount = count;
            if (!configHash) configHash = config_hash;
          },
          onError: (detail) => {
            streamError = detail;
          },
        },
      );

      const actualMs = Date.now() - startedAt;
      const prev = get().rollingDurationMs;
      const blended = Math.round(prev * (1 - EWMA_ALPHA) + actualMs * EWMA_ALPHA);
      try {
        if (typeof window !== "undefined") {
          window.localStorage.setItem(STORAGE_KEY_DURATION, String(blended));
        }
      } catch {
        /* localStorage may be disabled; in-memory value still updates below. */
      }
      set({
        queryTimeMs: actualMs,
        configHash,
        configSource,
        freqSummary,
        loading: false,
        error: streamError,
        scanStartedAt: null,
        scanEstimateMs: null,
        rollingDurationMs: blended,
      });
      // finalCount is informational; the rendered list already reflects it.
      void finalCount;
    } catch (err) {
      set({
        error: (err as Error).message,
        loading: false,
        scanStartedAt: null,
        scanEstimateMs: null,
      });
    }
  },

  loadDetectorConfig: async () => {
    if (IS_KIOSK) return;
    const config = await getDetectorConfig();
    set((state) => ({
      detectorConfig: config,
      detectorDraft: state.detectorDirty ? state.detectorDraft : config.patch ?? {},
      detectorDirty: state.detectorDirty,
    }));
  },

  setDetectorDraft: (partial) =>
    set((s) => ({
      detectorDraft: mergeDetectorDraft(s.detectorDraft, partial),
      detectorDirty: true,
    })),

  runDetectorComparison: async () => {
    if (IS_KIOSK) return;
    const { params, detectorDraft } = get();
    set({ loading: true, error: null });
    try {
      const current = await scanSituations({ ...params });
      const draft = await scanSituations({ ...params, preview_patch: detectorDraft });
      const currentTop = current.situations[0];
      const draftTop = draft.situations[0];
      const currentLabel = currentTop ? `${currentTop.station} ${currentTop.severity}` : "not detected";
      const draftLabel = draftTop ? `${draftTop.station} ${draftTop.severity}` : "not detected";
      set({
        detectorComparison: {
          matched: draftTop ? 1 : 0,
          missed: draftTop ? 0 : 1,
          severity_mismatches: currentTop?.severity !== draftTop?.severity ? 1 : 0,
          rows: [{ id: "active-scan", label: params.station || "Active scan window", current: currentLabel, draft: draftLabel }],
        },
        loading: false,
      });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  saveDetectorConfig: async () => {
    if (IS_KIOSK) return;
    set({ detectorSaving: true, error: null });
    try {
      const config = await saveDetectorConfigApi(get().detectorDraft);
      set({ detectorConfig: config, detectorDraft: config.patch ?? {}, detectorDirty: false, detectorSaving: false });
    } catch (err) {
      set({ error: (err as Error).message, detectorSaving: false });
    }
  },

  resetDetectorConfig: async () => {
    if (IS_KIOSK) return;
    set({ detectorSaving: true, error: null });
    try {
      const config = await resetDetectorConfigApi();
      set({ detectorConfig: config, detectorDraft: config.patch ?? {}, detectorDirty: false, detectorSaving: false });
    } catch (err) {
      set({ error: (err as Error).message, detectorSaving: false });
    }
  },

  previewDetectorConfig: async () => {
    if (IS_KIOSK) return;
    const startedAt = Date.now();
    set({ loading: true, error: null, scanStartedAt: startedAt, scanEstimateMs: get().rollingDurationMs });
    try {
      const response = await scanSituations({
        ...get().params,
        max_alarm_rows: get().maxAlarmRows,
        max_scada_rows: get().maxScadaRows,
        preview_patch: get().detectorDraft,
      });
      set({
        rawSituations: response.situations,
        situations: response.situations,
        queryTimeMs: response.query_time_ms,
        freqSummary: response.freq_summary ?? null,
        gridStatus: response.grid_status ?? null,
        configHash: response.config_hash ?? response.situations[0]?.config_hash ?? null,
        configSource: response.config_source ?? "preview",
        loading: false,
        scanStartedAt: null,
        scanEstimateMs: null,
      });
    } catch (err) {
      set({ error: (err as Error).message, loading: false, scanStartedAt: null, scanEstimateMs: null });
    }
  },

  buildInvestigatePrompt: (sit) => {
    /* Parse signal counts for concise display. */
    const alarmSigs = (() => { try { return JSON.parse(sit.alarm_signals); } catch { return {}; } })();
    const scadaSigs = (() => { try { return JSON.parse(sit.scada_signals); } catch { return {}; } })();
    const alarmStr = Object.entries(alarmSigs).map(([k, v]) => `${k}=${v}`).join(", ") || "none";
    const scadaStr = Object.entries(scadaSigs).map(([k, v]) => `${k}=${v}`).join(", ") || "none";

    /* Lean prompt: station, time range, signal counts, and a small set
       of detector-derived hypothesis seeds (severity, compound
       patterns, MW impact, registry-confirmed unit-trip rollup).
       Verbose prompts cause excessive tool calls and timeouts; keep
       each line terse. */
    const lines = [
      `Investigate ${sit.station}, ${sit.window_start} to ${sit.window_end}.`,
      `Alarm signals: ${alarmStr}.`,
      `SCADA signals: ${scadaStr}.`,
    ];

    /* Severity is the detector's own banding — useful as a priority
       cue without reading the score. */
    if (sit.severity) {
      lines.push(`Detector severity: ${sit.severity} (score ${sit.total_score}).`);
    }

    /* Compound patterns are the detector's pre-computed hypothesis
       hints (e.g. unit_unplanned_offline, generator_motoring). The
       investigator can use these to skip rediscovery. */
    if (sit.patterns && sit.patterns.length > 0) {
      lines.push(`Compound patterns matched: ${sit.patterns}.`);
    }

    /* Add MW impact context when available. */
    if (sit.total_mw_lost > 0 && sit.impact_region_pct > 0) {
      lines.push(`MW impact: ${sit.total_mw_lost} MW lost (${sit.impact_region_pct}% of ${sit.station_region} live generation).`);
    }

    /* Registry-confirmed unit-trip rollup — only present when the
       unit_unplanned_offline pattern matched. Counts are the
       corroborating-alarm tallies (CB / MWCC / KV-EMER) the detector
       already verified, so the agent does not need to re-derive. */
    const offlineSummary = sit.unit_offline_summary;
    const tripCount = offlineSummary?.trip_count ?? 0;
    if (tripCount > 0) {
      const cb = offlineSummary?.cb_count ?? 0;
      const mwcc = offlineSummary?.mwcc_count ?? 0;
      const kv = offlineSummary?.kv_emer_count ?? 0;
      lines.push(`Registry-confirmed unit trips: ${tripCount} (CB=${cb}, MWCC=${mwcc}, KV-EMER=${kv}).`);
    }

    /* Advisory NER 4.2.3 classifier prior — included ONLY when the
       background classifier has returned a complete result for this
       situation. Framed as a hypothesis the agent must test, never as
       a finding to accept, to prevent the investigator from anchoring
       on the classifier's verdict and rationalising it instead of
       independently investigating. Omitted entirely when status is
       idle / loading / error or when rationale is empty. */
    const cls = get().classifications[sit.situation_id];
    if (
      cls &&
      cls.status === "ready" &&
      cls.classification &&
      cls.rationale &&
      cls.rationale.trim().length > 0 &&
      !cls.error
    ) {
      /* Match the UI labels in CLASS_LABEL (SituationCard.tsx) so the
         operator and the agent see the same string. */
      const VERDICT_LABEL: Record<SituationClassification, string> = {
        credible: "CREDIBLE",
        non_credible: "NON-CREDIBLE",
        non_event: "NON-EVENT",
      };
      const verdict = VERDICT_LABEL[cls.classification];
      const ner = cls.ner_citation ? ` (${cls.ner_citation})` : "";
      lines.push(
        "",
        "ADVISORY HYPOTHESIS ONLY — REQUIRES STRICT CONFIRMATION OR REFUTATION:",
        `Prior classifier verdict: ${verdict}${ner} — ${cls.rationale.trim()}`,
        "Treat this as a hypothesis to test, not a finding to accept. Confirm or refute it with independent evidence from your investigation.",
      );
    }

    return lines.join("\n");
  },

  /* Fire the background NER 4.2.3 classifier for a single situation.
     The store keeps a per-situation status so the SituationCard can
     render a spinner while the call is in flight, a coloured pill once
     ready, and a retry hint on error. The backend caches by
     situation_id so a re-mount of the same card is essentially free. */
  classifySituation: async (sit) => {
    if (IS_KIOSK) return;
    const sid = sit.situation_id;
    const cur = get().classifications[sid];
    /* Skip if already in flight or completed — idempotent. */
    if (cur && (cur.status === "loading" || cur.status === "ready")) return;

    set((s) => ({
      classifications: { ...s.classifications, [sid]: { status: "loading" } },
    }));

    try {
      const res: ClassificationResult = await classifySituation({
        situation_id: sid,
        severity: sit.severity,
        station: sit.station,
        station_region: sit.station_region,
        total_score: sit.total_score,
        total_mw_lost: sit.total_mw_lost,
        alarm_signals: sit.alarm_signals,
        scada_signals: sit.scada_signals,
        affected_equipment: sit.affected_equipment,
        window_start: sit.window_start,
        window_end: sit.window_end,
      });
      set((s) => ({
        classifications: {
          ...s.classifications,
          [sid]: {
            status: "ready",
            classification: res.classification,
            /* Carry the classifier's 0–100 self-assessed certainty
               through to the card. Defaults to 50 server-side if the
               model omits the field, so this is always a number once
               the backend says ready. */
            confidence: res.confidence,
            ner_citation: res.ner_citation,
            rationale: res.rationale,
          },
        },
      }));
    } catch (err) {
      set((s) => ({
        classifications: {
          ...s.classifications,
          [sid]: {
            status: "error",
            error: (err as Error).message,
          },
        },
      }));
    }
  },
}));

/* ── Cluster-level Investigate prompt helpers ─────────────────────────
 *
 * The detector emits per-station per-window SituationRecord rows. A single
 * persistent incident with overlapping sliding windows therefore arrives
 * as N near-identical records sharing `(station, severity)`. The cluster
 * parent-card rendering path that consumed these helpers was retired
 * (Undertaker 2026-05-24); the only surviving consumer is
 * `buildClusterInvestigatePrompt`, which folds the same per-cluster
 * rollups (representative equipment, deduped pattern union) into the
 * agent prompt body.
 *
 * `buildClusterInvestigatePrompt` is a pure helper: it reads the
 * advisory classifier-prior block from a snapshot of the current
 * `classifications` map via `useSituationStore.getState()`, mirroring
 * the single-situation `buildInvestigatePrompt` path. Per CHAOS-035..057
 * the agent-integrity rules live in the foundation prompt, so the
 * client-side cluster prompt does NOT re-state them.
 */

function parseAffectedEquipmentForCluster(raw: string | null | undefined) {
  /* Defensive parse re-exported through `lib/situationRecord`. The
     prompt builder previously inlined its own `JSON.parse(...) catch`;
     consolidating onto the shared helper means malformed records,
     hand-edited fixtures, and partial SSE frames are all handled the
     same way the cards + panels handle them. */
  return parseAffectedEquipment(raw);
}

function deriveRepresentativeEquipment(children: SituationRecord[]): string | undefined {
  /* Per Couturier audit 2026-05-23 §"representative_equipment
     refinement": only surface an equipment_id at the cluster-header
     level when EVERY child has exactly one affected_equipment entry
     AND all entries share the same equipment_id. Otherwise the header
     falls back to station-only — equipment is not part of the cluster
     key, and we do not want to mis-label the cluster with one of the
     overlapping equipment ids when sibling windows touched different
     equipment. */
  if (children.length === 0) return undefined;
  let candidate: string | undefined;
  for (const child of children) {
    const eq = parseAffectedEquipmentForCluster(child.affected_equipment);
    if (eq.length !== 1) return undefined;
    const id = eq[0]?.equipment_id;
    if (!id) return undefined;
    if (candidate === undefined) {
      candidate = id;
    } else if (candidate !== id) {
      return undefined;
    }
  }
  return candidate;
}

function unionPatterns(children: SituationRecord[]): string[] {
  /* Tokenise each child's CSV patterns string, preserving first-seen
     order across the chronological child list. Empty / whitespace-only
     entries are dropped. */
  const seen = new Set<string>();
  const out: string[] = [];
  for (const child of children) {
    const tokens = (child.patterns ?? "").split(",").map((p) => p.trim()).filter(Boolean);
    for (const t of tokens) {
      if (!seen.has(t)) {
        seen.add(t);
        out.push(t);
      }
    }
  }
  return out;
}

/* Operator label mapping for the advisory verdict — kept in sync with
   the CLASS_LABEL map in SituationCard.tsx so the cluster prompt reads
   the same vocabulary the operator sees on screen. */
const CLUSTER_VERDICT_LABEL: Record<SituationClassification, string> = {
  credible: "CREDIBLE",
  non_credible: "NON-CREDIBLE",
  non_event: "NON-EVENT",
};

function formatSignalCounts(raw: string): string {
  /* `parseSignalCounts` rejects array payloads via its shape guard so
     a hand-edited `"[1,2]"` cannot render as `0=1, 1=2`. Empty result
     → "none" (matches the prior behaviour). */
  const obj = parseSignalCounts(raw);
  const entries = Object.entries(obj);
  if (entries.length === 0) return "none";
  return entries.map(([k, v]) => `${k}=${v}`).join(", ");
}

interface ReadyVerdict {
  sit: SituationRecord;
  verdict: SituationClassification;
  ner_citation?: string | null;
  rationale: string;
}

function collectReadyVerdicts(children: SituationRecord[]): ReadyVerdict[] {
  const map = useSituationStore.getState().classifications;
  const out: ReadyVerdict[] = [];
  for (const sit of children) {
    const cls = map[sit.situation_id];
    if (
      cls &&
      cls.status === "ready" &&
      cls.classification &&
      cls.rationale &&
      cls.rationale.trim().length > 0 &&
      !cls.error
    ) {
      out.push({
        sit,
        verdict: cls.classification,
        ner_citation: cls.ner_citation,
        rationale: cls.rationale.trim(),
      });
    }
  }
  return out;
}

function formatWindowRange(start: string, end: string): string {
  /* `Window HH:MM→HH:MM` compact form for the advisory cluster block.
     Delegates to `lib/situationRecord.hhmm` so the slicing rule
     (handles both space and `T` separators, returns original on no
     delimiter) lives in one place. */
  return `Window ${hhmmSlice(start)}→${hhmmSlice(end)}`;
}

/**
 * Build a natural-language Investigate prompt for a cluster of situation
 * records (one physical incident sliced into N detector windows).
 *
 * Output shape (per Couturier audit 2026-05-23 R2):
 *
 *   Investigate {representative_equipment} at {station} between {min_start} and {max_end}.
 *   Detected situations (chronological, {N} total):
 *   1. {ws} → {we} — severity {sev} — score {s} — alarms {alarm_str} — SCADA {scada_str}
 *   ...
 *
 *   Detector severity (cluster): {severity} (max score {max_score} across {N} windows).
 *   Compound patterns matched (union across cluster): {patterns_union}.
 *   MW impact (aggregate): {sum_mw_lost} MW lost peak.
 *
 *   [Advisory classifier-prior block — only when ≥1 child has a ready
 *    classifier verdict with a non-empty rationale.]
 *
 * Returns "" when called with an empty array (defensive — the panel
 * never invokes the cluster path without children, but a wrapper could).
 */
export function buildClusterInvestigatePrompt(situations: SituationRecord[]): string {
  if (!situations || situations.length === 0) return "";
  /* Ensure chronological order regardless of caller; the panel passes
     cluster.children which is already sorted, but tests may invoke
     this directly with raw arrays. */
  const children = [...situations].sort((a, b) => a.window_start.localeCompare(b.window_start));
  const repEq = deriveRepresentativeEquipment(children);
  const first = children[0];
  const station = first.station;
  const severity = first.severity;
  const minStart = children.reduce((m, c) => (c.window_start.localeCompare(m) < 0 ? c.window_start : m), first.window_start);
  const maxEnd = children.reduce((m, c) => (c.window_end.localeCompare(m) > 0 ? c.window_end : m), first.window_end);
  const maxScore = children.reduce((m, c) => (c.total_score > m ? c.total_score : m), first.total_score);
  const sumMwLost = children.reduce((s, c) => s + (c.total_mw_lost ?? 0), 0);
  const patternsUnion = unionPatterns(children);
  const n = children.length;

  /* Lead line: `Investigate {equipment} at {station} ...` when we have
     a representative equipment id; otherwise drop the prefix and lead
     with the station directly (matches audit doc R2 sample). */
  const leadSubject = repEq ? `${repEq} at ${station}` : station;

  const lines: string[] = [];
  lines.push(`Investigate ${leadSubject} between ${minStart} and ${maxEnd}.`);
  lines.push(`Detected situations (chronological, ${n} total):`);
  children.forEach((c, i) => {
    const alarmStr = formatSignalCounts(c.alarm_signals);
    const scadaStr = formatSignalCounts(c.scada_signals);
    lines.push(
      `${i + 1}. ${c.window_start} → ${c.window_end} — severity ${c.severity} — score ${c.total_score} — alarms ${alarmStr} — SCADA ${scadaStr}`,
    );
  });
  lines.push("");
  lines.push(`Detector severity (cluster): ${severity} (max score ${maxScore} across ${n} window${n === 1 ? "" : "s"}).`);
  if (patternsUnion.length > 0) {
    lines.push(`Compound patterns matched (union across cluster): ${patternsUnion.join(", ")}.`);
  }
  if (sumMwLost > 0) {
    lines.push(`MW impact (aggregate): ${Math.round(sumMwLost)} MW lost peak.`);
  }

  /* Advisory NER 4.2.3 classifier prior — aggregated across cluster
     members. Mirrors the single-situation framing in
     buildInvestigatePrompt but adds:
       - unanimous-suffix when every ready verdict agrees,
       - per-window verdict enumeration + an explicit "disagree" line
         when ready verdicts disagree, so the agent treats each as an
         independent hypothesis to confirm or refute.
     0 ready verdicts → block omitted entirely (matches current single
     -situation behaviour). The CHAOS-035..057 hardening lives in the
     foundation prompt; this client-side block does NOT restate those
     rules. */
  const ready = collectReadyVerdicts(children);
  if (ready.length > 0) {
    lines.push("");
    lines.push("ADVISORY HYPOTHESIS ONLY — REQUIRES STRICT CONFIRMATION OR REFUTATION:");
    const verdicts = new Set(ready.map((r) => r.verdict));
    if (ready.length === 1) {
      const r = ready[0];
      const ner = r.ner_citation ? ` (${r.ner_citation})` : "";
      lines.push(`Prior classifier verdict: ${CLUSTER_VERDICT_LABEL[r.verdict]}${ner} — ${r.rationale}`);
    } else if (verdicts.size === 1) {
      /* Unanimous across ≥ 2 ready children. Lead with a single
         verdict line and enumerate rationales beneath so the agent
         sees every supporting rationale without losing the headline. */
      const v = ready[0].verdict;
      const ner = ready[0].ner_citation ? ` (${ready[0].ner_citation})` : "";
      lines.push(
        `Prior classifier verdict: ${CLUSTER_VERDICT_LABEL[v]}${ner} (unanimous across ${ready.length} cluster member${ready.length === 1 ? "" : "s"}).`,
      );
      for (const r of ready) {
        lines.push(`- ${formatWindowRange(r.sit.window_start, r.sit.window_end)}: ${r.rationale}`);
      }
    } else {
      lines.push("Prior classifier verdicts across cluster members:");
      for (const r of ready) {
        const ner = r.ner_citation ? ` (${r.ner_citation})` : "";
        lines.push(
          `- ${formatWindowRange(r.sit.window_start, r.sit.window_end)}: ${CLUSTER_VERDICT_LABEL[r.verdict]}${ner} — ${r.rationale}`,
        );
      }
      lines.push(
        "Classifier verdicts disagree across cluster — treat each as an independent hypothesis to test against the others.",
      );
    }
    lines.push(
      "Treat these as hypotheses to test, not findings to accept. Confirm or refute with independent evidence from your investigation.",
    );
  }

  /* Deduped affected-equipment roster — appended to every Investigate
     prompt (single-row, cluster, station-level) per operator brief
     2026-05-24. Collects `equipment_id` across every child via the
     shared `parseAffectedEquipmentForCluster` helper, dedupes case-
     sensitively, sorts alphabetically (operators scan by station
     prefix), and emits a bulleted list under a fixed heading so the
     agent can lean on a known structure when targeting tool calls. */
  const equipmentSet = new Set<string>();
  for (const c of children) {
    const eq = parseAffectedEquipmentForCluster(c.affected_equipment);
    for (const row of eq) {
      const id = row?.equipment_id?.trim();
      if (id) equipmentSet.add(id);
    }
  }
  if (equipmentSet.size > 0) {
    const sorted = Array.from(equipmentSet).sort((a, b) => a.localeCompare(b));
    lines.push("");
    lines.push("Affected equipment:");
    for (const id of sorted) {
      lines.push(`* ${id}`);
    }
  }

  return lines.join("\n");
}

/**
 * Station-level investigate prompt — fired by the magnifier-plus
 * button on a station-group header (2026-05-24). Reuses the cluster
 * prompt body so the agent sees the same chronological enumeration,
 * compound-pattern union, MW aggregate, and advisory-classifier
 * block, but replaces the opening line with a station-framed lead:
 *
 *   "These situations are happening at {station}. Investigate..."
 *
 * The cluster builder's normal lead is "Investigate {equipment} at
 * {station}..." which is correct for a single-incident cluster but
 * wrong for a multi-severity, multi-equipment station sweep where
 * the operator's intent is "look at everything happening here".
 */
export function buildStationInvestigatePrompt(
  station: string,
  situations: SituationRecord[],
): string {
  if (!situations || situations.length === 0) return "";
  const body = buildClusterInvestigatePrompt(situations);
  const minStart = situations.reduce(
    (m, c) => (c.window_start.localeCompare(m) < 0 ? c.window_start : m),
    situations[0].window_start,
  );
  const maxEnd = situations.reduce(
    (m, c) => (c.window_end.localeCompare(m) > 0 ? c.window_end : m),
    situations[0].window_end,
  );
  const lead = `These situations are happening at ${station} between ${minStart} and ${maxEnd}. Investigate.`;
  /* Replace just the first line of the cluster prompt so every
     downstream block (chronological list, patterns, MW, classifier
     prior) reads identically without re-implementing it here. */
  const nl = body.indexOf("\n");
  return nl < 0 ? lead : lead + body.slice(nl);
}
