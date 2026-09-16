import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { startLocalFixture } from "../support/local-ui-acquisition.mjs";

const output = resolve(process.env.ARTIFACT_DIR || "/tmp/agentcraft-local-ui-acquisition");
mkdirSync(output, { recursive: true });
const report = {
  scope: "SYNTHETIC LOCAL component controls, not Investigation backend or provider acceptance",
  persona: { who: "Analyst inspecting local source, inventory and tool results", goal: "Read source and bounded rows, recover a failed read, inspect remaining rows without executing code", known: "Source files, tables and keyboard navigation", not_known: "These components and their control names", constraints: "Desktop mouse/keyboard; mobile emulated touch plus keyboard" },
  checks: [], observations: [], gaps: [], errors: [],
};
const fixture = await startLocalFixture(output);
Object.assign(report, { environment: fixture.environment, packages: fixture.packages, bundle: fixture.bundle, runtime: fixture.runtime, base: fixture.base });
const check = (name, passed, detail = {}) => {
  report.checks.push({ name, passed: Boolean(passed), detail });
  console.log(`${passed ? "PASS" : "FAIL"} ${name}`);
};
const settle = (page) => page.evaluate(() => new Promise((resolveFrame) => requestAnimationFrame(() => requestAnimationFrame(resolveFrame))));
const press = async (page, locator, key = "Enter") => { await locator.focus(); await page.keyboard.press(key); };

async function snapshot(page, component, state, viewport) {
  await settle(page);
  const geometry = await page.evaluate(() => {
    const rectangle = (node) => { const box = node.getBoundingClientRect(); return { x: box.x, y: box.y, width: box.width, height: box.height, right: box.right, bottom: box.bottom }; };
    const controls = [...document.querySelectorAll("main > section button, main > section input, main > section summary, main > section select")]
      .filter((node) => node.getClientRects().length && node.getBoundingClientRect().width > 0)
      .map((node) => ({ name: node.getAttribute("aria-label") || node.textContent.trim(), tag: node.tagName, role: node.getAttribute("role"), box: rectangle(node), hitBox: rectangle(node.labels?.[0] || node), className: node.className, focused: document.activeElement === node, outline: getComputedStyle(node).outline, outlineOffset: getComputedStyle(node).outlineOffset, pressed: node.getAttribute("aria-pressed") }));
    const regions = [...document.querySelectorAll('[data-testid="resource-explorer"] > .rex-navigation, [data-testid="resource-explorer"] > .rex-viewer')].map((node) => ({ className: node.className, box: rectangle(node) }));
    const scrollers = [...document.querySelectorAll("main > section *")].filter((node) => /(auto|scroll)/.test(getComputedStyle(node).overflowX + getComputedStyle(node).overflowY) && (node.scrollWidth > node.clientWidth || node.scrollHeight > node.clientHeight)).map((node) => ({ tag: node.tagName, className: node.className, clientWidth: node.clientWidth, scrollWidth: node.scrollWidth, clientHeight: node.clientHeight, scrollHeight: node.scrollHeight, scrollLeft: node.scrollLeft, scrollTop: node.scrollTop }));
    return { viewport: { width: innerWidth, height: innerHeight }, document: { width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight }, touchPoints: navigator.maxTouchPoints, controls, regions, scrollers, sentinelExecuted: globalThis.__sourceExecuted === true };
  });
  const path = `${output}/${component}-${state}-${viewport.width}x${viewport.height}.png`;
  const bytes = await page.screenshot({ path, fullPage: true });
  const observation = { component, state, viewport, screenshot: path, png: { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) }, geometry };
  report.observations.push(observation);
  check(`${component}/${state}/${viewport.width}: no page horizontal overflow`, geometry.document.scrollWidth <= geometry.document.width, geometry.document);
  if (viewport.width < 700) {
    const small = geometry.controls.filter((control) => control.hitBox.width < 44 || control.hitBox.height < 44);
    check(`${component}/${state}/${viewport.width}: mobile targets at least 44x44`, small.length === 0, { controls: geometry.controls.map(({ name, hitBox }) => ({ name, width: hitBox.width, height: hitBox.height })), touchPoints: geometry.touchPoints });
    if (small.length) report.gaps.push({ kind: "touch-target", component, state, viewport, expected: "effective mobile target at least 44x44 CSS px", controls: small, screenshot: path });
  }
  return observation;
}

