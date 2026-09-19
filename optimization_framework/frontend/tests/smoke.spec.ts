import { expect, test, type Page } from '@playwright/test';
import { runSchema, type Run } from '../src/api';

test.beforeEach(async ({ request, baseURL }) => {
  if (process.env.UI_FIXTURE === '1') {
    const response = await request.post('/__fixture/reset', { headers: { Origin: baseURL! }, data: {} });
    expect(response.ok()).toBeTruthy();
  }
});

export async function startRun(page: Page): Promise<Run> {
  await expect(page.getByRole('button', { name: 'Start run', exact: true })).toBeEnabled();
  const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/runs' && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBeTruthy();
  expect((await response.request().allHeaders()).origin).toBe(new URL(page.url()).origin);
  expect(response.request().postDataJSON()).toMatchObject({ executor: 'deterministic', idempotency_key: expect.any(String) });
  return runSchema.parse(await response.json());
}

export async function finished(page: Page, id: string): Promise<Run> {
  let result: Run | undefined;
  await expect.poll(async () => {
    const response = await page.request.get(`/api/runs/${encodeURIComponent(id)}`);
    expect(response.ok()).toBeTruthy();
    result = runSchema.parse(await response.json());
    return result.status;
  }, { timeout: 25000, intervals: [250, 500, 1000] }).not.toBe('running');
  return result!;
}

async function geometry(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  const controls = page.locator('button:visible, select:visible, textarea:visible');
  for (const control of await controls.all()) {
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(0);
    if ((page.viewportSize()?.width ?? 1440) <= 700) expect(box!.height).toBeGreaterThanOrEqual(44);
  }
}

