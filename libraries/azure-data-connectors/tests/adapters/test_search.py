import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from azdata import (
    ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, HttpResponse, Limits,
    Policy, QueryRequest, ReadRequest, RecordInput, RecordKey, ResourceAddress, SchemaRequest,
    UpdateRequest, UpsertRequest, Verification, confirmation_digest, connect,
)


class Credential:
    def __init__(self):
        self.calls = 0

    def get_token(self, scope):
        self.calls += 1
        return SimpleNamespace(token="fixture-token", expires_on=2**31)


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def request(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def record(key="one", **fields):
    return RecordInput(RecordKey({"id": key}), ContentValue(fields))


def accepted(*keys):
    return HttpResponse(200, {"value": [{"key": key, "status": True, "statusCode": 200} for key in keys]})


class SearchTests(unittest.IsolatedAsyncioTestCase):
    def connector(self, *responses, policy=None, readable=("id", "title")):
        self.transport = ScriptedTransport(*responses)
        self.credential = Credential()
        config = ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}),
                                 ("unit.search.windows.net",), retrievable_fields=readable)
        return connect("search", config, credential=self.credential,
                       policy=policy or Policy(principal="fixture", grants={"read", "query", "create", "update", "upsert", "delete", "schema.read", "schema.create", "schema.update"}),
                       transport=self.transport)

    async def test_atomic_create_refuses_without_io(self):
        connector = self.connector()
        result = await connector.create(CreateRequest(records=(record(title="new"),)))
        self.assertEqual(result.status, "unsupported")
        self.assertEqual(self.credential.calls, 0)
        self.assertFalse(self.transport.requests)

    async def test_merge_replace_and_update_use_distinct_native_actions(self):
        connector = self.connector(accepted("one"), accepted("one"), accepted("one"))
        for request, method, action in ((UpsertRequest(mode="merge", records=(record(),)), connector.upsert, "mergeOrUpload"),
                                        (UpsertRequest(mode="replace", records=(record(),)), connector.upsert, "upload"),
                                        (UpdateRequest(mode="merge", records=(record(),)), connector.update, "merge")):
            result = await method(request)
            self.assertEqual(result.status, "success")
            self.assertEqual(self.transport.requests[-1].body["value"][0]["@search.action"], action)
        self.assertEqual(self.credential.calls, 1)

    async def test_replace_update_and_reserved_actions_refuse(self):
        connector = self.connector()
        result = await connector.update(UpdateRequest(mode="replace", records=(record(),)))
        self.assertEqual(result.status, "unsupported")
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(**{"@search.action": "delete"}),)))
        self.assertEqual(result.status, "invalid")
        self.assertFalse(self.transport.requests)

    async def test_partial_batch_preserves_order_and_safe_errors(self):
        connector = self.connector(HttpResponse(207, {"value": [
            {"key": "two", "status": False, "statusCode": 400, "errorMessage": "private-payload"},
            {"key": "one", "status": True, "statusCode": 200},
        ]}))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record("one"), record("two"))))
        self.assertEqual(result.status, "partial")
        self.assertEqual([item.key.parts["id"] for item in result.items], ["one", "two"])
        self.assertNotIn("private-payload", repr(result))

    async def test_missing_acknowledgment_is_unknown_not_success(self):
        connector = self.connector(accepted("one"))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record("one"), record("two"))))
        self.assertEqual(result.status, "partial")
        self.assertEqual([item.status for item in result.items], ["success", "unknown"])
        self.assertEqual(len(result.items), 2)

    async def test_existing_stale_content_is_not_verified(self):
        connector = self.connector(accepted("one"), HttpResponse(200, {"id": "one", "title": "old"}))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(title="new"),),
                                                     verification=Verification("content", attempts=1)))
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.items[0].verification.achieved, "acknowledgment")

    async def test_matching_content_is_verified(self):
        connector = self.connector(accepted("one"), HttpResponse(200, {"id": "one", "title": "new"}))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(title="new"),), verification=Verification("content")))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification.state, "satisfied")

    async def test_unreadable_content_refuses_before_write(self):
        connector = self.connector(readable=("id",))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(title="new"),), verification=Verification("content")))
        self.assertEqual(result.status, "unsupported")
        self.assertFalse(self.transport.requests)

    async def test_policy_minimum_cannot_be_lowered(self):
        policy = Policy(principal="fixture", grants={"read", "upsert"}, minimum_verification={"upsert": "content"})
        connector = self.connector(policy=policy)
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(),), verification=Verification("presence")))
        self.assertEqual(result.status, "denied")
        self.assertFalse(self.transport.requests)

    async def test_timeout_after_submission_is_unknown_and_not_retried(self):
        connector = self.connector(TimeoutError())
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(),)))
        self.assertEqual(result.status, "unknown")
        self.assertEqual(len(self.transport.requests), 1)

    async def test_delete_requires_explicit_missing_ok_and_reads_back(self):
        connector = self.connector(accepted("one"), HttpResponse(404))
        result = await connector.delete(DeleteRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "unsupported")
        result = await connector.delete(DeleteRequest(keys=(RecordKey({"id": "one"}),), missing="ok", verification=Verification("absence")))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification.achieved, "absence")

    async def test_query_options_and_scoped_continuation(self):
        connector = self.connector(HttpResponse(200, {"value": [{"id": "one"}]}), HttpResponse(200, {"value": []}))
        query = QueryRequest(dialect="search", expression="example", limits=Limits(max_items=1),
                             service_options={"search": {"queryType": "semantic", "semanticConfiguration": "fixture"}})
        result = await connector.query(query)
        self.assertIsNotNone(result.continuation)
        bad = await connector.query(QueryRequest(dialect="search", expression="changed", continuation=result.continuation))
        self.assertEqual(bad.status, "invalid")
        from dataclasses import replace
        final = await connector.query(replace(query, continuation=result.continuation))
        self.assertEqual(final.status, "success")
        self.assertIsNone(final.continuation)
        self.assertEqual(self.transport.requests[1].body["skip"], 1)

    async def test_schema_create_is_conditional_and_read_back(self):
        definition = {"name": "fixture", "fields": [{"name": "id", "type": "Edm.String", "key": True}]}
        connector = self.connector(HttpResponse(201, definition), HttpResponse(200, definition))
        result = await connector.schema(SchemaRequest(action="create", definition=definition))
        self.assertEqual(result.status, "success")
        self.assertEqual(self.transport.requests[0].headers["If-None-Match"], "*")
        self.assertEqual(result.verification.achieved, "schema")

    async def test_schema_readback_accepts_provider_defaults_not_missing_requested_fields(self):
        definition = {"name": "fixture", "fields": [{"name": "id", "type": "Edm.String", "key": True}]}
        stored = {"name": "fixture", "fields": [{**definition["fields"][0], "retrievable": True}], "@odata.etag": '"v1"'}
        connector = self.connector(HttpResponse(201), HttpResponse(200, stored))
        result = await connector.schema(SchemaRequest(action="create", definition=definition))
        self.assertEqual(result.verification.state, "satisfied")

    async def test_schema_update_refuses_removal_before_put(self):
        current = {"name": "fixture", "fields": [{"name": "id", "type": "Edm.String", "key": True},
                                                   {"name": "title", "type": "Edm.String"}], "@odata.etag": '"v1"'}
        desired = {"name": "fixture", "fields": current["fields"][:1]}
        connector = self.connector(HttpResponse(200, current))
        result = await connector.schema(SchemaRequest(action="update", definition=desired, expected_version='"v1"'))
        self.assertEqual(result.status, "unsupported")
        self.assertEqual([request.method for request in self.transport.requests], ["GET"])

    async def test_schema_additive_update_uses_exact_version(self):
        current = {"name": "fixture", "fields": [{"name": "id", "type": "Edm.String", "key": True}], "@odata.etag": '"v1"'}
        desired = {"name": "fixture", "fields": current["fields"] + [{"name": "title", "type": "Edm.String"}]}
        connector = self.connector(HttpResponse(200, current), HttpResponse(204), HttpResponse(200, desired))
        result = await connector.schema(SchemaRequest(action="update", definition=desired, expected_version='"v1"'))
        self.assertEqual(result.status, "success")
        self.assertEqual(self.transport.requests[1].headers["If-Match"], '"v1"')

    async def test_schema_delete_needs_exact_target_confirmation_and_grant(self):
        policy = Policy(principal="fixture", grants={"schema.read", "schema.delete"}, destructive=True)
        connector = self.connector(HttpResponse(204), HttpResponse(404), policy=policy)
        request = SchemaRequest(action="delete", expected_version='"v1"')
        denied = await connector.schema(request)
        self.assertEqual(denied.status, "denied")
        self.assertFalse(self.transport.requests)
        configuration = connector._config
        digest = confirmation_digest("search", configuration, request)
        other = replace(configuration, endpoint="https://other.search.windows.net", allowed_hosts=("other.search.windows.net",))
        self.assertNotEqual(digest, confirmation_digest("search", other, request))
        result = await connector.schema(replace(request, confirmation=digest))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification.achieved, "schema")

    async def test_content_comparison_does_not_equate_boolean_and_integer(self):
        connector = self.connector(accepted("one"), HttpResponse(200, {"id": "one", "title": True}))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(title=1),), verification=Verification("content", attempts=1)))
        self.assertEqual(result.status, "pending")

    async def test_query_byte_bound_retains_prefix_and_discards_unusable_cursor(self):
        connector = self.connector(HttpResponse(200, {"value": [{"id": "one"}, {"id": "two", "title": "x" * 100}, {"id": "three"}]}))
        result = await connector.query(QueryRequest(dialect="search", expression="*", limits=Limits(max_items=3, max_output_bytes=30)))
        self.assertEqual([item.content.data["id"] for item in result.items], ["one"])
        self.assertTrue(result.truncated)
        self.assertIsNone(result.continuation)

    async def test_duplicate_mutation_keys_refuse_without_transport(self):
        connector = self.connector()
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(), record())))
        self.assertEqual(result.errors[0].code, "duplicate_mutation_key")
        self.assertFalse(self.transport.requests)

    async def test_duplicate_acknowledgments_do_not_hide_valid_other_items(self):
        connector = self.connector(HttpResponse(200, {"value": [
            {"key": "one", "status": True}, {"key": "one", "status": True}, {"key": "two", "status": True},
        ]}))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record("one"), record("two"))))
        self.assertEqual([item.status for item in result.items], ["unknown", "success"])

    async def test_vector_query_is_preserved_without_an_sdk_object(self):
        connector = self.connector(HttpResponse(200, {"value": []}))
        result = await connector.query(QueryRequest(dialect="search", expression="example", service_options={"search": {
            "vectorQueries": [{"kind": "vector", "vector": [0.2, 0.8], "fields": "embedding", "k": 5}]
        }}))
        self.assertEqual(result.status, "success")
        self.assertEqual(self.transport.requests[0].body["vectorQueries"][0]["vector"], [0.2, 0.8])

    async def test_unexposed_query_metadata_refuses_instead_of_disappearing(self):
        connector = self.connector()
        for option in ({"facets": ["category"]}, {"count": True}, {"answers": "extractive"}, {"captions": "extractive"}):
            result = await connector.query(QueryRequest(dialect="search", expression="*", service_options={"search": option}))
            self.assertEqual(result.errors[0].code, "query_metadata_not_exposed")
        self.assertFalse(self.transport.requests)


if __name__ == "__main__":
    unittest.main()