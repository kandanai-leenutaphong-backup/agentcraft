# event_stream

Server-sent event framing for a browser `ReadableStream`. Frontend-only, no dependencies, no
framework: TypeScript and the standard web platform.

## Surface

Reached through [frontend/index.ts](frontend/index.ts), exported by `@harness/event-stream`.

| Export | Contract |
| --- | --- |
| `readEventFrames(body, onFrame)` | Reads `body` to completion, calling `onFrame({ event, data })` once per frame, in order. `data` is the frame's `data:` lines rejoined with `\n`. |
| `readJsonEvents(body, onEvent)` | The same read, with each payload parsed: `onEvent(event, parsed)`. A payload that is not JSON throws out of the read. |
| `EventFrame` | `{ event: string; data: string }`. |

Both release the stream reader when they finish, including on a thrown error or an abort.

## Framing rules

- Chunk boundaries may fall inside a multi-byte character; decoding is streaming until the
  final chunk.
- A trailing CR is held back for its possible LF in the next chunk.
- CRLF, lone CR and LF all terminate a line.
- A frame ends at a blank line, and a trailing unterminated frame is still delivered.
- Comments, keepalives, `id:` and `retry:` are ignored, and a frame without both an event name
  and at least one `data:` line is not delivered.

## Not in scope

HTTP, request construction, headers, authentication, session recovery, retry, and what any
event name means. Those belong to the calling application's own API adapter.
