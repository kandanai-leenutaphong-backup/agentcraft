"""Explicit local archival publication, never execution of delivered evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path('/home/hanchoong/agentcraft')
PROJECT = ROOT / 'demonstration_project/agentcraft_projects/overseer-self-optimization'
EVIDENCE = PROJECT / 'results/20260920T105851Z-public-app-integration/evidence'
PRESTATE = PROJECT / 'records/v2/20260920T105621593777Z-public-integrated-app-deployment-prestate/record.json'
AUTH = PROJECT / 'records/v2/20260920T105621430601Z-public-integrated-app-deployment-authorized/record.json'
FINAL = EVIDENCE / '20260920T112457914750Z-command.json'
PIN = '070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37'
APP = 'template_apps/investigation_app/'
ABSENT = ['deploy/investigation.py', 'deploy/infra/investigation.bicep', 'deploy/env/agentcraft-dev.json',
          'deploy/Dockerfile.investigation', 'deploy/tests/test_investigation.py']
DEPLOYMENT = ['deploy/deploy.sh', 'deploy/README.md', APP + 'deploy/README.md',
              APP + 'pyproject.toml', APP + 'uv.lock', '.gitignore', 'README.md']
OWNERS = [APP + suffix for suffix in [
    'app/cybereye/backend/data/__init__.py', 'app/cybereye/backend/data/graph.py',
    'app/cybereye/backend/data/graph_binding.py', 'app/cybereye/backend/data/telemetry.py',
    'app/cybereye/backend/data/public_graph.py', 'app/cybereye/backend/config.py',
    'app/cybereye/backend/main.py', 'app/cybereye/backend/security/entra.py',
    'app/cybereye/backend/security/signin_routes.py', 'app/cybereye/backend/agents/library.py',
    'app/cybereye/backend/agents/editor.py', 'app/cybereye/backend/agents/profiles.py',
    'app/cybereye/control/public_agent_config.yaml', 'app/cybereye/control/public_data_inventory.yaml',
    'app/cybereye/control/prompts/public/investigation.md']]
FIXTURE = APP + 'app/cybereye/tests/public_runtime.py'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '.github/skills/agentcraft-process'))
import record as recorder


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def read(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Symlink refused: ' + str(path))
    return path.read_bytes()


def load(path):
    return json.loads(read(path))


def ref(path, relation):
    return {'path': str(path.relative_to(PROJECT)), 'sha256': digest(read(path)), 'relation': relation}


def safe(payload, source):
    payload.decode('utf-8')
    if b'\x00' in payload or re.search(rb'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----', payload):
        raise ValueError('Restricted payload: ' + source)
    if re.search(rb'(?:AccountKey|SharedAccessSignature)\s*=\s*[^\s;"\']{16,}|\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}', payload):
        raise ValueError('Credential-shaped payload: ' + source)
    if len(payload) > 2 * 1024**2:
        raise ValueError('Oversize artifact: ' + source)


def check():
    pins = {
        PRESTATE: 'e6965a8775a73a7355920f5658f74bd1854598bc5d265d41a0345987cf60c2cf',
        AUTH: '3baad87de19d58d0167896b3dc77a02e58d970ffff3763b83bacf37f5321e423',
        PROJECT / 'constitution/constitution.yaml': PIN,
        EVIDENCE / 'snapshot-request.json': '77b8f2c162128e8b34c19b564b85bb7a61aaccd1f79b13cc38f00494a5b6e939',
        EVIDENCE / '20260920T112245850767Z-command.json': 'b04a2d0627df71620d346fc5bfdba54c1d436df978f19ed0ffa60948884701d3',
        EVIDENCE / '20260920T112256295932Z-command.json': '7be2c48a170f9dd9ca9ed02bf148b824f7472ec35259d4258bd870e8ff1aa185',
        EVIDENCE / '20260920T111717051962Z-command.json': 'ca28a1399fbdb33b0dda2411a379fb47172571700a4ab9b2ee1af36d9a3f5181',
        EVIDENCE / '20260920T112214437601Z-command.json': '6ec929cbd82ed3c6e462c9017988b4f7a73c8d7e2c4a34c199bb4a8fdb62b77c',
        EVIDENCE / '2026-09-20T11-17-28-057Z-browser/report.json': '38da3952ccc1eb8d478bfc0c397a4e4bbcba5f04f8ef5c8c4983da78ca60c3a0'}
    for path, expected in pins.items():
        assert digest(read(path)) == expected, 'Pin drift: ' + str(path)
    prior = load(PRESTATE)
    before = {item['path']: item['before'] for item in prior['changes']}
    for previous in before.values():
        if previous and previous.get('state') == 'present':
            payload = read(PRESTATE.parent / previous['snapshot'])
            assert digest(payload) == previous['sha256'] and len(payload) == previous['bytes']
    final = load(FINAL)
    sources = {}
    for absolute, expected in final['sources'].items():
        path = Path(absolute)
        relative = str(path.relative_to(ROOT))
        assert not path.name.startswith('.env') or path.name == '.env.example'
        payload = read(path)
        safe(payload, relative)
        assert digest(payload) == expected, 'Worker manifest drift: ' + relative
        sources[relative] = payload
    ui = load(EVIDENCE / 'snapshot-request.json')['requested_snapshots']
    assert len(ui) == len({item['path'] for item in ui}) == 3
    for item in ui:
        payload = read(ROOT / item['path'])
        safe(payload, item['path'])
        assert digest(payload) == item['sha256'] and len(payload) == item['bytes'], item['path']
        sources[item['path']] = payload
    for relative in DEPLOYMENT + OWNERS + [FIXTURE]:
        assert relative in sources, relative
    for relative in ABSENT:
        assert before[relative]['state'] == 'absent', relative
        assert not (ROOT / relative).exists() and not (ROOT / relative).is_symlink(), relative
    commands = sorted(EVIDENCE.glob('*-command.json'))
    reports = sorted(EVIDENCE.glob('*-browser/report.json'))
    paths = [EVIDENCE / 'handoff.md', EVIDENCE / 'snapshot-request.json', *commands, *reports]
    evidence = {str(path.relative_to(ROOT)): read(path) for path in paths}
    for relative, payload in evidence.items():
        safe(payload, relative)
    browser = load(EVIDENCE / '2026-09-20T11-17-28-057Z-browser/report.json')
    assert browser['status'] == 'failed' and len(browser['checks']) == 21
    for filename, expected in [('20260920T112245850767Z-command.json', '286 passed'),
                               ('20260920T112256295932Z-command.json', '# pass 29\n')]:
        command = load(EVIDENCE / filename)
        assert command['exit_code'] == 0 and expected in command['output']
    assert load(EVIDENCE / '20260920T111717051962Z-command.json')['exit_code'] == 0
    for report_path in reports:
        for screenshot in load(report_path).get('screenshots', []):
            path = Path(screenshot['path'])
            assert path.is_relative_to(EVIDENCE)
            assert digest(read(path)) == screenshot['sha256'], str(path)
    summary = {'checked_at': now(), 'constitution_revision': 9, 'constitution_sha256': PIN,
               'ui_hashes_verified': 3, 'manifest_sources': len(final['sources']),
               'command_receipts': len(commands), 'browser_reports': len(reports),
               'absent_deployment_paths': ABSENT, 'browser_status': browser['status'],
               'browser_successful_checks': len(browser['checks']),
               'command_outcomes': [{'path': str(path.relative_to(PROJECT)), 'exit_code': load(path).get('exit_code'),
                                     'elapsed_seconds': load(path).get('elapsed_seconds')} for path in commands]}
    return sources, evidence, before, ui, summary


def publish():
    sources, evidence, before, ui, summary = check()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    material = PROJECT / ('records/v2/' + stamp + '-public-integration-capture-material')
    material.mkdir()
    staged = {}
    for index, (relative, payload) in enumerate({**sources, **evidence}.items()):
        target = material / (f'source-{index:04d}-' + Path(relative).name.replace('.env.example', 'env-example.txt'))
        with target.open('xb') as stream:
            stream.write(payload)
        assert read(target) == payload
        staged[relative] = target

    def write_json(name, value):
        target = material / name
        with target.open('x') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
        assert load(target) == value
        return target

    manifest = write_json('capture-manifest.json', {
        'observed_at': summary['checked_at'], 'clock': 'UTC host wall clock; archival capture, not historical execution',
        'worker_manifest': ref(FINAL, 'worker-final-source-manifest'), 'preflight': summary,
        'entries': [{'source_path': relative, 'sha256': digest(read(target)), 'bytes': target.stat().st_size,
                     'staged_path': str(target.relative_to(PROJECT))} for relative, target in staged.items()],
        'script_sha256': digest(read(Path(__file__))),
        'authority': 'Current user assignment; records only; no source mutation, cloud/model calls or evidence execution'})
    initial_refs = [ref(PRESTATE, 'prior-prestate'), ref(AUTH, 'prior-authorization')]
    receipts = []

    def base(kind, identity):
        return {'record_type': kind, 'id': identity, 'actor': 'archivist', 'stage': 'data-understanding',
                'occurred_at': None, 'historical_time_reason': 'No single event timestamp supplied; command timestamps retained in evidence',
                'evidence': [ref(manifest, 'capture-manifest')], 'record_refs': list(initial_refs), 'supersedes': [],
                'comparison_series': {'id': 'public-investigation-20260920', 'status': 'unscored-exploration'},
                'archival_actions': [
                    'Read process, handoff, request, prior receipts, recorder/schema, approved manifest and blank/example-only .env.example.',
                    'Parsed delivered command/report JSON as data; no worker commands executed; no private session history or live secrets read.',
                    'Initial apply_patch command failed because tool unavailable; no write occurred. Used git apply for record-only archival helper.',
                    'Tightened preflight initially expected pytest wording in Node TAP output and failed; jq summarizer also unavailable. Corrected expected TAP line; retained original evidence unchanged.',
                    'Verified constitution/receipt/source/UI pins, prior snapshot bytes and five explicit deployment absences.',
                    'Staged exact allowlisted UTF-8 bytes in project record folder; published through saved recorder; immediately verified schema/references/bytes.',
                ], 'clock': {'archival': 'saved recorder UTC host wall clock', 'historical': 'delivered command clocks; otherwise null'}}

    def capture(record, paths):
        chosen = list(dict.fromkeys(paths))
        snapshots = [str(staged[relative].relative_to(ROOT)) for relative in chosen]
        snapshots.append(str(manifest.relative_to(ROOT)))
        for index, relative in enumerate(chosen):
            snapshot = {'state': 'present', 'snapshot': f'artifacts/{index:04d}-{staged[relative].name}',
                        'sha256': digest(read(staged[relative])), 'bytes': staged[relative].stat().st_size,
                        'observed_at': summary['checked_at']}
            for change in record.get('changes', []):
                if change['path'] == relative:
                    change['before' if record.get('capture_phase') == 'before' else 'after'] = snapshot
        destination = recorder.publish(PROJECT, record, snapshots=snapshots, snapshot_root=ROOT)
        verified = recorder.verify(PROJECT)
        assert str(destination) in verified
        archived = load(destination)
        assert archived['constitution']['sha256'] == PIN
        for artifact in archived['artifacts']:
            assert read(destination.parent / artifact['path']) == read(ROOT / artifact['source_path'])
        receipt = {'id': archived['id'], **ref(destination, record['record_type']),
                   'artifact_count': len(archived['artifacts']), 'verified_at': now()}
        receipts.append(receipt)
        print(json.dumps(receipt), flush=True)
        return destination

    gaps = [
        'Retrospective partial capture: complete worker read/edit/tool ledger, initial validation/runtime probe timestamps and costs not delivered.',
        'First browser timeout has command receipt but no report.json; local browser state folders and server logs not copied or inspected.',
        'Paths missing from original prestate have unknown historical before-state unless absence explicitly recorded; current bytes do not prove past absence.',
        'Measurement receipts pin only declared sources, not full source/build closure. Final manifest follows tests; temporal association is not causation.',
        'Browser overall FAILED despite 21 successful checks: two /api/whoami 404s; no browser rerun after backend-only fractional/minute-boundary fix.',
        'Real public payload with synthetic stores; production lifespan/routes/signed authorization and native Search keyed-read path exercised, not native Cosmos SDK network I/O.',
        'No deployed Entra login, populated cloud Search, cloud readback, model acceptance, fresh candidate invocation or held-out scoring; legacy browser not rerun.',
        'Scanner button and native agent dispatch acceptance pending; graph semantic edge integrity and mixed timestamp formats require focused review.',
        'No scoped diff supplied. Exact before/after bytes retained where available. Screenshots remain digest-linked primary evidence, not UTF-8 snapshots.',
        'No live restore or independent process inspection. Worker reports task servers settled. No notebook publication: archival work adds no reusable finding.',
    ]
    partial = base('checkpoint', 'public-integrated-app-partial-outcome')
    partial.update(status='partial-needs-rescope', decision_ids=[load(AUTH)['id']], capture_phase='after',
                   rationale='Preserve local checks and failures; no complete integration, deployment, model acceptance or improvement claim.',
                   coverage={'status': 'partial', 'observed': ['Exact final worker source allowlist and all delivered command/report receipts retained',
                             '286 backend passed; 29 frontend passed; build passed; browser failed with 21 successful checks'], 'gaps': gaps},
                   reversion={'status': 'not_verified', 'plan': 'Separate authorized restore from prior before.snapshot mappings. Unknown prior state needs explicit owner decision. No restoration by archivist.'},
                   changes=[], metrics=[], settlement={'cloud_operations': 'none reported; none by archivist', 'model_calls': 'none reported; none by archivist',
                   'servers': 'worker reports settled true and exit 0; not independently inspected', 'candidate_dispatch': 'none reported',
                   'verdict': 'No evaluator verdict supplied; partial checkpoint only'})
    for absolute in load(FINAL)['sources']:
        relative = str(Path(absolute).relative_to(ROOT))
        if Path(absolute).is_relative_to(EVIDENCE):
            continue
        previous = before.get(relative)
        before_ref = None if previous is None else {**previous, 'record': ref(PRESTATE, 'before-state')}
        action = 'unknown' if previous is None else ('added' if previous['state'] == 'absent' else
                 ('unchanged' if previous['sha256'] == digest(sources[relative]) else 'modified'))
        partial['changes'].append({'path': relative, 'action': action, 'before': before_ref, 'after': None,
                                   'before_gap': None if previous else 'Original prestate missing; historical absence not inferred'})
    for name, count, filename, unit in [
        ('backend_tests_passed', 286, '20260920T112245850767Z-command.json', 'tests'),
        ('frontend_tests_passed', 29, '20260920T112256295932Z-command.json', 'tests'),
        ('production_build_exit_code', 0, '20260920T111717051962Z-command.json', 'exit code'),
        ('browser_successful_checks', 21, '2026-09-20T11-17-28-057Z-browser/report.json', 'checks')]:
        partial['metrics'].append({'name': name, 'value': count, 'unit': unit, 'evidence': ref(EVIDENCE / filename, 'measurement'),
                                   'denominator': None, 'comparison': 'none; overlapping checks not additive',
                                   'overall_browser_status': 'failed' if name.startswith('browser') else None})
    partial['record_refs'] += [ref(ROOT / relative, 'primary-evidence') for relative in evidence]
    for report_path in sorted(EVIDENCE.glob('*-browser/report.json')):
        report = load(report_path)
        partial['evidence'].append({'report': ref(report_path, 'browser-report'), 'status': report.get('status'),
                                    'checks': len(report.get('checks', [])), 'errors': report.get('browser_errors'),
                                    'error': report.get('error'),
                                    'screenshots': report.get('screenshots')})
        for screenshot in report.get('screenshots', []):
            value = screenshot if isinstance(screenshot, str) else screenshot.get('path')
            if not value:
                continue
            path = Path(value)
            if not path.is_absolute():
                path = report_path.parent / path
            if path.is_relative_to(EVIDENCE) and path.is_file():
                partial['record_refs'].append(ref(path, 'retained-browser-screenshot'))
    outcome = capture(partial, [change['path'] for change in partial['changes']] + list(evidence))
    initial_refs.append(ref(outcome, 'partial-outcome'))

    decision = base('decision', 'public-source-aware-ui-whoami-authorized')
    decision.update(observation='Public mode shows legacy ADX/KQL/date/firewall claims; signed fixture omits existing protected whoami.',
                    hypothesis='Source-aware UI and existing protected identity handler composition can resolve misleading claims and 404s without auth weakening.',
                    decision='Authorize only requested three-file UI correction and existing signed whoami fixture repair, then local scoped checks.',
                    changed_levers={'ui': ui, 'signed_fixture': FIXTURE, 'read_only_handler': APP + 'app/cybereye/backend/security/signin_routes.py'},
                    rationale='Current user explicitly requests bounded continuation; archivist performs no implementation.',
                    approval={'attributed_to': 'Current user archival assignment through overseer', 'event_time': None,
                              'scope': 'Local source-aware UI and protected signed whoami fixture composition only',
                              'invariants': ['Preserve legacy default, owner state and native agent binding', 'No anonymous bypass or fake successful identity response',
                                             'No auth weakening, cloud/model operations, deployment, or source/constitution/evaluator/verdict mutation by archivist'],
                              'gate': 'Verify UI BEFORE receipt and partial-outcome fixture snapshot before mutation; pin drift needs new capture'},
                    expected_outcome='Truthful public labels/prompts and protected whoami fixture; unmeasured until worker checks.',
                    acceptance_refs=[{'check': 'Focused frontend tests/build and backend fixture tests'},
                                     {'check': 'Signed whoami success plus anonymous refusal, no bypass'},
                                     {'check': 'Actual scanner button and full desktop/mobile journey with errors retained; no external model call'}],
                    authority_source={'kind': 'current-user-assignment', 'decision_owner': 'overseer/user', 'historical_timestamp': None})
    authorized = capture(decision, [str((EVIDENCE / 'snapshot-request.json').relative_to(ROOT))])
    initial_refs.append(ref(authorized, 'bounded-continuation-authorization'))

    def before_checkpoint(identity, paths, rationale):
        checkpoint = base('checkpoint', identity)
        checkpoint.update(status='before-captured', decision_ids=[decision['id']], capture_phase='before', metrics=[],
                          changes=[{'path': relative, 'action': 'unchanged', 'before': None, 'after': None,
                                    'change_status': 'prechange-only'} for relative in paths],
                          rationale=rationale, coverage={'status': 'complete-for-declared-scope',
                          'observed': ['Current exact bytes verified against final worker manifest or explicit UI expected hashes'],
                          'gaps': ['No correction/deployment executed or measured; hashes do not establish runtime acceptance']},
                          reversion={'status': 'not_verified', 'plan': 'Separate authorized restore from changes[].before.snapshot and scoped verification. No restoration performed.'})
        return checkpoint

    ui_before = before_checkpoint('public-source-aware-ui-before', [item['path'] for item in ui],
                                 'Exactly three requested UI files; expected hashes and sizes verified before correction.')
    capture(ui_before, [item['path'] for item in ui])
    deploy_paths = list(dict.fromkeys(DEPLOYMENT + OWNERS))
    deployment = before_checkpoint('public-deployment-current-before', deploy_paths,
                                   'Deterministic current deployment inputs and manifest-listed data/roster/security/store owners; capture only, no new deployment grant.')
    deployment['decision_ids'] = [load(AUTH)['id']]
    for relative in ABSENT:
        deployment['changes'].append({'path': relative, 'action': 'unchanged', 'after': None, 'change_status': 'prechange-only',
                                      'before': {'state': 'absent', 'observed_at': summary['checked_at'],
                                                 'prior_absence': {'record': ref(PRESTATE, 'prior-absence'), 'path': relative}}})
    capture(deployment, deploy_paths)
    for relative, payload in {**sources, **evidence}.items():
        assert read(ROOT / relative) == payload, 'Source changed during capture: ' + relative
    for relative in ABSENT:
        assert not (ROOT / relative).exists() and not (ROOT / relative).is_symlink()
    verified = recorder.verify(PROJECT)
    index = write_json('publication-receipts.json', {'kind': 'derived-receipt-index-not-new-authority', 'receipts': receipts,
                       'constitution_sha256': PIN, 'verification': 'saved recorder.verify; owned snapshots read back; current sources rechecked',
                       'verified_owned_records': len(receipts), 'verified_at': now(), 'reversion': 'not_verified', 'coverage_gaps': gaps,
                       'next_unresolved_fact': 'Does bounded UI/whoami correction pass signed desktop/mobile scanner and full journey checks?',
                       'full_v2_records_verified': len(verified)})
    print(json.dumps({'receipt_index': ref(index, 'derived-receipts'), 'summary': summary}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish:
        publish()
    else:
        print(json.dumps(check()[-1], indent=2))
