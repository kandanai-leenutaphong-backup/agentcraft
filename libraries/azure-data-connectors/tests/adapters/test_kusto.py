import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from azdata import (ConfigurationError, ConnectorConfig, ContentValue, HttpResponse, IngestRequest, Policy, QueryRequest,
                    ResourceAddress, SchemaRequest, Verification, connect)
from azdata.event_store import AdxIdentifierError, validate_identifier
from tests.adapters.test_storage import Scripted


class Credential:
    def __init__(self):
        self.scopes = []

    async def get_token(self, scope):
        assert scope == "https://kusto.kusto.windows.net/.default"
        self.scopes.append(scope)
        return SimpleNamespace(token="fixture", expires_on=2**31)


def connector(service, transport, grants=None, credential=None):
    host = "fixture.eastus2.kusto.windows.net" if service == "adx" else "fixture.z1.kusto.fabric.microsoft.com"
    return connect(service, ConnectorConfig(f"https://{host}", ResourceAddress({"database": "Fixture", "table": "Events"}), (host,)),
                   credential=credential or Credential(), transport=transport, policy=Policy("fixture", grants or {"query", "ingest", "schema.read"}))


def dataset(rows=None):
    return [{"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
             "Columns": [{"ColumnName": "value", "ColumnType": "long"}], "Rows": [[2]] if rows is None else rows},
            {"FrameType": "DataSetCompletion", "HasErrors": False}]


class KustoTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_parameters_are_declared_without_interpolating_values(self):
        moment = datetime(2026, 8, 13, tzinfo=timezone.utc)
        hostile = "host'; .drop table Events"
        transport = Scripted(HttpResponse(200, dataset()))
        async with connector("adx", transport) as client:
            result = await client.query(QueryRequest(dialect="kql",
                expression="Events | where source_time >= start and name == host",
                parameters={"start": moment, "host": hostile, "ids": ["a", "b"]}))
        self.assertEqual(result.status, "success", result.errors)
        request = transport.requests[0]
        self.assertTrue(request.body["csl"].startswith("declare query_parameters(start:datetime, host:string, ids:dynamic);"))
        self.assertNotIn(hostile, request.body["csl"])
        values = json.loads(request.body["properties"])["Parameters"]
        self.assertEqual(values["start"], moment.isoformat())
        self.assertEqual(values["host"], hostile)
        self.assertEqual(json.loads(values["ids"]), ["a", "b"])

    async def test_shared_identifier_boundary_refuses_reserved_and_trailing_text(self):
        for name in ("where", "record\n", "record; .drop table Events", "record name"):
            with self.subTest(name=name), self.assertRaises(AdxIdentifierError):
                validate_identifier(name)
            transport = Scripted()
            async with connector("adx", transport) as client:
                result = await client.query(QueryRequest(dialect="kql", expression="print value=7", parameters={name: 1}))
            self.assertEqual(result.status, "invalid")
            self.assertFalse(transport.requests)
            with self.assertRaises(ConfigurationError):
                connect("adx", ConnectorConfig("https://fixture.kusto.windows.net", ResourceAddress({"database": name}),
                                               ("fixture.kusto.windows.net",)),
                    credential=Credential(), policy=Policy("fixture"))

    async def test_pipeline_authenticates_before_transport(self):
        for service in ("adx", "eventhouse"):
            credential = Credential()
            transport = Scripted(HttpResponse(200, dataset()))
            async with connector(service, transport, credential=credential) as client:
                result = await client.query(QueryRequest(dialect="kql", expression="Events"))
            self.assertEqual(result.status, "success")
            self.assertEqual(credential.scopes, ["https://kusto.kusto.windows.net/.default"])
            self.assertEqual(transport.requests[0].headers["Authorization"], "Bearer fixture")

    async def test_invalid_credential_refuses_before_transport(self):
        class InvalidCredential:
            async def get_token(self, scope):
                return SimpleNamespace(token="", expires_on=0)

        for service in ("adx", "eventhouse"):
            transport = Scripted()
            async with connector(service, transport, credential=InvalidCredential()) as client:
                result = await client.query(QueryRequest(dialect="kql", expression="Events"))
            self.assertEqual(result.status, "denied")
            self.assertEqual(result.errors[0].code, "credential_unavailable")
            self.assertFalse(transport.requests)

    async def test_both_profiles_share_native_query_and_safe_bounds(self):
        for service in ("adx", "eventhouse"):
            transport = Scripted(HttpResponse(200, dataset()))
            client = connector(service, transport)
            result = await client.query(QueryRequest(dialect="kql", expression="declare query_parameters(minimum:long); Events | where value > minimum", parameters={"minimum": 1}))
            self.assertEqual(result.status, "success", result.errors)
            self.assertEqual(result.items[0].content.data["value"], 2)
            properties = json.loads(transport.requests[0].body["properties"])
            self.assertTrue(properties["Options"]["request_readonly"])
            self.assertTrue(properties["Options"]["request_remote_entities_disabled"])
            self.assertEqual(properties["Parameters"], {"minimum": 1})
            self.assertIn("/v2/rest/query", transport.requests[0].url)
            await client.aclose()

    async def test_streaming_ingestion_is_acknowledgment_not_verified_content(self):
        for service in ("adx", "eventhouse"):
            transport = Scripted(HttpResponse(200, {}))
            client = connector(service, transport)
            content = ContentValue(({"value": 2}, {"value": 3}))
            refusal = await client.ingest(IngestRequest(content=content, verification=Verification("content")))
            self.assertEqual(refusal.status, "unsupported")
            self.assertFalse(transport.requests)
            result = await client.ingest(IngestRequest(content=content, verification=Verification("acknowledgment")))
            self.assertEqual(result.status, "success", result.errors)
            self.assertEqual(result.items[0].effect, "accepted")
            self.assertEqual(transport.requests[0].body, b'{"value":2}\n{"value":3}')
            self.assertIn("streamFormat=multijson", transport.requests[0].url)
            await client.aclose()

    async def test_query_commands_and_write_policy_refuse_before_io(self):
        transport = Scripted()
        client = connector("adx", transport, {"query"})
        self.assertEqual((await client.query(QueryRequest(dialect="kql", expression=".drop table Events"))).status, "denied")
        self.assertEqual((await client.ingest(IngestRequest(content=ContentValue(({"value": 1},))))).status, "denied")
        self.assertFalse(transport.requests)

    async def test_provider_partial_errors_are_not_success(self):
        payload = dataset()
        payload[-1]["HasErrors"] = True
        result = await connector("adx", Scripted(HttpResponse(200, payload))).query(QueryRequest(dialect="kql", expression="Events"))
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.errors[0].code, "kusto_partial_error")

    async def test_schema_read_is_separately_granted(self):
        body = {"Tables": [{"Columns": [{"ColumnName": "Schema", "ColumnType": "string"}], "Rows": [["fixture"]]}]}
        transport = Scripted(HttpResponse(200, body))
        result = await connector("adx", transport).schema(SchemaRequest(action="read", verification=Verification("schema")))
        self.assertEqual(result.status, "success", result.errors)
        self.assertEqual(result.verification.state, "satisfied")
        self.assertEqual(transport.requests[0].body["csl"], ".show table Events schema as json")


if __name__ == "__main__":
    unittest.main()