async function sourceWalk(page, viewport) {
  const prefix = `source/${viewport.width}`;
  await page.getByLabel("Fixture surface").selectOption("source");
  const viewer = page.locator(".scv");
  await page.locator(".scv[data-highlighted=true]").waitFor();
  check(`${prefix}: highlighted safe text`, await viewer.locator(".scv-line-content").allTextContents().then((lines) => lines.join("\n") === undefined ? false : lines.join("\n").includes('globalThis.__sourceExecuted = true;')) && await viewer.locator("img,script").count() === 0 && !(await page.evaluate(() => globalThis.__sourceExecuted === true)));
  check(`${prefix}: original line and truncation`, await viewer.locator(".scv-line-number").first().textContent() === "7" && (await viewer.locator(".scv-status").innerText()).includes("Truncated preview"));
  await page.getByLabel("Source input").focus();
  await page.keyboard.press("Tab");
  const wrap = page.getByRole("button", { name: "Wrap lines", exact: true });
  check(`${prefix}: Tab reaches wrap`, await wrap.evaluate((node) => document.activeElement === node));
  await page.keyboard.press("Enter");
  check(`${prefix}: Enter toggles wrap`, await wrap.getAttribute("aria-pressed") === "true");
  await snapshot(page, "source", "wrapped-keyboard", viewport);
  const copy = page.getByRole("button", { name: /^(Copy|Copied) source code$/ });
  await page.keyboard.press("Tab");
  check(`${prefix}: Tab reaches copy`, await copy.evaluate((node) => document.activeElement === node));
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Copied source code", exact: true }).waitFor();
  check(`${prefix}: native clipboard original read-back`, await page.evaluate(async () => (await navigator.clipboard.readText()) === window.__fixture.sentinel));
  await page.evaluate(() => { window.__fixture.originalWrite = navigator.clipboard.writeText.bind(navigator.clipboard); navigator.clipboard.writeText = async () => { throw new DOMException("Synthetic clipboard refusal", "NotAllowedError"); }; });
  await copy.click();
  await viewer.getByRole("alert").waitFor();
  check(`${prefix}: synthetic clipboard refusal is explicit`, (await viewer.getByRole("alert").innerText()) === "Could not copy source code.");
  await snapshot(page, "source", "copy-refusal", viewport);
  await page.evaluate(() => { navigator.clipboard.writeText = window.__fixture.originalWrite; });
  await press(page, copy);
  await viewer.getByRole("alert").waitFor({ state: "hidden" });
  check(`${prefix}: clipboard retry clears failure`, await page.evaluate(async () => (await navigator.clipboard.readText()) === window.__fixture.sentinel));
  await page.getByLabel("Source input").selectOption("unknown");
  await page.locator('.scv[data-language="text"]').waitFor();
  check(`${prefix}: unknown language falls back to plain text`, await viewer.getAttribute("data-highlighted") === "false" && (await viewer.locator(".scv-language").innerText()) === "Plain text");
  await page.getByLabel("Source input").selectOption("sentinel");
  await page.getByLabel("Source input").selectOption("replacement");
  await page.locator(".scv[data-highlighted=true]").waitFor();
  check(`${prefix}: source switch discards prior content`, await viewer.locator(".scv-line-content").allTextContents().then((lines) => lines.join("\n").includes("replacement-only") && !lines.join("\n").includes("__sourceExecuted")));
  await snapshot(page, "source", "replacement", viewport);
  for (const input of ["arguments", "arguments-kql"]) {
    await page.getByLabel("Source input").selectOption(input);
    if (input === "arguments-kql") await page.locator(".scv[data-highlighted=true]").waitFor();
    const original = await page.evaluate((value) => window.__fixture[value === "arguments-kql" ? "query" : "sentinel"], input);
    check(`${prefix}/${input}: full original lines`, JSON.stringify(await viewer.locator(".scv-line-content").allTextContents()) === JSON.stringify(original.split(/\r\n|\r|\n/)));
    check(`${prefix}/${input}: conservative language and caption`, await viewer.getAttribute("data-language") === (input === "arguments-kql" ? "kusto" : "text") && await viewer.locator(".scv-filename").textContent() === (input === "arguments-kql" ? "KQL · query text" : "code · shell"));
    check(`${prefix}/${input}: original display bounds`, await viewer.getByRole("button", { name: "Wrap lines" }).getAttribute("aria-pressed") === "true" && await viewer.locator("pre").evaluate((node) => node.style.maxHeight) === "220px" && await viewer.locator(".scv-line-number").first().textContent() === "1");
    await press(page, viewer.getByRole("button", { name: "Copy source code", exact: true }));
    await viewer.getByRole("button", { name: "Copied source code", exact: true }).waitFor();
    check(`${prefix}/${input}: native clipboard preserves original bytes`, await page.evaluate(() => navigator.clipboard.readText()) === original);
    check(`${prefix}/${input}: markup remains inert`, await viewer.locator("img,script").count() === 0 && !(await page.evaluate(() => globalThis.__sourceExecuted === true)));
    await snapshot(page, "source", input, viewport);
  }
}

