import assert from "node:assert/strict";
import test from "node:test";
import { loadModule } from "../support/transpile.mjs";

const api = await loadModule("../../src/shared/api/api.ts", import.meta.url);
const state = await loadModule("../../src/shared/api/agent-events.ts", import.meta.url);
const situation = { situation_id: "fixture" };
const streams = {
  scan: (callbacks, signal) => api.streamScan("start", "end", callbacks.scan, signal),
  summary: (callbacks, signal) => api.streamSummary(situation, callbacks, signal),
  diagnosis: (callbacks, signal) => api.streamDiagnosis(situation, callbacks, signal),
  chat: (callbacks, signal) => api.streamChat("session", "question", situation, callbacks, signal),
};

function callbacks(events) {
  return new Proxy({}, { get: (_, name) => (...args) => events.push({ name, args }) });
}

function body(text, chunkSize) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(controller) {
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
    }
    controller.close();
  } });
}

test("shared tool state: arguments, timing, error outcome and unrelated calls", () => {
  const initial = [{ id: "call", status: "running", startedAt: 100 },
    { id: "other", status: "running", startedAt: 150 }];
  const partial = state.appendToolArguments(initial, "call", "{");
  assert.equal(state.appendToolArguments(partial, "call", "}")[0].pendingArgs, "{}");
  assert.equal(initial[0].pendingArgs, undefined);
  const settled = state.settleToolArguments(partial, "call", { host: "fixture" });
  assert.equal(settled[0].pendingArgs, undefined);
  assert.deepEqual(settled[0].args, { host: "fixture" });
  const finished = state.finishTool(settled, "call", { rows: [] }, 350);
  assert.equal(finished[0].status, "done");
  assert.equal(finished[0].durationMs, 250);
  assert.equal(finished[1], initial[1]);
  assert.deepEqual(state.finishTool(finished, "unknown", {}, 500), finished);
  assert.equal(state.finishTool(settled, "call", { error: "failed" }, 350)[0].status, "error");
});

test("shared reasoning state: terminal text is not appended twice", () => {
  const started = state.applyReasoning([], "one", "", "start");
  const partial = state.applyReasoning(started, "one", "summary", "delta");
  assert.deepEqual(state.applyReasoning(partial, "one", "summary", "end"),
    [{ id: "one", text: "summary", done: true }]);
  assert.deepEqual(state.applyReasoning([], "two", "summary", "end"),
    [{ id: "two", text: "summary", done: true }]);
  assert.equal(started[0].text, "");
});

for (const [name, run] of Object.entries(streams)) {
  test(`${name}: chunked UTF-8, ordered callbacks and final frame`, async () => {
    const originalFetch = globalThis.fetch;
    const signal = new AbortController().signal;
    const events = [];
    const frame = 'event: status\ndata: {"label":"Ready \\u2603"}\n\n'
      + 'event: done\ndata: {"status":"completed"}';
    try {
      for (const chunkSize of [1, 7, 1000]) {
        events.length = 0;
        globalThis.fetch = async (_, options) => {
          assert.equal(options.signal, signal);
          assert.equal(options.method, "POST");
          assert.equal(options.headers.Accept, "text/event-stream");
          return new Response(body(frame.replace("\\u2603", "\u2603"), chunkSize));
        };
        await run(callbacks(events), signal);
        assert.deepEqual(name === "scan" ? events.map(event => event.args[0].type)
          : events.map(event => event.name), ["status", "done"]);
        const label = name === "scan" ? events[0].args[0].data.label : events[0].args[0];
        assert.equal(label, "Ready \u2603");
      }
    } finally { globalThis.fetch = originalFetch; }
  });

  test(`${name}: errors propagate and malformed JSON is not swallowed`, async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => new Response("upstream failed", { status: 503 });
      await assert.rejects(run(callbacks([])), /upstream failed/);
      globalThis.fetch = async () => new Response(body("event: done\ndata: {invalid}\n\n", 1));
      await assert.rejects(run(callbacks([])), SyntaxError);
      globalThis.fetch = async () => { throw new DOMException("cancelled", "AbortError"); };
      await assert.rejects(run(callbacks([])), { name: "AbortError" });
    } finally { globalThis.fetch = originalFetch; }
  });

  test(`${name}: split CRLF, lone CR, multiline data and comments`, async () => {
    const originalFetch = globalThis.fetch;
    try {
      for (const newline of ["\r\n", "\r", "\n"]) {
        const events = [];
        const wire = [": keepalive", "event: status", 'data: {"label":', 'data: "ready"}',
          "", "event: done", 'data: {"status":"completed"}', "", ""].join(newline);
        globalThis.fetch = async () => new Response(body(wire, 1));
        await run(callbacks(events));
        assert.equal(events.length, 2);
        assert.equal(name === "scan" ? events[0].args[0].data.label : events[0].args[0], "ready");
      }
    } finally { globalThis.fetch = originalFetch; }
  });
}

