"""Retained Search safety through the native async knowledge owner. Offline only."""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from azdata import ConnectorConfig, HttpResponse, Limits, Policy, ResourceAddress

from app.cybereye.backend.knowledge import search


INDEX = "fixture"
HOST = "unit.search.windows.net"
CONFIG = ConnectorConfig(f"https://{HOST}", ResourceAddress({"index": INDEX}), (HOST,))
POLICY = Policy("offline-reader", grants={"query", "read"}, max_concurrency=1,
                limits=Limits(timeout_seconds=30, max_items=100,
                              max_output_bytes=1_048_576, max_attempts=1))


class AsyncSearchSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await search.reset_client()
        self.addAsyncCleanup(search.reset_client)
        self.credential = SimpleNamespace(
            get_token=Mock(return_value=SimpleNamespace(token="offline-fixture", expires_on=2**31)),
            close=Mock())

    async def configure(self, *responses, policy=POLICY):
        transport = SimpleNamespace(request=AsyncMock(side_effect=list(responses)), aclose=AsyncMock())
        client = await search.configure(CONFIG, credential=self.credential, policy=policy, transport=transport)
        return client, transport

    async def test_query_preserves_native_annotations_nested_values_and_order(self):
        documents = [
            {"id": "z", "title": None, "tags": ["Windows", "Linux"],
             "nested": {"ordinary": None, "values": [1, True]}, "@search.score": 1.25,
             "@search.rerankerScore": 2.5, "@search.highlights": {"title": ["hit"]}},
            {"id": "a", "@search.score": 1.25},
        ]
        _, transport = await self.configure(HttpResponse(200, {"value": documents}))
        hits, relaxed, expression = await search.retrieve(
            doc_kind="analytic", query="discovery", terms={}, top=2)
        request = transport.request.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.body["search"], "discovery")
        self.assertEqual(request.body["top"], 2)
        self.assertEqual(request.body["filter"], "doc_kind eq 'analytic'")
        self.assertEqual(request.body["select"], ",".join(search.SELECT))
        self.assertEqual((relaxed, expression), ([], "doc_kind eq 'analytic'"))
        self.assertEqual([row["id"] for row in hits], ["z", "a"])
        self.assertIsNone(hits[0]["title"])
        self.assertNotIn("title", hits[1])
        self.assertEqual(hits[0]["nested"], {"ordinary": None, "values": [1, True]})
        self.assertIsInstance(hits[0]["nested"], dict)
        self.assertIsInstance(hits[0]["nested"]["values"], list)
        self.assertEqual(hits[0]["@search.reranker_score"], 2.5)
        self.assertNotIn("@search.rerankerScore", hits[0])
        self.assertEqual(transport.request.call_count, 1)

    async def test_count_is_exact_metadata_not_number_of_key_documents(self):
        for count in (0, 1234):
            with self.subTest(count=count):
                _, transport = await self.configure(
                    HttpResponse(200, {"@odata.count": count, "value": [{"id": "one"}]}),
                    HttpResponse(200, {"@odata.count": 0, "value": []}),
                    HttpResponse(200, {"@odata.count": 0, "value": []}))
                report = await search.status()
                self.assertEqual(report["documents"], count)
                self.assertEqual(report["available"], count > 0)
                self.assertEqual(transport.request.call_args_list[0].args[0].body,
                                 {"search": "*", "top": 1, "select": "id", "count": True})

    async def test_count_unknown_or_invalid_is_not_reported_as_zero(self):
        for metadata in ({}, {"@odata.count": None}, {"@odata.count": True}, {"@odata.count": -1}):
            with self.subTest(metadata=metadata):
                _, transport = await self.configure(HttpResponse(200, {**metadata, "value": []}))
                report = await search.status()
                self.assertFalse(report["available"])
                self.assertFalse(report["local_fallback"])
                self.assertNotIn("documents", report)
                self.assertIn("reason", report)
                self.assertEqual(transport.request.call_count, 1)

    async def test_keyed_content_absence_and_failure_remain_distinct(self):
        document = {"id": "analytic_T1001-0bc78cde", "doc_kind": "analytic", "doc_id": "T1001",
                    "title": None, "path": "source.md", "commit": "fixture", "nested": [1, {"value": None}]}
        _, transport = await self.configure(HttpResponse(200, document), HttpResponse(404), HttpResponse(403))
        self.assertEqual(await search.get_by_doc_id("analytic", "T1001"), document)
        self.assertIsNone(await search.get_by_doc_id("analytic", "missing"))
        with self.assertRaises(search.KnowledgeUnavailable):
            await search.get_by_doc_id("analytic", "unavailable")
        self.assertEqual([call.args[0].method for call in transport.request.call_args_list], ["GET"] * 3)

    async def test_malformed_keyed_document_is_unavailable(self):
        for body in ({"title": "no key"}, {"id": "other"}, ["not a document"]):
            with self.subTest(body=body):
                _, transport = await self.configure(HttpResponse(200, body))
                with self.assertRaises(search.KnowledgeUnavailable):
                    await search.get_by_doc_id("analytic", "T1001")
                self.assertEqual(transport.request.call_count, 1)

    async def test_first_response_continuation_does_not_walk_or_sort(self):
        _, transport = await self.configure(HttpResponse(200, {
            "value": [{"id": "z"}, {"id": "a"}],
            "@odata.nextLink": f"https://{HOST}/indexes/{INDEX}/docs/search?api-version=2024-07-01",
            "@search.nextPageParameters": {"search": "*", "top": 2, "skip": 2},
        }))
        hits, relaxed, _ = await search.retrieve(doc_kind="analytic", query="*", terms={}, top=2)
        self.assertEqual(hits, [{"id": "z"}, {"id": "a"}])
        self.assertEqual(relaxed, [])
        self.assertEqual(transport.request.call_count, 1)

    async def test_failures_and_output_loss_are_safe_and_never_relax_or_retry(self):
        policy = replace(POLICY, limits=replace(POLICY.limits, max_output_bytes=40))
        responses = (
            HttpResponse(403, {"error": {"message": "private-provider-body"}}),
            HttpResponse(429), HttpResponse(500), TimeoutError("private-provider-body"),
            HttpResponse(200, {"value": [{"id": "one"}, {"id": "two", "text": "x" * 100}]}),
        )
        for response in responses:
            with self.subTest(response_type=type(response).__name__):
                _, transport = await self.configure(response, policy=policy)
                with self.assertRaises(search.KnowledgeUnavailable) as caught:
                    await search.retrieve(doc_kind="analytic", query="*", terms={"platforms": ["Windows"]}, top=2)
                self.assertNotIn("private-provider-body", str(caught.exception))
                self.assertEqual(transport.request.call_count, 1)

    async def test_exact_integer_limits_and_missing_grant_refuse_before_io(self):
        _, transport = await self.configure()
        for top in (0, 101, -1, True, 1.0, "1", None):
            with self.subTest(top=top), self.assertRaises(search.KnowledgeUnavailable):
                await search.retrieve(doc_kind="analytic", query="*", terms={}, top=top)
        self.credential.get_token.assert_not_called()
        transport.request.assert_not_called()
        _, denied_transport = await self.configure(policy=replace(POLICY, grants=frozenset()))
        with self.assertRaises(search.KnowledgeUnavailable):
            await search.retrieve(doc_kind="analytic", query="*", terms={}, top=1)
        self.credential.get_token.assert_not_called()
        denied_transport.request.assert_not_called()

    async def test_accounting_covers_counts_keyed_failure_and_borrowed_lifetime(self):
        _, transport = await self.configure(
            *(HttpResponse(200, {"value": [], "@odata.count": 0}) for _ in range(3)),
            HttpResponse(404), HttpResponse(403))
        self.assertEqual(search.describe()["metrics"]["submitted"], 0)
        self.credential.get_token.assert_not_called()
        transport.request.assert_not_called()
        self.assertEqual((await search.status())["documents"], 0)
        self.assertIsNone(await search.get_by_doc_id("analytic", "missing"))
        with self.assertRaises(search.KnowledgeUnavailable):
            await search.retrieve(doc_kind="analytic", query="*", terms={}, top=1)
        self.assertEqual(search.describe()["metrics"], {
            "submitted": 5, "completed": 5, "known_attempts": 5,
            "unknown_attempt_operations": 0, "operations": {"query": 4, "read": 1}})
        self.assertEqual(transport.request.call_count, 5)
        await search.reset_client()
        self.credential.close.assert_not_called()
        transport.aclose.assert_not_awaited()

    async def test_unreported_attempt_is_unknown_never_zero(self):
        client, transport = await self.configure()
        with patch.object(client, "query", AsyncMock(side_effect=OSError("private-provider-body"))):
            with self.assertRaises(search.KnowledgeUnavailable) as caught:
                await search.retrieve(doc_kind="analytic", query="*", terms={}, top=1)
        self.assertNotIn("private-provider-body", str(caught.exception))
        self.assertEqual(search.describe()["metrics"], {
            "submitted": 1, "completed": 1, "known_attempts": 0,
            "unknown_attempt_operations": 1, "operations": {"query": 1, "read": 0}})
        self.credential.get_token.assert_not_called()
        transport.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()