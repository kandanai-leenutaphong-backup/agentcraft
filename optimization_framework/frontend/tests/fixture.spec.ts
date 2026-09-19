import { expect, test, type APIRequestContext } from '@playwright/test';
import { runSchema } from '../src/api';

const origin = 'http://127.0.0.1:19027';
async function control(request: APIRequestContext, body: object) {
  const response = await request.post('/__fixture/control', { headers: { Origin: origin }, data: body });
  expect(response.ok()).toBeTruthy();
}

test.beforeEach(async ({ request }) => {
  await request.post('/__fixture/reset', { headers: { Origin: origin }, data: {} });
});

test('fixture: loading, empty, service error, recovery and schema refusal', async ({ page, request }) => {
  await control(request, { delayTasks: true });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Loading workspace' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible();
  await control(request, { failReads: true, delayTasks: false });
  await page.getByRole('button', { name: 'Refresh runs', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  await expect(page.getByRole('button', { name: 'Start run', exact: true })).toBeDisabled();
  await control(request, { failReads: false, malformed: true });
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('API contract mismatch');
  await control(request, { malformed: false });
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Start run', exact: true })).toBeEnabled();
});

test('fixture: ambiguous feedback retry stays idempotent; restore and download refusal stay visible', async ({ page, request }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Selected run' })).toContainText('completed');
  const id = new URL(page.url()).searchParams.get('run')!;
  await page.getByRole('button', { name: 'Candidate evidence', exact: true }).click();
  await control(request, { loseFeedbackResponse: true });
  await page.getByRole('textbox', { name: 'Observation', exact: true }).fill('Fixture ambiguous save: retain this observation once.');
  const requests: string[] = [];
  page.on('request', outgoing => { if (outgoing.method() === 'POST' && outgoing.url().endsWith('/feedback')) requests.push(outgoing.postDataJSON().idempotency_key); });
  await page.getByRole('button', { name: 'Submit feedback', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 504');
  await page.getByRole('button', { name: 'Submit feedback', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Observation', exact: true })).toHaveValue('');
  expect(requests).toHaveLength(2);
  expect(requests[0]).toBe(requests[1]);
  const run = runSchema.parse(await (await request.get(`/api/runs/${id}`)).json());
  expect(run.feedback).toHaveLength(1);
  await expect(page.getByRole('article')).toHaveCount(1);
  await control(request, { refuseRestore: true });
  await page.getByRole('button', { name: 'Restore candidate', exact: true }).click();
  await page.getByRole('checkbox', { name: 'I confirm restoration to this candidate.' }).check();
  await page.getByRole('button', { name: 'Confirm restore', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('HTTP 403');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'Experiment report', exact: true }).click();
  await control(request, { refuseDownload: true });
  await page.getByRole('button', { name: 'Download JSON report', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Report download refused (HTTP 403)');
  await expect(page.getByText('No restore receipts recorded.')).toBeVisible();
  const wrongOrigin = await request.post('/api/runs', { headers: { Origin: 'http://untrusted.invalid' }, data: { task_id: 'fixture-export', executor: 'deterministic', idempotency_key: 'refused' } });
  expect(wrongOrigin.status()).toBe(403);
});

test('fixture: parent links survive shuffled candidates and restore requires verified receipt', async ({ page, request }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Selected run' })).toContainText('completed');
  await control(request, { reverseCandidates: true, missingRestoreReceipt: true });
  await page.getByRole('button', { name: 'Refresh runs', exact: true }).click();
  await page.getByRole('button', { name: 'Candidate evidence', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Previous known-good: Baseline', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Previous known-good: Baseline', exact: true }).click();
  await page.getByRole('button', { name: 'Restore candidate', exact: true }).click();
  await page.getByRole('checkbox', { name: 'I confirm restoration to this candidate.' }).check();
  await page.getByRole('button', { name: 'Confirm restore', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Restore response lacks matching selected candidate and verified receipt');
});