test("diagnosis and chat: all tool and reasoning lifecycle callbacks remain ordered", async () => {
  const frames = [
    ["tool_call_start", { id: "call", name: "tool", display_name: "Tool" }],
    ["tool_call_delta", { id: "call", delta: "{}" }],
    ["tool_call_end", { id: "call", arguments: {} }],
    ["tool_result", { id: "call", name: "tool", result: { rows: [] } }],
    ["reasoning_start", { id: "thought" }],
    ["reasoning_delta", { id: "thought", delta: "summary" }],
    ["reasoning_end", { id: "thought", text: "summary" }],
    ["diagnosis", { situation_id: "fixture" }],
    ["sequence_step", { position: 1 }], ["sequence", { steps: [] }],
    ["token", { token: "answer" }], ["metadata", { model: "model", agent_id: "saved-agent",
      agent_name: "Saved Investigator", config_version: 3 }],
    ["done", { status: "completed" }],
  ].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  const originalFetch = globalThis.fetch;
  try {
    for (const name of ["diagnosis", "chat"]) {
      const events = [];
      globalThis.fetch = async () => new Response(body(frames, 5));
      await streams[name](callbacks(events));
      assert.deepEqual(events.map(event => event.name), ["toolStart", "toolDelta", "toolEnd",
        "toolResult", "reasoning", "reasoning", "reasoning", ...(name === "diagnosis"
          ? ["diagnosis", "sequenceStep", "sequence"] : ["token"]), "metadata", "done"]);
      assert.deepEqual(events[2].args, ["call", {}]);
      assert.deepEqual(events[3].args, ["call", "tool", { rows: [] }]);
      assert.deepEqual(events[5].args, ["thought", "summary", "delta"]);
      assert.deepEqual(events.find((event) => event.name === "metadata").args, [{
        model: "model", agent_id: "saved-agent", agent_name: "Saved Investigator", config_version: 3,
      }]);
    }
    globalThis.fetch = async () => new Response("missing", { status: 404 });
    await assert.rejects(streams.chat(callbacks([])), api.SessionExpiredError);
  } finally { globalThis.fetch = originalFetch; }
});

test("native model streams refuse quiet EOF, incomplete runs, and regressed sequence", async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const name of ["summary", "diagnosis", "chat"]) {
      globalThis.fetch = async () => new Response(body('event: token\ndata: {"token":"partial"}\n\n', 5));
      await assert.rejects(streams[name](callbacks([])), /without a terminal event/);
      const events = [];
      globalThis.fetch = async () => new Response(body('event: done\ndata: {"status":"incomplete"}\n\n', 5));
      await streams[name](callbacks(events));
      assert.deepEqual(events.map(event => event.name), ["error"]);
      const frames = [2, 1].map(sequence => 'event: metadata\ndata: ' + JSON.stringify({
        native: { schema_version: 1, run_id: "fixture", sequence, kind: "text.delta" },
      }) + '\n\n').join('');
      globalThis.fetch = async () => new Response(body(frames, 5));
      await assert.rejects(streams[name](callbacks([])), /Invalid native run event/);
    }
  } finally { globalThis.fetch = originalFetch; }
});