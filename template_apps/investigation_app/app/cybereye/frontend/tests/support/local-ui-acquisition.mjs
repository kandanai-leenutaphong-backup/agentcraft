import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, realpathSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { chromium } from "playwright";
import ts from "typescript";

const frontend = fileURLToPath(new URL("../../", import.meta.url));
const repository = fileURLToPath(new URL("../../../../../../../", import.meta.url));
const requireHost = createRequire(join(frontend, "package.json"));
const requireDocs = createRequire(join(repository, "doc_app/package.json"));
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");

const fixture = String.raw`
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { SourceCodeViewer } from "@agentcraft/source-code";
import { ResourceExplorer } from "@agentcraft/resource-explorer";
import { ResultTable, getArchetypeRenderer } from "@agentcraft/modular-agents";
import "@agentcraft/modular-agents/styles";
import { ToolArguments } from ${JSON.stringify(join(frontend, "src/shared/agent-output/ToolArguments.tsx"))};

const sentinel = 'globalThis.__sourceExecuted = true;\n<img src="/sentinel-request" onerror="globalThis.__sourceExecuted = true">\n' + 'const synthetic = "' + 'bounded-source-'.repeat(90) + '";';
const replacement = 'export const replacement = "replacement-only";\n';
const query = 'EventsUnified\r\n| where Message contains "SYNTHETIC"\r\n' + sentinel + '\r\n';
window.__fixture = { synthetic: true, requests: [], agents: 0, offlineReads: 0, sentinel, replacement, query };
const observedAt = "2026-09-16T00:00:00Z";
const sources = [
  { id: "synthetic.events", label: "Synthetic events" },
  { id: "synthetic.offline", label: "Synthetic retry source" },
];
function enabled(selection, identifier) {
  return selection === "all" || selection.split(",").includes(identifier);
}
async function fetchFixture(input, options = {}) {
  const url = new URL(String(input), location.origin);
  const selection = new Headers(options.headers).get("X-Inventory-Selection") || "all";
  window.__fixture.requests.push({ path: url.pathname, node: url.searchParams.get("node"), selection });
  if (url.origin !== location.origin || !url.pathname.startsWith("/synthetic/inventory/")) throw new Error("Undeclared synthetic read");
  if (options.method && options.method !== "GET") throw new Error("Synthetic fixture is read-only");
  const operation = url.pathname.split("/").at(-1);
  const node = url.searchParams.get("node") || "root";
  const source = sources.find((entry) => entry.id === node);
  const common = { schemaVersion: 1, fixtures: true, node, label: source?.label || "Synthetic catalogue", kind: source ? "source" : "use_case", breadcrumb: [], status: "ok", observedAt, useCaseId: "synthetic", sourceId: source?.id || "", sourceType: "local_table" };
  let payload;
  if (operation === "selection") {
    payload = { schemaVersion: 1, mode: selection === "all" ? "all" : selection === "none" ? "none" : "explicit", enabled: sources.filter((entry) => enabled(selection, entry.id)).map((entry) => entry.id), scope: "browser-session", observedAt, sources: sources.map((entry) => ({ sourceId: entry.id, useCaseId: "synthetic", label: entry.label, sourceType: "local_table", configured: true, enabled: enabled(selection, entry.id) })) };
  } else if (operation === "tree") {
    payload = { ...common, kind: node === "root" ? "root" : "use_case", truncated: false, hasContent: false, selectionScope: "browser-session", children: node === "root" ? [{ id: "synthetic", label: "Synthetic local inventory", kind: "use_case", expandable: true, hasContent: false, status: "ok", useCaseId: "synthetic", configured: true }] : sources.map((entry) => ({ id: entry.id, label: entry.label, kind: "source", expandable: false, hasContent: true, status: "ok", useCaseId: "synthetic", sourceId: entry.id, sourceType: "local_table", configured: true, enabled: enabled(selection, entry.id), tags: ["SYNTHETIC"] })) };
  } else if (source && !enabled(selection, source.id)) {
    return new Response(JSON.stringify({ error: "source_disabled" }), { status: 409, headers: { "Content-Type": "application/json" } });
  } else if (operation === "resource" && source) {
    const unavailable = source.id === "synthetic.offline" && window.__fixture.offlineReads++ === 0;
    payload = { ...common, status: unavailable ? "unreachable" : "ok", configured: true, enabled: true, holds: "Synthetic rows", capabilities: ["metadata", "preview"], connector: { id: "synthetic", name: "Synthetic explicit loader", reachedBy: "fixture" }, coordinates: { table: "synthetic_events" }, metrics: unavailable ? {} : { rows: 3 }, schemaFields: [{ name: "source_time", type: "string" }, { name: "value", type: "int" }], settings: [], provenance: "SYNTHETIC LOCAL FIXTURE. No provider or authentication journey.", error: unavailable ? "Synthetic transport unavailable; retry is local" : null };
  } else if (operation === "content" && source) {
    payload = { ...common, contentKind: "rows", mediaType: "application/json", rows: [{ source_time: observedAt, value: 3, description: "<img src=/sentinel-request onerror=globalThis.__sourceExecuted=true>" }, { source_time: observedAt, value: 1, description: "Synthetic second row" }, { source_time: observedAt, value: 2, description: "bounded-cell-".repeat(100) }], columns: ["source_time", "value", "description"], sizeBytes: 1400, rowLimit: 3, sampleOf: 7, truncated: true, sampleNotes: ["Synthetic preview limited to 3 of 7 rows"], provenance: "SYNTHETIC LOCAL FIXTURE. No provider read." };
  } else {
    throw new Error("Undeclared synthetic operation: " + operation + " " + node);
  }
  return new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json", "Cache-Control": "no-store, private" } });
}
async function loadAgents(signal) {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  window.__fixture.agents += 1;
  if (window.__fixture.agents === 1) throw new Error("Synthetic catalogue unavailable");
  return { agents: [{ id: "synthetic-agent", name: "Synthetic analyst", description: "Synthetic local tool catalogue", model: "no-model", config_id: "synthetic", config_version: 1, config_digest: "synthetic", tools: [
    { id: "synthetic-read", name: "Inspect synthetic source", description: "Read-only synthetic source", category: "local", fallback: false, parameters: { properties: { limit: { type: "integer", description: "Synthetic row limit" } }, required: [] }, datasource: { kind: "local_table", label: "Synthetic events", target: "synthetic_events", target_label: "Synthetic events", endpoint: "", configured: true }, datasource_ids: ["synthetic.events"], source: { available: true, path: "synthetic-sentinel.js", start_line: 7, code: sentinel, truncated: true } },
    { id: "synthetic-replacement", name: "Inspect replacement source", description: "Second synthetic source", category: "local", fallback: false, parameters: { properties: {}, required: [] }, datasource: { kind: "local_table", label: "Synthetic events", target: "synthetic_events", target_label: "Synthetic events", endpoint: "", configured: true }, datasource_ids: ["synthetic.events"], source: { available: true, path: "replacement.js", start_line: 1, code: replacement, truncated: false } },
  ] }] };
}
const Tabular = getArchetypeRenderer("tabular");
const tableRows = Array.from({ length: 12 }, (_, index) => ["synthetic-" + (index + 1), index + 1, "metadata-".repeat(35)]);
function Fixture() {
  const [surface, setSurface] = useState("source");
  const [source, setSource] = useState("sentinel");
  const [result, setResult] = useState("rows");
  const envelope = result === "error" ? { error: true, detail: "Synthetic transport unavailable" } : result === "refused" ? { refused: true, accepts: "Explicit local synthetic rows", reason: "Synthetic grant refused" } : { columns: ["source", "value"], rows: [] };
  return <main>
    <header><strong>SYNTHETIC LOCAL FIXTURE</strong><span>No backend, provider, model, or authentication journey.</span>
      <label>Fixture surface <select aria-label="Fixture surface" value={surface} onChange={(event) => setSurface(event.target.value)}><option value="source">Source viewer</option><option value="catalogue">Inventory and source catalogue</option><option value="modular">Modular result controls</option></select></label>
    </header>
    {surface === "source" && <section aria-label="Source fixture"><label>Source input <select aria-label="Source input" value={source} onChange={(event) => setSource(event.target.value)}><option value="sentinel">Synthetic sentinel</option><option value="replacement">Replacement source</option><option value="unknown">Unknown language</option><option value="arguments">Investigation multiline argument</option><option value="arguments-kql">Investigation KQL argument</option></select></label>{source.startsWith("arguments") ? <ToolArguments args={source === "arguments-kql" ? { query_text: query } : { shell: sentinel }} /> : <SourceCodeViewer code={source === "replacement" ? replacement : sentinel} language={source === "unknown" ? "synthetic-unknown-language" : "javascript"} filename={source === "replacement" ? "replacement.js" : "synthetic-sentinel.js"} startLine={source === "replacement" ? 1 : 7} truncated={source !== "replacement"} maxHeight={360} />}</section>}
    {surface === "catalogue" && <section aria-label="Catalogue fixture"><ResourceExplorer base="/synthetic/inventory" fetchImpl={fetchFixture} loadAgents={loadAgents} previewRows={3} /></section>}
    {surface === "modular" && <section aria-label="Modular fixture"><label>Result state <select aria-label="Result state" value={result} onChange={(event) => setResult(event.target.value)}><option value="rows">Synthetic rows</option><option value="error">Synthetic failure</option><option value="refused">Synthetic refusal</option><option value="empty">Empty result</option></select></label>{result === "rows" ? <ResultTable headers={["source", "value", "metadata"]} rows={tableRows} prominentColumns={["source", "value"]} previewRows={5} /> : <Tabular result={JSON.stringify(envelope)} />}</section>}
  </main>;
}
createRoot(document.getElementById("root")).render(<Fixture />);
`;

