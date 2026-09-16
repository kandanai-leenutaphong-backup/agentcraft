import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SourceCodeViewer } from "../dist/SourceCodeViewer.js";

test("compiled viewer renders source as text with original line and truncation state", () => {
  const html = renderToStaticMarkup(createElement(SourceCodeViewer, {
    code: '<script>throw "not executed"</script>\nsecond line', filename: "sample.txt", startLine: 9, truncated: true,
  }));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.match(html, /scv-line-number[^>]*>9<\/span>/);
  assert.ok(html.includes("Truncated preview"));
  assert.ok(html.includes('aria-label="Copy source code"'));
});

test("distribution exports built JavaScript, declarations and byte-identical CSS", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(manifest.exports["."].import, "./dist/index.js");
  assert.equal(manifest.exports["."].types, "./dist/index.d.ts");
  assert.ok(manifest.sideEffects.includes("./dist/index.js"));
  assert.ok(manifest.sideEffects.includes("**/*.css"));
  assert.equal(readFileSync(new URL("../dist/source-code.css", import.meta.url), "utf8"),
    readFileSync(new URL("../frontend/source-code.css", import.meta.url), "utf8"));
  assert.match(readFileSync(new URL("../dist/SourceCodeViewer.d.ts", import.meta.url), "utf8"), /SourceCodeViewerProps/);
});