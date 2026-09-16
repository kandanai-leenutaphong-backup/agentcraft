# `src/api/` — Typed HTTP + SSE client

The only place in the frontend that issues HTTP requests. Every store and component reaches the backend through this directory.

Confidentiality: NDA-restricted per [../../../README.md](../../../README.md) §0. Do not commit station codes, telemetry, or equipment ids in API fixtures.

## Layout

| File | Purpose |
|---|---|
| [client.ts](client.ts) | Core: `BASE` URL, `authHeaders()`, `ApiError`, `handleResponse<T>()`, `handleAuthExpired()`. Re-exports every domain file via `export *` so `import * as api from "@/api/client"` resolves the whole surface. |
| [types.ts](types.ts) | Hand-maintained TypeScript mirror of `foundation/models.py`. Single source of truth for request/response shapes. |
| [chatApi.ts](chatApi.ts) | `streamChat`, `subscribeBackground`, `abortChat`. Owns the SSE parser. |
| [sessionApi.ts](sessionApi.ts) | Session CRUD + priority-action decisions. |
| [agentApi.ts](agentApi.ts) | `getAgents`, scenario detail/topology/agent-prompt fetches. |
| [auditApi.ts](auditApi.ts) | Audit envelope GET/run. |
| [classifyApi.ts](classifyApi.ts) | Classifier verdict fetch. |
| [platformApi.ts](platformApi.ts) | Platform/auth-setup helpers. |
| [scenariosApi.ts](scenariosApi.ts) | Scenario list metadata. |
| [situationApi.ts](situationApi.ts) | Situations list + detector config + comparison. |
| [summaryApi.ts](summaryApi.ts) | Situation-summary state fetch + ack. |
| [topologyApi.ts](topologyApi.ts) | Topology graph query. |

## Conventions

- **One source of truth for the base URL.** Import `BASE` from [`@/foundation/constants`](../foundation/constants.ts). Never read `import.meta.env.VITE_API_URL` directly outside that file.
- **Auth + identity headers.** Every request goes through `authHeaders()` from [client.ts](client.ts). In Entra mode it attaches `Authorization: Bearer <token>`; in dev mode it generates a `sessionStorage`-scoped `X-User-Id` / `X-User-Name` pair.
- **Error envelope.** Non-2xx responses throw `ApiError(status, detail)` via `handleResponse<T>`. 401 triggers `handleAuthExpired()` which calls `msalInstance.loginRedirect`.
- **Domain splits, single import.** Domain files (`*Api.ts`) are re-exported by `client.ts`. Consumers may import either `from "@/api/client"` (full surface) or directly `from "@/api/sessionApi"` (narrower).

## SSE protocol (chat)

[chatApi.ts](chatApi.ts) parses an `event: <name>\ndata: <json>\n\n` framed stream from `POST /api/chat/<session_id>`. The event-name union is defined by `StreamEventType` in [types.ts](types.ts); the authoritative list of names emitted by the backend lives in [`hosting/fastapi/routers/chat.py`](../../../../hosting/fastapi/routers/chat.py).

Frontend assumptions about event order:

- The first non-`metadata` event for a turn opens the assistant message.
- `tool_call_start` precedes any `tool_call_delta` / `tool_call_end` / `tool_result` for the same `id`.
- `done` or `aborted` or a transport error terminates the turn. `keepalive` and `rate_limited` may interleave at any point.
- Delegation and background events mirror the main shape, prefixed with `delegation_` / `background_`, and carry an `agent_id` so renderers can route them to the correct slice.

Consumers register typed callbacks via `SSECallbacks`; the parser is the only place that touches the raw stream.

## Adding a new endpoint

1. Add the request/response interfaces to [types.ts](types.ts), mirroring the Pydantic model.
2. Add a function to the matching `*Api.ts` (or create a new domain file) that calls `fetch` + `handleResponse<T>`.
3. If you create a new domain file, add it to the `export * from "./newApi"` list at the bottom of [client.ts](client.ts).
4. Consumers call through `import * as api from "@/api/client"` or the domain file directly.

## See also

- Backend models: [`foundation/models.py`](../../../../foundation/models.py).
- Backend routers: [`hosting/fastapi/routers/`](../../../../hosting/fastapi/routers/).
- Frontend conventions: [`../../README.md`](../../README.md).
