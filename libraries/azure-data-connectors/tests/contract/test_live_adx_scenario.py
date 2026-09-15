import importlib.util
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from azdata import HttpResponse


spec = importlib.util.spec_from_file_location("adx_live_case", Path(__file__).resolve().parents[1] / "live_tests/features/adx_query.py")
scenario = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scenario
spec.loader.exec_module(scenario)


class Credential:
    def __init__(self):
        self.calls = 0

    def get_token(self, _scope):
        self.calls += 1
        return SimpleNamespace(token="fixture", expires_on=2**31)


class Transport:
    def __init__(self, rows=None, *, partial=False, status=200):
        self.rows = [[1]] if rows is None else rows
        self.partial, self.status = partial, status
        self.requests = []

    async def request(self, request):
        self.requests.append(request)
        return HttpResponse(self.status, [
            {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
             "Columns": [{"ColumnName": "value", "ColumnType": "long"}], "Rows": self.rows},
            {"FrameType": "DataSetCompletion", "HasErrors": self.partial},
        ])


class LiveAdxScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def execute_case(self, expected, payload, *, comparison="ordered", semantic="query", maximum_bytes=65536):
        transport = SimpleNamespace(request=Mock())

        async def request(value):
            transport.request(value)
            return HttpResponse(200, payload)

        self.reserve = Mock(return_value=10)
        result = await scenario.run({"case_id": "LI-ADX-ORDINAL", "expression": '["Events"] | take 2',
            "parameters": {}, "expected_status": "success", "expected": expected,
            "comparison": comparison, "semantic": semantic},
            target={"endpoint": "https://fixture.eastus2.kusto.windows.net", "database": "Fixture", "principal_id": "offline"},
            limits={"timeout_seconds": 10, "max_rows": 100, "max_output_bytes": maximum_bytes},
            credential=Credential(), before_call=self.reserve, transport=SimpleNamespace(request=request))
        return result

    @staticmethod
    def payload(rows, columns):
        return [{"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
                 "Columns": [{"ColumnName": name, "ColumnType": kind} for name, kind in columns], "Rows": rows},
                {"FrameType": "DataSetCompletion", "HasErrors": False}]

    async def test_missing_oracle_refuses_before_any_reservation(self):
        with self.assertRaisesRegex(ValueError, "independent_expected_required"):
            await self.execute_case(None, self.payload([], [("value", "long")]))
        self.reserve.assert_not_called()

    async def test_explicit_typed_multiset_keeps_exact_membership_and_column_order(self):
        expected = {"columns": ["value"], "rows": [[1], [2]], "truncated": False}
        result = await self.execute_case(expected, self.payload([[2], [1]], [("value", "long")]), comparison="typed-multiset")
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        for rows, kind in (([[2]], "long"), ([[2], [3]], "long"), ([[True], [2]], "dynamic")):
            result = await self.execute_case(expected, self.payload(rows, [("value", kind)]), comparison="typed-multiset")
            self.assertEqual(result["outcome"], "FAIL")
        ordered = await self.execute_case(expected, self.payload([[2], [1]], [("value", "long")]))
        self.assertEqual(ordered["outcome"], "FAIL")

    async def test_wide_ordinal_schema_mismatch_and_duplicate_cannot_be_oracles(self):
        fields = [{"name": f"field_{180 - index:03d}", "type": "string"} for index in range(181)]
        expected = {"columns": ["fields", "field_count"], "rows": [[fields, 181]], "truncated": False}
        result = await self.execute_case(expected, self.payload([[fields, 181]], [("fields", "dynamic"), ("field_count", "long")]), semantic="ordinal-schema")
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        reordered = {**expected, "rows": [[list(reversed(fields)), 181]]}
        result = await self.execute_case(reordered, self.payload([[fields, 181]], [("fields", "dynamic"), ("field_count", "long")]), semantic="ordinal-schema")
        self.assertEqual(result["outcome"], "FAIL")
        for malformed in ((fields, 180), ([fields[0], fields[0]], 2), ("not-json", 1)):
            bad = {**expected, "rows": [list(malformed)]}
            with self.assertRaisesRegex(ValueError, "invalid_ordinal_schema"):
                await self.execute_case(bad, [], semantic="ordinal-schema")
            self.reserve.assert_not_called()

    async def test_null_or_boolean_count_is_not_an_observed_zero(self):
        for count in (None, True, -1):
            with self.assertRaisesRegex(ValueError, "invalid_count"):
                await self.execute_case({"columns": ["Count"], "rows": [[count]], "truncated": False},
                                        [], semantic="count")
            self.reserve.assert_not_called()

    async def test_lost_tail_cannot_pass_even_with_matching_lossy_expected(self):
        fields = [("value", "string")]
        expected = {"columns": ["value"], "rows": [], "truncated": True}
        result = await self.execute_case(expected, self.payload([["x" * 2000]], fields), maximum_bytes=256)
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["error_code"], "incomplete_result")

    async def test_native_observer_reaches_io_with_native_timeout_and_no_library_credit(self):
        from azure.kusto.data.aio import KustoClient
        from azure.kusto.data.response import KustoResponseDataSetV2

        calls = []

        async def native_io(client, endpoint, request, properties=None, stream_response=False):
            calls.append(endpoint)
            self.assertIsInstance(request.timeout, timedelta)
            self.assertTrue(properties.get_option("request_readonly", False))
            return KustoResponseDataSetV2([
                {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
                 "Columns": [{"ColumnName": "value", "ColumnType": "long"}], "Rows": [[1]]},
                {"FrameType": "DataSetCompletion", "HasErrors": False},
            ])

        with patch.object(KustoClient, "_execute", native_io):
            result = await scenario.observe({"expression": "print value=1", "parameters": {}},
                target={"endpoint": "https://fixture.eastus2.kusto.windows.net", "database": "Fixture"},
                limits={"timeout_seconds": 10, "max_rows": 20, "max_output_bytes": 65536},
                credential=Credential(), before_call=lambda: 10)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["expected"]["rows"], [[1]])
        self.assertNotIn("outcome", result)

    async def test_native_datetime_oracle_preserves_declared_type_and_value(self):
        from azure.kusto.data.aio import KustoClient
        from azure.kusto.data.response import KustoResponseDataSetV2

        async def native_io(client, endpoint, request, properties=None, stream_response=False):
            return KustoResponseDataSetV2([
                {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
                 "Columns": [{"ColumnName": "at", "ColumnType": "datetime"}],
                 "Rows": [["2026-08-13T03:00:00Z"]]},
                {"FrameType": "DataSetCompletion", "HasErrors": False},
            ])

        with patch.object(KustoClient, "_execute", native_io):
            result = await scenario.observe({"expression": "print at=datetime(2026-08-13T03:00:00Z)", "parameters": {}},
                target={"endpoint": "https://fixture.eastus2.kusto.windows.net", "database": "Fixture"},
                limits={"timeout_seconds": 10, "max_rows": 20, "max_output_bytes": 65536},
                credential=Credential(), before_call=lambda: 10)
        self.assertEqual(result["expected"]["rows"], [[{"type": "datetime", "value": "2026-08-13T03:00:00+00:00"}]])
        self.assertEqual(result["attempts"], 1)

    async def invoke(self, *, rows=None, expected_rows=None, partial=False, status=200, before_call=lambda: 10):
        credential, transport = Credential(), Transport(rows, partial=partial, status=status)
        case = {"case_id": "LI-ADX-01", "expression": "print value=1", "parameters": {},
                "expected_status": "success", "expected": {"columns": ["value"],
                    "rows": [[1]] if expected_rows is None else expected_rows, "truncated": False}}
        result = await scenario.run(case, target={"endpoint": "https://fixture.eastus2.kusto.windows.net", "database": "Fixture",
                                                 "principal_id": "fixture-principal"},
                                    limits={"timeout_seconds": 10, "max_rows": 20, "max_output_bytes": 65536},
                                    credential=credential, before_call=before_call, transport=transport)
        return result, transport, credential

    async def test_actual_facade_query_and_oracle_do_not_claim_live_when_io_is_controlled(self):
        result, transport, credential = await self.invoke()
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(credential.calls, 1)
        self.assertEqual(transport.requests[0].headers["Authorization"], "Bearer fixture")
        self.assertNotIn("rows", result)
        self.assertNotIn("expression", result)

    async def test_observed_output_is_returned_only_to_private_caller_sink(self):
        observed = {}
        expected = {"columns": ["value"], "rows": [[1]], "truncated": False}
        result = await scenario.run({"expression": "print value=1", "parameters": {}, "expected_status": "success", "expected": expected},
            target={"endpoint": "https://fixture.eastus2.kusto.windows.net", "database": "Fixture", "principal_id": "offline"},
            limits={"timeout_seconds": 10, "max_rows": 1, "max_output_bytes": 65536},
            credential=Credential(), before_call=lambda: 10, transport=Transport(), observed_out=observed)
        self.assertEqual(observed, expected)
        self.assertNotIn("rows", result)

    async def test_empty_schema_and_independent_oracle(self):
        result, _, _ = await self.invoke(rows=[], expected_rows=[])
        self.assertEqual(result["outcome"], "PASS_OFFLINE")
        result, _, _ = await self.invoke(expected_rows=[[2]])
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["error_code"], "oracle_mismatch")

    async def test_permission_and_partial_service_errors_are_not_empty_passes(self):
        for options in ({"partial": True}, {"status": 403}):
            with self.subTest(options=options):
                result, _, _ = await self.invoke(**options)
                self.assertEqual(result["outcome"], "FAIL")
                self.assertEqual(result["error_code"], "service_failed")

    async def test_missing_host_authority_refuses_before_credential_or_transport(self):
        def refuse():
            raise PermissionError("host authorization absent")

        with self.assertRaises(PermissionError):
            await self.invoke(before_call=refuse)


if __name__ == "__main__":
    unittest.main()