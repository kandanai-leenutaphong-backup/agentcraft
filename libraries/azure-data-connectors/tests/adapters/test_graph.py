import unittest
from types import SimpleNamespace

from azdata import (ConnectorConfig, HttpResponse, IngestRequest, Policy, QueryRequest, ResourceAddress,
                    SchemaRequest, StatusRequest, Verification, connect)
from tests.adapters.test_storage import Scripted

WORKSPACE = "11111111-1111-4111-8111-111111111111"
MODEL = "22222222-2222-4222-8222-222222222222"
JOB = "33333333-3333-4333-8333-333333333333"


class Credential:
    async def get_token(self, scope):
        assert scope == "https://api.fabric.microsoft.com/.default"
        return SimpleNamespace(token="fixture", expires_on=2**31)


def connector(transport, *, preview=True, grants=None):
    config = ConnectorConfig("https://api.fabric.microsoft.com", ResourceAddress({"workspace": WORKSPACE, "graph_model": MODEL}),
                             ("api.fabric.microsoft.com",), enable_preview=preview)
    return connect("graph", config, credential=Credential(), transport=transport,
                   policy=Policy("fixture", grants or {"query", "ingest", "status", "schema.read"}))


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_gql_status_and_data_shape(self):
        payload = {"status": {"code": "00000"}, "result": {"kind": "TABLE", "columns": [{"name": "name"}], "data": [{"name": "one"}]}, "continuationToken": "next"}
        transport = Scripted(HttpResponse(200, payload), HttpResponse(200, {**payload, "continuationToken": None}), HttpResponse(200, {"status": {"code": "error"}}))
        client = connector(transport)
        result = await client.query(QueryRequest(dialect="gql", expression="MATCH (node) RETURN node.name AS name LIMIT 10"))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.items[0].content.data["name"], "one")
        self.assertTrue(result.continuation)
        self.assertIn("beta=true", transport.requests[0].url)
        following = await client.query(QueryRequest(dialect="gql", expression="MATCH (node) RETURN node.name AS name LIMIT 10", continuation=result.continuation))
        self.assertEqual(following.status, "success")
        self.assertIn("continuationToken=next", transport.requests[1].url)
        self.assertEqual((await client.query(QueryRequest(dialect="gql", expression="RETURN 1"))).status, "failed")

    async def test_refresh_reference_is_scoped_and_status_reads_native_job(self):
        location = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/items/{MODEL}/jobs/instances/{JOB}"
        transport = Scripted(HttpResponse(202, headers={"Location": location}), HttpResponse(200, {"status": "Completed"}))
        client = connector(transport)
        result = await client.ingest(IngestRequest(format="refresh", verification=Verification("acknowledgment")))
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.items[0].effect, "accepted")
        other = connector(Scripted())
        self.assertEqual((await other.status(StatusRequest(operation_ref=result.operation_ref))).status, "invalid")
        status = await client.status(StatusRequest(operation_ref=result.operation_ref))
        self.assertEqual(status.status, "success")
        self.assertEqual(transport.requests[-1].url, location)
        self.assertEqual(status.verification.achieved, "none")

    async def test_preview_mutation_and_foreign_job_locations_refuse(self):
        transport = Scripted()
        result = await connector(transport, preview=False).query(QueryRequest(dialect="gql", expression="RETURN 1"))
        self.assertEqual(result.status, "unsupported")
        self.assertFalse(transport.requests)
        self.assertEqual((await connector(transport).query(QueryRequest(dialect="gql", expression="MATCH (node) DELETE node"))).status, "denied")
        result = await connector(Scripted(HttpResponse(202, headers={"Location": "https://other.example/job"}))).ingest(IngestRequest(format="refresh"))
        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.operation_ref)

    async def test_retry_after_suppresses_early_status_network_call(self):
        location = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/items/{MODEL}/jobs/instances/{JOB}"
        transport = Scripted(HttpResponse(202, headers={"Location": location, "Retry-After": "60"}))
        client = connector(transport)
        result = await client.ingest(IngestRequest(format="refresh"))
        status = await client.status(StatusRequest(operation_ref=result.operation_ref))
        self.assertEqual(status.status, "pending")
        self.assertEqual(len(transport.requests), 1)

    async def test_schema_reads_native_definition(self):
        transport = Scripted(HttpResponse(200, {"definition": {"parts": []}}))
        result = await connector(transport).schema(SchemaRequest(action="read"))
        self.assertEqual(result.status, "success")
        self.assertTrue(transport.requests[0].url.endswith("/getDefinition"))

    async def test_subsequent_poll_honors_new_retry_after(self):
        location = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/items/{MODEL}/jobs/instances/{JOB}"
        transport = Scripted(HttpResponse(202, headers={"Location": location}), HttpResponse(200, {"status": "InProgress"}, {"Retry-After": "60"}))
        client = connector(transport)
        started = await client.ingest(IngestRequest(format="refresh"))
        pending = await client.status(StatusRequest(operation_ref=started.operation_ref))
        repeated = await client.status(StatusRequest(operation_ref=pending.operation_ref))
        self.assertEqual(repeated.status, "pending")
        self.assertEqual(len(transport.requests), 2)


if __name__ == "__main__":
    unittest.main()