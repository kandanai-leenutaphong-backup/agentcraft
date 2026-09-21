"""Deny-by-default public event collector; never reads native private state."""

import re


class Capture:
    def __init__(self, limit=100000):
        self.limit = limit
        self.final = None
        self.truncated = False
        self.discarded = 0
        self.selected = None
        self.usage = []

    def accept(self, kind, data):
        if not isinstance(data, dict):
            self.discarded += 1
            return
        if kind == 'assistant.message' and data.get('phase') == 'final':
            content = data.get('content')
            if isinstance(content, str):
                if re.search(r'gh[pousr]_|github_pat_|-----BEGIN .*PRIVATE KEY-----|Bearer\s+\S+', content, re.I):
                    raise ValueError('credential-shaped-final-refused')
                self.truncated = len(content.encode()) > self.limit
                self.final = None if self.truncated else content
        elif kind == 'subagent.selected':
            name = data.get('agentName')
            if name == 'local-dev-test-subject':
                self.selected = name
        elif kind == 'assistant.usage':
            self.usage.append({key: value for key, value in data.items()
                               if key in ('inputTokens', 'outputTokens', 'cacheReadTokens',
                                          'cacheWriteTokens', 'cost', 'duration')
                               and type(value) in (int, float)})
        else:
            self.discarded += 1