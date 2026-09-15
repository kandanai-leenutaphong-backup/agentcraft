import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from azdata import (ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, HttpResponse, Limits, Policy, QueryRequest,
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
    async def test_empty_blob_prefix_lists_container_root(self):
        transport = Scripted(HttpResponse(200, b'<EnumerationResults><Blobs/><NextMarker/></EnumerationResults>', {"content-type": "application/xml"}))
        result = await connector("blobs", transport).query(QueryRequest(dialect="blob-prefix", expression=""))
        self.assertEqual(result.status, "success", result.errors)
        self.assertFalse(result.items)
        self.assertEqual(len(transport.requests), 1)

    async def test_table_query_binds_odata_values_and_native_continuation(self):
        entity = {"PartitionKey": "run", "RowKey": "one", "title": "fixture", "odata.etag": 'W/"one"'}
        transport = Scripted(HttpResponse(200, {"value": [entity]}, {"x-ms-continuation-NextPartitionKey": "run", "x-ms-continuation-NextRowKey": "two"}),
                             HttpResponse(200, {"value": []}))
        client = connector("tables", transport)
        request = dict(dialect="odata", expression="title eq @title", parameters={"title": "O'Brien"})
        result = await client.query(QueryRequest(**request))
        self.assertEqual(result.status, "success", result.errors)
        self.assertEqual(result.items[0].key.parts["RowKey"], "one")
        self.assertTrue(result.continuation)
        self.assertIn("O%27%27Brien", transport.requests[0].url)
        following = await client.query(QueryRequest(**request, continuation=result.continuation))
        self.assertEqual(following.status, "success")
        self.assertFalse(following.items)
        self.assertIn("NextRowKey=two", transport.requests[1].url)

    async def test_blob_listing_uses_sdk_xml_and_native_marker(self):
        body = (b'<EnumerationResults ServiceEndpoint="https://fixture.blob.core.windows.net/" ContainerName="fixture">'
                b'<Blobs><Blob><Name>run/one</Name><Properties><Etag>one</Etag><Content-Length>3</Content-Length>'
                b'<BlobType>BlockBlob</BlobType></Properties></Blob></Blobs><NextMarker>next</NextMarker></EnumerationResults>')
        transport = Scripted(HttpResponse(200, body, {"content-type": "application/xml"}),
                             HttpResponse(200, b'<EnumerationResults><Blobs/><NextMarker/></EnumerationResults>', {"content-type": "application/xml"}))
        client = connector("blobs", transport)
        result = await client.query(QueryRequest(dialect="blob-prefix", expression="run/"))
        self.assertEqual(result.status, "success", result.errors)
        self.assertEqual(result.items[0].key.parts["id"], "run/one")
        self.assertEqual(result.items[0].content.data["size"], 3)
        self.assertTrue(result.continuation)
        following = await client.query(QueryRequest(dialect="blob-prefix", expression="run/", continuation=result.continuation))
        self.assertEqual(following.status, "success")
        self.assertIn("marker=next", transport.requests[1].url)

    async def test_storage_writes_do_not_retry_and_preserve_unknown_tail(self):
        for service in ("blobs", "tables"):
            keys = (RecordKey({"id": "one"}), RecordKey({"id": "two"})) if service == "blobs" else (
                RecordKey({"PartitionKey": "run", "RowKey": "one"}), RecordKey({"PartitionKey": "run", "RowKey": "two"}))
            content = ContentValue(b"fixture", kind="bytes") if service == "blobs" else ContentValue({"title": "fixture"})
            transport = Scripted(OSError("connection lost"))
            result = await connector(service, transport).create(CreateRequest(records=tuple(RecordInput(key, content) for key in keys)))
            self.assertEqual([item.status for item in result.items], ["unknown", "not_attempted"])
            self.assertEqual(result.items[0].effect, "unknown")
            self.assertEqual(len(transport.requests), 1)

    async def test_native_json_blob_content_is_not_reencoded(self):
        data = b' { "key" : 1 }\n'
        headers = {"etag": '"one"', "content-length": str(len(data)), "x-ms-blob-type": "BlockBlob", "content-type": "application/json"}
        def response(status, body, response_headers):
            async def chunks():
                if body:
                    yield body
            return SimpleNamespace(status_code=status, headers=response_headers, iter_bytes=chunks, close=AsyncMock())
        native = SimpleNamespace(send=AsyncMock(side_effect=[response(200, b"", headers),
            response(206, data, {**headers, "content-range": f"bytes 0-{len(data) - 1}/{len(data)}"})]), close=AsyncMock())
        client = connector("blobs", None)
        with patch("azure.core.pipeline.transport.AioHttpTransport", return_value=native):
            result = await client.read(ReadRequest(keys=(RecordKey({"id": "fixture.json"}),)))
            self.assertEqual(result.status, "success", result.errors)
            self.assertEqual(result.items[0].content.data, data)
            self.assertEqual(result.items[0].content.media_type, "application/json")
            await client.aclose()
        native.close.assert_awaited_once()

    async def test_table_native_values_preserve_bytes_int64_and_timestamp(self):
        body = {"PartitionKey": "run", "RowKey": "one", "data@odata.type": "Edm.Binary", "data": "AP8=",
                "quantity@odata.type": "Edm.Int64", "quantity": "9223372036854775800", "when@odata.type": "Edm.DateTime",
                "when": "2026-09-15T00:00:00Z", "odata.etag": 'W/"one"'}
        transport = Scripted(HttpResponse(200, body), HttpResponse(204, headers={"etag": 'W/"two"'}))
        client = connector("tables", transport)
        key = RecordKey({"PartitionKey": "run", "RowKey": "one"})
        result = await client.read(ReadRequest(keys=(key,)))
        self.assertEqual(result.status, "success", result.errors)
        content = result.items[0].content
        self.assertEqual(content.data["data"], b"\x00\xff")
        self.assertEqual(content.data["quantity"], 9223372036854775800)
        self.assertEqual(type(content.data["quantity"]), int)
        self.assertEqual(type(content.data["when"]), datetime)
        self.assertEqual(result.to_dict()["items"][0]["content"]["data"]["when"]["type"], "datetime")
        written = await client.upsert(UpsertRequest(mode="replace", records=(RecordInput(key, content),)))
        self.assertEqual(written.status, "success", written.errors)
        self.assertEqual(transport.requests[1].body["quantity@odata.type"], "Edm.Int64")
        self.assertEqual(transport.requests[1].body["data"], "AP8=")

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