/**
 * Audit store — drives the SessionAuditPanel.
 *
 * Owns the live SSE connection while a run is in flight, the latest
 * report (live or loaded), the in-memory stream events for the live
 * tool sequence, and the history list for the dropdown.
 *
 * Stream events are intentionally NOT persisted — only the final
 * report lands in Cosmos. When a saved audit is loaded, the panel
 * shows the report only; the stream area shows the "stream not
 * retained" banner. This is the data-boundary rule (README §3).
 */

import { create } from "zustand";

import {
  AuditReport,
  AuditStreamEvent,
  AuditSummary,
  getAudit,
  interruptAudit,
  listAudits,
  streamAudit,
} from "@/api/auditApi";
import { IS_KIOSK } from "@/foundation/constants";

export type AuditStatus =
  | "idle"
  | "running"
  | "completed"
  | "interrupted"
  | "error";

interface AuditStore {
  status: AuditStatus;
  auditId: string | null;
  report: AuditReport | null;
  /** Source of the currently shown report — "live" (from the in-flight
   *  or just-finished run) vs "history" (loaded via dropdown). */
  reportSource: "live" | "history" | null;
  streamEvents: AuditStreamEvent[];
  /** Best-effort streaming text the auditor wrote between tool calls. */
  partialNarration: string;
  history: AuditSummary[];
  loadingHistory: boolean;
  loadingReport: boolean;
  error: string | null;
  /** Reference to the active fetch controller so the user can interrupt. */
  controller: AbortController | null;

  startAudit: (sessionId: string) => Promise<void>;
  interrupt: (sessionId: string) => Promise<void>;
  loadHistory: (sessionId: string) => Promise<void>;
  loadReport: (sessionId: string, auditId: string) => Promise<void>;
  /** Clear state when the active session changes. */
  reset: () => void;
}

const INITIAL: Omit<AuditStore, "startAudit" | "interrupt" | "loadHistory" | "loadReport" | "reset"> = {
  status: "idle",
  auditId: null,
  report: null,
  reportSource: null,
  streamEvents: [],
  partialNarration: "",
  history: [],
  loadingHistory: false,
  loadingReport: false,
  error: null,
  controller: null,
};

export const useAuditStore = create<AuditStore>((set, get) => ({
  ...INITIAL,

  reset: () => set({ ...INITIAL }),

  startAudit: async (sessionId: string) => {
    if (IS_KIOSK) return;
    /* If an audit is already running on this client, abort it first.
       The server-side guard cancels any concurrent run on the same
       session, but doing it client-first gives clean UI feedback. */
    const existing = get().controller;
    if (existing) {
      existing.abort();
    }

    const controller = new AbortController();
    set({
      ...INITIAL,
      status: "running",
      reportSource: "live",
      controller,
    });

    try {
      await streamAudit(
        sessionId,
        {
          onEvent: (event) => {
            const state = get();
            const events = [...state.streamEvents, event];

            switch (event.kind) {
              case "started":
                set({
                  status: "running",
                  auditId: event.auditId,
                  streamEvents: events,
                });
                break;

              case "token":
                set({
                  streamEvents: events,
                  partialNarration: state.partialNarration + event.token,
                });
                break;

              case "tool_call_start":
              case "tool_call_delta":
              case "tool_call_end":
              case "tool_result":
                set({ streamEvents: events });
                break;

              case "report":
                set({
                  streamEvents: events,
                  report: event.report,
                  reportSource: "live",
                  auditId: event.report.id,
                });
                break;

              case "error":
                set({
                  streamEvents: events,
                  error: event.message,
                  status: "error",
                });
                break;

              case "aborted":
                set({
                  streamEvents: events,
                  status: "interrupted",
                });
                break;

              case "done":
                set({
                  streamEvents: events,
                  status: event.persisted
                    ? "completed"
                    : (state.status === "error" || state.status === "interrupted"
                        ? state.status
                        : "interrupted"),
                  controller: null,
                });
                /* Refresh history so the dropdown picks up the new
                   audit. Best-effort — failure does not surface to
                   the user. */
                if (event.persisted) {
                  void get().loadHistory(sessionId);
                }
                break;

              case "keepalive":
                /* No state change — the SSE connection is still open. */
                break;
            }
          },
        },
        controller.signal,
      );
    } catch (err) {
      set({
        status: "error",
        error: (err as Error).message,
        controller: null,
      });
    }
  },

  interrupt: async (sessionId: string) => {
    /* Abort the local stream first so the UI flips immediately. */
    const ctrl = get().controller;
    if (ctrl) {
      ctrl.abort();
    }
    try {
      await interruptAudit(sessionId);
    } catch {
      /* The server may already be tearing down — non-fatal. */
    }
    set({
      status: "interrupted",
      controller: null,
    });
  },

  loadHistory: async (sessionId: string) => {
    if (IS_KIOSK) return;
    set({ loadingHistory: true });
    try {
      const items = await listAudits(sessionId);
      set({ history: items, loadingHistory: false });
    } catch (err) {
      set({
        history: [],
        loadingHistory: false,
        error: (err as Error).message,
      });
    }
  },

  loadReport: async (sessionId: string, auditId: string) => {
    if (IS_KIOSK) return;
    set({ loadingReport: true });
    try {
      const report = await getAudit(sessionId, auditId);
      set({
        report,
        reportSource: "history",
        auditId,
        loadingReport: false,
        /* Stream is not retained for saved audits. */
        streamEvents: [],
        partialNarration: "",
      });
    } catch (err) {
      set({
        loadingReport: false,
        error: (err as Error).message,
      });
    }
  },
}));
