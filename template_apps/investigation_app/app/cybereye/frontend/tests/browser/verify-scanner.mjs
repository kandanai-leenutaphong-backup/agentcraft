// Investigation workspace: the deterministic scan an analyst actually runs, in a real browser.
//
//   node app/cybereye/frontend/verify-scanner.mjs                       # local dev server
//   CYBEREYE_URL=https://<host> node app/cybereye/frontend/verify-scanner.mjs
//   VERIFY_SELFTEST=1 CYBEREYE_URL=… node …/verify-scanner.mjs          # must exit 1
//
// Env: CYBEREYE_URL (default http://127.0.0.1:5173), ARTIFACT_DIR (default ./artifacts/
// beside this file), CYBEREYE_SCENARIO (default focal-privileged-session).
//
// Prints one JSON report, writes it beside the screenshots, and exits non-zero on any failed
// check, any caught exception, or any console/page error.
//
// What this proves that a render test cannot. Streaming: an in-page MutationObserver records
// the states the user is actually shown — the button passing through "Scanning…", the rule
// header counting up from 0 hit · 0 miss, and the per-rule status cells — rather than only
// the settled end state. Arithmetic: the score ladder's stated total is compared against the
// sum of the score cells above it, so a derivation that stops describing its own rows fails
// here. Geometry: the three shipped viewports are measured and the workspace tab strip is
// hit-tested at each, because a tab that is present but painted over is the defect a
// visibility assertion misses.
//
// It targets .rule-grid / .rgrid-record. The revision of this file before 2026-09-06 targeted
// .rule-run, a class no component has rendered since the rule board became a RecordGrid:
// docs/UNRESOLVED_GAPS/scanner-verifiers-target-a-removed-class.md.

import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { signContext } from '../support/verify-auth.mjs';

const BASE = process.env.CYBEREYE_URL ?? 'http://127.0.0.1:5173';
const SCENARIO = process.env.CYBEREYE_SCENARIO ?? 'focal-privileged-session';
const SELFTEST = process.env.VERIFY_SELFTEST === '1';
const READ_ONLY = process.env.CYBEREYE_READ_ONLY_ACCEPTANCE === '1';
const DATA_ONLY = process.env.CYBEREYE_DATA_WORKFLOWS === '1';
const GUARDED = READ_ONLY || DATA_ONLY;
if (DATA_ONLY && !/^http:\/\/(127\.0\.0\.1|localhost):[0-9]+\/?$/.test(BASE)) {
  throw new Error('data workflow verification requires a loopback origin');
}
const rawDir = process.env.ARTIFACT_DIR ?? new URL('../../artifacts/', import.meta.url).pathname;
const SHOTS = rawDir.endsWith('/') ? rawDir : `${rawDir}/`;
// A negative run keeps its own namespace so it can never overwrite the passing run's evidence.
const PREFIX = SELFTEST ? 'selftest-scanner-verify' : 'scanner-verify';

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 900, height: 800 },
  { name: 'mobile', width: 390, height: 844 },
];

const checks = [];
const check = (id, ok, detail) => {
  checks.push({ id, ok: Boolean(ok), detail: String(detail) });
  return Boolean(ok);
};

const consoleErrors = [];
const pageErrors = [];
const blockedRequests = [];
const evidenceResponses = [];
// A missing favicon is chrome, not the application under test.
const noise = (text) => /favicon\.ico/.test(text);
// A console error that names no resource cannot be acted on, so the failing URL is appended.
const consoleText = (m) => `${m.text()} ${m.location()?.url ?? ''}`.trim();

const report = {
  base: BASE, scenario: SCENARIO, selftest: SELFTEST,
  readOnlyAcceptance: READ_ONLY, dataWorkflows: DATA_ONLY, blockedRequests,
  startedAt: new Date().toISOString(), observed: {}, screenshots: [],
};
let failure = null;

