import unittest

from native import PublicReader, reject_permission, environment, CLI, PINS, digest, error_category, normalize_ping


class NativeTests(unittest.TestCase):
    def test_iso_ping_preserves_protocol(self):
        value = {'timestamp': '1970-01-01T00:00:01Z', 'message': 'safe', 'protocolVersion': 3}
        self.assertEqual(normalize_ping(value), {'timestamp': 1000, 'message': 'safe', 'protocolVersion': 3})
        self.assertEqual(value['timestamp'], '1970-01-01T00:00:01Z')

    def test_error_category_retains_no_content(self):
        self.assertEqual(error_category(ValueError('protocol version PRIVATE')), 'protocol-version-mismatch')
        self.assertEqual(error_category(ValueError('PRIVATE')), 'unclassified-withheld')

    def test_cli_bytes(self):
        self.assertEqual(digest(CLI.read_bytes()), PINS[CLI])

    def test_fixed_read(self):
        reader = PublicReader({'event-1': {'field': 'public'}})
        self.assertEqual(reader.read({'key': 'event-1'}).result_type, 'success')
        for arguments in ({'key': '/etc/passwd'}, {'key': '../oracle.json'}, {'key': 'event-1', 'write': True},
                          {'command': 'id'}, {'key': ['event-1']}, None):
            self.assertEqual(reader.read(arguments).result_type, 'denied')
        self.assertTrue(all(call['key'] is None for call in reader.calls[1:]))

    def test_permissions_reject(self):
        for kind in ('shell', 'write', 'read', 'url', 'custom-tool'):
            self.assertEqual(reject_permission({'kind': kind}, {}).kind, 'reject')

    def test_no_provider_substitution_or_project_host_state(self):
        child = environment()
        self.assertNotIn('COPILOT_PROVIDER_BASE_URL', child)
        self.assertNotIn('COPILOT_HOME', child)
        self.assertEqual(child['COPILOT_OTEL_ENABLED'], 'false')


if __name__ == '__main__':
    unittest.main()