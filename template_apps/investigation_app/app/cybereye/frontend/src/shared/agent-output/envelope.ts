import { extractDuplicate, extractError, extractRefusal, projectObjectRow } from "@agentcraft/modular-agents";
import type { QueryResult } from "../types";

export interface ScopeEntry {
  label: string;
  value: string;
}

export interface SignalChip {
  label: string;
  value: string;
  tone: "neutral" | "good" | "warn" | "bad";
}

export interface SituationBrief {
  situation_id: string;
  host: string;
  principal: string;
  severity: string;
  confidence: string;
  detector_count: number;
  rule_ids: string[];
}

export interface ScanBrief {
  window_start: string;
  window_end: string;
  situations: SituationBrief[];
  situation_count: number;
  critical: number;
  high: number;
  evidence_rows: number;
  elapsed_ms: number;
  rules_run: number;
  rules_hit: number;
}

interface Common {
  tool: string;
  category: string;
  scope: ScopeEntry[];
  fallback: boolean;
  historicalReplay: boolean;
}

export type ToolRenderModel =
  | (Common & { kind: "situations"; scan: ScanBrief })
  | (Common & {
      kind: "table";
      columns: string[];
      rows: unknown[][];
      rowCount: number;
      maxRows: number | null;
      truncated: boolean;
      elapsedMs: number | null;
    })
  | (Common & { kind: "empty"; reason: string })
  | { kind: "refusal"; tool: string; refusal: NonNullable<ReturnType<typeof extractRefusal>> }
  | { kind: "duplicate"; tool: string; duplicate: NonNullable<ReturnType<typeof extractDuplicate>> }
  | { kind: "error"; tool: string; errorCode: string; message: string }
  | { kind: "raw"; tool: string; text: string };

const SCOPE_SKIP = new Set(["row_count", "max_rows", "situation_count"]);

