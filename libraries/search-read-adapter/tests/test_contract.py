import asyncio
import unittest

from azdata import ConnectorConfig, Limits, Policy, ResourceAddress
from search_read_adapter import SearchError, SearchReadClient, safe_key


class PublicContractTests(unittest.TestCase):
    def config(self):
        return ConnectorConfig("https://fixture.search.windows.net", ResourceAddress({"index": "fixture"}),
                               ("fixture.search.windows.net",))

    def policy(self, grants=frozenset({"query", "read"})):
        return Policy("offline-reader", grants=grants, max_concurrency=1,
                      limits=Limits(timeout_seconds=30, max_items=100,
                                    max_output_bytes=1_048_576, max_attempts=1))

    def test_key_identity_matches_existing_documents(self):
        self.assertEqual(safe_key("abc"), "abc-ba7816bf")
        self.assertNotEqual(safe_key("a/b"), safe_key("a_b"))

    def test_description_and_close_need_no_credential(self):
        with SearchReadClient(self.config(), credential=None, policy=self.policy()) as client:
            self.assertFalse(client.describe()["credential_configured"])
            self.assertEqual(client.describe()["metrics"]["submitted"], 0)
        self.assertTrue(client.describe()["closed"])

    def test_write_policy_and_target_widening_refuse_before_io(self):
        with self.assertRaises(SearchError):
            SearchReadClient(self.config(), credential=None, policy=self.policy({"query", "schema.create"}))
        with SearchReadClient(self.config(), credential=None, policy=self.policy()) as client:
            with self.assertRaises(SearchError) as caught:
                client.search("another-index")
            self.assertEqual(caught.exception.status, 403)
            self.assertEqual(client.describe()["metrics"]["submitted"], 0)

    def test_active_event_loop_refuses_before_creating_work(self):
        with SearchReadClient(self.config(), credential=None, policy=self.policy()) as client:
            async def call():
                with self.assertRaises(SearchError) as caught:
                    client.search("fixture")
                self.assertEqual(caught.exception.message, "active_event_loop_use_asyncio_to_thread")
            asyncio.run(call())
            self.assertEqual(client.describe()["metrics"]["submitted"], 0)