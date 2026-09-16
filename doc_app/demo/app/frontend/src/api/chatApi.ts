/**
 * Chat API — SSE streaming, background subscriptions, and abort.
 *
 * Extracted from client.ts for domain-specific organization.
 * Contains the SSE streaming protocol parser, background SSE subscriber,
 * and abort function.
 */

import type { ChatRequest, StreamEventType } from "./types";
import { BASE, authHeaders, extractErrorMessage } from "./client";

export interface SSECallbacks {
  onToken?: (token: string) => void;
  onToolCallStart?: (id: string, name: string) => void;
  onToolCallDelta?: (id: string, argumentsDelta: string) => void;
  onToolCallEnd?: (
    id: string,
    name: string,
    args: Record<string, unknown>,
  ) => void;
  onToolResult?: (id: string, name: string, result: string) => void;
  onCitation?: (id: number, source: string, content?: string) => void;
  onMetadata?: (data: Record<string, unknown>) => void;
  onRateLimited?: (retryAfter: number, attempt: number) => void;
  onKeepalive?: () => void;
  // Delegation overlay events — specialist streaming surfaced on the main SSE
  onDelegationStart?: (agentId: string, agentName: string, task: string) => void;
  onDelegationToken?: (agentId: string, token: string) => void;
  onDelegationToolStart?: (agentId: string, toolId: string, toolName: string) => void;
  onDelegationToolDelta?: (agentId: string, toolId: string, argumentsDelta: string) => void;
  onDelegationToolEnd?: (agentId: string, toolId: string, toolName: string, args: Record<string, unknown>) => void;
  onDelegationToolResult?: (agentId: string, toolId: string, toolName: string, result: string) => void;
  onDelegationDone?: (agentId: string) => void;
  onDelegationError?: (agentId: string, error: string) => void;
  onError?: (error: string, errorCode?: string, errorId?: string) => void;
  onDone?: () => void;
  onAborted?: () => void;
}

/**
 * Send a chat message and consume the SSE response stream.
 *
 * Uses fetch + ReadableStream (not EventSource) for:
 *   - POST method support (EventSource is GET-only)
 *   - AbortController integration
 *   - Custom event type parsing
 */
