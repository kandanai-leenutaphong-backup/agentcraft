"""Non-inference ACP metadata probe; never retains raw process output."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time


CLI = Path('/home/hanchoong/.local/bin/copilot')
ROOT = Path(__file__).resolve().parent
METHODS = frozenset({'initialize', 'session/new'})
WORKSPACE = ROOT.parents[5]
CANDIDATE = WORKSPACE / '.github/agents/local-dev-test-subject.agent.md'
MODEL_RECEIPT = ROOT / '20260921T101027225664Z-host-probe.json'


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._:/()+-]{0,99}', value):
        return None
    if re.search(r'gh[pousr]_|github_pat_|bearer|token|secret|password', value, re.I):
        return None
    return value


def summarize(message):
    error = message.get('error')
    if isinstance(error, dict):
        text = str(error.get('message', '')).lower()
        category = 'host-error-message-withheld'
        for terms, name in ((('auth', 'login', 'log in'), 'authentication-required'),
                            (('model',), 'model-refusal'),
                            (('method',), 'protocol-method-refusal')):
            if any(term in text for term in terms):
                category = name
                break
        return {'error_code': error.get('code') if isinstance(error.get('code'), int) else None,
                'error_category': category}
    result = message.get('result', {})
    if not isinstance(result, dict):
        return {'result_shape': 'unsupported'}
    allowed_fields = ('protocolVersion', 'agentInfo', 'agentCapabilities', 'authMethods',
                      'models', 'modes', 'configOptions', '_meta')
    summary = {'result_shape': 'object', 'response_fields': [key for key in allowed_fields if key in result],
               'loaded_identity_field_presence': {key: key in result for key in
                   ('loadedDefinitionPath', 'loadedDefinitionSha256', 'selectedAgent')}}
    if isinstance(result.get('protocolVersion'), int):
        summary['protocol_version'] = result['protocolVersion']
    info = result.get('agentInfo', {})
    if isinstance(info, dict):
        summary['host'] = {key: safe_name(info.get(key)) for key in ('name', 'version')}
    summary['session_created'] = isinstance(result.get('sessionId'), str)
    models = result.get('models', {})
    if isinstance(models, dict):
        summary['current_model_metadata_only'] = safe_name(models.get('currentModelId'))
        available = models.get('availableModels', [])
        if isinstance(available, list):
            summary['available_models'] = [
                {'id': safe_name(model.get('modelId')), 'name': safe_name(model.get('name'))}
                for model in available if isinstance(model, dict)
            ]
    summary['auth_methods_count'] = len(result['authMethods']) if isinstance(result.get('authMethods'), list) else None
    return summary


def apply_candidate_gate(record):
    if record.get('failure') == 'mapping-found-follow-on-gates-required':
        record['failure'] = 'safe-inference-persistence-and-loaded-definition-attestation-unverified'
    record['inference_admitted'] = False


def encode_request(identifier, method, params):
    if method not in METHODS:
        raise ValueError('inference-and-other-methods-forbidden')
    return (json.dumps({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}) + '\n').encode()


def child_environment(state):
    allowed = ('PATH', 'HOME', 'LANG', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'NODE_EXTRA_CA_CERTS',
               'COPILOT_GITHUB_TOKEN', 'GH_TOKEN', 'GITHUB_TOKEN', 'GH_HOST', 'COPILOT_GH_HOST',
               'GH_CONFIG_DIR', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy')
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(COPILOT_HOME=str(state), COPILOT_AUTO_UPDATE='false',
                       COPILOT_OTEL_ENABLED='false', USE_TGREP='false', NO_COLOR='1',
                       GIT_CEILING_DIRECTORIES=str(state.parent))
    return environment


def structural_events(state):
    result = {'files': [], 'types': {}, 'selected_agents': [], 'session_starts': [],
              'private_payload_fields_present': 0, 'loaded_definition_path': None,
              'loaded_definition_sha256': None}
    for path in sorted((state / 'session-state').glob('*/events.jsonl')):
        result['files'].append(str(path.relative_to(ROOT)))
        for line in path.read_text().splitlines():
            event = json.loads(line)
            kind = safe_name(event.get('type'))
            if kind is None:
                kind = 'unrecognized-event-name'
            result['types'][kind] = result['types'].get(kind, 0) + 1
            data = event.get('data', {})
            if not isinstance(data, dict):
                continue
            result['private_payload_fields_present'] += sum(key in data for key in ('reasoningText', 'reasoning', 'content', 'token'))
            if kind == 'subagent.selected':
                result['selected_agents'].append({'name': safe_name(data.get('agentName')),
                    'tools': [safe_name(tool) for tool in data.get('tools', [])] if isinstance(data.get('tools'), list) else None})
            if kind == 'session.start':
                result['session_starts'].append({'selected_model': safe_name(data.get('selectedModel')),
                                                 'reasoning_effort': safe_name(data.get('reasoningEffort'))})
    return result


def run_probe(timeout, candidate_metadata=False):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    state = ROOT / (stamp + '-metadata-state')
    workspace = state / 'workspace'
    workspace.mkdir(parents=True, mode=0o700)
    (workspace / '.git').mkdir()
    candidate_source = None
    if candidate_metadata:
        assert hashlib.sha256(MODEL_RECEIPT.read_bytes()).hexdigest() == 'a3aedd28d4c1679ace58b985365b7422248c7fb4ce6d5c42ecbab0a974ce4aeb'
        assert json.loads(MODEL_RECEIPT.read_text())['canonical_model_matches'] == [{'id': 'gpt-6-astra', 'name': 'GPT-6 Astra'}]
        staged = workspace / '.github/agents/local-dev-test-subject.agent.md'
        staged.parent.mkdir(parents=True)
        with staged.open('xb') as handle:
            handle.write(CANDIDATE.read_bytes())
        assert staged.read_bytes() == CANDIDATE.read_bytes()
        candidate_source = {'source': str(CANDIDATE), 'staged': str(staged),
                            'sha256': hashlib.sha256(staged.read_bytes()).hexdigest(),
                            'meaning': 'Byte-identical stage, not host-loaded digest attestation'}
    argv = [str(CLI), '--no-auto-update', '--no-remote', '--no-remote-export',
            '--log-level', 'none', '--disable-builtin-mcps', '--available-tools=',
            '--no-custom-instructions', '--disallow-temp-dir', '--acp', '-C', str(workspace)]
    if candidate_metadata:
        argv.extend(['--agent', 'local-dev-test-subject', '--model', 'gpt-6-astra', '--effort', 'max'])
    record = {'started_at': datetime.now(timezone.utc).isoformat(), 'argv': argv,
              'cli_sha256': hashlib.sha256(CLI.read_bytes()).hexdigest(),
              'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'timeout_seconds': timeout, 'inference_requests': 0, 'requests': [],
              'responses': [], 'notifications': 0, 'denied_host_requests': 0,
              'stderr_bytes_discarded': 0, 'raw_output_retained': False,
              'candidate_loaded_identity': None, 'effective_effort': None,
              'candidate_source': candidate_source,
              'effective_effort_reason': 'unsupported: metadata is not inference/runtime attestation',
              'state_scope': 'Fresh evidence-local COPILOT_HOME; existing HOME/gh auth readable by CLI only; no credential copies',
              'status': 'blocked'}
    started = time.monotonic_ns()
    process = None
    selector = selectors.DefaultSelector()
    buffer = b''
    try:
        auth = subprocess.run(['/usr/bin/gh', 'auth', 'status', '--hostname', 'github.com'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                              env=child_environment(state))
        record['existing_github_auth'] = {'command': 'gh auth status --hostname github.com',
                                         'exit_code': auth.returncode, 'authenticated': auth.returncode == 0,
                                         'output': 'discarded; identity/token values never retained',
                                         'scope': 'GitHub CLI auth, not proof of successful model inference'}
        if auth.returncode != 0:
            record['failure'] = 'existing-github-auth-refused'
            raise PermissionError('existing-auth-required')
        process = subprocess.Popen(argv, cwd=workspace, env=child_environment(state),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
        selector.register(process.stderr, selectors.EVENT_READ, 'stderr')

        def send(identifier, method, params):
            process.stdin.write(encode_request(identifier, method, params))
            process.stdin.flush()
            record['requests'].append({'id': identifier, 'method': method})

        send(1, 'initialize', {'protocolVersion': 1, 'clientCapabilities': {},
                               'clientInfo': {'name': 'bounded-host-metadata', 'version': '1'}})
        finished = False
        while not finished:
            remaining = timeout - (time.monotonic_ns() - started) / 1e9
            if remaining <= 0:
                record['failure'] = 'metadata-timeout'
                break
            events = selector.select(remaining)
            if not events:
                record['failure'] = 'metadata-timeout'
                break
            for key, _mask in events:
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    if key.data == 'stdout':
                        record['failure'] = 'host-stdout-closed-before-metadata'
                        finished = True
                    continue
                if key.data == 'stderr':
                    record['stderr_bytes_discarded'] += len(chunk)
                    continue
                buffer += chunk
                if len(buffer) > 2_000_000:
                    record['failure'] = 'metadata-frame-cap-no-truncation-success'
                    finished = True
                    break
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError('non-object-frame')
                    if 'method' in message:
                        if 'id' in message:
                            process.stdin.write((json.dumps({'jsonrpc': '2.0', 'id': message['id'],
                                'error': {'code': -32601, 'message': 'Host requests forbidden by metadata probe'}}) + '\n').encode())
                            process.stdin.flush()
                            record['denied_host_requests'] += 1
                        else:
                            record['notifications'] += 1
                        continue
                    identifier = message.get('id')
                    if identifier not in (1, 2):
                        raise ValueError('unexpected-response-id')
                    summary = summarize(message)
                    record['responses'].append({'id': identifier, **summary})
                    if 'error' in message:
                        record['failure'] = summary['error_category']
                        finished = True
                        break
                    if identifier == 1:
                        send(2, 'session/new', {'cwd': str(workspace), 'mcpServers': []})
                    else:
                        matches = [model for model in summary.get('available_models', [])
                                   if model['name'] == 'GPT-6 Astra' and model['id']]
                        record['canonical_model_matches'] = matches
                        record['failure'] = ('mapping-found-follow-on-gates-required' if len(matches) == 1
                                             else 'exact-model-mapping-unavailable')
                        finished = True
                        break
    except Exception as error:
        record.setdefault('failure', 'probe-exception')
        record['exception_type'] = type(error).__name__
    finally:
        selector.close()
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            record['exit_code_after_settlement'] = process.returncode
            record['process_settled'] = process.poll() is not None
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
        else:
            record['process_started'] = False
            record['process_settled'] = True
        record['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        record['capture_gaps'] = ['stderr discarded, not complete host telemetry',
                                 'host internal requests/cost unknown',
                                 'metadata session is not candidate loading or inference',
                                 'shutdown-tail output deliberately not captured']
        record['persisted_structural_events'] = structural_events(state)
        if candidate_metadata:
            apply_candidate_gate(record)
    output = ROOT / (stamp + '-host-probe.json')
    with output.open('x') as handle:
        json.dump(record, handle, indent=2)
        handle.write('\n')
    assert json.loads(output.read_text()) == record
    print(json.dumps({'receipt': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                      'failure': record.get('failure'), 'inference_requests': 0,
                      'elapsed_seconds': record['elapsed_seconds'],
                      'process_settled': record.get('process_settled')}))
    return 0 if record.get('canonical_model_matches') and not candidate_metadata else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--candidate-metadata', action='store_true')
    options = parser.parse_args()
    if not 1 <= options.timeout <= 120:
        parser.error('timeout must be 1..120 seconds')
    raise SystemExit(run_probe(options.timeout, options.candidate_metadata))