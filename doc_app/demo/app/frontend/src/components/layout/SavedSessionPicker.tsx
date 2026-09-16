/**
 * SavedSessionPicker — dropdown menu for loading historical sessions.
 *
 * Reads from config/savedSessions.ts. On selection, fetches the full
 * session from Cosmos, then hydrates chat messages and panel state.
 */

import { useState, useRef, useEffect } from "react";
import { History, ChevronDown, Loader2 } from "lucide-react";
import { SAVED_SESSIONS, SCAN_SCENARIOS } from "@/config/savedSessions";
import type { SavedSession } from "@/config/savedSessions";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { usePanelStore } from "@/stores/panelStore";
import { useAgentStore } from "@/stores/agentStore";
import { useSituationStore } from "@/stores/situationStore";
import { usePlaceholderStore } from "@/stores/placeholderStore";
import { useSummaryStore } from "@/stores/summaryStore";
import { BASE } from "@/foundation/constants";
import { authHeaders } from "@/api/client";

export function SavedSessionPicker() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (SAVED_SESSIONS.length === 0) return null;

  async function handleSelect(sessionId: string) {
    setLoading(true);
    setOpen(false);

    /* Find the saved session config entry for scan params. */
    const savedEntry: SavedSession | undefined = SAVED_SESSIONS.find((s) => s.sessionId === sessionId);

    try {
      // Fetch the demo session. The endpoint is now auth-gated server-side
      // (it returns the session only when the caller's identity matches the
      // owner OR when the session is a shared __default__ template), so we
      // must attach the same Authorization / X-User-Id headers used by the
      // rest of the API client. Without these the request is rejected with
      // 401 in production and the picker silently fails.
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/sessions/demo/${sessionId}`, { headers });
      if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
      const session = await res.json();

      // Disable placeholder mode so real data shows
      if (usePlaceholderStore.getState().enabled) {
        usePlaceholderStore.getState().toggle();
      }

      // Set as active session on the store (bypassing auth-protected selectSession)
      useSessionStore.setState({
        activeSessionId: session.id,
        activeSession: session,
        loading: false,
      });

      // Hydrate chat + panels from the loaded session
      if (session?.threads) {
        const defaultAgentId = useAgentStore.getState().agents[0]?.id ?? "grid_manager";
        useChatStore.getState().clearAll();
        usePanelStore.getState().clearPanels();
        useSummaryStore.getState().resetLocal();
        useSummaryStore.getState().hydrate(session.id, session.summary_state);
        usePanelStore.getState().hydratePriorityActionState(session.priority_action_state);
        useChatStore.getState().loadSessionMessages(session.threads, defaultAgentId);
        usePanelStore.getState().syncPriorityActionsFromThreads(session.threads);
      }

      // Auto-run situation scan if the saved session has scan params
      if (savedEntry?.scanParams) {
        const sitStore = useSituationStore.getState();
        sitStore.setParams(savedEntry.scanParams);
        sitStore.fetchSituations();
      }
    } catch (err) {
      console.error("Failed to load saved session:", err);
    } finally {
      setLoading(false);
    }
  }

  // Find current label if a saved session is active
  const currentLabel = SAVED_SESSIONS.find((s) => s.sessionId === activeSessionId)?.label;

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        disabled={loading}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-neutral-bg2 rounded transition-colors"
      >
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <History className="h-3.5 w-3.5" />
        )}
        {currentLabel ?? "Saved Sessions"}
        <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-neutral-bg1 border border-border rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <span className="text-label uppercase tracking-wider text-text-tertiary font-bold">
              Load Historical Session
            </span>
          </div>
          {SAVED_SESSIONS.map((s) => (
            <button
              key={s.sessionId}
              onClick={() => handleSelect(s.sessionId)}
              className={`w-full text-left px-3 py-2.5 hover:bg-neutral-bg2 transition-colors border-b border-border/30 last:border-0 ${
                s.sessionId === activeSessionId ? "bg-brand/10 text-brand" : ""
              }`}
            >
              <div className="text-sm font-medium text-text-primary">{s.label}</div>
              {s.description && (
                <div className="text-label text-text-tertiary mt-0.5">{s.description}</div>
              )}
            </button>
          ))}

          {/* Scan Scenarios — populate situation alerts without loading a session */}
          {SCAN_SCENARIOS.length > 0 && (
            <>
              <div className="px-3 py-2 border-t border-border">
                <span className="text-label uppercase tracking-wider text-text-tertiary font-bold">
                  Scan Scenarios
                </span>
              </div>
              {SCAN_SCENARIOS.map((sc) => (
                <button
                  key={sc.label}
                  data-testid="scan-scenario-button"
                  onClick={() => {
                    setOpen(false);
                    if (usePlaceholderStore.getState().enabled) {
                      usePlaceholderStore.getState().toggle();
                    }
                    const sitStore = useSituationStore.getState();
                    sitStore.setParams(sc.scanParams);
                    usePanelStore.getState().setCenterTab("status");
                    sitStore.fetchSituations();
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-neutral-bg2 transition-colors border-b border-border/30 last:border-0"
                >
                  <div className="text-sm font-medium text-text-primary">{sc.label}</div>
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
