/**
 * Slice reducers — pure functions for mutating AgentChatSlice streaming state.
 *
 * Module role:
 *   Extracts the duplicated event-handling logic from chatStore's sendMessage
 *   callbacks and handleDelegationEvent into reusable pure functions. Each
 *   function takes a slice, applies a mutation, and returns the partial state
 *   update for Zustand's set().
 *
 *   These functions have zero side effects and zero store dependencies —
 *   they operate only on the plain AgentChatSlice object passed to them.
 *
 * Key collaborators:
 *   - stores/chatStore.ts — calls these from onToken/onToolCallStart/etc.
 *   - features/chat/partUtils.ts — generateToolSummary for tool results
 *   - features/chat/messageBuilder.ts — buildAssistantMessage for finalize
 *
 * Dependents:
 *   Used by: chatStore.ts (sendMessage callbacks + handleDelegationEvent)
 */

import type { ToolCall, ContentPart } from "@/api/types";
import { generateToolSummary } from "@/features/chat/partUtils";

/** Minimal subset of AgentChatSlice needed by reducers. */
export interface SliceState {
  streamingParts: ContentPart[];
  streamingToolIndex: Map<string, number>;
  _toolStartTimes: Map<string, number>;
  hasSeenToolCall: boolean;
  lastEventWasToolResult: boolean;
}

/**
 * Append a text token to the streaming parts.
 * If the last part is text, appends to it; otherwise pushes
 * a new text part.
 */
export function appendToken(
  parts: ContentPart[],
  token: string,
): { streamingParts: ContentPart[] } {
  const updated = [...parts];
  const last = updated[updated.length - 1];
  if (last && last.type === "text") {
    updated[updated.length - 1] = { ...last, text: last.text + token };
  } else {
    updated.push({ type: "text", text: token });
  }
  return { streamingParts: updated };
}

/**
 * Start a new tool call — creates the ToolCall part and updates indexes.
 */
export function startToolCall(
  s: SliceState,
  id: string,
  name: string,
): Partial<SliceState> {
  const parts = [...s.streamingParts];
  const now = Date.now();
  const toolCall: ToolCall = { id, name, arguments: {}, status: "running", start_ms: now };
  const newIndex = parts.length;
  parts.push({ type: "tool_call", toolCall });
  const toolIndex = new Map(s.streamingToolIndex);
  toolIndex.set(id, newIndex);
  const startTimes = new Map(s._toolStartTimes);
  startTimes.set(id, now);
  return {
    streamingParts: parts,
    streamingToolIndex: toolIndex,
    _toolStartTimes: startTimes,
    hasSeenToolCall: true,
    lastEventWasToolResult: false,
  };
}

/**
 * End a tool call — updates arguments on the existing part.
 */
export function endToolCall(
  s: SliceState,
  id: string,
  args: Record<string, unknown>,
): Partial<SliceState> {
  const idx = s.streamingToolIndex.get(id);
  if (idx === undefined) return {};
  const parts = [...s.streamingParts];
  const part = parts[idx];
  if (!part || part.type !== "tool_call") return {};
  // Install authoritative arguments and clear any pending raw fragment
  // — the partial JSON buffer is only meaningful while the call is
  // still streaming.
  parts[idx] = {
    type: "tool_call",
    toolCall: { ...part.toolCall, arguments: args, pendingArgsRaw: undefined },
  };
  return { streamingParts: parts };
}

/**
 * Append one TOOL_CALL_DELTA fragment to the in-flight tool call.
 *
 * The backend ToolCallBuffer streams partial JSON fragments via
 * TOOL_CALL_DELTA before emitting TOOL_CALL_END with the parsed dict.
 * This reducer concatenates fragments into ``pendingArgsRaw`` and tries
 * to parse — when the buffer becomes valid JSON, ``arguments`` is
 * eagerly installed so the UI can flip from the raw streaming view to
 * the structured ArgumentsGrid without waiting for the END event.
 *
 * Returns ``{}`` (no-op) when no streaming part exists for this id —
 * delegation/background events route through their own slices and may
 * arrive here as orphans during late-binding.
 */
export function appendToolCallArgumentsDelta(
  s: SliceState,
  id: string,
  delta: string,
): Partial<SliceState> {
  if (!delta) return {};
  const idx = s.streamingToolIndex.get(id);
  if (idx === undefined) return {};
  const parts = [...s.streamingParts];
  const part = parts[idx];
  if (!part || part.type !== "tool_call") return {};
  // Concatenate the new fragment onto any prior raw buffer. If the call
  // was somehow already parsed (eager close) we defensively reset.
  const newRaw = (part.toolCall.pendingArgsRaw ?? "") + delta;
  let parsedArgs = part.toolCall.arguments;
  let pending: string | undefined = newRaw;
  // Eager parse — succeeds once the closing brace arrives. Wrap any
  // non-object result so the contract (Record<string, unknown>) holds.
  try {
    const candidate = JSON.parse(newRaw) as unknown;
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      parsedArgs = candidate as Record<string, unknown>;
    } else {
      parsedArgs = { value: candidate };
    }
    pending = undefined;
  } catch {
    // Still partial — keep the raw buffer for the next delta.
  }
  parts[idx] = {
    type: "tool_call",
    toolCall: {
      ...part.toolCall,
      arguments: parsedArgs,
      pendingArgsRaw: pending,
    },
  };
  return { streamingParts: parts };
}

/**
 * Apply a tool result — updates status, summary, duration on the tool call part.
 */
export function applyToolResult(
  s: SliceState,
  id: string,
  name: string,
  result: string,
): Partial<SliceState> {
  const idx = s.streamingToolIndex.get(id);
  if (idx === undefined) return {};
  const parts = [...s.streamingParts];
  const part = parts[idx];
  if (!part || part.type !== "tool_call") return {};
  const isError = result.includes('"error"') && result.includes("true");
  const startTime = s._toolStartTimes.get(id);
  const duration_ms = startTime ? Date.now() - startTime : null;
  parts[idx] = {
    type: "tool_call",
    toolCall: {
      ...part.toolCall,
      result,
      status: isError ? "error" : "complete",
      summary: generateToolSummary(name, result),
      duration_ms,
    },
  };
  return { streamingParts: parts, lastEventWasToolResult: true };
}