test('four views: deterministic run, persisted SME disposition, restore and exports', async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to workspace' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
  const started = await startRun(page);
  const completed = await finished(page, started.id);
  expect(completed.evidence_class).toBe('synthetic-integration');
  await expect(page.getByText('Synthetic evidence.', { exact: true })).toBeVisible();
  await expect(page.getByRole('row').filter({ has: page.getByRole('button', { name: `Select run ${started.id}`, exact: true }) })).toContainText(completed.status);
  if (completed.metrics.model_requests === null) await expect(page.getByRole('cell', { name: /Model requests: Not captured/ }).first()).toBeVisible();
  await geometry(page);
  await page.screenshot({ path: testInfo.outputPath(`${process.env.UI_FIXTURE ? 'fixture' : 'integrated'}-desktop-comparison.png`), fullPage: true });

  await page.getByRole('button', { name: 'Run timeline', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Recorded timeline/ })).toBeVisible();
  expect(completed.events.length).toBeGreaterThan(0);
  await expect(page.locator('.timeline li')).toHaveCount(completed.events.length);
  await page.getByRole('button', { name: 'Candidate evidence', exact: true }).click();
  const good = completed.candidates.find(candidate => candidate.status === 'passed' && candidate.checks.length > 0 && candidate.checks.every(check => check.status === 'passed'));
  expect(good, 'Demo must retain at least one known-good candidate').toBeDefined();
  const failed = completed.candidates.find(candidate => candidate.status === 'failed');
  if (failed) {
    await page.getByRole('combobox', { name: 'Candidate', exact: true }).selectOption(failed.id);
    await expect(page.getByRole('button', { name: 'Restore candidate', exact: true })).toBeDisabled();
    if (failed.diff) await expect(page.getByLabel('Candidate source diff')).toContainText(failed.diff);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: testInfo.outputPath(`${process.env.UI_FIXTURE ? 'fixture' : 'integrated'}-desktop-diff.png`), fullPage: true });
  }
  await page.getByRole('combobox', { name: 'Candidate', exact: true }).selectOption(good!.id);
  await expect(page.getByRole('heading', { name: 'Acceptance checks', exact: true })).toBeVisible();
  const observation = `Browser smoke observation ${Date.now()}: retain failed checks.`;
  await page.getByRole('textbox', { name: 'Observation', exact: true }).fill(observation);
  await page.getByRole('combobox', { name: 'Linked candidate', exact: true }).selectOption(good!.id);
  await page.getByRole('button', { name: 'Submit feedback', exact: true }).click();
  const entry = page.getByRole('article').filter({ hasText: observation });
  await expect(entry).toContainText('awaiting response');
  const stored = runSchema.parse(await (await page.request.get(`/api/runs/${started.id}`)).json());
  const feedback = stored.feedback.find(item => item.text === observation)!;
  expect(feedback.author.length).toBeGreaterThan(0);
  await expect(entry).toContainText(feedback.author);
  await entry.getByRole('button', { name: 'Respond', exact: true }).click();
  await entry.getByRole('combobox', { name: 'Disposition', exact: true }).selectOption('apply');
  await entry.getByRole('combobox', { name: 'Resulting candidate', exact: true }).selectOption(good!.id);
  await entry.getByRole('textbox', { name: 'Reason', exact: true }).fill('Linked candidate and retained acceptance checks reviewed.');
  await entry.getByRole('button', { name: 'Record disposition', exact: true }).click();
  await expect(entry).toContainText('apply');
  await page.reload();
  await page.getByRole('button', { name: 'Candidate evidence', exact: true }).click();
  await expect(entry).toContainText('Linked candidate and retained acceptance checks reviewed.');
  await entry.getByRole('button', { name: `Change & checks: ${good!.name}`, exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Candidate', exact: true })).toHaveValue(good!.id);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath(`${process.env.UI_FIXTURE ? 'fixture' : 'integrated'}-desktop-evidence.png`), fullPage: true });
  await page.getByRole('button', { name: 'Restore candidate', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: 'Confirm restore', exact: true })).toBeDisabled();
  await dialog.getByRole('checkbox', { name: 'I confirm restoration to this candidate.' }).check();
  await dialog.getByRole('button', { name: 'Confirm restore', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Experiment report', exact: true }).click();
  await expect(page.getByText('Restore verified by service', { exact: true }).last()).toBeVisible();
  for (const format of ['json', 'csv', 'html']) {
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: `Download ${format.toUpperCase()} report` }).click();
    const download = await downloadPromise;
    expect(await download.failure()).toBeNull();
    await download.saveAs(testInfo.outputPath(`report.${format}`));
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const name of ['Comparison', 'Run timeline', 'Candidate evidence', 'Experiment report']) {
    await page.getByRole('navigation', { name: 'Views' }).getByRole('button', { name, exact: true }).click();
    await geometry(page);
    await page.screenshot({ path: testInfo.outputPath(`${process.env.UI_FIXTURE ? 'fixture' : 'integrated'}-mobile-${name.toLowerCase().replaceAll(' ', '-')}.png`), fullPage: true });
  }
  const readBack = runSchema.parse(await (await page.request.get(`/api/runs/${started.id}`)).json());
  expect(readBack.feedback.filter(item => item.text === observation)).toHaveLength(1);
  expect(readBack.feedback.find(item => item.text === observation)).toMatchObject({ disposition: 'apply', candidate_id: good!.id });
  expect(readBack.restorations).toContainEqual(expect.objectContaining({ candidate_id: good!.id, verified: true }));
  expect(browserErrors).toEqual([]);
});

test('running experiment can be cancelled through its actual control', async ({ page }) => {
  await page.goto('/');
  const started = await startRun(page);
  test.skip(started.status !== 'running', 'Run already settled at creation; cancellation window unavailable.');
  const responsePromise = page.waitForResponse(response => response.url().endsWith(`/api/runs/${started.id}/cancel`) && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBeTruthy();
  const cancelled = runSchema.parse(await response.json());
  test.skip(cancelled.status === 'completed', 'Run completed before cancellation reached service; cancellation not verified.');
  await expect(page.getByRole('region', { name: 'Selected run' })).toContainText('cancelled');
  const result = runSchema.parse(await (await page.request.get(`/api/runs/${started.id}`)).json());
  expect(result.status).toBe('cancelled');
});