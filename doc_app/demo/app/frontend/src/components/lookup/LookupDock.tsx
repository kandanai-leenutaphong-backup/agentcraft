/**
 * DockContent — chat interface for the dock-surface Data Search Assistant.
 *
 * Hosted inside the centre column's "Data Search" workspace mode (see
 * `Workspace`) as of the C1 overhaul (2026-05-17; replaced the former
 * CenterTabs "Data" tab). Exports a frameless `DockContent` component
 * that consumes whatever vertical space its parent provides. A legacy
 * `LookupDock` alias is re-exported so older imports continue to resolve.
 *
 * Role in system: presentation layer for the single `dock`-surface agent.
 * Reads agent roster, active assistant, and session state from `lookupStore`;
 * pushes user messages and reads streaming state via `chatStore`.
 *
 * Collaborators:
 *   - `lookupStore` — dock agent list, active agent, dock session id.
 *   - `chatStore`   — per-agent message slices, streaming, abort.
 *   - `Workspace`   — parent container that mounts this when the
 *                    `centerTab === "data"` workspace mode is active.
 */

import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Search, Send, Square, ChevronDown, ChevronRight, BookOpen } from "lucide-react";
import { useLookupStore } from "@/stores/lookupStore";
import { useChatStore } from "@/stores/chatStore";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer";
import { DOCK_GUIDES } from "@/config/dockGuides";
import type { ContentPart } from "@/api/types";
import type { ChatMessage } from "@/features/chat/messageModels";

/**
 * Dock panel body — assistant header, message list, and input.
 * Fills parent height/width. Returns null while the agent roster is still
 * being fetched so the tab body stays empty rather than flashing chrome.
 */
export function DockContent() {
  const dockAgents = useLookupStore((s) => s.dockAgents);
  const activeDockAgentId = useLookupStore((s) => s.activeDockAgentId);
  const fetchDockAgents = useLookupStore((s) => s.fetchDockAgents);
  const activeAgent = dockAgents.find((agent) => agent.id === activeDockAgentId);

  useEffect(() => {
    if (dockAgents.length === 0) fetchDockAgents();
  }, [dockAgents.length, fetchDockAgents]);

  if (!activeDockAgentId) return null;

  return (
    <div
      data-testid="lookup-dock"
      className="h-full flex flex-col bg-neutral-bg1"
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50 shrink-0">
        <Search className="h-3.5 w-3.5 text-text-muted" />
        <div className="min-w-0">
          <div className="text-xs font-semibold text-text-primary truncate">
            {activeAgent?.name ?? "Data Search Assistant"}
          </div>
          <div className="text-micro text-text-muted truncate">
            Operational data, topology, procedures, incidents, and participants
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        <DockMessages agentId={activeDockAgentId} />
        <DockInput agentId={activeDockAgentId} />
      </div>
    </div>
  );
}

/** Legacy alias — keeps old imports working. */
export const LookupDock = DockContent;

/** Message list for a dock agent — renders from chatStore slice. */
function DockMessages({ agentId }: { agentId: string }) {
  const messages = useChatStore((s) => s.getSlice(agentId).messages);
  const status = useChatStore((s) => s.getSlice(agentId).status);
  const streamingParts = useChatStore((s) => s.getSlice(agentId).streamingParts);
  const containerRef = useRef<HTMLDivElement>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const guide = DOCK_GUIDES[agentId];

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, streamingParts.length]);

  if (messages.length === 0 && status !== "streaming") {
    return (
      <div className="flex-1 flex flex-col overflow-y-auto">
        {guide && (
          <div data-testid="dock-agent-guide" className="px-3 py-2 border-b border-border/30">
            <button
              onClick={() => setGuideOpen(!guideOpen)}
              className="flex items-center gap-1.5 text-xs font-medium text-text-muted hover:text-text-secondary transition-colors w-full text-left"
            >
              {guideOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <BookOpen className="h-3 w-3" />
              {guide.title}
            </button>
            {guideOpen && (
              <div className="mt-2 prose prose-sm max-w-none text-xs text-text-secondary">
                <MarkdownRenderer content={guide.content} />
              </div>
            )}
          </div>
        )}
        <div className="flex-1 flex items-center justify-center text-text-muted text-xs italic">
          Type a query to search operational data, topology, or knowledge bases
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-2 scroll-smooth">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {status === "streaming" && streamingParts.length > 0 && (
        <MessageBubble
          key="streaming"
          message={{
            id: "dock-streaming",
            role: "assistant",
            content: "",
            parts: streamingParts as ContentPart[],
            status: "streaming",
            tool_calls: [],
            agent_name: agentId,
            created_at: new Date().toISOString(),
          } as ChatMessage}
          isStreaming
          streamingParts={streamingParts as ContentPart[]}
        />
      )}
    </div>
  );
}

/** Input bar — sends via chatStore using the dock-scoped session. */
function DockInput({ agentId }: { agentId: string }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const status = useChatStore((s) => s.getSlice(agentId).status);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const abort = useChatStore((s) => s.abort);
  const ensureDockSession = useLookupStore((s) => s.ensureDockSession);
  const isStreaming = status === "streaming";

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      if (isStreaming) return;
      const content = textareaRef.current?.value.trim();
      if (!content) return;
      const sessionId = await ensureDockSession();
      if (!sessionId) return;
      if (textareaRef.current) {
        textareaRef.current.value = "";
        textareaRef.current.style.height = "auto";
      }
      await sendMessage(sessionId, content, agentId);
    },
    [isStreaming, sendMessage, agentId, ensureDockSession],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleAbort = useCallback(async () => {
    const sessionId = useLookupStore.getState().dockSessionId;
    if (sessionId) abort(sessionId, agentId);
  }, [abort, agentId]);

  return (
    <div className="shrink-0 border-t border-border/50 px-3 py-2 bg-neutral-bg1">
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          placeholder="Search data, topology, procedures, or participants..."
          rows={1}
          disabled={isStreaming}
          onKeyDown={handleKeyDown}
          onInput={() => {
            const el = textareaRef.current;
            if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 100)}px`; }
          }}
          className="flex-1 resize-none bg-neutral-bg2 rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted border border-border/50 focus:border-brand/50 focus:outline-none min-h-[36px]"
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={handleAbort}
            className="shrink-0 p-2 rounded-lg bg-status-error text-on-accent hover:bg-status-error/80 transition-colors"
          >
            <Square className="h-4 w-4" />
          </button>
        ) : (
          <button
            type="submit"
            className="shrink-0 p-2 rounded-lg bg-brand text-on-accent hover:bg-brand/80 transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        )}
      </form>
    </div>
  );
}
