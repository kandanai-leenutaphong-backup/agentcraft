import unittest
from unittest.mock import MagicMock

from azdata import Policy
from azdata.adx_read import AdxQueryClient, bind_parameters


class AdxReadPolicyTests(unittest.TestCase):
    def test_write_grants_are_refused_before_transport_or_credentials(self):
        credential, transport = MagicMock(), MagicMock()
        with self.assertRaisesRegex(ValueError, "query-only"):
            AdxQueryClient(endpoint="https://fixture.kusto.windows.net", database="Fixture",
                           credential=credential, transport=transport,
                           policy=Policy("reader", grants={"query", "ingest"}))
        self.assertEqual(credential.mock_calls, [])
        self.assertEqual(transport.mock_calls, [])

    def test_absent_query_grant_refuses_and_close_keeps_borrowed_identity(self):
        credential, transport = MagicMock(), MagicMock()
        client = AdxQueryClient(endpoint="https://fixture.kusto.windows.net", database="Fixture",
                                credential=credential, transport=transport,
                                policy=Policy("reader", grants=frozenset()))
        try:
            with self.assertRaises(ValueError):
                client.query("print value=1")
        finally:
            client.close()
        self.assertEqual(credential.mock_calls, [])
        self.assertEqual(transport.mock_calls, [])

    def test_parameters_never_become_executable_query_text(self):
        value = "'; .drop table Events"
        prologue, parameters = bind_parameters({"name": value, "ids": ["first", "second"]})
        self.assertNotIn(value, prologue)
        self.assertEqual(parameters["name"], value)
        self.assertIn("ids:dynamic", prologue)
        with self.assertRaises(ValueError):
            bind_parameters({"name); .drop": "value"})