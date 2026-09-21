import asyncio
import copy
import json
from types import SimpleNamespace
import unittest

import reuse
from transport import LIMIT, LiveReader, publish_bytes, publication, reconstruct, wire


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def test_unicode_byte_exact_and_sdk_result(self):
        from copilot.tools import ToolResult
        content = ('line\r\n\"\\' + chr(0x1f600) + chr(0xe9)) .encode() * 900
        chunks = publish_bytes('test', content)
        self.assertEqual(reconstruct(chunks, reuse.digest(content)), content)
        for chunk in chunks:
            result = ToolResult(text_result_for_llm=wire(chunk))
            self.assertEqual(json.loads(result.text_result_for_llm), chunk)
            self.assertLessEqual(len(result.text_result_for_llm), LIMIT)
            self.assertLessEqual(len(result.text_result_for_llm.encode()), LIMIT)

    def test_missing_duplicate_reordered_tampered_refused(self):
        chunks = publish_bytes('test', b'abcdef' * 900)
        for changed in (chunks[:-1], [chunks[0]] + chunks[:-1], list(reversed(chunks))):
            with self.assertRaises(AssertionError):
                reconstruct(changed, reuse.digest(b'abcdef' * 900))
        changed = copy.deepcopy(chunks)
        changed[0]['content'] += 'x'
        with self.assertRaises(AssertionError):
            reconstruct(changed, reuse.digest(b'abcdef' * 900))

    def test_real_publication_and_pins(self):
        reuse.pins()
        chunks, index = publication()
        self.assertEqual(sum(len(item['keys']) for item in index.values()), len(chunks))
        for item in index.values():
            self.assertEqual(reconstruct([chunks[key] for key in item['keys']], item['sha256']),
                             (reuse.WORKSPACE / item['path']).read_bytes())

    async def test_actual_fetch_and_instruction(self):
        calls = []
        def fetch(path):
            calls.append(path)
            return SimpleNamespace(status=200, body=b'{"value":1}')
        chunks = publish_bytes('test', b'exact')
        reader = LiveReader({chunks[0]['key']: chunks[0]}, {'event-1': '/fixed'}, fetch)
        self.assertEqual((await reader.read({'key': 'test:001'})).result_type, 'success')
        for unused in range(2):
            self.assertEqual((await reader.read({'key': 'event-1'})).result_type, 'success')
        self.assertEqual(calls, ['/fixed', '/fixed'])
        self.assertEqual((await reader.drain())['outstanding_reads'], 0)

    async def test_denied_key_mutation_never_fetches(self):
        def fetch(path):
            self.fail('denied callback reached network')
        reader = LiveReader({}, {'event-1': '/fixed'}, fetch)
        for arguments in ({'key': '../outside'}, {'key': 'event-1', 'write': True},
                          {'key': 'event-1', 'method': 'POST'}, {'shell': 'pwd'}, {'key': []}, None):
            self.assertEqual((await reader.read(arguments)).result_type, 'denied')

    async def test_failure_and_timeout_no_replay(self):
        for outcome in (SimpleNamespace(status=403, body=b'refused'), TimeoutError()):
            def fetch(path):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            reader = LiveReader({}, {'event-1': '/fixed'}, fetch)
            self.assertEqual((await reader.read({'key': 'event-1'})).result_type, 'failure')
            self.assertIn('failure', reader.calls[0])
            self.assertEqual((await reader.drain())['outstanding_reads'], 0)

    async def test_cancelled_thread_joined(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        def fetch(path):
            entered.set()
            release.wait(2)
            return SimpleNamespace(status=200, body=b'{}')
        reader = LiveReader({}, {'event-1': '/fixed'}, fetch)
        task = asyncio.create_task(reader.read({'key': 'event-1'}))
        await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        release.set()
        self.assertEqual((await reader.drain())['outstanding_reads'], 0)


if __name__ == '__main__':
    unittest.main()