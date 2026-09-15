// Data-sources inventory: the journey an analyst actually walks, in a real browser.
//
// Run the app first (backend on 9000 with the graph coordinates exported, frontend on 5173):
//   set -a && source app/data/gremlin.env && set +a && app/cybereye/dev.sh
//   node app/cybereye/frontend/verify-inventory.mjs
//
// Prints one JSON report and exits non-zero on any failed check. Screenshots land in
// app/cybereye/frontend/artifacts/, or in ARTIFACT_DIR when one is named.
//
// Three things this proves that a test render cannot. Geometry: the panes are measured at
// both shipped viewports, so a tree squeezed to nothing fails here rather than in review.
// Session independence: tab B is a separate browser context with its own sessionStorage,
// so "switched off here, still working there" is observed and not asserted. Reachability:
// sections 12 to 15 load the app cold at five narrow widths in five fresh contexts and
// press real keys, because the defects they cover — a drawer painted over the tab strip,
// a tree that swallowed Space aimed at a checkbox — are invisible to a walk that resizes
// after the feature is already open, or that clicks where it means to press.

import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { signContext, signingConfigured } from '../support/verify-auth.mjs';

const BASE = process.env.CYBEREYE_URL ?? 'http://127.0.0.1:5173';
const rawDir = process.env.ARTIFACT_DIR ?? new URL('../../artifacts/', import.meta.url).pathname;
const SHOTS = rawDir.endsWith('/') ? rawDir : `${rawDir}/`;
const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

const checks = [];
const check = (id, ok, detail) => { checks.push({ id, ok: Boolean(ok), detail }); return ok; };

const browser = await chromium.launch({ headless: true });
await mkdir(SHOTS, { recursive: true });

// Every context is created through this, so none can be left unsigned by accident. A walk
// against a deployed host with one unsigned context reports the sign-in page's absent
// controls as application defects.
async function newContext(options) {
  const context = await browser.newContext({ serviceWorkers: 'block', ...options });
  await signContext(context, BASE);
  return context;
}

// A console error that names no resource cannot be acted on, so the failing URL is appended.
const consoleText = (m) => `${m.text()} ${m.location()?.url ?? ''}`.trim();
const consoleErrors = [];
// The walk deliberately asks the server for a source it has just switched off, so
// the browser logs one 409 as a failed resource load. That is the proof, not a fault.
// Section 10 deliberately sends a stale selection, which is refused with 400 for the
// same reason; that window is opened and closed around it rather than left open.
let expectingRejections = false;
const noise = (text) =>
  /status of 409/.test(text) || (expectingRejections && /status of 400/.test(text));
const report = { signed: signingConfigured() };

async function openApp(context, viewport) {
  const page = await context.newPage();
  await page.setViewportSize(viewport);
  page.on('console', (m) => { if (m.type() === 'error' && !noise(consoleText(m))) consoleErrors.push(consoleText(m)); });
  page.on('pageerror', (e) => { if (!noise(e.message)) consoleErrors.push(e.message); });
  await page.goto(BASE, { waitUntil: 'networkidle' });
  return page;
}

const contextA = await newContext();
const page = await openApp(contextA, DESKTOP);

// ---- 9. the investigation view exists first, and must survive the switch ----------------
await page.getByRole('button', { name: 'Scan ADX window' }).first().waitFor({ state: 'visible' });
const scenario = page.getByLabel('Test Scenarios');
await scenario.selectOption({ index: 1 });
const beforeSwitch = {
  scenario: await scenario.inputValue(),
  start: await page.getByLabel('Scan start UTC').inputValue(),
};

// ---- 1. the tab is discoverable, and the root lists exactly two use cases ---------------
const tab = page.getByRole('tab', { name: 'Data sources' });
check('1a-tab-present', await tab.isVisible(), 'a top-level tab, not a nested one');
await tab.click();
await page.locator('.inv-tree [role="treeitem"]').first().waitFor();

const useCases = await page.locator('[data-kind="use_case"]').evaluateAll((nodes) =>
  nodes.map((n) => n.querySelector('.inv-row-label b')?.textContent ?? ''));
report.useCases = useCases;
check('1b-two-use-cases', useCases.length === 2, useCases.join(' | '));
check('1c-exact-labels',
  useCases.includes('Perth Cybersec POC_0') && useCases.includes('AIT'), useCases.join(' | '));
const strayResources = await page.locator('[data-kind="resource"], [data-kind="resource_group"]').count();
check('1d-no-subscription-estate', strayResources === 0, `${strayResources} estate nodes`);

// ---- 2. each use case opens onto its own three slots -------------------------------------
for (const label of useCases) {
  await page.locator(`[data-kind="use_case"]:has-text("${label}") .inv-twisty`).click();
}
// Both expansions are separate fetches. Waiting for the first source row would
// snapshot whichever branch happened to answer first.
await page.waitForFunction(
  () => document.querySelectorAll('[data-kind="source"]').length === 6, null, { timeout: 30000 });

const sources = await page.locator('[data-kind="source"]').evaluateAll((nodes) =>
  nodes.map((n) => ({
    sourceId: n.getAttribute('data-source-id'),
    enabled: n.getAttribute('data-enabled'),
    label: n.querySelector('.inv-row-label b')?.textContent ?? '',
    tags: [...n.querySelectorAll('.inv-tag')].map((t) => t.textContent),
    badge: n.querySelector('.inv-badge')?.textContent ?? null,
  })));