async function inventoryWalk(page, viewport) {
  const prefix = `inventory/${viewport.width}`;
  await page.getByLabel("Fixture surface").selectOption("catalogue");
  await page.getByText("Synthetic catalogue unavailable", { exact: true }).waitFor();
  await snapshot(page, "inventory", "catalogue-failure", viewport);
  await press(page, page.getByRole("button", { name: "Retry", exact: true }));
  await page.getByText("Synthetic analyst", { exact: true }).first().waitFor();
  check(`${prefix}: catalogue Retry loads actual tool navigation`, await page.evaluate(() => window.__fixture.agents === 2));
  await press(page, page.getByRole("button", { name: "Expand Synthetic local inventory", exact: true }));
  const events = page.locator('[data-source-id="synthetic.events"]');
  await events.waitFor();
  check(`${prefix}: expand opens two declared sources`, await page.locator('[data-kind="source"]').count() === 2);
  await press(page, events);
  await page.getByRole("button", { name: "Preview contents", exact: true }).waitFor();
  await press(page, page.getByRole("button", { name: "Preview contents", exact: true }));
  await page.locator(".inv-rows table tbody tr").first().waitFor();
  const rows = await page.locator(".inv-rows table tbody tr").count();
  check(`${prefix}: bounded preview read-back`, rows === 3 && (await page.locator(".inv-rows").innerText()).includes("Synthetic preview limited to 3 of 7 rows"), { rows });
  const announcement = await page.locator('[aria-live="polite"]').allTextContents();
  const honest = announcement.some((text) => text.includes("3 rows previewed")) && !announcement.some((text) => text.includes("1400 rows previewed"));
  check(`${prefix}: preview announcement uses row count`, honest, { rows, sizeBytes: 1400, announcement });
  if (!honest) report.gaps.push({ kind: "row-announcement", component: "inventory", viewport, expected: "3 rows previewed", observed: announcement, input: { rows: 3, sizeBytes: 1400 } });
  const sort = page.locator(".inv-rows").getByRole("button", { name: /^value$/i });
  await press(page, sort);
  check(`${prefix}: keyboard sorts rows`, JSON.stringify(await page.locator(".inv-rows tbody tr td:nth-child(2)").allTextContents()) === JSON.stringify(["1", "2", "3"]));
  await snapshot(page, "inventory", "preview", viewport);
  check(`${prefix}: cell sentinel remains text`, await page.locator(".inv-rows img,.inv-rows script").count() === 0 && !(await page.evaluate(() => globalThis.__sourceExecuted === true)));
  const beforeDisable = await page.evaluate(() => window.__fixture.requests.filter((request) => request.path.endsWith("/content")).length);
  const toggle = page.getByRole("checkbox", { name: /^Use Synthetic events,/ });
  await press(page, toggle, "Space");
  await page.locator('.inv-notice[data-state="disabled"]').waitFor();
  const selection = await page.evaluate(() => sessionStorage.getItem("cybereye.inventory.selection"));
  check(`${prefix}: Space disables source and stores narrowed selection`, await events.getAttribute("data-enabled") === "false" && selection.includes("synthetic.offline") && !selection.includes("synthetic.events"), { selection });
  check(`${prefix}: disabled view offers no content read`, await page.getByRole("button", { name: "Preview contents", exact: true }).count() === 0 && await page.evaluate(() => window.__fixture.requests.filter((request) => request.path.endsWith("/content")).length) === beforeDisable);
  await page.getByLabel("Fixture surface").selectOption("source");
  await page.getByLabel("Fixture surface").selectOption("catalogue");
  await press(page, page.getByRole("button", { name: "Expand Synthetic local inventory", exact: true }));
  await page.locator('[data-source-id="synthetic.events"][data-enabled="false"]').waitFor();
  check(`${prefix}: selection read-back survives component remount`, await page.evaluate(() => sessionStorage.getItem("cybereye.inventory.selection")) === selection);
  await press(page, page.getByRole("checkbox", { name: /^Use Synthetic events,/ }), "Space");
  await page.locator('[data-source-id="synthetic.events"][data-enabled="true"]').waitFor();
  await events.focus();
  await page.keyboard.press("ArrowDown");
  check(`${prefix}: ArrowDown reaches next source`, await page.evaluate(() => document.activeElement?.getAttribute("data-source-id")) === "synthetic.offline");
  await page.keyboard.press("Enter");
  await page.getByText("Synthetic transport unavailable; retry is local", { exact: true }).waitFor();
  await snapshot(page, "inventory", "metadata-failure", viewport);
  await press(page, page.getByRole("button", { name: "Retry", exact: true }));
  await page.getByText("Synthetic transport unavailable; retry is local", { exact: true }).waitFor({ state: "hidden" });
  check(`${prefix}: metadata Retry reads recovered result`, await page.evaluate(() => window.__fixture.offlineReads === 2) && (await page.locator(".inv-metrics").innerText()).includes("3"));
  await press(page, page.locator(".agent-branch > summary").first());
  await page.keyboard.press("Tab");
  const firstTool = page.getByRole("button", { name: "Inspect synthetic source", exact: true });
  check(`${prefix}: Tab reaches tool source control`, await firstTool.evaluate((node) => document.activeElement === node));
  await page.keyboard.press("Enter");
  await page.locator(".rex-pane:not([hidden]) .scv[data-highlighted=true]").waitFor();
  check(`${prefix}: opened source is safe and dependency is identified`, (await page.locator(".rex-pane:not([hidden]) .scv").innerText()).includes("__sourceExecuted") && (await events.innerText()).includes("TOOL DEPENDENCY") && !(await page.evaluate(() => globalThis.__sourceExecuted === true)));
  await press(page, page.locator("summary").filter({ hasText: /^Parameters/ }), "Space");
  await page.getByText("Synthetic row limit", { exact: true }).waitFor();
  await snapshot(page, "inventory", "source-parameters", viewport);
  const replacementTool = page.getByRole("button", { name: "Inspect replacement source", exact: true });
  if (viewport.width < 700) await replacementTool.tap(); else await replacementTool.click();
  await page.locator(".rex-pane:not([hidden]) .scv").getByText(/replacement-only/).waitFor();
  check(`${prefix}: switch tools replaces source`, !(await page.locator(".rex-pane:not([hidden]) .scv").innerText()).includes("__sourceExecuted"));
  await snapshot(page, "inventory", "source-switched", viewport);
  report.observations.push({ component: "inventory", viewport, request_trace: await page.evaluate(() => window.__fixture.requests), selection_readback: await page.evaluate(() => sessionStorage.getItem("cybereye.inventory.selection")) });
}

