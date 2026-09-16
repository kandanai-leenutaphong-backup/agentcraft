from unittest import TestCase
from unittest.mock import MagicMock

from azdata.event_store import AdxConfig, AdxConnector, AdxPermissionError, EventStorePolicy


class CanonicalOperatorAdoptionTests(TestCase):
    def test_public_query_is_readonly_and_mutations_refuse_before_io(self):
        config = AdxConfig(cluster_uri="https://fixture.example.test", database="Events")
        with AdxConnector(config, credential=object()) as store:
            sdk = store.client._client = MagicMock()
            sdk.execute_query.return_value.primary_results = []
            self.assertEqual(store.query("print value=1").to_dicts(), [])
            properties = sdk.execute_query.call_args.args[2]
            self.assertTrue(properties.get_option("request_readonly", False))
            sdk.reset_mock()
            with self.assertRaises(AdxPermissionError):
                store.command(".drop table Records")
            self.assertEqual(sdk.mock_calls, [])
        self.assertEqual(EventStorePolicy().grants, frozenset())