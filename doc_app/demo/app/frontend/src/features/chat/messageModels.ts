/**
 * Chat message normalisation helpers.
 *
 * Role:
 *   The frontend renders messages through the `ContentPart[]` model (text +
 *   tool_call parts in order). The backend may emit older messages whose
 *   `parts` field is null/empty \u2014 those must be reconstructed from
 *   `content` and `tool_calls` before render. This module owns that
 *   conversion and the assistant-error/abort placeholder builder.
 *
 * Exports:
 *   - normalizeMessage / normalizeMessages \u2014 ApiMessage \u2192 ChatMessage with a
 *     populated `parts` array (falls back to legacyToParts when absent).
 *   - buildFallbackAssistantMessage \u2014 deterministic placeholder used by
 *     chatStore when streaming aborts or errors before any token arrives.
 *
 * Why a separate module:
 *   Keeps chatStore free of conversion branches and lets MessageBubble and
 *   sessionStore reuse the same normalisation when hydrating cached threads.
 *
 * Key collaborators:
 *   - api/types.ts                    \u2014 ApiMessage, ContentPart, Message
 *   - features/chat/partUtils.ts      \u2014 legacyToParts (the actual transform)
 *   - stores/chatStore.ts             \u2014 normalises stream-finalised messages
 */

import type {
  ApiMessage,
  ContentPart,
  Message,
  MessageStatus,
} from "@/api/types";
import { legacyToParts } from "@/features/chat/partUtils";

export type ChatMessage = Message;

export function normalizeMessage(message: ApiMessage): ChatMessage {
  return {
    ...message,
    parts: message.parts?.length ? message.parts : legacyToParts(message),
  };
}

export function normalizeMessages(messages: ApiMessage[]): ChatMessage[] {
  return messages.map(normalizeMessage);
}

export function buildFallbackAssistantMessage(
  agentId: string,
  status: Extract<MessageStatus, "error" | "aborted">,
  content?: string,
): ChatMessage {
  const resolvedContent = content ?? (status === "aborted" ? "[Aborted]" : "[Error building message]");
  const parts: ContentPart[] = resolvedContent ? [{ type: "text", text: resolvedContent }] : [];

  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: resolvedContent,
    parts,
    tool_calls: [],
    agent_name: agentId,
    status,
    created_at: new Date().toISOString(),
  };
}