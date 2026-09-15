import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.CYBEREYE_URL || "http://127.0.0.1:5174";
const output = process.env.ARTIFACT_DIR || "/tmp/cybereye-current-catalogue";
const expectedSources = [
  "perth.adx.events_unified", "perth.gremlin.ontology", "ait.adx.events", "ait.gremlin.aitgraph",
  "cyberkb.search.mitre_attack",
];
const report = { base, started_at: new Date().toISOString(), checks: [], screenshots: [], page_errors: [] };
const record = (name, detail) => {
  report.checks.push({ name, detail, passed: true });
  console.log(`PASS ${name}: ${JSON.stringify(detail)}`);
};
const read = async (path, params = {}) => {
  const url = new URL(path, base);
  url.search = new URLSearchParams(params).toString();
  const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
  assert.equal(response.status, 200, `${path}: HTTP ${response.status}`);
  return response.json();
};

mkdirSync(output, { recursive: true });
const browser = await chromium.launch();
try {
  const root = await read("/api/cyber/inventory/tree");
  const useCases = root.children;
  assert.deepEqual(useCases.map(node => node.useCaseId).sort(),
    ["perth_cybersec_poc_0", "ait", "open_source_cybersecurity"].sort());
  const sources = [];
  for (const useCase of useCases) {
    const tree = await read("/api/cyber/inventory/tree", { node: useCase.id });
    sources.push(...tree.children.map(node => ({ ...node, useCaseLabel: useCase.label })));
  }
  assert.deepEqual(sources.map(node => node.sourceId).sort(), [...expectedSources].sort());
  record("all declared sources are present under their own use cases", { use_cases: useCases.length, sources: sources.length });

  for (const source of sources) {
    const metadata = await read("/api/cyber/inventory/resource", { node: source.id });
    assert.equal(metadata.fixtures, false, source.sourceId);
    assert.equal(metadata.status, "ok", `${source.sourceId}: ${metadata.status}`);
    const preview = await read("/api/cyber/inventory/content", { node: source.id, limit: "2" });
    if (source.sourceId === "guide.sqlite.labels") {
      assert.equal(source.hasContent, false);
      assert.equal(preview.status, "forbidden");
      assert.equal(preview.rows?.length || 0, 0);
      record("GUIDE labels remain evaluator-only", { status: preview.status });
    } else {
      assert.equal(preview.status, "ok", `${source.sourceId}: ${preview.status}`);
      assert.ok(preview.rows.length > 0 && preview.rows.length <= 2, source.sourceId);
      record("real bounded source preview", { source: source.sourceId, rows: preview.rows.length, columns: preview.columns });
    }
  }
  const disabled = await fetch(new URL(`/api/cyber/inventory/content?node=${encodeURIComponent(sources[0].id)}`, base), {
    headers: { "X-Inventory-Selection": "none" }, signal: AbortSignal.timeout(30000),
  });
  assert.equal(disabled.status, 409);
  record("disabled-source read is refused", { status: disabled.status });

  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, serviceWorkers: "block" });
    page.on("pageerror", error => report.page_errors.push(String(error)));
    await page.goto(base, { waitUntil: "domcontentloaded" });
    await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
    const explorer = page.getByTestId("resource-explorer");
    for (const useCase of useCases) {
      const expand = explorer.getByRole("button", { name: `Expand ${useCase.label}`, exact: true });
      if (await expand.count()) await expand.click();
    }
    for (const source of sources) {
      await explorer.locator(`[data-source-id="${source.sourceId}"] .inv-row-label`).click();
      const pane = page.getByRole("region", { name: `${source.label}, ${source.useCaseLabel}`, exact: true });
      await pane.getByRole("region", { name: "Measured now", exact: true }).waitFor({ timeout: 60000 });
      if (source.hasContent) {
        await pane.getByRole("button", { name: "Preview contents", exact: true }).click();
        await pane.locator("tbody tr").first().waitFor({ timeout: 60000 });
        const rows = await pane.locator("tbody tr").count();
        assert.ok(rows > 0 && rows <= 100, source.sourceId);
      } else {
        assert.equal(await pane.getByRole("button", { name: "Preview contents", exact: true }).count(), 0);
        await pane.getByText("Metadata only. Row access is not authorized.", { exact: true }).waitFor();
      }
      const geometry = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
      assert.ok(geometry.document <= geometry.viewport + 1, JSON.stringify(geometry));
      await pane.scrollIntoViewIfNeeded();
      const shot = `${output}/${source.sourceId}-${viewport.width}.png`;
      await page.screenshot({ path: shot, fullPage: true });
      report.screenshots.push(shot);
      record("catalogue control renders real result", { source: source.sourceId, width: viewport.width, geometry });
    }
    await page.close();
  }
  assert.deepEqual(report.page_errors, []);
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.error = String(error);
  throw error;
} finally {
  report.finished_at = new Date().toISOString();
  writeFileSync(`${output}/report.json`, JSON.stringify(report, null, 2));
  await browser.close();
}