report.sources = sources;
check('2a-six-sources', sources.length === 6, `${sources.length}`);
check('2b-type-tags', sources.every((s) => s.tags.length > 0), JSON.stringify(sources.map((s) => s.tags)));

// Name matching is what misfiles a source. Ids carry the use case; assert on the ids.
const perthIds = sources.filter((s) => s.sourceId.startsWith('perth.')).map((s) => s.sourceId);
const aitIds = sources.filter((s) => s.sourceId.startsWith('ait.')).map((s) => s.sourceId);
check('2c-three-per-use-case', perthIds.length === 3 && aitIds.length === 3,
  `${perthIds.join(',')} / ${aitIds.join(',')}`);

const aitRowIndex = sources.findIndex((s) => s.sourceId === 'ait.adx.events');
const perthRowIndex = sources.findIndex((s) => s.sourceId === 'perth.adx.events_unified');
check('2d-ait-not-under-perth', aitRowIndex > perthRowIndex, `${perthRowIndex} -> ${aitRowIndex}`);

// ---- 3. a configured source yields live, timestamped metadata ----------------------------
async function openSource(sourceId) {
  await page.locator(`[data-source-id="${sourceId}"] .inv-row-label`).click();
  await page.locator('.inv-detail h2').waitFor();
}

async function readDetail() {
  return page.evaluate(() => {
    const pane = document.querySelector('.inv-detail');
    if (!pane) return null;
    const kv = {};
    for (const row of pane.querySelectorAll('.inv-kv > div')) {
      kv[row.querySelector('dt')?.textContent ?? ''] = row.querySelector('dd')?.textContent ?? '';
    }
    return {
      title: pane.querySelector('h2')?.textContent ?? '',
      eyebrow: pane.querySelector('.inv-eyebrow')?.textContent ?? '',
      metrics: [...pane.querySelectorAll('.inv-metrics > div')]
        .map((m) => `${m.querySelector('span')?.textContent}=${m.querySelector('b')?.textContent}`),
      kv,
      capabilities: [...pane.querySelectorAll('.inv-chips .inv-tag')].map((t) => t.textContent),
      schemaCount: pane.querySelectorAll('.inv-schema span').length,
      provenance: pane.querySelector('.inv-provenance')?.textContent ?? '',
      observed: [...pane.querySelectorAll('.inv-observed')].map((o) => o.textContent),
      statusNotes: [...pane.querySelectorAll('.inv-note')].map((n) => n.textContent.trim()),
    };
  });
}

await openSource('perth.adx.events_unified');
await page.waitForFunction(() => document.querySelectorAll('.inv-metrics > div').length > 0, null,
  { timeout: 60000 });
const perthAdx = await readDetail();
report.perthAdx = perthAdx;
check('3a-live-row-count', perthAdx.metrics.some((m) => m.startsWith('Rows=') && m !== 'Rows=0'),
  perthAdx.metrics.join(' '));
check('3b-coordinates', perthAdx.kv.Endpoint?.includes('kusto.windows.net')
  && perthAdx.kv.Database === 'PerthCyber' && perthAdx.kv.Table === 'EventsUnified',
  JSON.stringify(perthAdx.kv));
check('3c-connector-identity', perthAdx.kv.Name?.includes('Data Explorer') && Boolean(perthAdx.kv.Id),
  JSON.stringify(perthAdx.kv));
check('3d-capabilities', perthAdx.capabilities.length > 0, perthAdx.capabilities.join(','));
check('3e-schema', perthAdx.schemaCount > 100, `${perthAdx.schemaCount} fields`);
check('3f-provenance-caveat', /replay/i.test(perthAdx.provenance) && /not live/i.test(perthAdx.provenance),
  perthAdx.provenance);
check('3g-timestamped', perthAdx.observed.some((o) => /Read at \d{4}-\d{2}-\d{2}T/.test(o)),
  perthAdx.observed.join(' | '));

// ---- 4. bounded preview of real rows ------------------------------------------------------
async function preview() {
  await page.getByRole('button', { name: 'Preview contents' }).click();
  await page.locator('.inv-rows table tbody tr').first().waitFor({ timeout: 60000 });
  return page.evaluate(() => ({
    scale: document.querySelector('.inv-rows-scale')?.textContent ?? '',
    notes: [...document.querySelectorAll('.inv-rows-notes li')].map((n) => n.textContent ?? ''),
    columns: [...document.querySelectorAll('.inv-rows thead th')].map((h) => h.textContent),
    rows: document.querySelectorAll('.inv-rows tbody tr').length,
    firstCell: document.querySelector('.inv-rows tbody td')?.textContent ?? '',
  }));
}

const perthRows = await preview();
report.perthRows = perthRows;
check('4a-real-rows', perthRows.rows > 0 && perthRows.columns.includes('source_time'),
  `${perthRows.rows} rows, ${perthRows.columns.length} columns`);
check('4b-sample-scale', /of 15,520/.test(perthRows.scale) && /sample limit/.test(perthRows.scale),
  perthRows.scale);
check('4c-truncation-stated', /truncated/.test(perthRows.scale), perthRows.scale);
// A bounded sample may be lossy only where it says which bound made it lossy.
check('4f-bound-is-named', perthRows.notes.length > 0
  && perthRows.notes.some((n) => /not in this sample|sample limit|bytes|shortened|column/.test(n)),
  perthRows.notes.join(' | '));

