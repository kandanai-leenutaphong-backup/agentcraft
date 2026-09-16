from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from azdata import HttpResponse

from app.cybereye.backend.data.adx import ReadOnlyAdx


class Credential:
    def __init__(self):
        self.scopes = []
        self.closed = False

    def get_token(self, scope):
        self.scopes.append(scope)
        return SimpleNamespace(token="fixture", expires_on=2**31)

    def close(self):
        self.closed = True


class Transport:
    def __init__(self, *, rows=None, columns=None, partial=False, status=200):
        self.rows = [[1, ["row-1"]]] if rows is None else rows
        self.columns = columns or [("n", "long"), ("evidence_ids", "dynamic")]
        self.partial, self.status = partial, status
        self.requests, self.loops = [], []

    async def request(self, request):
        self.requests.append(request)
        self.loops.append(asyncio.get_running_loop())
        return HttpResponse(self.status, [
            {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult",
             "TableName": "PrimaryResult", "Columns": [
                 {"ColumnName": name, "ColumnType": kind} for name, kind in self.columns
             ], "Rows": self.rows},
            {"FrameType": "DataSetCompletion", "HasErrors": self.partial},
        ])


class AzdataMigrationTests(unittest.IsolatedAsyncioTestCase):
    def reader(self, **kwargs):
        transport, credential = Transport(**kwargs), Credential()
        reader = ReadOnlyAdx(credential=credential, transport=transport)
        self.addAsyncCleanup(reader.aclose)
        return reader, transport, credential

    async def test_real_library_preserves_rows_and_binds_values_outside_query(self):
        reader, transport, credential = self.reader()
        moment = datetime(2026, 8, 13, tzinfo=timezone.utc)
        host = "host'; .drop table EventsUnified"
        result = await reader.parameterized("EventsUnified | where source_time >= start and device_name == host",
                                      {"start": moment, "host": host, "ids": ["a", "b"]}, 10)
        self.assertEqual(result.rows, [[1, ["row-1"]]])
        self.assertEqual(result.columns, ["n", "evidence_ids"])
        self.assertFalse(result.truncated)
        self.assertTrue(result.client_request_id.startswith("azdata;"))
        request = transport.requests[0]
        self.assertIn("declare query_parameters(start:datetime, host:string, ids:dynamic);", request.body["csl"])
        self.assertIn("| take 11", request.body["csl"])
        self.assertNotIn(host, request.body["csl"])
        properties = json.loads(request.body["properties"])
        self.assertEqual(properties["Parameters"], {"start": moment.isoformat(), "host": host,
                                                     "ids": '["a","b"]'})
        self.assertTrue(properties["Options"]["request_readonly"])
        self.assertTrue(properties["Options"]["request_remote_entities_disabled"])
        self.assertEqual(credential.scopes, ["https://kusto.kusto.windows.net/.default"])

    async def test_empty_result_retains_schema(self):
        reader, _, _ = self.reader(rows=[])
        result = await reader.query("EventsUnified | take 1")
        self.assertEqual(result.columns, ["n", "evidence_ids"])
        self.assertEqual(result.rows, [])

    async def test_native_timestamps_and_dynamic_containers_survive_application_copy(self):
        moment = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)
        reader, _, _ = self.reader(
            columns=[("source_time", "datetime"), ("evidence", "dynamic")],
            rows=[[moment.isoformat(), {"ids": ["row-1"]}]],
        )
        result = await reader.query("EventsUnified | project source_time, evidence")
        self.assertEqual(result.rows, [[moment, {"ids": ["row-1"]}]])
        self.assertIsInstance(result.rows[0][0], datetime)
        self.assertEqual(result.model_dump(mode="json")["rows"][0][0], "2026-08-13T02:30:00Z")
        result.rows[0][1]["ids"].append("local-copy")
        self.assertEqual((await reader.query("EventsUnified")).rows[0][1], {"ids": ["row-1"]})

    async def test_row_cap_retains_truncation_signal(self):
        reader, _, _ = self.reader(rows=[[index, []] for index in range(201)])
        result = await reader.query("EventsUnified", 5000)
        self.assertEqual(result.row_count, 200)
        self.assertTrue(result.truncated)

    async def test_partial_service_failure_is_not_success(self):
        reader, _, _ = self.reader(partial=True)
        with self.assertRaisesRegex(RuntimeError, "kusto_partial_error"):
            await reader.query("EventsUnified")

    async def test_permission_failure_is_not_empty(self):
        reader, _, _ = self.reader(status=403)
        with self.assertRaises((ValueError, RuntimeError)):
            await reader.query("EventsUnified")

    async def test_refusals_do_not_acquire_credentials_or_send_requests(self):
        reader, transport, credential = self.reader()
        for query in (".drop table EventsUnified", "OtherTable | take 1",
                      "EventsUnified | evaluate python(typeof(*))"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                await reader.query(query)
        for limit in (0, -1, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await reader.query("EventsUnified", limit)
        with self.assertRaises(ValueError):
            await reader.parameterized("EventsUnified", {"bad); .drop": "value"})
        self.assertEqual(transport.requests, [])
        self.assertEqual(credential.scopes, [])

    async def test_identity_reports_attempts_without_turning_unknown_into_zero(self):
        reader, transport, _ = self.reader()
        self.assertEqual(reader.library_identity()["query_metrics"], {
            "submitted": 0, "completed": 0, "known_attempts": 0, "unknown_attempt_queries": 0,
        })
        await reader.query("EventsUnified")
        with patch.object(reader.connector, "query", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                await reader.query("EventsUnified")
            identity = reader.library_identity()
        self.assertEqual(identity["query_metrics"], {
            "submitted": 2, "completed": 2, "known_attempts": 1, "unknown_attempt_queries": 1,
        })
        identity["query_metrics"]["known_attempts"] = 100
        self.assertEqual(reader.library_identity()["query_metrics"]["known_attempts"], 1)
        self.assertEqual(len(transport.requests), 1)

    async def test_parallel_async_callers_share_one_loop_and_borrow_identity(self):
        reader, transport, credential = self.reader()
        results = await asyncio.gather(*(reader.query("EventsUnified") for _ in range(8)))
        self.assertEqual(len(results), 8)
        self.assertEqual(len(set(transport.loops)), 1)
        self.assertEqual(reader.library_identity()["query_metrics"], {
            "submitted": 8, "completed": 8, "known_attempts": 8, "unknown_attempt_queries": 0,
        })
        await reader.aclose()
        await reader.aclose()
        self.assertFalse(credential.closed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            await reader.query("EventsUnified")

    async def test_health_uses_read_query_not_management_endpoint(self):
        reader, transport, _ = self.reader()
        self.assertTrue((await reader.health())["reachable"])
        self.assertTrue(transport.requests[0].url.endswith("/v2/rest/query"))

    async def test_identity_snapshots_actual_runtime_without_querying(self):
        import azdata

        reader, transport, credential = self.reader()
        identity = reader.library_identity()
        root = Path(azdata.__file__).resolve().parent
        files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in root.rglob("*.py")}
        expected = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(identity["source_sha256"], expected)
        self.assertEqual(identity["version"], importlib.metadata.version("azdata"))
        self.assertEqual(identity["transport"], "injected")
        identity["source_sha256"] = "changed copy"
        self.assertEqual(reader.library_identity()["source_sha256"], expected)
        self.assertEqual(transport.requests, [])
        self.assertEqual(credential.scopes, [])


if __name__ == "__main__":
    unittest.main()