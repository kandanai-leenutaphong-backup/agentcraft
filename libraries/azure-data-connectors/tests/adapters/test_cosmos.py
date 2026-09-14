import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from tests.sdk_fixtures import cosmos_metadata

from azdata import (
    ConfigurationError, ConnectorConfig, ContentValue, CreateRequest, DeleteRequest,
    HttpResponse, OPERATIONS, Policy, QueryRequest, ReadRequest, RecordInput, RecordKey,
    Requirements, ResourceAddress, UpdateRequest, UpsertRequest, Verification, connect,
)


class Credential:
    def __init__(self):
        self.calls = []

    async def get_token(self, scope):
        self.calls.append(scope)
        return SimpleNamespace(token="fixture-token", expires_on=2**31)


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def request(self, request):
        metadata = cosmos_metadata(request)
        if metadata is not None:
            return metadata
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def key(identifier="one", partition="north"):
    return RecordKey({"id": identifier}, partition)


def record(identifier="one", partition="north", version=None, **fields):
    return RecordInput(key(identifier, partition), ContentValue(fields), version)


def stored(identifier="one", partition="north", **fields):
    return {"id": identifier, "site": partition, "_etag": '"version-1"', **fields}


class CosmosTests(unittest.IsolatedAsyncioTestCase):
    def connector(self, *responses, policy=None):
        config = ConnectorConfig("https://unit.documents.azure.com", ResourceAddress({"database": "fixture", "container": "items"}),
                                 ("unit.documents.azure.com",), partition_key_field="site")
        self.credential = Credential()
        self.transport = ScriptedTransport(*responses)
        return connect("cosmos", config, credential=self.credential, transport=self.transport,
                       policy=policy or Policy(principal="fixture", grants={"read", "create", "upsert", "update", "delete", "query"}))

    def test_same_interface_and_explicit_capabilities(self):
        connector = self.connector()
        self.assertEqual(set(connector.describe().operations), set(OPERATIONS))
        self.assertTrue(connector.describe().partition_required)
        self.assertEqual(connector.describe().operations["schema"].support, "unsupported")

    async def test_create_is_native_and_conflict_preserves_other_items(self):
        connector = self.connector(HttpResponse(409), HttpResponse(201, stored("two")))
        result = await connector.create(CreateRequest(records=(record(), record("two"))))
        self.assertEqual(result.status, "partial")
        self.assertEqual([item.status for item in result.items], ["conflict", "success"])
        self.assertEqual(self.transport.requests[0].method, "POST")
        self.assertEqual(json.loads(self.transport.requests[0].headers["x-ms-documentdb-partitionkey"]), ["north"])
        self.assertNotIn("x-ms-documentdb-is-upsert", self.transport.requests[0].headers)
        self.assertEqual(self.credential.calls, ["https://cosmos.azure.com/.default"])

    async def test_partition_required_before_io(self):
        connector = self.connector()
        result = await connector.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "invalid")
        self.assertFalse(self.transport.requests)
        self.assertFalse(self.credential.calls)

    async def test_partition_content_mismatch_refuses(self):
        connector = self.connector()
        result = await connector.create(CreateRequest(records=(record(site="different"),)))
        self.assertEqual(result.errors[0].code, "content_key_mismatch")
        self.assertFalse(self.transport.requests)

    async def test_replace_update_sends_condition_and_missing_is_not_upsert(self):
        connector = self.connector(HttpResponse(404))
        result = await connector.update(UpdateRequest(mode="replace", records=(record(version='"version-0"', title="new"),)))
        self.assertEqual(result.status, "not_found")
        request = self.transport.requests[0]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.headers["If-Match"], '"version-0"')

    async def test_merge_refuses_and_replace_upsert_is_explicit(self):
        connector = self.connector(HttpResponse(200, stored(title="new")))
        result = await connector.upsert(UpsertRequest(mode="merge", records=(record(),)))
        self.assertEqual(result.status, "unsupported")
        result = await connector.upsert(UpsertRequest(mode="replace", records=(record(title="new"),)))
        self.assertEqual(result.status, "success")
        self.assertEqual(self.transport.requests[0].headers["x-ms-documentdb-is-upsert"].lower(), "true")

    async def test_conditional_requirement_needs_a_version(self):
        connector = self.connector()
        result = await connector.update(UpdateRequest(mode="replace", records=(record(),), requirements=Requirements(("conditional_version",))))
        self.assertEqual(result.errors[0].code, "expected_version_required")
        self.assertFalse(self.transport.requests)

    async def test_version_conflict_is_not_retried(self):
        connector = self.connector(HttpResponse(412))
        result = await connector.delete(DeleteRequest(keys=(key(),), expected_versions=('"version-0"',)))
        self.assertEqual(result.status, "conflict")
        self.assertEqual(len(self.transport.requests), 1)

    async def test_wildcard_does_not_satisfy_exact_version_requirement(self):
        connector = self.connector()
        updated = await connector.update(UpdateRequest(mode="replace", records=(record(version="*"),),
                                                       requirements=Requirements(("conditional_version",))))
        deleted = await connector.delete(DeleteRequest(keys=(key(),), expected_versions=("*",)))
        self.assertEqual(updated.status, "invalid")
        self.assertEqual(deleted.status, "invalid")
        self.assertFalse(self.transport.requests)

    async def test_partition_comparison_preserves_scalar_types(self):
        connector = self.connector()
        result = await connector.create(CreateRequest(records=(record(partition=1, site=True),)))
        self.assertEqual(result.errors[0].code, "content_key_mismatch")
        self.assertFalse(self.transport.requests)

    async def test_replacement_verification_detects_unremoved_fields(self):
        connector = self.connector(HttpResponse(200, stored(title="new")), HttpResponse(200, stored(title="new", stale=True)))
        result = await connector.update(UpdateRequest(mode="replace", records=(record(title="new"),), verification=Verification("content", attempts=1)))
        self.assertEqual(result.status, "pending")

    async def test_verified_create_matches_content_excluding_system_fields(self):
        connector = self.connector(HttpResponse(201, stored(title="new")), HttpResponse(200, stored(title="new")))
        result = await connector.create(CreateRequest(records=(record(title="new"),), verification=Verification("content")))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification.achieved, "content")

    async def test_unknown_preserves_preceding_success_and_unattempted_tail(self):
        connector = self.connector(HttpResponse(201, stored()), TimeoutError())
        result = await connector.create(CreateRequest(records=(record(), record("two"), record("three"))))
        self.assertEqual(result.status, "partial")
        self.assertEqual([item.status for item in result.items], ["success", "unknown", "not_attempted"])
        self.assertEqual(len(self.transport.requests), 2)

    async def test_delete_evidence_is_partition_scoped(self):
        connector = self.connector(HttpResponse(404), HttpResponse(404))
        result = await connector.delete(DeleteRequest(keys=(key(),)))
        self.assertEqual(result.status, "not_found")
        result = await connector.delete(DeleteRequest(keys=(key(),), missing="ok", verification=Verification("absence")))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification.achieved, "absence")
        self.assertTrue(any(caveat.code == "addressed_partition" for caveat in result.caveats))

    async def test_bound_parameters_and_scoped_query_continuation(self):
        connector = self.connector(HttpResponse(200, {"Documents": [stored()]}, {"x-ms-continuation": "native-cursor"}),
                                   HttpResponse(200, {"Documents": []}))
        request = QueryRequest(dialect="cosmos-sql", expression="SELECT * FROM c WHERE c.id = @id", parameters={"@id": "one"},
                               service_options={"cosmos": {"partition": "north"}})
        result = await connector.query(request)
        self.assertEqual(self.transport.requests[0].body["parameters"], [{"name": "@id", "value": "one"}])
        self.assertEqual(json.loads(self.transport.requests[0].headers["x-ms-documentdb-partitionkey"]), ["north"])
        result = await connector.query(replace(request, continuation=result.continuation))
        self.assertEqual(result.status, "success")
        self.assertEqual(self.transport.requests[1].headers["x-ms-continuation"], "native-cursor")

    async def test_query_does_not_submit_mutation_as_sql(self):
        connector = self.connector()
        result = await connector.query(QueryRequest(dialect="cosmos-sql", expression="DELETE FROM c"))
        self.assertEqual(result.status, "invalid")
        self.assertFalse(self.transport.requests)


if __name__ == "__main__":
    unittest.main()