---
name: event-stream
description: "Use for framework-free browser ReadableStream framing of named server-sent events and JSON payloads, including split UTF-8/CRLF, multiline data, trailing frames and reader cleanup on errors. HTTP, authorization, reconnect and event semantics remain host-owned."
---

# Named Event Stream

Import `readEventFrames`, `readJsonEvents` and `EventFrame` from `@harness/event-stream`.
The [contract](README.md) and [implementation](frontend/read-events.ts) are authoritative.
This preserves the source's named-event protocol, not every EventSource behavior: frames without
an event name or data are ignored; `id`/`retry` are ignored; payload indentation is trimmed.

The host supplies an authorized response body, handles cancellation/reconnect and interprets events.
The reader releases its lock on finish and failure; malformed JSON raises instead of silently dropping
a result. No dependencies or framework are required at runtime. Use the copied framing tests before
changing parsing semantics shared by multiple callers.