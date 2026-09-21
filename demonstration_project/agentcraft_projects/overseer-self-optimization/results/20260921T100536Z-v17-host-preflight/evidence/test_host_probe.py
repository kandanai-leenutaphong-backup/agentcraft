import json
import unittest
from unittest.mock import patch

import host_probe


class MetadataSafetyTests(unittest.TestCase):
    def test_candidate_source_boundary(self):
        self.assertTrue(host_probe.CANDIDATE.is_file())
        self.assertEqual(host_probe.CANDIDATE.name, 'local-dev-test-subject.agent.md')
        self.assertEqual(host_probe.WORKSPACE.name, 'agentcraft')

    def test_no_inference_method(self):
        for method in ('session/prompt', 'session.send', 'authenticate', 'tools/call'):
            with self.assertRaises(ValueError):
                host_probe.encode_request(1, method, {})
        self.assertEqual(json.loads(host_probe.encode_request(1, 'initialize', {}))['method'], 'initialize')

    def test_only_allowlisted_model_fields(self):
        message = {'result': {'sessionId': 'private-id', 'token': 'secret-value',
                             'reasoning': 'private-deliberation', 'models': {'currentModelId': 'gpt-example',
                             'availableModels': [{'modelId': 'gpt-example', 'name': 'GPT Example',
                                                  'description': 'private-value', 'token': 'secret-value'}]}}}
        result = host_probe.summarize(message)
        self.assertTrue(result['session_created'])
        encoded = json.dumps(result)
        for forbidden in ('private', 'secret-value', 'reasoning', 'description', 'sessionId'):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(result['available_models'], [{'id': 'gpt-example', 'name': 'GPT Example'}])

    def test_error_message_not_retained(self):
        result = host_probe.summarize({'error': {'code': -32000, 'message': 'Authentication required: secret-value'}})
        self.assertEqual(result, {'error_code': -32000, 'error_category': 'authentication-required'})

    def test_candidate_gate_preserves_host_failure(self):
        record = {'failure': 'authentication-required'}
        host_probe.apply_candidate_gate(record)
        self.assertEqual(record['failure'], 'authentication-required')
        self.assertFalse(record['inference_admitted'])
        record = {'failure': 'mapping-found-follow-on-gates-required'}
        host_probe.apply_candidate_gate(record)
        self.assertEqual(record['failure'], 'safe-inference-persistence-and-loaded-definition-attestation-unverified')

    def test_secret_shaped_metadata_refused(self):
        for value in ('ghp_secret', 'github_pat_secret', 'Bearer secret', 'line\nbreak'):
            self.assertIsNone(host_probe.safe_name(value))

    def test_environment_rejects_permission_and_capture_inheritance(self):
        with patch.dict(host_probe.os.environ, {'COPILOT_ALLOW_ALL': 'true', 'COPILOT_PROVIDER_API_KEY': 'secret',
                                              'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://invalid',
                                              'COPILOT_CUSTOM_INSTRUCTIONS_DIRS': '/forbidden'}, clear=True):
            environment = host_probe.child_environment(host_probe.ROOT / 'state')
        for forbidden in ('COPILOT_ALLOW_ALL', 'COPILOT_PROVIDER_API_KEY', 'OTEL_EXPORTER_OTLP_ENDPOINT',
                          'COPILOT_CUSTOM_INSTRUCTIONS_DIRS'):
            self.assertNotIn(forbidden, environment)


if __name__ == '__main__':
    unittest.main()