import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';

const port = 19027;
const root = resolve('dist');
const runs = new Map();
const keys = new Map();
let counter = 0;
let controls = {};
const tasks = [{ id: 'fixture-export', name: 'Fixture: batch export', domain: 'test-fixture', description: 'Test-owned synthetic API fixture. No backend, agent, model, or deployment verification.' }];
const now = () => new Date().toISOString();
const digest = value => value.repeat(64);
const goodCheck = { name: 'CSV parser contract', status: 'passed', detail: 'Fixture output: 3 parser cases passed; output read-back matches expected bytes.' };

function makeRun() {
  const id = `fixture-run-${++counter}`;
  const baseline = { id: `${id}-baseline`, parent_id: null, name: 'Baseline', digest: digest('a'), status: 'passed', hypothesis: 'Retain measured baseline before changing export quoting.', diff: '', checks: [goodCheck] };
  const bad = { id: `${id}-failed`, parent_id: baseline.id, name: 'Unquoted export', digest: digest('b'), status: 'failed', hypothesis: 'Remove quotes to reduce output size.', diff: '--- a/export.ts\n+++ b/export.ts\n@@ -1 +1 @@\n-return quote(value);\n+return value;', checks: [{ name: 'Embedded comma', status: 'failed', detail: 'Fixture output: expected 2 columns, received 3. Deliberately wrong candidate retained.' }] };
  const fixed = { id: `${id}-fixed`, parent_id: bad.id, name: 'Quoted export', digest: digest('c'), status: 'passed', hypothesis: 'Quote only fields containing delimiters; preserve parser semantics.', diff: '--- a/export.ts\n+++ b/export.ts\n@@ -1 +1 @@\n-return value;\n+return needsQuotes(value) ? quote(value) : value;', checks: [goodCheck] };
  return {
    id, task_id: tasks[0].id, task_name: tasks[0].name, domain: tasks[0].domain,
    status: 'running', acceptance: 'not_verified', decision: 'inconclusive', evidence_class: 'synthetic-integration', executor: 'deterministic',
    created_at: now(), updated_at: now(),
    metrics: { elapsed_seconds: 2.4, repair_cycles: 1, actions: 6, calls: 4, files_changed: 1, lines_added: 1, lines_deleted: 1, first_pass_success: false, model_requests: null, telemetry_coverage: 'Fixture events only; model telemetry unavailable' },
    candidates: [baseline, bad, fixed],
    events: [
      { id: `${id}-1`, at: now(), kind: 'baseline', detail: 'Fixture baseline measured and retained.', candidate_id: baseline.id },
      { id: `${id}-2`, at: now(), kind: 'check_failed', detail: 'Fixture parser rejected unquoted delimiter. Failure remains in evidence.', candidate_id: bad.id },
      { id: `${id}-3`, at: now(), kind: 'repair', detail: 'Fixture repair recorded and independent parser check passed.', candidate_id: fixed.id },
    ],
    feedback: [], selected_candidate_id: fixed.id,
    limitations: ['TEST-OWNED FIXTURE. Browser behavior only; not real framework acceptance.', 'Cost, tokens, cohort denominators, deployment and handoff evidence are unavailable.'],
    restorations: [],
  };
}

