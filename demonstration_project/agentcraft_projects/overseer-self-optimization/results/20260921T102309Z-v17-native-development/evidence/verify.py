"""Independent source/readback and settled failed-mission verification; no inference."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from live_inputs import ROOT, WORKSPACE, load_package, PACKAGE_SHA256, save, sha
from native import PINS


def verify():
    started = time.monotonic_ns()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    inputs_path = ROOT / '20260921T102610719813Z-inputs.json'
    readback_path = ROOT / '20260921T103925446797Z-independent-readback.json'
    mission_path = ROOT / '20260921T103242004052Z-mission.json'
    inputs = json.loads(inputs_path.read_text())
    readback = json.loads(readback_path.read_text())
    mission = json.loads(mission_path.read_text())
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'checking',
              'mission_outcome': 'failed-timeout-no-final', 'failures': [], 'checks': [],
              'candidate_claims': {'incorrect': [], 'missing': 'Entire final answer absent; chronology, explanation, causal restraint and next steps not assessable',
                                   'quality_accepted': False},
              'artifacts': {path.name: sha(path.read_bytes()) for path in (inputs_path, readback_path, mission_path)}}
    try:
        for path, expected in PINS.items():
            assert sha(path.read_bytes()) == expected
        report['checks'].append('source-constitution-authority-prestate-cli-pins-unchanged')
        assert mission['prompt_requests'] == 1 and mission['selected_agent'] == 'local-dev-test-subject'
        assert mission['selected_model'] == 'gpt-6-astra' and mission['native_authenticated'] is True
        assert mission['status'] == 'failed' and 'final' not in mission
        assert mission['oracle_sha256'] == sha((ROOT / 'oracle.json').read_bytes())
        assert mission['launcher_sha256'] == sha((ROOT / 'native.py').read_bytes())
        snapshot = ROOT / 'native-invoked.py.snapshot'
        if not snapshot.exists():
            with snapshot.open('xb') as handle:
                handle.write((ROOT / 'native.py').read_bytes())
            snapshot.chmod(0o444)
        assert sha(snapshot.read_bytes()) == mission['launcher_sha256']
        report['checks'].append('exact-invoked-launcher-snapshot-and-one-prompt')
        assert inputs['status'] == readback['status'] == 'complete'
        assert set(inputs['responses']) == set(readback['responses'])
        report['stable_responses'] = []
        for name, earlier in inputs['responses'].items():
            current = readback['responses'][name]
            assert earlier['status'] == current['status'] == 200
            assert earlier['sha256'] == current['sha256']
            assert earlier['body'] == current['body']
            report['stable_responses'].append(name)
        assert all(item['status'] == item['expected'] for item in readback['refusals'])
        report['checks'].append('nine-live-response-hashes-and-semantics-stable-plus-two-refusals')
        package = WORKSPACE / 'template_apps/investigation_app/deploy/data/public-investigation/packages' / PACKAGE_SHA256
        manifest, documents = load_package(package)
        events = [item for item in documents['cosmos'] if item['kind'] == 'event']
        membership = {event['resource_id'] for event in events}
        for index, event in enumerate(events, 1):
            actual = readback['responses'][f'event-{index}']['body'][0]
            assert all(actual.get(key) == value for key, value in event.items())
        for name, kind in [('cases', 'incident'), ('alarms', 'alarm')]:
            expected = next(item for item in documents['cosmos'] if item['kind'] == kind)
            actual = readback['responses'][name]['body'][0]
            assert all(actual.get(key) == value for key, value in expected.items())
        report['checks'].append('all-event-case-alarm-source-fields-match-current-service')
        vertices = {item['id']: item for item in documents['gremlin']['vertices']}
        edges = {item['id']: item for item in documents['gremlin']['edges']}
        seen_nodes, seen_edges = set(), set()
        for name, response in readback['responses'].items():
            if not name.startswith('graph-'):
                continue
            graph = response['body']
            for node in graph['nodes']:
                expected = vertices[node['id']]
                assert node['label'] == expected['label']
                for key, value in expected['properties'].items():
                    assert node['properties'].get(key) == value
                assert set(node['properties']['evidence_refs']) <= membership
                seen_nodes.add(node['id'])
            for edge in graph['edges']:
                expected = edges[edge['id']]
                assert (edge['from'], edge['to'], edge['label']) == (expected['from_id'], expected['to_id'], expected['label'])
                for key, value in expected['properties'].items():
                    assert edge['properties'].get(key) == value
                assert set(edge['properties']['evidence_refs']) <= membership
                seen_edges.add(edge['id'])
        report['graph_coverage'] = {'nodes_checked': len(seen_nodes), 'source_nodes': len(vertices),
                                    'edges_checked': len(seen_edges), 'source_edges': len(edges)}
        report['checks'].append('graph-node-edge-source-provenance-endpoints-and-event-membership-match')
        report['independent_chronology_not_candidate_output'] = [
            {'resource_id': event['resource_id'], 'source_timestamp': event['timestamp'],
             'embedded_UtcTime': event['fields']['UtcTime'], 'ProcessId': event['fields']['ProcessId'],
             'CommandLine': event['fields']['CommandLine'], 'host': event['host'],
             'User': event['fields']['User'], 'parent_reference': event['entity_refs']['parent_process'],
             'label_status': event['label_status']}
            for event in sorted(events, key=lambda event: event['timestamp'])]
        lingering = []
        for identifier in mission['observed_child_pids']:
            try:
                os.kill(identifier, 0)
                lingering.append(identifier)
            except ProcessLookupError:
                pass
        assert not lingering
        report['settlement'] = {'owned_pids_absent': mission['observed_child_pids'],
                                 'prior_forced_kills': mission['forced_child_kills'],
                                 'process_settled': True, 'other_existing_hosts': 'untouched',
                                 'restoration': 'not needed for unchanged canonical sources; not tested'}
        suite = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(ROOT), '-p', 'test_*.py', '-v'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        report['focused_tests'] = {'exit_code': suite.returncode, 'output': (suite.stdout + suite.stderr).decode()}
        assert suite.returncode == 0
        report['status'] = 'verified-failed-mission'
    except Exception as error:
        report['status'] = 'verification-failed'
        report['failures'].append({'exception_type': type(error).__name__})
    report['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    output = ROOT / (stamp + '-verification.json')
    save(output, report)
    print(json.dumps({'path': str(output), 'sha256': sha(output.read_bytes()), 'status': report['status'],
                      'checks': report['checks'], 'failures': report['failures']}))
    return 0 if report['status'] == 'verified-failed-mission' else 2


if __name__ == '__main__':
    raise SystemExit(verify())