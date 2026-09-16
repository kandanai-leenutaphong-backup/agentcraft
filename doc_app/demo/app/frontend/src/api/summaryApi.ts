/**
 * Summary API — operator-driven Summarize button.
 *
 * Two flavours:
 *   - `runSummary`     — blocking POST, returns the final SummaryState.
 *                        Kept for back-compat + any non-streaming caller.
 *   - `streamSummary`  — Phase 2 workstream E (2026-05-18). SSE consumer
 *                        that yields token chunks as the model writes,
 *                        then a terminal complete event with the parsed
 *                        SummaryState. Cuts perceived "Summarising…"
 *                        latency from 4–8s to ~1.5s for first token.
 *
 * ``getSummary`` is used once on session-load to hydrate any prior
 * result regardless of which run flavour was used.
 */

import type { SummaryState } from "./types";
import { BASE, authHeaders, extractErrorMessage, handleResponse } from "./client";

export async function getSummary(sessionId: string): Promise<SummaryState> {
  const res = await fetch(`${BASE}/summaries/${encodeURIComponent(sessionId)}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<SummaryState>(res);
}

export async function runSummary(sessionId: string): Promise<SummaryState> {
  const res = await fetch(
    `${BASE}/summaries/${encodeURIComponent(sessionId)}/run`,
    {
      method: "POST",
      headers: { ...await authHeaders() },
    },
  );
  return handleResponse<SummaryState>(res);
}

/* SSE consumer callbacks for the streaming summarizer. The store
   uses `onToken` to grow the muted "Summarising…" banner in real
   time, then swaps to the parsed bullets on `onComplete`. */
export interface SummaryStreamCallbacks {
  /** Each model token as it arrives. Concatenate into a partial draft. */
  onToken?: (chunk: string) => void;
  /** Terminal event with the parsed `SummaryState`. The state already
   *  includes `current` (parsed bullets) and `last_error` (if parse
   *  failed). */
  onComplete?: (state: SummaryState) => void;
  /** Early failure before any complete event was emitted. */
  onError?: (detail: string) => void;
}

/* Stream the summarizer over SSE. Mirrors the `streamChat` pattern in
   chatApi.ts: fetch + ReadableStream parser. Uses fetch instead of
   EventSource so we can POST + attach Bearer auth + AbortSignal. */
export async function streamSummary(
  sessionId: string,
  callbacks: SummaryStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${BASE}/summaries/${encodeURIComponent(sessionId)}/run/stream`;

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

        // Server emits `keepalive` frames every 20s; ignore.
        if (eventType === "keepalive" || eventType === "ping") continue;

        let parsed: Record<string, unknown> = {};
        try {
          parsed = data ? JSON.parse(data) : {};
        } catch {
          // Tokens are JSON-wrapped, but defend against partial frames.
          continue;
        }

        switch (eventType) {
          case "token": {
            const chunk = parsed.chunk as string | undefined;
            if (chunk) callbacks.onToken?.(chunk);
            break;
          }
          case "complete": {
            // Server emits the full SummaryState as the data payload.
            callbacks.onComplete?.(parsed as unknown as SummaryState);
            return;
          }
          case "error": {
            const detail = (parsed.detail as string) ?? "summary stream failed";
            callbacks.onError?.(detail);
            return;
          }
        }
      }
    }
  } catch (err) {
    callbacks.onError?.((err as Error).message);
  } finally {
    try { reader.releaseLock(); } catch { /* already released */ }
  }
}