function json(response, status, body) {
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store, private' });
  response.end(JSON.stringify(body));
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://127.0.0.1:${port}`);
    const path = url.pathname;
    if (request.method === 'POST') {
      if (request.headers.origin !== `http://127.0.0.1:${port}`) return json(response, 403, { detail: 'Fixture: same-origin browser mutation required.' });
      let raw = '';
      for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw || '{}');
      if (path === '/__fixture/reset') { runs.clear(); keys.clear(); controls = {}; return json(response, 200, {}); }
      if (path === '/__fixture/control') { controls = { ...controls, ...body }; return json(response, 200, {}); }
      const identity = `${path}:${body.idempotency_key}`;
      if (body.idempotency_key && keys.has(identity)) return json(response, 200, runs.get(keys.get(identity)));
      if (path === '/api/runs') {
        if (body.executor !== 'deterministic' || body.task_id !== tasks[0].id || !body.idempotency_key) return json(response, 422, { detail: 'Fixture: invalid run request.' });
        const run = makeRun();
        runs.set(run.id, run);
        keys.set(identity, run.id);
        const timer = setTimeout(() => {
          if (run.status !== 'running') return;
          run.status = 'completed'; run.acceptance = 'passed'; run.decision = 'no_improvement'; run.updated_at = now();
          run.events.push({ id: `${run.id}-4`, at: now(), kind: 'completed', detail: 'Fixture completed; no measured optimization improvement claimed.', candidate_id: run.selected_candidate_id });
        }, 2400);
        timer.unref();
        return json(response, 201, run);
      }
      const segments = path.split('/');
      const run = runs.get(decodeURIComponent(segments[3] || ''));
      if (!run) return json(response, 404, { detail: 'Fixture run not found.' });
      if (segments[4] === 'cancel') {
        if (run.status === 'running') { run.status = 'cancelled'; run.updated_at = now(); }
        return json(response, 200, run);
      }
      if (!body.idempotency_key) return json(response, 422, { detail: 'Fixture: idempotency key required.' });
      if (segments[4] === 'restore') {
        if (controls.refuseRestore) return json(response, 403, { detail: 'Fixture authority refuses restore.' });
        const candidate = run.candidates.find(item => item.id === body.candidate_id);
        if (!candidate || candidate.status !== 'passed' || !candidate.checks.every(check => check.status === 'passed')) return json(response, 409, { detail: 'Fixture: candidate not known-good.' });
        run.selected_candidate_id = candidate.id;
        if (!controls.missingRestoreReceipt) run.restorations.push({ at: now(), candidate_id: candidate.id, verified: true });
      } else if (segments[4] === 'feedback' && segments[6] === 'respond') {
        const feedback = run.feedback.find(item => item.id === segments[5]);
        if (!feedback) return json(response, 404, { detail: 'Fixture: feedback not found.' });
        if (!['apply', 'clarify', 'defer', 'decline'].includes(body.disposition) || !body.reason?.trim()) return json(response, 422, { detail: 'Fixture: invalid disposition.' });
        Object.assign(feedback, { disposition: body.disposition, reason: body.reason, candidate_id: body.candidate_id });
      } else if (segments[4] === 'feedback') {
        if (!body.text?.trim()) return json(response, 422, { detail: 'Fixture: observation required.' });
        run.feedback.push({ id: `feedback-${run.feedback.length + 1}`, at: now(), author: 'Fixture local operator', text: body.text, candidate_id: body.candidate_id, disposition: null, reason: null });
      } else return json(response, 404, { detail: 'Fixture route not found.' });
      keys.set(identity, run.id);
      run.updated_at = now();
      if (segments[4] === 'feedback' && !segments[6] && controls.loseFeedbackResponse) {
        controls.loseFeedbackResponse = false;
        return json(response, 504, { detail: 'Fixture save outcome unknown after persistence.' });
      }
      return json(response, 200, run);
    }
    if (path === '/api/health') return json(response, 200, { status: 'ok' });
    if (path === '/api/tasks') {
      if (controls.delayTasks) await new Promise(resolveDelay => setTimeout(resolveDelay, 800));
      if (controls.failReads) return json(response, 503, { detail: 'Fixture API temporarily unavailable.' });
      return json(response, 200, { tasks });
    }
    if (path === '/api/runs') return json(response, 200, controls.malformed ? { runs: [{ id: 'broken' }] } : { runs: [...runs.values()].reverse() });
    if (path.startsWith('/api/runs/')) {
      const segments = path.split('/');
      const run = runs.get(decodeURIComponent(segments[3]));
      if (!run) return json(response, 404, { detail: 'Fixture run not found.' });
      if (segments[4] === 'report') {
        if (controls.refuseDownload) return json(response, 403, { detail: 'Fixture report access refused.' });
        const format = url.searchParams.get('format');
        const content = format === 'json' ? JSON.stringify(run) : format === 'csv' ? `id,status,decision\n${run.id},${run.status},${run.decision}\n` : `<!doctype html><title>Test fixture report</title><h1>TEST-OWNED FIXTURE</h1><p>${run.id}: ${run.decision}</p>`;
        response.writeHead(200, { 'Content-Type': format === 'json' ? 'application/json' : format === 'csv' ? 'text/csv' : 'text/html', 'Content-Disposition': `attachment; filename="fixture.${format}"`, 'Cache-Control': 'no-store, private' });
        return response.end(content);
      }
      return json(response, 200, controls.reverseCandidates ? { ...run, candidates: [...run.candidates].reverse() } : run);
    }
    if (path.startsWith('/api/')) return json(response, 404, { detail: 'Fixture route not found.' });
    const file = resolve(root, path === '/' ? 'index.html' : `.${decodeURIComponent(path)}`);
    if (!file.startsWith(`${root}/`)) return json(response, 403, { detail: 'Outside fixture static root.' });
    const content = await readFile(file);
    response.writeHead(200, { 'Content-Type': ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' })[extname(file)] || 'application/octet-stream' });
    response.end(content);
  } catch (error) {
    json(response, 500, { detail: `Fixture error: ${error.message}` });
  }
});

server.listen(port, '127.0.0.1', () => console.log(`TEST-OWNED FIXTURE server http://127.0.0.1:${port}; not integrated backend evidence.`));