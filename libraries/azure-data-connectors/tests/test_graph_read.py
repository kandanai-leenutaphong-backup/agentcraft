import unittest
from concurrent.futures import Future
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from azdata.graph_read import GraphReadConfig, GraphUnavailable, GremlinReader


CONFIG = GraphReadConfig("fixture", "database", "graph", "subscription", "group")


def driver(rows=None, error=None):
    client = MagicMock()
    result = Future()
    if error is not None:
        result.set_exception(error)
    else:
        result.set_result(rows if rows is not None else [])
    client.submit.return_value.all.return_value = result
    return client


class GraphReadTests(unittest.TestCase):
    def test_default_denial_construction_description_and_close_make_no_calls(self):
        credential, key, factory = MagicMock(), MagicMock(), MagicMock()
        reader = GremlinReader(CONFIG, credential=credential, key_provider=key, client_factory=factory)
        self.assertFalse(reader.describe()["allow_reads"])
        with self.assertRaisesRegex(GraphUnavailable, "not_granted"):
            reader.query("g.V().count()")
        reader.close()
        factory.assert_not_called()
        key.assert_not_called()
        credential.get_token.assert_not_called()
        credential.close.assert_not_called()

    def test_serialization_bounds_fixed_target_and_connection_reuse(self):
        native = driver([{"id": "one"}])
        key, factory = MagicMock(return_value="synthetic-read-only-key"), MagicMock(return_value=native)
        with GremlinReader(CONFIG, allow_reads=True, key_provider=key, client_factory=factory) as reader:
            self.assertEqual(reader.query("g.V().has('name', wanted)", {"wanted": "${g.V().drop()}"}), [{"id": "one"}])
            reader.query("g.V().groupCount().by(label)")
            expression = native.submit.call_args_list[0].args[0]
            self.assertIn("\\$", expression)
            self.assertTrue(expression.endswith(".limit(2501)"))
            self.assertGreater(native.submit.call_args.kwargs["request_options"]["evaluationTimeout"], 0)
            self.assertEqual(factory.call_args.kwargs["username"], "/dbs/database/colls/graph")
            self.assertEqual(factory.call_count, 1)
        key.assert_called_once()
        native.close.assert_called_once()
        with self.assertRaisesRegex(GraphUnavailable, "closed"):
            reader.query("g.V().count()")

    def test_mutation_and_unbounded_scripts_refuse_before_secret_or_connection(self):
        key, factory = MagicMock(), MagicMock()
        with GremlinReader(CONFIG, allow_reads=True, key_provider=key, client_factory=factory) as reader:
            for expression in ("g.V().drop()", "g.V(); g.addV('bad')", "g.V().repeat(__.both()).emit()"):
                with self.assertRaises(GraphUnavailable):
                    reader.query(expression)
        key.assert_not_called()
        factory.assert_not_called()

    def test_incomplete_and_oversized_results_are_not_silently_truncated(self):
        for config, rows in ((replace(CONFIG, max_items=1), [{"id": "one"}, {"id": "two"}]),
                             (replace(CONFIG, max_output_bytes=5), [{"id": "one"}])):
            native = driver(rows)
            with GremlinReader(config, allow_reads=True, key_provider=lambda: "synthetic",
                               client_factory=MagicMock(return_value=native)) as reader:
                with self.assertRaises(GraphUnavailable):
                    reader.query("g.V()")
            native.close.assert_called_once()

    def test_idle_drop_reconnects_once_and_only_read_queries_can_retry(self):
        dead, live = driver(error=RuntimeError("Connection was already closed")), driver([7])
        factory = MagicMock(side_effect=[dead, live])
        with GremlinReader(CONFIG, allow_reads=True, key_provider=lambda: "synthetic",
                           client_factory=factory) as reader:
            self.assertEqual(reader.query("g.V().count()"), [7])
            self.assertEqual(reader.reconnects, 1)
            dead.close.assert_called_once()
        live.close.assert_called_once()

    def test_query_fault_is_not_retried_or_exposed_in_error_text(self):
        native = driver(error=RuntimeError("sensitive-provider-payload"))
        factory = MagicMock(return_value=native)
        with GremlinReader(CONFIG, allow_reads=True, key_provider=lambda: "synthetic",
                           client_factory=factory) as reader:
            with self.assertRaises(GraphUnavailable) as caught:
                reader.query("g.V()")
            self.assertNotIn("sensitive-provider-payload", str(caught.exception))
            self.assertEqual(reader.reconnects, 0)
            factory.assert_called_once()

    def test_native_sdk_reads_only_read_only_keys_once_and_borrows_identity(self):
        credential, management = MagicMock(), MagicMock()
        management.database_accounts.list_read_only_keys.return_value = SimpleNamespace(primary_readonly_master_key="synthetic")
        with patch("azure.mgmt.cosmosdb.CosmosDBManagementClient", return_value=management) as create:
            with GremlinReader(CONFIG, allow_reads=True, credential=credential,
                               client_factory=MagicMock(return_value=driver([1]))) as reader:
                self.assertEqual(reader.element_count("vertices"), 1)
                self.assertEqual(reader.element_count("edges"), 1)
            create.assert_called_once()
            self.assertEqual(create.call_args.args, (credential, "subscription"))
            management.database_accounts.list_read_only_keys.assert_called_once_with("group", "fixture")
            management.database_accounts.list_keys.assert_not_called()
            management.close.assert_called_once()
        credential.close.assert_not_called()

    def test_key_failure_preserves_denial_cause_without_exposing_a_secret(self):
        credential, management = MagicMock(), MagicMock()
        management.database_accounts.list_read_only_keys.side_effect = RuntimeError("private-key-context")
        factory = MagicMock()
        with patch("azure.mgmt.cosmosdb.CosmosDBManagementClient", return_value=management):
            with GremlinReader(CONFIG, allow_reads=True, credential=credential, client_factory=factory) as reader:
                with self.assertRaises(GraphUnavailable) as caught:
                    reader.query("g.V().count()")
            self.assertNotIn("private-key-context", str(caught.exception))
            self.assertIsInstance(caught.exception.__cause__, RuntimeError)
            factory.assert_not_called()
            management.close.assert_called_once()

    def test_empty_key_refuses_before_connecting(self):
        factory = MagicMock()
        with GremlinReader(CONFIG, allow_reads=True, key_provider=lambda: "", client_factory=factory) as reader:
            with self.assertRaisesRegex(GraphUnavailable, "key_absent"):
                reader.query("g.V().count()")
        factory.assert_not_called()

    def test_missing_identity_refuses_before_management_or_driver_io(self):
        factory = MagicMock()
        with patch("azure.mgmt.cosmosdb.CosmosDBManagementClient") as management:
            with GremlinReader(CONFIG, allow_reads=True, client_factory=factory) as reader:
                with self.assertRaisesRegex(GraphUnavailable, "unconfigured"):
                    reader.query("g.V().count()")
            management.assert_not_called()
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()