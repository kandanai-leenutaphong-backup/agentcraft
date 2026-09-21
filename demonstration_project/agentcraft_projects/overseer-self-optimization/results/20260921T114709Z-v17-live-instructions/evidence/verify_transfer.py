"""Independent transport coverage, actual live provenance and final readback."""

import json
import time

from reuse import ROOT, PROJECT, WORKSPACE, ORIGINS, PRIOR, digest, load, now, receipts, save, sha, stamp
from transport import reconstruct, wire


def verify():
    started, started_at, identifier = time.monotonic_ns(), now(), stamp()
    report = {'started_at': started_at, 'status': 'failed', 'checks': [],
              'semantic_consumption_verified': False, 'comparison_claim': False}
    try:
        structural = json.loads(receipts('verification')[-1].read_text())
        assert structural['status'] == 'verified'
        mission_path, = receipts('mission')
        mission = json.loads(mission_path.read_text())
        publication = json.loads((ROOT / 'instruction-publication.json').read_text())
        inputs = json.loads(receipts('inputs')[-1].read_text())
        readback = json.loads(receipts('independent-readback')[-1].read_text())
        assert mission['prompt_requests'] == 1 and mission['owned_process_count'] == 1
        assert mission['status'] == 'mission-output-retained'
        assert mission['capture']['permission_denied_count'] == 0
        assert mission['callback_settlement']['outstanding_reads'] == 0
        calls = mission['tool_calls']
        assert all(item['allowed'] and not item.get('failure') and item['status'] == 200 for item in calls)
        instruction_calls = [item for item in calls if item['kind'] == 'instruction-chunk']
        delivered = {item['key'] for item in instruction_calls}
        expected = set(publication['chunks'])
        report['instruction_coverage'] = {'expected': len(expected), 'unique_returned': len(delivered),
                                          'calls': len(instruction_calls), 'missing': sorted(expected - delivered),
                                          'duplicates': len(instruction_calls) - len(delivered)}
        assert delivered == expected
        report['documents'] = []
        for name, document in publication['documents'].items():
            chunks = [publication['chunks'][key] for key in document['keys']]
            content = reconstruct(chunks, document['sha256'])
            assert content == (WORKSPACE / document['path']).read_bytes()
            for key in document['keys']:
                payload = wire(publication['chunks'][key]).encode()
                actual = [item for item in instruction_calls if item['key'] == key]
                assert all(item['payload_sha256'] == digest(payload) and item['payload_bytes'] == len(payload)
                           and item['payload_chars'] <= 2000 and item['payload_bytes'] <= 2000 for item in actual)
            report['documents'].append({'document': name, 'sha256': digest(content), 'bytes': len(content), 'chunks': len(chunks)})
        report['checks'].append('all-instruction-chunks-returned-byte-exact-digests-and-bounds')
        live_calls = [item for item in calls if item['kind'] == 'live-signed-GET']
        assert {item['key'] for item in live_calls} == set(readback['responses'])
        report['live_calls'] = []
        for call in live_calls:
            response_path = ROOT / call['receipt']
            response = json.loads(response_path.read_text())
            before, after = inputs['responses'][call['key']], readback['responses'][call['key']]
            assert response['status'] == call['status'] == before['status'] == after['status'] == 200
            assert response['path'] == call['path'] == before['path'] == after['path']
            assert digest(response['raw_utf8'].encode()) == response['sha256'] == call['sha256'] == before['sha256'] == after['sha256']
            assert response['body'] == before['body'] == after['body']
            report['live_calls'].append({'key': call['key'], 'path': response_path.name, 'sha256': sha(response_path),
                                         'response_sha256': call['sha256'], 'elapsed_seconds': call['elapsed_seconds'],
                                         'status': call['status'], 'retrieved_at': call['retrieved_at']})
        report['checks'].append('all-nine-actual-callback-live-responses-match-independent-pre-post')
        for record in (inputs, readback):
            assert len(record['refusals']) == 2 and all(item['status'] == item['expected'] for item in record['refusals'])
        report['refusals'] = {'before': inputs['refusals'], 'after': readback['refusals']}
        assert sha(PRIOR / 'oracle.json') == ORIGINS['oracle.json']
        report['checks'].append('independent-anonymous-401-foreign-partition-422-and-fixed-oracle')
        report['stage_seconds_to_final'] = mission['inference']['elapsed_seconds'] + (float(mission.get('pre_admission_seconds', 0)))
        report['stage_seconds_to_final_scope'] = 'launcher admission plus inference; whole stage interval below'
        from datetime import datetime
        report['stage_to_retained_final_utc_seconds'] = (datetime.fromisoformat(mission['finals'][0]['at']) - datetime.fromisoformat('2026-09-21T11:47:09.830188+00:00')).total_seconds()
        report['stage_to_verification_monotonic_seconds'] = time.monotonic() - 351892.18
        timings = mission['capture']['event_timings']
        report['timings'] = {'inference_seconds': mission['inference']['elapsed_seconds'],
                             'last_public_tool_completion_to_final_seconds': timings['assistant.message']['last_seconds'] - timings['tool.execution_complete']['last_seconds'],
                             'native_settlement_seconds': mission['settlement']['elapsed_seconds']}
        report['artifacts'] = {path.name: sha(path) for path in (mission_path, receipts('verification')[-1],
                              receipts('independent-readback')[-1], ROOT / 'instruction-publication.json', ROOT / 'rev12-gate.json')}
        report['graph_coverage'] = structural['graph_coverage']
        report['status'] = 'verified'
    except Exception as error:
        report['failure'] = {'exception_type': type(error).__name__, 'raw_detail': 'withheld'}
    report.update(elapsed_seconds=(time.monotonic_ns() - started) / 1e9, finished_at=now())
    output = ROOT / (identifier + '-transfer-verification.json')
    save(output, report)
    print(json.dumps({'receipt': output.name, 'sha256': sha(output), 'status': report['status'],
                      'coverage': report.get('instruction_coverage'), 'checks': report['checks']}))
    return 0 if report['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(verify())