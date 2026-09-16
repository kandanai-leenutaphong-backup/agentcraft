// Framing behaviour the application's own stream tests cannot reach.
//
// verify-streams.mjs already drives this parser through all four CyberEye streams: chunked
// UTF-8, split CRLF, lone CR, multiline data, comments and malformed JSON. What it cannot show
// is the component's contract on its own terms — the raw frame surface, the reader being
// released, and the frames a stream is entitled to send that no CyberEye endpoint happens to.
import assert from "node:assert/strict";
import test from "node:test";
import { readEventFrames, readJsonEvents } from "@agentcraft/event-stream";

function body(text, chunkSize = 1000, onRelease) {
  const bytes = new TextEncoder().encode(text);
  const stream = new ReadableStream({ start(controller) {
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
    }
    controller.close();
  } });
  if (!onRelease) return stream;
  const getReader = stream.getReader.bind(stream);
  stream.getReader = () => {
    const reader = getReader();
    const releaseLock = reader.releaseLock.bind(reader);
    reader.releaseLock = () => { onRelease(); releaseLock(); };
    return reader;
  };
  return stream;
}

async function frames(text, chunkSize) {
  const seen = [];
  await readEventFrames(body(text, chunkSize), (frame) => seen.push(frame));
  return seen;
}

test("raw frames carry the event name and the data lines rejoined", async () => {
  assert.deepEqual(await frames("event: status\ndata: not json\ndata: still not\n\n"),
    [{ event: "status", data: "not json\nstill not" }]);
});

test("a frame needs both an event name and data to be delivered", async () => {
  assert.deepEqual(await frames([
    ": comment only", "", "data: orphaned payload", "", "event: nameless", "",
    "id: 7", "retry: 3000", "event: kept", "data: {}", "",
  ].join("\n")), [{ event: "kept", data: "{}" }]);
});

test("an unterminated trailing frame is still delivered", async () => {
  assert.deepEqual(await frames("event: done\ndata: {}"), [{ event: "done", data: "{}" }]);
  assert.deepEqual(await frames("   \n\n"), []);
});

test("event names are trimmed and data indentation is stripped, not preserved", async () => {
  assert.deepEqual(await frames("event:  spaced  \ndata:   indented\n\n"),
    [{ event: "spaced", data: "indented" }]);
});

test("a payload split across a chunk boundary inside a multi-byte character survives", async () => {
  const wire = 'event: status\ndata: {"label":"Ready \u2603"}\n\n';
  for (const chunkSize of [1, 3, 7, 1000]) {
    const seen = [];
    await readJsonEvents(body(wire, chunkSize), (event, data) => seen.push([event, data]));
    assert.deepEqual(seen, [["status", { label: "Ready \u2603" }]]);
  }
});

test("the reader is released when a consumer callback throws", async () => {
  let released = false;
  const failing = () => { throw new Error("consumer failed"); };
  await assert.rejects(
    readEventFrames(body("event: a\ndata: {}\n\n", 1000, () => { released = true; }), failing),
    /consumer failed/);
  assert.equal(released, true);
});

test("the reader is released when the stream itself fails mid-read", async () => {
  let released = false;
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("event: a\n"));
      controller.error(new Error("upstream dropped"));
    },
  });
  const getReader = stream.getReader.bind(stream);
  stream.getReader = () => {
    const reader = getReader();
    const releaseLock = reader.releaseLock.bind(reader);
    reader.releaseLock = () => { released = true; releaseLock(); };
    return reader;
  };
  await assert.rejects(readEventFrames(stream, () => {}), /upstream dropped/);
  assert.equal(released, true);
});
