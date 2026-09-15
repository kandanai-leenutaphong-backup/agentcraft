import importlib.util
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from azdata import HttpResponse
from azure.core.pipeline.transport import AsyncHttpResponse, AsyncHttpTransport


spec = importlib.util.spec_from_file_location("search_live_case", Path(__file__).resolve().parents[1] / "live_tests/features/search_read.py")
scenario = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scenario)


class Transport:
    def __init__(self, response):
        self.response = response
        self.requests = []

    async def request(self, request):
        self.requests.append(request)
        return self.response


class NativeResponse(AsyncHttpResponse):
    def __init__(self, request, payload):
        super().__init__(request, None)
        self.status_code = 200
        self.headers = {"content-type": "application/json"}
        self.content_type = "application/json"
        self.payload = json.dumps(payload).encode()

    def body(self):
        return self.payload

    async def load_body(self):
        return None


class NativeTransport(AsyncHttpTransport):
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    async def open(self):
        return None

    async def close(self):
        return None

    async def __aexit__(self, *args):
        await self.close()

    async def send(self, request, **kwargs):
        self.requests.append(request)
        return NativeResponse(request, self.payload)


class LiveSearchScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, operation, response, expected, *, options=None, maximum_bytes=65536):
        transport = Transport(response)
        self.before_call = Mock(return_value=10)
        result = await scenario.run({"operation": operation, "expression": "fixture", "projection": ["id"],
            "options": options or {}, "expected_status": "success", "expected": expected},
            target={"endpoint": "https://fixture.search.windows.net", "index": "fixture", "key_field": "id",
                    "principal_id": "fixture-principal"},
            limits={"timeout_seconds": 10, "max_rows": 5, "max_output_bytes": maximum_bytes},
            credential=SimpleNamespace(get_token=lambda *args, **kwargs: SimpleNamespace(token="fixture", expires_on=2**31)),
            before_call=self.before_call, transport=transport)
        return result, transport

    async def test_query_preserves_count_annotations_and_never_claims_mocked_live(self):
        documents = [{"id": "fixture", "@search.score": 1.0}]
        expected = {"documents": documents, "metadata": {"count": 1}, "truncated": False}
        result, transport = await self.invoke("query", HttpResponse(200, {"value": documents, "@odata.count": 1}),
                                              expected, options={"count": True})
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        self.assertEqual(result["observed_sha256"], scenario.digest(expected))
        self.assertEqual(len(transport.requests), 1)
        self.assertTrue(transport.requests[0].body["count"])
        self.assertNotIn("documents", result)

    async def test_keyed_read_matches_independent_document(self):
        expected = {"documents": [{"id": "fixture"}], "metadata": {}, "truncated": False}
        result, transport = await self.invoke("read", HttpResponse(200, {"id": "fixture"}), expected)
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        self.assertEqual(transport.requests[0].method, "GET")

    async def test_schema_compares_ordered_fields_without_secret_configuration(self):
        schema = {"name": "fixture", "fields": [{"name": "id", "type": "Edm.String", "key": True}],
                  "@odata.etag": '"fixture"'}
        expected = {"documents": [scenario.schema_projection(schema)], "metadata": {}, "truncated": False}
        result, _ = await self.invoke("schema", HttpResponse(200, schema), expected)
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        projected = scenario.schema_projection({**schema, "credentials": {"apiKey": "private"}})
        self.assertNotIn("credentials", projected)

    async def test_empty_query_and_provider_denial_remain_distinct(self):
        expected = {"documents": [], "metadata": {"count": 0}, "truncated": False}
        result, _ = await self.invoke("query", HttpResponse(200, {"value": [], "@odata.count": 0}), expected,
                                     options={"count": True})
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        denied, _ = await self.invoke("query", HttpResponse(403), expected)
        self.assertEqual(denied["outcome"], "FAIL")
        self.assertEqual(denied["result_status"], "denied")
        self.assertEqual(denied["attempts"], 1)

    async def test_missing_oracle_refuses_before_reservation_or_io(self):
        with self.assertRaisesRegex(ValueError, "independent_expected_required"):
            await self.invoke("query", HttpResponse(200, {"value": []}), None)
        self.before_call.assert_not_called()

    async def test_missing_key_is_successful_absence_not_service_failure(self):
        expected = {"documents": [], "metadata": {}, "truncated": False}
        result, transport = await self.invoke("read", HttpResponse(404), expected)
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        self.assertEqual(result["row_count"], 0)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(transport.requests), 1)

    async def test_exact_projection_filter_top_ties_and_native_annotation(self):
        documents = [{"id": "z", "title": None, "@search.score": 1.25, "@search.reranker_score": 2.5},
                     {"id": "a", "@search.score": 1.25}]
        response_documents = [{**documents[0], "@search.rerankerScore": 2.5}, documents[1]]
        response_documents[0].pop("@search.reranker_score")
        expected = {"documents": documents, "metadata": {"count": 2}, "truncated": False}
        result, transport = await self.invoke("query", HttpResponse(200, {"value": response_documents, "@odata.count": 2}),
                                              expected, options={"count": True, "filter": "doc_kind eq 'analytic'"})
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        self.assertEqual(transport.requests[0].body, {"search": "fixture", "select": "id", "top": 5,
                         "count": True, "filter": "doc_kind eq 'analytic'"})
        self.assertEqual(result["attempts"], self.before_call.call_count)
        reordered = {**expected, "documents": list(reversed(documents))}
        failed, _ = await self.invoke("query", HttpResponse(200, {"value": response_documents, "@odata.count": 2}),
                                      reordered, options={"count": True})
        self.assertEqual(failed["outcome"], "FAIL")

    async def test_matching_lost_tail_cannot_be_credited_as_complete_observation(self):
        expected = {"documents": [{"id": "one"}], "metadata": {}, "truncated": True}
        result, _ = await self.invoke("query", HttpResponse(200, {"value": [
            {"id": "one"}, {"id": "two", "title": "x" * 1000}]}), expected, maximum_bytes=40)
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["error_code"], "incomplete_result")

    async def test_native_observer_does_not_use_candidate_mapper(self):
        expected = {"documents": [{"id": "one", "title": None}], "metadata": {"count": 1}, "truncated": False}
        native_transport = NativeTransport({"value": expected["documents"], "@odata.count": 1})
        reserve = Mock(return_value=10)
        with patch.object(scenario, "candidate_observation", create=True, side_effect=AssertionError("candidate mapper reached")):
            observation = await scenario.observe(
                {"operation": "query", "expression": "*", "projection": ["id", "title"], "options": {"count": True}},
                target={"endpoint": "https://fixture.search.windows.net", "index": "fixture"},
                limits={"max_rows": 5, "max_output_bytes": 65536},
                credential=SimpleNamespace(get_token=lambda *args, **kwargs: SimpleNamespace(token="offline", expires_on=2**31)),
                before_call=reserve, transport=native_transport)
        self.assertEqual(observation["expected"], expected)
        self.assertEqual(observation["attempts"], 1)
        self.assertEqual(len(native_transport.requests), reserve.call_count)


class SearchCitationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        document = {"id": "one", "title": "Fixture", "path": "source.yaml", "commit": "fixed"}
        common = {"operation": "read", "expression": "one", "projection": [], "options": {},
                  "expected_status": "success", "parameters": {}}
        read = {**common, "case_id": "LI-SEARCH-CITATION-READ", "expected": {
            "documents": [document], "metadata": {}, "truncated": False}}
        missing = {**common, "case_id": "LI-SEARCH-CITATION-MISSING", "expression": "missing", "expected": {
            "documents": [], "metadata": {}, "truncated": False}}
        query = {"case_id": "LI-SEARCH-CITATION-QUERY", "operation": "query", "expression": "*",
                 "parameters": {}, "projection": ["id", "path", "commit"], "options": {},
                 "expected_status": "success", "workflow": "search-citation", "reads": [read], "missing": missing,
                 "expected": {"documents": [{"id": "one", "path": "source.yaml", "commit": "fixed"}],
                              "metadata": {}, "truncated": False}}
        return query, [HttpResponse(200, {"value": query["expected"]["documents"]}),
                       HttpResponse(200, document), HttpResponse(404)]

    async def invoke(self, case, responses):
        from tests.live_tests.workflows.search_citation import run

        class ScriptedTransport(Transport):
            async def request(self, request):
                self.requests.append(request)
                response = self.response.pop(0)
                if isinstance(response, Exception):
                    raise response
                return response

        transport = ScriptedTransport(responses)
        self.reserve = Mock(return_value=10)
        report = await run(case, target={"endpoint": "https://fixture.search.windows.net",
            "index": "fixture", "key_field": "id", "principal_id": "offline"},
            limits={"timeout_seconds": 10, "max_rows": 1, "max_output_bytes": 65536},
            credential=SimpleNamespace(get_token=lambda *args, **kwargs: SimpleNamespace(token="offline", expires_on=2**31)),
            before_call=self.reserve, transport=transport)
        return report, transport

    async def test_actual_query_output_drives_citation_and_separate_missing_read(self):
        case, responses = self.fixture()
        report, transport = await self.invoke(case, responses)
        self.assertEqual(report["outcome"], "PASS_OFFLINE")
        self.assertEqual(report["attempts"], 3)
        self.assertEqual([request.method for request in transport.requests], ["POST", "GET", "GET"])
        self.assertIn("one", transport.requests[1].url)
        self.assertIn("missing", transport.requests[2].url)
        self.assertEqual([step["outcome"] for step in report["steps"]], ["PASS_OFFLINE"] * 3)
        self.assertNotIn("source.yaml", json.dumps(report))

    async def test_drift_failure_retains_unrun_denominator(self):
        case, responses = self.fixture()
        responses[0] = HttpResponse(200, {"value": [{"id": "other"}]})
        report, transport = await self.invoke(case, responses)
        self.assertEqual(report["outcome"], "FAIL")
        self.assertEqual([step["outcome"] for step in report["steps"]], ["FAIL", "NOT_RUN", "NOT_RUN"])
        self.assertEqual(len(transport.requests), 1)

    async def test_standalone_passing_read_with_wrong_provenance_fails_composition(self):
        case, responses = self.fixture()
        case = copy.deepcopy(case)
        case["reads"][0]["expected"]["documents"][0]["path"] = "different.yaml"
        responses[1] = HttpResponse(200, case["reads"][0]["expected"]["documents"][0])
        report, _ = await self.invoke(case, responses)
        self.assertEqual(report["outcome"], "FAIL")
        self.assertEqual(report["error_code"], "oracle_mismatch")
        self.assertEqual(report["steps"][-1]["outcome"], "NOT_RUN")

    async def test_missing_downstream_baseline_refuses_before_query(self):
        case, responses = self.fixture()
        case["reads"][0]["expected"] = None
        with self.assertRaisesRegex(ValueError, "independent_expected_required"):
            await self.invoke(case, responses)
        self.reserve.assert_not_called()


if __name__ == "__main__":
    unittest.main()