import unittest
from concurrent.futures import ThreadPoolExecutor

from agentcraft_core import CallerContext, ExecutionBudget, ExecutionContext, FrameworkError, current_execution, reserve


class ContextTests(unittest.TestCase):
    def test_explicit_context_resets_and_cannot_widen(self):
        run = ExecutionContext.create(CallerContext("fixture"), limits={"data_calls": 2})
        with run.activate():
            reserve("data_calls")
            self.assertIs(current_execution(), run)
            child = run.child(limits={"data_calls": 1})
            with child.activate():
                reserve("data_calls")
                with self.assertRaises(FrameworkError):
                    reserve("data_calls")
            with self.assertRaises(FrameworkError):
                run.child(limits={"data_calls": 3})
            with self.assertRaises(FrameworkError):
                run.child(limits={"data_calls": 1}, timeout_seconds=1000)
        self.assertIsNone(current_execution())
        self.assertEqual(run.budget.snapshot()["reserved"], {"data_calls": 2})

    def test_atomic_reservations_and_unknowns_never_refund(self):
        budget = ExecutionBudget({"data_calls": 5})

        def attempt(_):
            try:
                budget.reserve("data_calls")
                return True
            except FrameworkError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(20))), 5)
        budget.mark_unknown("data_calls", 2)
        self.assertEqual(budget.snapshot()["unknown"]["data_calls"], 2)
        with self.assertRaises(FrameworkError):
            budget.reserve("data_calls")
        with self.assertRaises(FrameworkError):
            budget.reserve("not_granted")
        with self.assertRaises(FrameworkError):
            budget.mark_unknown("data_calls", 4)