import json
import unittest

from capture import Capture


class CaptureTests(unittest.TestCase):
    def test_final_only(self):
        capture = Capture()
        for kind, data in [('assistant.reasoning', {'content': 'PRIVATE'}),
                           ('unknown', {'content': 'PRIVATE'}),
                           ('assistant.message', {'content': 'PRIVATE'}),
                           ('assistant.message', {'phase': 'analysis', 'content': 'PRIVATE'})]:
            capture.accept(kind, data)
        capture.accept('assistant.message', {'phase': 'final', 'content': 'public', 'reasoningText': 'PRIVATE'})
        self.assertEqual(capture.final, 'public')
        self.assertNotIn('PRIVATE', json.dumps(vars(capture)))

    def test_metadata_allowlist(self):
        capture = Capture()
        capture.accept('subagent.selected', {'agentName': 'local-dev-test-subject', 'content': 'PRIVATE'})
        capture.accept('assistant.usage', {'inputTokens': 12, 'outputTokens': 'PRIVATE', 'reasoningText': 'PRIVATE'})
        self.assertEqual(capture.selected, 'local-dev-test-subject')
        self.assertEqual(capture.usage, [{'inputTokens': 12}])
        self.assertNotIn('PRIVATE', json.dumps(vars(capture)))

    def test_truncation_fails_closed(self):
        capture = Capture(limit=4)
        capture.accept('assistant.message', {'phase': 'final', 'content': '12345'})
        self.assertTrue(capture.truncated)
        self.assertIsNone(capture.final)

    def test_credentials_refused(self):
        with self.assertRaisesRegex(ValueError, 'credential-shaped-final-refused'):
            Capture().accept('assistant.message', {'phase': 'final', 'content': 'Bearer fixture'})


if __name__ == '__main__':
    unittest.main()