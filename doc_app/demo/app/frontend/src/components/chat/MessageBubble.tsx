/**
 * @module MessageBubble
 *
 * Single message renderer — displays one user or assistant message
 * within the conversation timeline.
 *
 * User messages render as plain text in a right-aligned bubble.
 * Assistant messages render an ordered array of {@link ContentPart}
 * objects, each dispatched to its specialised sub-component:
 *   - {@link ToolCallDisplay} — collapsible tool invocation card
 *   - {@link TextBlock}       — markdown-rendered final text
 *
 * Parts are rendered in chronological order exactly as they arrived
 * from the SSE stream, preserving the interleaved tool →
 * text flow. Messages reach this component after normalization in
 * `messageModels.ts`, so the renderer only deals with UI-ready parts.
 *
 * During active streaming, `streamingParts` are rendered instead of
 * persisted parts, and a {@link StreamingIndicator} is appended.
 *
 * @props
 *   - `message`        — the {@link Message} object (id, role, content, parts, status)
 *   - `streamingParts`  — live parts array during SSE generation (optional)
 *   - `isStreaming`     — whether this bubble represents the in-flight response
 *
 * @collaborators
 *   - {@link ToolCallDisplay}   — renders tool_call parts
 *   - {@link TextBlock}         — renders text parts
 *   - {@link StreamingIndicator} — typing dots during streaming
 *
 * @dependents
 *   Rendered by {@link MessageList} for each message in the conversation.
 */

import { useState, memo } from "react";
import { AlertCircle, StopCircle, ChevronRight } from "lucide-react";
import type { ContentPart } from "@/api/types";
import type { ChatMessage } from "@/features/chat/messageModels";
import { MarkdownRenderer } from "../shared/MarkdownRenderer";
import { ToolCallDisplay } from "./ToolCallDisplay";
import { TextBlock } from "./TextBlock";
import { StreamingIndicator } from "./StreamingIndicator";

interface MessageBubbleProps {
  message: ChatMessage;
  /** Streaming parts (only for the current assistant message). */
  streamingParts?: ContentPart[];
  isStreaming?: boolean;
}

