import unittest
from types import SimpleNamespace

from azdata import (ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, HttpResponse, Policy, QueryRequest,
                    ReadRequest, RecordInput, RecordKey, ResourceAddress, UpdateRequest, UpsertRequest, Verification, connect)


class Credential:
    async def get_token(self, scope):
        assert scope == "https://storage.azure.com/.default"
        return SimpleNamespace(token="fixture", expires_on=2**31)


class Scripted:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def request(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def connector(service, transport, grants=None):
    host = "fixture.blob.core.windows.net" if service == "blobs" else "fixture.table.core.windows.net"
    target = {"container": "fixture"} if service == "blobs" else {"table": "Fixture"}
    return connect(service, ConnectorConfig(f"https://{host}", ResourceAddress(target), (host,)), credential=Credential(), transport=transport,
                   policy=Policy(principal="fixture", grants=grants or {"read", "query", "create", "update", "upsert", "delete"}))


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_blob_create_uses_native_nonoverwrite_and_bytes(self):
        transport = Scripted(HttpResponse(201, headers={"etag": '"one"', "last-modified": "Tue, 15 Sep 2026 00:00:00 GMT"}), HttpResponse(409))
        client = connector("blobs", transport)
        record = RecordInput(RecordKey({"id": "run/data.bin"}), ContentValue(b"\x00\xff", kind="bytes", media_type="application/octet-stream"))
        result = await client.create(CreateRequest(records=(record,)))
        self.assertEqual(result.status, "success")
        self.assertEqual(transport.requests[0].body, b"\x00\xff")
        self.assertEqual(transport.requests[0].headers.get("If-None-Match", transport.requests[0].headers.get("if-none-match")), "*")
        self.assertEqual((await client.create(CreateRequest(records=(record,)))).status, "conflict")

    async def test_blob_read_preserves_bytes_and_bounds(self):
        headers = {"etag": '"one"', "content-length": "2", "x-ms-blob-type": "BlockBlob", "content-type": "application/octet-stream"}
        transport = Scripted(HttpResponse(200, b"", headers), HttpResponse(206, b"\x00\xff", {**headers, "content-range": "bytes 0-1/2"}))
        result = await connector("blobs", transport).read(ReadRequest(keys=(RecordKey({"id": "run/data.bin"}),)))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.items[0].content.data, b"\x00\xff")

    async def test_blob_merge_refuses_and_update_requires_existing_object(self):
        transport = Scripted(HttpResponse(412))
        client = connector("blobs", transport)
        record = RecordInput(RecordKey({"id": "one"}), ContentValue(b"new", kind="bytes"))
        self.assertEqual((await client.update(UpdateRequest(mode="merge", records=(record,)))).status, "unsupported")
        self.assertFalse(transport.requests)
        result = await client.update(UpdateRequest(mode="replace", records=(record,)))
        self.assertEqual(result.status, "conflict")
        self.assertEqual(transport.requests[0].headers.get("If-Match", transport.requests[0].headers.get("if-match")), "*")

    async def test_table_composite_create_and_read(self):
        entity = {"PartitionKey": "run", "RowKey": "one", "title": "new", "odata.etag": 'W/"one"'}
        transport = Scripted(HttpResponse(204, headers={"etag": 'W/"one"'}), HttpResponse(200, entity))
        client = connector("tables", transport)
        key = RecordKey({"PartitionKey": "run", "RowKey": "one"})
        result = await client.create(CreateRequest(records=(RecordInput(key, ContentValue({"title": "new"})),), verification=Verification("content")))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.verification.state, "satisfied")
        self.assertEqual(client.describe().required_key_fields, ("PartitionKey", "RowKey"))
        self.assertIn("PartitionKey='run'", transport.requests[1].url)

    async def test_table_merge_replace_and_conditions_are_native(self):
        transport = Scripted(HttpResponse(204, headers={"etag": 'W/"next"'}), HttpResponse(412), HttpResponse(204))
        client = connector("tables", transport)
        key = RecordKey({"PartitionKey": "run", "RowKey": "one"})
        record = RecordInput(key, ContentValue({"title": "new"}), expected_version='W/"old"')
        self.assertEqual((await client.update(UpdateRequest(mode="merge", records=(record,)))).status, "success")
        self.assertEqual(transport.requests[0].method, "PATCH")
        self.assertEqual((await client.update(UpdateRequest(mode="replace", records=(record,)))).status, "conflict")
        self.assertEqual(transport.requests[1].method, "PUT")
        self.assertEqual((await client.delete(DeleteRequest(keys=(key,)))).status, "success")

    async def test_storage_policy_refuses_before_sdk_and_unknown_keys_refuse(self):
        for service in ("blobs", "tables"):
            transport = Scripted()
            client = connector(service, transport, {"read"})
            key = RecordKey({"id": "one"}) if service == "blobs" else RecordKey({"PartitionKey": "run", "RowKey": "one"})
            content = ContentValue(b"one", kind="bytes") if service == "blobs" else ContentValue({"title": "one"})
            result = await client.create(CreateRequest(records=(RecordInput(key, content),)))
            self.assertEqual(result.status, "denied")
            self.assertFalse(transport.requests)


if __name__ == "__main__":
    unittest.main()