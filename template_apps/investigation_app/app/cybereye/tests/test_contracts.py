from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from app.cybereye.backend.api.scanning import evidence
from app.cybereye.backend.data.adx import ReadOnlyAdx
from app.cybereye.backend.models import (
    Pattern, QueryResponse, ScanRequest, ScanResponse, ScanSummary, Situation,
)
from app.cybereye.backend.security import OwnedCache

import _auth_support

CALLER = _auth_support.DEFAULT
OTHER_CALLER = _auth_support.OTHER


class FakeResult:
    columns = ("n",)
    rows = ((1,),)
    elapsed_seconds = 0.01
    client_request_id = "test;1"


class FakeConnector:
    def __init__(self) -> None:
        self.last_query = ""

    def query(self, query: str, *args, **kwargs):
        self.last_query = query
        return FakeResult()


class ReadOnlyQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adx = ReadOnlyAdx.__new__(ReadOnlyAdx)
        self.adx.connector = FakeConnector()

    def test_safe_pipeline_is_bounded(self) -> None:
        result = self.adx.query("EventsUnified | summarize n=count()", 20)
        self.assertEqual(result.rows, [[1]])
        self.assertIn("| take 21", self.adx.connector.last_query)

    def test_kql_range_syntax_is_allowed(self) -> None:
        self.adx.query(
            "EventsUnified | where source_time between (datetime(2026-08-13) .. datetime(2026-08-14))"
        )

    def test_management_and_external_queries_are_rejected(self) -> None:
        rejected = [
            ".drop table EventsUnified",
            "OtherTable | take 1",
            "EventsUnified; .drop table EventsUnified",
            "EventsUnified | evaluate python(typeof(*))",
            "EventsUnified | join externaldata(x:string)[h@'https://example.invalid/x'] on x",
            "EventsUnified | invoke plugin()",
        ]
        for query in rejected:
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.adx.query(query)

    def test_row_cap_applies(self) -> None:
        self.adx.query("EventsUnified | take 5000", 5000)
        self.assertIn("| take 201", self.adx.connector.last_query)

    def test_large_cell_is_truncated(self) -> None:
        rows, truncated = self.adx._bounded_rows((("x" * 10_000,),), 10)
        self.assertTrue(truncated)
        self.assertLess(len(rows[0][0]), 5_000)

    def test_total_result_size_is_bounded(self) -> None:
        rows, truncated = self.adx._bounded_rows(tuple(("x" * 4_000,) for _ in range(100)), 100)
        self.assertTrue(truncated)
        self.assertLess(len(rows), 100)


class ContractTests(unittest.TestCase):
    def test_scan_window_is_utc_and_bounded(self) -> None:
        request = ScanRequest()
        self.assertEqual(request.start.tzinfo, timezone.utc)
        self.assertLess((request.end - request.start).total_seconds(), 48 * 3600)

    def test_query_response_serializes_datetime(self) -> None:
        response = QueryResponse(
            columns=["source_time"], rows=[[datetime(2026, 8, 13, tzinfo=timezone.utc)]],
            row_count=1, truncated=False, max_rows=1, elapsed_ms=1, client_request_id="test",
        )
        self.assertIn("2026-08-13T00:00:00Z", response.model_dump_json())


class EvidenceAcrossReplicasTests(unittest.IsolatedAsyncioTestCase):
    """`last_scan` is per-process and ingress has no session affinity.

    Measured on the deployed app before the fix: 21 of 40 evidence reads returned 404 while two
    replicas were warm. Resolution must not depend on which replica served the scan.
    """

    WINDOW = {"start": datetime(2026, 8, 12, tzinfo=timezone.utc),
              "end": datetime(2026, 8, 12, 12, tzinfo=timezone.utc)}

    def setUp(self) -> None:
        self.situation = _situation("cyb_known")
        self.scan = ScanResponse(
            window_start=self.WINDOW["start"], window_end=self.WINDOW["end"],
            situations=[self.situation],
            summary=ScanSummary(situations=1, critical=0, high=0, evidence_rows=1, elapsed_ms=1),
        )

    def _request(self, last_scan: ScanResponse | None) -> Any:
        outer = self
        cache: OwnedCache[ScanResponse] = OwnedCache()
        if last_scan is not None:
            cache.put(CALLER.id, last_scan)

        class Scanner:
            calls = 0

            async def scan_async(self, request: ScanRequest) -> ScanResponse:
                Scanner.calls += 1
                return outer.scan

        class Adx:
            def parameterized(self, kql: str, params: dict[str, Any], max_rows: int) -> QueryResponse:
                return QueryResponse(columns=["resource_id"], rows=[["r1"]], row_count=1,
                                     truncated=False, max_rows=max_rows, elapsed_ms=1,
                                     client_request_id="test")

        state = SimpleNamespace(last_scan=cache, scanner=Scanner(), adx=Adx())
        return SimpleNamespace(app=SimpleNamespace(state=state)), Scanner

    async def test_served_from_local_state_without_rescanning(self) -> None:
        request, scanner = self._request(self.scan)
        result = await evidence("cyb_known", request, CALLER, **self.WINDOW)
        self.assertEqual(result["situation_id"], "cyb_known")
        self.assertEqual(scanner.calls, 0)

    async def test_rederived_when_this_replica_never_served_the_scan(self) -> None:
        request, scanner = self._request(None)
        result = await evidence("cyb_known", request, CALLER, **self.WINDOW)
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(scanner.calls, 1)

    async def test_rederived_when_this_replica_holds_a_different_window(self) -> None:
        other = self.scan.model_copy(update={"situations": [_situation("cyb_other")]})
        request, scanner = self._request(other)
        result = await evidence("cyb_known", request, CALLER, **self.WINDOW)
        self.assertEqual(result["situation_id"], "cyb_known")
        self.assertEqual(scanner.calls, 1)

    async def test_without_a_window_the_404_names_the_remedy(self) -> None:
        request, _ = self._request(None)
        with self.assertRaises(HTTPException) as caught:
            await evidence("cyb_known", request, CALLER)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertIn("start=", caught.exception.detail)

    async def test_unknown_id_in_a_supplied_window_still_404s(self) -> None:
        request, _ = self._request(None)
        with self.assertRaises(HTTPException) as caught:
            await evidence("cyb_absent", request, CALLER, **self.WINDOW)
        self.assertEqual(caught.exception.status_code, 404)

    async def test_another_caller_never_resolves_from_this_callers_cached_scan(self) -> None:
        """A cached scan is the caller's own. Someone else re-derives or gets nothing."""
        request, scanner = self._request(self.scan)
        with self.assertRaises(HTTPException) as caught:
            await evidence("cyb_known", request, OTHER_CALLER)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(scanner.calls, 0)


def _situation(situation_id: str) -> Situation:
    moment = datetime(2026, 8, 12, 3, tzinfo=timezone.utc)
    pattern = Pattern(
        detector="explicit_credential_burst", rule_id="explicit_credential_burst",
        rule_version="1.0.0", label="Explicit credential use", description="d",
        observed_fact="f", count=5, score=35, confidence="high", role="anchor",
        first_seen=moment, last_seen=moment, summary="s", evidence_ids=["r1"],
        evidence_semantics="e",
    )
    return Situation(
        situation_id=situation_id, host="svpmn082", principal="admLRhodes",
        severity="medium", confidence="medium", score=35, detector_count=1,
        first_seen=moment, last_seen=moment, patterns=[pattern],
    )


if __name__ == "__main__":
    unittest.main()
