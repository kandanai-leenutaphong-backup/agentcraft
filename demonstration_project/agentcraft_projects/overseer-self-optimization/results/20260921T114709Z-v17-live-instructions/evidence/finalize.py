"""Retain measured primary handoff evidence without authoritative publication."""

import json
import os
import time

from reuse import ROOT, WORKSPACE, PROJECT, PINS, REPAIR_PINS, ORIGINS, pins, now, receipts, save, sha, stamp


def finalize():
    started, started_at, identifier = time.monotonic_ns(), now(), stamp()
    pins()
    mission_path, = receipts('mission')
    mission = json.loads(mission_path.read_text())
    assert mission['prompt_requests'] <= 1 and mission['owned_process_count'] <= 1
    assert mission['settlement']['process_settled'] and mission['callback_settlement']['outstanding_reads'] == 0
    for operation, key in ((os.kill, 'pid'), (os.killpg, 'owned_group')):
        value = mission['settlement'].get(key)
        if value:
            try:
                operation(value, 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError('owned-process-or-group-present')
    actions = [json.loads(path.read_text()) for path in sorted(ROOT.glob('*-action-*.json')) if not path.name.endswith('-started.json')]
    invoked, = [item for item in actions if item['action'] == 'mission']
    for name, expected in invoked['source_sha256'].items():
        assert sha(ROOT / name) == expected
    for item in mission['staged'] + mission['finals']:
        assert sha(ROOT / item['path']) == item['sha256']
    gate = json.loads((ROOT / 'rev12-gate.json').read_text())
    assert sha(WORKSPACE / 'demonstration_project/README.md') == gate['readme_sha256']
    files = []
    for path in sorted(ROOT.rglob('*')):
        if path.is_file():
            assert not path.is_symlink()
            files.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size})
    evaluation_paths = receipts('evaluation')
    evaluation = json.loads(evaluation_paths[-1].read_text()) if evaluation_paths else None
    report = {'objective': 'v17-fulfilment-20260921', 'stage': 'data-understanding', 'started_at': started_at,
              'status': 'settled', 'mission_status': mission['status'], 'fresh_prompts': mission['prompt_requests'],
              'owned_pid_and_group_absent': True, 'callback_reads_settled': True, 'files': files,
              'constitution': {'revision': 12, 'sha256': sha(PROJECT / 'constitution/constitution.yaml')},
              'readme_sha256': gate['readme_sha256'], 'pins': {str(path): value for path, value in PINS.items()},
              'reused_sources': {'repair': REPAIR_PINS, 'original': ORIGINS},
              'evaluation': {'path': evaluation_paths[-1].name, 'sha256': sha(evaluation_paths[-1])} if evaluation else None,
              'commands': actions,
              'timing': {'stage_start_utc': gate['stage_clock']['utc'], 'stage_start_monotonic_seconds': 351892.18,
                         'stage_to_handback_manifest_seconds': time.monotonic() - 351892.18,
                         'clock_precision_seconds': 0.01, 'archive_overhead_seconds': None,
                         'final_response_delivery_seconds': None, 'finalizer_seconds': (time.monotonic_ns() - started) / 1e9},
              'parent_actions_after_gate': ['Current-byte 18-fixture pass; independent signed preflight/refusals',
                                            'One native session/prompt with final-only structural capture',
                                            'Added independent transfer verifier during inference; syntax checked',
                                            'Diagnostics found no errors; read gate and prior finalizer',
                                            'Independent post-readback, source/graph verification, fixed-oracle review and handoff'],
              'failures_and_repairs': ['Initial gate failed missing editable signed_dev_access import; retained receipt; added existing explicit source path; same gate passed. No inference consumed.',
                                      'Architecture overview absent; no architectural mutation.'],
              'archival_request': 'Overseer dispatches archivist for rev12/source/outcome checkpoint and note_scribe for bounded findings; worker published neither.',
              'remaining_objective_gap': 'Fresh current-overseer comparisons and criteria freeze required. Current runtime direct-child/subordinate routing cannot supply comparison; no CLI or clone bypass. Stop supporting-only launches.',
              'capture_gaps': ['Individual initial tool-call times/counts incomplete; no complete transcript or private logs acquired',
                               'Parent effective effort, hidden provider retries/cost units and full archive overhead unknown',
                               'Byte-complete callback delivery does not prove semantic consumption or cryptographic host-loaded identity',
                               'No scored baseline, population/generalization or v1.7 claim; source v1.62 does not hot-reload parent v1.61',
                               'Initial uninvoked draft bytes not all snapshotted; invoked runtime sources retained unchanged',
                               'Restoration not attempted or verified; existing prestate is recoverable reference only'],
              'finished_at': now()}
    output = ROOT / (identifier + '-manifest.json')
    save(output, report)
    for item in files:
        path = ROOT / item['path']
        assert sha(path) == item['sha256'] and path.stat().st_size == item['bytes']
    print(json.dumps({'manifest': output.name, 'sha256': sha(output), 'files': len(files),
                      'status': report['status'], 'timing': report['timing']}))


if __name__ == '__main__':
    finalize()