await page.screenshot({ path: `${SHOTS}inventory-desktop.png`, fullPage: false });

// Both graphs, each in its own vocabulary.
for (const [id, expect] of [['perth.gremlin.ontology', 'Vertices'], ['ait.gremlin.aitgraph', 'Vertices']]) {
  await openSource(id);
  await page.waitForFunction(() => document.querySelectorAll('.inv-metrics > div').length > 0, null,
    { timeout: 60000 });
  const detail = await readDetail();
  const rows = await preview();
  report[id] = { metrics: detail.metrics, columns: rows.columns, rows: rows.rows };
  check(`4d-${id}`, detail.metrics.some((m) => m.startsWith(`${expect}=`)) && rows.rows > 0,
    `${detail.metrics.join(' ')} :: ${rows.columns.join(',')}`);
}
check('4e-graph-vocabularies-differ',
  JSON.stringify(report['perth.gremlin.ontology'].columns)
    !== JSON.stringify(report['ait.gremlin.aitgraph'].columns),
  `${report['perth.gremlin.ontology'].columns} vs ${report['ait.gremlin.aitgraph'].columns}`);

// ---- 5. the Search slot reads its own index, and says which one -----------------------
// It used to be unconfigured, and this section asserted that it said so. The service now
// exists, so the honest assertion is the opposite one: a live count, the index it came from,
// and a preview offered because there is something to preview.
await openSource('perth.search.index');
// The slot used to answer instantly because it answered "not configured". Now it makes a
// live call, so reading the pane before the call lands reads an empty pane.
await page.locator('.inv-detail .inv-metrics > div').first().waitFor({ timeout: 60000 });
const searchSlot = await readDetail();
report.searchSlot = searchSlot;
check('5a-configured', !searchSlot.statusNotes.some((n) => /Not configured/.test(n)),
  searchSlot.statusNotes.join(' | ') || 'no unconfigured note');
check('5b-live-document-count',
  searchSlot.metrics.some((m) => /Documents=15,?520/.test(m)),
  searchSlot.metrics.join(' '));
const searchPaneText = await page.locator('.inv-detail').innerText();
check('5c-names-its-index',
  searchPaneText.includes('perth-events') && searchPaneText.includes('search.windows.net'),
  searchPaneText.split('\n').filter((line) => /perth-events|windows\.net/.test(line)).join(' | '));
check('5d-probe-offered', await page.getByRole('button', { name: 'Preview contents' }).isVisible(),
  'a configured slot offers a preview');

// ---- 8. keyboard reach -------------------------------------------------------------------
await page.locator('[data-source-id="perth.adx.events_unified"]').focus();
const keyboard = { start: await page.evaluate(() => document.activeElement?.getAttribute('data-source-id')) };
await page.keyboard.press('ArrowDown');
keyboard.afterDown = await page.evaluate(() => document.activeElement?.getAttribute('data-source-id'));
await page.keyboard.press('Enter');
await page.locator('.inv-detail h2').waitFor();
keyboard.selectedTitle = await page.locator('.inv-detail h2').textContent();
await page.locator('[data-source-id="ait.adx.events"]').focus();
await page.keyboard.press('t');
await page.locator('[data-source-id="ait.adx.events"][data-enabled="false"]').waitFor();
keyboard.toggled = await page.getAttribute('[data-source-id="ait.adx.events"]', 'data-enabled');
report.keyboard = keyboard;
check('8a-keyboard-walks', keyboard.afterDown && keyboard.afterDown !== keyboard.start,
  JSON.stringify(keyboard));
check('8b-keyboard-selects', Boolean(keyboard.selectedTitle), keyboard.selectedTitle);
check('8c-keyboard-toggles', keyboard.toggled === 'false', String(keyboard.toggled));

// ---- 6. session selection: refused here, survives reload, unaffected elsewhere -------------
await openSource('ait.adx.events');
const disabledPane = await readDetail();
report.disabledPane = disabledPane;
check('6a-disabled-shows-no-preview',
  !(await page.getByRole('button', { name: 'Preview contents' }).isVisible())
  && (await page.locator('.inv-notice[data-state="disabled"]').isVisible()),
  'a switched-off source offers no read and says why');

const refusal = await page.evaluate(async () => {
  const row = document.querySelector('[data-source-id="ait.adx.events"]');
  const stored = window.sessionStorage.getItem('cybereye.inventory.selection');
  const parsed = JSON.parse(stored ?? '{}');
  const header = parsed.mode === 'all' ? 'all'
    : parsed.mode === 'none' ? 'none' : (parsed.ids ?? []).join(',');
  const id = row?.getAttribute('data-node-id') ?? '';
  const response = await fetch(`/api/cyber/inventory/content?node=${encodeURIComponent(id)}&limit=3`,
    { headers: { 'X-Inventory-Selection': header } });
  return { stored, header, status: response.status, body: await response.text() };
});
report.refusal = refusal;
check('6b-server-refuses-disabled', refusal.status === 409 && refusal.body.includes('source_disabled'),
  `${refusal.status} ${refusal.body}`);
check('6c-selection-is-per-tab-storage',
  refusal.stored !== null && !refusal.header.includes('ait.adx.events'),
  String(refusal.stored));

