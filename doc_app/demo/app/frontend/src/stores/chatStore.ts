/**
 * Chat store — per-agent message slices and streaming state.
 *
 * Module role:
 *   Zustand store that owns all chat-related state, organized as a map of
 *   per-agent slices. Each slice holds its own messages, streaming status,
 *   content parts, tool call index, and abort controller. This enables
 *   independent, concurrent chat sessions per agent tab.
 *
 * State machine (per slice):
 *   IDLE → user sends message → STREAMING → events arrive → DONE/ERROR
 *                                    ↓
 *                                  ABORT → ABORTED
 *
 * Key collaborators:
 *   - api/chatApi.ts (re-exported via api/client.ts) — streamChat /
 *     subscribeBackground / abortChat
 *   - stores/sessionStore.ts       — refreshes session after stream completes
 *   - stores/agentStore.ts         — provides activeAgentId
 *   - features/chat/sliceReducers  — pure reducers for streaming events
 *   - features/chat/messageBuilder + messageModels — assistant-message
 *                                     finalisation and ApiMessage → ChatMessage
 *                                     normalisation
 *   - components/chat/MessageList  — renders slice messages
 *   - components/chat/StreamingIndicator — renders streamingParts mid-stream
 *
 * Dependents:
 *   ChatPanel, ChatInput, MessageList, StreamingIndicator, MessageBubble,
 *   AgentTabBar, ContextInspector.
 */

import { create } from "zustand";
import type {
  ApiMessage,
  StreamMetadata,
  ContentPart,
  AgentThread,
} from "@/api/types";
import * as api from "@/api/client";
import { useSessionStore } from "./sessionStore";
import { IS_KIOSK } from "@/foundation/constants";
import { kioskFakeReply } from "@/demo/kioskReplies";
import { buildAssistantMessage } from "@/features/chat/messageBuilder";
import { syncMessageIds } from "@/features/chat/idSync";
import {
  buildFallbackAssistantMessage,
  normalizeMessages,
  type ChatMessage,
} from "@/features/chat/messageModels";
import {
  appendToken as _appendToken,
  startToolCall as _startToolCall,
  endToolCall as _endToolCall,
  applyToolResult as _applyToolResult,
  appendToolCallArgumentsDelta as _appendToolCallArgumentsDelta,
} from "@/features/chat/sliceReducers";

type ChatStatus = "idle" | "streaming" | "error";



// ── Per-agent chat slice ────────────────────────────────────────────────────

/** All state for one agent's chat tab. */
export interface AgentChatSlice {
  messages: ChatMessage[];
  status: ChatStatus;
  streamingParts: ContentPart[];
  streamingToolIndex: Map<string, number>;
  /** Tracks tool call start timestamps for duration calculation (tool_id → Date.now()) */
  _toolStartTimes: Map<string, number>;
  hasSeenToolCall: boolean;
  lastEventWasToolResult: boolean;
  lastMetadata: StreamMetadata | null;
  error: string | null;
  errorCode: string | null;
  errorId: string | null;
  rateLimitCountdown: number | null;
  _sendTimestamp: number | null;
  _firstTokenReceived: boolean;
  ttftMs: number | null;
  ttltMs: number | null;
  ttftHistory: number[];
  ttltHistory: number[];
  _abortController: AbortController | null;
  _streamingTimeout: ReturnType<typeof setTimeout> | null;
}

/* Auto-summarize trigger. Fires the summarizer over the just-completed
 * GridManager turn so the operator gets a glance-readable recap without
 * having to click Summarize. Used by both the onDone and onAborted
 * handlers below so a normal stop AND an operator abort both trigger
 * the recap. Gated on:
 *   - agentId is a GridManager surface (default or legacy alias) —
 *     specialist / hidden agents have no SituationSummaryCard.
 *   - summaryStore not already running — server-side is idempotent but
 *     parallel calls waste tokens.
 *   - Thread has at least one user message — empty sessions have
 *     nothing to summarize.
 * Dynamic imports keep chatStore free of agentStore + summaryStore
 * import cycles (same pattern as the delegation hooks below). */
