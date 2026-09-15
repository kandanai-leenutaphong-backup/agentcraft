from __future__ import annotations

import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

from azdata import HttpResponse

from app.cybereye.backend.data.adx import ReadOnlyAdx
from app.cybereye.backend.data.azdata_client import AdxQueryClient


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
    def __init__(self, *, rows=None, partial=False, status=200):
        self.rows = [[1, ["row-1"]]] if rows is None else rows
        self.partial, self.status = partial, status
        self.requests, self.loops = [], []

    async def request(self, request):
        self.requests.append(request)
        self.loops.append(asyncio.get_running_loop())
        return HttpResponse(self.status, [
            {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult",
             "TableName": "PrimaryResult", "Columns": [
                 {"ColumnName": "n", "ColumnType": "long"},
                 {"ColumnName": "evidence_ids", "ColumnType": "dynamic"},
             ], "Rows": self.rows},
            {"FrameType": "DataSetCompletion", "HasErrors": self.partial},
        ])


class AzdataMigrationTests(unittest.TestCase):
    def reader(self, **kwargs):
        transport, credential = Transport(**kwargs), Credential()
        connector = AdxQueryClient(endpoint="https://fixture.australiaeast.kusto.windows.net",
                                   database="PerthCyber", credential=credential,
                                   max_rows=200, timeout_seconds=30, transport=transport)
        self.addCleanup(connector.close)
        reader = ReadOnlyAdx.__new__(ReadOnlyAdx)
        reader.connector = connector
        return reader, transport, credential

    def test_real_library_preserves_rows_and_binds_values_outside_query(self):
        reader, transport, credential = self.reader()
        moment = datetime(2026, 8, 13, tzinfo=timezone.utc)
        host = "host'; .drop table EventsUnified"
        result = reader.parameterized("EventsUnified | where source_time >= start and device_name == host",
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
                                                     "ids": '["a", "b"]'})
        self.assertTrue(properties["Options"]["request_readonly"])
        self.assertTrue(properties["Options"]["request_remote_entities_disabled"])
        self.assertEqual(credential.scopes, ["https://kusto.kusto.windows.net/.default"])

    def test_empty_result_retains_schema(self):
        reader, _, _ = self.reader(rows=[])
        result = reader.query("EventsUnified | take 1")
        self.assertEqual(result.columns, ["n", "evidence_ids"])
        self.assertEqual(result.rows, [])

    def test_row_cap_retains_truncation_signal(self):
        reader, _, _ = self.reader(rows=[[index, []] for index in range(201)])
        result = reader.query("EventsUnified", 5000)
        self.assertEqual(result.row_count, 200)
        self.assertTrue(result.truncated)

    def test_partial_service_failure_is_not_success(self):
        reader, _, _ = self.reader(partial=True)
        with self.assertRaisesRegex(RuntimeError, "kusto_partial_error"):
            reader.query("EventsUnified")

    def test_permission_failure_is_not_empty(self):
        reader, _, _ = self.reader(status=403)
        with self.assertRaises((ValueError, RuntimeError)):
            reader.query("EventsUnified")

    def test_refusals_do_not_acquire_credentials_or_send_requests(self):
        reader, transport, credential = self.reader()
        for query in (".drop table EventsUnified", "OtherTable | take 1",
                      "EventsUnified | evaluate python(typeof(*))"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                reader.query(query)
        for limit in (0, -1, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                reader.query("EventsUnified", limit)
        with self.assertRaises(ValueError):
            reader.parameterized("EventsUnified", {"bad); .drop": "value"})
        self.assertEqual(transport.requests, [])
        self.assertEqual(credential.scopes, [])

    def test_parallel_sync_callers_share_one_loop_and_close_once(self):
        reader, transport, credential = self.reader()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: reader.query("EventsUnified"), range(8)))
        self.assertEqual(len(results), 8)
        self.assertEqual(len(set(transport.loops)), 1)
        reader.close()
        reader.close()
        self.assertFalse(reader.connector._thread.is_alive())
        self.assertFalse(credential.closed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            reader.query("EventsUnified")

    def test_health_uses_read_query_not_management_endpoint(self):
        reader, transport, _ = self.reader()
        self.assertTrue(reader.health()["reachable"])
        self.assertTrue(transport.requests[0].url.endswith("/v2/rest/query"))


if __name__ == "__main__":
    unittest.main()