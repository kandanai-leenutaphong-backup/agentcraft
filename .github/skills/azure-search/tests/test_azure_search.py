"""Azure AI Search CRUD against a fake service, including the awkward parts.

The fake keeps 207 partial success, 404s, and retryable statuses intact, because
those are the behaviours that silently lose documents when unhandled.
"""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

from azure_search import (
    FieldSpec,
    IndexSpec,
    SearchConfig,
    SearchConfigError,
    SearchError,
    SearchIndexClient,
    Transport,
    VectorSpec,
    render_index,
    safe_key,
    valid_index_name,
)
from azure_search.config import SEARCH_SCOPE

ENDPOINT = "https://svc.search.windows.net"


class FakeCredential:
    def __init__(self) -> None:
        self.calls = 0

    def get_token(self, scope):
        self.calls += 1
        return SimpleNamespace(token=f"token-{self.calls}", expires_on=2**31)


class FakeService:
    """Records requests and replies from a scripted queue, else a default."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict | None]] = []
        self.scripted: list[tuple[int, object]] = []

    def script(self, status: int, body: object) -> None:
        self.scripted.append((status, body))

    def opener(self, request, timeout):
        body = json.loads(request.data.decode()) if request.data else None
        self.requests.append((request.get_method(), request.full_url, body))
        assert request.get_header("Authorization", "").startswith("Bearer ")
        if self.scripted:
            status, payload = self.scripted.pop(0)
            return status, b"" if payload is None else json.dumps(payload).encode()
        return 200, json.dumps({"value": []}).encode()


def spec(name: str = "handbook", vector: bool = False) -> IndexSpec:
    return IndexSpec(
        name=name,
        purpose="Retrieval for operator answers.",
        fields=(
            FieldSpec("id", key=True, filterable=True),
            FieldSpec("title", searchable=True, filterable=True),
            FieldSpec("content", searchable=True),
        ),
        vector=VectorSpec("content_vector", 1536, "content") if vector else None,
        semantic_title_field="title",
        semantic_content_fields=("content",),
    )


class NameTests(unittest.TestCase):
    def test_accepts_lowercase_and_single_dashes(self):
        for name in ("a", "handbook", "kb-2026", "a-b-c"):
            self.assertTrue(valid_index_name(name), name)

    def test_rejects_what_the_service_rejects(self):
        for name in ("", "Handbook", "kb_2026", "-kb", "kb-", "kb--2026", "a" * 129):
            self.assertFalse(valid_index_name(name), name)


class SchemaTests(unittest.TestCase):
    def test_purpose_is_required(self):
        with self.assertRaises(SearchConfigError):
            IndexSpec(name="x", purpose="  ", fields=(FieldSpec("id", key=True),))

    def test_exactly_one_key_field(self):
        with self.assertRaises(SearchConfigError):
            IndexSpec(name="x", purpose="p", fields=(FieldSpec("a"), FieldSpec("b")))
        with self.assertRaises(SearchConfigError):
            IndexSpec(name="x", purpose="p", fields=(FieldSpec("a", key=True), FieldSpec("b", key=True)))

    def test_vector_content_field_must_exist(self):
        with self.assertRaises(SearchConfigError):
            IndexSpec(name="x", purpose="p", fields=(FieldSpec("id", key=True),),
                      vector=VectorSpec("v", 8, "missing"))

    def test_render_is_deterministic(self):
        self.assertEqual(render_index(spec(vector=True)), render_index(spec(vector=True)))

    def test_vector_field_is_never_retrievable(self):
        rendered = render_index(spec(vector=True))
        vec = next(f for f in rendered["fields"] if f["name"] == "content_vector")
        self.assertFalse(vec["retrievable"])
        self.assertEqual(vec["dimensions"], 1536)
        self.assertEqual(vec["vectorSearchProfile"], "vector-profile")

    def test_hnsw_parameters_are_written_explicitly(self):
        algorithms = render_index(spec(vector=True))["vectorSearch"]["algorithms"][0]
        self.assertEqual(algorithms["hnswParameters"]["metric"], "cosine")

    def test_no_vector_search_block_without_a_vector(self):
        self.assertNotIn("vectorSearch", render_index(spec()))

    def test_semantic_configuration_is_rendered(self):
        semantic = render_index(spec())["semantic"]["configurations"][0]
        self.assertEqual(semantic["prioritizedFields"]["titleField"], {"fieldName": "title"})

    def test_safe_key_is_deterministic_and_accepted(self):
        first, second = safe_key("docs/a b.md"), safe_key("docs/a b.md")
        self.assertEqual(first, second)
        self.assertNotEqual(safe_key("docs/a"), safe_key("docs/b"))
        self.assertRegex(first, r"^[A-Za-z0-9_\-=]+$")


class ConfigTests(unittest.TestCase):
    def test_endpoint_must_be_https(self):
        with self.assertRaises(SearchConfigError):
            SearchConfig(endpoint="http://svc.search.windows.net")

    def test_from_env_reads_at_call_time(self):
        with mock.patch.dict(os.environ, {"SEARCH_ENDPOINT": ENDPOINT}, clear=True):
            config = SearchConfig.from_env()
        self.assertEqual(config.endpoint, ENDPOINT)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SearchConfigError):
                SearchConfig.from_env()

    def test_api_version_is_pinned_into_every_url(self):
        config = SearchConfig(endpoint=ENDPOINT)
        query = parse_qs(urlparse(config.url("indexes/x")).query)
        self.assertEqual(query["api-version"], [config.api_version])

    def test_api_version_survives_a_path_that_already_has_a_query(self):
        config = SearchConfig(endpoint=ENDPOINT)
        query = parse_qs(urlparse(config.url("indexes?$select=name")).query)
        self.assertEqual(query["api-version"], [config.api_version])
        self.assertEqual(query["$select"], ["name"])

    def test_default_scope_is_the_search_audience(self):
        self.assertEqual(SearchConfig(endpoint=ENDPOINT).scope, SEARCH_SCOPE)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.credential = FakeCredential()
        transport = Transport(credential=self.credential, opener=self.service.opener, sleep=lambda _: None)
        self.client = SearchIndexClient(SearchConfig(endpoint=ENDPOINT), transport)

    def test_describe_makes_no_request_and_names_both_roles(self):
        described = self.client.describe()
        self.assertEqual(self.service.requests, [])
        self.assertIn("Search Index Data Contributor", described["roles_required"])
        self.assertEqual(described["auth"], "entra-id-bearer-token")

    def test_create_index_puts_the_rendered_definition(self):
        self.service.script(201, {"name": "handbook"})
        self.client.create_or_update_index(spec())
        method, url, body = self.service.requests[0]
        self.assertEqual(method, "PUT")
        self.assertTrue(url.startswith(f"{ENDPOINT}/indexes/handbook?"))
        self.assertEqual(body, render_index(spec()))

    def test_update_returning_204_reads_the_definition_back(self):
        self.service.script(204, None)
        self.service.script(200, {"name": "handbook", "fields": []})
        stored = self.client.create_or_update_index(spec())
        self.assertEqual(stored["name"], "handbook")
        self.assertEqual([m for m, _, _ in self.service.requests], ["PUT", "GET"])

    def test_get_index_absent_is_none_not_an_error(self):
        self.service.script(404, {"error": {"message": "not found"}})
        self.assertIsNone(self.client.get_index("handbook"))

    def test_list_indexes_is_sorted(self):
        self.service.script(200, {"value": [{"name": "b"}, {"name": "a"}]})
        self.assertEqual(self.client.list_indexes(), ["a", "b"])

    def test_delete_index_reports_whether_it_existed(self):
        self.service.script(200, {"name": "handbook"})
        self.service.script(204, None)
        self.assertTrue(self.client.delete_index("handbook"))
        self.service.script(404, {"error": {"message": "no"}})
        self.assertFalse(self.client.delete_index("handbook"))

    def test_index_name_is_validated_before_it_reaches_a_url(self):
        for bad in ("../admin", "Handbook", "kb_2026"):
            with self.assertRaises(SearchConfigError):
                self.client.get_index(bad)
        self.assertEqual(self.service.requests, [])

    def test_upload_sends_the_search_action(self):
        self.service.script(200, {"value": [{"key": "1", "status": True, "statusCode": 200}]})
        result = self.client.upload_documents("handbook", [{"id": "1", "content": "x"}])
        _, _, body = self.service.requests[0]
        self.assertEqual(body["value"][0]["@search.action"], "mergeOrUpload")
        self.assertEqual(result["succeeded"], 1)

    def test_partial_success_raises_and_names_the_failed_key(self):
        self.service.script(207, {"value": [
            {"key": "1", "status": True, "statusCode": 200},
            {"key": "2", "status": False, "statusCode": 400, "errorMessage": "bad vector length"},
        ]})
        with self.assertRaises(SearchError) as caught:
            self.client.upload_documents("handbook", [{"id": "1"}, {"id": "2"}])
        self.assertIn("'2'", str(caught.exception))
        self.assertEqual(caught.exception.body["failed"], 1)

    def test_batching_splits_the_upload(self):
        for _ in range(3):
            self.service.script(200, {"value": [{"key": "k", "status": True}]})
        self.client.upload_documents("handbook", [{"id": str(i)} for i in range(3)], batch_size=1)
        self.assertEqual(len(self.service.requests), 3)

    def test_batch_size_is_bounded(self):
        with self.assertRaises(SearchConfigError):
            self.client.upload_documents("handbook", [{"id": "1"}], batch_size=0)
        with self.assertRaises(SearchConfigError):
            self.client.upload_documents("handbook", [{"id": "1"}], batch_size=1001)

    def test_delete_documents_uses_the_delete_action(self):
        self.service.script(200, {"value": [{"key": "1", "status": True}]})
        self.client.delete_documents("handbook", "id", ["1"])
        _, _, body = self.service.requests[0]
        self.assertEqual(body["value"][0], {"@search.action": "delete", "id": "1"})

    def test_keyword_query_shape(self):
        self.service.script(200, {"value": [{"id": "1"}]})
        hits = self.client.search("handbook", "escalate", top=3, filter="source eq 'kb'")
        _, _, body = self.service.requests[0]
        self.assertEqual(body["search"], "escalate")
        self.assertEqual(body["top"], 3)
        self.assertEqual(body["filter"], "source eq 'kb'")
        self.assertEqual(hits, [{"id": "1"}])

    def test_embedder_makes_the_query_hybrid(self):
        self.service.script(200, {"value": []})
        self.client.search("handbook", "escalate", vector_field="content_vector",
                           embedder=lambda text: [0.1, 0.2])
        _, _, body = self.service.requests[0]
        self.assertEqual(body["search"], "escalate")
        self.assertEqual(body["vectorQueries"][0]["vector"], [0.1, 0.2])
        self.assertEqual(body["vectorQueries"][0]["fields"], "content_vector")

    def test_vector_query_without_a_field_is_refused(self):
        with self.assertRaises(SearchConfigError):
            self.client.search("handbook", "x", vector=[0.1])

    def test_document_count_reads_stats(self):
        self.service.script(200, {"documentCount": 12})
        self.assertEqual(self.client.document_count("handbook"), 12)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.credential = FakeCredential()
        self.transport = Transport(credential=self.credential, opener=self.service.opener, sleep=lambda _: None)
        self.config = SearchConfig(endpoint=ENDPOINT, max_attempts=4)

    def call(self):
        return self.transport.request("GET", self.config.url("indexes"),
                                      max_attempts=self.config.max_attempts)

    def test_token_is_cached_across_requests(self):
        self.service.script(200, {"value": []})
        self.service.script(200, {"value": []})
        self.call()
        self.call()
        self.assertEqual(self.credential.calls, 1)

    def test_retryable_status_is_retried_then_succeeds(self):
        self.service.script(503, {"error": {"message": "busy"}})
        self.service.script(200, {"value": ["ok"]})
        self.assertEqual(self.call()["value"], ["ok"])
        self.assertEqual(len(self.service.requests), 2)

    def test_client_fault_is_not_retried(self):
        self.service.script(400, {"error": {"message": "bad request"}})
        with self.assertRaises(SearchError) as caught:
            self.call()
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(len(self.service.requests), 1)

    def test_retries_are_bounded(self):
        for _ in range(6):
            self.service.script(429, {"error": {"message": "throttled"}})
        with self.assertRaises(SearchError):
            self.call()
        self.assertEqual(len(self.service.requests), 4)

    def test_service_message_is_surfaced(self):
        self.service.script(403, {"error": {"message": "Search Index Data Contributor is required"}})
        with self.assertRaises(SearchError) as caught:
            self.call()
        self.assertIn("Data Contributor", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