function triggerAutoSummary(
  agentId: string,
  sessionId: string | undefined,
  threadMessages: ApiMessage[],
): void {
  if (!sessionId) return;
  void Promise.all([
    import("@/stores/agentStore"),
    import("@/stores/summaryStore"),
  ]).then(([{ useAgentStore }, { useSummaryStore }]) => {
    const agents = useAgentStore.getState().agents;
    const defaultAgentId = agents.find((a) => a.is_default)?.id;
    const isGridManagerSurface =
      agentId === defaultAgentId ||
      agentId === "grid_manager" ||
      agentId === "investigator" ||
      agentId === "dispatcher";
    if (!isGridManagerSurface) return;
    if (useSummaryStore.getState().loading) return;
    if (!threadMessages.some((m) => m.role === "user")) return;
    void useSummaryStore.getState().run(sessionId);
  });
}

/** Factory: creates a default empty slice. */
function createDefaultSlice(): AgentChatSlice {
  return {
    messages: [],
    status: "idle",
    streamingParts: [],
    streamingToolIndex: new Map(),
    _toolStartTimes: new Map(),
    hasSeenToolCall: false,
    lastEventWasToolResult: false,
    lastMetadata: null,
    error: null,
    errorCode: null,
    errorId: null,
    rateLimitCountdown: null,
    _sendTimestamp: null,
    _firstTokenReceived: false,
    ttftMs: null,
    ttltMs: null,
    ttftHistory: [],
    ttltHistory: [],
    _abortController: null,
    _streamingTimeout: null,
  };
}

// ── Store ────────────────────────────────────────────────────────────────────

interface ChatState {
  /** Per-agent chat state. Keyed by agent ID (e.g. "controller"). */
  slices: Record<string, AgentChatSlice>;

  /** Get the slice for an agent (lazy-creates if missing). */
  getSlice: (agentId: string) => AgentChatSlice;

  /** Send a message to a specific agent. */
  sendMessage: (sessionId: string, content: string, agentId: string) => Promise<void>;

  /** Abort an in-flight stream for a specific agent. */
  abort: (sessionId: string, agentId: string) => void;

  /** Set messages for a specific agent (e.g. on session load). */
  setMessages: (agentId: string, messages: ApiMessage[]) => void;

  /** Load a session's threads, populating each agent slice from its thread. */
  loadSessionMessages: (threads: Record<string, AgentThread>, defaultAgentId: string) => void;

  /** Clear a specific agent's chat state. */
  clearChat: (agentId: string) => void;

  /** Clear ALL agent slices (e.g. on session change). */
  clearAll: () => void;

  /** Handle a delegation event from the session event bus.
   *  Routes delegation streaming events to the correct agent slice. */
  handleDelegationEvent: (agentId: string, eventType: string, data: Record<string, unknown>) => void;

  /** Handle an async background-run event from the background SSE stream. */
  handleBackgroundEvent: (agentId: string, eventType: string, data: Record<string, unknown>) => void;

  /** Seed placeholder messages for agents whose slices are empty.
   *  Placeholders are replaced on the first real message send. */
  seedPlaceholderMessages: (agentIds: string[]) => void;
}

// ── Slice helpers (module-level, initialized when store is created) ──────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _set: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _get: any;

function _getSlice(agentId: string): AgentChatSlice {
  const s = _get().slices[agentId];
  if (s) return s;
  const fresh = createDefaultSlice();
  _set((state: ChatState) => ({
    slices: { ...state.slices, [agentId]: fresh },
  }));
  return fresh;
}

function _setSlice(agentId: string, patch: Partial<AgentChatSlice>) {
  _set((state: ChatState) => {
    const current = state.slices[agentId] ?? createDefaultSlice();
    return {
      slices: {
        ...state.slices,
        [agentId]: { ...current, ...patch },
      },
    };
  });
}

function _updateSlice(
  agentId: string,
  updater: (slice: AgentChatSlice) => Partial<AgentChatSlice>,
) {
  _set((state: ChatState) => {
    const current = state.slices[agentId] ?? createDefaultSlice();
    const patch = updater(current);
    return {
      slices: {
        ...state.slices,
        [agentId]: { ...current, ...patch },
      },
    };
  });
}

/* ── Placeholder chat data — rich fake data for every agent/tool type ───── */

import { PLACEHOLDER_CHAT_DATA } from "./placeholderChatData";

