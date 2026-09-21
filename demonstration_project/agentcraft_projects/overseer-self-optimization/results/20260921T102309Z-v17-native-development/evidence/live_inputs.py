"""Read-only public mission inputs and independent readback; existing signer owner."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[5]
sys.path.insert(0, str(WORKSPACE / 'deploy'))
from investigation_loader import load_package, PACKAGE_SHA256


def sha(content):
    return hashlib.sha256(content).hexdigest()


def save(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')
    assert json.loads(path.read_text()) == value


def collect(phase):
    import httpx
    from signed_dev_access import RequestSigner, load_private_key

    started = time.monotonic_ns()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = ROOT / (stamp + '-' + phase + '.json')
    config = json.loads((WORKSPACE / 'deploy/env/agentcraft-dev.json').read_text())
    package = WORKSPACE / 'template_apps/investigation_app/deploy/data/public-investigation/packages' / PACKAGE_SHA256
    manifest, documents = load_package(package)
    partition = manifest['partition']
    incident = next(item for item in documents['cosmos'] if item['kind'] == 'incident')
    events = [item for item in documents['cosmos'] if item['kind'] == 'event']
    key = load_private_key(str(Path.home() / '.local/state/agentcraft/rg-agentcraft-dev/caller.ed25519'))
    signer = RequestSigner(key, origin=config['runtime']['origin'], allow_mutations=False)
    routes = {
        'cases': '/api/cyber/public/cases?' + urlencode({'partition': partition}),
        'alarms': '/api/cyber/public/alarms?' + urlencode({'partition': partition, 'case_id': incident['id']}),
        'technique': '/api/cyber/knowledge/type/T1218.011',
    }
    for index, event in enumerate(events, 1):
        routes[f'event-{index}'] = '/api/cyber/public/evidence?' + urlencode({'partition': partition, 'resource_id': event['resource_id']})
        for role, identifier in event['entity_refs'].items():
            if role in ('host', 'user', 'process'):
                routes['graph-' + identifier] = '/api/cyber/graph/node?' + urlencode({'id': identifier})
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'phase': phase,
              'origin': config['runtime']['origin'], 'package_sha256': PACKAGE_SHA256,
              'partition': partition, 'responses': {}, 'refusals': [], 'failures': [],
              'classification': 'live signed GET readbacks for development replay; no full live candidate acceptance'}
    try:
        for name, path in routes.items():
            before = time.monotonic_ns()
            reply = signer.request('GET', path, timeout_seconds=25, max_response_bytes=1000000)
            item = {'path': path, 'status': reply.status, 'sha256': sha(reply.body),
                    'bytes': len(reply.body), 'seconds': (time.monotonic_ns() - before) / 1e9,
                    'retrieved_at': datetime.now(timezone.utc).isoformat()}
            report['responses'][name] = item
            if reply.status != 200:
                raise RuntimeError('live-status-refused')
            item['body'] = json.loads(reply.body)
        foreign = signer.request('GET', '/api/cyber/public/cases?partition=foreign', timeout_seconds=25)
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            anonymous = client.get(config['runtime']['origin'] + '/api/whoami')
        report['refusals'] = [{'check': 'foreign-partition', 'status': foreign.status, 'expected': 422},
                              {'check': 'anonymous', 'status': anonymous.status_code, 'expected': 401}]
        assert foreign.status == 422 and anonymous.status_code == 401
        for index, event in enumerate(events, 1):
            assert event['source']['raw_sha256'] in json.dumps(report['responses'][f'event-{index}']['body'])
        report['local_source'] = {'manifest_sha256': PACKAGE_SHA256, 'events': events,
                                  'graph': documents['gremlin']}
        report['status'] = 'complete'
    except Exception as error:
        report['status'] = 'failed'
        report['failures'].append({'exception_type': type(error).__name__, 'message': 'withheld; no raw exceptions retained'})
    report['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save(output, report)
    print(json.dumps({'path': str(output), 'sha256': sha(output.read_bytes()), 'status': report['status'],
                      'responses': len(report['responses']), 'elapsed_seconds': report['elapsed_seconds']}))
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('inputs', 'independent-readback'))
    raise SystemExit(collect(parser.parse_args().phase))