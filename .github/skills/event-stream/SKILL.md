---
name: event-stream
description: "Use for framework-free browser ReadableStream framing of named server-sent events and JSON payloads, including split UTF-8/CRLF, multiline data, trailing frames and reader cleanup on errors. HTTP, authorization, reconnect and event semantics remain host-owned."
---

# Named Event Stream

Import `readEventFrames`, `readJsonEvents` and `EventFrame` from `@agentcraft/event-stream`.
The [library guide](../../../libraries/event-stream/docs/skills/event-stream.md) owns the contract,
limits and notice provenance.
Use the installed package, not skill-local source. This entry grants no HTTP or data access.

The host supplies an authorized response body, handles cancellation/reconnect and interprets events.
The reader releases its lock on finish and failure; malformed JSON raises instead of silently dropping
a result. No dependencies or framework are required at runtime.