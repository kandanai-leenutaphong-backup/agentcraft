import { readJsonEvents } from "@agentcraft/event-stream";
import type { AgentCatalogueEntry, GraphEntity, GraphNode, GraphOverview, GraphScope, GraphSlice, GraphStatus, GraphWindow, QueryResult, RuleDefinition, ScanResponse, ScanStreamEvent, Scenario, SequenceStepEvent, Situation, SituationDiagnosis, SituationSequence, SituationSummary, ToolRun } from "../types";

const json = { "Content-Type": "application/json" };

/** The backend lost the session: restarted, evicted, or idled it out. Recoverable by recreating. */
export class SessionExpiredError extends Error {
  constructor() { super("chat session expired"); this.name = "SessionExpiredError"; }
}

/** Who the server believes the caller is. Never asserted by the client. */
export interface Caller {
  id: string;
  kind: string;
  issuer: string;
  display: string;
  tenant_id: string;
}

/**
 * A signed-in session ended while the page was open — expired, or revoked elsewhere.
 *
 * Sending the browser back to sign in is the honest response: every panel is about to fail
 * with an unexplained error, and an application that shows twelve of those instead of one
 * sign-in prompt has decided its user should diagnose it.
 *
 * Only page navigations are redirected. A signed developer request never has a session to
 * lose, and the redirect is harmless there because the gate refuses it either way.
 */
let signingIn = false;
function sessionEnded(): never {
  if (!signingIn && typeof window !== "undefined") {
    signingIn = true;
    const back = window.location.pathname + window.location.search;
    window.location.assign(`/auth/login?return_to=${encodeURIComponent(back)}`);
  }
  throw new Error("your session has ended; signing in again");
}

async function checked<T>(pending: Response | Promise<Response>): Promise<T> {
  const response = await pending;
  if (response.status === 401) sessionEnded();
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ") : body.detail;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  return checked<T>(fetch(path, {
    ...options, credentials: "same-origin", headers: { ...json, ...options.headers },
  }));
}

export const api = {
  whoami: () => checked<Caller>(fetch("/api/whoami")),
  agents: (signal?: AbortSignal) => checked<{ agents: AgentCatalogueEntry[] }>(
    fetch("/api/cyber/agents", { signal })),
  health: () => checked<Record<string, unknown>>(fetch("/api/health")),
  scenarios: () => checked<Scenario[]>(fetch("/api/cyber/scenarios")),
  scan: (start: string, end: string) =>
    checked<ScanResponse>(fetch("/api/cyber/scan", {
      method: "POST", headers: json, body: JSON.stringify({ start, end }),
    })),
  query: (query: string, maxRows = 100) =>
    checked<QueryResult>(fetch("/api/cyber/query", {
      method: "POST", headers: json, body: JSON.stringify({ query, max_rows: maxRows }),
    })),
  evidence: (id: string, window?: { start: string; end: string } | null) => checked<QueryResult & { situation_id: string }>(fetch(`/api/cyber/evidence/${id}${window ? `?start=${encodeURIComponent(window.start)}&end=${encodeURIComponent(window.end)}` : ""}`)),
  summarizeSituation: (situation: Situation) => checked<SituationSummary>(fetch("/api/cyber/situations/summary", {
    method: "POST", headers: json, body: JSON.stringify(situation),
  })),
  knowledgeType: (typeId: string) => checked<Record<string, unknown>>(
    fetch(`/api/cyber/knowledge/type/${encodeURIComponent(typeId)}`)),
  /**
   * Open a chat session.
   *
   * The JSON content type and the empty object body are not decoration. This is an unsafe
   * method, and a signed-in person carries their identity in a cookie the browser attaches
   * automatically, so the cross-site guard requires a same-origin JSON request before it will
   * let one through. Without these headers every human caller received 403 while signed
   * developer access — which carries a header, not a cookie — kept working, so the defect was
   * invisible to every automated check.
   */
  createSession: () => checked<{ session_id: string }>(fetch("/api/sessions", {
    method: "POST", credentials: "same-origin", headers: json, body: "{}",
  })),
  graphStatus: () => checked<GraphStatus>(fetch("/api/cyber/graph/status")),
  graphOverview: () => checked<GraphOverview>(fetch("/api/cyber/graph/overview")),
  graphCore: (window?: GraphWindow, limit = 260) =>
    checked<GraphSlice>(fetch(`/api/cyber/graph/core?limit=${limit}${windowQuery(window)}`)),
  graphNode: (id: string, window?: GraphWindow, limit = 220, depth = 1) =>
    checked<GraphSlice>(fetch(`/api/cyber/graph/node?id=${encodeURIComponent(id)}&limit=${limit}&depth=${depth}${windowQuery(window)}`)),
  graphSelection: (ids: string[], window?: GraphWindow, depth = 1,
                   scope: GraphScope = "only", limit = 220) => {
    const query = ids.map((id) => `id=${encodeURIComponent(id)}`).join("&");
    return checked<GraphSlice>(fetch(`/api/cyber/graph/selection?${query}&depth=${depth}&scope=${scope}&limit=${limit}${windowQuery(window)}`));
  },
  rules: () => checked<RuleDefinition[]>(fetch("/api/cyber/rules")),
  graphEntities: () => checked<GraphEntity[]>(fetch("/api/cyber/graph/entities")),
  graphSearch: (term: string) =>
    checked<GraphNode[]>(fetch(`/api/cyber/graph/search?q=${encodeURIComponent(term)}`)),
};

