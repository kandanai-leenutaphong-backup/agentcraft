/**
 * AgentTabBar — flat horizontal tab bar for the three configured agents
 * (Investigator, Dispatcher), plus optional ad-hoc delegated tabs.
 *
 * Module role:
 *   Renders one permanent tab per configured agent and one ephemeral pill
 *   per non-configured delegate. No slots, no sub-tabs, no track grouping.
 *
 * Key collaborators:
 *   - stores/agentStore.ts  — agents array, activeAgentId, delegatedAgents
 *   - stores/chatStore.ts   — per-agent slice status for streaming dots
 *
 * Dependents:
 *   Rendered by ChatPanel above the MessageList.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { usePanelStore } from "@/stores/panelStore";
import { useSummaryStore } from "@/stores/summaryStore";
import type { DelegatedAgent } from "@/stores/agentStore";
import { CornerUpLeft, Zap, CheckCircle2, XCircle, Plus, Trash2 } from "lucide-react";

/* Window during which a second click on Clear Session confirms the
   destructive action (Couturier v2 R7). Single click only primes the
   confirm state; if the operator does not click again within this
   window the button reverts and nothing is cleared. */
const CLEAR_CONFIRM_WINDOW_MS = 4000;

export function AgentTabBar() {
  const agents = useAgentStore((s) => s.agents);
  const activeAgentId = useAgentStore((s) => s.activeAgentId);
  const returnToAgentId = useAgentStore((s) => s.returnToAgentId);
  const delegatedAgents = useAgentStore((s) => s.delegatedAgents);
  const createSession = useSessionStore((s) => s.createSession);
  const [confirmClear, setConfirmClear] = useState(false);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tablistRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => {
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
  }, []);

  const handleClearClick = useCallback(() => {
    if (!confirmClear) {
      setConfirmClear(true);
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = setTimeout(() => {
        setConfirmClear(false);
        confirmTimerRef.current = null;
      }, CLEAR_CONFIRM_WINDOW_MS);
      return;
    }
    /* Second click within the confirm window — perform the destructive
       action and reset the priming state. */
    if (confirmTimerRef.current) {
      clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }
    setConfirmClear(false);
    useSummaryStore.getState().resetLocal();
    useChatStore.getState().clearAll();
    usePanelStore.getState().clearPanels();
    useSessionStore.setState({ activeSessionId: null, activeSession: null });
  }, [confirmClear]);

  const onTabKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, index: number, count: number) => {
      let next = index;
      if (e.key === "ArrowRight") next = (index + 1) % count;
      else if (e.key === "ArrowLeft") next = (index - 1 + count) % count;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = count - 1;
      else return;
      e.preventDefault();
      const buttons = tablistRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]',
      );
      buttons?.[next]?.focus();
    },
    [],
  );

  if (agents.length === 0) return null;

  const returnToAgent = agents.find((agent) => agent.id === returnToAgentId);
  const totalTabs = agents.length + delegatedAgents.length;

  return (
    <div className="shrink-0">
      <div
        ref={tablistRef}
        role="tablist"
        aria-label="Agent tabs"
        className="flex items-center border-b border-border bg-header-bg overflow-x-auto gap-1 px-2"
        data-testid="agent-tab-bar"
      >
        {agents.map((agent, index) => {
          const active = activeAgentId === agent.id;
          return (
            <button
              key={agent.id}
              data-testid={`agent-tab-${agent.id}`}
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              onKeyDown={(e) => onTabKeyDown(e, index, totalTabs)}
              onClick={() => useAgentStore.getState().setActiveAgent(agent.id)}
              className={`
                px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors
                border-b-2 flex items-center gap-1.5 rounded-t
                ${active
                  ? "border-accent text-text-primary"
                  : "border-transparent text-header-text/60 hover:text-header-text"
                }
              `}
            >
              <Zap className="h-3.5 w-3.5" />
              {agent.name}
              <StreamingDot agentId={agent.id} />
            </button>
          );
        })}

        {delegatedAgents.length > 0 && (
          <div className="h-5 w-px bg-divider mx-1 shrink-0" />
        )}
        {delegatedAgents.map((da, di) => (
          <SubagentTab
            key={da.id}
            delegated={da}
            isActive={activeAgentId === da.id}
            tabIndex={activeAgentId === da.id ? 0 : -1}
            onKeyDown={(e) => onTabKeyDown(e, agents.length + di, totalTabs)}
          />
        ))}

        <div className="flex-1" />

        <button
          data-testid="new-chat-button"
          onClick={() => createSession()}
          title="New Chat"
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-on-accent bg-brand hover:bg-brand-hover rounded transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New Chat
        </button>

        <button
          data-testid="clear-session-button"
          data-confirm={confirmClear ? "true" : "false"}
          onClick={handleClearClick}
          aria-label={confirmClear ? "Confirm clear session" : "Clear session"}
          title={confirmClear ? "Click again within 4 s to clear" : "Clear Session"}
          className={`flex items-center gap-1 px-2 py-1.5 text-xs rounded transition-colors ${
            confirmClear
              ? "bg-status-error/15 text-status-error border border-status-error/40"
              : "text-text-muted hover:text-status-error hover:bg-status-error/10"
          }`}
        >
          <Trash2 className="h-3.5 w-3.5" />
          {confirmClear && <span className="ml-1">Confirm</span>}
        </button>

        {returnToAgentId && (
          <button
            data-testid="return-to-origin"
            onClick={() => useAgentStore.getState().returnToOrigin()}
            className="px-3 py-2 text-xs font-medium text-brand hover:bg-brand/10 border-b-2 border-transparent transition-colors whitespace-nowrap flex items-center gap-1"
          >
            <CornerUpLeft className="h-3 w-3" />
            Return to {returnToAgent?.name ?? "Origin"}
          </button>
        )}
      </div>
    </div>
  );
}

