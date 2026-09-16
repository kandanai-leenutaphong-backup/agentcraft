# `src/features/chat/` — Chat-message transforms (pure)

Side-effect-free helpers that the chat store and chat components share. Every export here is a pure function or a plain TypeScript type — there are no React hooks, no `fetch` calls, and no `useXStore` references.

Confidentiality: NDA-restricted per [../../../../README.md](../../../../README.md) §0. Do not embed station codes or telemetry in unit fixtures for this folder.

## Why this folder exists

[`stores/chatStore.ts`](../../stores/chatStore.ts) was previously a single 800-line file mixing the SSE event-handler callbacks, the temp-id reconciliation, the legacy-shape conversion, and the assistant-message finaliser. Pulling those transforms out into pure functions made the store testable in isolation and let `MessageBubble` and `sessionStore` reuse the same conversion when hydrating cached threads.

## Inventory

| File | Role |
|---|---|
| [idSync.ts](idSync.ts) | `syncMessageIds(local, server)` — reconciles temp ids (`temp-*`, `assistant-*`, `aborted-*`) with the canonical server ids by matching role + nearby index. Called from `chatStore` after `onDone` / `onAborted` session refresh. |
| [messageBuilder.ts](messageBuilder.ts) | `buildAssistantMessage(parts, status, agent)` — assembles the final `Message` from accumulated streaming `ContentPart[]` (joins text parts, hoists tool_call parts into `tool_calls`, preserves `parts` for interleaved render). Used by `chatStore` for `onDone` / `onAborted` / `onError`. |
| [messageModels.ts](messageModels.ts) | `normalizeMessage` / `normalizeMessages` — `ApiMessage → ChatMessage` with `parts` always populated (falls back to `legacyToParts` when null). `buildFallbackAssistantMessage` — deterministic placeholder for abort/error before any token arrived. |
| [partUtils.ts](partUtils.ts) | `legacyToParts(msg)` — reconstructs a `ContentPart[]` for an old message that lacks one. `generateToolSummary(name, json)` — one-line summary for the tool-call card body. |
| [sliceReducers.ts](sliceReducers.ts) | Pure reducers (`appendToken`, `startToolCall`, `endToolCall`, `applyToolResult`, `appendToolCallArgumentsDelta`) that map an SSE event onto the slice's streaming fields. The only place that mutates the slice mid-stream. |

## Conventions

- **Pure functions only.** No `useStore`, no `fetch`, no `setTimeout`, no `crypto.randomUUID()` except where the caller explicitly opts in (`buildFallbackAssistantMessage`).
- **No store imports.** These helpers know nothing about Zustand. The store imports from here; never the reverse.
- **Single direction of data flow.** SSE callback (in `chatStore.sendMessage`) calls a reducer here, applies the returned partial state via `set()`. The reducer never touches the store.
- **Types come from [`../../api/types.ts`](../../api/types.ts).** Do not redeclare `Message`, `ApiMessage`, `ContentPart`, or `ToolCall` here.

## Streaming contract these helpers assume

The reducers in [sliceReducers.ts](sliceReducers.ts) assume the SSE event order defined by [`../../api/chatApi.ts`](../../api/chatApi.ts) and emitted by [`hosting/fastapi/routers/chat.py`](../../../../../hosting/fastapi/routers/chat.py):

- `tool_call_start(id, name)` opens a tool call; `tool_call_delta(id, args_delta)` appends to its `pendingArgsRaw`; `tool_call_end(id, name, args)` installs the parsed arguments; `tool_result(id, name, result)` resolves the body.
- `token(text)` always coalesces into the trailing text part — a token after `tool_call_end` starts a new text part.
- `done` / `aborted` terminate the turn. After either, `chatStore` calls `buildAssistantMessage` here to materialise the final `Message`.

If the backend changes event semantics, the reducers and the SSE parser change together; this folder is the contract surface.

## See also

- Chat store: [`../../stores/chatStore.ts`](../../stores/chatStore.ts).
- SSE parser: [`../../api/chatApi.ts`](../../api/chatApi.ts).
- Frontend conventions: [`../../../README.md`](../../../README.md).
