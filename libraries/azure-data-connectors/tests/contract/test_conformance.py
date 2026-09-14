import asyncio
import inspect
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from tests.sdk_fixtures import cosmos_metadata

from azdata import (
    ConfigurationError, ConnectorConfig, ContentValue, CreateRequest, DeleteRequest,
    HttpResponse, IngestRequest, Limits, OPERATIONS, Policy, ProvisionRequest, QueryRequest,
    ReadRequest, RecordInput, RecordKey, Requirements, ResourceAddress, SchemaRequest,
    StatusRequest, UpdateRequest, UpsertRequest, Verification, connect,
)


class NoIO:
    def get_token(self, scope):
        raise AssertionError("no credential call expected")

    async def request(self, request):
        raise AssertionError("no transport call expected")


def config(service):
    if service == "search":
        return ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}), ("unit.search.windows.net",))
    return ConnectorConfig("https://unit.documents.azure.com", ResourceAddress({"database": "fixture", "container": "items"}),
                           ("unit.documents.azure.com",), partition_key_field="site")


def requests(service):
    key = RecordKey({"id": "one"}, "north" if service == "cosmos" else None)
    records = (RecordInput(key, ContentValue({"title": "new"})),)
    return {
        "create": CreateRequest(records=records), "read": ReadRequest(keys=(key,)),
        "update": UpdateRequest(mode="merge" if service == "search" else "replace", records=records),
        "upsert": UpsertRequest(mode="replace", records=records), "delete": DeleteRequest(keys=(key,), missing="ok"),
        "query": QueryRequest(dialect="search" if service == "search" else "cosmos-sql", expression="SELECT * FROM c"),
        "ingest": IngestRequest(), "schema": SchemaRequest(action="read"),
        "provision": ProvisionRequest(action="read"), "status": StatusRequest(operation_ref="fixture"),
    }


class ConformanceTests(unittest.IsolatedAsyncioTestCase):
    def test_all_adapters_share_the_same_class_and_signatures(self):
        connectors = [connect(service, config(service), credential=NoIO(), policy=Policy(principal="fixture"), transport=NoIO()) for service in ("search", "cosmos")]
        self.assertIs(type(connectors[0]), type(connectors[1]))
        for operation in OPERATIONS:
            self.assertEqual(inspect.signature(getattr(connectors[0], operation)), inspect.signature(getattr(connectors[1], operation)))
        for connector in connectors:
            self.assertEqual(set(connector.describe().to_dict()["operations"]), set(OPERATIONS))
            self.assertEqual(connector.describe().availability, "unverified")

    async def test_every_operation_refuses_without_authority_or_support_and_no_io(self):
        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=NoIO(), policy=Policy(principal="fixture", grants=()), transport=NoIO())
            for operation, request in requests(service).items():
                with self.subTest(service=service, operation=operation):
                    result = await getattr(connector, operation)(request)
                    self.assertIn(result.status, {"unsupported", "denied"})
                    self.assertEqual(result.metrics["attempts"], 0)
                    json.dumps(result.to_dict(), allow_nan=False)

    async def test_malformed_values_return_invalid_for_each_adapter(self):
        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=NoIO(), policy=Policy(principal="fixture"), transport=NoIO())
            for request in (ReadRequest(verification=Verification(kind=[])), ReadRequest(verification=Verification(attempts=True)),
                            ReadRequest(limits=Limits(max_items=True)), ReadRequest(limits=Limits(timeout_seconds=float("nan"))),
                            ReadRequest(request_id=["bad"]), ReadRequest(keys=(RecordKey(None),)),
                            ReadRequest(requirements=Requirements({"atomic": True})), ReadRequest(service_options={service: 5}),
                            ReadRequest(projection=("field,other",))):
                with self.subTest(service=service, request=request):
                    result = await connector.read(request)
                    self.assertEqual(result.status, "invalid")

    async def test_unknown_options_cannot_replace_policy_or_target(self):
        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=NoIO(), policy=Policy(principal="fixture"), transport=NoIO())
            result = await connector.query(replace(requests(service)["query"], service_options={service: {"endpoint": "https://other.example", "allow_write": True}}))
            self.assertEqual(result.errors[0].code, "unknown_service_option")

    async def test_nested_projection_refuses_instead_of_silently_dropping_fields(self):
        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=NoIO(), policy=Policy(principal="fixture"), transport=NoIO())
            result = await connector.read(replace(requests(service)["read"], projection=("parent/child",)))
            self.assertEqual(result.errors[0].code, "nested_projection_unsupported")

    async def test_empty_read_is_a_noop_without_io(self):
        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=NoIO(), policy=Policy(principal="fixture"), transport=NoIO())
            result = await connector.read(ReadRequest())
            self.assertEqual(result.status, "success")
            self.assertEqual(result.verification.state, "not_requested")

    async def test_missing_read_cannot_satisfy_required_presence(self):
        class Credential:
            def get_token(self, scope):
                return SimpleNamespace(token="fixture-token", expires_on=2**31)

        class MissingTransport:
            async def request(self, request):
                return cosmos_metadata(request) or HttpResponse(404)

        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=Credential(), policy=Policy(principal="fixture"), transport=MissingTransport())
            result = await connector.read(replace(requests(service)["read"], missing="ok", verification=Verification("presence")))
            self.assertEqual(result.status, "not_found")
            self.assertEqual(result.verification.state, "failed")

    async def test_cancellation_propagates_without_retry_for_each_adapter(self):
        class Credential:
            async def get_token(self, scope):
                return SimpleNamespace(token="fixture-token", expires_on=2**31)

        class CancelTransport:
            async def request(self, request):
                raise asyncio.CancelledError()

        for service in ("search", "cosmos"):
            connector = connect(service, config(service), credential=Credential(), policy=Policy(principal="fixture"), transport=CancelTransport())
            with self.assertRaises(asyncio.CancelledError):
                await connector.read(requests(service)["read"])

    def test_unknown_service_and_secret_credentials_are_not_adapters(self):
        with self.assertRaises(ConfigurationError):
            connect("arbitrary.module", config("search"), credential=NoIO(), policy=Policy(principal="fixture"))
        with self.assertRaises(ConfigurationError):
            connect("search", config("search"), credential="account-key", policy=Policy(principal="fixture"))

    def test_malformed_policy_is_configuration_error(self):
        for values in ({"grants": [[]]}, {"minimum_verification": {"upsert": []}}, {"limits": Limits(max_items=10**1000)}):
            with self.subTest(values=values), self.assertRaises(ConfigurationError):
                Policy(principal="fixture", **values)


if __name__ == "__main__":
    unittest.main()