// same-tab navigation
await page.reload({ waitUntil: 'networkidle' });
await page.getByRole('tab', { name: 'Data sources' }).click();
await page.locator('.inv-tree [role="treeitem"]').first().waitFor();
for (const label of useCases) {
  await page.locator(`[data-kind="use_case"]:has-text("${label}") .inv-twisty`).click();
}
await page.waitForFunction(
  () => document.querySelectorAll('[data-kind="source"]').length === 6, null, { timeout: 30000 });
const afterReload = await page.getAttribute('[data-source-id="ait.adx.events"]', 'data-enabled');
report.afterReload = afterReload;
check('6d-survives-same-tab-reload', afterReload === 'false', String(afterReload));

// an independent tab, with its own sessionStorage
const contextB = await newContext();
const pageB = await openApp(contextB, DESKTOP);
await pageB.getByRole('tab', { name: 'Data sources' }).click();
await pageB.locator('.inv-tree [role="treeitem"]').first().waitFor();
for (const label of useCases) {
  await pageB.locator(`[data-kind="use_case"]:has-text("${label}") .inv-twisty`).click();
}
await pageB.waitForFunction(
  () => document.querySelectorAll('[data-kind="source"]').length === 6, null, { timeout: 30000 });
const otherSession = await pageB.getAttribute('[data-source-id="ait.adx.events"]', 'data-enabled');
report.otherSession = otherSession;
check('6e-other-session-unaffected', otherSession === 'true', String(otherSession));

await pageB.locator('[data-source-id="ait.adx.events"] .inv-row-label').click();
await pageB.waitForFunction(() => document.querySelectorAll('.inv-metrics > div').length > 0, null,
  { timeout: 60000 });
const otherRows = await (async () => {
  await pageB.getByRole('button', { name: 'Preview contents' }).click();
  await pageB.locator('.inv-rows table tbody tr').first().waitFor({ timeout: 60000 });
  return pageB.evaluate(() => ({
    rows: document.querySelectorAll('.inv-rows tbody tr').length,
    scale: document.querySelector('.inv-rows-scale')?.textContent ?? '',
  }));
})();
report.otherRows = otherRows;
check('6f-other-session-still-reads', otherRows.rows > 0 && /of 814,887/.test(otherRows.scale),
  JSON.stringify(otherRows));
await contextB.close();

// stale results must not repopulate a pane after the selection changes
const stale = await page.evaluate(() => {
  const pane = document.querySelector('.inv-detail');
  return { rowsShown: pane?.querySelectorAll('.inv-rows tbody tr').length ?? 0 };
});
report.stale = stale;
check('6g-no-stale-preview', stale.rowsShown === 0, `${stale.rowsShown} rows still shown`);

// turn it back on and confirm the switch actually did something reversible
await page.locator('[data-source-id="ait.adx.events"] .inv-switch input').click();
await page.locator('[data-source-id="ait.adx.events"][data-enabled="true"]').waitFor();
check('6h-reversible', true, 'switched back on');

// ---- 8. geometry, at both shipped viewports ------------------------------------------------
async function geometry() {
  return page.evaluate(() => {
    const box = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height) };
    };
    return {
      viewport: { w: window.innerWidth, h: window.innerHeight },
      documentWidth: document.documentElement.scrollWidth,
      tree: box('.inv-panel-tree'),
      detail: box('.inv-panel-detail'),
      firstRow: box('.inv-row'),
    };
  });
}

const desktop = await geometry();
report.desktop = desktop;
check('8d-desktop-no-overflow', desktop.documentWidth <= desktop.viewport.w + 1,
  `${desktop.documentWidth} vs ${desktop.viewport.w}`);
check('8e-desktop-tree-usable', desktop.tree.w >= 300 && desktop.tree.h >= 300, JSON.stringify(desktop.tree));
check('8f-desktop-detail-usable', desktop.detail.w >= 500, JSON.stringify(desktop.detail));

await page.setViewportSize(MOBILE);
await page.waitForTimeout(300);
await page.screenshot({ path: `${SHOTS}inventory-mobile.png`, fullPage: false });
const mobile = await geometry();
report.mobile = mobile;
check('8g-mobile-no-overflow', mobile.documentWidth <= mobile.viewport.w + 1,
  `${mobile.documentWidth} vs ${mobile.viewport.w}`);
check('8h-mobile-tree-usable', mobile.tree.h >= 180 && mobile.tree.w >= 340, JSON.stringify(mobile.tree));
check('8i-mobile-detail-usable', mobile.detail.h >= 200, JSON.stringify(mobile.detail));
await page.setViewportSize(DESKTOP);

// ---- 9. the investigation workspace survived the whole walk ---------------------------------
await page.getByRole('tab', { name: 'Investigation' }).click();
await page.getByRole('button', { name: 'Scan ADX window' }).first().waitFor({ state: 'visible' });
const investigation = await page.evaluate(() => ({
  scenarioOptions: document.querySelectorAll('select option').length,
  scanButton: Boolean(document.querySelector('.primary-button')),
  columns: document.querySelectorAll('.three-column > .panel-column').length,
}));
report.investigation = { beforeSwitch, investigation };
// The mid-walk reload cleared React state by design. What must hold is that the
// investigation workspace is intact and operable after the round trip.
check('9a-investigation-intact',
  investigation.scanButton && investigation.columns === 3 && investigation.scenarioOptions > 1,
  JSON.stringify(investigation));
