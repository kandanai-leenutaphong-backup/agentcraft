# `src/stores/` — Zustand state slices

State for the frontend. Each store is a Zustand slice with a narrow responsibility; there is no global app store. Stores talk to the backend through [`../api/`](../api/) and to each other through direct `useXStore.getState()` calls (never circular).

Confidentiality: NDA-restricted per [../../../README.md](../../../README.md) §0. No station codes, telemetry, or composite ids in fixtures or snapshots seeded from these stores.

## Inventory

| Store | Owns | Primary consumers |
|---|---|---|
| [agentStore.ts](agentStore.ts) | Configured agent tabs (`GET /api/agents`), active agent id, delegated/ad-hoc agent registry | `AgentTabBar`, `ChatPanel`, anywhere keyed by `activeAgentId` |
| [auditStore.ts](auditStore.ts) | Live audit SSE connection, current report, stream-event log, history list | `SessionAuditPanel` |
| [chatStore.ts](chatStore.ts) | Per-agent message slices + streaming state machine (`idle → streaming → done / error / aborted`) | `ChatPanel`, `ChatInput`, `MessageList`, `StreamingIndicator`, `MessageBubble` |
| [lookupStore.ts](lookupStore.ts) | Dock-surface assistant id + dock-session id (independent of chatStore/sessionStore) | `LookupDock` |
| [paletteStore.ts](paletteStore.ts) | Command palette + help overlay open flags | `CommandPalette`, `HelpOverlay` |
| [panelStore.ts](panelStore.ts) | Control-room panel data populated from `tool_call_end` events for `update_*` tools | `PriorityActionsPanel`, `OperatingStatePanel`, `PinnedSituationPanel`, `PanelLayout` |
| [placeholderChatData.ts](placeholderChatData.ts) | Empty stub — placeholder dataset retired; export kept for compile compatibility | (none) |
| [placeholderStore.ts](placeholderStore.ts) | Empty stub — placeholder toggle retired; export kept for compile compatibility | (none) |
| [sessionStore.ts](sessionStore.ts) | Session list, active session, background-run polling, summary/panel sync on switch | session-aware components across the app (chat, panels, layout) |
| [situationStore.ts](situationStore.ts) | Situations from `POST /api/situations/scan`, detector config draft + comparison, Investigate-flow handoff | `SituationAlertsPanel`, `OperatingStatePanel`, `SituationDetectorTuningPanel` |
| [summaryStore.ts](summaryStore.ts) | Per-session situation summary state; synchronous POST-to-summarize, no SSE | `SituationSummaryCard` |
| [toastStore.ts](toastStore.ts) | Transient notification queue with auto-dismiss | `Toaster`, `escalationWatcher` |
| [topologyStore.ts](topologyStore.ts) | Active station, adjacency graph, optional situation overlay, traversal breadcrumb | `TopologyMap`, `TopologyPanel`, `TopologyDetailPane`, `StationNode` |

## Conventions

- **One slice per concern.** Do not bolt unrelated state onto an existing store.
- **Async actions live on the store.** Components dispatch via the store's action method; they never call `api/*` directly when the result needs to land in state.
- **Cross-store reads use `getState()`.** Inside an action, read another store with `useOtherStore.getState()`; do not subscribe.
- **Cross-store writes flow one way.** `chatStore` calls `sessionStore.refreshActiveSession`; `sessionStore` does not import from `chatStore`. Any new edge must preserve a DAG.
- **No store imports a component.** Stores depend on `api/`, `features/`, and other stores only.
- **Persistence.** [`../hooks/usePersistence.ts`](../hooks/usePersistence.ts) snapshots a subset of state to `localStorage` per session. New persisted keys must be added there.

## SSE handling

The chat SSE stream is parsed in [`../api/chatApi.ts`](../api/chatApi.ts) and dispatched into `chatStore` via typed callbacks (`SSECallbacks`). Reducers for each event live in [`../features/chat/sliceReducers.ts`](../features/chat/sliceReducers.ts) — those are the only place that mutates a slice mid-stream. `chatStore` is the orchestrator; pure transforms live in `features/chat/`.

## See also

- API client: [`../api/README.md`](../api/README.md).
- Chat normalisation utilities: [`../features/chat/README.md`](../features/chat/README.md).
- Frontend conventions: [`../../README.md`](../../README.md).