function StreamingDot({ agentId }: { agentId: string }) {
  const status = useChatStore((s) => s.getSlice(agentId).status);
  if (status !== "streaming") return null;
  return (
    <span
      data-testid={`agent-tab-${agentId}-streaming`}
      className="h-2 w-2 rounded-full bg-status-info animate-pulse shrink-0"
    />
  );
}

function SubagentTab({
  delegated,
  isActive,
  tabIndex,
  onKeyDown,
}: {
  delegated: DelegatedAgent;
  isActive: boolean;
  tabIndex: number;
  onKeyDown: (e: React.KeyboardEvent<HTMLButtonElement>) => void;
}) {
  const sliceStatus = useChatStore((s) => s.getSlice(delegated.id).status);
  return (
    <button
      data-testid={`subagent-tab-${delegated.id}`}
      role="tab"
      aria-selected={isActive}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
      onClick={() => useAgentStore.getState().viewDelegatedTab(delegated.id)}
      title={delegated.task}
      className={`
        px-2.5 py-1.5 text-label font-medium whitespace-nowrap transition-colors
        border-b-2 flex items-center gap-1.5 rounded-t
        ${isActive
          ? "border-accent text-text-primary"
          : "border-transparent text-header-text/50 hover:text-header-text"
        }
      `}
    >
      {delegated.status === "streaming" || sliceStatus === "streaming" ? (
        <span
          data-testid={`subagent-tab-${delegated.id}-streaming`}
          className="h-1.5 w-1.5 rounded-full bg-status-info animate-pulse shrink-0"
        />
      ) : delegated.status === "complete" ? (
        <CheckCircle2 className="h-3 w-3 text-status-success shrink-0" />
      ) : delegated.status === "error" ? (
        <XCircle className="h-3 w-3 text-status-error shrink-0" />
      ) : null}
      {delegated.name}
    </button>
  );
}