/** Category label + one-line framing. Names the tool contract, never the evidence claim. */
export const CATEGORY_META: Record<string, { title: string; note: string }> = {
  orientation: { title: "Deterministic scan", note: "Ranked historical situation envelopes from the rule registry." },
  cited_evidence: { title: "Cited rows", note: "Bounded EventsUnified rows referenced by one situation envelope." },
  situation_evidence: { title: "Situation evidence", note: "Bounded rows retrieved for one situation envelope." },
  not_found: { title: "No matching situation", note: "The requested situation id was not present in this replay window." },
  empty_evidence: { title: "No sampled evidence", note: "The situation qualified but returned no sampled resource_id values." },
  host_activity: { title: "Host activity profile", note: "Categorical product and event-type composition for one host." },
  authentication: { title: "Authentication activity", note: "Windows events 4624, 4625, and 4648 grouped for one host." },
  privileged_session: { title: "Privileged session records", note: "CyberArk session records; titles show what was displayed." },
  dns: { title: "DNS activity", note: "Query-name and cadence composition for one source address." },
  raw_kql_fallback: { title: "Raw KQL fallback", note: "Model-authored KQL outside the purpose-built tool set." },
  mitre_attack: { title: "MITRE ATT&CK knowledge", note: "Advisory ATT&CK material from the pinned bundle. A match characterises a pattern; it does not prove one." },
  mitre_attack_unavailable: { title: "MITRE ATT&CK unavailable", note: "The knowledge index could not be reached. There is no local copy to fall back to." },
  event_timeline: { title: "Event timeline", note: "Per-minute event counts by recovered event type across the selected replay window." },
  product_composition: { title: "Product composition", note: "Event volume per source product across the whole export." },
  authentication_mix: { title: "Authentication mix", note: "Windows security event id composition across the whole export." },
  firewall_baseline: { title: "Firewall baseline", note: "Daily flow volume and blocked-flow count; the corpus baseline, not a targeted response." },
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function text(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const num = (value: unknown, fallback: number): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

function scopeEntries(scope: unknown): ScopeEntry[] {
  if (!isRecord(scope)) return [];
  return Object.entries(scope)
    .filter(([key, value]) => !SCOPE_SKIP.has(key) && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({ label: key.replace(/_/g, " "), value: text(value) }));
}

function alignRows(columns: string[], rows: unknown[]): unknown[][] {
  return rows.map((row) =>
    Array.isArray(row)
      ? columns.map((_, index) => row[index])
      : isRecord(row) ? projectObjectRow(columns, row) : columns.map(() => undefined),
  );
}

function scanBrief(result: Record<string, unknown>): ScanBrief {
  const raw = Array.isArray(result.situations) ? result.situations : [];
  const summary = isRecord(result.summary) ? result.summary : {};
  const executions = Array.isArray(result.rule_executions) ? result.rule_executions : [];
  return {
    window_start: text(result.window_start),
    window_end: text(result.window_end),
    situations: raw.filter(isRecord).map((item) => ({
      situation_id: text(item.situation_id),
      host: text(item.host),
      principal: text(item.principal),
      severity: text(item.severity),
      confidence: text(item.confidence),
      detector_count: num(item.detector_count, 0),
      rule_ids: (Array.isArray(item.patterns) ? item.patterns : [])
        .filter(isRecord)
        .map((pattern) => text(pattern.rule_id)),
    })),
    situation_count: num(summary.situations, raw.length),
    critical: num(summary.critical, 0),
    high: num(summary.high, 0),
    evidence_rows: num(summary.evidence_rows, 0),
    elapsed_ms: num(summary.elapsed_ms, 0),
    rules_run: executions.length,
    rules_hit: executions.filter((item) => isRecord(item) && num(item.hit_count, 0) > 0).length,
  };
}

function truncate(value: string): string {
  return value.length > 6000 ? `${value.slice(0, 6000)}\n… result truncated in UI` : value;
}

/** Parse an agent tool-result envelope exactly once, at the boundary. */
export function parseToolEnvelope(value: unknown): ToolRenderModel {
  if (!isRecord(value)) return { kind: "raw", tool: "tool", text: truncate(JSON.stringify(value, null, 2) ?? "—") };

  const tool = typeof value.tool === "string" ? value.tool : "tool";

  const refusal = extractRefusal(value);
  if (refusal) return { kind: "refusal", tool, refusal };
  const duplicate = extractDuplicate(value);
  if (duplicate) return { kind: "duplicate", tool, duplicate };
  const error = extractError(value);
  if (error !== null) {
    return { kind: "error", tool, errorCode: typeof value.error === "string" && value.error ? value.error : "error", message: error };
  }

  const category = typeof value.category === "string" ? value.category : "";
  const fallback = value.fallback === true;
  const historicalReplay = value.historical_replay === true;
  const scope = scopeEntries(value.scope);

  if (category === "orientation" && isRecord(value.result)) {
    return { kind: "situations", tool, category, scope, fallback, historicalReplay, scan: scanBrief(value.result) };
  }
  if (Array.isArray(value.situations)) {
    return { kind: "situations", tool, category: category || "orientation", scope, fallback, historicalReplay, scan: scanBrief(value) };
  }

  if (Array.isArray(value.columns) && Array.isArray(value.rows)) {
    const columns = value.columns.map(String);
    const rows = alignRows(columns, value.rows);
    const scopeRecord = isRecord(value.scope) ? value.scope : {};
    if (!columns.length || !rows.length) {
      return {
        kind: "empty", tool, category: category || "empty_evidence", scope, fallback, historicalReplay,
        reason: CATEGORY_META[category]?.note ?? "The bounded query returned no rows for this scope.",
      };
    }
    return {
      kind: "table", tool, category, scope, fallback, historicalReplay, columns, rows,
      rowCount: num(scopeRecord.row_count, num(value.row_count, rows.length)),
      maxRows: typeof scopeRecord.max_rows === "number" ? scopeRecord.max_rows : null,
      truncated: value.truncated === true,
      elapsedMs: typeof value.elapsed_ms === "number" ? value.elapsed_ms : null,
    };
  }

  return { kind: "raw", tool, text: truncate(JSON.stringify(value, null, 2)) };
}

/** Adapt a direct /api/cyber/query or /api/cyber/evidence response to the same render model. */
export function fromQueryResult(
  tool: string,
  category: string,
  scope: Record<string, unknown>,
  result: QueryResult,
): ToolRenderModel {
  const columns = result.columns.map(String);
  const entries = scopeEntries(scope);
  if (!columns.length || !result.rows.length) {
    return {
      kind: "empty", tool, category, scope: entries, fallback: false, historicalReplay: true,
      reason: "The bounded query returned no rows for this scope.",
    };
  }
  return {
    kind: "table", tool, category, scope: entries, fallback: false, historicalReplay: true,
    columns, rows: alignRows(columns, result.rows),
    rowCount: result.row_count, maxRows: result.max_rows,
    truncated: result.truncated, elapsedMs: result.elapsed_ms,
  };
}

/** Signal chips are computed from the payload, not authored per tool. */
export function signalChips(model: ToolRenderModel): SignalChip[] {
  if (model.kind === "situations") {
    const chips: SignalChip[] = [
      { label: "situations", value: String(model.scan.situation_count), tone: "neutral" },
      { label: "critical", value: String(model.scan.critical), tone: model.scan.critical > 0 ? "bad" : "neutral" },
      { label: "evidence representations", value: String(model.scan.evidence_rows), tone: "neutral" },
    ];
    if (model.scan.rules_run > 0) {
      chips.push({ label: "rules hit", value: `${model.scan.rules_hit}/${model.scan.rules_run}`, tone: "good" });
    }
    chips.push({ label: "scan time", value: `${model.scan.elapsed_ms} ms`, tone: "neutral" });
    return chips;
  }
  if (model.kind === "table") {
    const chips: SignalChip[] = [
      { label: "rows returned", value: String(model.rowCount), tone: "neutral" },
      { label: "columns", value: String(model.columns.length), tone: "neutral" },
    ];
    if (model.maxRows !== null) chips.push({ label: "row cap", value: String(model.maxRows), tone: "neutral" });
    if (model.elapsedMs !== null) chips.push({ label: "query time", value: `${model.elapsedMs} ms`, tone: "neutral" });
    if (model.truncated) chips.push({ label: "truncated", value: "at row cap", tone: "warn" });
    return chips;
  }
  if (model.kind === "empty") return [{ label: "rows returned", value: "0", tone: "warn" }];
  return [];
}
