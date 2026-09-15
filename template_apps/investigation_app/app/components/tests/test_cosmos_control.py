"""Shared graph provisioning and key lookup, with no Azure requests."""

from unittest import TestCase
from unittest.mock import Mock, call

from app.components.azure_arm import ArmClient, ArmError
from app.components.data_connector_library import cosmos_ensure_graph, cosmos_primary_key

ACCOUNT = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/acct"
DATABASE = f"{ACCOUNT}/gremlinDatabases/db?api-version=2024-11-15"
GRAPH = f"{ACCOUNT}/gremlinDatabases/db/graphs/graph?api-version=2024-11-15"


class CosmosControlTests(TestCase):
    def setUp(self) -> None:
        self.client = Mock(spec=ArmClient)

    def ensure(self, **kwargs):
        return cosmos_ensure_graph("sub", "rg", "acct", "db", "graph", "pk",
                                   client=self.client, **kwargs)

    def test_existing_graph_never_writes(self) -> None:
        self.client.get.return_value = (200, {})
        self.assertEqual(self.ensure(), "existing")
        self.client.get.assert_called_once_with(GRAPH, absent_ok=True)
        self.client.put.assert_not_called()
        self.client.await_provisioned.assert_not_called()

    def test_missing_database_and_graph_are_created_then_read_back(self) -> None:
        self.client.get.side_effect = [(404, {}), (404, {})]
        self.assertEqual(self.ensure(max_throughput=5000, wait_seconds=12), "created")
        self.assertEqual(self.client.method_calls, [
            call.get(GRAPH, absent_ok=True), call.get(DATABASE, absent_ok=True),
            call.put(DATABASE, body={"properties": {"resource": {"id": "db"}, "options": {}}}),
            call.await_provisioned(DATABASE, wait_seconds=12),
            call.put(GRAPH, body={"properties": {
                "resource": {"id": "graph", "partitionKey": {"paths": ["/pk"], "kind": "Hash"}},
                "options": {"autoscaleSettings": {"maxThroughput": 5000}},
            }}),
            call.await_provisioned(GRAPH, wait_seconds=12),
        ])

    def test_existing_database_is_not_rewritten(self) -> None:
        self.client.get.side_effect = [(404, {}), (200, {})]
        self.assertEqual(self.ensure(), "created")
        self.assertEqual(self.client.put.call_count, 1)
        self.client.await_provisioned.assert_called_once_with(GRAPH, wait_seconds=300)

    def test_key_lookup_and_missing_key_refusal(self) -> None:
        self.client.post.return_value = (200, {"primaryMasterKey": "fixture-only"})
        self.assertEqual(cosmos_primary_key("sub", "rg", "acct", client=self.client), "fixture-only")
        self.client.post.assert_called_once_with(f"{ACCOUNT}/listKeys?api-version=2024-11-15", absent_ok=True)
        self.client.post.return_value = (404, {})
        with self.assertRaisesRegex(RuntimeError, "ARM returned no account key"):
            cosmos_primary_key("sub", "rg", "acct", client=self.client)

    def test_failed_readback_never_reports_created(self) -> None:
        self.client.get.side_effect = [(404, {}), (200, {})]
        self.client.await_provisioned.side_effect = ArmError(0, "deadline")
        with self.assertRaises(ArmError):
            self.ensure()

    def test_permission_denial_never_attempts_creation(self) -> None:
        self.client.get.side_effect = ArmError(403, "denied")
        with self.assertRaises(ArmError):
            self.ensure()
        self.client.put.assert_not_called()

    def test_empty_subscription_refused_before_any_request(self) -> None:
        with self.assertRaises(ArmError):
            cosmos_primary_key("", "rg", "acct", client=self.client)
        self.assertEqual(self.client.method_calls, [])
