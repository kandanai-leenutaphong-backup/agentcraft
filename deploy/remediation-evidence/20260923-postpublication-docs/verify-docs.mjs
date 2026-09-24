import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const evidence = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(evidence, '../../..');
process.chdir(root);
const project = 'agentcraft_projects/foundry-official-integration-20260922';
const recordPath = `${project}/records/v2/20260922T200128628556Z-f09-migration-accepted/record.json`;
const resultSha = '9b170b406f631d275efb89cfb4ae71df241561b17706c7fe51eb2680c02d6416';
const constitutionSha = '0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8';
const before = {
  'testbeds/foundry-hosted-agents/README.md': '2c21901c7f306d1a571052f184d7998fd29910dd100e11ad4b37eb1f3773c69b',
  'testbeds/foundry-hosted-agents/deploy/README.md': '89966fc7c2f7c6dabb76884967e8a5e79705a1082b3df98c34f57e20a9ddf8e2',
  'testbeds/foundry-agent-evaluation/README.md': 'fda522e9baf6191d2ecfc2a29b0629333879b4accd78487a77b296d7d5d7639d',
  'testbeds/foundry-agent-evaluation/deploy/README.md': 'fabe7e549dba6fc63d2323ecaa8586faf479ef88a0a1a4356c9c6f496a69fad0',
  'testbeds/foundry-agent optimization/README.md': '1e2dc14922dba30b22349173e77ec66080ad1d9ac5d313b84e0b8925254ca0b3',
  'testbeds/foundry-agent optimization/deploy/README.md': '4854b00bbfb6e636b719cdffbacd90f2efa316cf4cd1d5497300009e266ef7b3',
  'specs/20260922_FOUNDRY_OFFICIAL_INTEGRATION_REMEDIATION.md': '95343d9507492f4d078213c905737c4623916a6a27a5f5b882de16c6f3112fa3',
  [`${project}/reports/latest.html`]: '5469a579ceb7a7b36e717475f487a9d2164ddd441a81f96b816804022bb99f89',
  'README.md': '4f97782cb933de3198fbf7942bd7c14e36dd1fbd14362d0a0df2204ec487b69a',
};
const hash = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const load = filename => JSON.parse(fs.readFileSync(filename, 'utf8'));
const requireCheck = (condition, message) => { if (!condition) throw Error(message); };
requireCheck(hash(recordPath) === resultSha, 'F09 digest mismatch');
requireCheck(hash(`${project}/constitution/constitution.yaml`) === constitutionSha, 'Constitution digest mismatch');
const result = load(recordPath);
let references = 0;
function verifyReferences(value) {
  if (!value || typeof value !== 'object') return;
  if (typeof value.path === 'string' && /^[a-f0-9]{64}$/.test(value.sha256 || '')) {
    const base = value.path.startsWith('artifacts/') ? path.dirname(recordPath)
      : /^(records|constitution)\//.test(value.path) ? project : '.';
    const target = path.join(base, value.path);
    requireCheck(hash(target) === value.sha256, `Reference digest mismatch: ${target}`);
    if (value.bytes !== undefined) requireCheck(fs.statSync(target).size === value.bytes, `Size mismatch: ${target}`);
    references++;
  }
  for (const child of Object.values(value)) verifyReferences(child);
}
verifyReferences(result);
requireCheck(hash(path.join(path.dirname(recordPath), result.constitution.snapshot)) === constitutionSha, 'Constitution snapshot mismatch');
const measurement = load('deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/measurement-addendum.json');
for (const entry of Object.values(measurement.current_source)) requireCheck(hash(entry.path) === entry.sha256, `Production source changed: ${entry.path}`);
const failures = [];
const stale = [];
const documents = Object.entries(before).map(([filename, beforeSha]) => {
  const text = fs.readFileSync(filename, 'utf8');
  const targets = filename.endsWith('.html')
    ? [...text.matchAll(/href="([^"]+)"/g)].map(match => match[1])
    : [...text.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)].map(match => match[1]);
  let local = 0, external = 0, fragments = 0;
  for (const target of targets) {
    if (/^[a-z][a-z0-9+.-]*:/i.test(target)) { external++; continue; }
    local++;
    const [relative, fragment] = decodeURIComponent(target).split('#');
    const resolved = relative ? path.resolve(path.dirname(filename), relative) : path.resolve(filename);
    if (!fs.existsSync(resolved)) { failures.push({ filename, target, issue: 'missing target' }); continue; }
    if (!fragment) continue;
    fragments++;
    const content = fs.readFileSync(resolved, 'utf8');
    const headings = [...content.matchAll(/^#{1,6}\s+(.+)$/gm)].map(match => match[1].toLowerCase().replace(/[^\p{L}\p{N}_\-\s]/gu, '').replace(/\s/g, '-'));
    const valid = /^L\d+(?:-L\d+)?$/.test(fragment)
      ? Number(fragment.match(/^L(\d+)/)[1]) <= content.split('\n').length
      : headings.includes(fragment) || content.includes(`id="${fragment}"`);
    if (!valid) failures.push({ filename, target, issue: 'missing fragment' });
  }
  if (/F09 (?:authoritative )?publication (?:remains )?pending|f08_verified_f09_publication_pending|F09 settlement prepared/i.test(text.replace(/\s+/g, ' '))) stale.push(filename);
  requireCheck(text.includes('20260922T200128628556Z-f09-migration-accepted/record.json'), `Missing authoritative link: ${filename}`);
  return { path: filename, before_sha256: beforeSha, after_sha256: hash(filename), links: { local, external_not_requested: external, fragments } };
});
const spec = fs.readFileSync('specs/20260922_FOUNDRY_OFFICIAL_INTEGRATION_REMEDIATION.md', 'utf8');
const order = JSON.parse(spec.match(/```json\n([\s\S]*?)\n```/)[1]);
requireCheck(order.status === 'f09_migration_accepted' && order.authoritative_result_sha256 === resultSha, 'Work order mismatch');
requireCheck(spec.includes('- [x] F09 operations settled'), 'F09 completion checkbox not checked');
const verification = spawnSync('python3', ['.github/skills/agentcraft-process/record.py', '--project-root', project, '--verify'], { encoding: 'utf8' });
requireCheck(verification.status === 0, `Recorder verification failed: ${verification.stderr}`);
const recorder = JSON.parse(verification.stdout);
const existingGaps = failures.filter(failure => failure.filename === 'README.md' && failure.target === 'demonstration_project/README.md' && failure.issue === 'missing target');
const newFailures = failures.filter(failure => !existingGaps.includes(failure));
const receipt = {
  authoritative: false, kind: 'postpublication-docs', observed_at: new Date().toISOString(),
  baseline_observed_at: '2026-09-22T20:03:23.769Z',
  result: { path: recordPath, sha256: resultSha }, constitution: { revision: 1, sha256: constitutionSha },
  status: newFailures.length || stale.length ? 'failed' : existingGaps.length ? 'complete_with_preexisting_link_gap' : 'complete', documents,
  checks: { local_link_failures: failures, unresolved_active_f09_status: stale, final_record_references: references,
    preexisting_out_of_scope_link_gaps: existingGaps, new_link_failures: newFailures,
    local_links_checked: documents.reduce((total, document) => total + document.links.local, 0),
    constitution_snapshot: 'verified', production_files_unchanged: Object.keys(measurement.current_source).length,
    recorder_command: `python3 .github/skills/agentcraft-process/record.py --project-root ${project} --verify`, recorder },
  scope: 'Nine active docs only; prior snapshots and receipts unchanged. No runtime/cloud/dependency changes, test reruns, agents, notebook edits or authoritative publication.',
  inherited_deadline: '2026-09-22T21:06:18Z', original_mission_monotonic_id: 'unavailable; local clock does not reset mission',
  clock: 'deploy/remediation-evidence/20260923-postpublication-docs/clock.jsonl',
  prior_check: { observed_at: '2026-09-22T20:06:47.009Z', exit_code: 1, finding: 'Existing root README link demonstration_project/README.md missing; present in pre-edit read. No docs acceptance defect or new broken link. Retained as out-of-scope gap, not silently repaired.' },
  capture_gaps: ['Tool calls retained in host transcript; no independent full transcript capture.', 'Clock checks exceeded 60 seconds during read/edit intervals.', 'External links not fetched; no fresh live acceptance or cost telemetry.'],
};
console.log(JSON.stringify(receipt, null, 2));
requireCheck(newFailures.length === 0 && stale.length === 0, 'Docs checks failed; no completion receipt written');
const destination = path.join(evidence, 'receipt.json');
if (fs.existsSync(destination)) {
  const retained = load(destination);
  requireCheck(JSON.stringify(retained.documents) === JSON.stringify(documents), 'Existing receipt differs; preserve it and use a new evidence path');
} else fs.writeFileSync(destination, JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });