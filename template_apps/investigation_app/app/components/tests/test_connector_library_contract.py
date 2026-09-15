"""The migrated connector API, frozen at the shape its callers were written against.

The superseded `app/data/data_connectors` package is gone, so parity can no longer be a
diff. What survives it is the contract: the public call signatures every pipeline, battery
and deployment script already depends on, and the names the two old barrels exported, which
must all still resolve from the one library barrel.

These are deliberately API-level, not byte-level. Changing a body here is free; changing a
public signature or dropping an exported name is a breaking change and fails this test.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import unittest
from pathlib import Path

import app.components.data_connector_library as library

REPO_ROOT = Path(__file__).resolve().parents[3]
SUPERSEDED_PATH = REPO_ROOT / "app" / "data" / "data_connectors"
SUPERSEDED_MODULE = "app.data.data_connectors"

#: Captured from the superseded package at migration, before it was deleted.
MIGRATED_API: dict[str, dict[str, str]] = {
    "AdxConnector": {
        "close": "(self) -> 'None'",
        "command": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, **kwargs: 'Any') -> 'QueryResult'",
        "create_table": "(self, schema: 'TableSchema', *, mapping_name: 'str | None' = None) -> 'TableSchema'",
        "enable_streaming": "(self, table: 'str') -> 'QueryResult'",
        "ensure_infrastructure": "(self, *, wait: 'bool' = True) -> 'ClusterInfo'",
        "from_env": "(credential: 'Any | None' = None, **overrides: 'object') -> \"'AdxConnector'\"",
        "health": "(self) -> 'dict[str, Any]'",
        "infer_schema_from_csv": "(self, csv_path: 'Path', table_name: 'str', **kwargs: 'Any') -> 'TableSchema'",
        "ingestion_failures": "(self, *, hours: 'int' = 1) -> 'QueryResult'",
        "iter_pages": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, **kwargs: 'Any')",
        "list_tables": "(self) -> 'list[str]'",
        "query": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, **kwargs: 'Any') -> 'QueryResult'",
        "repository": "(self, schema: 'TableSchema') -> 'CrudRepository'",
        "set_batching_latency": "(self, table: 'str', seconds: 'int') -> 'QueryResult'",
        "table_schema": "(self, table_name: 'str') -> 'TableSchema'",
        "wait_for_rows": "(self, table: 'str', expected: 'int', *, timeout_seconds: 'int' = 600, poll_seconds: 'int' = 5) -> 'int'",
    },
    "AdxClient": {
        "close": "(self) -> 'None'",
        "command": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, *, timeout_seconds: 'int | None' = None, client_request_id: 'str | None' = None) -> 'QueryResult'",
        "declare_parameters": "(parameters: 'Mapping[str, Any] | None') -> 'str'",
        "iter_pages": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, *, page_size: 'int' = 10000, order_by: 'Sequence[str]' = ('source_time asc', 'resource_id asc')) -> 'Iterator[QueryResult]'",
        "ping": "(self) -> 'bool'",
        "query": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, *, timeout_seconds: 'int | None' = None, declare: 'bool' = True, client_request_id: 'str | None' = None) -> 'QueryResult'",
        "scalar": "(self, kql: 'str', parameters: 'Mapping[str, Any] | None' = None, default: 'Any' = None) -> 'Any'",
    },
    "CrudRepository": {
        "count": "(self, *, where: 'str' = '', parameters: 'Mapping[str, Any] | None' = None) -> 'int'",
        "delete_in": "(self, key_column: 'str', keys: 'Sequence[Any]', *, chunk: 'int' = 500) -> 'int'",
        "delete_where": "(self, predicate: 'str', parameters: 'Mapping[str, Any] | None' = None) -> 'int'",
        "drop": "(self, *, confirm: 'str' = '') -> 'QueryResult'",
        "drop_by_tag": "(self, tag: 'str') -> 'QueryResult'",
        "exists": "(self, key_column: 'str', key_value: 'Any') -> 'bool'",
        "extents": "(self) -> 'QueryResult'",
        "get": "(self, key_column: 'str', key_value: 'Any') -> 'dict[str, Any] | None'",
        "latest_by": "(self, key_column: 'str', version_column: 'str', *, where: 'str' = '', parameters: 'Mapping[str, Any] | None' = None, limit: 'int | None' = 1000) -> 'QueryResult'",
        "new_batch_tag": "(prefix: 'str' = 'batch') -> 'str'",
        "purge_where": "(self, predicate: 'str', *, confirm: 'bool' = False) -> 'QueryResult'",
        "read": "(self, *, where: 'str' = '', parameters: 'Mapping[str, Any] | None' = None, project: 'Sequence[str]' = (), order_by: 'str' = '', limit: 'int | None' = 1000) -> 'QueryResult'",
        "truncate": "(self, *, confirm: 'str' = '') -> 'QueryResult'",
    },
    "Ingestor": {
        "close": "(self) -> 'None'",
        "inline_command": "(table: 'str', schema: 'TableSchema', rows: 'Sequence[Mapping[str, Any]]') -> 'str'",
    },
    "AdxProvisioner": {
        "cluster_exists": "(self) -> 'bool'",
        "ensure_cluster": "(self, *, streaming_ingestion: 'bool' = True, wait: 'bool' = True) -> 'ClusterInfo'",
        "ensure_database": "(self, *, hot_cache_days: 'int' = 31, retention_days: 'int' = 365) -> 'bool'",
        "teardown_cluster": "(self, *, confirm: 'str' = '') -> 'None'",
        "wait_for_running": "(self, *, timeout_seconds: 'int' = 1800, poll_seconds: 'int' = 20) -> 'str'",
    },
    "AdxConfig": {
        "from_env": "(**overrides: 'object') -> \"'AdxConfig'\"",
        "require_provisioning_fields": "(self) -> 'tuple[str, str, str]'",
    },
    "GremlinGraph": {
        "close": "(self) -> 'None'",
        "counts": "(self) -> 'dict[str, int]'",
        "drop_all": "(self) -> 'None'",
        "label_counts": "(self) -> 'dict[str, dict[str, int]]'",
        "submit": "(self, script: 'str', bindings: 'dict[str, Any] | None' = None) -> 'list[Any]'",
        "upsert_edges": "(self, edges: 'Sequence[dict[str, Any]]') -> 'int'",
        "upsert_vertices": "(self, vertices: 'Sequence[dict[str, Any]]') -> 'int'",
    },
    "GremlinSettings": {
        "from_env": "() -> 'GremlinSettings'",
    },
}

#: `__all__` of the two superseded barrels, captured the same way.
SUPERSEDED_EXPORTS = {
    "adx_connector": (
        "AdxAuthError", "AdxClient", "AdxConfig", "AdxConfigError", "AdxConnector",
        "AdxError", "AdxIdentifierError", "AdxIngestionError", "AdxProvisioner",
        "AdxProvisioningError", "AdxQueryError", "AdxTimeoutError", "ColumnSpec",
        "IngestMode", "IngestResult", "QueryResult", "TableSchema",
    ),
    "gremlin_connector": (
        "DEFAULT_BATCH", "GremlinError", "GremlinGraph", "GremlinSettings",
        "PROPERTY_TEXT_LIMIT", "encode_properties",
    ),
}


def public_signatures(obj: type) -> dict[str, str]:
    return {
        name: str(inspect.signature(member))
        for name, member in inspect.getmembers(obj, callable)
        if not name.startswith("_")
    }


class MigratedApiContractTests(unittest.TestCase):
    def test_public_signatures_are_the_ones_callers_were_written_against(self) -> None:
        for name, expected in MIGRATED_API.items():
            with self.subTest(symbol=name):
                actual = public_signatures(getattr(library, name))
                # A superset is allowed: added methods break nobody, changed ones do.
                self.assertEqual(expected, {k: v for k, v in actual.items() if k in expected})
                self.assertEqual(set(), set(expected) - set(actual))

    def test_every_name_the_old_barrels_exported_resolves_from_the_library_barrel(self) -> None:
        for package, names in SUPERSEDED_EXPORTS.items():
            for name in names:
                with self.subTest(package=package, name=name):
                    self.assertIn(name, library.__all__)
                    self.assertIsNotNone(getattr(library, name))

    def test_the_superseded_package_is_gone_and_unimportable(self) -> None:
        self.assertFalse(SUPERSEDED_PATH.exists(), f"{SUPERSEDED_PATH} is back")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module(SUPERSEDED_MODULE)


if __name__ == "__main__":
    unittest.main()