/**
 * End the session here, then at Microsoft.
 *
 * The local revocation happens first and does not depend on the second step completing: a
 * sign-out that only ends the identity provider's session leaves this application's cookie
 * live, which is the opposite of what the button appears to do.
 *
 * A failed revocation must not navigate. Sending the browser to the signed-out page while the
 * cookie is still valid tells a person they are signed out when they are not — the single
 * most dangerous thing this function could say. It throws instead, so the caller can offer a
 * retry on a page that is still the signed-in one.
 */
export async function signOut(): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/auth/logout", {
      method: "POST", credentials: "same-origin", headers: json, body: "{}",
    });
  } catch {
    throw new Error("could not reach the server to sign out; you are still signed in");
  }
  if (!response.ok) {
    throw new Error(
      `sign-out failed (HTTP ${response.status}); you are still signed in — try again`,
    );
  }
  const body = await response.json().catch(() => ({}));
  window.location.assign(body.providerLogoutUrl || "/auth/signed-out");
}

function windowQuery(window?: GraphWindow): string {
  if (!window) return "";
  return `&start=${encodeURIComponent(window.start)}&end=${encodeURIComponent(window.end)}`;
}

export async function streamScan(
  start: string,
  end: string,
  onEvent: (event: ScanStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const body = await postStream("/api/cyber/scan/stream", { start, end }, signal);
  await readJsonEvents(body, (type, data) => onEvent({ type, data } as ScanStreamEvent));
}

export interface DiagnosisCallbacks {
  metadata?: (data: Record<string, unknown>) => void;
  status: (label: string) => void;
  toolStart: (name: string, displayName: string, id: string) => void;
  toolDelta: (id: string, delta: string) => void;
  toolEnd: (id: string, args: Record<string, unknown>) => void;
  toolResult: (id: string, name: string, result: unknown) => void;
  reasoning: (id: string, delta: string, state: ReasoningState) => void;
  diagnosis: (value: SituationDiagnosis) => void;
  sequenceStep: (value: SequenceStepEvent) => void;
  sequence: (value: SituationSequence) => void;
  error: (detail: string) => void;
  done: () => void;
}

/** Where a reasoning summary part is in its life: opened, growing, or finished. */
export type ReasoningState = "start" | "delta" | "end";

export interface SummaryCallbacks {
  metadata?: (data: Record<string, unknown>) => void;
  status: (label: string) => void;
  token: (value: string) => void;
  summary: (value: SituationSummary) => void;
  error: (detail: string) => void;
  done: () => void;
}

/**
 * Stream the situation summary as the model produces it.
 *
 * The non-streaming POST stays on `api.summarizeSituation` for callers that want one JSON
 * response. The tokens here are the server's own deltas: nothing is replayed character by
 * character on the client, so a stalled model looks stalled rather than busy.
 */
export async function streamSummary(
  situation: Situation,
  callbacks: SummaryCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const body = await postStream("/api/cyber/situations/summary/stream", situation, signal);
  await readJsonEvents(body, (event, parsed) => {
    if (event === "status") callbacks.status(String(parsed.label ?? "Working…"));
    else if (event === "metadata") callbacks.metadata?.(parsed);
    else if (event === "token") callbacks.token(String(parsed.token ?? ""));
    else if (event === "summary") callbacks.summary(parsed as unknown as SituationSummary);
    else if (event === "error") callbacks.error(String(parsed.detail ?? parsed.error ?? "Summary failed"));
    else if (event === "done") callbacks.done();
  });
}

async function postStream(path: string, payload: unknown, signal?: AbortSignal,
                          session = false): Promise<ReadableStream<Uint8Array>> {
  const response = await fetch(path, {
    method: "POST", headers: { ...json, Accept: "text/event-stream" },
    body: JSON.stringify(payload), signal,
  });
  if (!response.ok || !response.body) {
    if (session && response.status === 404) throw new SessionExpiredError();
    throw new Error(await response.text() || `HTTP ${response.status}`);
  }
  return response.body;
}

export async function streamDiagnosis(
  situation: Situation,
  callbacks: DiagnosisCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const body = await postStream("/api/cyber/situations/diagnose", situation, signal);
  await readJsonEvents(body, (event, parsed) => {
    if (event === "status") callbacks.status(String(parsed.label ?? "Working…"));
    else if (event === "metadata") callbacks.metadata?.(parsed);
    else if (event === "tool_call_start") callbacks.toolStart(String(parsed.name), String(parsed.display_name ?? parsed.name), String(parsed.id));
    else if (event === "tool_call_delta") callbacks.toolDelta(String(parsed.id), String(parsed.arguments_delta ?? ""));
    else if (event === "tool_call_end") callbacks.toolEnd(String(parsed.id), (parsed.arguments ?? {}) as Record<string, unknown>);
    else if (event === "tool_result") callbacks.toolResult(String(parsed.id), String(parsed.name), parsed.result);
    else if (event === "reasoning_start") callbacks.reasoning(String(parsed.id), "", "start");
    else if (event === "reasoning_delta") callbacks.reasoning(String(parsed.id), String(parsed.delta ?? ""), "delta");
    else if (event === "reasoning_end") callbacks.reasoning(String(parsed.id), String(parsed.text ?? ""), "end");
    else if (event === "diagnosis") callbacks.diagnosis(parsed as unknown as SituationDiagnosis);
    else if (event === "sequence_step") callbacks.sequenceStep(parsed as unknown as SequenceStepEvent);
    else if (event === "sequence") callbacks.sequence(parsed as unknown as SituationSequence);
    else if (event === "error") callbacks.error(String(parsed.detail ?? parsed.error ?? "Diagnosis failed"));
    else if (event === "done") callbacks.done();
  });
}

interface StreamCallbacks {
  token: (value: string) => void;
  toolStart: (tool: ToolRun) => void;
  toolDelta: (id: string, delta: string) => void;
  toolEnd: (id: string, args: Record<string, unknown>) => void;
  toolResult: (id: string, name: string, result: unknown) => void;
  reasoning: (id: string, delta: string, state: ReasoningState) => void;
  metadata: (data: Record<string, unknown>) => void;
  status: (label: string) => void;
  done: () => void;
  error: (message: string) => void;
}

function dispatchFrame(event: string, parsed: Record<string, unknown>, callbacks: StreamCallbacks): void {
  if (event === "token") callbacks.token(String(parsed.token ?? ""));
  else if (event === "tool_call_start") callbacks.toolStart({
    id: String(parsed.id), name: String(parsed.name),
    displayName: String(parsed.display_name ?? parsed.name), fallback: parsed.fallback === true,
    status: "running", startedAt: Date.now(),
  });
  else if (event === "tool_call_delta") callbacks.toolDelta(
    String(parsed.id), String(parsed.arguments_delta ?? ""),
  );
  else if (event === "tool_call_end") callbacks.toolEnd(
    String(parsed.id), (parsed.arguments ?? {}) as Record<string, unknown>,
  );
  else if (event === "tool_result") callbacks.toolResult(
    String(parsed.id), String(parsed.name), parsed.result,
  );
  else if (event === "reasoning_start") callbacks.reasoning(String(parsed.id), "", "start");
  else if (event === "reasoning_delta") callbacks.reasoning(
    String(parsed.id), String(parsed.delta ?? ""), "delta",
  );
  else if (event === "reasoning_end") callbacks.reasoning(
    String(parsed.id), String(parsed.text ?? ""), "end",
  );
  else if (event === "metadata") callbacks.metadata(parsed);
  else if (event === "status") callbacks.status(String(parsed.label ?? "Working…"));
  else if (event === "done") callbacks.done();
  else if (event === "error") callbacks.error(String(parsed.detail ?? parsed.error ?? "Agent error"));
}

export async function streamChat(
  sessionId: string,
  message: string,
  situation: Situation | null,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const body = await postStream(`/api/chat/${sessionId}`, { message, situation }, signal, true);
  await readJsonEvents(body, (event, parsed) => dispatchFrame(event, parsed, callbacks));
}