export const MessageBubble = memo(function MessageBubble({
  message,
  streamingParts,
  isStreaming = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isError = message.status === "error";
  const isAborted = message.status === "aborted";

  /* Collapsible state — expanded by default, click to collapse to one line */
  const [collapsed, setCollapsed] = useState(false);

  /* Font size — hardcoded default (chatSettingsStore removed) */
  const fontSize = "14px";

  /* Delegation detection — delegation messages get distinct styling. */
  const isDelegation = isUser && (message as any)._isDelegation === true;

  // Determine parts to render — filter out any undefined/null entries
  // that can occur when SSE events arrive with malformed or truncated data.
  const parts: ContentPart[] = (isStreaming
    ? (streamingParts ?? [])
    : message.parts
  ).filter((p): p is ContentPart => p != null && typeof p === "object" && "type" in p);

  const timestamp = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  /** Toggle collapsed state — used by avatar, chevron, and timestamp. */
  const toggleCollapse = (e: React.MouseEvent) => {
    e.stopPropagation();
    setCollapsed((v) => !v);
  };

  return (
    <article
      className="flex gap-1.5 px-3 py-1.5 group/msg"
      aria-label={`${message.role} message at ${timestamp}`}
    >
      {/* Collapse/expand chevron — click to toggle */}
      <ChevronRight
        onClick={toggleCollapse}
        className={`h-4 w-4 shrink-0 mt-1 text-text-muted opacity-60 hover:opacity-100 transition-all cursor-pointer ${
          collapsed ? "" : "rotate-90"
        }`}
      />

      {/* Role glyph — 16 px circular badge that identifies the speaker at a
          glance. `U` for user turns (brand fill), the agent’s first
          initial for assistant turns (neutral fill with brand outline).
          Sits between the chevron and the content so the reading order is
          always chevron → who → what. */}
      <div
        aria-hidden="true"
        className={[
          "h-4 w-4 shrink-0 mt-1 rounded-full flex items-center justify-center text-micro font-bold leading-none select-none",
          isUser
            ? "bg-brand text-on-accent"
            : "bg-neutral-bg2 text-text-secondary border border-brand/40",
        ].join(" ")}
        title={isUser ? (message.agent_name ? `User — ${message.agent_name}` : "User") : (message.agent_name ?? "Assistant")}
      >
        {(() => {
          if (isUser) return "U";
          const name = message.agent_name ?? "Assistant";
          return (name.trim().charAt(0) || "A").toUpperCase();
        })()}
      </div>

      {/* Content — full width, color-coded by role */}
      <div
        className="flex flex-1 min-w-0 flex-col gap-0.5"
        style={{ fontSize, lineHeight: 1.35 }}
      >
        {/* User message — subtle left border + tinted background */}
        {isUser && (
          <div className={`border-l-2 pl-3 py-1.5 rounded-r-lg ${
            isDelegation
              ? "border-l-delegation-border bg-delegation-bg/50 text-delegation-text"
              : "border-l-brand text-text-primary"
          }`}
            style={!isDelegation ? { backgroundColor: "color-mix(in srgb, var(--color-brand) 8%, transparent)" } : undefined}
          >
            {isDelegation && (
              <span className="text-micro font-semibold uppercase tracking-wider text-delegation-label block mb-1">From {message.agent_name}</span>
            )}
            {collapsed ? (
              <p className="truncate">{message.content}</p>
            ) : (
              <MarkdownRenderer content={message.content ?? ""} />
            )}
          </div>
        )}

        {/* Assistant message — interleaved parts */}
        {!isUser && (
          <div className={`w-full ${
            collapsed ? "" : "space-y-0.5"
          }`}>
            {/* Status indicators (always shown) */}
            {isError && (
              <div className="flex items-center gap-1.5 text-status-error text-xs px-1">
                <AlertCircle className="h-3.5 w-3.5" />
                <span>Error generating response</span>
              </div>
            )}
            {isAborted && (
              <div className="flex items-center gap-1.5 text-status-warning text-xs px-1">
                <StopCircle className="h-3.5 w-3.5" />
                <span>Generation stopped</span>
              </div>
            )}

            {/* Collapsed preview — single truncated line from first text part */}
            {collapsed ? (
              <div className="bg-neutral-bg2 text-text-primary rounded-lg px-4 py-2 truncate max-w-full">
                {(() => {
                  const firstText = parts.find((p) => p.type === "text");
                  if (firstText && firstText.type === "text") {
                    const preview = firstText.text.replace(/\n/g, " ").slice(0, 120);
                    return <span className="text-text-secondary">{preview}{firstText.text.length > 120 ? "…" : ""}</span>;
                  }
                  return <span className="text-text-muted italic">collapsed</span>;
                })()}
              </div>
            ) : (
              <>
                {/* Render parts in order — no chain connectors, just spacing. */}
                {parts.map((part, i) => {
                  switch (part.type) {
                    case "text":
                      return <TextBlock key={`text-${i}`} text={part.text} isStreaming={isStreaming} />;
                    case "tool_call":
                      return (
                        <ToolCallDisplay
                          key={part.toolCall.id}
                          toolCall={part.toolCall}
                          isStreaming={isStreaming}
                        />
                      );
                  }
                })}

                {/* Streaming indicator when no parts yet */}
                {isStreaming && parts.length === 0 && (
                  <div className="bg-neutral-bg2 text-text-primary rounded-lg px-4 py-2.5">
                    <StreamingIndicator />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Timestamp — hover-only, also toggles collapse */}
        <span
          onClick={toggleCollapse}
          className="px-2 text-xs text-text-muted cursor-pointer opacity-0 group-hover/msg:opacity-100 transition-opacity"
          title={collapsed ? "Click to expand" : "Click to collapse"}
        >
          {timestamp}
        </span>
      </div>
    </article>
  );
});
