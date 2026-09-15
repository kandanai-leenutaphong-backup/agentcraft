import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";

const optimizer = process.env.OPTIMIZER_URL || "http://127.0.0.1:5180";
const investigation = process.env.INVESTIGATION_URL || "http://127.0.0.1:5175";
const output = process.env.ARTIFACT_DIR || new URL("../../../artifacts/browser/separation", import.meta.url).pathname;
for (const value of [optimizer, investigation]) {
  const url = new URL(value);
  assert.equal(url.protocol, "http:");
  assert.ok(["127.0.0.1", "localhost"].includes(url.hostname));
}
const report = { optimizer, investigation, checks: [], screenshots: [], errors: [], model_calls: false };
const record = (name, detail) => {
  report.checks.push({ name, detail, passed: true });
  console.log(`PASS ${name}: ${JSON.stringify(detail)}`);
};
mkdirSync(output, { recursive: true });
const browser = await chromium.launch();
try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, serviceWorkers: "block" });
    page.on("pageerror", error => report.errors.push(String(error)));
    await page.goto(optimizer, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Custom Optimizer", exact: true }).waitFor();
    const workspace = page.getByTestId("optimization");
    await workspace.getByRole("button", { name: "Create experiment", exact: true }).waitFor();
    assert.equal(await page.getByRole("tab", { name: "Investigation", exact: true }).count(), 0);
    const snapshot = await page.evaluate(async () => (await fetch("/api/cyber/optimization")).json());
    assert.equal(snapshot.available, true);
    assert.ok(snapshot.dataset.counts.evidence > 0);
    await workspace.getByLabel("Test protocol", { exact: true }).selectOption("joint-smoke");
    assert.equal(await workspace.getByLabel("Test protocol", { exact: true }).inputValue(), "joint-smoke");
    const latest = snapshot.experiments.at(-1);
    if (latest) {
      await workspace.getByLabel("Experiment", { exact: true }).selectOption(latest.id);
      await page.waitForFunction(count => document.querySelectorAll(".opt-version-list [data-version]").length === count,
        latest.versions.length);
      const saved = await page.evaluate(async identifier => (await fetch(`/api/cyber/optimization/experiments/${identifier}`)).json(), latest.id);
      assert.equal(saved.versions.length, latest.versions.length);
      assert.ok(saved.versions.every(version => version.status === "completed"));
      record("saved generations read back in standalone app", { width: viewport.width, experiment: latest.id, versions: saved.versions.length });
    }
    const geometry = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
      height: innerHeight, pageHeight: document.documentElement.scrollHeight }));
    assert.ok(geometry.scroll <= geometry.width + 1, JSON.stringify(geometry));
    assert.ok(geometry.pageHeight <= geometry.height + 1, JSON.stringify(geometry));
    const shot = `${output}/optimizer-${viewport.width}.png`;
    await page.screenshot({ path: shot, fullPage: true });
    report.screenshots.push(shot);
    record("standalone optimizer controls and geometry", geometry);
    const terminal = await page.evaluate(async () => {
      const response = await fetch("/api/cyber/optimization/terminal/info", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Copilot-Terminal": "1" }, body: "{}",
      });
      const body = await response.json();
      return { status: response.status, available: body.available };
    });
    assert.equal(terminal.status, 200);
    assert.equal(terminal.available, true);
    record("native CLI is available in standalone host", terminal);
    await page.close();
  }

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, serviceWorkers: "block" });
  page.on("pageerror", error => report.errors.push(String(error)));
  await page.goto(investigation, { waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Investigation", exact: true }).waitFor();
  assert.deepEqual(await page.locator(".header-tabs [role=tab]").allTextContents(),
    ["Investigation", "Data & Tools Catalogue", "Agent Editor"]);
  const boundaries = await page.evaluate(async () => {
    const removed = await fetch("/api/cyber/optimization");
    const inventory = await (await fetch("/api/cyber/inventory/tree")).json();
    return { optimizerStatus: removed.status, useCases: inventory.children.map(node => node.useCaseId) };
  });
  assert.equal(boundaries.optimizerStatus, 404);
  assert.equal(boundaries.useCases.includes("guide"), false);
  await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
  await page.getByTestId("agent-editor").getByRole("button", { name: "Create agent", exact: true }).waitFor();
  assert.equal(await page.getByRole("region", { name: "Optimization versions", exact: true }).count(), 0);
  await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
  const explorer = page.getByTestId("resource-explorer");
  await explorer.locator(".agent-branch > summary").first().click();
  await explorer.locator(".agent-tool-list button").first().click();
  await explorer.locator(".rex-pane:not([hidden]) .scv[data-highlighted=true]").waitFor();
  record("Investigation retains its three workspaces without optimizer hooks", boundaries);
  const shot = `${output}/investigation-1440.png`;
  await page.screenshot({ path: shot, fullPage: true });
  report.screenshots.push(shot);
  await page.close();
  assert.deepEqual(report.errors, []);
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