await page.screenshot({ path: `${SHOTS}inventory-investigation-after.png` });

// switching away and back must not lose in-tab investigation state
await page.getByLabel('Test Scenarios').selectOption({ index: 2 });
const marked = await page.getByLabel('Scan start UTC').inputValue();
await page.getByRole('tab', { name: 'Data sources' }).click();
await page.locator('.inv-tree').waitFor();
await page.getByRole('tab', { name: 'Investigation' }).click();
const kept = await page.getByLabel('Scan start UTC').inputValue();
check('9b-state-survives-tab-switch', kept === marked && kept.length > 0, `${marked} -> ${kept}`);

// ---- 10. a stale selection narrows; it never switches sources back on -------------------
// The failure this covers: a stored selection naming one id the server no longer
// declares is refused wholesale, and "repair" by resetting to all switches every
// source the reader had switched off back on. Scope must only ever narrow.
async function openInventory(target, expand = useCases) {
  await target.getByRole('tab', { name: 'Data sources' }).click();
  await target.locator('.inv-tree [role="treeitem"]').first().waitFor({ timeout: 30000 });
  for (const label of expand) {
    await target.locator(`[data-kind="use_case"]:has-text("${label}") .inv-twisty`).click();
  }
  await target.waitForFunction(
    (count) => document.querySelectorAll('[data-kind="source"]').length === count,
    expand.length * 3, { timeout: 30000 });
}

expectingRejections = true;
await page.evaluate(() => {
  window.sessionStorage.setItem('cybereye.inventory.selection', JSON.stringify({
    mode: 'explicit', ids: ['perth.adx.events_unified', 'zzz.stale.source'],
  }));
});
await page.reload({ waitUntil: 'networkidle' });
await openInventory(page);
const afterStale = await page.evaluate(() => ({
  enabled: Object.fromEntries([...document.querySelectorAll('[data-kind="source"]')]
    .map((n) => [n.getAttribute('data-source-id'), n.getAttribute('data-enabled')])),
  stored: JSON.parse(window.sessionStorage.getItem('cybereye.inventory.selection') ?? '{}'),
  notice: document.querySelector('.inv-notice')?.textContent ?? '',
  counter: document.querySelector('.inv-selection-controls span')?.textContent ?? '',
}));
expectingRejections = false;
report.afterStale = afterStale;
const switchedOn = Object.entries(afterStale.enabled).filter(([, on]) => on === 'true');
check('10a-stale-does-not-widen', switchedOn.length === 1
  && switchedOn[0][0] === 'perth.adx.events_unified', JSON.stringify(afterStale.enabled));
check('10b-stale-id-dropped', afterStale.stored.mode === 'explicit'
  && !JSON.stringify(afterStale.stored.ids).includes('zzz.stale.source'),
  JSON.stringify(afterStale.stored));
check('10c-narrowing-is-explained', /nothing was switched back on/i.test(afterStale.notice),
  afterStale.notice);
check('10d-counter-agrees', /^1\/6 /.test(afterStale.counter), afterStale.counter);

// ---- 11. a toggle in one open branch must not drop the collapsed one ---------------------
// The tree is lazily expanded. Reconciling against the ids it happens to have
// loaded rewrites the selection down to the open branch, silently switching off
// every source in a collapsed one.
await page.evaluate(() => window.sessionStorage.removeItem('cybereye.inventory.selection'));
await page.reload({ waitUntil: 'networkidle' });
await openInventory(page, [useCases[0]]);
await page.locator('[data-source-id="perth.adx.events_unified"] .inv-switch input').click();
await page.locator('[data-source-id="perth.adx.events_unified"][data-enabled="false"]')
  .waitFor({ timeout: 30000 });
const lazy = await page.evaluate(() =>
  JSON.parse(window.sessionStorage.getItem('cybereye.inventory.selection') ?? '{}'));
report.lazy = lazy;
check('11a-collapsed-branch-survives-a-toggle',
  lazy.mode === 'explicit' && lazy.ids.length === 5
  && lazy.ids.filter((id) => id.startsWith('ait.')).length === 3, JSON.stringify(lazy));

// ---- 12. reaching the inventory from a cold load on a narrow screen ---------------------
// The failure this covers, observed on --0000005: the chat drawer was fixed to the
// viewport and painted over the workspace tab strip, so below 600px "Data sources"
// was there, was reported visible, and every click landed on the chat instead.
// A resize performed *after* the inventory is already open never sees it. Each width
// below is therefore a fresh context and a genuine click, never a forced one.
const NARROW = [390, 391, 480, 600, 901];
report.narrow = {};

