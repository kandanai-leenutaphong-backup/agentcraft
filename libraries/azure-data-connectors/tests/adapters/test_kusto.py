import json
import unittest
from types import SimpleNamespace

from azdata import (ConnectorConfig, ContentValue, HttpResponse, IngestRequest, Policy, QueryRequest,
                    ResourceAddress, SchemaRequest, Verification, connect)
from tests.adapters.test_storage import Scripted


class Credential:
    async def get_token(self, scope):
        assert scope == "https://kusto.kusto.windows.net/.default"
        return SimpleNamespace(token="fixture", expires_on=2**31)


def connector(service, transport, grants=None):
    host = "fixture.eastus2.kusto.windows.net" if service == "adx" else "fixture.z1.kusto.fabric.microsoft.com"
    return connect(service, ConnectorConfig(f"https://{host}", ResourceAddress({"database": "Fixture", "table": "Events"}), (host,)),
                   credential=Credential(), transport=transport, policy=Policy("fixture", grants or {"query", "ingest", "schema.read"}))


def dataset(rows=None):
    return [{"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
             "Columns": [{"ColumnName": "value", "ColumnType": "long"}], "Rows": [[2]] if rows is None else rows},
            {"FrameType": "DataSetCompletion", "HasErrors": False}]


class KustoTests(unittest.IsolatedAsyncioTestCase):
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