export async function streamChat(
  sessionId: string,
  req: ChatRequest,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
  agentId?: string,
): Promise<void> {
  const params = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  const url = `${BASE}/chat/${sessionId}${params}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...await authHeaders(),
      },
      body: JSON.stringify(req),
      signal,
    });
  } catch (fetchErr) {
    callbacks.onError?.((fetchErr as Error).message);
    return;
  }

  if (!res.ok) {
    if (res.status === 401) {
      const { handleAuthExpired } = await import("./client");
      handleAuthExpired();
    }
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    callbacks.onError?.(extractErrorMessage(body, `HTTP ${res.status}`));
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

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk.replace(/\r\n/g, "\n");

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        if (!frame.trim()) continue;

        let eventType: StreamEventType | null = null;
        const dataLines: string[] = [];

        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim() as StreamEventType;
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
          console.warn("[streamChat] Non-JSON SSE data skipped:", data?.slice(0, 100));
        }

        switch (eventType) {
          case "token":
            callbacks.onToken?.(parsed.token as string);
            break;
          case "tool_call_start":
            callbacks.onToolCallStart?.(parsed.id as string, parsed.name as string);
            break;
          case "tool_call_delta":
            callbacks.onToolCallDelta?.(parsed.id as string, parsed.arguments_delta as string);
            break;
          case "tool_call_end":
            callbacks.onToolCallEnd?.(parsed.id as string, parsed.name as string, parsed.arguments as Record<string, unknown>);
            break;
          case "tool_result":
            callbacks.onToolResult?.(parsed.id as string, parsed.name as string, parsed.result as string);
            break;
          case "citation":
            callbacks.onCitation?.(parsed.id as number, parsed.source as string, parsed.content as string | undefined);
            break;
          case "metadata":
            callbacks.onMetadata?.(parsed);
            break;
          case "rate_limited":
            callbacks.onRateLimited?.(parsed.retry_after as number, parsed.attempt as number);
            break;
          case "error":
            callbacks.onError?.(parsed.error as string, parsed.error_code as string | undefined, parsed.error_id as string | undefined);
            break;
          case "done":
            callbacks.onDone?.();
            break;
          case "aborted":
            callbacks.onAborted?.();
            break;
          case "keepalive":
            callbacks.onKeepalive?.();
            break;
          // Delegation overlay events — specialist streaming
          case "delegation_start":
            callbacks.onDelegationStart?.(
              parsed.agent_id as string,
              parsed.agent_name as string,
              parsed.task as string,
            );
            break;
          case "delegation_token":
            callbacks.onDelegationToken?.(parsed.agent_id as string, parsed.token as string);
            break;
          case "delegation_tool_start":
            callbacks.onDelegationToolStart?.(parsed.agent_id as string, parsed.id as string, parsed.name as string);
            break;
          case "delegation_tool_delta":
            callbacks.onDelegationToolDelta?.(parsed.agent_id as string, parsed.id as string, (parsed.arguments_delta as string) || "");
            break;
          case "delegation_tool_end":
            callbacks.onDelegationToolEnd?.(parsed.agent_id as string, parsed.id as string, parsed.name as string, parsed.arguments as Record<string, unknown>);
            break;
          case "delegation_tool_result":
            callbacks.onDelegationToolResult?.(parsed.agent_id as string, parsed.id as string, parsed.name as string, parsed.result as string);
            break;
          case "delegation_done":
            callbacks.onDelegationDone?.(parsed.agent_id as string);
            break;
          case "delegation_error":
            callbacks.onDelegationError?.(parsed.agent_id as string, parsed.error as string);
            break;
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      callbacks.onAborted?.();
    } else {
      callbacks.onError?.((err as Error).message);
    }
  }
}

export async function abortGeneration(sessionId: string, agentId?: string): Promise<void> {
  const params = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  await fetch(`${BASE}/chat/${sessionId}/abort${params}`, {
    method: "POST",
    headers: { ...await authHeaders() },
  });
}

/**
 * Callbacks for background SSE events emitted by a detached agent run.
 *
 * Each callback maps to a BACKGROUND_* event type published by the
 * BackgroundEventBroker on the backend. Used to stream dispatcher
 * progress into the chatStore/panelStore after delegation.
 */
export interface BackgroundSSECallbacks {
  onStart?: (agentId: string, task: string) => void;
  onToken?: (agentId: string, token: string) => void;
  onToolCallStart?: (agentId: string, id: string, name: string) => void;
  onToolCallDelta?: (agentId: string, id: string, argumentsDelta: string) => void;
  onToolCallEnd?: (agentId: string, id: string, name: string, args: Record<string, unknown>) => void;
  onToolResult?: (agentId: string, id: string, name: string, result: string) => void;
  onDone?: (agentId: string) => void;
  onError?: (agentId: string, error: string) => void;
  onAborted?: (agentId: string) => void;
}

/**
 * Subscribe to background agent run events via GET SSE.
 *
 * Opens a persistent connection to the background events endpoint and
 * dispatches parsed events through the provided callbacks. The connection
 * stays open until background_done/error/aborted fires, the AbortSignal
 * triggers, or the server closes the stream.
 *
 * Uses fetch + ReadableStream (not EventSource) for custom auth header
 * support — EventSource is limited to GET with no custom headers.
 *
 * @param sessionId - Active chat session ID
 * @param agentId   - Target agent (e.g. "dispatcher") to filter events
 * @param callbacks - Event handlers for background streaming events
 * @param signal    - Optional AbortSignal for cancellation
 */
export async function subscribeBackground(
  sessionId: string,
  agentId: string,
  callbacks: BackgroundSSECallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const params = `?agent_id=${encodeURIComponent(agentId)}`;
  const url = `${BASE}/chat/${sessionId}/background${params}`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "text/event-stream",
        ...await authHeaders(),
      },
      signal,
    });
  } catch (fetchErr) {
    /* Network-level failure — connection refused, DNS, or AbortError */
    if ((fetchErr as Error).name !== "AbortError") {
      console.error("[subscribeBackground] fetch failed:", fetchErr);
      callbacks.onError?.(agentId, (fetchErr as Error).message);
    }
    return;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    console.error("[subscribeBackground] HTTP error:", res.status, body);
    callbacks.onError?.(agentId, extractErrorMessage(body, `HTTP ${res.status}`));
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError?.(agentId, "No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk.replace(/\r\n/g, "\n");

      /* Split on double-newline SSE frame boundaries */
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        if (!frame.trim()) continue;

        let eventType: StreamEventType | null = null;
        const dataLines: string[] = [];

        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim() as StreamEventType;
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
          console.warn("[subscribeBackground] Non-JSON SSE data skipped:", data?.slice(0, 100));
          continue;
        }

        /* Extract the agent_id from the event payload — every background
           event includes it, but fall back to the subscription agentId. */
        const evAgentId = (parsed.agent_id as string) || agentId;

        switch (eventType) {
          case "background_start":
            callbacks.onStart?.(evAgentId, (parsed.task as string) || "");
            break;
          case "background_token":
            callbacks.onToken?.(evAgentId, (parsed.token as string) || "");
            break;
          case "background_tool_start":
            callbacks.onToolCallStart?.(evAgentId, parsed.id as string, parsed.name as string);
            break;
          case "background_tool_delta":
            callbacks.onToolCallDelta?.(evAgentId, parsed.id as string, (parsed.arguments_delta as string) || "");
            break;
          case "background_tool_end":
            callbacks.onToolCallEnd?.(evAgentId, parsed.id as string, parsed.name as string, (parsed.arguments as Record<string, unknown>) || {});
            break;
          case "background_tool_result":
            callbacks.onToolResult?.(evAgentId, parsed.id as string, parsed.name as string, (parsed.result as string) || "");
            break;
          case "background_done":
            callbacks.onDone?.(evAgentId);
            return; /* Terminal — close the subscription */
          case "background_error":
            callbacks.onError?.(evAgentId, (parsed.error as string) || "Background run error");
            return; /* Terminal — close the subscription */
          case "background_aborted":
            callbacks.onAborted?.(evAgentId);
            return; /* Terminal — close the subscription */
          case "keepalive":
            /* Server heartbeat — ignore */
            break;
          default:
            /* Unknown event types are silently ignored */
            break;
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      callbacks.onAborted?.(agentId);
    } else {
      console.error("[subscribeBackground] stream error:", err);
      callbacks.onError?.(agentId, (err as Error).message);
    }
  }
}
