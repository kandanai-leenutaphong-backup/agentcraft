"""Read back bounded primary evidence, protected pins and process settlement."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
WORKSPACE = ROOT.parents[5]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic_ns()
    start = json.loads((ROOT / 'start.json').read_text())
    for field in ('authority', 'prestate'):
        assert digest(PROJECT / start[field]['path']) == start[field]['sha256']
    constitution = PROJECT / 'constitution/constitution.yaml'
    assert digest(constitution) == 'efa3f7785478f6aa3a7ccd627d1a4aa85ee2da0fce367b571187241e6fe76d38'
    snapshot = PROJECT / 'records/v2/20260921T094557457189Z-v17-fulfilment-20260921-prestate/artifacts'
    assert digest(snapshot / 'constitution.yaml') == start['initial_constitution_sha256']
    assert digest(snapshot / '0000-README.md') == 'd28fc207e005334157f3d3b2ab8acf59200a8543fa5f93eb1a0f4232688c6516'
    current = yaml.safe_load(constitution.read_text())
    previous = yaml.safe_load((snapshot / 'constitution.yaml').read_text())
    assert current['revision'] == 11 and current['status'] == 'exploring'
    for field in ('metrics', 'primary_metric', 'dataset'):
        assert current[field] == previous[field]
    checks = []
    for command in ([sys.executable, '-B', str(WORKSPACE / '.github/skills/agentcraft-process/validate.py'), str(constitution)],
                    [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(ROOT), '-p', 'test_host_probe.py', '-v']):
        before = time.monotonic_ns()
        completed = subprocess.run(command, cwd=WORKSPACE, text=True, capture_output=True, timeout=30)
        checks.append({'argv': command, 'exit_code': completed.returncode,
                       'elapsed_seconds': (time.monotonic_ns() - before) / 1e9,
                       'output': completed.stdout + completed.stderr})
        assert completed.returncode == 0
    expected = {
        '20260921T101027225664Z-host-probe.json': 'a3aedd28d4c1679ace58b985365b7422248c7fb4ce6d5c42ecbab0a974ce4aeb',
        '20260921T101208859517Z-host-probe.json': 'a58074a8225f59f3da7cdc210e4a37b46b7f6bde39b332bf8f3809527ded7d1b',
        '20260921T101345074091Z-host-probe.json': 'b1e909141c6df13371028cb63ca1a5aa5ad9329ecb9b210648b76ca27e73feb6',
        '20260921T101418693145Z-host-probe.json': '52aca13e9dd30c15ac44a8d1c32a613723abb0b8f45b95d35bb73568b7cc7864',
    }
    probes = []
    for name, expected_digest in expected.items():
        assert digest(ROOT / name) == expected_digest
        probe = json.loads((ROOT / name).read_text())
        assert probe['inference_requests'] == 0
        assert {request['method'] for request in probe['requests']} <= {'initialize', 'session/new'}
        probes.append(probe)
    final = probes[-1]
    assert final['existing_github_auth']['authenticated'] is True
    assert final['responses'][-1]['current_model_metadata_only'] == 'gpt-6-astra'
    assert final['candidate_loaded_identity'] is None and final['inference_admitted'] is False
    assert digest(ROOT / 'host_probe.py') == final['probe_sha256']
    candidate = WORKSPACE / '.github/agents/local-dev-test-subject.agent.md'
    assert digest(candidate) == final['candidate_source']['sha256']
    for probe in probes:
        if probe.get('candidate_source'):
            assert Path(probe['candidate_source']['staged']).read_bytes() == candidate.read_bytes()
    process_list = subprocess.run(['ps', '-eo', 'args='], text=True, capture_output=True, check=True, timeout=5)
    owned_live = [line for line in process_list.stdout.splitlines()
                  if line.startswith('/home/hanchoong/.local/bin/copilot ') and str(ROOT) in line]
    assert not owned_live
    secret_shape_files = []
    metadata_text_files = 0
    for directory in ROOT.glob('*-metadata-state'):
        for path in directory.rglob('*'):
            if path.is_file() and path.suffix in ('.json', '.jsonl', '.yaml'):
                metadata_text_files += 1
                content = path.read_text()
                if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----', content):
                    secret_shape_files.append(str(path.relative_to(ROOT)))
    assert not secret_shape_files, 'Secret-shaped metadata: values withheld'
    files = [path for path in ROOT.iterdir() if path.is_file() and not path.name.startswith('verification')]
    files += [constitution, WORKSPACE / 'demonstration_project/README.md', candidate]
    endpoint = time.monotonic_ns()
    record = {'status': 'PASS-integrity-and-local-checks; host-inference-blocked',
              'finished_at': datetime.now(timezone.utc).isoformat(),
              'stage_timing': {'start_monotonic_ns': start['start_monotonic_ns'], 'endpoint_monotonic_ns': endpoint,
                               'elapsed_seconds': (endpoint - start['start_monotonic_ns']) / 1e9,
                               'scope': start['clock_scope'] + ' Endpoint before verification receipt write; archival excluded.'},
              'verification_elapsed_seconds': (endpoint - started) / 1e9,
              'checks': checks,
              'files': [{'path': str(path.relative_to(WORKSPACE)), 'sha256': digest(path)} for path in sorted(files)],
              'observed_counts': {'probe_attempts': len(probes), 'cli_metadata_processes': sum(bool(probe['requests']) for probe in probes),
                                  'acp_requests': sum(len(probe['requests']) for probe in probes),
                                  'inference_requests': sum(probe['inference_requests'] for probe in probes),
                                  'owned_live_cli_processes': len(owned_live)},
              'metadata_text_scan': {'files_checked': metadata_text_files, 'known_secret_shapes_found': len(secret_shape_files),
                                     'limits': 'Known token/private-key shapes only; not general secret certification; SQLite not inspected'},
              'actual_effective_effort': None, 'effort_reason': 'unsupported/unverified',
              'archival_request': 'Overseer-owned outcome checkpoint and post-change constitution/README snapshots',
              'restoration': 'not_verified; no restoration attempted',
              'settlement': 'No workers, all three native metadata processes exited; one failed probe launched none; no inference/cloud/app mutation'}
    path = ROOT / 'verification.json'
    if path.exists():
        path = ROOT / ('verification-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with path.open('x') as handle:
        json.dump(record, handle, indent=2)
        handle.write('\n')
    assert json.loads(path.read_text()) == record
    print(json.dumps({'status': record['status'], 'path': str(path), 'sha256': digest(path),
                      'stage_elapsed_seconds': record['stage_timing']['elapsed_seconds'],
                      'counts': record['observed_counts'],
                      'handoff_sha256': digest(ROOT / 'handoff.md')}, indent=2))


if __name__ == '__main__':
    main()