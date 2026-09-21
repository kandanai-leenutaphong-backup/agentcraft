"""Bounded exact instruction chunks and fixed-key live signed GET callbacks."""

import asyncio
import json
import time

from reuse import ROOT, WORKSPACE, PROJECT, digest, load, now, save
from capture import SECRET, category
from copilot.tools import ToolResult

LIMIT = 2000
DOCUMENTS = {
    'role': WORKSPACE / '.github/agents/local-dev-test-subject.agent.md',
    'process': WORKSPACE / '.github/skills/agentcraft-process/SKILL.md',
    'constitution': PROJECT / 'constitution/constitution.yaml',
}


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def publish_bytes(name, content):
    text = content.decode('utf-8')
    pieces = []
    piece = ''
    for character in text:
        prospective = piece + character
        if len(wire(prospective).encode('utf-8')) > 1400:
            pieces.append(piece)
            piece = character
        else:
            piece = prospective
    pieces.append(piece)
    chunks = []
    offset = 0
    for index, piece in enumerate(pieces):
        raw = piece.encode('utf-8')
        chunk = {'key': f'{name}:{index + 1:03d}', 'index': index + 1, 'count': len(pieces),
                 'document_sha256': digest(content), 'chunk_sha256': digest(raw),
                 'byte_offset': offset, 'bytes': len(raw), 'content': piece}
        assert len(wire(chunk)) <= LIMIT and len(wire(chunk).encode('utf-8')) <= LIMIT
        chunks.append(chunk)
        offset += len(raw)
    return chunks


def reconstruct(chunks, expected):
    assert chunks and len(chunks) == chunks[0]['count']
    result = bytearray()
    for index, chunk in enumerate(chunks, 1):
        assert chunk['index'] == index and chunk['count'] == len(chunks)
        assert chunk['document_sha256'] == expected
        assert chunk['byte_offset'] == len(result)
        raw = chunk['content'].encode('utf-8')
        assert len(raw) == chunk['bytes'] and digest(raw) == chunk['chunk_sha256']
        result.extend(raw)
    assert digest(result) == expected
    return bytes(result)


def publication():
    chunks, index = {}, {}
    for name, path in DOCUMENTS.items():
        content = path.read_bytes()
        items = publish_bytes(name, content)
        assert reconstruct(items, digest(content)) == content
        chunks.update({item['key']: item for item in items})
        index[name] = {'path': str(path.relative_to(WORKSPACE)), 'sha256': digest(content),
                       'bytes': len(content), 'keys': [item['key'] for item in items]}
    return chunks, index


class LiveReader:
    def __init__(self, chunks, routes, fetch, output=None):
        self.chunks, self.routes, self.fetch, self.output = chunks, routes, fetch, output
        self.calls, self.active = [], set()

    async def read(self, arguments):
        started = time.monotonic_ns()
        valid = isinstance(arguments, dict) and set(arguments) == {'key'}
        key = arguments.get('key') if valid else None
        valid = valid and isinstance(key, str) and key in (self.chunks.keys() | self.routes.keys())
        call = {'sequence': len(self.calls) + 1, 'key': key if valid else None,
                'allowed': bool(valid), 'at': now(), 'kind': 'denied'}
        self.calls.append(call)
        try:
            if not valid:
                return ToolResult(result_type='denied', text_result_for_llm='Denied: published keys only; no arbitrary paths, queries or mutations.')
            if key in self.chunks:
                call['kind'] = 'instruction-chunk'
                payload = wire(self.chunks[key])
                call.update(status=200, payload_sha256=digest(payload.encode()),
                            payload_chars=len(payload), payload_bytes=len(payload.encode()))
            else:
                call['kind'] = 'live-signed-GET'
                call['path'] = self.routes[key]
                task = asyncio.create_task(asyncio.to_thread(self.fetch, self.routes[key]))
                self.active.add(task)
                try:
                    reply = await asyncio.shield(task)
                finally:
                    if task.done():
                        self.active.discard(task)
                call.update(status=reply.status, sha256=digest(reply.body), bytes=len(reply.body), retrieved_at=now())
                if reply.status != 200:
                    call['failure'] = 'live-status-refused'
                    return ToolResult(result_type='failure', text_result_for_llm='Live read refused; no replay substituted.')
                body = json.loads(reply.body)
                payload = wire({'key': key, 'path': self.routes[key], 'status': reply.status,
                                'sha256': call['sha256'], 'retrieved_at': call['retrieved_at'], 'body': body})
                if SECRET.search(payload):
                    raise ValueError('unsafe-public-response')
                if self.output:
                    receipt = self.output / f'callback-{call["sequence"]:04d}.json'
                    save(receipt, {'key': key, 'path': self.routes[key], 'status': reply.status,
                                   'sha256': call['sha256'], 'retrieved_at': call['retrieved_at'], 'body': body,
                                   'raw_utf8': reply.body.decode('utf-8')})
                    call['receipt'] = receipt.name
                call.update(payload_chars=len(payload), payload_bytes=len(payload.encode()))
            return ToolResult(result_type='success', text_result_for_llm=payload)
        except asyncio.CancelledError:
            call['failure'] = 'callback-cancelled'
            raise
        except Exception as error:
            call.update(failure=category(error), exception_type=type(error).__name__)
            return ToolResult(result_type='failure', text_result_for_llm='Live read failed; no replay substituted. Failure category: ' + call['failure'])
        finally:
            call['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9

    async def tool(self, invocation):
        return await self.read(invocation.arguments)

    async def drain(self):
        pending = list(self.active)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self.active.clear()
        return {'outstanding_reads': len(self.active), 'joined_reads': len(pending)}


def live_owner(inputs):
    from pathlib import Path
    from signed_dev_access import RequestSigner, load_private_key
    owner = load('live_inputs')
    config = json.loads((WORKSPACE / 'deploy/env/agentcraft-dev.json').read_text())
    manifest, documents = owner.load_package(WORKSPACE / 'template_apps/investigation_app/deploy/data/public-investigation/packages' / owner.PACKAGE_SHA256)
    assert inputs['origin'] == config['runtime']['origin']
    assert inputs['package_sha256'] == owner.PACKAGE_SHA256 and inputs['partition'] == manifest['partition']
    incident = next(item for item in documents['cosmos'] if item['kind'] == 'incident')
    routes = {'cases': '/api/cyber/public/cases?' + owner.urlencode({'partition': manifest['partition']}),
              'alarms': '/api/cyber/public/alarms?' + owner.urlencode({'partition': manifest['partition'], 'case_id': incident['id']}),
              'technique': '/api/cyber/knowledge/type/T1218.011'}
    for index, event in enumerate((item for item in documents['cosmos'] if item['kind'] == 'event'), 1):
        routes[f'event-{index}'] = '/api/cyber/public/evidence?' + owner.urlencode({'partition': manifest['partition'], 'resource_id': event['resource_id']})
        for role, identifier in event['entity_refs'].items():
            if role in ('host', 'user', 'process'):
                routes['graph-' + identifier] = '/api/cyber/graph/node?' + owner.urlencode({'id': identifier})
    assert len(routes) == 9 and routes == {key: value['path'] for key, value in inputs['responses'].items()}
    signer = RequestSigner(load_private_key(str(Path.home() / '.local/state/agentcraft/rg-agentcraft-dev/caller.ed25519')),
                           origin=config['runtime']['origin'], allow_mutations=False)
    return routes, lambda path: signer.request('GET', path, timeout_seconds=25, max_response_bytes=1000000)