"""Read back assigned evidence, immutable invocation and settled owned processes."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from reuse import ROOT, PRIOR, ORIGINS, receipts, sha
from run import save


def finalize():
    started = time.monotonic_ns()
    started_at = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    evaluation_path = receipts('evaluation')[-1]
    evaluation = json.loads(evaluation_path.read_text())
    assert not evaluation['incorrect_claims']
    missions = [json.loads(path.read_text()) for path in receipts('mission')]
    admitted = [item for item in missions if item['prompt_requests'] == 1]
    assert len(admitted) == 1
    mission = admitted[0]
    assert mission['status'] == 'mission-output-retained'
    for path, expected in mission['pins'].items():
        assert sha(Path(path)) == expected
    for name, expected in ORIGINS.items():
        assert sha(PRIOR / name) == expected
    actions = [json.loads(path.read_text()) for path in sorted(ROOT.glob('*-action-*.json')) if not path.name.endswith('-started.json')]
    invoked = next(item for item in actions if item['action'] == 'mission' and item['exit_code'] == 0)
    for name, expected in invoked['source_sha256'].items():
        assert sha(ROOT / name) == expected
        assert sha(ROOT / invoked['snapshots'] / (name + '.snapshot')) == expected
    for item in mission['staged']:
        assert sha(ROOT / item['path']) == item['sha256']
    for item in mission['finals']:
        assert sha(ROOT / item['path']) == item['sha256']
    for operation, identifier in ((os.kill, mission['settlement']['pid']), (os.killpg, mission['settlement']['owned_group'])):
        try:
            operation(identifier, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError('owned-process-or-group-remains')
    files = []
    for path in sorted(ROOT.rglob('*')):
        if path.is_file():
            assert not path.is_symlink()
            files.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size})
    report = {'objective': 'v17-fulfilment-20260921', 'status': 'complete', 'stage': 'data-understanding',
              'started_at': started_at, 'evaluation': {'path': evaluation_path.name, 'sha256': sha(evaluation_path)},
              'mission_outcome': evaluation['mission_only_qualitative_outcome'], 'fresh_prompts': 1,
              'pre_admission_failed_launches': sum(item['prompt_requests'] == 0 for item in missions),
              'owned_pid_and_group_absent': True, 'files': files,
              'commands': [{key: item.get(key) for key in ('action', 'command', 'status', 'exit_code', 'started_at', 'finished_at', 'elapsed_seconds', 'stderr_bytes_withheld')} for item in actions],
              'archival_request': 'Overseer dispatches archivist and note_scribe; no authoritative publication here',
              'capture_gaps': ['Whole-task start/duration, complete parent action timestamps and runtime effort unverified',
                               'No private host state, message-delta content, raw errors or unknown event content saved',
                               'Model-visible instruction truncation reported by candidate, not independently attested',
                               'Evaluator and finalizer execution timings separate from candidate inference; no comparative claim'],
              'elapsed_seconds': (time.monotonic_ns() - started) / 1e9, 'finished_at': datetime.now(timezone.utc).isoformat()}
    output = ROOT / (stamp + '-manifest.json')
    save(output, report)
    print(json.dumps({'manifest': output.name, 'sha256': sha(output), 'status': report['status'],
                      'evaluation': report['evaluation'], 'files': len(files), 'owned_pid_and_group_absent': True}))


if __name__ == '__main__':
    finalize()