async function modularWalk(page, viewport) {
  const prefix = `modular/${viewport.width}`;
  await page.getByLabel("Fixture surface").selectOption("modular");
  check(`${prefix}: row cap starts at five`, await page.locator("tbody tr").count() === 5);
  await page.getByLabel("Result state").focus();
  await page.keyboard.press("Tab");
  const metadata = page.getByRole("button", { name: "show metadata (1)", exact: true });
  check(`${prefix}: Tab reaches metadata`, await metadata.evaluate((node) => document.activeElement === node));
  await page.keyboard.press("Enter");
  check(`${prefix}: Enter opens metadata column`, await page.locator("thead th").count() === 3);
  await snapshot(page, "modular", "metadata-keyboard", viewport);
  const expand = page.getByRole("button", { name: "show all (7 more)", exact: true });
  if (viewport.width < 700) await expand.tap(); else await press(page, expand);
  check(`${prefix}: expand reads all twelve rows`, await page.locator("tbody tr").count() === 12);
  const last = page.locator("tbody tr").last();
  await last.scrollIntoViewIfNeeded();
  const lastVisible = await last.evaluate((node) => { const box = node.getBoundingClientRect(); const ancestor = node.closest("table").parentElement; const clip = ancestor.getBoundingClientRect(); return box.top >= clip.top && box.bottom <= clip.bottom + 1; });
  check(`${prefix}: last row reachable inside bounded scroller`, lastVisible);
  await snapshot(page, "modular", "all-rows", viewport);
  await press(page, page.getByRole("button", { name: "collapse", exact: true }), "Space");
  await press(page, page.getByRole("button", { name: "hide metadata", exact: true }));
  check(`${prefix}: collapse and hide restore preview`, await page.locator("tbody tr").count() === 5 && await page.locator("thead th").count() === 2);
  await page.getByLabel("Result state").selectOption("error");
  await page.getByRole("alert").waitFor();
  check(`${prefix}: failure is explicit alert`, (await page.getByRole("alert").innerText()).includes("Synthetic transport unavailable"));
  await snapshot(page, "modular", "failure", viewport);
  await page.getByLabel("Result state").selectOption("refused");
  check(`${prefix}: refusal distinct from failure`, (await page.locator("main > section").innerText()).includes("REFUSED") && await page.getByRole("alert").count() === 0);
  await page.getByLabel("Result state").selectOption("empty");
  check(`${prefix}: empty envelope does not retain rows`, await page.locator("tbody tr").count() === 0);
  await page.getByLabel("Result state").selectOption("rows");
  check(`${prefix}: controlled result recovery restores five rows`, await page.locator("tbody tr").count() === 5 && await page.getByRole("alert").count() === 0);
  await snapshot(page, "modular", "recovered", viewport);
}

