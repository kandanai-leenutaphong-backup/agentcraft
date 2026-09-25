"""Offline replay: migrated deploy code recomputes retained live evidence and published metrics exactly.

Reads retained records only; no cloud client is constructed and nothing is written under deploy/evidence.
"""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
EVIDENCE = DEPLOY / "evidence"
sys.path.insert(0, str(DEPLOY))
spec = importlib.util.spec_from_file_location("iris_live_replay", DEPLOY / "live.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)

import campaign  # noqa: E402 - live.py puts foundry_ops on sys.path
import prepare  # noqa: E402
from foundry_ops.evaluation import check_canary_rows, check_counts  # noqa: E402

SERIES = "native-mapping-v2"
ROWS = 30
PUBLISHED = {"baseline_validation_accuracy": 0.9333333333333333, "baseline_validation_macro_f1": 0.9333333333333332,
             "native_baseline_macro_f1": 0.9665831244778613, "generated_macro_f1": 0.9326599326599326,
             "selected": "cand_opt_21aee306b2db4bebb7eb89a07d9c1f8d_0000",
             "demonstration": "cand_opt_21aee306b2db4bebb7eb89a07d9c1f8d_0001",
             "candidates": ["cand_opt_21aee306b2db4bebb7eb89a07d9c1f8d_000" + str(index) for index in range(3)],
             "first_job_candidates": ["cand_opt_89d941bff7214fa0b670b77249c583ad_0000"],
             "holdout_correct": {"baseline": 30, "chosen": 30}, "validation_macro_f1_gain": 0.033249791144528085}


def same(what, actual, expected):
    if actual != expected:
        raise ValueError("replay mismatch: " + what)


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def replay_rows(directory, prefix, expected_items, label_key, check_intent):
    """Recompute frozen metrics from per-row primary response files; cross-check the derived row records."""
    labels, predictions, rows = [], [], []
    for index, item in enumerate(expected_items):
        stem = directory / (prefix + "-row-" + str(index).zfill(3))
        response = json.loads(stem.with_suffix(".response.json").read_text())
        row = json.loads(stem.with_suffix(".json").read_text())
        check_intent(json.loads(stem.with_suffix(".intent.json").read_text()), index, item)
        same(f"{prefix} row {index} response", row["response"], response)
        same(f"{prefix} row {index} prediction", row["prediction"], response["text"])
        same(f"{prefix} row {index} label", (row["index"], row["label"]), (index, item[label_key]))
        labels.append(item[label_key])
        predictions.append(response["text"])
        rows.append(row)
    return prepare.EVALUATOR.score(labels, predictions), rows


def replay(directory):
    def read(name):
        return json.loads((directory / name).read_text())

    validation = json.loads((prepare.DATA / "candidate/validation.json").read_text())["items"]
    holdout = json.loads((prepare.DATA / "private/holdout.json").read_text())
    same("validation membership", len(validation), ROWS)
    out = {}

    def baseline_intent(intent, index, item):
        same(f"baseline intent {index}", (intent["index"], intent["query_sha256"]),
             (index, prepare.sha(item["query"].encode())))

    out["baseline"], rows = replay_rows(directory, "baseline-validation", validation, "ground_truth", baseline_intent)
    same("baseline row queries", [row["query"] for row in rows], [item["query"] for item in validation])
    same("baseline-validation.json metrics", out["baseline"], read("baseline-validation.json")["metrics"])
    with (directory / "baseline-validation.csv").open(newline="") as stream:
        same("baseline-validation.csv", [(row["label"], row["prediction"], row["response_id"]) for row in csv.DictReader(stream)],
             [(row["label"], row["prediction"], row["response"]["id"]) for row in rows])

    terminal = read(SERIES + "-optimizer-job-terminal.json")
    maximum = read(SERIES + "-optimizer-job-default-turn-intent.json")["request"]["inputs"]["options"]["max_candidates"]
    listing = campaign.completed_membership(terminal, maximum)
    retained_listing = read(SERIES + "-native-candidates.json")["data"]
    same("native candidate listing", list(live.candidate_parity(listing).items()),
         list(live.candidate_parity(retained_listing).items()))
    out["candidate_ids"] = [candidate.get("candidate_id") or candidate["id"] for candidate in listing]
    first_job = read("optimizer-job-terminal.json")
    first_listing = campaign.native_candidates(first_job, 1)
    out["first_job_candidate_ids"] = [candidate.get("candidate_id") or candidate["id"] for candidate in first_listing]
    same("first native candidate listing", live.candidate_parity(first_listing),
         live.candidate_parity(read("native-candidates.json")["data"]))
    try:
        campaign.completed_membership(first_job, maximum)
    except ValueError:
        out["first_job_baseline_only_refused"] = True

    comparison = read("candidate-validation-metrics.json")
    same("candidate-validation-metrics membership", [item["candidate_id"] for item in comparison["candidates"]], out["candidate_ids"])
    with (directory / "candidate-validation-metrics.csv").open(newline="") as stream:
        published_csv = {row["candidate_id"]: row for row in csv.DictReader(stream)}
    same("candidate CSV membership", sorted(published_csv), sorted(out["candidate_ids"]))
    scored = []
    for native, retained, published in zip(listing, retained_listing, comparison["candidates"], strict=True):
        candidate_id = native.get("candidate_id") or native["id"]

        def candidate_intent(intent, index, item, candidate_id=candidate_id):
            same(f"{candidate_id} intent {index}", (intent["candidate_id"], intent["index"]), (candidate_id, index))

        metrics, rows = replay_rows(directory, candidate_id + "-validation", validation, "ground_truth", candidate_intent)
        same(candidate_id + " row queries", [row["query"] for row in rows], [item["query"] for item in validation])
        same(candidate_id + " native identity", published["native"], retained)
        same(candidate_id + " comparison metrics", published["metrics"], metrics)
        same(candidate_id + "-validation.json metrics", read(candidate_id + "-validation.json")["metrics"], metrics)
        row = published_csv[candidate_id]
        same(candidate_id + " CSV metrics", {key: float(row[key]) for key in ("n", "accuracy", "macro_f1", "invalid_rate")},
             {key: float(metrics[key]) for key in ("n", "accuracy", "macro_f1", "invalid_rate")})
        same(candidate_id + " CSV evaluation identity", (row["eval_id"], row["eval_run_id"], float(row["native_avg_score"])),
             (native["eval_id"], native["eval_run_id"], float(native["avg_score"])))
        scored.append({"candidate_id": candidate_id, "metrics": metrics})
    out["candidates"] = {item["candidate_id"]: item["metrics"] for item in scored}

    out["selected"] = campaign.select_candidate(scored, ROWS)["candidate_id"]
    same("published selection", (comparison["selected"], read("selected-candidate.json")["candidate_id"]),
         (out["selected"], out["selected"]))
    same("selected metrics", read("selected-candidate.json")["metrics"], out["candidates"][out["selected"]])

    baseline_id = terminal["result"]["baseline"]
    demonstration = campaign.demonstration_candidate(
        {"complete_independent_validation": comparison["complete_independent_validation"], "candidates": scored}, baseline_id)
    out["demonstration"] = demonstration["candidate_id"]
    for name in ("demonstration-decision.json", "demonstration-result.json"):
        published = read(name)
        same(name + " candidate", published["candidate_id"], out["demonstration"])
        same(name + " validation", published["validation"], out["candidates"][out["demonstration"]])
        same(name + " baseline validation", published["baseline_validation"], out["candidates"][baseline_id])

    final = read("final-holdout-result.json")
    same("holdout selection", final["selected"], out["selected"])
    out["holdout"], out["holdout_correct"], holdout_rows = {}, {}, []
    for role in ("baseline", "chosen"):
        def holdout_intent(intent, index, item, role=role):
            same(f"holdout {role} intent {index}", (intent["role"], intent["index"], intent["row_id"]), (role, index, item["id"]))

        metrics, rows = replay_rows(directory, "holdout-" + role, holdout, "label", holdout_intent)
        same(f"holdout {role} row ids", [row["id"] for row in rows], [item["id"] for item in holdout])
        same(f"holdout {role} metrics", final["results"][role]["metrics"], metrics)
        out["holdout"][role] = metrics
        out["holdout_correct"][role] = sum(row["prediction"].strip() == row["label"] for row in rows)
        holdout_rows.extend((role, row["id"], row["label"], row["prediction"], row["response"]["id"]) for row in rows)
    with (directory / "final-holdout-rows.csv").open(newline="") as stream:
        same("final-holdout-rows.csv", [(row["role"], row["row_id"], row["label"], row["prediction"], row["response_id"])
                                        for row in csv.DictReader(stream)], holdout_rows)
    out["validation_macro_f1_gain"] = out["candidates"][out["selected"]]["macro_f1"] - out["baseline"]["macro_f1"]
    same("validation macro-F1 gain", final["validation_macro_f1_gain"], out["validation_macro_f1_gain"])

    out["canaries"] = {}
    for path in sorted(directory.rglob("evaluator-*canary-passed.json")):
        value = json.loads(path.read_text())
        check_counts(value["run"].get("result_counts"), total=3, passed=1, failed=2)
        check = check_canary_rows(value["rows"], eval_id=value["run"]["eval_id"], run_id=value["run"]["id"],
                                  criterion_name="classification_correctness", expected=live.CANARY_SCORES,
                                  match_field="sample.output_text" if "-mapped-" in path.name else "response")
        same(path.name + " canary", (check["passed"], value["passed"]), (True, True))
        out["canaries"][str(path.relative_to(directory))] = check["scores"]
    return out


class ReplayEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = tree_digest(EVIDENCE)
        cls.result = replay(EVIDENCE)

    @classmethod
    def tearDownClass(cls):
        if tree_digest(EVIDENCE) != cls.before:
            raise AssertionError("retained evidence changed during replay")

    def test_published_validation_metrics(self):
        baseline = self.result["baseline"]
        self.assertEqual((baseline["n"], baseline["accuracy"], baseline["macro_f1"], baseline["invalid_rate"]),
                         (ROWS, PUBLISHED["baseline_validation_accuracy"], PUBLISHED["baseline_validation_macro_f1"], 0.0))
        self.assertEqual(round(baseline["accuracy"], 6), 0.933333)
        candidates = self.result["candidates"]
        self.assertEqual(list(candidates), PUBLISHED["candidates"])
        self.assertEqual([candidates[name]["macro_f1"] for name in PUBLISHED["candidates"]],
                         [PUBLISHED["native_baseline_macro_f1"], PUBLISHED["generated_macro_f1"], PUBLISHED["generated_macro_f1"]])
        self.assertEqual([candidates[name]["invalid_rate"] for name in PUBLISHED["candidates"]], [0.0, 0.0, 0.0])
        self.assertEqual([candidates[name]["accuracy"] for name in PUBLISHED["candidates"]], [29 / 30, 28 / 30, 28 / 30])

    def test_native_listing_and_selection(self):
        self.assertEqual(self.result["candidate_ids"], PUBLISHED["candidates"])
        self.assertEqual(self.result["first_job_candidate_ids"], PUBLISHED["first_job_candidates"])
        self.assertTrue(self.result["first_job_baseline_only_refused"])
        self.assertEqual(self.result["selected"], PUBLISHED["selected"])
        self.assertEqual(self.result["demonstration"], PUBLISHED["demonstration"])

    def test_holdout_and_gain(self):
        self.assertEqual(self.result["holdout_correct"], PUBLISHED["holdout_correct"])
        for metrics in self.result["holdout"].values():
            self.assertEqual((metrics["n"], metrics["accuracy"], metrics["macro_f1"], metrics["invalid_rate"]), (ROWS, 1.0, 1.0, 0.0))
        self.assertEqual(self.result["validation_macro_f1_gain"], PUBLISHED["validation_macro_f1_gain"])

    def test_canaries_one_zero_zero(self):
        self.assertGreaterEqual(len(self.result["canaries"]), 2)
        for scores in self.result["canaries"].values():
            self.assertEqual(scores, {" Iris-setosa ": 1.0, "Iris-versicolor": 0.0, "not-a-label": 0.0})

    def test_mutated_copy_fails(self):
        def rewrite(path, change):
            path.write_text(json.dumps(change(json.loads(path.read_text()))))

        def consistent_candidate_row(copy):
            stem = copy / (PUBLISHED["candidates"][1] + "-validation-row-000")
            rewrite(stem.with_suffix(".response.json"), lambda value: dict(value, text="not-a-label"))
            response = json.loads(stem.with_suffix(".response.json").read_text())
            rewrite(stem.with_suffix(".json"), lambda value: dict(value, response=response, prediction=response["text"]))

        def baseline_response_only(copy):
            rewrite(copy / "baseline-validation-row-007.response.json", lambda value: dict(value, text=" not-a-label "))

        for mutate, reason in ((consistent_candidate_row, "comparison metrics"), (baseline_response_only, "row 7 response")):
            with self.subTest(mutation=mutate.__name__), tempfile.TemporaryDirectory() as directory:
                copy = Path(directory)
                for path in EVIDENCE.iterdir():
                    if path.is_file() and path.suffix in (".json", ".csv"):
                        shutil.copyfile(path, copy / path.name)
                self.assertEqual(replay(copy)["selected"], PUBLISHED["selected"])
                mutate(copy)
                with self.assertRaisesRegex(ValueError, "replay mismatch: .*" + reason):
                    replay(copy)


if __name__ == "__main__":
    unittest.main()
