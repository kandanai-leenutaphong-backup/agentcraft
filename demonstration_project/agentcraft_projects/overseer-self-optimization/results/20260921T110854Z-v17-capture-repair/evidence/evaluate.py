"""Independent exact-field checks plus attributed qualitative oracle review."""

from datetime import datetime, timezone
from decimal import Decimal
import json
import time

from reuse import ROOT, PRIOR, ORIGINS, receipts, sha
from run import save


def evaluate():
    started = time.monotonic_ns()
    started_at = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    verification_path = receipts('verification')[-1]
    verification = json.loads(verification_path.read_text())
    assert verification['status'] == 'verified'
    mission_path = ROOT / verification['artifacts']['mission']['path']
    mission = json.loads(mission_path.read_text())
    final_path = ROOT / mission['finals'][0]['path']
    wrapper = json.loads(final_path.read_text())
    candidate = json.loads(wrapper['content'])
    readback_path = ROOT / verification['artifacts']['readback']['path']
    readback = json.loads(readback_path.read_text())
    inputs_path = ROOT / verification['artifacts']['inputs']['path']
    inputs = json.loads(inputs_path.read_text())
    responses = readback['responses']
    oracle_path = PRIOR / 'oracle.json'
    assert sha(oracle_path) == ORIGINS['oracle.json']
    oracle = json.loads(oracle_path.read_text())
    checks = []

    def check(label, observed, expected):
        item = {'claim': label, 'passed': observed == expected}
        if not item['passed']:
            item.update(candidate=observed, expected=expected)
        checks.append(item)

    observed = candidate['observations']
    chronology = observed['chronology']
    events = {key: responses[key]['body'][0] for key in ('event-1', 'event-2')}
    ordered = sorted(events, key=lambda key: events[key]['timestamp'])
    check('chronology.order', [item['key'] for item in chronology], ordered)
    for item in chronology:
        event = events[item['key']]
        prefix = item['key'] + '.'
        for field in ('id', 'event_record_id', 'ordinal', 'timestamp', 'raw_sha256'):
            check(prefix + field, item[field], event[field])
        for field in ('UtcTime', 'ProcessId', 'ProcessGuid', 'CommandLine'):
            check(prefix + field, item[field], event['fields'][field])
        check(prefix + 'process_entity', item['process_entity'], event['entity_refs']['process'])
        check(prefix + 'source_byte_offset', item['source_byte_offset'], event['byte_offset'])
        check(prefix + 'source_byte_length', item['source_byte_length'], event['byte_length'])
    first, second = [events[key] for key in ordered]
    source_gap = Decimal(second['timestamp'][17:-1]) - Decimal(first['timestamp'][17:-1]) + Decimal(60)
    embedded_gap = (datetime.fromisoformat(second['fields']['UtcTime']) - datetime.fromisoformat(first['fields']['UtcTime'])).total_seconds()
    check('source_timestamp_gap_seconds', Decimal(str(observed['ordering']['calculated_timestamp_gap_seconds'])), source_gap)
    check('embedded_timestamp_gap_seconds', observed['ordering']['calculated_UtcTime_gap_seconds'], embedded_gap)
    common = observed['common_fields']
    aliases = {'host_entity': 'host', 'user_entity': 'user', 'parent_entity': 'parent_process'}
    for key, value in common.items():
        for event_key, event in events.items():
            if key in aliases:
                expected = event['entity_refs'][aliases[key]]
            elif key == 'image_sha256_from_Hashes':
                expected = dict(part.split('=', 1) for part in event['fields']['Hashes'].split(','))['SHA256']
            else:
                expected = event.get(key, event['fields'].get(key))
            check(event_key + '.common.' + key, value, expected)
    alarm = responses['alarms']['body'][0]
    for key in ('id', 'incident_id', 'derived', 'rule_version', 'rule_description', 'classification'):
        check('alarm.' + key, observed['alarm'][key], alarm[key])
    check('alarm.resource_membership', sorted(events[key]['resource_id'] for key in observed['alarm']['referenced_events']), sorted(alarm['event_refs']))
    source = candidate['evidence']['telemetry_source']
    for key, value in source.items():
        expected = first['source']['sha256'] if key == 'source_sha256' else first.get(key, first['source'].get(key))
        check('source.' + key, value, expected)
    check('reported_callback_keys', [item['key'] for batch in candidate['commands']['argument_batches'] for item in batch], [item['key'] for item in mission['tool_calls']])
    check('all_candidate_callbacks_allowed', all(item['allowed'] for item in mission['tool_calls']), True)
    check('no_candidate_permission_requests', mission['capture']['permission_denied_count'], 0)
    check('public_emulation', responses['cases']['body'][0]['ground_truth_kind'], 'emulation_scenario')
    check('mitre_advisory_only', responses['technique']['body']['advisory_only'], True)
    nodes, edges = {}, {}
    for key, response in responses.items():
        if key.startswith('graph-'):
            graph = response['body']
            check(key + '.historical_replay', graph['historical_replay'], True)
            check(key + '.depth', graph['depth'], 1)
            check(key + '.empty_window', [graph['window']['start'], graph['window']['end']], ['', ''])
            nodes.update({node['id']: node for node in graph['nodes']})
            edges.update({edge['id']: edge for edge in graph['edges']})
    graph_claims = observed['graph']
    for role, entity in [('host', common['host_entity']), ('identity', common['user_entity']), ('parent', common['parent_entity'])]:
        check('graph.' + role + '.event_count', graph_claims['event_counts'][role], nodes[entity]['event_count'])
    for event in events.values():
        process = event['entity_refs']['process']
        check('graph.' + process + '.event_count', graph_claims['event_counts']['each_child'], nodes[process]['event_count'])
        for label, origin, target in [('PARENT_OF', common['parent_entity'], process), ('PROCESS_ON_HOST', process, common['host_entity']), ('EXECUTED_AS', process, common['user_entity'])]:
            check('graph.' + process + '.' + label, any(edge['label'] == label and edge['from'] == origin and edge['to'] == target for edge in edges.values()), True)
    check('graph.parent_observation_roles', graph_claims['parent_observation_roles'], nodes[common['parent_entity']]['properties']['observation_roles'])
    domain = nodes[graph_claims['domain_entity']]
    check('graph.domain_kind', graph_claims['domain_kind'], domain['properties']['domain_kind'])
    check('graph.membership', any(edge['label'] == 'MEMBER_OF_DOMAIN' and edge['from'] == common['user_entity'] and edge['to'] == domain['id'] for edge in edges.values()), True)
    failures = [item for item in checks if not item['passed']]
    intervals = mission['capture']['event_timings']
    last_tool = intervals['tool.execution_complete']['last_seconds']
    final_at = intervals['assistant.message']['last_seconds']
    delta_first = intervals['assistant.message_delta']['first_seconds']
    documents = {key: value for key, value in inputs['responses'].items()}
    for item in mission['staged']:
        path = ROOT / item['path']
        key = str(path.relative_to(ROOT / path.relative_to(ROOT).parts[0]))
        documents[key] = {'path': key, 'sha256': sha(path), 'content': path.read_text()}
    payload_bytes = {key: len(json.dumps(value).encode()) for key, value in documents.items()}
    report = {
        'started_at': started_at,
        'objective': 'v17-fulfilment-20260921', 'stage': 'data-understanding',
        'evaluator': 'agentcraft-orchestrator independent source checks plus explicit qualitative review; candidate has no evaluator access',
        'evaluator_sha256': sha(ROOT / 'evaluate.py'), 'oracle_sha256': sha(oracle_path),
        'artifacts': {path.name: sha(path) for path in (verification_path, mission_path, final_path, readback_path, inputs_path)},
        'field_checks': checks, 'field_check_count': len(checks), 'incorrect_claims': failures,
        'criteria': [
            {'criterion': oracle['criteria'][0], 'outcome': 'satisfied' if not failures else 'review-required', 'evidence': 'Both timestamps, embedded UtcTime, ordinals, source offsets and calculated gaps independently compared.'},
            {'criterion': oracle['criteria'][1], 'outcome': 'satisfied', 'evidence': 'Exact event IDs, keys, source ordinals and partition identify both resources unambiguously; fields and alarm membership checked. Canonical event:// URIs not repeated verbatim.'},
            {'criterion': oracle['criteria'][2], 'outcome': 'satisfied', 'evidence': 'Exact entities and graph edges checked. Parent creation/lifetime explicitly unobserved; sibling processes correctly distinguished.'},
            {'criterion': oracle['criteria'][3], 'outcome': 'satisfied', 'evidence': 'Explicit unlabelled emulation, advisory-only ATT&CK, no compromise claim; retry/success inference bounded.'},
            {'criterion': oracle['criteria'][4], 'outcome': 'satisfied', 'evidence': 'Proposed bounded host/time/ProcessGuid EventID 7/11/1 evidence acquisition, not executed; missing evidence not treated as absence.'},
            {'criterion': oracle['criteria'][5], 'outcome': 'satisfied', 'evidence': 'Pre/post 401 and 422; fixture reader/permission denials; actual callbacks only published keys. Host restrictions are not OS sandbox attestation.'},
            {'criterion': oracle['criteria'][6], 'outcome': 'satisfied' if not failures else 'review-required', 'evidence': 'Final hash read back, all nine live responses stable, source and graph checked. Incorrect/missing claims retained below.'},
        ],
        'mission_only_qualitative_outcome': 'supported-with-instruction-delivery-gap' if not failures else 'not-accepted-field-mismatch',
        'full_instruction_consumption_verified': False,
        'missing_or_unverified': [
            'Candidate reports constitution/process truncated to previews and no range reader. Full callback payload construction is reproducible; actual model-visible truncation is self-report, not independently attested.',
            'Canonical event resource URIs omitted verbatim; exact event IDs, keys, source ordinals and partition permit unambiguous mapping.',
            'Candidate reports multi_tool_use.parallel executor; only the 12 read_public invocations are independently observed.',
            'No population, production, generalized quality, direct live candidate-tool acceptance or comparative v1.7 evidence.',
        ],
        'bottleneck': {'last_tool_completion_to_final_seconds': final_at - last_tool,
                       'last_tool_completion_to_first_public_message_delta_seconds': delta_first - last_tool,
                       'first_public_message_delta_to_final_seconds': final_at - delta_first,
                       'inference_seconds': mission['inference']['elapsed_seconds'],
                       'interpretation': 'Post-retrieval interval dominates this run. Event timing only, no private reasoning or causal attribution; message delta phase/content not retained.',
                       'reconstructed_callback_payload_bytes': payload_bytes,
                       'payload_limit': 'Exact JSON serialization from pinned public inputs, not attestation of model-visible bytes'},
        'smallest_next_delta': {'owner': 'read_public input publication', 'change': 'Publish deterministic size-bounded instruction chunk keys with whole-document SHA-256, chunk index/count and byte-complete reconstruction; no arbitrary path/range access or candidate-role change.',
                               'reason': 'Final explicitly reports unreadable full constitution/process, and current key-only callback offers no bounded recovery.',
                               'next_comparison': 'Fresh separately authorized trial; hold candidate/model/mission/oracle fixed. Verify all instruction chunks consumed and measure post-retrieval time without predicting improvement.'},
        'capture_hypothesis': 'Repaired collector retained explicit public final before idle. Prior discarded content remains unknown; cannot prove prior timeout was solely lost-final capture.',
        'settlement': mission['settlement'], 'comparison_claim': False,
        'elapsed_seconds': (time.monotonic_ns() - started) / 1e9,
        'finished_at': datetime.now(timezone.utc).isoformat(),
    }
    output = ROOT / (stamp + '-evaluation.json')
    save(output, report)
    print(json.dumps({'receipt': output.name, 'sha256': sha(output), 'field_check_count': len(checks),
                      'incorrect_claims': failures, 'outcome': report['mission_only_qualitative_outcome'],
                      'bottleneck': {key: value for key, value in report['bottleneck'].items() if key != 'reconstructed_callback_payload_bytes'}}))
    return 0 if not failures else 2


if __name__ == '__main__':
    raise SystemExit(evaluate())