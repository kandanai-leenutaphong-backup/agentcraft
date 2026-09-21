"""Measured create-only actions; gate one session against exact tested sources."""

import argparse
import json
import subprocess
import sys
import time
import unittest

from reuse import ROOT, PROJECT, WORKSPACE, PINS, REPAIR_PINS, ORIGINS, SITE, load, pins, now, save, sha, stamp


def sources():
    return {path.name: sha(path) for path in ROOT.glob('*.py')}


def tests():
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_transport.py')
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(load('test_capture', repair=True)))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 2


def gate():
    import yaml
    pins()
    previous = PROJECT / 'records/v2/20260921T114607680099Z-v17-live-instructions-20260921-prestate/artifacts/constitution.yaml'
    original, current = previous.read_bytes(), (PROJECT / 'constitution/constitution.yaml').read_bytes()
    metric_bytes = lambda raw: raw.split(b'\nmetrics:\n', 1)[1].split(b'\ndata_understanding:\n', 1)[0]
    assert metric_bytes(original) == metric_bytes(current)
    document = yaml.safe_load(current)
    assert document['revision'] == 12 and document['status'] == 'exploring'
    assert len(document['metrics']) == 13 and all(item['target']['value'] is None for item in document['metrics'])
    result = subprocess.run([sys.executable, '-B', str(WORKSPACE / '.github/skills/agentcraft-process/validate.py'),
                             str(PROJECT / 'constitution/constitution.yaml')], capture_output=True, timeout=20)
    assert result.returncode == 0
    import copilot, signed_dev_access
    from transport import publication, wire
    from copilot.generated.rpc import ToolCallResult, ToolsHandlePendingToolCallRequest
    chunks, index = publication()
    for chunk in chunks.values():
        text = wire(chunk)
        request = ToolsHandlePendingToolCallRequest(request_id='fixture', result=ToolCallResult(text_result_for_llm=text, result_type='success'))
        assert request.to_dict()['result']['textResultForLlm'] == text
        assert len(text) <= 2000 and len(text.encode()) <= 2000
    receipt = {'at': now(), 'constitution_revision': 12, 'constitution_sha256': sha(PROJECT / 'constitution/constitution.yaml'),
               'readme_sha256': sha(WORKSPACE / 'demonstration_project/README.md'), 'exact_original_metric_bytes': True,
               'metric_count': 13, 'all_targets_null': True, 'validator_exit_code': result.returncode,
               'authority_pins': {str(path.relative_to(WORKSPACE)): value for path, value in PINS.items()},
               'repair_sources': REPAIR_PINS, 'original_sources': ORIGINS, 'instruction_index': index,
               'sdk_rpc_roundtrip_exact': True, 'max_instruction_payload_bytes': max(len(wire(chunk).encode()) for chunk in chunks.values()),
               'runtime': {'python': sys.executable, 'existing_site_append': str(SITE), 'sdk': copilot.__file__, 'signer': signed_dev_access.__file__},
               'stage_clock': {'utc': '2026-09-21T11:47:09.830188818Z', 'linux_monotonic_seconds': 351892.18,
                               'precision_seconds': 0.01, 'source': 'date UTC and /proc/uptime, first stage command'},
               'initial_actions': ['Read process and pinned prior handoff; architecture overview absent',
                                   'Read native/reuse/constitution/README and verify decision/prestate/rev11 hashes',
                                   'Minimal rev12/README edit; immediate validator and exact metric-byte check passed',
                                   'Read pinned capture/live-input/evaluation/run/verification/fixtures and public SDK contracts',
                                   'Added reuse/transport/seven fixtures; immediate seven fixtures passed',
                                   'Read candidate/generic orchestration rules, SDK serialization and scoped git status'],
               'capture_gaps': ['Initial individual tool dispatch timestamps and exact complete action counts unknown',
                                'Missing docs/ARCHITECTURE_OVERVIEW.md', 'Parent effort unverified; no private logs inspected'],
               'checkpoint_kind': 'worker primary version/validation receipt; authoritative archivist publication remains overseer-owned'}
    save(ROOT / 'rev12-gate.json', receipt)
    print(json.dumps({'gate_sha256': sha(ROOT / 'rev12-gate.json'), 'chunks': len(chunks), 'sdk_roundtrip': True}))
    return 0


def run(action):
    identifier, started = stamp(), time.monotonic_ns()
    commands = {name: [sys.executable, '-B', str(ROOT / 'run.py'), '--internal', name] for name in ('tests', 'gate', 'inputs', 'readback', 'verify')}
    commands['mission'] = [sys.executable, '-B', str(ROOT / 'native.py')]
    report = {'action': action, 'command': commands[action], 'started_at': now(), 'monotonic_start_ns': started,
              'timeout_seconds': 1100 if action == 'mission' else 360, 'source_sha256': sources()}
    if action == 'mission':
        assert not (ROOT / 'one-session-started.json').exists() and not (ROOT / 'one-inference-admitted.json').exists()
        passed = [json.loads(path.read_text()) for path in ROOT.glob('*-action-tests.json')]
        assert any(item['exit_code'] == 0 and item['source_sha256'] == report['source_sha256'] for item in passed)
        assert (ROOT / 'rev12-gate.json').exists()
        pins()
    save(ROOT / (identifier + '-action-' + action + '-started.json'), report)
    try:
        result = subprocess.run(commands[action], cwd=WORKSPACE, capture_output=True, timeout=report['timeout_seconds'])
        report.update(exit_code=result.returncode, status='complete' if result.returncode == 0 else 'failed')
        if action in ('tests', 'gate'):
            report['output'] = (result.stdout + result.stderr).decode()
        else:
            report.update(stdout_bytes=len(result.stdout), stderr_bytes_withheld=len(result.stderr))
    except Exception as error:
        report.update(status='failed', exit_code=None, exception_type=type(error).__name__)
    report.update(elapsed_seconds=(time.monotonic_ns() - started) / 1e9, finished_at=now())
    output = ROOT / (identifier + '-action-' + action + '.json')
    save(output, report)
    print(json.dumps({'receipt': output.name, 'sha256': sha(output), 'status': report['status'],
                      'exit_code': report['exit_code'], 'elapsed_seconds': report['elapsed_seconds']}))
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('tests', 'gate', 'inputs', 'mission', 'readback', 'verify'))
    parser.add_argument('--internal', action='store_true')
    arguments = parser.parse_args()
    if arguments.internal:
        if arguments.action == 'tests':
            result = tests()
        elif arguments.action == 'gate':
            result = gate()
        elif arguments.action in ('inputs', 'readback'):
            from reuse import acquire
            result = acquire('inputs' if arguments.action == 'inputs' else 'independent-readback')
        elif arguments.action == 'verify':
            owner = load('verify', repair=True)
            result = owner.verify()
        else:
            raise ValueError('no internal inference route')
    else:
        result = run(arguments.action)
    raise SystemExit(result)