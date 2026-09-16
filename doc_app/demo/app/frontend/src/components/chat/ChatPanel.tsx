/**
 * @module ChatPanel
 *
 * Main chat container — the primary conversational interface for the
 * scenario-driven AI agent application.
 *
 * Composes MessageList (scrollable message history) and ChatInput
 * (user textarea + send/abort controls) into a single vertical flex
 * column. Surfaces an error banner when chatStore.error is set,
 * and a metadata bar (model name, token count, latency) after each
 * completed assistant turn.
 *
 * @remarks
 * - No props — all state is consumed from Zustand stores.
 * - The metadata bar reads `lastMetadata` from chatStore, which is
 *   populated by the SSE stream's final `[DONE]` event.
 *
 * @collaborators
 *   - {@link useChatStore}     — error, lastMetadata (read)
 *   - {@link useSessionStore}  — activeSessionId (read)
 *   - {@link MessageList}      — rendered child (message history)
 *   - {@link ChatInput}        — rendered child (user input)
 *
 * @dependents
 *   Rendered by the root App layout as the right-hand panel.
 */

import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { AgentTabBar } from "./AgentTabBar";
import { SuggestedQueries } from "./SuggestedQueries";
import { PlusCircle } from "lucide-react";

export function ChatPanel() {
  const activeAgentId = useAgentStore((s) => s.activeAgentId);
  const agents = useAgentStore((s) => s.agents);
  const agentId = activeAgentId ?? agents[0]?.id ?? "investigator";
  const activeAgent = agents.find((agent) => agent.id === agentId);

  const error = useChatStore((s) => s.getSlice(agentId).error);
  const errorCode = useChatStore((s) => s.getSlice(agentId).errorCode);
  const messages = useChatStore((s) => s.getSlice(agentId).messages);
  const status = useChatStore((s) => s.getSlice(agentId).status);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const backgroundRun = useSessionStore((s) => s.activeSession?.background_runs?.[agentId] ?? null);
  const isBackgroundActive = backgroundRun?.status === "queued" || backgroundRun?.status === "running";

  const isEmpty = messages.length === 0 && status !== "streaming";

  return (
    <main className="h-full flex flex-col bg-neutral-bg1 overflow-hidden">
      {/* Error banner */}
      {error && (
        <div className="border-b border-status-error/30 bg-status-error/10 px-4 py-2 text-sm text-status-error">
          {error}
          {errorCode && <span className="text-xs opacity-60 ml-2">[{errorCode}]</span>}
        </div>
      )}

      {/* Agent tabs — core agents are always visible; delegated tabs are additive. */}
      <AgentTabBar />

      {isBackgroundActive && (
        <div data-testid={`background-run-banner-${agentId}`} className="border-b border-brand/20 bg-brand/10 px-4 py-2 text-sm text-brand">
          {backgroundRun?.status === "queued"
            ? "Operator task queued."
            : "Operator is working in the background."}
        </div>
      )}

      {isEmpty ? (
        <>
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6">
            <img src="/favicon.png" alt="GridIQ" className="h-16 w-16" />
            <p className="text-sm font-medium text-text-secondary">Ask {activeAgent?.name ?? "GridIQ"}</p>
            <p className="text-xs text-text-tertiary text-center max-w-[260px]">
              {activeAgent?.description ?? "GridIQ can help further analyse alarms, explain system behaviour or surface signals."}
            </p>
            {!activeSessionId && (
              <button
                data-testid="empty-new-chat-button"
                onClick={() => void createSession()}
                className="mt-2 flex items-center gap-2 px-4 py-2 rounded bg-brand text-on-accent text-sm font-medium hover:bg-brand-hover transition-colors"
              >
                <PlusCircle className="h-4 w-4" />
                New Chat
              </button>
            )}
          </div>
          {activeSessionId && (
            <SuggestedQueries
              agentId={agentId}
              onSelect={(query) => sendMessage(activeSessionId, query, agentId)}
            />
          )}
          {/* Couturier v2 F-003: pre-session, the "New Chat" button is the
              single affordance. Rendering ChatInput here would surface the
              contradictory "Select or create a conversation..." disabled
              bottom-bar message immediately below it. */}
          {activeSessionId && <ChatInput agentId={agentId} />}
        </>
      ) : (
        <>
          <MessageList />
          <ChatInput agentId={agentId} />
        </>
      )}
    </main>
  );
}
