"""The retry policy reports what it actually did.

A permanent fault must stop after one attempt, and must say so. Reporting the retry budget
instead of the real attempt count reads as a throttling problem during an incident and sends
the reader looking for a transient fault that never happened.

Moved here with the connector: the policy now lives in
`app/components/data_connector_library/kusto/retry.py`.
"""

from __future__ import annotations

import unittest

from azure.kusto.data.exceptions import KustoClientError, KustoNetworkError, KustoThrottlingError

from azdata.event_store import AdxQueryError
from azdata.event_store.retry import call_with_retry, is_retryable


class _Failing:
    def __init__(self, exception: BaseException) -> None:
        self.exception = exception
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1
        raise self.exception


def _run(exception: BaseException, max_retries: int) -> tuple[int, AdxQueryError]:
    operation = _Failing(exception)
    with unittest.TestCase().assertRaises(AdxQueryError) as caught:
        call_with_retry(operation, max_retries=max_retries, base=0.001, cap=0.002,
                        description="probe")
    return operation.calls, caught.exception


class AttemptReportingTests(unittest.TestCase):
    def test_permanent_fault_stops_at_one_attempt_and_reports_one(self) -> None:
        calls, error = _run(TypeError("'NoneType' object is not iterable"), max_retries=4)
        self.assertEqual(calls, 1)
        self.assertIn("failed after 1 attempt(s)", str(error))
        self.assertFalse(error.retryable)

    def test_client_error_stops_at_one_attempt_and_reports_one(self) -> None:
        calls, error = _run(KustoClientError("bad request"), max_retries=4)
        self.assertEqual(calls, 1)
        self.assertIn("failed after 1 attempt(s)", str(error))

    def test_transient_fault_exhausts_the_budget_and_reports_it(self) -> None:
        calls, error = _run(KustoNetworkError("connection reset"), max_retries=2)
        self.assertEqual(calls, 3)
        self.assertIn("failed after 3 attempt(s)", str(error))
        self.assertTrue(error.retryable)

    def test_reported_count_equals_real_invocations_across_budgets(self) -> None:
        for budget in (0, 1, 5):
            with self.subTest(budget=budget):
                calls, error = _run(KustoThrottlingError("request is denied due to throttling"),
                                    max_retries=budget)
                self.assertEqual(calls, budget + 1)
                self.assertIn(f"failed after {calls} attempt(s)", str(error))


class ClassificationTests(unittest.TestCase):
    def test_permanent_and_transient_faults_are_classified_apart(self) -> None:
        self.assertFalse(is_retryable(TypeError("'NoneType' object is not iterable")))
        self.assertFalse(is_retryable(KustoClientError("bad request")))
        self.assertTrue(is_retryable(KustoNetworkError("connection reset")))
        self.assertTrue(is_retryable(KustoThrottlingError("throttled")))


if __name__ == "__main__":
    unittest.main()
