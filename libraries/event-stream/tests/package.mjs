import assert from "node:assert/strict";
import test from "node:test";
import { readEventFrames, readJsonEvents } from "@agentcraft/event-stream";

function stream(text) {
  return new ReadableStream({ start(controller) {
    for (const byte of new TextEncoder().encode(text)) controller.enqueue(Uint8Array.of(byte));
    controller.close();
  } });
}

test("built ESM preserves split UTF-8, CRLF, multiline and trailing frames", async () => {
  const body = stream("event: observation\r\ndata: caf\u00e9\r\ndata: second\r\n\r\nevent: done\ndata: {}");
  const frames = [];
  await readEventFrames(body, frame => frames.push(frame));
  assert.deepEqual(frames, [
    { event: "observation", data: "caf\u00e9\nsecond" },
    { event: "done", data: "{}" },
  ]);
  assert.equal(body.locked, false);
});

test("built JSON reader refuses malformed payloads and releases its lock", async () => {
  const body = stream("event: observation\ndata: {invalid}\n\n");
  await assert.rejects(readJsonEvents(body, () => assert.fail("invalid payload delivered")), SyntaxError);
  assert.equal(body.locked, false);
});