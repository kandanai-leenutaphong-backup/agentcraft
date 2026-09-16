import unittest
import json
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from azdata import (ConfigurationError, ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, Limits, Policy, QueryRequest, ReadRequest,
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
    async def test_read_retry_is_bounded_and_native_faults_never_expose_payload(self):
        config = ConnectorConfig("wss://fixture.gremlin.cosmos.azure.com",
            ResourceAddress({"database": "Fixture", "container": "Vertices"}),
            ("fixture.gremlin.cosmos.azure.com",), credential_kind="readonly_key")
        provider = AsyncMock(return_value="synthetic-readonly-key")
        dead, fresh = driver([]), driver([7])
        dead.submit.side_effect = RuntimeError("Connection was already closed")
        async with connect("gremlin", config, credential=Credential(),
                           policy=Policy("fixture", {"query"}, limits=Limits(max_attempts=2)),
                           gremlin_readonly_key_provider=provider) as client:
            with patch("gremlin_python.driver.client.Client", side_effect=[dead, fresh]):
                result = await client.query(QueryRequest(dialect="gremlin", expression="g.V().count()"))
            self.assertEqual(result.status, "success")
            self.assertEqual(result.metrics["attempts"], 2)
            dead.close.assert_called_once()
            fresh.close.assert_called_once()
            broken = driver([])
            broken.submit.side_effect = RuntimeError("private-query-payload")
            with patch("gremlin_python.driver.client.Client", return_value=broken) as factory:
                result = await client.query(QueryRequest(dialect="gremlin", expression="g.V().count()"))
            self.assertEqual(result.status, "failed")
            self.assertNotIn("private-query-payload", repr(result.to_dict()))
            factory.assert_called_once()

    async def test_resource_token_cannot_substitute_for_readonly_key(self):
        config = ConnectorConfig("wss://fixture.gremlin.cosmos.azure.com",
            ResourceAddress({"database": "Fixture", "container": "Vertices"}),
            ("fixture.gremlin.cosmos.azure.com",), credential_kind="readonly_key")
        async with connect("gremlin", config, credential=Credential(), policy=Policy("fixture", {"query"}),
                gremlin_readonly_key_provider=AsyncMock(return_value="type=resource&sig=synthetic")) as client:
            with patch("gremlin_python.driver.client.Client") as factory:
                result = await client.query(QueryRequest(dialect="gremlin", expression="g.V()"))
            self.assertEqual(result.status, "denied")
            factory.assert_not_called()

    async def test_readonly_key_exact_target_and_no_credential_or_mutation_fallback(self):
        credential = Credential()
        credential.close = MagicMock()
        config = ConnectorConfig("wss://fixture.gremlin.cosmos.azure.com",
            ResourceAddress({"database": "Fixture", "container": "Vertices"}),
            ("fixture.gremlin.cosmos.azure.com",), partition_key_field="site", credential_kind="readonly_key")
        provider = AsyncMock(return_value="synthetic-readonly-key")
        native = driver([{"id": "one"}])
        async with connect("gremlin", config, credential=credential,
                policy=Policy("fixture", {"query", "create", "read", "delete"}),
                gremlin_readonly_key_provider=provider) as client:
            client.describe()
            provider.assert_not_called()
            key = RecordKey({"id": "one"}, partition="run")
            for request, operation in ((CreateRequest(records=(RecordInput(key, ContentValue({"label": "Person"})),)), client.create),
                                       (DeleteRequest(keys=(key,)), client.delete)):
                result = await operation(request)
                self.assertEqual(result.status, "unsupported")
            result = await client.query(QueryRequest(dialect="gremlin", expression="g.V().drop()"))
            self.assertEqual(result.status, "denied")
            result = await client.query(QueryRequest(dialect="gremlin", expression="g.V()",
                target=ResourceAddress({"database": "Other", "container": "Vertices"})))
            self.assertEqual(result.status, "denied")
            provider.assert_not_called()
            with patch("gremlin_python.driver.client.Client", return_value=native) as factory:
                result = await client.query(QueryRequest(dialect="gremlin", expression="g.V()"))
            self.assertEqual(result.status, "success")
            provider.assert_awaited_once_with(config)
            self.assertEqual(factory.call_args.kwargs["password"], "synthetic-readonly-key")
            self.assertNotIn("synthetic-readonly-key", repr(result))
        native.close.assert_called_once()
        credential.close.assert_not_called()
        self.assertEqual(credential.calls, 0)

    async def test_readonly_key_provider_failure_is_safe_and_never_falls_back(self):
        credential = Credential()
        config = ConnectorConfig("wss://fixture.gremlin.cosmos.azure.com",
            ResourceAddress({"database": "Fixture", "container": "Vertices"}),
            ("fixture.gremlin.cosmos.azure.com",), credential_kind="readonly_key")
        with self.assertRaises(ConfigurationError):
            connect("gremlin", config, credential=credential, policy=Policy("fixture", {"query"}))
        provider = AsyncMock(side_effect=RuntimeError("private-key-value"))
        async with connect("gremlin", config, credential=credential, policy=Policy("fixture", {"query"}),
                           gremlin_readonly_key_provider=provider) as client:
            with patch("gremlin_python.driver.client.Client") as factory:
                result = await client.query(QueryRequest(dialect="gremlin", expression="g.V()"))
            self.assertEqual(result.status, "denied")
            self.assertNotIn("private-key-value", repr(result.to_dict()))
            factory.assert_not_called()
        self.assertEqual(credential.calls, 0)

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

    async def test_investigation_read_traversals_use_the_existing_native_driver(self):
        credential = Credential()
        async with connector(credential, grants={"query"}) as client:
            with patch("gremlin_python.driver.client.Client", side_effect=lambda *args, **kwargs: driver([])) as factory:
                for expression in (
                    "g.V().groupCount().by(label)",
                    "g.V().hasLabel('Host').order().by('event_count', decr).limit(40).valueMap(true)",
                    "g.E().limit(100).project('e','from','to').by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())",
                    "g.V('host').repeat(__.both().hasLabel('Host').simplePath()).times(3).emit().dedup().limit(220).valueMap(true)",
                    "g.V().has('name', TextP.containing('needle')).limit(25).valueMap(true)",
                ):
                    with self.subTest(expression=expression):
                        result = await client.query(QueryRequest(dialect="gremlin", expression=expression))
                        self.assertEqual(result.status, "success", result.errors)
                self.assertEqual(factory.call_count, 5)
        self.assertEqual(credential.calls, 5)

    async def test_unbounded_repeats_and_predicate_scripts_refuse_before_credentials(self):
        credential = Credential()
        async with connector(credential, grants={"query"}) as client:
            with patch("gremlin_python.driver.client.Client") as factory:
                for expression in (
                    "g.V().repeat(__.both()).emit()", "g.V().repeat(__.both()).times(33)",
                    "g.V().repeat(__.both()).times(0)", "g.V().repeat(__.both()).times(true)",
                    "g.V().repeat(__.drop()).times(2)", "g.V().has('name', TextP.drop())",
                    "g.V().has('name', Runtime.exec('bad'))",
                ):
                    with self.subTest(expression=expression):
                        result = await client.query(QueryRequest(dialect="gremlin", expression=expression))
                        self.assertIn(result.status, {"denied", "unsupported"})
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