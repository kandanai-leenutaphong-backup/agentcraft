import unittest

from foundry_ops.errors import RefusedError, VerificationError
from foundry_ops.evals import (DATASET_VERSION_MAX, PartialRowsError, check_counts, check_criteria, check_criterion,
                               check_membership, check_row, collect_rows, target_text, validate_dataset_version,
                               wait_for_run)

from fakes import Clock, Page, ResponseModel, eval_client
from types import SimpleNamespace


def row(identifier, query, **changes):
    value = {"id": identifier, "eval_id": "e", "run_id": "r", "status": "completed", "error": None,
             "datasource_item": {"query": query}, "sample": {"output_text": "A"}}
    value.update(changes)
    return ResponseModel(value)


CRITERION = {"name": "Coherence", "metric": "coherence", "type": "azure_ai_evaluator", "status": "completed",
             "score": 4, "passed": True, "evaluator_name": "builtin.coherence", "evaluator_version": "3"}


class DatasetVersionTests(unittest.TestCase):
    def test_fifty_character_limit(self):
        self.assertEqual(validate_dataset_version("sha256-" + "a" * 32), "sha256-" + "a" * 32)
        self.assertEqual(len(validate_dataset_version("v" * DATASET_VERSION_MAX)), 50)
        for bad in ("v" * 51, "sha256-" + "a" * 64, "", None):
            with self.assertRaises(RefusedError):
                validate_dataset_version(bad)


class CollectTests(unittest.TestCase):
    def test_rows_across_pages(self):
        client = eval_client([Page([row("1", "a"), row("2", "b")], "2"), Page([row("3", "c")], "3")])
        rows = collect_rows(client, eval_id="e", run_id="r", expected_count=3)
        self.assertEqual([item["id"] for item in rows], ["1", "2", "3"])

    def test_duplicate_surplus_and_page_bound_keep_partial(self):
        cases = {"row_identity": [Page([row("1", "a")]), Page([row("1", "a")])],
                 "row_surplus": [Page([row("1", "a"), row("2", "b")])],
                 "evaluation_pages": [Page([row(str(i), str(i))], str(i)) for i in range(3)]}
        for code, pages in cases.items():
            with self.assertRaises(PartialRowsError) as caught:
                collect_rows(eval_client(pages), eval_id="e", run_id="r", expected_count=1 if code == "row_surplus" else 5,
                             max_pages=2)
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(caught.exception.partial["complete"])
            self.assertTrue(caught.exception.partial["rows"])

    def test_wait_for_run(self):
        clock = Clock()
        runs = [SimpleNamespace(status="queued"), SimpleNamespace(status="in_progress"), SimpleNamespace(status="completed")]
        result = wait_for_run(eval_client(runs=runs), eval_id="e", run_id="r", sleep=clock.sleep, clock=clock)
        self.assertEqual((result.settled, result.attempts), (True, 3))
        stuck = wait_for_run(eval_client(runs=[SimpleNamespace(status="queued")] * 3), eval_id="e", run_id="r",
                             attempts=3, sleep=clock.sleep, clock=clock)
        self.assertFalse(stuck.settled)


class CheckTests(unittest.TestCase):
    def test_counts(self):
        counts = {"total": 3, "passed": 1, "failed": 2, "errored": 0, "skipped": 0}
        self.assertEqual(check_counts(counts, total=3, passed=1), counts)
        for bad in (dict(counts, errored=1, failed=1), dict(counts, total=4), dict(counts, passed="1")):
            with self.assertRaises(VerificationError):
                check_counts(bad, total=3)

    def test_criteria_readback(self):
        expected = [{"type": "azure_ai_evaluator", "name": "c", "evaluator_name": "x", "evaluator_version": "1"}]
        check_criteria([dict(expected[0], id="svc-1", labels=None, model=None)], expected)
        for actual in ([], [dict(expected[0], evaluator_version="2")], [dict(expected[0], labels=["x"])],
                       [dict(expected[0], threshold=0.5)], [dict(expected[0], id="")]):
            with self.assertRaises(VerificationError):
                check_criteria(actual, expected)

    def test_row_and_membership(self):
        rows = [row("1", "a"), row("2", "b")]
        for item in rows:
            check_row(item, eval_id="e", run_id="r")
        check_membership(rows, expected={"a", "b"})
        for bad in (row("1", "a", status="failed"), row("1", "a", run_id="other"), row("", "a")):
            with self.assertRaises(VerificationError):
                check_row(bad, eval_id="e", run_id="r")
        for bad in ([rows[0]], [rows[0], row("3", "a")], [rows[0], row("1", "b")], [rows[0], row("2", "z")]):
            with self.assertRaises(VerificationError):
                check_membership(bad, expected={"a", "b"})

    def test_criterion(self):
        self.assertTrue(check_criterion(CRITERION, name="Coherence", metric="coherence",
                                        evaluator_name="builtin.coherence", evaluator_version="3"))
        for change in ({"metric": "other"}, {"status": "failed"}, {"error": "x"}, {"score": float("nan")},
                       {"score": True}, {"score": "4"}, {"passed": None}, {"evaluator_version": "4"}):
            with self.assertRaises(VerificationError):
                check_criterion(dict(CRITERION, **change), name="Coherence", metric="coherence",
                                evaluator_name="builtin.coherence", evaluator_version="3")


class TargetTextTests(unittest.TestCase):
    def test_agreeing_representations(self):
        blocks = '[{"type": "output_text", "text": "A"}]'
        value = {"datasource_item": {"query": "q", "sample.output_text": "A"},
                 "sample": {"output_text": "A", "output": [{"role": "user", "content": "q"},
                                                           {"role": "assistant", "content": blocks}]}}
        self.assertEqual(target_text(value), "A")
        self.assertEqual(target_text({"datasource_item": {"response": "B"}, "sample": None}), "B")
        self.assertEqual(target_text({"sample": {"output": [{"role": "assistant", "content": "plain"}]}}), "plain")

    def test_conflict_missing_and_malformed_refused(self):
        for value in ({"sample": {"output_text": "A"}, "datasource_item": {"response": "B"}},
                      {"datasource_item": {}}, {"sample": "text"},
                      {"sample": {"output": [{"role": "assistant", "content": [{"type": "image"}]}]}},
                      {"datasource_item": {"sample": {"other": 1}}}):
            with self.assertRaises(VerificationError):
                target_text(value)


if __name__ == "__main__":
    unittest.main()
