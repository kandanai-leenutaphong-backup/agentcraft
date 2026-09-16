/**
 * Audit API — session-audit run, interrupt, list, get + SSE parser.
 *
 * Mirrors the chat SSE parser ([chatApi.ts](./chatApi.ts)) so the
 * Session Audit panel reuses the same event vocabulary the chat
 * stream uses (`token`, `tool_call_start/delta/end`, `tool_result`)
 * plus three audit-only events: `audit_started`, `audit_report`, and
 * the existing terminal `done` / `error` / `keepalive`.
 *
 * Wire contract documented in
 * [specs/session_audit.md](../../../../specs/session_audit.md).
 */

import { BASE, authHeaders, extractErrorMessage, handleResponse } from "./client";

// ── Shapes ────────────────────────────────────────────────────────────

export type AuditBand = "excellent" | "strong" | "adequate" | "weak" | "poor";
export type AuditConfidence = "high" | "medium" | "low";
export type AuditImprovementCategory =
  | "prompt"
  | "tooling"
  | "data"
  | "process"
  | "other";

export interface AuditRubricItem {
  dimension:
    | "evidence_completeness"
    | "topology_coverage"
    | "hypothesis_quality"
    | "action_grounding"
    | "summary_quality"
    | "grounding";
  score: 0 | 1 | 2 | 3;
  band: AuditBand;
  note: string;
}

export interface AuditImprovement {
  category: AuditImprovementCategory;
  text: string;
}

export interface AuditReport {
  id: string;
  session_id: string;
  user_oid?: string;
  started_at: string;
  finished_at?: string;
  duration_seconds?: number;
  iteration_count?: number;
  tool_call_count?: number;
  headline: string;
  markdown: string;
  rubric: AuditRubricItem[];
  gaps: string[];
  improvements?: AuditImprovement[];
  confidence: AuditConfidence;
  weighted_score: number;
  score_pct: number;
  band: AuditBand;
  auditor_model?: string;
  context_prompt?: string;
  synthetic?: boolean;
}

export interface AuditSummary {
  id: string;
  session_id: string;
  started_at: string;
  finished_at?: string;
  duration_seconds?: number | null;
  headline: string | null;
  band: AuditBand | null;
  weighted_score: number | null;
  score_pct: number | null;
  confidence: AuditConfidence | null;
  tool_call_count: number | null;
  context_prompt?: string;
  improvement_count?: number;
}

// ── Stream events ─────────────────────────────────────────────────────

export type AuditStreamEvent =
  | { kind: "started"; auditId: string; startedAt: string }
  | { kind: "token"; token: string }
  | { kind: "tool_call_start"; id: string; name: string }
  | { kind: "tool_call_delta"; id: string; argumentsDelta: string }
  | { kind: "tool_call_end"; id: string; name: string; args: Record<string, unknown> }
  | { kind: "tool_result"; id: string; name: string; result: string }
  | { kind: "report"; report: AuditReport }
  | { kind: "error"; message: string }
  | { kind: "done"; persisted: boolean }
  | { kind: "aborted" }
  | { kind: "keepalive" };

export interface AuditCallbacks {
  onEvent: (event: AuditStreamEvent) => void;
}

// ── REST endpoints ────────────────────────────────────────────────────

export async function listAudits(sessionId: string): Promise<AuditSummary[]> {
  const res = await fetch(`${BASE}/audit/${encodeURIComponent(sessionId)}`, {
    headers: await authHeaders(),
  });
  return handleResponse<AuditSummary[]>(res);
}

export async function getAudit(sessionId: string, auditId: string): Promise<AuditReport> {
  const res = await fetch(
    `${BASE}/audit/${encodeURIComponent(sessionId)}/${encodeURIComponent(auditId)}`,
    { headers: await authHeaders() },
  );
  return handleResponse<AuditReport>(res);
}

export async function interruptAudit(sessionId: string): Promise<{ interrupted: boolean }> {
  const res = await fetch(
    `${BASE}/audit/${encodeURIComponent(sessionId)}/interrupt`,
    { method: "POST", headers: await authHeaders() },
  );
  if (!res.ok) {
    if (res.status === 404) return { interrupted: false };
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

// ── SSE drive ─────────────────────────────────────────────────────────

/** Open the audit SSE stream and dispatch events into ``callbacks``. */
export async function streamAudit(
  sessionId: string,
  callbacks: AuditCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${BASE}/audit/${encodeURIComponent(sessionId)}/run`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        ...await authHeaders(),
      },
      signal,
    });
  } catch (err) {
    callbacks.onEvent({ kind: "error", message: (err as Error).message });
    return;
  }

  if (!res.ok) {
    if (res.status === 401) {
      const { handleAuthExpired } = await import("./client");
      handleAuthExpired();
    }
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    callbacks.onEvent({ kind: "error", message: extractErrorMessage(body, `HTTP ${res.status}`) });
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onEvent({ kind: "error", message: "no response body" });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame.trim()) continue;
        let eventType: string | null = null;
        const dataLines: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          }
        }
        const data = dataLines.join("\n");
        if (!eventType) continue;
        let parsed: Record<string, unknown> = {};
        try {
          parsed = data ? JSON.parse(data) : {};
        } catch {
          // Non-JSON payload — skip silently.
          continue;
        }

        switch (eventType) {
          case "audit_started":
            callbacks.onEvent({
              kind: "started",
              auditId: String(parsed.audit_id ?? ""),
              startedAt: String(parsed.started_at ?? ""),
            });
            break;
          case "token":
            callbacks.onEvent({ kind: "token", token: String(parsed.token ?? "") });
            break;
          case "tool_call_start":
            callbacks.onEvent({
              kind: "tool_call_start",
              id: String(parsed.id ?? ""),
              name: String(parsed.name ?? ""),
            });
            break;
          case "tool_call_delta":
            callbacks.onEvent({
              kind: "tool_call_delta",
              id: String(parsed.id ?? ""),
              argumentsDelta: String(parsed.arguments_delta ?? ""),
            });
            break;
          case "tool_call_end":
            callbacks.onEvent({
              kind: "tool_call_end",
              id: String(parsed.id ?? ""),
              name: String(parsed.name ?? ""),
              args: (parsed.arguments as Record<string, unknown>) ?? {},
            });
            break;
          case "tool_result":
            callbacks.onEvent({
              kind: "tool_result",
              id: String(parsed.id ?? ""),
              name: String(parsed.name ?? ""),
              result: String(parsed.result ?? ""),
            });
            break;
          case "audit_report":
            callbacks.onEvent({ kind: "report", report: parsed as unknown as AuditReport });
            break;
          case "error":
            callbacks.onEvent({ kind: "error", message: String(parsed.error ?? parsed.message ?? "error") });
            break;
          case "aborted":
            callbacks.onEvent({ kind: "aborted" });
            break;
          case "done":
            callbacks.onEvent({ kind: "done", persisted: Boolean(parsed.persisted) });
            break;
          case "keepalive":
            callbacks.onEvent({ kind: "keepalive" });
            break;
          default:
            // Ignore other runtime events (rate_limited / metadata) —
            // not displayed in the audit panel.
            break;
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      callbacks.onEvent({ kind: "aborted" });
      return;
    }
    callbacks.onEvent({ kind: "error", message: (err as Error).message });
  }
}
