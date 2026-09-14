import inspect
import unittest

from azdata import (
    ConnectorConfig, OPERATIONS, Policy, ReadRequest, RecordKey, Requirements, ResourceAddress,
)
from azdata.adapters.base import Adapter
from azdata.connector import DataConnector
from azdata.contracts import OperationCapability


class NoIO:
    def get_token(self, *args):
        raise AssertionError("credential must not be called")

    async def request(self, request):
        raise AssertionError("transport must not be called")


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        config = ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}), ("unit.search.windows.net",))
        adapter = Adapter(config)
        adapter.service = "search"
        self.connector = DataConnector(adapter, credential=NoIO(), policy=Policy(principal="fixture"), transport=NoIO())

    def test_all_operations_are_present_and_async(self):
        self.assertEqual(set(self.connector.describe().operations), set(OPERATIONS))
        for operation in OPERATIONS:
            method = getattr(self.connector, operation)
            self.assertTrue(inspect.iscoroutinefunction(method))
            self.assertEqual(list(inspect.signature(method).parameters), ["request"])

    async def test_unsupported_is_a_result_without_io(self):
        result = await self.connector.read(ReadRequest(keys=(RecordKey({"id": "one"}),)))
        self.assertEqual(result.status, "unsupported")
        self.assertEqual(result.metrics["attempts"], 0)

    async def test_target_cannot_escape_scope(self):
        result = await self.connector.read(ReadRequest(target=ResourceAddress({"index": "other"})))
        self.assertEqual(result.status, "denied")

    async def test_wrong_request_type_returns_invalid(self):
        result = await self.connector.read({"keys": ["one"]})
        self.assertEqual(result.status, "invalid")

    async def test_unsupported_guarantee_cannot_trigger_io(self):
        self.connector._adapter.capabilities["read"] = OperationCapability(support="supported")
        result = await self.connector.read(ReadRequest(requirements=Requirements(("atomic_batch",))))
        self.assertEqual(result.errors[0].code, "guarantee_unsupported")

    async def test_close_is_idempotent_and_borrowed_transport_untouched(self):
        await self.connector.aclose()
        await self.connector.aclose()
        result = await self.connector.read(ReadRequest())
        self.assertEqual(result.errors[0].code, "connector_closed")


if __name__ == "__main__":
    unittest.main()