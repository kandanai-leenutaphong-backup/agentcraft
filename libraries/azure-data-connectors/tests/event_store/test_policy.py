import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from azdata.event_store import (
    AdxClient, AdxConfig, AdxConfigError, AdxConnector, AdxPermissionError,
    AdxProvisioner, AdxProvisioningError, ColumnSpec, EventStorePolicy, TableSchema,
)
from azdata.event_store.ingest import IngestMode, Ingestor


CONFIG = AdxConfig(cluster_uri="https://cluster.example.test", database="Events",
                   subscription_id="11111111-1111-1111-1111-111111111111",
                   resource_group="rg-fixture", cluster_name="fixtureadx")
SCHEMA = TableSchema("Records", (ColumnSpec("record_id", "string"), ColumnSpec("score", "long")))


def policy(*grants):
    return EventStorePolicy(principal="offline-test-operator", grants=frozenset(grants))


class EventStorePolicyTests(unittest.TestCase):
    def test_default_grants_are_empty_and_mutation_identity_is_required(self):
        self.assertEqual(EventStorePolicy().grants, frozenset())
        for options in ({"grants": {"ingest"}}, {"principal": "operator", "grants": {"unknown"}},
                        {"principal": "", "grants": {"command"}}):
            with self.subTest(options=options), self.assertRaises(AdxConfigError):
                EventStorePolicy(**options)

    def test_default_connector_refuses_every_mutation_before_sdk_io(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text("record_id,score\na,7\n", encoding="utf-8")
            store = AdxConnector(CONFIG, credential=object())
            query_sdk = store.client._client = MagicMock()
            ingest_sdk = store.ingestor._managed = store.ingestor._queued = MagicMock()
            management_sdk = store.provisioner._client = MagicMock()
            repository = store.repository(SCHEMA)
            operations = {
                "command": lambda: store.command(".drop table Records"),
                "schema": lambda: store.create_table(SCHEMA),
                "batching": lambda: store.set_batching_latency("Records", 30),
                "streaming": lambda: store.enable_streaming("Records"),
                "rows": lambda: store.ingestor.ingest_rows([{"record_id": "a"}], "Records", SCHEMA),
                "file": lambda: store.ingestor.ingest_file(path, "Records"),
                "load": lambda: store.load_csv(path, "Records"),
                "insert": lambda: repository.insert([{"record_id": "a"}]),
                "delete": lambda: repository.delete_where("score > 0"),
                "purge": lambda: repository.purge_where("score > 0", confirm="Records"),
                "drop": lambda: repository.drop(confirm="Records"),
                "truncate": lambda: repository.truncate(confirm="Records"),
                "drop-tag": lambda: repository.drop_by_tag("batch", confirm="Records"),
                "cluster": lambda: store.provisioner.ensure_cluster(),
                "database": lambda: store.provisioner.ensure_database(),
                "teardown": lambda: store.provisioner.teardown_cluster(confirm="fixtureadx"),
            }
            for name, operation in operations.items():
                with self.subTest(operation=name), self.assertRaises(AdxPermissionError):
                    operation()
            self.assertEqual(query_sdk.mock_calls, [])
            self.assertEqual(ingest_sdk.mock_calls, [])
            self.assertEqual(management_sdk.mock_calls, [])

    def test_read_commands_and_queries_request_server_enforced_readonly(self):
        client = AdxClient(CONFIG, credential=object())
        client._client = MagicMock()
        client._client.execute_query.return_value.primary_results = []
        client._client.execute_mgmt.return_value.primary_results = []
        client.query("print value=7")
        client.command(".show tables")
        for call in (client._client.execute_query.call_args, client._client.execute_mgmt.call_args):
            properties = call.args[2]
            self.assertTrue(properties.get_option("request_readonly", False))
            self.assertTrue(properties.get_option("request_remote_entities_disabled", False))

    def test_schema_grant_cannot_run_arbitrary_or_destructive_commands(self):
        store = AdxConnector(CONFIG, credential=object(), policy=policy("schema"))
        store.client._client = MagicMock()
        store.client._client.execute_mgmt.return_value.primary_results = []
        store.create_table(SCHEMA)
        self.assertTrue(store.client._client.execute_mgmt.call_args.args[1].startswith(".create-merge table Records"))
        with self.assertRaises(AdxPermissionError):
            store.command(".drop table Records")
        with self.assertRaises(AdxPermissionError):
            store.repository(SCHEMA).drop(confirm="Records")
        self.assertEqual(store.client._client.execute_mgmt.call_count, 1)

    def test_raw_management_requires_command_and_delete_grants(self):
        for granted in (("command",), ("delete",)):
            client = AdxClient(CONFIG, credential=object(), policy=policy(*granted))
            with self.subTest(granted=granted), self.assertRaises(AdxPermissionError):
                client.command(".drop table Records")
        client = AdxClient(CONFIG, credential=object(), policy=policy("command", "delete"))
        client._client = MagicMock()
        client._client.execute_mgmt.return_value.primary_results = []
        client.command(".drop table Records")
        self.assertEqual(client._client.execute_mgmt.call_count, 1)

    def test_generated_delete_has_narrow_grant_and_named_confirmation(self):
        store = AdxConnector(CONFIG, credential=object(), policy=policy("delete"))
        store.client._client = MagicMock()
        store.client._client.execute_mgmt.return_value.primary_results = []
        repository = store.repository(SCHEMA)
        for confirmation in (True, "Other", ""):
            with self.subTest(confirmation=confirmation), self.assertRaises(Exception):
                repository.purge_where("score > 0", confirm=confirmation)
        repository.purge_where("score > 0", confirm="Records")
        self.assertEqual(store.client._client.execute_mgmt.call_count, 1)

    def test_replace_requires_ingest_and_delete_before_any_io(self):
        for granted in (("ingest",), ("delete",)):
            store = AdxConnector(CONFIG, credential=object(), policy=policy(*granted))
            sdk = store.client._client = MagicMock()
            with self.subTest(granted=granted), self.assertRaises(AdxPermissionError):
                store.repository(SCHEMA).update("record_id", [{"record_id": "a", "score": 7}])
            self.assertEqual(sdk.mock_calls, [])

    def test_managed_streaming_acceptance_does_not_claim_arrival(self):
        ingestor = Ingestor(CONFIG, credential=object(), policy=policy("ingest"))
        sdk = ingestor._managed = MagicMock()
        result = ingestor.ingest_rows([{"record_id": "a", "score": 7}], "Records", SCHEMA)
        self.assertFalse(result.is_terminal)
        self.assertEqual(result.status, "accepted")
        self.assertTrue(sdk.ingest_from_stream.call_args.kwargs["ingestion_properties"].flush_immediately)

    def test_nonexistent_cluster_differs_from_forbidden_or_unknown(self):
        provisioner = AdxProvisioner(CONFIG, credential=object(), policy=policy("provision"))
        sdk = provisioner._client = MagicMock()
        sdk.clusters.get.side_effect = ResourceNotFoundError("fixture missing")
        self.assertFalse(provisioner.cluster_exists())
        for error in (HttpResponseError("fixture forbidden"), TimeoutError("fixture timeout")):
            sdk.clusters.get.side_effect = error
            with self.subTest(error=type(error).__name__), self.assertRaises(AdxProvisioningError):
                provisioner.ensure_cluster()
        sdk.clusters.begin_create_or_update.assert_not_called()

    def test_failed_database_read_does_not_provision(self):
        provisioner = AdxProvisioner(CONFIG, credential=object(), policy=policy("provision"))
        sdk = provisioner._client = MagicMock()
        sdk.databases.get.side_effect = HttpResponseError("fixture forbidden")
        with self.assertRaises(AdxProvisioningError):
            provisioner.ensure_database()
        sdk.databases.begin_create_or_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()