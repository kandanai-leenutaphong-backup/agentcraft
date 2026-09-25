"""Offline replay: retained live receipts through the migrated reconcile/collect/closeout path, no network."""

import copy
import functools
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("evaluation_replay", Path(__file__).resolve().parents[1] / "deploy/experiment.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
from foundry_ops.evaluation import summarize_criteria  # noqa: E402  (path set by runner)

RECORDS = runner.DEPLOY / "records"
FINAL = RECORDS / "migration-e-final-h-v3"
FINAL_VERIFY = "20260922T194842941922Z-verify.json"
FINAL_VERIFY_SHA256 = "0c6ebc3f87a1d0ac243addb2a785d3d0d7936fa9de446f1ac4271587ce94339d"
V1 = RECORDS / "migration-e-v1"
V1_VERIFY = "20260922T181808468298Z-verify.json"
LEGACY_CLOSEOUT = "20260922T075756325970Z-closeout.json"


def load(path):
    return json.loads(Path(path).read_text())


def tree_digest(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(directory).rglob("*")) if path.is_file()}


def diff(expected, actual, path="$"):
    if isinstance(expected, dict) and isinstance(actual, dict):
        found = []
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                found.append(f"{path}.{key}")
            else:
                found += diff(expected[key], actual[key], f"{path}.{key}")
        return found
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [item for index, pair in enumerate(zip(expected, actual)) for item in diff(*pair, f"{path}[{index}]")]
    return [] if type(expected) is type(actual) and expected == actual else [path]


def model(value):
    return SimpleNamespace(model_dump=lambda **kwargs: copy.deepcopy(value))


def replay(series, verify_name):
    """Serve the receipt's own polls, definition readback and rows to `reconcile`; return (result, events, calls)."""
    receipt = load(series / verify_name)
    result = receipt["result"]
    polls = [event for event in receipt["events"] if event.get("operation") == "poll"]
    definition = next(event["definition"] for event in receipt["events"]
                      if event.get("operation") == "evaluation_definition_readback")
    runs = iter([SimpleNamespace(status=poll["status"], _request_id=poll["request_id"],
                                 model_dump=lambda status=poll["status"], **kwargs: dict(copy.deepcopy(result["aggregate"]), status=status))
                 for poll in polls])
    calls = []

    def retrieve_run(**kwargs):
        calls.append(("runs.retrieve", kwargs))
        return next(runs)

    def list_items(**kwargs):
        calls.append(("output_items.list", {key: kwargs[key] for key in ("eval_id", "run_id")}))
        page = SimpleNamespace(data=[model(item) for item in result["items"]], last_id=result["items"][-1]["id"])
        return SimpleNamespace(iter_pages=lambda: iter([page]))

    def retrieve_eval(identifier):
        calls.append(("evals.retrieve", {"eval_id": identifier}))
        return model(definition)

    client = SimpleNamespace(evals=SimpleNamespace(retrieve=retrieve_eval, runs=SimpleNamespace(
        retrieve=retrieve_run, output_items=SimpleNamespace(list=list_items))))
    decision = load(series / "approved-decision.json")
    events = []
    with patch.object(runner, "RECORDS", series), patch.object(runner, "DECISION", decision), \
         patch.object(runner, "PINS", decision["pins"]), patch.object(runner, "EVENTS", events), \
         patch.object(runner.ORACLE, "ROOT", series), \
         patch.object(runner, "wait_for_run", functools.partial(runner.wait_for_run, sleep=lambda seconds: None)):
        derived = runner.reconcile(client)
    return derived, events, calls


def without_utc(events):
    return [{key: value for key, value in event.items() if key != "utc"} for event in events]


class ReplayEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.before = tree_digest(RECORDS)
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)

    def tearDown(self):
        self.assertEqual(tree_digest(RECORDS), self.before, "retained records changed")

    def copy_series(self, source, name=None):
        target = Path(self.scratch.name) / (name or source.name)
        shutil.copytree(source, target)
        return target

    def assert_series_replays(self, source, verify_name):
        series = self.copy_series(source)
        receipt = load(series / verify_name)
        derived, events, calls = replay(series, verify_name)
        self.assertEqual(diff(receipt["result"], derived), [])
        self.assertEqual(without_utc(events), without_utc(receipt["events"]))
        return series, receipt, derived, calls

    def test_final_series_reproduces_retained_verify(self):
        self.assertEqual(runner.digest(FINAL / FINAL_VERIFY), FINAL_VERIFY_SHA256)
        series, receipt, derived, calls = self.assert_series_replays(FINAL, FINAL_VERIFY)
        run_id, evaluation = load(series / "run-id.json"), load(series / "evaluation.json")
        registered, dataset = load(series / "dataset-registered.json"), load(series / "dataset.json")
        definition = load(series / "definition-intent.json")["request"]
        run_request = load(series / "run-intent.json")["request"]
        identity = {"eval_id": run_id["eval_id"], "run_id": run_id["run_id"]}
        self.assertEqual(evaluation["id"], run_id["eval_id"])
        self.assertEqual(derived["identity"], run_id)
        self.assertTrue(all(call[1] == ({"eval_id": evaluation["id"]} if call[0] == "evals.retrieve" else identity)
                            for call in calls))
        self.assertEqual([name for name, _ in calls].count("runs.retrieve"), 5)
        self.assertEqual((derived["aggregate"]["id"], derived["aggregate"]["eval_id"]), (run_id["run_id"], evaluation["id"]))
        self.assertEqual((registered["id"], registered["version"]), (dataset["id"], dataset["version"]))
        self.assertEqual(derived["dataset"]["version"], registered["version"])
        self.assertEqual(run_request["data_source"]["source"]["id"], registered["id"])
        self.assertEqual(registered["version"], runner.validate_dataset_version("sha256-" + dataset["sha256"][:32]))
        self.assertEqual(len(derived["rows"]), 3)
        self.assertEqual([row["id"] for row in derived["rows"]], [item["id"] for item in receipt["result"]["items"]])
        self.assertEqual([row["criterion_passed"] for row in derived["rows"]], [True, True, True])
        self.assertEqual([row["oracle_passed"] for row in derived["rows"]], [True, True, True])
        self.assertEqual((derived["accepted"], derived["complete"], derived["settled"], derived["proof_passed"]), (True, True, True, 3))
        summary = summarize_criteria(derived["items"], criteria_names=[definition["testing_criteria"][0]["name"]])
        [aggregate] = derived["aggregate"]["per_testing_criteria_results"]
        self.assertEqual({key: summary[aggregate["testing_criteria"]][key] for key in ("passed", "failed", "errored")},
                         {key: aggregate[key] for key in ("passed", "failed", "errored")})

    def test_v1_series_reproduces_retained_verify(self):
        _, _, derived, _ = self.assert_series_replays(V1, V1_VERIFY)
        self.assertTrue(derived["accepted"])

    def test_mutated_copy_fails_replay(self):
        series = self.copy_series(FINAL)
        path = series / "definition-intent.json"
        intent = load(path)
        intent["request"]["testing_criteria"][0]["evaluator_version"] = "13"
        path.write_text(json.dumps(intent))
        derived, _, _ = replay(series, FINAL_VERIFY)
        differences = diff(load(series / FINAL_VERIFY)["result"], derived)
        self.assertIn("$.accepted", differences)
        self.assertFalse(derived["accepted"])
        receipt = load(FINAL / FINAL_VERIFY)
        receipt["result"]["rows"][0]["criterion_passed"] = False
        self.assertEqual(diff(receipt["result"], replay(self.copy_series(FINAL, "clean"), FINAL_VERIFY)[0]),
                         ["$.rows[0].criterion_passed"])

    def test_legacy_closeout_reproduces_retained_derivation(self):
        root = Path(self.scratch.name) / "legacy"
        root.mkdir()
        for path in RECORDS.glob("*.json"):
            shutil.copy2(path, root / path.name)
        retained = load(root / LEGACY_CLOSEOUT)["result"]
        dataset = load(root / "dataset.json")
        project = SimpleNamespace(datasets=SimpleNamespace(get=lambda **kwargs: SimpleNamespace(**kwargs)))
        with patch.object(runner, "RECORDS", root), patch.object(runner, "selection_check"), \
             patch.object(runner, "dataset_readback", return_value=copy.deepcopy(dataset)):
            derived = runner.settled_closeout(project)
        # Directory inventory has changed since closeout; only inventory-independent fields are replayable.
        fields = ("status", "stage", "next_transition", "objective", "hypothesis", "outcome", "pins", "image", "judge",
                  "dataset", "eval_id", "run_id", "request_id", "report_url", "rows", "aggregate", "verified_receipt")
        self.assertEqual(diff({key: retained[key] for key in fields}, {key: derived[key] for key in fields}), [])
        self.assertEqual(derived["status"], "complete")
        self.assertEqual([row["coherence"]["score"] for row in derived["rows"]], [4.0, 4.0, 2.0])


if __name__ == "__main__":
    unittest.main()