for (const width of NARROW) {
  const context = await newContext();
  const narrow = await openApp(context, { width, height: 844 });

  const cold = await narrow.evaluate(() => {
    const tab = [...document.querySelectorAll('[role="tab"]')]
      .find((node) => node.textContent.trim() === 'Data sources');
    const rect = tab.getBoundingClientRect();
    const cx = Math.round(rect.x + rect.width / 2);
    const cy = Math.round(rect.y + rect.height / 2);
    const hit = document.elementFromPoint(cx, cy);
    const box = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const r = node.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    };
    return {
      tab: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
      hitPoint: { cx, cy },
      // What a finger actually lands on. `isVisible` says nothing about who is on top.
      hitIsTab: hit === tab || tab.contains(hit),
      hitWas: hit ? `${hit.tagName.toLowerCase()}.${hit.className}`.slice(0, 48) : null,
      documentWidth: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
      tabs: box('.header-tabs'),
      panels: { scanner: box('.scanner'), board: box('.board'), chat: box('.chat-panel') },
    };
  });

  const overlaps = (a, b) => a !== null && b !== null
    && a.x < b.x + b.w - 2 && b.x < a.x + a.w - 2
    && a.y < b.y + b.h - 2 && b.y < a.y + a.h - 2;
  const { scanner, board, chat } = cold.panels;
  cold.overlapping = [
    overlaps(scanner, chat) ? 'scanner/chat' : null,
    overlaps(board, chat) ? 'board/chat' : null,
    overlaps(scanner, board) ? 'scanner/board' : null,
  ].filter(Boolean);

  check(`12a-${width}-tab-hit-tests`, cold.hitIsTab,
    `centre ${cold.hitPoint.cx},${cold.hitPoint.cy} of tab ${JSON.stringify(cold.tab)} resolves to ${cold.hitWas}`);
  // Two bands, two different rules. Below 900 the columns stack and nothing may sit on
  // anything. Above it the chat is deliberately a drawer over the columns — which is fine,
  // and was fine before this change; what was not fine was the drawer reaching the tabs.
  if (width <= 900) {
    check(`12b-${width}-stacked-panels-do-not-overlap`, cold.overlapping.length === 0,
      cold.overlapping.join(', ') || JSON.stringify(cold.panels));
  } else {
    check(`12b-${width}-drawer-clears-the-chrome-and-the-first-column`,
      chat !== null && cold.tabs !== null
      && chat.y >= cold.tabs.y + cold.tabs.h && chat.x >= 380,
      `chat ${JSON.stringify(chat)} against tabs ${JSON.stringify(cold.tabs)}`);
  }
  check(`12c-${width}-cold-no-horizontal-overflow`, cold.documentWidth <= cold.viewport + 1,
    `${cold.documentWidth} vs ${cold.viewport}`);
  check(`12d-${width}-scan-control-reachable`,
    await narrow.getByRole('button', { name: 'Scan ADX window' }).first().isVisible(),
    'the investigation workspace is still operable at this width');

  let opened = 'clicked';
  try {
    await narrow.getByRole('tab', { name: 'Data sources' }).click({ timeout: 5000 });
    await narrow.locator('.inv-tree [role="treeitem"]').first().waitFor({ timeout: 30000 });
  } catch (error) {
    opened = `blocked: ${String(error.message).split('\n')[0].slice(0, 90)}`;
  }
  const after = await narrow.evaluate(() => ({
    selected: [...document.querySelectorAll('[role="tab"]')]
      .find((node) => node.textContent.trim() === 'Data sources').getAttribute('aria-selected'),
    rows: document.querySelectorAll('.inv-tree [role="treeitem"]').length,
    documentWidth: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
    tree: (() => { const r = document.querySelector('.inv-panel-tree')?.getBoundingClientRect();
      return r ? { w: Math.round(r.width), h: Math.round(r.height) } : null; })(),
  }));

  check(`12e-${width}-tab-opens-from-cold`, opened === 'clicked' && after.selected === 'true' && after.rows > 0,
    `${opened}, aria-selected=${after.selected}, ${after.rows} rows`);
  check(`12f-${width}-inventory-no-horizontal-overflow`, after.documentWidth <= after.viewport + 1,
    `${after.documentWidth} vs ${after.viewport}`);
  check(`12g-${width}-inventory-tree-usable`, (after.tree?.h ?? 0) >= 180 && (after.tree?.w ?? 0) >= 320,
    JSON.stringify(after.tree));

  if (width === 390) {
    await narrow.screenshot({ path: `${SHOTS}inventory-mobile-cold-sources.png` });
    await narrow.getByRole('tab', { name: 'Investigation' }).click();
    await narrow.screenshot({ path: `${SHOTS}inventory-mobile-cold-investigation.png` });
  }
  report.narrow[width] = { ...cold, ...after, opened };
  await context.close();
}

await contextA.close();

// ---- 13. the switch is operable from the keyboard, and no toggle tears the tree down ----
// Two failures observed on --0000005: the tree's own key handler caught Space and Enter
// bubbling from the focused checkbox and cancelled them, so a focused switch could not be
// operated at all; and every toggle rebuilt the tree from nothing, blanking it and dropping
// the focus. Real key presses only - a forced or scripted click proves neither.
const contextC = await newContext();
const keys = await openApp(contextC, DESKTOP);
await openInventory(keys);

const treeState = () => keys.evaluate(() => {
  const active = document.activeElement;
  const row = active?.closest?.('[role="treeitem"]') ?? null;
  return {
    counter: document.querySelector('.inv-selection-controls span')?.textContent ?? '',
    checked: document.querySelector('[data-source-id="perth.adx.events_unified"] .inv-switch input')?.checked,
    focus: active
      ? { tag: active.tagName.toLowerCase(), type: active.getAttribute('type'), role: active.getAttribute('role'),
          row: row?.getAttribute('data-source-id') ?? row?.getAttribute('data-node-id') ?? null }
      : null,
    rows: document.querySelectorAll('.inv-tree [role="treeitem"]').length,
  };
});

