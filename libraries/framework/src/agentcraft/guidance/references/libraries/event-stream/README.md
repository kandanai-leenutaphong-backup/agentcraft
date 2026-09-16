# event_stream

Server-sent event framing for a browser `ReadableStream`. Frontend-only, no dependencies, no
framework: TypeScript and the standard web platform.

## Build And Install

Exports resolve to ES2022 ESM and declarations under `dist`, not TypeScript source.
Development uses TypeScript 5.9 and native Web Streams (verified on Node 20.20.0).
From this package directory:

```bash
npm install
npm run typecheck
npm test
npm pack
```

`prepack` rebuilds the archive. Install the returned
`agentcraft-event-stream-0.1.0.tgz` with `npm install <archive-path>` in the host.
Local `file:` consumers build this package before their own tests/builds and use
installed exports, not aliases to `frontend`. Hosts own lockfiles and releases;
registry publication is not implied. No runtime dependencies or assets are bundled.

```ts
import { readJsonEvents } from "@agentcraft/event-stream";

export async function observe(body: ReadableStream<Uint8Array>) {
  const events: Array<{ event: string; data: Record<string, unknown> }> = [];
  await readJsonEvents(body, (event, data) => events.push({ event, data }));
  return events;
}
```

## Surface

Import from the public `@agentcraft/event-stream` package. No skill or app source path is required.

| Export | Contract |
| --- | --- |
| `readEventFrames(body, onFrame)` | Reads `body` to completion, calling `onFrame({ event, data })` once per frame, in order. `data` is the frame's `data:` lines rejoined with `\n`. |
| `readJsonEvents(body, onEvent)` | The same read, with each payload parsed: `onEvent(event, parsed)`. A payload that is not JSON throws out of the read. |
| `EventFrame` | `{ event: string; data: string }`. |

Both release the stream reader when they finish, including on a thrown error or an abort.
They do not cancel the transport or retry. Callbacks are synchronous; the parser
does not await callback promises. There is no frame-size/response-size limit or
persistence: hosts bound input and own cancellation and terminal meaning.

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
