/**
 * Summary store — operator-driven situation summary.
 *
 * Owns the one summary slot per session: hydration on session load,
 * the in-flight state of the **Summarize** button, and (since
 * Phase 2 workstream E, 2026-05-18) a `streamingText` slot used to
 * render the live token feed from the streaming summarizer while
 * the model is composing.
 *
 * `run()` calls the SSE endpoint `POST /api/summaries/{sid}/run/stream`
 * via `streamSummary()`. Tokens grow `streamingText`; on the terminal
 * `complete` event the parsed `SummaryState` replaces `summaryState`
 * and `streamingText` is cleared.
 */

import { create } from "zustand";
import type { SummaryState } from "@/api/types";
import * as api from "@/api/client";
import { IS_KIOSK } from "@/foundation/constants";

export const EMPTY_SUMMARY_STATE: SummaryState = {
  status: "idle",
  current: null,
  revisions: [],
  processed_event_ids: [],
  pending_event_ids: [],
  last_error: null,
};

interface SummaryStoreState {
  summaryState: SummaryState;
  activeSessionId: string | null;
  /** Local UI state — distinct from the persisted SummaryState.status. */
  loading: boolean;
  error: string | null;
  /** Live token feed from the streaming summarizer. Empty when not
   *  streaming. The card renders this behind a muted "Summarising…"
   *  banner so the operator sees activity before the bullets arrive. */
  streamingText: string;

  /** Hydrate from a session load. Idempotent. */
  hydrate: (sessionId: string, state: SummaryState | null | undefined) => void;
  /** Clear local state — called when the session id changes / unmounts. */
  resetLocal: () => void;
  /** Run the summarizer over SSE. Replaces the current summary on success. */
  run: (sessionId: string) => Promise<void>;
  /** Optional: refresh from the server without re-running. */
  refresh: (sessionId: string) => Promise<void>;
}

export const useSummaryStore = create<SummaryStoreState>((set, get) => ({
  summaryState: EMPTY_SUMMARY_STATE,
  activeSessionId: null,
  loading: false,
  error: null,
  streamingText: "",

  hydrate: (sessionId, state) =>
    set({
      summaryState: state ?? EMPTY_SUMMARY_STATE,
      activeSessionId: sessionId,
      loading: false,
      error: null,
      streamingText: "",
    }),

  resetLocal: () =>
    set({
      summaryState: EMPTY_SUMMARY_STATE,
      activeSessionId: null,
      loading: false,
      error: null,
      streamingText: "",
    }),

  run: async (sessionId: string) => {
    if (IS_KIOSK) return;
    set({
      activeSessionId: sessionId,
      loading: true,
      error: null,
      streamingText: "",
    });
    /* Stream via SSE so the operator sees progress within ~1.5s rather
       than 4-8s of dead UI. Tokens accumulate into `streamingText`;
       the terminal `complete` event swaps in the parsed bullets. */
    await api.streamSummary(sessionId, {
      onToken: (chunk: string) => {
        // Guard against late tokens after session switch.
        if (get().activeSessionId !== sessionId) return;
        set((state) => ({ streamingText: state.streamingText + chunk }));
      },
      onComplete: (state: SummaryState) => {
        if (get().activeSessionId !== sessionId) return;
        set({
          summaryState: state,
          loading: false,
          streamingText: "",
          error: state.last_error ?? null,
        });
      },
      onError: (detail: string) => {
        if (get().activeSessionId !== sessionId) return;
        set({ loading: false, error: detail, streamingText: "" });
      },
    });
  },

  refresh: async (sessionId: string) => {
    try {
      const next = await api.getSummary(sessionId);
      if (get().activeSessionId !== sessionId) return;
      set({ summaryState: next });
    } catch (err) {
      if (get().activeSessionId !== sessionId) return;
      set({ error: (err as Error).message });
    }
  },
}));
