# Named Event Stream

Use installed `@agentcraft/event-stream`; public exports are `readEventFrames`,
`readJsonEvents` and `EventFrame`. The [contract](../../README.md) owns framing.
The skill contains no runtime, source-path import, HTTP client or credentials.

The host supplies an authorized `ReadableStream` body. Frames preserve named
event/data order, split UTF-8 characters and CRLF boundaries, multiline data and
a trailing unterminated frame. Comments, keepalives, `id` and `retry` are ignored;
a frame requires an event name and data. JSON parsing failures raise rather than
silently dropping a result. Callback/stream errors propagate.

Reader locks are released on finish/failure. Host owns transport cancellation,
connection lifetime, retry, reconnect, event interpretation and authorization.
The parser has no configurable frame-size or total-response limit: bound input
and cancellation at the host. Parsing a stream does not prove domain completion,
persisted results or exactly-once delivery.

## Retirement Finish, 2026-09-16

Parent already retired these paths under `.github/skills/event-stream/`:
`README.md`, `frontend/index.ts`, `frontend/read-events.ts`, `package.json`.
Parent reported seven framing tests passing; this notice-only finish does not
claim a new runtime test run. No runtime bytes changed in this increment.

The original Microsoft MIT notice remains at the native skill and is copied
byte-for-byte to the canonical library's `LICENSE`. Native name/triggers remain;
the guide now makes bounds and lifecycle explicit. Shared metadata, packaging
and portable discovery remain parent-owned. No server, service or model ran.