try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const context = await fixture.context(viewport);
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.on("pageerror", (error) => report.errors.push({ viewport, message: error.message }));
    await page.goto(fixture.base, { waitUntil: "networkidle" });
    for (const [name, walk] of [["source", sourceWalk], ["inventory", inventoryWalk], ["modular", modularWalk]]) {
      if (process.env.LOCAL_UI_SURFACES && !process.env.LOCAL_UI_SURFACES.split(",").includes(name)) continue;
      try { await walk(page, viewport); }
      catch (error) { report.errors.push({ viewport, component: name, message: error.message }); check(`${name}/${viewport.width}: journey completed`, false, { error: error.message }); await snapshot(page, name, "stopped", viewport); }
    }
    check(`all/${viewport.width}: sentinel never executed or inserted`, !(await page.evaluate(() => globalThis.__sourceExecuted === true)) && !fixture.blocked.some((entry) => entry.url.includes("sentinel-request")));
    await context.close();
  }
  check("network: only declared fixture assets requested", fixture.blocked.length === 0 && fixture.delivered.every((entry) => entry.method === "GET" && ["/", "/fixture.js", "/fixture.css"].includes(entry.path)), { blocked: fixture.blocked, delivered: fixture.delivered });
} finally {
  await fixture.close();
  report.cleanup = { retained_servers: 0, browser_closed: !fixture.browser.isConnected(), retained_artifacts: output, data_deleted: false };
  report.counts = { checks: report.checks.length, passed: report.checks.filter((entry) => entry.passed).length, failed: report.checks.filter((entry) => !entry.passed).length, errors: report.errors.length, observations: report.observations.length };
  report.status = report.counts.failed || report.errors.length || report.gaps.length ? "blocked" : "complete";
  writeFileSync(`${output}/result.json`, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ status: report.status, ...report.counts, gap_observations: report.gaps.length, output, cleanup: report.cleanup }));
}
if (report.status !== "complete") process.exitCode = 1;