const browser = await chromium.launch({ headless: true });
try {
  await mkdir(SHOTS, { recursive: true });
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1440, height: 900 } });
  await signContext(context, BASE);
  if (GUARDED) {
    await context.route('**/api/**', async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (!path.startsWith('/api/')) return route.continue();
      const safeGet = /^\/api\/(?:whoami|cyber\/(?:rules|scenarios|agents|tools|library-identity|detector\/configuration|inventory\/(?:tree|selection)|evidence\/[A-Za-z0-9_-]+))$/;
      const allowed = request.method() === 'GET' && safeGet.test(path)
        || request.method() === 'POST' && ['/api/cyber/scan/stream', '/api/sessions'].includes(path);
      if (allowed) return route.continue();
      blockedRequests.push({ method: request.method(), path });
      await route.abort('blockedbyclient');
    });
  }
  if (READ_ONLY) {
    const identity = await context.request.get(`${BASE}/api/cyber/library-identity`);
    report.observed.identityBefore = await identity.json();
    if (identity.status() !== 200 || report.observed.identityBefore.editable !== false
      || report.observed.identityBefore.wheel_install !== true || report.observed.identityBefore.transport !== 'native') {
      throw new Error('read-only acceptance requires the native installed candidate');
    }
  }
  const page = await context.newPage();
  page.on('console', (m) => {
    const expectedAbort = GUARDED && /ERR_BLOCKED_BY_CLIENT/.test(m.text())
      && blockedRequests.some(({ path }) => m.location()?.url?.includes(path));
    if (m.type() === 'error' && !expectedAbort && !noise(consoleText(m))) consoleErrors.push(consoleText(m));
  });
  page.on('pageerror', (e) => { if (!noise(e.message)) pageErrors.push(e.message); });
  page.on('response', (response) => {
    if (new URL(response.url()).pathname.startsWith('/api/cyber/evidence/')) {
      evidenceResponses.push(response.json().then((body) => ({ status: response.status(),
        rowCount: body.row_count, truncated: body.truncated, situationId: body.situation_id })));
    }
  });

  let scanPayload = null;
  page.on('request', (request) => {
    if (request.url().includes('/api/cyber/scan/stream')) scanPayload = request.postDataJSON();
  });

  await page.goto(BASE, { waitUntil: 'networkidle' });

  // ---- 1. the scan controls are the first thing an analyst meets --------------------------
  const scanButton = page.locator('.scanner-scan-button');
  await scanButton.waitFor({ state: 'visible' });
  const scenarioSelect = page.getByLabel('Test Scenarios');
  await page.waitForFunction(
    () => document.querySelectorAll('.scanner-scenario option').length > 1, null, { timeout: 60000 });
  const scenarioOptions = await page.locator('.scanner-scenario option').evaluateAll(
    (nodes) => nodes.map((n) => ({ value: n.value, label: n.textContent })));
  report.observed.scenarioOptions = scenarioOptions;
  check('1a-scenarios-loaded', scenarioOptions.length > 1,
    `${scenarioOptions.length} options: ${scenarioOptions.map((o) => o.value).filter(Boolean).join(',')}`);
  check('1b-settled-menu-is-not-a-loading-menu',
    scenarioOptions[0].value === '' && !/Loading/.test(scenarioOptions[0].label ?? ''),
    `first option ${JSON.stringify(scenarioOptions[0])}`);
  check('1c-requested-scenario-present', scenarioOptions.some((o) => o.value === SCENARIO),
    `looking for ${SCENARIO}`);

  // ---- 2. choosing a scenario fills the window it declares --------------------------------
  await scenarioSelect.selectOption(SCENARIO);
  const selected = {
    scenario: await scenarioSelect.inputValue(),
    start: await page.getByLabel('Scan start UTC').inputValue(),
    end: await page.getByLabel('Scan end UTC').inputValue(),
  };
  report.observed.selected = selected;
  const declared = scenarioOptions.find((o) => o.value === SCENARIO);
  check('2a-scenario-applied', selected.scenario === SCENARIO, JSON.stringify(selected));
  check('2b-window-populated', /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(selected.start)
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(selected.end)
    && new Date(`${selected.end}Z`) > new Date(`${selected.start}Z`),
    `${selected.start} → ${selected.end} for ${declared?.label}`);

  // ---- 3. the states a user is shown while the scan streams -------------------------------
  // Installed before the click: the button text, the rule header tally and the per-rule status
  // cells are sampled on every mutation, so the progression is observed rather than inferred
  // backwards from the settled result.
  await page.evaluate(() => {
    const state = { button: [], header: [], rowStatuses: {}, rowCounts: [] };
    const push = (list, value) => { if (value && list[list.length - 1] !== value) list.push(value); };
    const sample = () => {
      push(state.button, document.querySelector('.scanner-scan-button')?.textContent?.trim());
      push(state.header, document.querySelector('.rule-board-title span')?.textContent?.trim());
      const cells = document.querySelectorAll('.rule-grid .rgrid-status');
      for (const cell of cells) state.rowStatuses[cell.textContent.trim()] = true;
      if (cells.length) push(state.rowCounts, String(cells.length));
    };
    window.__scanStates = state;
    sample();
    new MutationObserver(sample).observe(document.body, {
      subtree: true, childList: true, characterData: true, attributes: true,
    });
  });

  await scanButton.click();
  // Expand the rule board while the queries are still in flight: the rows only exist once it
  // is open, and their running state is the thing being observed.
  const ruleToggle = page.locator('.rule-board-title');
  await ruleToggle.waitFor({ state: 'visible', timeout: 20000 });
  check('3a-rule-board-collapsed-by-default',
    (await ruleToggle.getAttribute('aria-expanded')) === 'false',
    `aria-expanded=${await ruleToggle.getAttribute('aria-expanded')}`);
  await ruleToggle.click();
  check('3b-rule-board-expands', (await ruleToggle.getAttribute('aria-expanded')) === 'true',
    `aria-expanded=${await ruleToggle.getAttribute('aria-expanded')}`);
  await page.locator('.rule-grid .rgrid-record').first().waitFor({ timeout: 30000 });
  await page.getByRole('region', { name: 'Historical replay rule execution' }).waitFor();
  const ruleWindow = await page.locator('.rule-window').innerText();
  check('3c-rule-window-echoes-the-request',
    ruleWindow.includes(`${selected.start}:00Z`) && ruleWindow.includes(`${selected.end}:00Z`),
    ruleWindow);

  // ---- 4. the stream reaches a terminal state, and the user can see that it did -----------
  // The losing branch is settled rather than left to reject after the race resolves; an
  // unhandled rejection terminates the process and would read as a verifier crash.
  const terminalAlert = page.locator(GUARDED ? '.scanner .error-box[role="alert"]' : '.error-box[role="alert"]').first();
  await Promise.race([
    page.locator('.scanned-window').waitFor({ timeout: 180000 }).catch(() => {}),
    terminalAlert.waitFor({ timeout: 180000 }).catch(() => {}),
  ]);
  const alertText = GUARDED
    ? (await terminalAlert.count() ? await terminalAlert.textContent() : null)
    : await terminalAlert.textContent().catch(() => null);
  check('4a-no-terminal-error', alertText === null, alertText ?? 'no error alert rendered');
  // Terminal is the settled control plus the visible result, not the button alone.
  await page.waitForFunction(
    () => document.querySelector('.scanner-scan-button')?.textContent?.includes('Scan ADX window')
      && !document.querySelector('.scan-live'),
    null, { timeout: 180000 });
  const scannedWindow = await page.locator('.scanned-window').innerText();
  // Several labels are uppercased by CSS, so innerText returns SCANNED UTC INTERVAL, OBSERVED,
  // CONFIDENCE and FINAL. The wording is unchanged; only the rendered casing is, so the label
  // assertions below are case-insensitive and the value assertions are not.
  check('4b-scanned-interval-shown', /scanned utc interval/i.test(scannedWindow),
    scannedWindow.replace(/\n/g, ' | '));
  check('4c-scanned-interval-is-the-requested-one',
    scannedWindow.includes(`${selected.start}:00Z`) && scannedWindow.includes(`${selected.end}:00Z`),
    scannedWindow.replace(/\n/g, ' | '));

  report.observed.scanPayload = scanPayload;
  check('4d-payload-matches-the-controls',
    scanPayload?.start === `${selected.start}:00Z` && scanPayload?.end === `${selected.end}:00Z`,
    JSON.stringify(scanPayload));

  const states = await page.evaluate(() => window.__scanStates);
  report.observed.streamStates = states;
  check('4e-live-control-state-shown', states.button.includes('Scanning…')
    && states.button[states.button.length - 1] === 'Scan ADX window',
    states.button.join(' → '));
  check('4f-rule-tally-counts-up', states.header.length >= 2 && states.header[0] === '0 hit · 0 miss',
    states.header.join(' → '));
  const seenStatuses = Object.keys(states.rowStatuses);
  check('4g-non-terminal-rule-state-rendered',
    seenStatuses.some((s) => s === 'pending' || s === 'running'), seenStatuses.join(','));
  check('4h-terminal-rule-state-rendered',
    seenStatuses.some((s) => s === 'hit' || s === 'miss'), seenStatuses.join(','));

  if (SELFTEST) {
    // Same checker, one injected contract break: the class the rule rows carry is renamed —
    // exactly the drift that made the previous revision of this file a false green. Nothing
    // server-side is touched; the mutation lives in this page only.
    await page.evaluate(() => {
      for (const node of document.querySelectorAll('.rule-grid .rgrid-record')) {
        node.classList.replace('rgrid-record', 'rgrid-record-legacy');
      }
    });
  }

  // ---- 5. every rule row is a readable record of one deterministic query ------------------
  const rules = await page.locator('.rule-grid .rgrid-record').evaluateAll((nodes) => nodes.map((n) => ({
    label: n.querySelector('.rgrid-name b')?.textContent ?? null,
    idVersion: n.querySelector('.rgrid-name b')?.getAttribute('title') ?? null,
    status: n.querySelector('.rgrid-status')?.textContent ?? null,
    groups: n.querySelector('.rgrid-stack.right b')?.textContent ?? null,
    elapsed: n.querySelector('.rgrid-stack.right small')?.textContent ?? null,
  })));
  report.observed.rules = rules;
  const hits = rules.filter((r) => r.status === 'hit');
  const misses = rules.filter((r) => r.status === 'miss');
  check('5a-rule-rows-rendered', rules.length > 0, `${rules.length} rows`);
  check('5b-every-rule-terminal', rules.length > 0 && hits.length + misses.length === rules.length,
    `${hits.length} hit + ${misses.length} miss of ${rules.length}`);
  check('5c-at-least-one-rule-qualified', hits.length > 0, `${hits.length} hit`);
  const headerTally = await ruleToggle.locator('span').innerText();
  check('5d-header-tally-matches-rows',
    headerTally === `${hits.length} hit · ${misses.length} miss`,
    `header "${headerTally}" vs rows ${hits.length} hit / ${misses.length} miss`);
  check('5e-rules-identified-and-versioned',
    rules.length > 0 && rules.every((r) => r.label && /·\s*v\d/.test(r.idVersion ?? '')),
    JSON.stringify(rules.map((r) => r.idVersion)));
  check('5f-rules-report-groups-and-time',
    rules.length > 0 && rules.every((r) => r.groups !== null && /ms$/.test(r.elapsed ?? '')),
    JSON.stringify(rules.map((r) => `${r.groups} / ${r.elapsed}`)));

  // ---- 6. a rule explains itself from its own query, one explanation at a time ------------
  const hitRow = page.locator('.rule-grid .rgrid-record.hit').first();
  await hitRow.locator('.rgrid-row').click();
  await hitRow.locator('.rule-explanation .derived').waitFor({ timeout: 20000 });
  const explanation = await page.evaluate(() => {
    const root = document.querySelector('.rule-grid .rgrid-record.open .rule-explanation');
    if (!root) return null;
    return {
      headline: root.querySelector('.derived-headline')?.innerText.replace(/\n/g, ' ') ?? '',
      steps: [...root.querySelectorAll('.derived-steps > li')].map((li) => li.querySelector('b')?.textContent ?? ''),
      lines: [...root.querySelectorAll('.derived-steps > li li')].map((li) => li.textContent),
      rawTermsSummary: root.querySelector('.derived-raw summary')?.textContent ?? '',
    };
  });
  report.observed.ruleExplanation = explanation;
  check('6a-rule-explanation-opens',
    (await hitRow.locator('.rgrid-row').getAttribute('aria-expanded')) === 'true',
    `aria-expanded=${await hitRow.locator('.rgrid-row').getAttribute('aria-expanded')}`);
  check('6b-explanation-is-derived-not-authored',
    (explanation?.steps.length ?? 0) >= 3 && (explanation?.lines.length ?? 0) > 0,
    `${explanation?.steps.length} steps: ${explanation?.steps.join(' / ')}`);
  check('6c-explanation-reports-this-window',
    Boolean(explanation?.steps.some((s) => /In this window it found/.test(s))),
    explanation?.steps.join(' / ') ?? 'none');
  check('6d-explanation-carries-threshold-and-score',
    /threshold/.test(explanation?.headline ?? '') && /score \+\d/.test(explanation?.headline ?? ''),
    explanation?.headline ?? '');
  check('6e-exact-query-terms-offered',
    /Show the exact query terms/.test(explanation?.rawTermsSummary ?? ''),
    explanation?.rawTermsSummary ?? '');

  if (rules.length > 1) {
    const secondRow = page.locator('.rule-grid .rgrid-record').nth(1);
    await secondRow.locator('.rgrid-row').click();
    await page.waitForFunction(
      () => document.querySelectorAll('.rule-grid .rgrid-record.open').length === 1,
      null, { timeout: 10000 });
    const openIndex = await page.evaluate(() =>
      [...document.querySelectorAll('.rule-grid .rgrid-record')].findIndex((n) => n.classList.contains('open')));
    check('6f-one-explanation-at-a-time', openIndex === 1, `the only open row is index ${openIndex}`);
    await secondRow.locator('.rgrid-row').click();
  } else {
    await hitRow.locator('.rgrid-row').click();
  }

  // ---- 7. situations, their severity, and the arithmetic behind them ----------------------
  const summaryStrip = await page.locator('.summary-strip').innerText();
  const situationsClaimed = Number(summaryStrip.match(/(\d+)\s*situations?/)?.[1] ?? -1);
  const criticalClaimed = Number(summaryStrip.match(/(\d+)\s*critical/)?.[1] ?? -1);
  const situationCount = await page.locator('.situation').count();
  const criticalCount = await page.locator('.situation .severity.critical').count();
  report.observed.summaryStrip = summaryStrip.replace(/\n/g, ' | ');
  check('7a-situations-rendered', situationCount > 0, `${situationCount} situations`);
  check('7b-summary-matches-rendered-situations', situationsClaimed === situationCount,
    `strip says ${situationsClaimed}, rendered ${situationCount}`);
  check('7c-summary-matches-rendered-critical', criticalClaimed === criticalCount,
    `strip says ${criticalClaimed}, rendered ${criticalCount}`);

  const situation = criticalCount > 0
    ? page.locator('.situation').filter({ has: page.locator('.severity.critical') }).first()
    : page.locator('.situation').first();
  await situation.locator('.situation-body').waitFor({ timeout: 20000 });
  const identity = await situation.locator('.situation-identity').innerText();
  const situationMeta = await situation.locator('.situation-meta').innerText();
  check('7d-situation-identified', identity.trim().split('\n').filter(Boolean).length === 2,
    identity.replace(/\n/g, ' / '));
  check('7e-situation-meta-states-rules-and-confidence',
    /rules qualified/i.test(situationMeta) && /confidence/i.test(situationMeta) && /final/i.test(situationMeta),
    situationMeta.replace(/\n/g, ' | '));

  const factorRows = situation.locator('.situation-body .rgrid-record');
  const factorCount = await factorRows.count();
  const scores = await situation.locator('.situation-body .rgrid-score').evaluateAll(
    (nodes) => nodes.map((n) => Number(n.textContent.replace('+', ''))));
  report.observed.factorScores = scores;
  check('7f-factor-rows-rendered',
    factorCount > 0 && scores.length === factorCount && scores.every((s) => Number.isFinite(s)),
    `${factorCount} rows, scores ${scores.join('+')}`);

  await factorRows.first().locator('.rgrid-row').click();
  await situation.locator('.factor-body').first().waitFor({ timeout: 20000 });
  const factor = await situation.locator('.factor-body').first().evaluate((node) => ({
    ladder: node.querySelector('.score-ladder')?.innerText.replace(/\n/g, ' ') ?? '',
    observed: node.querySelector('.observed-fact')?.innerText.replace(/\n/g, ' ') ?? '',
    facts: [...node.querySelectorAll('.fact-grid > div')].map((d) => d.innerText.replace(/\n/g, '=')),
    evidence: node.querySelector('.factor-evidence')?.innerText.replace(/\n/g, ' ') ?? '',
    reasoningSummary: node.querySelector('.factor-reasoning summary')?.textContent ?? '',
  }));
  report.observed.factor = factor;

  const ladderTotal = Number(factor.ladder.match(/summed to\s*(\d+)/)?.[1] ?? NaN);
  const scoreSum = scores.reduce((total, value) => total + value, 0);
  check('7g-score-ladder-sums-the-rows-above-it', ladderTotal === scoreSum,
    `ladder total ${ladderTotal} vs summed score cells ${scoreSum} (${scores.join('+')})`);
  check('7h-ladder-states-the-severity-step', /→\s*(critical|high|medium|low)/.test(factor.ladder),
    factor.ladder);
  check('7i-observed-fact-present', /^observed\s+\S/i.test(factor.observed), factor.observed);
  check('7j-factor-facts-labelled',
    factor.facts.some((f) => /^confidence=/i.test(f)) && factor.facts.some((f) => /^sampled ids=/i.test(f)),
    factor.facts.join(' | '));
  check('7k-evidence-run-completed', /evidence\s*complete/i.test(factor.evidence), factor.evidence);
  check('7l-factor-derivation-offered',
    /read from its own query/.test(factor.reasoningSummary), factor.reasoningSummary);

  await page.screenshot({ path: `${SHOTS}${PREFIX}-desktop-1440x900.png`, fullPage: true });
  report.screenshots.push(`${PREFIX}-desktop-1440x900.png`);

  await page.locator('.board-tabs').getByRole('button', { name: 'evidence', exact: true }).click();
  const evidenceTable = page.locator('.board-content').getByRole('table').first();
  await evidenceTable.waitFor({ state: 'visible', timeout: 30000 });
  const evidenceRows = await evidenceTable.locator('tbody tr').count();
  report.observed.evidenceReadbacks = await Promise.all(evidenceResponses);
  check('7m-evidence-control-renders-real-readback', evidenceRows > 0
    && report.observed.evidenceReadbacks.some((value) => value.status === 200 && value.rowCount >= evidenceRows),
    `${evidenceRows} rendered rows; ${report.observed.evidenceReadbacks.length} API readbacks`);
  await page.screenshot({ path: `${SHOTS}${PREFIX}-evidence-1440x900.png`, fullPage: true });
  report.screenshots.push(`${PREFIX}-evidence-1440x900.png`);
  await page.locator('.board-tabs').getByRole('button', { name: 'situation', exact: true }).click();

  // ---- 8. geometry at every shipped viewport, with the tab strip hit-tested ---------------
  // Reading the drilldown scrolled the panels; geometry is measured from the top, which is
  // what a user arriving at each width actually sees.
  await page.evaluate(() => {
    for (const node of document.querySelectorAll('.panel-column, .three-column, .board-content')) node.scrollTop = 0;
  });
  report.observed.geometry = {};
  for (const { name, width, height } of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await page.waitForFunction((expected) => document.documentElement.clientWidth === expected,
      width, { timeout: 10000 });
    const geometry = await page.evaluate(() => {
      const box = (selector) => {
        const rect = document.querySelector(selector)?.getBoundingClientRect();
        return rect && {
          x: Math.round(rect.x), y: Math.round(rect.y),
          w: Math.round(rect.width), h: Math.round(rect.height),
        };
      };
      const tab = document.querySelector('.header-tabs #tab-explorer[role="tab"]');
      const rect = tab?.getBoundingClientRect();
      const hit = rect ? document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2) : null;
      return {
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        columns: getComputedStyle(document.querySelector('.three-column')).gridTemplateColumns,
        topbar: box('.topbar'), scanner: box('.scanner'), board: box('.board'), chat: box('.chat-panel'),
        controls: box('.scanner-controls'), tabs: box('.header-tabs'),
        tabHit: hit ? `${hit.tagName.toLowerCase()}.${hit.className}`.slice(0, 80) : null,
        tabReachable: Boolean(tab && hit && (hit === tab || tab.contains(hit))),
      };
    });
    report.observed.geometry[`${width}x${height}`] = geometry;
    check(`8a-${name}-no-horizontal-overflow`, geometry.overflow === 0,
      `scrollWidth - clientWidth = ${geometry.overflow}`);
    check(`8b-${name}-panels-have-area`,
      geometry.scanner.w > 0 && geometry.scanner.h > 0 && geometry.board.w > 0 && geometry.board.h > 0,
      `scanner ${geometry.scanner.w}x${geometry.scanner.h}, board ${geometry.board.w}x${geometry.board.h}`);
    check(`8c-${name}-scan-controls-on-screen`,
      geometry.controls.y >= 0 && geometry.controls.w > 0, JSON.stringify(geometry.controls));
    check(`8d-${name}-workspace-tab-hit-testable`, geometry.tabReachable,
      `the centre of the catalogue tab returns ${geometry.tabHit}`);
    const stacked = geometry.columns.trim().split(/\s+/).length === 1;
    check(`8e-${name}-layout-matches-width`, width <= 900 ? stacked : !stacked,
      `grid-template-columns: ${geometry.columns}`);
    await page.screenshot({ path: `${SHOTS}${PREFIX}-${name}-${width}x${height}.png`, fullPage: true });
    report.screenshots.push(`${PREFIX}-${name}-${width}x${height}.png`);
    if (width === 390) {
      const evidenceControl = page.locator('.board-tabs').getByRole('button', { name: 'evidence', exact: true });
      await evidenceControl.click();
      await evidenceTable.waitFor({ state: 'visible' });
      const control = await evidenceControl.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
          hit: hit === node || node.contains(hit) };
      });
      check('8f-mobile-evidence-control-hit-testable', control.hit && control.width > 0 && control.height > 0,
        JSON.stringify(control));
      await page.keyboard.press('Tab');
      await page.keyboard.press('Shift+Tab');
      check('8g-mobile-evidence-keyboard-reachable',
        await evidenceControl.evaluate((node) => document.activeElement === node), 'Tab and Shift+Tab return to evidence');
      await page.screenshot({ path: `${SHOTS}${PREFIX}-evidence-${width}x${height}.png`, fullPage: true });
      report.screenshots.push(`${PREFIX}-evidence-${width}x${height}.png`);
    }
  }

  check('9a-no-console-errors', consoleErrors.length === 0, consoleErrors.join(' | ') || 'none');
  check('9b-no-page-errors', pageErrors.length === 0, pageErrors.join(' | ') || 'none');
  if (READ_ONLY) {
    const identity = await context.request.get(`${BASE}/api/cyber/library-identity`);
    report.observed.identityAfter = await identity.json();
    check('9c-candidate-identity-retained', identity.status() === 200
      && report.observed.identityBefore.source_sha256 === report.observed.identityAfter.source_sha256
      && report.observed.identityAfter.transport === 'native', report.observed.identityAfter.source_sha256);
    check('9d-attempt-accounting-known', report.observed.identityAfter.query_metrics?.unknown_attempt_queries === 0,
      JSON.stringify(report.observed.identityAfter.query_metrics));
  }
  await context.close();
} catch (error) {
  failure = String(error?.stack ?? error).slice(0, 2000);
} finally {
  await browser.close();
  const failed = checks.filter((c) => !c.ok);
  report.finishedAt = new Date().toISOString();
  report.checks = checks;
  report.summary = { total: checks.length, failed: failed.length };
  report.failure = failure;
  report.consoleErrors = consoleErrors;
  report.pageErrors = pageErrors;
  const name = SELFTEST ? 'scanner-verification.selftest.json' : 'scanner-verification.json';
  await mkdir(SHOTS, { recursive: true }).catch(() => {});
  await writeFile(`${SHOTS}${name}`, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify({
    base: BASE, selftest: SELFTEST, artifact: `${SHOTS}${name}`,
    total: checks.length, failed: failed.length,
    failures: failed, failure, consoleErrors, pageErrors,
    checks: checks.map((c) => `${c.ok ? 'ok  ' : 'FAIL'} ${c.id} — ${c.detail}`),
  }, null, 2));
  process.exitCode = failure || failed.length || consoleErrors.length || pageErrors.length ? 1 : 0;
}
