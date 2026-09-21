"""Public final-only capture and bounded native process settlement."""

import asyncio
from collections import Counter
import math
import os
import re
import signal
import time


KINDS = frozenset(('assistant.message', 'assistant.message_delta', 'assistant.usage',
                   'assistant.turn_start', 'assistant.turn_end', 'session.idle',
                   'session.error', 'tool.execution_start', 'tool.execution_complete',
                   'assistant.reasoning', 'assistant.reasoning_delta', 'session.start',
                   'session.shutdown', 'user.message'))
NUMERIC = ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens', 'duration', 'cost')
SECRET = re.compile(r'gh[pousr]_|github_pat_|-----BEGIN .*PRIVATE KEY-----|Bearer\s+\S+|(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[=:]\s*\S+', re.I)


def category(error):
    return 'timeout' if isinstance(error, (TimeoutError, asyncio.TimeoutError)) else 'public-operation-failed'


class Capture:
    def __init__(self, persist=None, limit=100000):
        self.persist = persist
        self.limit = limit
        self.started = time.monotonic_ns()
        self.counts = Counter()
        self.timings = {}
        self.usage = []
        self.final = None
        self.final_source = None
        self.final_count = 0
        self.failure = None
        self.denied = 0
        self.ready = asyncio.Event()

    def accept(self, kind, data, sdk_final=False):
        if not sdk_final:
            name = kind if kind in KINDS else 'other'
            self.counts[name] += 1
            elapsed = (time.monotonic_ns() - self.started) / 1e9
            timing = self.timings.setdefault(name, {'first_seconds': elapsed, 'last_seconds': elapsed})
            timing['last_seconds'] = elapsed
        if not isinstance(data, dict):
            return
        if kind == 'assistant.usage' and not sdk_final:
            self.usage.append({key: float(data[key]) for key in NUMERIC
                               if type(data.get(key)) in (int, float) and math.isfinite(data[key]) and data[key] >= 0})
        if kind == 'session.error':
            self.failure = 'public-session-error'
            self.ready.set()
        if kind != 'assistant.message':
            return
        phase = data.get('phase')
        if phase not in ('final', 'final_answer') and not (sdk_final and phase is None):
            return
        content = data.get('content')
        if not isinstance(content, str) or not content.strip():
            return
        if SECRET.search(content) or len(content.encode()) > self.limit:
            self.failure = 'unsafe-or-oversized-final-refused'
            self.ready.set()
            return
        if content == self.final:
            return
        self.final = content
        self.final_source = 'sdk-documented-final-return' if sdk_final else 'public-explicit-final-message'
        self.final_count += 1
        if self.persist:
            self.persist({'content': content, 'source': self.final_source, 'sequence': self.final_count})
        self.ready.set()

    def permission(self, request, invocation):
        from copilot.session import PermissionRequestResult
        self.denied += 1
        return PermissionRequestResult(kind='reject')

    def summary(self):
        return {'event_counts': dict(self.counts), 'event_timings': self.timings,
                'usage': self.usage, 'final_count': self.final_count,
                'permission_denied_count': self.denied, 'capture_failure': self.failure}


async def infer_once(session, prompt, capture, bound):
    started = time.monotonic_ns()
    task = asyncio.create_task(session.send_and_wait(prompt, timeout=bound))
    ready = asyncio.create_task(capture.ready.wait())
    result = {'bound_seconds': bound, 'timeout': False, 'idle_return': False}
    try:
        done, _ = await asyncio.wait((task, ready), timeout=bound, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            returned = task.result()
            result['idle_return'] = True
            if returned is not None:
                capture.accept('assistant.message', {'phase': returned.data.phase, 'content': returned.data.content}, sdk_final=True)
        elif ready not in done:
            raise TimeoutError()
        if capture.failure:
            result['failure'] = capture.failure
        elif capture.final is None:
            result['failure'] = 'no-final-output'
    except Exception as error:
        result['failure'] = category(error)
        result['timeout'] = isinstance(error, TimeoutError)
        result['exception_type'] = type(error).__name__
    finally:
        for pending in (task, ready):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, ready, return_exceptions=True)
        result['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
        result['captured_final'] = capture.final is not None
    return result


async def settle(session, client, process, bound=5):
    started = time.monotonic_ns()
    report = {'operations': [], 'forced_kill': False, 'process_settled': process is None}
    group = None
    if process is not None:
        try:
            group = os.getpgid(process.pid)
            if group != process.pid:
                group = None
        except ProcessLookupError:
            pass
    for name, operation in (('abort', session.abort if session else None), ('stop', client.stop if client else None)):
        if operation is None:
            continue
        before = time.monotonic_ns()
        item = {'operation': name, 'status': 'complete'}
        try:
            await asyncio.wait_for(operation(), bound)
        except Exception as error:
            item.update(status='failed', category=category(error), exception_type=type(error).__name__)
        item['seconds'] = (time.monotonic_ns() - before) / 1e9
        report['operations'].append(item)
    if process is not None:
        report['pid'] = process.pid
        report['owned_group'] = group
        if group is not None:
            try:
                os.killpg(group, signal.SIGKILL)
                report['forced_kill'] = True
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
            report['forced_kill'] = True
        try:
            process.wait(timeout=bound)
            report['returncode'] = process.returncode
            report['process_settled'] = process.poll() is not None
        except Exception as error:
            report['reap_failure'] = category(error)
        if group is not None:
            try:
                os.killpg(group, 0)
                report['process_settled'] = False
                report['group_still_present'] = True
            except ProcessLookupError:
                report['group_still_present'] = False
    report['elapsed_seconds'] = (time.monotonic_ns() - started) / 1e9
    return report