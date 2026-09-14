import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from azdata import (ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, Policy, QueryRequest, ReadRequest,
                    RecordInput, RecordKey, ResourceAddress, UpdateRequest, UpsertRequest, Verification, connect)


class Credential:
    def __init__(self):
        self.scopes = []

    async def get_token(self, scope):
        self.scopes.append(scope)
        return SimpleNamespace(token="fixture", expires_on=2**31)


def connector(service, grants=None):
    host = "fixture.database.windows.net" if service == "sql" else "fixture.postgres.database.azure.com"
    protocol = "mssql" if service == "sql" else "postgresql"
    config = ConnectorConfig(f"{protocol}://{host}", ResourceAddress({"database": "Fixture", "schema": "dbo", "table": "Records"}),
                             (host,), database_user="fixture", key_fields=("id",))
    return connect(service, config, credential=Credential(), policy=Policy("fixture", grants or {"create", "read", "update", "upsert", "delete", "query"}))


class RelationalTests(unittest.IsolatedAsyncioTestCase):
    async def test_crud_is_bound_and_merge_upsert_uses_native_transaction_rules(self):
        key = RecordKey({"id": "one"})
        record = RecordInput(key, ContentValue({"title": "quote ' ; DROP TABLE X", "price": Decimal("1.20")}, kind="row"))
        for service in ("sql", "postgresql"):
            client = connector(service)
            with patch.object(client._adapter, "_run", new=AsyncMock(return_value=([], 1))) as execute:
                self.assertEqual((await client.create(CreateRequest(records=(record,)))).status, "success")
                self.assertNotIn("DROP TABLE", execute.call_args.args[0])
                self.assertIn("quote ' ; DROP TABLE X", execute.call_args.args[1])
                self.assertEqual((await client.upsert(UpsertRequest(mode="merge", records=(record,)))).status, "success")
                statement = execute.call_args.args[0]
                self.assertIn("ON CONFLICT" if service == "postgresql" else "UPDLOCK, HOLDLOCK", statement)
                self.assertEqual((await client.update(UpdateRequest(mode="replace", records=(record,)))).status, "unsupported")
                self.assertEqual((await client.delete(DeleteRequest(keys=(key,)))).status, "success")

    async def test_query_binding_and_scope_are_shared(self):
        for service, dialect in (("sql", "tsql"), ("postgresql", "postgresql")):
            client = connector(service)
            with patch.object(client._adapter, "_run", new=AsyncMock(return_value=([{"id": "one"}], 1))) as execute:
                result = await client.query(QueryRequest(dialect=dialect, expression="SELECT id FROM Records WHERE id = :wanted", parameters={"wanted": "one"}))
                self.assertEqual(result.status, "success", result.errors)
                self.assertEqual(execute.call_args.args[1], ("one",))
                self.assertNotIn("'one'", execute.call_args.args[0])
                self.assertTrue(execute.call_args.kwargs["readonly"])
                for expression in ("DELETE FROM Records", "SELECT * FROM Other", "SELECT * INTO Stolen FROM Records", "SELECT pg_sleep(5)", "SELECT * FROM Records; DELETE FROM Records"):
                    prior = execute.await_count
                    self.assertIn((await client.query(QueryRequest(dialect=dialect, expression=expression))).status, {"denied", "unsupported"})
                    self.assertEqual(execute.await_count, prior)

    async def test_read_identity_and_content_merge_verification(self):
        for service in ("sql", "postgresql"):
            client = connector(service)
            key = RecordKey({"id": 1})
            with patch.object(client._adapter, "_run", new=AsyncMock(side_effect=[([], 1), ([{"id": 1, "title": "new", "other": "retained"}], 1)])):
                result = await client.update(UpdateRequest(mode="merge", records=(RecordInput(key, ContentValue({"title": "new"})),), verification=Verification("content")))
                self.assertEqual(result.status, "success")
                self.assertEqual(result.verification.state, "satisfied")
            with patch.object(client._adapter, "_run", new=AsyncMock(return_value=([{"id": 2}], 1))):
                self.assertEqual((await client.read(ReadRequest(keys=(key,)))).status, "unknown")

    async def test_postgres_driver_uses_tls_fresh_token_and_readonly_transaction(self):
        client = connector("postgresql")
        connection = MagicMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock()
        transaction.__aexit__ = AsyncMock(return_value=False)
        connection.transaction.return_value = transaction
        cursor = MagicMock(rowcount=1)
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=False)
        cursor.execute = AsyncMock()
        cursor.fetchmany = AsyncMock(return_value=[{"id": "one"}])
        connection.cursor.return_value = cursor
        connection.close = AsyncMock()
        with patch("psycopg.AsyncConnection.connect", new=AsyncMock(return_value=connection)) as native:
            result = await client.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
            self.assertEqual(result.status, "success", result.errors)
            self.assertEqual(native.call_args.kwargs["sslmode"], "verify-full")
            self.assertEqual(native.call_args.kwargs["password"], "fixture")
            self.assertEqual(cursor.execute.call_args_list[0].args, ("SET TRANSACTION READ ONLY",))
            connection.close.assert_awaited_once()
        await client.aclose()

    async def test_sql_driver_uses_token_provider_parameters_and_closes(self):
        client = connector("sql")
        cursor = MagicMock(description=[("id",)], rowcount=1)
        cursor.fetchmany.return_value = [("one",)]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with patch("mssql_python.connect", return_value=connection) as native:
            result = await client.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
            self.assertEqual(result.status, "success", result.errors)
            self.assertIn("Encrypt=yes;TrustServerCertificate=no", native.call_args.args[0])
            self.assertNotIn("fixture;", native.call_args.args[0])
            self.assertEqual(cursor.execute.call_args.args[1], ("one",))
            connection.close.assert_called_once()
            cursor.close.assert_called_once()
        await client.aclose()


if __name__ == "__main__":
    unittest.main()