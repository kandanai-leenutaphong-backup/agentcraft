"""Prior exact-field method adapted to final JSON shape; fixed qualitative oracle."""

from datetime import datetime
from decimal import Decimal
import json
import time

from reuse import ROOT, PRIOR, ORIGINS, REPAIR_PINS, now, receipts, save, sha, stamp


def evaluate():
    started, started_at, identifier = time.monotonic_ns(), now(), stamp()
    transfer_path = receipts('transfer-verification')[-1]
    transfer = json.loads(transfer_path.read_text())
    assert transfer['status'] == 'verified'
    mission_path, = receipts('mission')
    mission = json.loads(mission_path.read_text())
    final_path = ROOT / mission['finals'][0]['path']
    assert sha(final_path) == mission['finals'][0]['sha256']
    candidate = json.loads(json.loads(final_path.read_text())['content'])
    readback_path = receipts('independent-readback')[-1]
    responses = json.loads(readback_path.read_text())['responses']
    assert sha(PRIOR / 'oracle.json') == ORIGINS['oracle.json']
    oracle = json.loads((PRIOR / 'oracle.json').read_text())
    checks = []

    def check(label, actual, expected):
        item = {'claim': label, 'passed': actual == expected}
        if not item['passed']:
            item.update(candidate=actual, expected=expected)
        checks.append(item)

    observed = candidate['observations']
    events = {key: responses[key]['body'][0] for key in ('event-1', 'event-2')}
    ordered = sorted(events, key=lambda key: events[key]['timestamp'])
    chronology = observed['chronology']
    check('chronology.order', [item['key'] for item in chronology], ordered)
    aliases = {'source_ordinal': 'ordinal', 'source_byte_offset': 'byte_offset', 'source_byte_length': 'byte_length'}
    for item in chronology:
        event = events[item['key']]
        for field in ('id', 'resource_id', 'event_record_id', 'timestamp', 'raw_sha256', 'source_ordinal', 'source_byte_offset', 'source_byte_length'):
            check(item['key'] + '.' + field, item[field], event[aliases.get(field, field)])
        for field in ('ProcessId', 'ProcessGuid', 'CommandLine'):
            check(item['key'] + '.' + field, item[field], event['fields'][field])
        check(item['key'] + '.UtcTime', item['fields.UtcTime'], event['fields']['UtcTime'])
        for field, value in observed['shared_event_fields'].items():
            check(item['key'] + '.shared.' + field, value, event.get(field, event['fields'].get(field)))
        check(item['key'] + '.unlabelled', event['label_status'], 'unlabelled')
    first, second = [events[key] for key in ordered]
    base_first = datetime.fromisoformat(first['timestamp'][:19])
    base_second = datetime.fromisoformat(second['timestamp'][:19])
    gap = Decimal(int((base_second - base_first).total_seconds())) + Decimal('0.' + second['timestamp'][20:-1]) - Decimal('0.' + first['timestamp'][20:-1])
    check('source_timestamp_gap_seconds', Decimal(str(observed['time_interpretation']['timestamp_gap_seconds'])), gap)
    check('embedded_timestamp_gap_seconds', observed['time_interpretation']['fields_UtcTime_gap_seconds'],
          (datetime.fromisoformat(second['fields']['UtcTime']) - datetime.fromisoformat(first['fields']['UtcTime'])).total_seconds())
    case, alarm, technique = responses['cases']['body'][0], responses['alarms']['body'][0], responses['technique']['body']
    check('case.id', observed['case_id'], case['id'])
    check('alarm.id', observed['alarm_id'], alarm['id'])
    check('case.alarm_refs', case['alarm_refs'], [observed['alarm_id']])
    check('alarm.incident_id', alarm['incident_id'], observed['case_id'])
    check('case.emulation', case['ground_truth_kind'], 'emulation_scenario')
    check('case.derived', case['derived'], True)
    check('alarm.derived', alarm['derived'], True)
    for document in (case, alarm):
        check(document['kind'] + '.event_membership', sorted(document['event_refs']), sorted(item['resource_id'] for item in chronology))
    for field in ('rule_version', 'rule_description', 'classification'):
        check('alarm.' + field, observed['alarm_explanation'][field], alarm[field])
    check('hosts', observed['affected_hosts_observed'], sorted({event['host'] for event in events.values()}))
    provenance = candidate['evidence']['cross_store_provenance']
    for key, event in events.items():
        check(key + '.partition', provenance['partition'], event['partition'])
        check(key + '.generation', provenance['generation'], event['generation'])
        for field, value in provenance['telemetry_source'].items():
            expected = event['source']['sha256'] if field == 'source_sha256' else event.get(field, event['source'].get(field))
            check(key + '.source.' + field, value, expected)
    for field, value in provenance['knowledge'].items():
        if field not in ('join', 'interpretation'):
            check('knowledge.' + field, value, technique[field])
    check('knowledge.type_id', technique['type_id'], 'T1218.011')
    check('knowledge.doc_id', technique['doc_id'], 'T1218.011')
    check('knowledge.case_join', case['knowledge_refs'], ['situation_type:' + technique['type_id']])
    check('knowledge.alarm_join', alarm['knowledge_refs'], case['knowledge_refs'])
    check('knowledge.generation', technique['generation'], provenance['generation'])
    nodes, edges = {}, {}
    for key, response in responses.items():
        if key.startswith('graph-'):
            graph = response['body']
            check(key + '.historical_replay', graph['historical_replay'], True)
            check(key + '.partition', graph['partition'], provenance['partition'])
            check(key + '.source', graph['source'], case['source'])
            nodes.update({item['id']: item for item in graph['nodes']})
            edges.update({item['id']: item for item in graph['edges']})
    entity_ids = observed['graph_evidence']['entity_ids']
    for key, event in events.items():
        for candidate_role, source_role in (('host', 'host'), ('user', 'user'), ('account_domain', 'domain'), ('parent', 'parent_process')):
            check(key + '.entity.' + candidate_role, entity_ids[candidate_role], event['entity_refs'][source_role])
        process = entity_ids['event_' + key[-1] + '_process']
        check(key + '.process_entity', process, event['entity_refs']['process'])
        check(key + '.process_count', nodes[process]['event_count'], 1)
        check(key + '.observation_roles', nodes[process]['properties']['observation_roles'], ['process_creation'])
        for label, origin, target in [('PARENT_OF', entity_ids['parent'], process), ('PROCESS_ON_HOST', process, entity_ids['host']), ('EXECUTED_AS', process, entity_ids['user'])]:
            selected = [edge for edge in edges.values() if (edge['label'], edge['from'], edge['to']) == (label, origin, target)]
            check(key + '.edge.' + label, len(selected), 1)
            if selected:
                check(key + '.edge_evidence.' + label, selected[0]['properties']['evidence_refs'], [event['resource_id']])
    check('parent.observation_roles', nodes[entity_ids['parent']]['properties']['observation_roles'], ['parent_field_reference'])
    for role in ('host', 'user', 'parent'):
        check(role + '.event_count', nodes[entity_ids[role]]['event_count'], 2)
        check(role + '.first_seen', nodes[entity_ids[role]]['first_seen'], first['timestamp'])
        check(role + '.last_seen', nodes[entity_ids[role]]['last_seen'], second['timestamp'])
    check('domain.kind', nodes[entity_ids['account_domain']]['properties']['domain_kind'], 'windows-account-domain')
    check('domain.membership', any(edge['label'] == 'MEMBER_OF_DOMAIN' and edge['from'] == entity_ids['user'] and edge['to'] == entity_ids['account_domain'] for edge in edges.values()), True)
    for item in list(nodes.values()) + list(edges.values()):
        check('graph.generation.' + item['id'], item['properties']['generation'], provenance['generation'])
        check('graph.source.' + item['id'], item['properties']['source'], case['source'])
    publication = json.loads((ROOT / 'instruction-publication.json').read_text())
    for item in candidate['evidence']['instruction_coverage']['documents']:
        document = next(value for value in publication['documents'].values() if value['path'] == item['path'])
        for field in ('retrieved_chunks', 'expected_chunks'):
            check('instructions.' + item['path'] + '.' + field, item[field], len(document['keys']))
        check('instructions.' + item['path'] + '.bytes', item['reported_content_bytes'], document['bytes'])
        check('instructions.' + item['path'] + '.sha256', item['source_sha256'], document['sha256'])
    calls = mission['tool_calls']
    claimed_keys = candidate['commands']['parallel_batches'][0]['keys'] + [item['key'] for item in candidate['evidence']['live_receipts']] + candidate['commands']['parallel_batches'][2]['keys']
    check('reported_callback_order', claimed_keys, [item['key'] for item in calls])
    for item in candidate['evidence']['live_receipts']:
        actual = [call for call in calls if call['key'] == item['key']]
        check('receipt.' + item['key'] + '.sha256', item['sha256'], responses[item['key']]['sha256'])
        check('receipt.' + item['key'] + '.timestamps', item['retrieved_at'], [call['retrieved_at'] for call in actual])
    counts = candidate['commands']['observable_counts']
    for field, expected in [('instruction_reads', 46), ('evidence_reads', 12), ('unique_evidence_keys', 9), ('intentional_repeat_reads', 3), ('failed_read_public_calls', 0), ('error_retries', 0), ('shell_commands', 0), ('candidate_requested_writes', 0), ('agent_dispatches', 0)]:
        check('commands.' + field, counts[field], expected)
    check('no_permission_requests', mission['capture']['permission_denied_count'], 0)
    check('next_probe.host', candidate['next_probe']['bounds']['host'], first['host'])
    failures = [item for item in checks if not item['passed']]
    rationale = [
        'Both exact source timestamps, embedded UtcTime, ordinals, offsets and calculated gaps checked; event-2 precedes event-1.',
        'Both canonical event:// resource URIs, exact image/commands/temp-DLL fields, rule and membership checked. Later MessageBoxThread distinguished without success claim.',
        'Exact entities and graph edges checked. Parent explicitly only parent_field_reference; sibling launches distinguished; domain not treated as C2.',
        'Final explicitly abstains on compromise, DLL content/loading/export success and retry-success interpretation; unlabelled emulation and advisory ATT&CK remain explicit.',
        'Proposed existing EventID 7/11/1/5 evidence only, one host, 09:40-09:43 UTC, 100 records/source; no scan, payload execution or remediation performed.',
        'Independent pre/post anonymous 401 and foreign-partition 422; fixtures refuse unknown keys/mutations; all actual reads allowlisted; no shell/agent tools or permission requests.',
        'Final bytes read back; independent source, live callback hashes/bodies, event/graph evidence and exact claim mapping verified. Any mismatches listed, not hidden.',
    ]
    report = {'started_at': started_at, 'objective': 'v17-fulfilment-20260921', 'stage': 'data-understanding',
              'evaluator_sha256': sha(ROOT / 'evaluate.py'), 'prior_exact_field_method_sha256': REPAIR_PINS['evaluate.py'],
              'mapping_change': 'Candidate-selected final JSON shape differs; output-specific field mapping only. Seven fixed qualitative oracle criteria unchanged; no score/threshold.',
              'oracle_sha256': sha(PRIOR / 'oracle.json'), 'field_checks': checks, 'field_check_count': len(checks), 'incorrect_claims': failures,
              'criteria': [{'criterion': criterion, 'outcome': 'satisfied' if not failures else 'review-required', 'evidence': evidence}
                           for criterion, evidence in zip(oracle['criteria'], rationale, strict=True)],
              'mission_only_qualitative_outcome': 'supported-with-complete-callback-transfer-and-live-retrieval' if not failures else 'not-accepted-field-mismatch',
              'full_instruction_semantic_consumption_verified': False, 'candidate_truncation_report': candidate['evidence']['instruction_coverage']['truncation'],
              'missing_or_unverified': ['No independent model-visible byte or semantic-consumption attestation',
                                       'Candidate parallel_wrapper_calls is self-report; host independently records 58 read_public calls',
                                       'Graph covers 8/10 source nodes and 14/19 edges, not complete graph',
                                       'Negative callback/mutation/timeout cases are fixtures; no actual adversarial candidate attempt',
                                       'No fresh overseer comparison, criteria freeze, scored baseline or v1.7 acceptance'],
              'comparison_claim': False, 'timings': transfer['timings'],
              'artifacts': {path.name: sha(path) for path in (transfer_path, mission_path, final_path, readback_path)},
              'elapsed_seconds': (time.monotonic_ns() - started) / 1e9, 'finished_at': now()}
    output = ROOT / (identifier + '-evaluation.json')
    save(output, report)
    print(json.dumps({'receipt': output.name, 'sha256': sha(output), 'field_checks': len(checks),
                      'incorrect_claims': failures, 'outcome': report['mission_only_qualitative_outcome']}))
    return 0 if not failures else 2


if __name__ == '__main__':
    raise SystemExit(evaluate())