// Watch every mutation for the whole section: a 44ms blank is invisible to polling.
await keys.evaluate(() => {
  window.__minRows = document.querySelectorAll('.inv-tree [role="treeitem"]').length;
  new MutationObserver(() => {
    const now = document.querySelectorAll('.inv-tree [role="treeitem"]').length;
    if (now < window.__minRows) window.__minRows = now;
  }).observe(document.querySelector('.inv-shell'), { childList: true, subtree: true });
});

await keys.locator('[data-source-id="perth.adx.events_unified"]').focus();
let tabbed = 0;
while (tabbed < 6) {
  await keys.keyboard.press('Tab');
  tabbed += 1;
  if (await keys.evaluate(() => document.activeElement?.getAttribute('type')) === 'checkbox') break;
}
const onSwitch = await treeState();
check('13a-switch-is-reachable-by-tab', onSwitch.focus?.type === 'checkbox'
  && onSwitch.focus.row === 'perth.adx.events_unified', `${tabbed} tabs -> ${JSON.stringify(onSwitch.focus)}`);

const settle = async () => {
  await keys.waitForFunction(() => document.querySelectorAll('[data-kind="source"]').length === 6,
    null, { timeout: 30000 });
  await keys.waitForTimeout(250);
};

await keys.keyboard.press(' ');
await settle();
const afterSpace = await treeState();
check('13b-space-toggles-exactly-once', afterSpace.checked === false && afterSpace.counter.startsWith('5/6'),
  `${onSwitch.counter} -> ${afterSpace.counter}, checked=${afterSpace.checked}`);
check('13c-space-keeps-the-focus-on-the-switch', afterSpace.focus?.type === 'checkbox'
  && afterSpace.focus.row === 'perth.adx.events_unified', JSON.stringify(afterSpace.focus));

await keys.keyboard.press('Enter');
await settle();
const afterEnter = await treeState();
check('13d-enter-toggles-exactly-once', afterEnter.checked === true && afterEnter.counter.startsWith('6/6'),
  `${afterSpace.counter} -> ${afterEnter.counter}, checked=${afterEnter.checked}`);
check('13e-enter-keeps-the-focus-on-the-switch', afterEnter.focus?.type === 'checkbox',
  JSON.stringify(afterEnter.focus));

// t on the row is the other path, and it must land back on the row it operated.
await keys.locator('[data-source-id="ait.adx.events"]').focus();
await keys.keyboard.press('t');
await settle();
const afterRowToggle = await keys.evaluate(() => ({
  enabled: document.querySelector('[data-source-id="ait.adx.events"]')?.getAttribute('data-enabled'),
  focusRow: document.activeElement?.getAttribute('data-source-id'),
  focusRole: document.activeElement?.getAttribute('role'),
}));
check('13f-row-toggle-keeps-the-row-focused', afterRowToggle.enabled === 'false'
  && afterRowToggle.focusRow === 'ait.adx.events' && afterRowToggle.focusRole === 'treeitem',
  JSON.stringify(afterRowToggle));

await keys.keyboard.press('ArrowDown');
const afterArrow = await keys.evaluate(() => document.activeElement?.getAttribute('role'));
check('13g-arrows-still-work-after-a-toggle', afterArrow === 'treeitem', String(afterArrow));
await keys.locator('[data-source-id="ait.adx.events"]').focus();
await keys.keyboard.press('t');
await settle();

await keys.getByRole('button', { name: 'All off' }).click();
await settle();
const allOff = await treeState();
await keys.getByRole('button', { name: 'All on' }).click();
await settle();
const allOn = await treeState();
const minRows = await keys.evaluate(() => window.__minRows);
report.keyboardSwitch = { onSwitch, afterSpace, afterEnter, afterRowToggle, allOff, allOn, minRows };
check('13h-bulk-actions-flip-in-place', allOff.counter.startsWith('0/6') && allOn.counter.startsWith('6/6')
  && allOff.rows === onSwitch.rows, `${allOff.counter} -> ${allOn.counter}, ${allOff.rows} rows throughout`);
check('13i-no-toggle-ever-blanks-the-tree', minRows === onSwitch.rows,
  `fewest rows seen across every toggle: ${minRows} of ${onSwitch.rows}`);

// ---- 14. two use cases may name a slot alike; a reader must still know which is which ----
const aliased = await keys.evaluate(() => [...document.querySelectorAll('[data-source-id$="search.index"]')]
  .map((node) => ({
    sourceId: node.getAttribute('data-source-id'),
    shown: node.querySelector('.inv-row-label b')?.textContent ?? '',
    row: node.getAttribute('aria-label'),
    control: node.querySelector('.inv-switch input')?.getAttribute('aria-label'),
  })));
report.aliased = aliased;
check('14a-labels-are-still-the-declared-ones', aliased.every((s) => s.shown === 'Retrieval index'),
  aliased.map((s) => s.shown).join(' | '));
check('14b-row-names-are-unique', new Set(aliased.map((s) => s.row)).size === aliased.length
  && aliased.every((s) => /Perth Cybersec POC_0|AIT/.test(s.row)), aliased.map((s) => s.row).join(' | '));
check('14c-control-names-are-unique', new Set(aliased.map((s) => s.control)).size === aliased.length,
  aliased.map((s) => s.control).join(' | '));

