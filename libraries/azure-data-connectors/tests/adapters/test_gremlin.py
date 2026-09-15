import unittest
import json
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from azdata import (ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, Policy, QueryRequest, ReadRequest,
                    RecordInput, RecordKey, ResourceAddress, UpdateRequest, Verification, connect)


class Credential:
    def __init__(self, token="type=resource&ver=1&sig=synthetic"):
        self.token = token
        self.calls = 0

    async def get_token(self, scope):
        assert scope == "https://cosmos.azure.com/.default"
        self.calls += 1
        return SimpleNamespace(token=self.token, expires_on=2**31)


def connector(credential=None, kind="resource_token", grants=None):
    config = ConnectorConfig("wss://fixture.gremlin.cosmos.azure.com", ResourceAddress({"database": "Fixture", "container": "Vertices"}),
        ("fixture.gremlin.cosmos.azure.com",), partition_key_field="site", credential_kind=kind)
    return connect("gremlin", config, credential=credential or Credential(),
                   policy=Policy("fixture", grants or {"create", "read", "update", "delete", "query"}))


def driver(rows):
    client = MagicMock()
    future = Future()
    future.set_result(rows)
    client.submit.return_value.all.return_value = future
    return client


class GremlinTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_driver_serializes_eval_and_resource_token_authentication(self):
        class Wire:
            closed = False
            def __init__(self):
                self.messages = []
            def connect(self, url, headers=None):
                self.url = url
            def write(self, message):
                self.messages.append(json.loads(message[message[0] + 1:]))
            def read(self):
                message = self.messages[-1]
                authentication = message["op"] == "authentication"
                request_id = message["requestId"]
                if isinstance(request_id, dict):
                    request_id = request_id["@value"]
                return json.dumps({"requestId": request_id, "status": {"code": 200 if authentication else 407, "message": "", "attributes": {}},
                    "result": {"data": [{"id": "one"}] if authentication else [], "meta": {}}}).encode()
            def close(self):
                self.closed = True
        wire = Wire()
        client = connector()
        with patch("azdata.adapters.gremlin_transport.GremlinTransport", return_value=wire):
            result = await client.query(QueryRequest(dialect="gremlin", expression="g.V().has('id', wanted)", parameters={"wanted": "one"}))
        self.assertEqual(result.status, "success", result.errors)
        self.assertEqual(result.items[0].content.data["id"], "one")
        self.assertEqual([message["op"] for message in wire.messages], ["eval", "authentication"])
        self.assertIn("limit(101)", wire.messages[0]["args"]["gremlin"])
        self.assertTrue(wire.closed)
        await client.aclose()

    async def test_resource_token_scope_graphson_and_safe_query_literals(self):
        credential = Credential()
        client = connector(credential)
        native = driver([{"id": "one"}])
        with patch("gremlin_python.driver.client.Client", return_value=native) as factory:
            request = QueryRequest(dialect="gremlin", expression="g.V().has('name', wanted).out('knows').in('knows')", parameters={"wanted": "${g.V().drop()}"})
            result = await client.query(request)
            self.assertEqual(result.status, "success", result.errors)
            self.assertIn("\\$", native.submit.call_args.args[0])
            self.assertTrue(native.submit.call_args.args[0].endswith(".limit(101)"))
            self.assertEqual(factory.call_args.kwargs["username"], "/dbs/Fixture/colls/Vertices")
            self.assertEqual(factory.call_args.kwargs["message_serializer"].version, b"application/vnd.gremlin-v2.0+json")
            native.close.assert_called_once()
        self.assertEqual(credential.calls, 1)
        await client.aclose()

    async def test_mutation_scripts_and_undocumented_auth_refuse_before_token(self):
        credential = Credential()
        client = connector(credential)
        for expression in ("g.V().drop()", "g.V().sideEffect(__.drop())", "g.V(); g.addV('X')", "__import__('os').system('x')", "g.V().map(lambda value: value)"):
            self.assertIn((await client.query(QueryRequest(dialect="gremlin", expression=expression))).status, {"denied", "unsupported"})
        result = await connector(credential, kind="entra").query(QueryRequest(dialect="gremlin", expression="g.V()"))
        self.assertEqual(result.status, "unsupported")
        self.assertEqual(credential.calls, 0)
        with patch("gremlin_python.driver.client.Client") as factory:
            result = await connector(Credential("account-key-shaped-value")).query(QueryRequest(dialect="gremlin", expression="g.V()"))
            self.assertEqual(result.status, "denied")
            factory.assert_not_called()

    async def test_vertex_create_and_partition_readback(self):
        client = connector()
        vertex = {"id": "one", "label": "Person", "properties": {"site": [{"value": "run"}], "name": [{"value": "Ada"}]}}
        native_write, native_read = driver([1]), driver([vertex])
        key = RecordKey({"id": "one"}, partition="run")
        with patch("gremlin_python.driver.client.Client", side_effect=[native_write, native_read]):
            result = await client.create(CreateRequest(records=(RecordInput(key, ContentValue({"label": "Person", "name": "Ada"})),), verification=Verification("content")))
            self.assertEqual(result.status, "success", result.errors)
            self.assertEqual(result.verification.state, "satisfied")
            self.assertIn("g.addV", native_write.submit.call_args.args[0])
            self.assertIn('g.V(["run","one"])', native_read.submit.call_args.args[0])
        await client.aclose()

    async def test_investigation_traversals_refuse_before_credentials_or_driver(self):
        credential = Credential()
        async with connector(credential, grants={"query"}) as client:
            with patch("gremlin_python.driver.client.Client") as factory:
                for expression in (
                    "g.V().groupCount().by(label)",
                    "g.V().hasLabel('Host').order().by('event_count', decr).limit(40).valueMap(true)",
                    "g.E().limit(100).project('e','from','to').by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())",
                ):
                    with self.subTest(expression=expression):
                        result = await client.query(QueryRequest(dialect="gremlin", expression=expression))
                        self.assertEqual(result.status, "denied")
                        self.assertEqual(result.errors[0].code, "gremlin_script_refused")
                factory.assert_not_called()
        self.assertEqual(credential.calls, 0)

    async def test_merge_does_not_create_and_delete_missing_is_explicit(self):
        client = connector()
        key = RecordKey({"id": "missing"}, partition="run")
        with patch("gremlin_python.driver.client.Client", side_effect=[driver([0]), driver([0])]):
            result = await client.update(UpdateRequest(mode="merge", records=(RecordInput(key, ContentValue({"name": "new"})),)))
            self.assertEqual(result.status, "not_found")
            result = await client.delete(DeleteRequest(keys=(key,), missing="ok"))
            self.assertEqual(result.status, "success")
        await client.aclose()


if __name__ == "__main__":
    unittest.main()