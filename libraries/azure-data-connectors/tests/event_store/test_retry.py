"""Retain the parent consumer's actual-attempt contract under the canonical owner."""

import unittest
from unittest.mock import MagicMock

from azure.kusto.data.exceptions import KustoClientError, KustoNetworkError, KustoThrottlingError

from azdata.event_store import AdxClient, AdxConfig, AdxQueryError, EventStorePolicy
from azdata.event_store.retry import call_with_retry, is_retryable


class RetryTests(unittest.TestCase):
    def failure(self, error, budget):
        operation = MagicMock(side_effect=error)
        with self.assertRaises(AdxQueryError) as caught:
            call_with_retry(operation, max_retries=budget, base=0, cap=0, description="offline-probe")
        return operation.call_count, caught.exception

    def test_permanent_fault_stops_at_one_attempt_and_reports_one(self):
        calls, error = self.failure(TypeError("fixture failure"), 4)
        self.assertEqual(calls, 1)
        self.assertIn("failed after 1 attempt(s)", str(error))
        self.assertFalse(error.retryable)

    def test_client_error_stops_at_one_attempt_and_reports_one(self):
        calls, error = self.failure(KustoClientError("bad request"), 4)
        self.assertEqual(calls, 1)
        self.assertIn("failed after 1 attempt(s)", str(error))

    def test_transient_fault_exhausts_budget_and_reports_it(self):
        calls, error = self.failure(KustoNetworkError("connection reset"), 2)
        self.assertEqual(calls, 3)
        self.assertIn("failed after 3 attempt(s)", str(error))
        self.assertTrue(error.retryable)

    def test_reported_count_equals_invocations_across_budgets(self):
        for budget in (0, 1, 5):
            calls, error = self.failure(KustoThrottlingError("throttled"), budget)
            self.assertEqual(calls, budget + 1)
            self.assertIn(f"failed after {calls} attempt(s)", str(error))

    def test_permanent_and_transient_faults_are_distinct(self):
        self.assertFalse(is_retryable(TypeError("fixture")))
        self.assertFalse(is_retryable(KustoClientError("fixture")))
        self.assertTrue(is_retryable(KustoNetworkError("fixture")))
        self.assertTrue(is_retryable(KustoThrottlingError("fixture")))

    def test_mutating_management_command_is_never_retried(self):
        client = AdxClient(AdxConfig("https://fixture.example.test", "Events", max_retries=4),
                           credential=object(), policy=EventStorePolicy("operator", {"command", "delete"}))
        client._client = MagicMock()
        client._client.execute_mgmt.side_effect = KustoNetworkError("connection reset")
        with self.assertRaises(AdxQueryError):
            client.command(".drop table Records")
        self.assertEqual(client._client.execute_mgmt.call_count, 1)


if __name__ == "__main__":
    unittest.main()