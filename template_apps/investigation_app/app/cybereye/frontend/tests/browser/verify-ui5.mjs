// Investigation workspace acceptance: the explanations, tool renders and controls an analyst
// reads after a scan, in a real browser.
//
//   node app/cybereye/frontend/verify-ui5.mjs                        # local dev server
//   CYBEREYE_URL=https://<host> node app/cybereye/frontend/verify-ui5.mjs
//   VERIFY_SELFTEST=1 CYBEREYE_URL=… node …/verify-ui5.mjs           # must exit 1
//
// Env: CYBEREYE_URL (default http://127.0.0.1:5173), ARTIFACT_DIR (default ./artifacts/
// beside this file), CYBEREYE_SCENARIO (default focal-privileged-session).
//
// Prints one JSON report, writes it beside the screenshots, and exits non-zero on any failed
// check, any caught exception, or any console/page error. The previous revision of this file
// collected the same material but caught every exception and exited 0, so a timeout on a
// removed class reported as a pass; it also hovered .rule-run, a class no component renders.
// See docs/UNRESOLVED_GAPS/scanner-verifiers-target-a-removed-class.md.
//
// Agent tool cards are matched by the tool that produced them, never by ordinal position, so a
// reordered or extra card cannot turn this green by accident. Every wait is on a user-visible
// terminal condition — a settled control, a completed tool state, a rendered envelope.

import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { signContext } from '../support/verify-auth.mjs';

const BASE = process.env.CYBEREYE_URL ?? 'http://127.0.0.1:5173';
const SCENARIO = process.env.CYBEREYE_SCENARIO ?? 'focal-privileged-session';
const SELFTEST = process.env.VERIFY_SELFTEST === '1';
const rawDir = process.env.ARTIFACT_DIR ?? new URL('../../artifacts/', import.meta.url).pathname;
const SHOTS = rawDir.endsWith('/') ? rawDir : `${rawDir}/`;
// A negative run keeps its own namespace so it can never overwrite the passing run's evidence.
const PREFIX = SELFTEST ? 'selftest-ui5-verify' : 'ui5-verify';

const AGENT_TURN_MS = 240000;
const VIEWPORTS = [[1440, 900], [900, 800], [390, 844]];

const checks = [];
const check = (id, ok, detail) => {
  checks.push({ id, ok: Boolean(ok), detail: String(detail) });
  return Boolean(ok);
};

const consoleErrors = [];
const pageErrors = [];
const noise = (text) => /favicon\.ico/.test(text);
// A console error that names no resource cannot be acted on, so the failing URL is appended.
const consoleText = (m) => `${m.text()} ${m.location()?.url ?? ''}`.trim();

const report = {
  base: BASE, scenario: SCENARIO, selftest: SELFTEST,
  startedAt: new Date().toISOString(), captured: {}, overflow: {}, screenshots: [],
};
let failure = null;

