import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "vite";
import { projectObjectRow, formatCell } from "@agentcraft/modular-agents";
import { loadModule } from "../support/transpile.mjs";

const api = await loadModule("../../src/shared/api/api.ts", import.meta.url);
const state = await loadModule("../../src/shared/api/agent-events.ts", import.meta.url);
const envelope = await loadModule("../../src/shared/agent-output/envelope.ts", import.meta.url);
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

async function loadRenderModule(entry) {
  const bundle = await build({
    configFile: false, logLevel: "silent", esbuild: { jsx: "automatic" },
    build: { write: false, minify: false, lib: { entry: fileURLToPath(entry), formats: ["es"] },
      rollupOptions: { external: ["react", "react/jsx-runtime"],
        output: { paths: (specifier) => import.meta.resolve(specifier) } },
    },
  });
  const output = (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === "chunk" && item.isEntry);
  return import(`data:text/javascript;base64,${Buffer.from(output.code).toString("base64")}`);
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

test("tool envelopes reuse canonical state precedence, including conflicting flags", () => {
  const table = { tool: "query", columns: ["count"], rows: [[1]] };
  for (const flags of [{}, { error: false }, { error: "" }, { status: "ok" }]) {
    assert.equal(state.toolOutcome({ ...table, ...flags }), "done");
    assert.equal(envelope.parseToolEnvelope({ ...table, ...flags }).kind, "table");
  }
  for (const flags of [{ error: true }, { error: "failed" }, { status: "error" },
    { error: false, status: "error" }]) {
    const value = { ...table, ...flags, detail: "Execution failed" };
    assert.equal(state.toolOutcome(value), "error");
    assert.equal(envelope.parseToolEnvelope(value).kind, "error");
    assert.equal(envelope.parseToolEnvelope(value).message, "Execution failed");
  }
  for (const flags of [{ refused: true }, { refused: true, duplicate: true, error: true },
    { duplicate: true }, { duplicate: true, status: "error" }]) {
    const value = { ...table, ...flags };
    assert.equal(state.toolOutcome(value), "done");
    assert.equal(envelope.parseToolEnvelope(value).kind, flags.refused ? "refusal" : "duplicate");
  }
  assert.deepEqual(envelope.parseToolEnvelope({ refused: true }).refusal,
    { parameter: "input", problem: "rejected", accepted: "" });
  assert.equal(envelope.parseToolEnvelope({ error: true }).message, "The tool reported an error.");
  for (const value of [null, [], "plain", false]) assert.equal(state.toolOutcome(value), "done");
});

test("canonical card defaults and host bands render without nested cards", async () => {
  const { ToolResultCard, ResultTable, TabularRenderer } = await loadRenderModule(import.meta.resolve("@agentcraft/modular-agents"));
  const defaults = renderToStaticMarkup(createElement(ToolResultCard, {
    scope: [{ label: "host", value: "fixture" }], signal: [{ label: "rows", value: 1 }], note: "Advisory",
  }, createElement(ResultTable, { headers: ["count"], rows: [[1]] })));
  assert.ok(defaults.indexOf("data-card-scope") < defaults.indexOf("data-card-signal"));
  assert.ok(defaults.indexOf("data-card-signal") < defaults.indexOf("data-card-note"));
  assert.ok(defaults.indexOf("data-card-note") < defaults.indexOf('data-testid="card-body"'));
  assert.match(defaults, /resize:vertical/);
  assert.match(defaults, /min-height:96px/);
  assert.match(defaults, /max-height:320px/);
  assert.match(defaults, /flex-1 min-h-0/);
  assert.match(defaults, /data-card-tone="accent"/);
  assert.match(defaults, /data-card-note="warning"/);
  const bands = renderToStaticMarkup(createElement(ToolResultCard, {
    header: createElement("header", null, "Identity"),
    scope: [{ label: "host", value: "fixture" }], signal: [{ label: "rows", value: 1 }],
    note: "Advisory", notePosition: "before-signal", bandLabels: { scope: "Inputs", result: "Results" },
    resizable: false,
  }, createElement(ResultTable, { headers: ["count"], rows: [[1]] })));
  assert.ok(bands.indexOf("Identity") < bands.indexOf("Inputs"));
  assert.ok(bands.indexOf("Inputs") < bands.indexOf("Advisory"));
  assert.ok(bands.indexOf("Advisory") < bands.indexOf("Results"));
  assert.doesNotMatch(bands, /resize:vertical|flex-1 min-h-0/);
  assert.equal((bands.match(/data-tool-card=/g) ?? []).length, 1);
  const table = renderToStaticMarkup(createElement(TabularRenderer, { result: JSON.stringify({
    columns: [{ name: "score" }, "missing"], rows: [{ score: 1.23456789 }, [2.3456789], 7],
  }) }));
  assert.match(table, /1\.2346/);
  assert.match(table, /2\.3457/);
  assert.match(table, /title="7"/);
});

test("object projection is shared; caller array, scalar and number policies remain distinct", () => {
  const precise = 1.23456789;
  const object = Object.freeze({ score: precise, nested: { value: false }, extra: 99 });
  assert.deepEqual(projectObjectRow(["nested", "score", "missing", "score"], object),
    [{ value: false }, precise, undefined, precise]);
  assert.deepEqual(projectObjectRow([], object), []);
  const value = { columns: ["score", "missing"], rows: [object, [precise, 2, 3], [precise], 7, null] };
  const expected = [[precise, undefined], [precise, 2], [precise, undefined], [undefined, undefined], [undefined, undefined]];
  assert.deepEqual(envelope.parseToolEnvelope(value).rows, expected);
  assert.deepEqual(envelope.fromQueryResult("query", "dns", {}, { ...value,
    row_count: 5, max_rows: 20, truncated: false, elapsed_ms: 1 }).rows, expected);
  assert.equal(envelope.text(precise), "1.23456789");
  assert.equal(formatCell(precise), "1.2346");
});

test("actual app tool rendering preserves bands, precision, caps and envelope states", async () => {
  const { ToolRender } = await loadRenderModule(new URL("../../src/shared/agent-output/ToolRender.tsx", import.meta.url));
  const render = (value) => renderToStaticMarkup(createElement(ToolRender, { value }));
  const table = { tool: "query", category: "dns", scope: { host: "fixture", row_count: 14, max_rows: 20 },
    columns: ["score"], rows: Array.from({ length: 14 }, () => [1.23456789]) };
  const normal = render({ ...table, error: false });
  assert.match(normal, /DNS activity/);
  assert.match(normal, /trender-scope/);
  assert.match(normal, /trender-signals/);
  assert.match(normal, /Showing 12 of 14 returned rows/);
  assert.match(normal, /1\.23456789/);
  assert.doesNotMatch(normal, /resize:vertical|data-card-note=/);
  assert.equal((normal.match(/data-tool-card=/g) ?? []).length, 1);
  const fallback = render({ ...table, fallback: true });
  assert.ok(fallback.indexOf("Inputs") < fallback.indexOf("Model-authored KQL"));
  assert.ok(fallback.indexOf("Model-authored KQL") < fallback.indexOf("Results"));
  assert.match(render({ ...table, rows: [] }), /data-card-note="info"/);
  for (const flags of [{ refused: true }, { refused: true, duplicate: true, error: true },
    { duplicate: true }, { duplicate: true, status: "error" }]) {
    const markup = render({ ...table, ...flags, parameter: "host", problem: "Invalid host", accepted: "Known host" });
    assert.match(markup, new RegExp(`data-tool-card="${flags.refused ? "refused" : "duplicate"}"`));
    assert.doesNotMatch(markup, /role="alert"|Unrecognised envelope|Tool failed/);
    if (flags.refused) assert.match(markup, /Accepts Known host/);
  }
  for (const flags of [{ error: true }, { error: "failed" }, { status: "error", error: false }]) {
    const markup = render({ ...table, ...flags, detail: "Failure detail" });
    assert.match(markup, /role="alert"/);
    assert.match(markup, /Failure detail/);
  }
});

test("height drag preserves directions, bounds, persistence, natural reset and cancellation", async () => {
  const { useHeightDrag } = await loadRenderModule(new URL("../../src/shared/ui/useHeightDrag.ts", import.meta.url));
  const originalWindow = globalThis.window;
  const stored = new Map();
  const target = new EventTarget();
  let writes = 0;
  target.localStorage = {
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => { writes += 1; stored.set(key, value); },
    removeItem: (key) => stored.delete(key),
  };
  let control;
  function Probe(props) {
    control = useHeightDrag(props);
    control.ref.current = { getBoundingClientRect: () => ({ height: 100 }) };
    return createElement("output", null, control.height);
  }
  const emit = (type, clientY, pointerId = 1) => {
    target.dispatchEvent(Object.assign(new Event(type), { clientY, pointerId }));
  };
  const start = () => control.startResize({ clientY: 200, pointerId: 1, preventDefault() {} });
  try {
    globalThis.window = target;
    for (const options of [
      { storageKey: "cybereye.height.fixture", direction: "down", min: 60, max: 1200 },
      { storageKey: "cybereye.composer", direction: "up", min: 38, max: 420 },
    ]) {
      assert.equal(renderToStaticMarkup(createElement(Probe, options)), "<output>0</output>");
      for (const [clientY, expected] of [[230, options.direction === "down" ? 130 : 70],
        [10000, options.direction === "down" ? options.max : options.min],
        [-10000, options.direction === "down" ? options.min : options.max]]) {
        start(); emit("pointermove", clientY); emit("pointerup", clientY);
        assert.equal(stored.get(options.storageKey), String(expected));
      }
      const beforeCancel = writes;
      start(); emit("pointermove", 250, 2); emit("pointerup", 250, 2);
      assert.equal(writes, beforeCancel);
      emit("pointercancel", 250); emit("pointerup", 250);
      assert.equal(writes, beforeCancel);
      start(); emit("blur", 0); emit("pointerup", 250);
      assert.equal(writes, beforeCancel);
      start(); start(); emit("pointermove", 230); emit("pointerup", 230);
      assert.equal(writes, beforeCancel + 1);
      control.resetHeight();
      assert.equal(stored.has(options.storageKey), false);
      for (const [saved, expected] of [["NaN", 0], ["-1", 0], [String(options.min), options.min],
        ["5000", options.max]]) {
        stored.set(options.storageKey, saved);
        assert.equal(renderToStaticMarkup(createElement(Probe, options)), `<output>${expected}</output>`);
      }
      stored.delete(options.storageKey);
    }
    target.localStorage = {
      getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); },
      removeItem() { throw new Error("blocked"); },
    };
    assert.equal(renderToStaticMarkup(createElement(Probe, { storageKey: "blocked", direction: "down", min: 60, max: 1200 })), "<output>0</output>");
    start(); emit("pointermove", 230); emit("pointerup", 230); control.resetHeight();
  } finally { globalThis.window = originalWindow; }
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
    ["tool_call_start", { id: "call", name: "tool", display_name: "Tool", fallback: true }],
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
      if (name === "diagnosis") assert.deepEqual(events[0].args, ["tool", "Tool", "call"]);
      else {
        const [tool] = events[0].args;
        assert.deepEqual({ ...tool, startedAt: 0 }, { id: "call", name: "tool", displayName: "Tool",
          fallback: true, status: "running", startedAt: 0 });
        assert.equal(typeof tool.startedAt, "number");
      }
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

test("shared lifecycle keeps diagnosis and chat error defaults and optional metadata", async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const name of ["diagnosis", "chat"]) {
      for (const [data, expected] of [[{}, name === "diagnosis" ? "Diagnosis failed" : "Agent error"],
        [{ error: "code" }, "code"], [{ detail: "detail", error: "code" }, "detail"]]) {
        const events = [];
        globalThis.fetch = async () => new Response(body(`event: error\ndata: ${JSON.stringify(data)}\n\n`, 1));
        await streams[name](callbacks(events));
        assert.deepEqual(events, [{ name: "error", args: [expected] }]);
      }
    }
    const events = [];
    const withoutMetadata = new Proxy({}, { get: (_, name) => name === "metadata" ? undefined
      : (...args) => events.push({ name, args }) });
    globalThis.fetch = async () => new Response(body('event: metadata\ndata: {}\n\nevent: done\ndata: {"status":"completed"}\n\n', 1));
    await streams.diagnosis(withoutMetadata);
    assert.deepEqual(events, [{ name: "done", args: [] }]);
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