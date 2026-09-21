"""Independent post-mission source, replay/readback and process verification."""

from datetime import datetime, timezone
import json
import os
import time

from reuse import ROOT, WORKSPACE, PRIOR, ORIGINS, load, sha, receipts
from run import save


def verify():
    started = time.monotonic_ns()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'status': 'failed',
              'semantic_evaluation': 'Separate evaluator review required; structural checks are not mission acceptance'}
    try:
        admitted = [path for path in receipts('mission') if json.loads(path.read_text())['prompt_requests'] == 1]
        mission_path, = admitted
        paths = {'inputs': receipts('inputs')[-1], 'readback': receipts('independent-readback')[-1], 'mission': mission_path}
        records = {name: json.loads(path.read_text()) for name, path in paths.items()}
        report['artifacts'] = {name: {'path': path.name, 'sha256': sha(path)} for name, path in paths.items()}
        before, after, mission = records['inputs'], records['readback'], records['mission']
        for name, expected in ORIGINS.items():
            assert sha(PRIOR / name) == expected
        for path, expected in mission['pins'].items():
            from pathlib import Path
            assert sha(Path(path)) == expected
        assert mission['launcher_sha256'] == sha(ROOT / 'native.py')
        assert mission['oracle_sha256'] == ORIGINS['oracle.json']
        assert mission['prompt_requests'] == 1
        assert mission['selected_agent'] == 'local-dev-test-subject'
        assert mission['selected_model'] == 'gpt-6-astra' and mission['native_authenticated'] is True
        for item in mission['staged']:
            assert sha(ROOT / item['path']) == item['sha256']
        report['checks'].append('unchanged-pins-exact-staged-source-model-auth-one-prompt')
        assert before['status'] == after['status'] == 'complete'
        assert set(before['responses']) == set(after['responses'])
        for name, response in before['responses'].items():
            current = after['responses'][name]
            assert response['status'] == current['status'] == 200
            assert response['sha256'] == current['sha256'] and response['body'] == current['body']
        for record in (before, after):
            assert all(item['status'] == item['expected'] for item in record['refusals'])
        report['stable_response_count'] = len(after['responses'])
        report['checks'].append('pre-post-live-hashes-bodies-and-auth-partition-refusals')
        owner = load('live_inputs')
        manifest, documents = owner.load_package(WORKSPACE / 'template_apps/investigation_app/deploy/data/public-investigation/packages' / owner.PACKAGE_SHA256)
        events = [item for item in documents['cosmos'] if item['kind'] == 'event']
        for index, event in enumerate(events, 1):
            actual = after['responses'][f'event-{index}']['body'][0]
            assert all(actual.get(key) == value for key, value in event.items())
        for name, kind in [('cases', 'incident'), ('alarms', 'alarm')]:
            expected = next(item for item in documents['cosmos'] if item['kind'] == kind)
            actual = after['responses'][name]['body'][0]
            assert all(actual.get(key) == value for key, value in expected.items())
        report['checks'].append('complete-event-case-alarm-source-fields-match')
        vertices = {item['id']: item for item in documents['gremlin']['vertices']}
        edges = {item['id']: item for item in documents['gremlin']['edges']}
        seen_nodes, seen_edges = set(), set()
        membership = {event['resource_id'] for event in events}
        for name, response in after['responses'].items():
            if not name.startswith('graph-'):
                continue
            for node in response['body']['nodes']:
                expected = vertices[node['id']]
                assert node['label'] == expected['label']
                assert all(node['properties'].get(key) == value for key, value in expected['properties'].items())
                assert set(node['properties']['evidence_refs']) <= membership
                seen_nodes.add(node['id'])
            for edge in response['body']['edges']:
                expected = edges[edge['id']]
                assert (edge['from'], edge['to'], edge['label']) == (expected['from_id'], expected['to_id'], expected['label'])
                assert all(edge['properties'].get(key) == value for key, value in expected['properties'].items())
                assert set(edge['properties']['evidence_refs']) <= membership
                seen_edges.add(edge['id'])
        report['graph_coverage'] = {'nodes_checked': len(seen_nodes), 'source_nodes': len(vertices), 'edges_checked': len(seen_edges), 'source_edges': len(edges)}
        report['checks'].append('graph-source-provenance-endpoints-and-membership-match')
        report['independent_chronology'] = [
            {'resource_id': event['resource_id'], 'source_timestamp': event['timestamp'], 'fields': event['fields'],
             'entity_refs': event['entity_refs'], 'host': event['host'], 'label_status': event['label_status']}
            for event in sorted(events, key=lambda event: event['timestamp'])]
        report['final_readback'] = []
        for item in mission['finals']:
            path = ROOT / item['path']
            assert sha(path) == item['sha256']
            final = json.loads(path.read_text())
            report['final_readback'].append({'path': path.name, 'sha256': sha(path), 'content_bytes': len(final['content'].encode())})
        settlement = mission['settlement']
        assert settlement['process_settled']
        if settlement.get('pid'):
            try:
                os.kill(settlement['pid'], 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError('owned-pid-present')
        if settlement.get('owned_group'):
            try:
                os.killpg(settlement['owned_group'], 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError('owned-group-present')
        report['checks'].append('final-bytes-read-back-owned-pid-and-group-absent')
        report['status'] = 'verified'
    except Exception as error:
        report['failure'] = {'exception_type': type(error).__name__, 'raw_detail': 'withheld'}
    report['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    output = ROOT / (stamp + '-verification.json')
    save(output, report)
    print(json.dumps({'receipt': output.name, 'sha256': sha(output), 'status': report['status'], 'checks': report['checks']}))
    return 0 if report['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(verify())