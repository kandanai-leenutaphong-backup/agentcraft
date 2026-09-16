import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createClient, DEFAULT_BASE, SourceDisabledError, StaleSelectionError } from "../dist/client.js";
import { ALL_SELECTED } from "../dist/selection.js";

test("built client uses neutral or host-provided routes without changing selection or cancellation", async () => {
  for (const base of [undefined, "/host/catalogue"]) {
    const calls = [];
    const signal = new AbortController().signal;
    const client = createClient({ base, fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return new Response(JSON.stringify({ node: "root", label: "Sources", kind: "root",
        status: "empty", children: [], breadcrumb: [], observed_at: "2026-09-16T00:00:00Z" }));
    } });
    const result = await client.tree("root", ALL_SELECTED, signal);
    assert.equal(result.status, "empty");
    assert.equal(calls[0].url, `${base ?? DEFAULT_BASE}/tree?node=root`);
    assert.equal(DEFAULT_BASE, "/api/inventory");
    assert.equal(calls[0].options.cache, "no-store");
    assert.equal(calls[0].options.signal, signal);
    assert.equal(calls[0].options.headers["X-Inventory-Selection"], "all");
  }
});

test("built client keeps disabled-source and stale-selection refusals distinct", async () => {
  for (const [status, error, expected] of [
    [409, "source_disabled", SourceDisabledError],
    [400, "invalid_selection", StaleSelectionError],
  ]) {
    const client = createClient({ fetchImpl: async () => new Response(JSON.stringify({ error }), { status }) });
    await assert.rejects(client.content("source", ALL_SELECTED, 1), expected);
  }
});

test("built exports include declarations and both unchanged stylesheets", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(manifest.exports["."].import, "./dist/index.js");
  assert.equal(manifest.exports["."].types, "./dist/index.d.ts");
  assert.ok(manifest.sideEffects.includes("./dist/index.js"));
  assert.ok(manifest.sideEffects.includes("**/*.css"));
  for (const name of ["inventory.css", "explorer.css"]) {
    assert.equal(readFileSync(new URL(`../dist/${name}`, import.meta.url), "utf8"),
      readFileSync(new URL(`../frontend/${name}`, import.meta.url), "utf8"));
  }
  assert.match(readFileSync(new URL("../dist/ResourceExplorer.d.ts", import.meta.url), "utf8"), /ResourceExplorerProps/);
});