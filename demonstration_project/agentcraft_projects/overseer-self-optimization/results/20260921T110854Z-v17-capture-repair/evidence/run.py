"""Measured, immutable action receipts; one inference only, no automatic retry."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

from reuse import ROOT, WORKSPACE, PRIOR, ORIGINS, sha


def save(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    assert json.loads(path.read_text()) == value


def run(action):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    started = time.monotonic_ns()
    python = sys.executable
    commands = {
        'tests': [python, '-B', '-m', 'unittest', 'discover', '-s', str(ROOT), '-p', 'test_capture.py', '-v'],
        'inputs': ['/tmp/agentcraft-investigation-browser-env/bin/python', '-B', str(ROOT / 'reuse.py'), 'inputs'],
        'mission': [python, '-B', str(ROOT / 'native.py')],
        'readback': ['/tmp/agentcraft-investigation-browser-env/bin/python', '-B', str(ROOT / 'reuse.py'), 'independent-readback'],
        'verify': ['/tmp/agentcraft-investigation-browser-env/bin/python', '-B', str(ROOT / 'verify.py')],
    }
    report = {'action': action, 'command': commands[action], 'started_at': datetime.now(timezone.utc).isoformat(),
              'monotonic_start_ns': started, 'timeout_seconds': 1100 if action == 'mission' else 360,
              'status': 'started', 'source_sha256': {path.name: sha(path) for path in ROOT.glob('*.py')}}
    if action == 'mission':
        assert not (ROOT / 'one-inference-admitted.json').exists()
        passed = [json.loads(path.read_text()) for path in ROOT.glob('*-action-tests.json')]
        assert any(item['exit_code'] == 0 and item['source_sha256'] == report['source_sha256'] for item in passed)
        assert sha(PRIOR / 'oracle.json') == ORIGINS['oracle.json']
        snapshots = ROOT / (stamp + '-invoked-source')
        snapshots.mkdir()
        for source in list(ROOT.glob('*.py')) + [PRIOR / 'oracle.json']:
            target = snapshots / (source.name + '.snapshot')
            with target.open('xb') as handle:
                handle.write(source.read_bytes())
            target.chmod(0o444)
        report['snapshots'] = str(snapshots.relative_to(ROOT))
    save(ROOT / (stamp + '-action-' + action + '-started.json'), report)
    try:
        result = subprocess.run(commands[action], cwd=WORKSPACE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=report['timeout_seconds'])
        report['exit_code'] = result.returncode
        report['status'] = 'complete' if result.returncode == 0 else 'failed'
        if action == 'tests':
            report['test_output'] = (result.stdout + result.stderr).decode()
        else:
            report['stderr_bytes_withheld'] = len(result.stderr)
            report['stdout_bytes'] = len(result.stdout)
    except Exception as error:
        report.update(status='failed', exit_code=None, exception_type=type(error).__name__)
    report['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    output = ROOT / (stamp + '-action-' + action + '.json')
    save(output, report)
    print(json.dumps({'receipt': output.name, 'sha256': sha(output), 'status': report['status'],
                      'exit_code': report['exit_code'], 'elapsed_seconds': report['elapsed_seconds']}))
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('tests', 'inputs', 'mission', 'readback', 'verify'))
    raise SystemExit(run(parser.parse_args().action))