import copy
import json
import unittest
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

from azdata import (
    ConnectorConfig, ContentValue, CreateRequest, DeleteRequest, HttpResponse, Policy,
    QueryRequest, ReadRequest, RecordInput, RecordKey, ResourceAddress, UpsertRequest,
    Verification, connect,
)


class Credential:
    async def get_token(self, scope):
        if scope not in {"https://search.azure.com/.default", "https://cosmos.azure.com/.default"}:
            raise AssertionError("unexpected credential audience")
        return SimpleNamespace(token="synthetic-token", expires_on=2**31)


class MemoryProvider:
    def __init__(self, service):
        self.service = service
        self.documents = {}

    async def request(self, request):
        if "synthetic-token" not in request.headers["Authorization"]:
            raise AssertionError("expected authenticated transport")
        parsed = urlsplit(request.url)
        if parsed.hostname not in {"synthetic.search.windows.net", "synthetic.documents.azure.com"}:
            raise AssertionError("target escaped fixture configuration")
        if self.service == "search":
            return self._search(request, parsed.path)
        return self._cosmos(request, parsed.path)

    def _search(self, request, path):
        if path.endswith("/docs/index"):
            results = []
            for document in request.body["value"]:
                document = copy.deepcopy(document)
                action = document.pop("@search.action")
                identifier = document["id"]
                if action == "delete":
                    self.documents.pop(identifier, None)
                elif action == "merge" and identifier not in self.documents:
                    results.append({"key": identifier, "status": False, "statusCode": 404})
                    continue
                elif action in {"merge", "mergeOrUpload"}:
                    self.documents[identifier] = {**self.documents.get(identifier, {}), **document}
                else:
                    self.documents[identifier] = document
                results.append({"key": identifier, "status": True, "statusCode": 200})
            return HttpResponse(200, {"value": results})
        if path.endswith("/docs/search"):
            start = request.body.get("skip", 0)
            return HttpResponse(200, {"value": copy.deepcopy(list(self.documents.values())[start:start + request.body["top"]])})
        identifier = unquote(path.rsplit("/", 1)[-1])
        return HttpResponse(200, copy.deepcopy(self.documents[identifier])) if identifier in self.documents else HttpResponse(404)

    def _cosmos(self, request, path):
        if request.headers.get("x-ms-documentdb-isquery") == "true":
            return HttpResponse(200, {"Documents": copy.deepcopy(list(self.documents.values()))})
        partition = json.loads(request.headers["x-ms-documentdb-partitionkey"])[0]
        identifier = request.body["id"] if request.method == "POST" else unquote(path.rsplit("/", 1)[-1])
        key = (identifier, partition)
        if request.method == "GET":
            return HttpResponse(200, copy.deepcopy(self.documents[key])) if key in self.documents else HttpResponse(404)
        if request.method == "DELETE":
            return HttpResponse(204) if self.documents.pop(key, None) is not None else HttpResponse(404)
        if request.method == "POST" and request.headers.get("x-ms-documentdb-is-upsert") != "true" and key in self.documents:
            return HttpResponse(409)
        if request.method == "PUT" and key not in self.documents:
            return HttpResponse(404)
        self.documents[key] = copy.deepcopy(request.body)
        return HttpResponse(201, copy.deepcopy(self.documents[key]))


class ConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_public_workflow_against_both_providers(self):
        for service in ("search", "cosmos"):
            with self.subTest(service=service):
                host = "synthetic.search.windows.net" if service == "search" else "synthetic.documents.azure.com"
                target = ResourceAddress({"index": "fixture"} if service == "search" else {"database": "fixture", "container": "items"})
                config = ConnectorConfig(f"https://{host}", target, (host,), partition_key_field="site" if service == "cosmos" else None,
                                         retrievable_fields=("id", "title"))
                provider = MemoryProvider(service)
                policy = Policy(principal="synthetic-consumer", grants={"create", "read", "upsert", "query", "delete"},
                                minimum_verification={"upsert": "content", "delete": "absence"})
                key = RecordKey({"id": "one"}, "north" if service == "cosmos" else None)
                async with connect(service, config, credential=Credential(), policy=policy, transport=provider) as connector:
                    for title in ("first", "updated"):
                        result = await connector.upsert(UpsertRequest(mode="replace", records=(RecordInput(key, ContentValue({"title": title})),)))
                        self.assertEqual(result.status, "success")
                        self.assertEqual(result.verification.state, "satisfied")
                        observed = await connector.read(ReadRequest(keys=(key,)))
                        self.assertEqual(observed.items[0].content.data["title"], title)
                    create = await connector.create(CreateRequest(records=(RecordInput(key, ContentValue({"title": "must-not-overwrite"})),)))
                    self.assertEqual(create.status, "unsupported" if service == "search" else "conflict")
                    observed = await connector.read(ReadRequest(keys=(key,)))
                    self.assertEqual(observed.items[0].content.data["title"], "updated")
                    query = await connector.query(QueryRequest(dialect="search" if service == "search" else "cosmos-sql",
                                                               expression="*" if service == "search" else "SELECT * FROM c"))
                    self.assertEqual(len(query.items), 1)
                    deleted = await connector.delete(DeleteRequest(keys=(key,), missing="ok"))
                    self.assertEqual(deleted.status, "success")
                    self.assertEqual(deleted.verification.achieved, "absence")
                    self.assertFalse(provider.documents)
                    json.dumps(deleted.to_dict(), allow_nan=False)
                closed = await connector.read(ReadRequest(keys=(key,)))
                self.assertEqual(closed.errors[0].code, "connector_closed")


if __name__ == "__main__":
    unittest.main()