report.attribution = {};
for (const sourceId of ['perth.search.index', 'ait.search.index', 'perth.adx.events_unified']) {
  await keys.locator(`[data-source-id="${sourceId}"] .inv-row-label`).click();
  await keys.locator('.inv-detail h2').waitFor();
  report.attribution[sourceId] = await keys.evaluate(() => ({
    region: document.querySelector('.inv-detail')?.getAttribute('aria-label'),
    breadcrumb: document.querySelector('.inv-detail .inv-breadcrumb')?.textContent ?? null,
    // The scope sentence is one persistent copy, not one per pane.
    scopeCopies: [...document.querySelectorAll('.inv-scope-note, .inv-detail p')]
      .filter((node) => /Selection scopes/.test(node.textContent)).length,
  }));
}
// A switched-off source still says whose it is, with no metadata read to tell it from.
await keys.locator('[data-source-id="ait.gremlin.aitgraph"] .inv-switch input').click();
await keys.locator('[data-source-id="ait.gremlin.aitgraph"][data-enabled="false"]').waitFor();
await keys.locator('[data-source-id="ait.gremlin.aitgraph"] .inv-row-label').click();
await keys.locator('.inv-notice[data-state="disabled"]').waitFor();
report.attribution.disabled = await keys.evaluate(() => ({
  region: document.querySelector('.inv-detail')?.getAttribute('aria-label'),
  breadcrumb: document.querySelector('.inv-detail .inv-breadcrumb')?.textContent ?? null,
  scopeCopies: [...document.querySelectorAll('.inv-scope-note, .inv-detail p')]
    .filter((node) => /Selection scopes/.test(node.textContent)).length,
}));
const panes = Object.values(report.attribution);
check('14d-every-pane-names-its-use-case',
  panes.every((pane) => /Use case: (Perth Cybersec POC_0|AIT)/.test(pane.breadcrumb ?? '')),
  panes.map((pane) => pane.breadcrumb).join(' | '));
check('14e-pane-region-names-are-attributable',
  report.attribution['perth.search.index'].region === 'Retrieval index, Perth Cybersec POC_0'
  && report.attribution['ait.search.index'].region === 'Retrieval index, AIT',
  panes.map((pane) => pane.region).join(' | '));
check('14f-scope-sentence-appears-once', panes.every((pane) => pane.scopeCopies === 1),
  panes.map((pane) => pane.scopeCopies).join(','));

const targets = await keys.evaluate(() => {
  const size = (selector) => { const r = document.querySelector(selector).getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height) }; };
  return { twisty: size('.inv-twisty'), switch: size('.inv-switch') };
});
report.targets = targets;
check('14g-touch-targets-are-at-least-24px',
  targets.twisty.w >= 24 && targets.twisty.h >= 24 && targets.switch.w >= 24 && targets.switch.h >= 24,
  JSON.stringify(targets));
await contextC.close();

// ---- 15. the shell states what it is showing, and what it is still waiting for ----------
const contextD = await newContext();
const shell = await contextD.newPage();
shell.on('console', (m) => { if (m.type() === 'error' && !noise(consoleText(m))) consoleErrors.push(consoleText(m)); });
await shell.setViewportSize(DESKTOP);
// Held open long enough to observe. The check is that the control says so rather than
// presenting an empty list of scenarios as if that were the answer.
await shell.route('**/api/cyber/scenarios', async (route) => {
  await new Promise((resolve) => setTimeout(resolve, 2000));
  // fallback, not continue: a page route that continues ends the chain, and the context-level
  // handler that carries this run's credential never runs. Against a deployed host that turns
  // a deliberate delay into a 401 and the select never settles.
  await route.fallback();
});
await shell.goto(BASE);
await shell.getByRole('button', { name: 'Scan ADX window' }).first().waitFor({ state: 'visible' });
const pending = await shell.evaluate(() => {
  const select = document.querySelector('.scanner-scenario select');
  return { text: select.options[0]?.textContent ?? '', options: select.options.length, disabled: select.disabled };
});
await shell.waitForFunction(
  () => document.querySelectorAll('.scanner-scenario select option').length > 1, null, { timeout: 30000 });
const settled = await shell.evaluate(() => {
  const select = document.querySelector('.scanner-scenario select');
  return { text: select.options[0]?.textContent ?? '', options: select.options.length, disabled: select.disabled };
});
const chip = await shell.evaluate(() => [...document.querySelectorAll('.health-chip')]
  .map((node) => node.textContent.trim()));
report.shell = { pending, settled, chip };
check('15a-scenarios-say-they-are-loading', /Loading scenarios/.test(pending.text) && pending.disabled === true,
  JSON.stringify(pending));
check('15b-scenarios-settle-to-a-choice', /Choose scenario/.test(settled.text) && settled.options > 1
  && settled.disabled === false, JSON.stringify(settled));
// The chip counts the Perth replay table; it does not follow the inventory selection.
check('15c-header-count-names-its-table', chip.some((text) => /Perth table/.test(text) && /15,520/.test(text)),
  chip.join(' | '));
await contextD.close();

report.consoleErrors = consoleErrors;
check('0-no-console-errors', consoleErrors.length === 0, consoleErrors.join(' | '));
await browser.close();

const failed = checks.filter((c) => !c.ok);
const summary = { base: BASE, passed: checks.length - failed.length, failed: failed.length, checks, report };
await writeFile(`${SHOTS}inventory-verification.json`, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
process.exit(failed.length === 0 ? 0 : 1);
