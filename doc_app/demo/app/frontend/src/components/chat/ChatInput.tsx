/**
 * @module ChatInput
 *
 * User message input — auto-resizing textarea with send/abort toggle.
 */

import { useCallback, useRef, KeyboardEvent, FormEvent } from "react";
import { Send, Square } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

export function ChatInput({ agentId }: { agentId: string }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const slice = useChatStore((s) => s.getSlice(agentId));
  const sendMessage = useChatStore((s) => s.sendMessage);
  const abort = useChatStore((s) => s.abort);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);

  const isStreaming = slice.status === "streaming";
  const isDisabled = isStreaming;

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      if (!activeSessionId || isDisabled) return;
      const content = textareaRef.current?.value.trim();
      if (!content) return;
      if (textareaRef.current) {
        textareaRef.current.value = "";
        textareaRef.current.style.height = "auto";
      }
      await sendMessage(activeSessionId, content, agentId);
    },
    [activeSessionId, isStreaming, sendMessage, agentId],
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

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const handleAbort = useCallback(() => {
    if (activeSessionId) abort(activeSessionId, agentId);
  }, [activeSessionId, abort, agentId]);

  if (!activeSessionId) {
    return (
      <div className="border-t border-border bg-neutral-bg1 px-4 py-4">
        <p className="text-center text-sm text-text-muted">
          Select or create a conversation to start chatting.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="shrink-0 bg-neutral-bg1 px-4 py-3">
      <div className="mx-auto flex items-center gap-2 px-2">
        <div className={`flex-1 rounded-2xl border transition-colors ${
          isStreaming
            ? 'border-border-subtle bg-neutral-bg3 opacity-60'
            : 'border-border-subtle bg-neutral-bg2 focus-within:border-border'
        }`}>
          <textarea
            ref={textareaRef}
            data-testid="chat-input-textarea"
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder="Send a message…"
            rows={1}
            disabled={isDisabled}
            className="w-full resize-none rounded-2xl bg-transparent px-4 py-3 text-sm text-text-primary placeholder-text-muted outline-none disabled:opacity-50"
            aria-label="Chat message input"
          />
        </div>

        {isStreaming ? (
          <button
            type="button"
            onClick={handleAbort}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-status-error/20 text-status-error hover:bg-status-error/30 transition-colors"
            aria-label="Stop generating"
            data-testid="abort-button"
          >
            <Square className="h-4 w-4 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand text-on-accent hover:bg-brand-hover transition-colors"
            aria-label="Send message"
            data-testid="send-button"
          >
            <Send className="h-4 w-4" />
          </button>
        )}
      </div>
    </form>
  );
}
