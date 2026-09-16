/**
 * Session store — manages session list and active session.
 *
 * Module role:
 *   Zustand store with async actions that call the API client for session
 *   CRUD operations. Owns the session sidebar state: which sessions exist,
 *   which one is active, and what its full message history looks like.
 *
 * State:
 *   sessions         — Array of SessionSummary (no messages, for sidebar list)
 *   activeSessionId  — ID of the currently selected session
 *   activeSession    — Full Session object with messages (loaded on selection)
 *   loading/error    — UI loading and error states
 *
 * Lifecycle:
 *   1. Component mounts → fetchSessions() loads sidebar list
 *   2. User creates session → createSession() → auto-selects it
 *   3. User clicks session → selectSession() → loads full messages
 *   4. Chat completes → chatStore calls refreshActiveSession() to sync
 *
 * Key collaborators:
 *   - api/sessionApi.ts     — all session CRUD HTTP requests (re-exported
 *                             via api/client.ts barrel)
 *   - stores/chatStore.ts   — calls refreshActiveSession after streaming
 *   - stores/summaryStore + panelStore — kept in sync on session switch
 *
 * Dependents (verified):
 *   - components/layout/SavedSessionPicker.tsx
 *   - components/chat/ChatPanel, ChatInput, AgentTabBar, ContextInspector,
 *     MessageList
 *   - components/panels/PriorityActionsPanel, SituationAlertsPanel,
 *     PinnedSituationPanel, SituationSummaryCard
 */

import { create } from "zustand";
import type { Session, SessionSummary } from "@/api/types";
import * as api from "@/api/client";
import { useSummaryStore } from "./summaryStore";
import { usePanelStore } from "./panelStore";
import { IS_KIOSK } from "@/foundation/constants";

const BACKGROUND_RUN_POLL_MS = 1500;
let backgroundRunPollTimer: ReturnType<typeof setInterval> | null = null;

function sessionHasActiveBackgroundRuns(session: Session | null): boolean {
  if (!session) return false;
  return Object.values(session.background_runs ?? {}).some(
    (run) => run.status === "queued" || run.status === "running",
  );
}

function stopBackgroundRunPolling(): void {
  if (backgroundRunPollTimer) {
    clearInterval(backgroundRunPollTimer);
    backgroundRunPollTimer = null;
  }
}

function syncBackgroundRunPolling(getState: () => SessionState): void {
  const { activeSession, refreshActiveSession } = getState();
  if (!sessionHasActiveBackgroundRuns(activeSession)) {
    stopBackgroundRunPolling();
    return;
  }
  if (backgroundRunPollTimer) return;
  backgroundRunPollTimer = setInterval(() => {
    void refreshActiveSession();
  }, BACKGROUND_RUN_POLL_MS);
}

interface SessionState {
  // State
  sessions: SessionSummary[];
  activeSessionId: string | null;
  activeSession: Session | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<Session>;
  selectSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  saveSession: (sessionId: string) => Promise<void>;
  resetDefaults: () => Promise<void>;
  clearError: () => void;

  // Internal — called by chatStore after messages change
  refreshActiveSession: () => Promise<void>;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  activeSession: null,
  loading: false,
  error: null,

  fetchSessions: async () => {
    if (IS_KIOSK) {
      set({ sessions: [], loading: false, error: null });
      return;
    }
    set({ loading: true, error: null });
    try {
      const sessions = await api.listSessions();
      set({ sessions, loading: false });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  createSession: async (title?: string) => {
    if (IS_KIOSK) {
      const now = new Date().toISOString();
      const session: Session = {
        id: `kiosk-session-${Date.now()}`,
        title: title ?? "Kiosk session",
        schema_version: 3,
        scenario_name: "kiosk",
        user_id: "kiosk",
        threads: {},
        background_runs: {},
        created_at: now,
        updated_at: now,
      };
      set({ activeSessionId: session.id, activeSession: session });
      return session;
    }
    try {
      const session = await api.createSession(title ? { title } : undefined);
      // Prepend to list and select it
      set((state) => ({
        sessions: [
          {
            id: session.id,
            title: session.title,
            scenario_name: "",
            user_id: session.user_id,
            message_count: 0,
            tool_call_count: 0,
            user_prompt_count: 0,
            agent_response_count: 0,
            created_at: session.created_at,
            updated_at: session.updated_at,
          },
          ...state.sessions,
        ],
        activeSessionId: session.id,
        activeSession: session,
      }));
      useSummaryStore.getState().hydrate(session.id, session.summary_state);
      usePanelStore.getState().hydratePriorityActionState(session.priority_action_state);
      syncBackgroundRunPolling(get);
      return session;
    } catch (err) {
      set({ error: (err as Error).message });
      throw err;
    }
  },

  selectSession: async (sessionId: string) => {
    set({ loading: true, error: null, activeSessionId: sessionId });
    try {
      const session = await api.getSession(sessionId);
      set({ activeSession: session, loading: false });
      useSummaryStore.getState().hydrate(session.id, session.summary_state);
      usePanelStore.getState().hydratePriorityActionState(session.priority_action_state);
      syncBackgroundRunPolling(get);
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
      stopBackgroundRunPolling();
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await api.deleteSession(sessionId);
      const { activeSessionId } = get();
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== sessionId),
        ...(activeSessionId === sessionId
          ? { activeSessionId: null, activeSession: null }
          : {}),
      }));
      if (activeSessionId === sessionId) stopBackgroundRunPolling();
      if (activeSessionId === sessionId) useSummaryStore.getState().resetLocal();
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  renameSession: async (sessionId: string, title: string) => {
    try {
      await api.updateSession(sessionId, { title });
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, title } : s,
        ),
        activeSession:
          state.activeSession?.id === sessionId
            ? { ...state.activeSession, title }
            : state.activeSession,
      }));
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  refreshActiveSession: async () => {
    if (IS_KIOSK) return;
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      const session = await api.getSession(activeSessionId);
      set({ activeSession: session });
      usePanelStore.getState().hydratePriorityActionState(session.priority_action_state);
      syncBackgroundRunPolling(get);
      // Also update the summary in the list
      /* Count messages across all threads for the sidebar summary */
      const totalMessages = Object.values(session.threads ?? {}).reduce(
        (sum, t) => sum + (t.messages?.length ?? 0), 0
      );
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === activeSessionId
            ? {
                ...s,
                title: session.title,
                message_count: totalMessages,
                updated_at: session.updated_at,
              }
            : s,
        ),
      }));
    } catch {
      // Silently fail — session may have been deleted
      stopBackgroundRunPolling();
    }
  },

  saveSession: async (sessionId: string) => {
    try {
      await api.saveSession(sessionId);
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  resetDefaults: async () => {
    try {
      await api.resetDefaults();
      // Refresh the session list to show newly cloned demos
      await get().fetchSessions();
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  clearError: () => set({ error: null }),
}));
