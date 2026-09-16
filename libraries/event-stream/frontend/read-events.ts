/**
 * Server-sent event framing for a browser `ReadableStream`.
 *
 * Framework-free and domain-blind: it knows bytes, line endings and frame boundaries, and
 * nothing about HTTP, authentication, sessions or what any event means. Transport and
 * dispatch stay with the caller.
 *
 * The framing rules it holds, each of which has cost a stream somewhere:
 *
 * - Chunk boundaries fall anywhere, including inside a multi-byte character, so decoding is
 *   streaming until the final chunk.
 * - A trailing CR waits for its possible LF in the next chunk; splitting it early turns one
 *   line ending into two and cuts a frame in half.
 * - CRLF, lone CR and LF all terminate a line.
 * - A frame ends at a blank line; a trailing unterminated frame is still delivered.
 * - Lines that are neither `event:` nor `data:` — comments, keepalives, `id:`, `retry:` — are
 *   ignored, and a frame without both an event name and data is not delivered.
 */

/** One delivered frame: its event name, and its `data:` lines rejoined with newlines. */
export interface EventFrame {
  event: string;
  data: string;
}

/** Read every frame in `body`, in order, until the stream ends. */
export async function readEventFrames(
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: EventFrame) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const emit = (frame: string) => {
    let event = "";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (event && data.length) onFrame({ event, data: data.join("\n") });
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const pendingCR = !done && buffer.endsWith("\r");
      buffer = (pendingCR ? buffer.slice(0, -1) : buffer).replace(/\r\n|\r/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        emit(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
      if (pendingCR) buffer += "\r";
      if (done) break;
    }
    if (buffer.trim()) emit(buffer);
  } finally {
    reader.releaseLock();
  }
}

/**
 * Read every frame and hand the caller its parsed JSON payload.
 *
 * A payload that is not JSON throws out of the read rather than being skipped: a stream that
 * silently drops the one frame carrying the answer is worse than one that fails.
 */
export async function readJsonEvents(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  await readEventFrames(body, ({ event, data }) => {
    onEvent(event, JSON.parse(data) as Record<string, unknown>);
  });
}
