/**
 * @module MessageList
 *
 * Scrollable message list — the vertical timeline of chat messages.
 *
 * Renders all persisted messages from `chatStore.messages` via
 * {@link MessageBubble}, plus an in-flight streaming bubble when
 * `status === 'streaming'`. Uses {@link useAutoScroll} for smart
 * auto-scroll behaviour: follows new content during streaming but
 * pauses when the user manually scrolls up, with a floating
 * "scroll to bottom" button to re-engage.
 *
 * Displays an empty state (icon + prompt text) when no session is
 * active or the conversation has no messages yet.
 *
 * @remarks
 * - No props — all state is consumed from `chatStore`.
 * - The streaming bubble is a synthetic {@link MessageBubble} with
 *   `isStreaming=true` and `streamingParts` from the store.
 *
 * @collaborators
 *   - {@link useChatStore}    — messages, status, streamingParts (read)
 *   - {@link useAutoScroll}   — containerRef, handleScroll, scrollToBottom
 *   - {@link MessageBubble}   — rendered child per message
 *
 * @dependents
 *   Rendered by {@link ChatPanel} as the scrollable body.
 */

import { ArrowDown, MessageSquare, PlusCircle, CornerUpLeft } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useAgentStore } from "@/stores/agentStore";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { MessageBubble } from "./MessageBubble";
import { OverallExecutionTimer } from "./OverallExecutionTimer";

export function MessageList() {
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "controller";
  const messages = useChatStore((s) => s.getSlice(activeAgentId).messages);
  const status = useChatStore((s) => s.getSlice(activeAgentId).status);
  const streamingParts = useChatStore((s) => s.getSlice(activeAgentId).streamingParts);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const createSession = useSessionStore((s) => s.createSession);

  const { containerRef, handleScroll, scrollToBottom, showScrollButton } =
    useAutoScroll({
      threshold: 120,
      deps: [streamingParts.length, messages.length],
    });

  const returnToAgentId = useAgentStore((s) => s.returnToAgentId);
  const returnToOrigin = useAgentStore((s) => s.returnToOrigin);

  // Empty state
  if (messages.length === 0 && status === "idle") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-text-muted">
        <MessageSquare className="h-12 w-12 opacity-30" />
        <div className="text-center">
          <p className="text-lg font-medium">
            {activeSessionId ? 'Start a conversation' : 'No chat session loaded'}
          </p>
          <p className="text-sm mt-1">
            {activeSessionId
              ? 'Type a message below to begin.'
              : 'Create a new session to get started.'}
          </p>
        </div>
        {/* New Chat button — only shown when no session is active */}
        {!activeSessionId && (
          <div className="flex flex-col items-center gap-2 mt-2">
            <button
              onClick={() => createSession()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand/10 border border-brand/30 text-brand text-sm font-medium hover:bg-brand/20 transition-colors"
            >
              <PlusCircle className="h-4 w-4" />
              New Chat
            </button>
          </div>
        )}
      </div>
    );
  }

  // Determine if the last message is the one being streamed
  const isStreaming = status === "streaming";

  return (
    <div className="relative flex-1 overflow-hidden min-h-0">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto scroll-smooth"
      >
        <div className="mx-auto px-6 py-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
            />
          ))}

          {/* Streaming placeholder (assistant response in progress) */}
          {isStreaming && (
            <div className="space-y-1">
              {/* Cumulative wall-clock for the active turn — sits above
                  the streaming bubble so the operator can see at a glance
                  how long the agent has been working overall, in addition
                  to the per-tool timers inside each tool call card. */}
              <div className="flex justify-start pl-2">
                <OverallExecutionTimer />
              </div>
              <MessageBubble
                message={{
                  id: "streaming",
                  role: "assistant",
                  content: "",
                  parts: [],
                  status: "streaming",
                  tool_calls: [],
                  agent_name: "",
                  created_at: new Date().toISOString(),
                }}
                streamingParts={streamingParts}
                isStreaming
              />
            </div>
          )}
        </div>
      </div>

      {/* New messages button — far right */}
      {showScrollButton && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 flex items-center gap-1.5 rounded-full bg-neutral-bg3 px-3 py-1.5 text-xs text-text-secondary shadow-lg border border-border hover:bg-neutral-bg4 transition-colors"
          aria-label="Scroll to bottom"
        >
          <ArrowDown className="h-3.5 w-3.5" />
          <span>New messages</span>
        </button>
      )}

      {/* Return to Origin button — bottom center, only after "View Tab" navigation */}
      {returnToAgentId && (
        <button
          onClick={returnToOrigin}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-neutral-bg3 px-3 py-1.5 text-xs text-text-secondary shadow-lg border border-border hover:bg-neutral-bg4 transition-colors"
          aria-label="Return to origin agent"
        >
          <CornerUpLeft className="h-3.5 w-3.5" />
          <span>Return to Origin</span>
        </button>
      )}
    </div>
  );
}