const browser = await chromium.launch({ headless: true });
try {
  await mkdir(SHOTS, { recursive: true });
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1440, height: 900 } });
  await signContext(context, BASE);
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error' && !noise(consoleText(m))) consoleErrors.push(consoleText(m)); });
  page.on('pageerror', (e) => { if (!noise(e.message)) pageErrors.push(e.message); });

  const shot = async (name) => {
    await page.screenshot({ path: `${SHOTS}${PREFIX}-${name}.png`, fullPage: true });
    report.screenshots.push(`${PREFIX}-${name}.png`);
  };
  // Tab labels are uppercased by CSS, so innerText is matched case-insensitively; the
  // fullscreen control shares the strip and carries no text.
  const boardTab = (name) => page.locator('.board-tabs button:not(.fullscreen-toggle)')
    .filter({ hasText: new RegExp(`^${name}$`, 'i') }).first();
  const overflow = () => page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);

  await page.goto(BASE, { waitUntil: 'networkidle' });

  // ---- 1. the three columns carry no repeated headings, and start level -------------------
  report.captured.columnTitleCount = await page.locator('.column-title').count();
  check('1a-column-headers-removed', report.captured.columnTitleCount === 0,
    `${report.captured.columnTitleCount} .column-title elements`);
  report.captured.sectionAriaLabels = await page.locator('main section[aria-label]')
    .evaluateAll((nodes) => nodes.map((n) => n.getAttribute('aria-label')));
  check('1b-columns-named-for-assistive-tech',
    report.captured.sectionAriaLabels.length === 3
      && report.captured.sectionAriaLabels.every((label) => label && label.length > 3),
    report.captured.sectionAriaLabels.join(' | '));
  report.captured.columnTops = await page.evaluate(() => {
    const top = (selector) => {
      const rect = document.querySelector(selector)?.getBoundingClientRect();
      return rect ? Math.round(rect.top) : null;
    };
    return {
      scanner: top('.scanner'), board: top('.board'), chat: top('.chat-panel'),
      tabsBottom: Math.round(document.querySelector('.header-tabs').getBoundingClientRect().bottom),
    };
  });
  const tops = report.captured.columnTops;
  check('1c-columns-start-level', tops.scanner === tops.board && tops.board === tops.chat,
    JSON.stringify(tops));
  check('1d-workspace-tabs-sit-above-the-columns', tops.tabsBottom <= tops.scanner,
    `tabs bottom ${tops.tabsBottom}, columns top ${tops.scanner}`);

  // ---- 2. run the scan everything below reads ---------------------------------------------
  await page.locator('.scanner-scan-button').waitFor({ state: 'visible' });
  await page.waitForFunction(
    () => document.querySelectorAll('.scanner-scenario option').length > 1, null, { timeout: 60000 });
  await page.getByLabel('Test Scenarios').selectOption(SCENARIO);
  await page.locator('.scanner-scan-button').click();
  await Promise.race([
    page.locator('.scanned-window').waitFor({ timeout: 180000 }).catch(() => {}),
    page.locator('.error-box[role="alert"]').first().waitFor({ timeout: 180000 }).catch(() => {}),
  ]);
  await page.waitForFunction(
    () => document.querySelector('.scanner-scan-button')?.textContent?.includes('Scan ADX window')
      && !document.querySelector('.scan-live'),
    null, { timeout: 180000 });
  const scanAlert = await page.locator('.error-box[role="alert"]').first().textContent().catch(() => null);
  check('2a-scan-completed-without-error', scanAlert === null, scanAlert ?? 'no error alert rendered');
  const summaryStrip = await page.locator('.summary-strip').innerText();
  report.captured.summaryStrip = summaryStrip.replace(/\n/g, ' | ');
  check('2b-scan-summary-rendered', /\d+\s+situations/i.test(summaryStrip)
    && /\d+\s+critical/i.test(summaryStrip),
    report.captured.summaryStrip);

  // ---- 3. rule execution: collapsed by default, expanded on request, explained on click ----
  const ruleToggle = page.locator('.rule-board-title');
  report.captured.ruleBoardCollapsedByDefault = await ruleToggle.getAttribute('aria-expanded');
  report.captured.ruleRowsWhileCollapsed = await page.locator('.rule-grid .rgrid-record').count();
  check('3a-rule-board-collapsed-by-default',
    report.captured.ruleBoardCollapsedByDefault === 'false'
      && report.captured.ruleRowsWhileCollapsed === 0,
    `aria-expanded=${report.captured.ruleBoardCollapsedByDefault}, ${report.captured.ruleRowsWhileCollapsed} rows`);
  await ruleToggle.click();
  report.captured.ruleBoardExpanded = await ruleToggle.getAttribute('aria-expanded');
  await page.locator('.rule-grid .rgrid-record').first().waitFor({ timeout: 30000 });
  report.captured.ruleRowCount = await page.locator('.rule-grid .rgrid-record').count();
  check('3b-rule-rows-appear-on-expand',
    report.captured.ruleBoardExpanded === 'true' && report.captured.ruleRowCount > 0,
    `aria-expanded=${report.captured.ruleBoardExpanded}, ${report.captured.ruleRowCount} rows`);
  report.captured.ruleGridAccessibleName = await page.locator('.rule-grid').getAttribute('aria-label');
  report.captured.ruleGridRole = await page.locator('.rule-grid').getAttribute('role');
  report.captured.ruleGridColumns = await page.locator('.rule-grid [role="columnheader"]')
    .evaluateAll((nodes) => nodes.map((n) => n.textContent));
  check('3c-rule-grid-is-a-named-table',
    report.captured.ruleGridRole === 'table' && Boolean(report.captured.ruleGridAccessibleName)
      && report.captured.ruleGridColumns.length === 3,
    `${report.captured.ruleGridRole} "${report.captured.ruleGridAccessibleName}" columns ${report.captured.ruleGridColumns.join('/')}`);

  // The explanation is disclosed by activating the row, not by hovering it.
  const firstRule = page.locator('.rule-grid .rgrid-record').first();
  await firstRule.locator('.rgrid-row').click();
  await firstRule.locator('.rule-explanation').waitFor({ state: 'visible', timeout: 20000 });
  report.captured.ruleExplanationDerived = (await firstRule.locator('.rule-explanation').innerText())
    .replace(/\n/g, ' | ').slice(0, 900);
  report.captured.ruleExplanationSteps = await firstRule
    .locator('.rule-explanation .derived-steps > li > .derived-step-body > b')
    .evaluateAll((nodes) => nodes.map((n) => n.textContent));
  check('3d-rule-explains-itself-from-its-query',
    report.captured.ruleExplanationSteps.length >= 3
      && report.captured.ruleExplanationSteps.some((s) => /In this window it found/i.test(s)),
    report.captured.ruleExplanationSteps.join(' / '));
  await shot('rule-derived-1440x900');
  await firstRule.locator('.rgrid-row').click();
  await firstRule.locator('.rule-explanation').waitFor({ state: 'detached', timeout: 10000 });
  check('3e-rule-explanation-closes-again',
    (await firstRule.locator('.rgrid-row').getAttribute('aria-expanded')) === 'false',
    `aria-expanded=${await firstRule.locator('.rgrid-row').getAttribute('aria-expanded')}`);

  // ---- 4. the critical situation, its score column, and its derivation --------------------
  const critical = page.locator('.situation').filter({ has: page.locator('.severity.critical') }).first();
  check('4a-critical-situation-present', (await critical.count()) > 0,
    `${await page.locator('.situation .severity.critical').count()} critical severities rendered`);
  if (!(await critical.evaluate((node) => node.classList.contains('selected')))) {
    await critical.locator('.situation-head').click();
    await page.locator('.situation.selected').first().waitFor({ timeout: 10000 });
  }
  if ((await critical.locator('.situation-body').count()) === 0) {
    await critical.locator('.situation-head').click();
  }
  await critical.locator('.situation-body').waitFor({ timeout: 10000 });
  report.captured.criticalSelected = await critical.evaluate((node) => node.classList.contains('selected'));
  check('4b-critical-situation-selected-and-open', report.captured.criticalSelected === true,
    `selected=${report.captured.criticalSelected}`);

  report.captured.factorColumns = await critical.locator('.situation-body [role="columnheader"]')
    .evaluateAll((nodes) => nodes.map((n) => n.textContent));
  check('4c-factor-score-column-is-labelled-once',
    report.captured.factorColumns.includes('Score') && report.captured.factorColumns.includes('Rule'),
    report.captured.factorColumns.join(' / '));
  report.captured.factorScores = await critical.locator('.situation-body .rgrid-score')
    .evaluateAll((nodes) => nodes.map((n) => n.textContent));
  check('4d-factor-scores-are-fixed-contributions',
    report.captured.factorScores.length > 0
      && report.captured.factorScores.every((s) => /^\+\d+$/.test(s.trim())),
    report.captured.factorScores.join(','));
  report.captured.factorEventsTest = await critical.locator('.situation-body .rgrid-stack.right')
    .first().innerText();
  check('4e-factor-reports-events-and-its-test',
    /\d/.test(report.captured.factorEventsTest) && report.captured.factorEventsTest.includes('\n'),
    report.captured.factorEventsTest.replace(/\n/g, ' | '));

  const factorRow = critical.locator('.situation-body .rgrid-record').first();
  await factorRow.locator('.rgrid-row').click();
  await critical.locator('.factor-body').first().waitFor({ timeout: 20000 });
  const factorBody = critical.locator('.factor-body').first();
  report.captured.factorLadder = (await factorBody.locator('.score-ladder').innerText()).replace(/\n/g, ' ');
  check('4f-score-ladder-explains-the-severity',
    /fixed contribution/i.test(report.captured.factorLadder)
      && /summed to\s*\d+/i.test(report.captured.factorLadder)
      && /→\s*(critical|high|medium|low)/i.test(report.captured.factorLadder),
    report.captured.factorLadder);
  // The nested "Show the exact query terms" disclosure lives inside this one, so scope to the
  // outer summary rather than matching both.
  await factorBody.locator('.factor-reasoning > summary').click();
  await factorBody.locator('.factor-reasoning .derived').waitFor({ timeout: 10000 });
  report.captured.factorDerived = (await factorBody.locator('.factor-reasoning .derived').innerText())
    .replace(/\n/g, ' | ').slice(0, 900);
  check('4g-factor-derivation-is-generated-from-the-query',
    /Reads/i.test(report.captured.factorDerived)
      && /In this window it found/i.test(report.captured.factorDerived),
    report.captured.factorDerived.slice(0, 240));
  await shot('factor-derived-1440x900');

  if (SELFTEST) {
    // Same checker, one injected contract break: the class the metric affordance carries is
    // renamed. Nothing server-side is touched; the mutation lives in this page only.
    await page.evaluate(() => {
      for (const node of document.querySelectorAll('.metric-cell')) {
        node.classList.replace('metric-cell', 'metric-cell-legacy');
      }
    });
  }

  // ---- 5. every metric states its definition, its derivation and its contributions --------
  await page.locator('.metric-grid').waitFor({ timeout: 20000 });
  const cells = page.locator('.metric-cell');
  const cellCount = await cells.count();
  report.captured.metricCellCount = cellCount;
  check('5a-metrics-rendered', cellCount > 0, `${cellCount} metric cells`);
  report.captured.metrics = [];
  for (let i = 0; i < cellCount; i += 1) {
    const cell = cells.nth(i);
    const label = (await cell.locator('span').first().innerText()).trim();
    await cell.click();
    const controls = await cell.getAttribute('aria-controls');
    const panel = page.locator(`#${controls}`);
    await panel.waitFor({ timeout: 10000 });
    const entry = {
      label,
      cellText: (await cell.innerText()).replace(/\n/g, ' | '),
      ariaExpanded: await cell.getAttribute('aria-expanded'),
      ariaControls: controls,
      value: await panel.locator('header span').innerText(),
      definition: await panel.locator('.metric-definition').innerText(),
      derivation: await panel.locator('.metric-derivation code').innerText(),
      contributions: await panel.locator('.metric-contributions li')
        .evaluateAll((nodes) => nodes.map((n) => n.innerText.replace(/\n/g, ' | '))),
    };
    report.captured.metrics.push(entry);
    check(`5b-metric-${label.replace(/\s+/g, '-')}-explains-itself`,
      entry.ariaExpanded === 'true' && entry.definition.length > 30 && entry.derivation.length > 10,
      `${entry.value} · definition ${entry.definition.length} chars · derivation "${entry.derivation.slice(0, 90)}"`);
    await shot(`metric-${label.replace(/\s+/g, '-')}-1440x900`);
  }
  check('5c-every-metric-names-a-derivation',
    cellCount > 0 && report.captured.metrics.every((m) => m.derivation.trim().length > 0),
    report.captured.metrics.map((m) => m.label).join(' / '));
  const scanTime = report.captured.metrics.find((m) => /scan query time/i.test(m.label));
  check('5d-scan-time-metric-cites-its-rule-executions',
    Boolean(scanTime) && /quer(y|ies) dispatched concurrently/i.test(scanTime.derivation)
      && scanTime.contributions.length > 0,
    scanTime ? `${scanTime.contributions.length} contributions · ${scanTime.derivation.slice(0, 120)}` : 'metric absent');

  // ---- 5b. the metric affordance is operable from the keyboard ----------------------------
  if (cellCount > 0) {
    await cells.first().focus();
    report.captured.metricKeyboardFocus = await page.evaluate(() =>
      document.activeElement?.className ?? null);
    const before = await cells.first().getAttribute('aria-expanded');
    await page.keyboard.press('Enter');
    const after = await cells.first().getAttribute('aria-expanded');
    check('5e-metric-operable-from-the-keyboard',
      /metric-cell/.test(report.captured.metricKeyboardFocus ?? '') && before !== after,
      `focus ${report.captured.metricKeyboardFocus}, aria-expanded ${before} → ${after}`);
    report.captured.metricAfterEnter = after;
    await page.keyboard.press('Enter');
  }

  // ---- 6. the pattern board and the evidence boundary -------------------------------------
  const patternCount = await page.locator('.pattern-board article').count();
  report.captured.patternCount = patternCount;
  report.captured.patternBoardFirst = (await page.locator('.pattern-board article').first().innerText())
    .replace(/\n/g, ' | ');
  check('6a-pattern-board-matches-the-factor-rows',
    patternCount > 0 && patternCount === report.captured.factorScores.length,
    `${patternCount} pattern articles vs ${report.captured.factorScores.length} factor rows`);
  report.captured.patternCountTitle = await page.locator('.pattern-board .pattern-count')
    .first().getAttribute('title');
  check('6b-qualified-event-count-is-attributed',
    /record\(s\) counted by/i.test(report.captured.patternCountTitle ?? ''),
    report.captured.patternCountTitle ?? 'no title');
  await page.locator('.pattern-board .pattern-head').first().click();
  await page.locator('.pattern-board .pattern-body').first().waitFor({ timeout: 10000 });
  report.captured.patternBody = (await page.locator('.pattern-board .pattern-body').first().innerText())
    .replace(/\n/g, ' | ').slice(0, 600);
  check('6c-pattern-body-names-its-detector',
    (await page.locator('.pattern-board .pattern-body code').first().innerText()).trim().length > 0,
    report.captured.patternBody.slice(0, 200));
  report.captured.boundaryNote = (await page.locator('.boundary-note').innerText()).replace(/\n/g, ' | ');
  report.captured.boundaryRuleIds = await page.locator('.boundary-note li code')
    .evaluateAll((nodes) => nodes.map((n) => n.textContent));
  check('6d-boundary-note-refuses-live-monitoring-language',
    /static historical export/i.test(report.captured.boundaryNote)
      && /Nothing shown is live monitoring, detection, prevention, or containment/i
        .test(report.captured.boundaryNote),
    report.captured.boundaryNote.slice(0, 200));
  check('6e-boundary-note-cites-every-rule',
    report.captured.boundaryRuleIds.length === patternCount,
    report.captured.boundaryRuleIds.join(','));

  // ---- 7. tool renders: cited evidence, a board query, and two agent tool cards -----------
  await boardTab('evidence').click();
  await page.locator('.evidence-view .trender').waitFor({ timeout: 120000 });
  report.captured.evidenceToolCard = (await page.locator('.evidence-view .trender').innerText())
    .replace(/\n/g, ' | ').slice(0, 700);
  report.captured.evidenceRowCount = await page.locator('.evidence-view .trender-table tbody tr').count();
  check('7a-cited-evidence-renders-bounded-rows',
    report.captured.evidenceRowCount > 0
      && /resource_id/i.test(report.captured.evidenceToolCard),
    `${report.captured.evidenceRowCount} rows · ${report.captured.evidenceToolCard.slice(0, 160)}`);
  await shot('evidence-render-1440x900');

  await boardTab('tools').click();
  await page.locator('.tool-button').filter({ hasText: /Authentication mix/i }).click();
  await page.locator('.tools-view .trender').waitFor({ timeout: 120000 });
  report.captured.boardToolCard = (await page.locator('.tools-view .trender').innerText())
    .replace(/\n/g, ' | ').slice(0, 700);
  report.captured.boardToolRowCount = await page.locator('.tools-view .trender-table tbody tr').count();
  report.captured.boardToolScope = await page.locator('.tools-view .trender-scope')
    .innerText().catch(() => '');
  check('7b-board-query-renders-its-inputs-and-rows',
    report.captured.boardToolRowCount > 0 && /EventsUnified/i.test(report.captured.boardToolScope),
    `${report.captured.boardToolRowCount} rows · inputs ${report.captured.boardToolScope.replace(/\n/g, ' ').slice(0, 160)}`);
  await shot('board-tool-render-1440x900');

  // Cards are found by the tool that produced them, not by position.
  const toolCard = (displayName) => page.locator('.chat-panel .tool-card')
    .filter({ has: page.locator('.tool-card-head b', { hasText: displayName }) }).first();

  const askAgent = async (prompt) => {
    await page.locator('.chat-input textarea').fill(prompt);
    await page.locator('.chat-input button[type="submit"]').click();
  };

  await askAgent('Use the purpose-built authentication activity tool for host svpmn082 between '
    + '2026-08-13T02:30:00Z and 2026-08-13T03:40:59Z and report what it returned.');
  const authCard = toolCard('Authentication activity');
  await authCard.waitFor({ timeout: AGENT_TURN_MS });
  await authCard.locator('.tool-state.done').waitFor({ timeout: AGENT_TURN_MS });
  await authCard.locator('.tool-card-head').click();
  await authCard.locator('.trender').first().waitFor({ timeout: 30000 });
  report.captured.chatToolName = await authCard.locator('.tool-card-head b').innerText();
  report.captured.chatToolCard = (await authCard.locator('.trender').first().innerText())
    .replace(/\n/g, ' | ').slice(0, 900);
  report.captured.chatToolSignals = await authCard.locator('.trender-signals li')
    .evaluateAll((nodes) => nodes.map((n) => n.innerText.replace(/\n/g, ' ')));
  report.captured.chatToolRowCount = await authCard.locator('.trender-table tbody tr').count();
  check('7c-agent-runs-the-purpose-built-authentication-tool',
    report.captured.chatToolName.trim() === 'Authentication activity'
      && report.captured.chatToolRowCount > 0,
    `${report.captured.chatToolName} · ${report.captured.chatToolRowCount} rows · signals ${report.captured.chatToolSignals.join(' / ')}`);
  await shot('chat-tool-render-1440x900');

  await page.waitForFunction(
    () => !document.querySelector('.chat-input textarea')?.disabled, null, { timeout: AGENT_TURN_MS });
  await askAgent('Run the purpose-built scanner for 2026-08-13T02:30:00Z to 2026-08-13T03:40:59Z '
    + 'and identify the highest-priority situation.');
  const scanCard = toolCard('Scan situations');
  await scanCard.waitFor({ timeout: AGENT_TURN_MS });
  await scanCard.locator('.tool-state.done').waitFor({ timeout: AGENT_TURN_MS });
  await scanCard.locator('.tool-card-head').click();
  await scanCard.locator('.trender-situations').waitFor({ timeout: 30000 });
  report.captured.chatOrientationCard = (await scanCard.locator('.trender').first().innerText())
    .replace(/\n/g, ' | ').slice(0, 900);
  report.captured.chatOrientationSituations = await scanCard.locator('.trender-situations > li')
    .evaluateAll((nodes) => nodes.map((n) => n.innerText.replace(/\n/g, ' ')));
  check('7d-agent-scan-renders-situation-envelopes',
    report.captured.chatOrientationSituations.length > 0
      && /rules qualified/i.test(report.captured.chatOrientationSituations.join(' ')),
    report.captured.chatOrientationSituations.join(' | ').slice(0, 300));
  await shot('chat-orientation-render-1440x900');

  // ---- 8. the column resizer still moves the boundary, by pointer and by key --------------
  const separator = page.getByRole('separator', { name: 'Resize scanner and tool board' });
  const beforeWidth = (await page.locator('.scanner').boundingBox())?.width ?? 0;
  const beforeValue = Number(await separator.getAttribute('aria-valuenow'));
  await separator.focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(
    (previous) => Number(document.querySelector('.column-resizer')?.getAttribute('aria-valuenow')) !== previous,
    beforeValue, { timeout: 5000 });
  const keyValue = Number(await separator.getAttribute('aria-valuenow'));
  const keyWidth = (await page.locator('.scanner').boundingBox())?.width ?? 0;
  check('8a-resizer-nudges-from-the-keyboard', keyValue === beforeValue + 2 && keyWidth > beforeWidth,
    `aria-valuenow ${beforeValue} → ${keyValue}, scanner ${Math.round(beforeWidth)} → ${Math.round(keyWidth)}px`);

  const handle = await separator.boundingBox();
  await page.mouse.move(handle.x + handle.width / 2, handle.y + 200);
  await page.mouse.down();
  await page.mouse.move(handle.x + handle.width / 2 + 90, handle.y + 200, { steps: 8 });
  await page.mouse.up();
  const afterWidth = (await page.locator('.scanner').boundingBox())?.width ?? 0;
  report.captured.resize = {
    before: Math.round(beforeWidth), afterKeyboard: Math.round(keyWidth),
    afterDrag: Math.round(afterWidth), dragDelta: Math.round(afterWidth - keyWidth),
  };
  check('8b-resizer-drags-with-the-pointer', afterWidth - keyWidth > 40,
    JSON.stringify(report.captured.resize));

  // ---- 9. no horizontal overflow at any shipped viewport ----------------------------------
  for (const [w, h] of VIEWPORTS) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForFunction((expected) => document.documentElement.clientWidth === expected,
      w, { timeout: 10000 });
    report.overflow[`${w}x${h}`] = await overflow();
    check(`9a-${w}x${h}-no-horizontal-overflow`, report.overflow[`${w}x${h}`] === 0,
      `scrollWidth - clientWidth = ${report.overflow[`${w}x${h}`]}`);
    await shot(`viewport-${w}x${h}`);
  }

  check('10a-no-console-errors', consoleErrors.length === 0, consoleErrors.join(' | ') || 'none');
  check('10b-no-page-errors', pageErrors.length === 0, pageErrors.join(' | ') || 'none');
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
  const name = SELFTEST ? 'ui5-verification.selftest.json' : 'ui5-verification.json';
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