export async function startLocalFixture(output) {
  assert.ok(output.startsWith("/tmp/"), "evidence must remain outside checkout");
  mkdirSync(output, { recursive: true });
  const runtime = mkdtempSync(join(output, "runtime-"));
  const consumer = process.env.LOCAL_UI_CONSUMER ? realpathSync(process.env.LOCAL_UI_CONSUMER) : frontend;
  const dependencies = join(consumer, "node_modules");
  const requirePeers = createRequire(join(consumer, "package.json"));
  const packages = [];
  for (const name of ["source-code", "resource-explorer", "modular-agents"]) {
    const origin = process.env.LOCAL_UI_CONSUMER ? join(dependencies, "@agentcraft", name) : join(repository, "libraries", name);
    const destination = join(runtime, "node_modules/@agentcraft", name);
    mkdirSync(destination, { recursive: true });
    cpSync(join(origin, "package.json"), join(destination, "package.json"));
    cpSync(join(origin, "dist"), join(destination, "dist"), { recursive: true });
    const metadata = JSON.parse(readFileSync(join(destination, "package.json"), "utf8"));
    const main = metadata.exports["."].import;
    const entry = join(destination, main);
    assert.equal(digest(readFileSync(entry)), digest(readFileSync(join(origin, main))));
    packages.push({ name: metadata.name, version: metadata.version, origin: join(origin, main), entry, sha256: digest(readFileSync(entry)), package_sha256: digest(readFileSync(join(destination, "package.json"))) });
    if (name === "resource-explorer") cpSync(join(origin, "docs/skills/assets"), join(destination, "docs/skills/assets"), { recursive: true });
    if (name === "modular-agents") {
      for (const relative of [metadata.exports["./styles"].default, metadata.exports["./tailwind-preset"]]) {
        mkdirSync(dirname(join(destination, relative)), { recursive: true });
        cpSync(join(origin, relative), join(destination, relative));
      }
    }
  }
  const modular = packages.find((entry) => entry.name === "@agentcraft/modular-agents");
  const requireRuntime = createRequire(join(runtime, "fixture.cjs"));
  const preset = requireRuntime("@agentcraft/modular-agents/tailwind-preset");
  const tailwind = requireDocs("tailwindcss");
  const candidates = new Set();
  const syntax = ts.createSourceFile("modular-agents.js", readFileSync(modular.entry, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  function collect(node) {
    if (ts.isStringLiteralLike(node)) for (const candidate of node.text.split(/\s+/)) candidates.add(candidate);
    ts.forEachChild(node, collect);
  }
  collect(syntax);
  const theme = readFileSync(join(dirname(requireDocs.resolve("tailwindcss/package.json")), "theme.css"), "utf8");
  const utilityCompiler = await tailwind.compile(theme + '\n@config "fixture-preset";\n@tailwind utilities;', {
    loadModule: async () => ({ module: preset, base: runtime }),
  });
  const utilityCss = utilityCompiler.build([...candidates]);
  const bundle = await build({ stdin: { contents: fixture, resolveDir: runtime, sourcefile: "synthetic-local-fixture.jsx", loader: "jsx" }, bundle: true, write: false, outdir: join(runtime, "bundle"), format: "esm", jsx: "automatic", platform: "browser", nodePaths: [join(runtime, "node_modules"), dependencies], loader: { ".woff2": "dataurl", ".woff": "dataurl", ".png": "dataurl" }, define: { "process.env.NODE_ENV": '"production"' }, metafile: true });
  const javascript = bundle.outputFiles.find((entry) => entry.path.endsWith(".js")).contents;
  const componentCss = bundle.outputFiles.find((entry) => entry.path.endsWith(".css"))?.text || "";
  const css = componentCss + "\n" + utilityCss + "\n" + `
    :root { font-family: 'IBM Plex Sans', sans-serif; color: #1c303b; background: #f5f7f8; }
    body { margin: 0; } * { box-sizing: border-box; } main { min-width: 0; padding: 12px; }
    main > header { display: flex; flex-wrap: wrap; gap: 8px 20px; align-items: center; border-bottom: 1px solid #bac5cc; padding-bottom: 12px; margin-bottom: 12px; }
    main > header span { font-size: 13px; } main > section { min-width: 0; }
    main > section > label { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 12px; }
    select { max-width: 100%; min-height: 44px; font: inherit; }
  `;
  const html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Synthetic local acceptance</title><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>';
  const delivered = [];
  const server = createServer((request, response) => {
    delivered.push({ method: request.method, path: request.url });
    response.setHeader("Cache-Control", "no-store, private");
    const asset = { "/": ["text/html", html], "/fixture.js": ["text/javascript", javascript], "/fixture.css": ["text/css", css] }[request.url];
    if (request.method !== "GET" || !asset) { response.writeHead(404); response.end(); return; }
    response.setHeader("Content-Type", asset[0]);
    response.end(asset[1]);
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try { browser = await chromium.launch({ headless: true }); }
  catch (error) { server.closeAllConnections(); await new Promise((resolve) => server.close(resolve)); throw error; }
  const blocked = [];
  return {
    browser, base, runtime, packages, delivered, blocked,
    environment: { node: process.version, node_executable: process.execPath, consumer, playwright: requireHost("playwright/package.json").version, playwright_origin: realpathSync(requireHost.resolve("playwright")), chromium: browser.version(), chromium_executable: chromium.executablePath(), react: requirePeers("react/package.json").version, react_origin: realpathSync(requirePeers.resolve("react")), esbuild: requireHost("esbuild/package.json").version, tailwind: requireDocs("tailwindcss/package.json").version },
    bundle: { javascript_sha256: digest(javascript), css_sha256: digest(css), inputs: Object.keys(bundle.metafile.inputs) },
    async context(viewport) {
      const context = await browser.newContext({ viewport, isMobile: viewport.width < 700, hasTouch: viewport.width < 700, serviceWorkers: "block", permissions: ["clipboard-read", "clipboard-write"] });
      await context.route("**/*", async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.origin === base && request.method() === "GET" && ["/", "/fixture.js", "/fixture.css"].includes(url.pathname)) return route.continue();
        blocked.push({ url: request.url(), method: request.method() });
        return route.abort("blockedbyclient");
      });
      await context.routeWebSocket("**/*", (socket) => socket.close());
      return context;
    },
    async close() {
      await browser.close();
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
      assert.equal(server.listening, false);
      assert.equal(browser.isConnected(), false);
    },
  };
}