export const useChatStore = create<ChatState>((set, get) => {
  /* Capture set/get for module-level helpers */
  _set = set;
  _get = get;

  /* Return the store object */
  const store: ChatState = {
    slices: {},

    getSlice: _getSlice,

    sendMessage: async (sessionId: string, content: string, agentId: string) => {
      const slice = _getSlice(agentId);
      if (slice.status === "streaming") return;

      // Do NOT clear subagent tabs — they persist across messages in FAE mode

      /* Strip placeholder messages (id starts with "ph-") on first real send
         so the demo data doesn't persist alongside real conversation. */
      const realMessages = slice.messages.filter((m) => !m.id.startsWith("ph-"));

      const userMessage: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: "user",
        content,
        parts: [{ type: "text", text: content }],
        status: "complete",
        tool_calls: [],
        agent_name: "",
        created_at: new Date().toISOString(),
      };

      const abortController = new AbortController();

      _setSlice(agentId, {
        messages: [...realMessages, userMessage],
        status: "streaming",
        streamingParts: [],
        streamingToolIndex: new Map(),
        hasSeenToolCall: false,
        lastEventWasToolResult: false,
        error: null,
        rateLimitCountdown: null,
        _abortController: abortController,
        _streamingTimeout: null,
        _sendTimestamp: Date.now(),
        _firstTokenReceived: false,
        ttftMs: null,
        ttltMs: null,
      });

      if (IS_KIOSK) {
        const reply = kioskFakeReply(agentId, content);
        const assistantMessage: ChatMessage = {
          id: `kiosk-${Date.now()}`,
          role: "assistant",
          content: reply,
          parts: [{ type: "text", text: reply }],
          status: "complete",
          tool_calls: [],
          agent_name: agentId,
          created_at: new Date().toISOString(),
        };
        _setSlice(agentId, {
          status: "idle",
          messages: [...realMessages, userMessage, assistantMessage],
          streamingParts: [],
          streamingToolIndex: new Map(),
          hasSeenToolCall: false,
          lastEventWasToolResult: false,
          _abortController: null,
          _streamingTimeout: null,
          rateLimitCountdown: null,
        });
        return;
      }

      // ── Idle-timeout guard (per-agent) ────────────────────────────
      const IDLE_TIMEOUT_MS = 300_000;

      const _fireStreamTimeout = () => {
        const cur = _getSlice(agentId);
        if (cur.status !== "streaming") return;
        if (cur.streamingParts.length > 0) {
          let partialMsg: ChatMessage;
          try {
            partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
          } catch (err) {
            console.error("[chatStore] buildAssistantMessage failed:", err);
            partialMsg = buildFallbackAssistantMessage(agentId, "error");
          }
          _setSlice(agentId, {
            status: "error",
            error: "Stream timed out — partial response preserved above.",
            messages: [...cur.messages, partialMsg],
            streamingParts: [],
            _abortController: null,
            _streamingTimeout: null,
          });
        } else {
          _setSlice(agentId, {
            status: "error",
            error: "Stream timed out — no response received.",
            _abortController: null,
            _streamingTimeout: null,
          });
        }
      };

      const _resetIdleTimeout = (ms: number = IDLE_TIMEOUT_MS) => {
        const cur = _getSlice(agentId);
        if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
        const tid = setTimeout(_fireStreamTimeout, ms);
        _setSlice(agentId, { _streamingTimeout: tid });
      };

      _resetIdleTimeout();

      try {
        // Context depth — hardcoded default (chatSettingsStore removed)
        const contextDepth = 10;
        await api.streamChat(
          sessionId,
          { content, max_context_turns: contextDepth },
          {
            onToken: (token) => {
              _resetIdleTimeout();
              const st = _getSlice(agentId);
              if (!st._firstTokenReceived && st._sendTimestamp) {
                const ttft = Date.now() - st._sendTimestamp;
                _setSlice(agentId, {
                  _firstTokenReceived: true,
                  ttftMs: ttft,
                  ttftHistory: [...st.ttftHistory, ttft],
                });
              }
              if (_getSlice(agentId).rateLimitCountdown !== null) {
                _setSlice(agentId, { rateLimitCountdown: null });
              }
              _updateSlice(agentId, (s) => _appendToken(s.streamingParts, token));
            },

            onToolCallStart: (id, name) => {
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _startToolCall(s, id, name));
            },

            onToolCallDelta: (id, argumentsDelta) => {
              // Per-chunk tool argument fragments — reducer concatenates
              // into pendingArgsRaw and eagerly parses once the JSON
              // closes so the UI can flip from the streaming view to
              // ArgumentsGrid without waiting for TOOL_CALL_END.
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _appendToolCallArgumentsDelta(s, id, argumentsDelta));
            },

            onToolCallEnd: (id, _name, args) => {
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _endToolCall(s, id, args));
              // Route panel tool results to the panel store. `classify`
              // is included here even though it doesn't follow the
              // `update_*` / `push_*` naming convention — it owns the
              // ClassifyVerdictCard panel slot (Phase 2 workstream C,
              // 2026-05-18) and needs the same hydration path.
              if (
                _name.startsWith("update_")
                || _name === "push_priority_action"
                || _name === "push_action"
                || _name === "classify"
              ) {
                import("@/stores/panelStore").then(({ usePanelStore }) => {
                  usePanelStore.getState().updatePanel(_name, args);
                });
              }
              // Detect dispatcher delegation — start background SSE subscription
              // When delegate_to_agent fires for the dispatcher, the backend queues
              // it as a background run. We create the tab and subscribe to the
              // background endpoint to stream dispatcher events live.
              if (_name === "delegate_to_agent" && typeof args.agent_id === "string") {
                const bgAgentId = args.agent_id as string;
                const bgTask = (args.task as string) || "";
                // Create ephemeral tab for the background agent.
                import("@/stores/agentStore").then(({ useAgentStore }) => {
                  useAgentStore.getState().addDelegatedAgent(bgAgentId, bgAgentId, bgTask);
                });
                // Pre-initialize streaming state so early tokens render immediately
                get().handleBackgroundEvent(bgAgentId, "start", { task: bgTask });
                // Open background SSE — fire-and-forget, events route to handleBackgroundEvent
                api.subscribeBackground(sessionId, bgAgentId, {
                  onStart: (_evAgentId, task) => {
                    get().handleBackgroundEvent(bgAgentId, "start", { task });
                  },
                  onToken: (_evAgentId, token) => {
                    get().handleBackgroundEvent(bgAgentId, "token", { token });
                  },
                  onToolCallStart: (_evAgentId, tcId, tcName) => {
                    get().handleBackgroundEvent(bgAgentId, "tool_call_start", { id: tcId, name: tcName });
                  },
                  onToolCallDelta: (_evAgentId, tcId, tcDelta) => {
                    get().handleBackgroundEvent(bgAgentId, "tool_call_delta", { id: tcId, arguments_delta: tcDelta });
                  },
                  onToolCallEnd: (_evAgentId, tcId, tcName, tcArgs) => {
                    get().handleBackgroundEvent(bgAgentId, "tool_call_end", { id: tcId, name: tcName, arguments: tcArgs });
                  },
                  onToolResult: (_evAgentId, tcId, tcName, tcResult) => {
                    get().handleBackgroundEvent(bgAgentId, "tool_result", { id: tcId, name: tcName, result: tcResult });
                  },
                  onDone: () => {
                    get().handleBackgroundEvent(bgAgentId, "done", {});
                    import("@/stores/agentStore").then(({ useAgentStore }) => {
                      useAgentStore.getState().updateDelegatedStatus(bgAgentId, "complete");
                    });
                  },
                  onError: (_evAgentId, error) => {
                    get().handleBackgroundEvent(bgAgentId, "error", { error });
                    import("@/stores/agentStore").then(({ useAgentStore }) => {
                      useAgentStore.getState().updateDelegatedStatus(bgAgentId, "error");
                    });
                  },
                  onAborted: () => {
                    get().handleBackgroundEvent(bgAgentId, "aborted", {});
                    import("@/stores/agentStore").then(({ useAgentStore }) => {
                      useAgentStore.getState().updateDelegatedStatus(bgAgentId, "error");
                    });
                  },
                }, abortController.signal).catch((err) => {
                  console.error("[chatStore] background subscription failed:", err);
                });
              }
            },

            onToolResult: (id, name, result) => {
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _applyToolResult(s, id, name, result));
              try {
                const parsed = JSON.parse(result) as { panel?: string; actions?: unknown[] };
                if (parsed.panel === "priority_actions" && Array.isArray(parsed.actions)) {
                  import("@/stores/panelStore").then(({ usePanelStore }) => {
                    usePanelStore.getState().updatePanel("update_priority_actions", parsed as Record<string, unknown>);
                  });
                }
              } catch {
                // Ignore non-JSON tool results.
              }
            },

            onCitation: () => {},

            onMetadata: (data) => {
              _setSlice(agentId, { lastMetadata: data as unknown as StreamMetadata });
            },

            onRateLimited: (retryAfter) => {
              _setSlice(agentId, { rateLimitCountdown: retryAfter });
              _resetIdleTimeout((retryAfter + 120) * 1000);
            },

            onKeepalive: () => {
              _resetIdleTimeout();
            },

            // ── Delegation → agent tab events ──────────────────────
            onDelegationStart: (agentId, agentName, task) => {
              _resetIdleTimeout();
              // Inject delegation task as a pastel-orange message in the specialist's tab
              const delegationMsg: ChatMessage = {
                id: crypto.randomUUID(),
                role: "user",
                content: task,
                parts: [{ type: "text", text: task }],
                status: "complete",
                tool_calls: [],
                agent_name: "",
                created_at: new Date().toISOString(),
                _isDelegation: true,
              };
              const cur = _getSlice(agentId);
              _setSlice(agentId, { messages: [...cur.messages, delegationMsg] });
              // Route to specialist agent's tab slice
              get().handleDelegationEvent(agentId, "delegation_start", { agent_name: agentName, task });
              // Register ephemeral subagent tab.
              import("@/stores/agentStore").then(({ useAgentStore }) => {
                useAgentStore.getState().addDelegatedAgent(agentId, agentName, task);
              });
            },
            onDelegationToken: (agentId, token) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "token", { token });
            },
            onDelegationToolStart: (agentId, toolId, toolName) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "tool_call_start", { id: toolId, name: toolName });
            },
            onDelegationToolDelta: (agentId, toolId, argumentsDelta) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "tool_call_delta", {
                id: toolId,
                arguments_delta: argumentsDelta,
              });
            },
            onDelegationToolEnd: (agentId, toolId, toolName, args) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "tool_call_end", {
                id: toolId,
                name: toolName,
                arguments: args,
              });
            },
            onDelegationToolResult: (agentId, toolId, toolName, result) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "tool_result", { id: toolId, name: toolName, result });
            },
            onDelegationDone: (agentId) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "done", {});
              // Update ephemeral tab status
              import("@/stores/agentStore").then(({ useAgentStore }) => {
                useAgentStore.getState().updateDelegatedStatus(agentId, "complete");
              });
            },
            onDelegationError: (agentId, error) => {
              _resetIdleTimeout();
              get().handleDelegationEvent(agentId, "error", { error });
              // Update ephemeral tab status
              import("@/stores/agentStore").then(({ useAgentStore }) => {
                useAgentStore.getState().updateDelegatedStatus(agentId, "error");
              });
            },

            onError: (error, errorCode, errorId) => {
              const cur = _getSlice(agentId);
              if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
              if (cur.streamingParts.length > 0) {
                let partialMsg: ChatMessage;
                try {
                  partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
                } catch (err) {
                  console.error("[chatStore] buildAssistantMessage failed:", err);
                  partialMsg = buildFallbackAssistantMessage(agentId, "error");
                }
                _setSlice(agentId, {
                  status: "error",
                  error,
                  errorCode: errorCode ?? null,
                  errorId: errorId ?? null,
                  messages: [...cur.messages, partialMsg],
                  streamingParts: [],
                  rateLimitCountdown: null,
                  _abortController: null,
                  _streamingTimeout: null,
                });
              } else {
                _setSlice(agentId, {
                  status: "error",
                  error,
                  errorCode: errorCode ?? null,
                  errorId: errorId ?? null,
                  rateLimitCountdown: null,
                  _abortController: null,
                  _streamingTimeout: null,
                });
              }
            },

            onDone: () => {
              const cur = _getSlice(agentId);
              if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
              const ttlt = cur._sendTimestamp ? Date.now() - cur._sendTimestamp : null;
              if (ttlt) _setSlice(agentId, { ttltMs: ttlt, ttltHistory: [...cur.ttltHistory, ttlt] });

              let assistantMessage: ChatMessage;
              try {
                assistantMessage = buildAssistantMessage(cur.streamingParts, agentId, "complete");
              } catch (err) {
                console.error("[chatStore] buildAssistantMessage failed:", err);
                assistantMessage = buildFallbackAssistantMessage(agentId, "error");
              }

              _setSlice(agentId, {
                status: "idle",
                messages: [...cur.messages, assistantMessage],
                streamingParts: [],
                streamingToolIndex: new Map(),
                hasSeenToolCall: false,
                lastEventWasToolResult: false,
                rateLimitCountdown: null,
                _abortController: null,
                _streamingTimeout: null,
              });

              const completedSessionId = useSessionStore.getState().activeSession?.id;
              useSessionStore
                .getState()
                .refreshActiveSession()
                .then(() => {
                  if (useSessionStore.getState().activeSession?.id !== completedSessionId) return;
                  const session = useSessionStore.getState().activeSession;
                  if (!session) return;
                  const localMessages = _getSlice(agentId).messages;
                  const thread = session.threads?.[agentId];
                  const serverMessages = normalizeMessages(thread?.messages?.filter((m: ApiMessage) => m.role !== "system") ?? []);
                  _setSlice(agentId, { messages: syncMessageIds(localMessages, serverMessages) });
                  triggerAutoSummary(agentId, completedSessionId, thread?.messages ?? []);
                });
            },

            onAborted: () => {
              const cur = _getSlice(agentId);
              let abortedMessage: ChatMessage;
              try {
                abortedMessage = buildAssistantMessage(cur.streamingParts, agentId, "aborted");
              } catch (err) {
                console.error("[chatStore] buildAssistantMessage failed:", err);
                abortedMessage = buildFallbackAssistantMessage(agentId, "aborted");
              }

              _setSlice(agentId, {
                status: "idle",
                messages: [...cur.messages, abortedMessage],
                streamingParts: [],
                streamingToolIndex: new Map(),
                hasSeenToolCall: false,
                lastEventWasToolResult: false,
                _abortController: null,
              });

              const completedSessionId = useSessionStore.getState().activeSession?.id;
              useSessionStore
                .getState()
                .refreshActiveSession()
                .then(() => {
                  if (useSessionStore.getState().activeSession?.id !== completedSessionId) return;
                  const session = useSessionStore.getState().activeSession;
                  if (!session) return;
                  const localMessages = _getSlice(agentId).messages;
                  const thread = session.threads?.[agentId];
                  const serverMessages = normalizeMessages(thread?.messages?.filter((m: ApiMessage) => m.role !== "system") ?? []);
                  _setSlice(agentId, { messages: syncMessageIds(localMessages, serverMessages) });
                  triggerAutoSummary(agentId, completedSessionId, thread?.messages ?? []);
                });
            },
          },
          abortController.signal,
          agentId,
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          _setSlice(agentId, {
            status: "error",
            error: (err as Error).message,
            _abortController: null,
          });
        }
      }
    },

    abort: (sessionId: string, agentId: string) => {
      const slice = _getSlice(agentId);
      if (slice._abortController) {
        slice._abortController.abort();
        _setSlice(agentId, { _abortController: null });
      }
      // Pass agentId so the backend can abort the correct generation.
      // During delegation the backend cascades to the orchestrator's
      // abort event, which the delegation tool checks on each update.
      api.abortGeneration(sessionId, agentId).catch(() => {});
    },

    setMessages: (agentId: string, messages: ApiMessage[]) => {
      _setSlice(agentId, {
        messages: normalizeMessages(messages),
      });
    },

    loadSessionMessages: (threads: Record<string, AgentThread>, _defaultAgentId: string) => {
      /* Load messages from per-agent threads. Each thread's messages are
         loaded into the corresponding agent slice. System messages (role=system)
         are excluded from the rendered list but remain available in the data.
         Also restores lastMetadata from the last assistant message's
         context_snapshot so Session Metrics display on reload. */
      for (const [agentId, thread] of Object.entries(threads)) {
        const currentSlice = _getSlice(agentId);
        if (currentSlice.status === "streaming") continue;

        const displayMessages = (thread.messages ?? []).filter((m: ApiMessage) => m.role !== "system");

        // Extract lastMetadata from the last assistant message's context_snapshot
        let restoredMetadata: StreamMetadata | null = null;
        for (let i = displayMessages.length - 1; i >= 0; i--) {
          const msg = displayMessages[i];
          if (msg.role === "assistant" && msg.context_snapshot) {
            const cs = msg.context_snapshot as Record<string, unknown>;
            restoredMetadata = {
              prompt_tokens: (cs.prompt_tokens as number) || (cs.tokens_used as number) || 0,
              completion_tokens: (cs.completion_tokens as number) || 0,
              total_tokens: (cs.total_tokens as number) || (cs.tokens_used as number) || 0,
              duration_ms: (cs.duration_ms as number) || 0,
              model: (cs.model as string) || "",
              assistant_message_id: msg.id,
              estimated_cost_usd: (cs.estimated_cost_usd as number) || undefined,
            };
            break;
          }
        }

        _setSlice(agentId, {
          messages: normalizeMessages(displayMessages),
          ...(restoredMetadata ? { lastMetadata: restoredMetadata } : {}),
        });
      }
    },

    clearChat: (agentId: string) => {
      const cur = _getSlice(agentId);
      if (cur._abortController) cur._abortController.abort();
      if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
      _setSlice(agentId, createDefaultSlice());
    },

    clearAll: () => {
      const { slices } = get();
      for (const slice of Object.values(slices)) {
        if (slice._abortController) slice._abortController.abort();
        if (slice._streamingTimeout) clearTimeout(slice._streamingTimeout);
      }
      set({ slices: {} });
    },

    seedPlaceholderMessages: (agentIds: string[]) => {
      for (const agentId of agentIds) {
        const existing = get().slices[agentId];
        /* Only seed if the slice is empty or doesn't exist yet. */
        if (existing && existing.messages.length > 0) continue;
        const placeholders = PLACEHOLDER_CHAT_DATA[agentId];
        if (!placeholders) continue;
        _setSlice(agentId, { messages: placeholders });
      }
    },

    handleDelegationEvent: (agentId: string, eventType: string, data: Record<string, unknown>) => {
      switch (eventType) {
        case "delegation_start": {
          /* Set streaming state immediately — the user message will
             appear after the next refresh (on "done"). No need to
             fetch the full session here; it blocks the UI. */
          _setSlice(agentId, {
            status: "streaming",
            streamingParts: [],
            streamingToolIndex: new Map(),
            hasSeenToolCall: false,
            lastEventWasToolResult: false,
            error: null,
          });
          break;
        }
        case "token": {
          _updateSlice(agentId, (s) => _appendToken(s.streamingParts, (data.token as string) || ""));
          break;
        }
        case "tool_call_start": {
          const id = (data.id as string) || "";
          const name = (data.name as string) || "";
          _updateSlice(agentId, (s) => _startToolCall(s, id, name));
          break;
        }
        case "tool_call_delta": {
          // Per-chunk argument fragment for a delegated specialist's
          // tool call \u2014 routes to the specialist agent's slice so
          // ToolCallDisplay shows char-by-char growth in that tab.
          const id = (data.id as string) || "";
          const delta = (data.arguments_delta as string) || "";
          _updateSlice(agentId, (s) => _appendToolCallArgumentsDelta(s, id, delta));
          break;
        }
        case "tool_call_end": {
          const id = (data.id as string) || "";
          const tcName = (data.name as string) || "";
          const args = (data.arguments as Record<string, unknown>) || {};
          _updateSlice(agentId, (s) => _endToolCall(s, id, args));
          /* Route panel-updating tools to the panel store. */
          if (
            tcName.startsWith("update_")
            || tcName === "push_priority_action"
            || tcName === "push_action"
            || tcName === "classify"
          ) {
            import("@/stores/panelStore").then(({ usePanelStore }) => {
              usePanelStore.getState().updatePanel(tcName, args);
            });
          }
          break;
        }
        case "tool_result": {
          const id = (data.id as string) || "";
          const name = (data.name as string) || "";
          const result = (data.result as string) || "";
          _updateSlice(agentId, (s) => _applyToolResult(s, id, name, result));
          break;
        }
        case "done": {
          /* Build the assistant message from accumulated parts */
          const cur = _getSlice(agentId);
          if (cur.streamingParts.length > 0) {
            const assistantMessage = buildAssistantMessage(cur.streamingParts, agentId, "complete");
            _setSlice(agentId, {
              status: "idle",
              messages: [...cur.messages, assistantMessage],
              streamingParts: [],
              streamingToolIndex: new Map(),
              hasSeenToolCall: false,
              lastEventWasToolResult: false,
            });
            /* No refreshActiveSession here — the orchestrator's onDone handler
               already calls refreshActiveSession when the full stream completes.
               Firing it mid-stream causes a large JSON fetch + React render storm
               while the orchestrator is still streaming tokens, freezing the UI. */
          } else {
            _setSlice(agentId, { status: "idle" });
          }
          break;
        }
        case "error": {
          const errorMsg = (data.error as string) || "Delegation failed";
          const cur = _getSlice(agentId);
          if (cur.streamingParts.length > 0) {
            const partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
            _setSlice(agentId, {
              status: "error",
              error: errorMsg,
              messages: [...cur.messages, partialMsg],
              streamingParts: [],
            });
          } else {
            _setSlice(agentId, { status: "error", error: errorMsg });
          }
          break;
        }
        default:
          console.warn("[handleDelegationEvent] Unknown event type:", eventType, data);
          break;
      }
    },

    handleBackgroundEvent: (agentId: string, eventType: string, data: Record<string, unknown>) => {
      switch (eventType) {
        case "start": {
          const task = (data.task as string) || "";
          const cur = _getSlice(agentId);
          const alreadyHasTask = cur.messages.some((message) => message._isDelegation && message.content === task);
          const delegationMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: "user",
            content: task,
            parts: [{ type: "text", text: task }],
            status: "complete",
            tool_calls: [],
            agent_name: agentId,
            created_at: new Date().toISOString(),
            _isDelegation: true,
          };
          const nextMessages = alreadyHasTask
            ? cur.messages
            : [...cur.messages, delegationMessage];
          _setSlice(agentId, {
            messages: nextMessages,
            status: "streaming",
            streamingParts: [],
            streamingToolIndex: new Map(),
            hasSeenToolCall: false,
            lastEventWasToolResult: false,
            error: null,
          });
          break;
        }
        case "token": {
          _updateSlice(agentId, (s) => _appendToken(s.streamingParts, (data.token as string) || ""));
          break;
        }
        case "tool_call_start": {
          const id = (data.id as string) || "";
          const name = (data.name as string) || "";
          _updateSlice(agentId, (s) => _startToolCall(s, id, name));
          break;
        }
        case "tool_call_delta": {
          // Background-run per-chunk argument fragment. Forwards into
          // the same reducer used for foreground/delegation streams so
          // the dispatcher tab renders char-by-char growth.
          const id = (data.id as string) || "";
          const delta = (data.arguments_delta as string) || "";
          _updateSlice(agentId, (s) => _appendToolCallArgumentsDelta(s, id, delta));
          break;
        }
        case "tool_call_end": {
          const id = (data.id as string) || "";
          const tcName = (data.name as string) || "";
          const args = (data.arguments as Record<string, unknown>) || {};
          _updateSlice(agentId, (s) => _endToolCall(s, id, args));
          if (
            tcName.startsWith("update_")
            || tcName === "push_priority_action"
            || tcName === "push_action"
            || tcName === "classify"
          ) {
            import("@/stores/panelStore").then(({ usePanelStore }) => {
              usePanelStore.getState().updatePanel(tcName, args);
            });
          }
          break;
        }
        case "tool_result": {
          const id = (data.id as string) || "";
          const name = (data.name as string) || "";
          const result = (data.result as string) || "";
          _updateSlice(agentId, (s) => _applyToolResult(s, id, name, result));
          break;
        }
        case "done": {
          const cur = _getSlice(agentId);
          if (cur.streamingParts.length > 0) {
            const assistantMessage = buildAssistantMessage(cur.streamingParts, agentId, "complete");
            _setSlice(agentId, {
              status: "idle",
              messages: [...cur.messages, assistantMessage],
              streamingParts: [],
              streamingToolIndex: new Map(),
              hasSeenToolCall: false,
              lastEventWasToolResult: false,
            });
          } else {
            _setSlice(agentId, { status: "idle" });
          }
          void useSessionStore.getState().refreshActiveSession();
          break;
        }
        case "error": {
          const errorMsg = (data.error as string) || "Background run failed";
          const cur = _getSlice(agentId);
          if (cur.streamingParts.length > 0) {
            const partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
            _setSlice(agentId, {
              status: "error",
              error: errorMsg,
              messages: [...cur.messages, partialMsg],
              streamingParts: [],
            });
          } else {
            _setSlice(agentId, { status: "error", error: errorMsg });
          }
          void useSessionStore.getState().refreshActiveSession();
          break;
        }
        case "aborted": {
          const cur = _getSlice(agentId);
          const abortedMessage = buildAssistantMessage(cur.streamingParts, agentId, "aborted");
          _setSlice(agentId, {
            status: "idle",
            messages: [...cur.messages, abortedMessage],
            streamingParts: [],
            streamingToolIndex: new Map(),
            hasSeenToolCall: false,
            lastEventWasToolResult: false,
          });
          void useSessionStore.getState().refreshActiveSession();
          break;
        }
      }
    },

  };

  return store;
});
