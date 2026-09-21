import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

import datasets
import explore_data
from explore_data import csv_survey, profile_csv, selected_overlap, semantic_observations


class Response(io.BytesIO):
    status = 200
    headers = {"Content-Type": "text/csv"}

    def geturl(self):
        return "https://example.org/test.csv"


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.entry = {"path": "test.csv", "url": "https://example.org/test.csv", "bytes": 8}

    def test_download_skip_and_tamper_refusal(self):
        with patch.object(datasets, "open_public", return_value=Response(b"col\none\n")) as opener:
            receipt = datasets.acquire(self.entry, self.root)
            self.assertEqual(datasets.acquire(self.entry, self.root), receipt)
            opener.assert_called_once()
        (self.root / "test.csv").write_bytes(b"col\ntwo\n")
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            datasets.acquire(self.entry, self.root)

    def test_truncated_download_is_not_published(self):
        with patch.object(datasets, "open_public", return_value=Response(b"short")):
            with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
                datasets.acquire(self.entry, self.root)
        self.assertFalse((self.root / "test.csv").exists())
        self.assertFalse((self.root / "test.csv.receipt.json").exists())

    def test_checksum_and_unreceipted_file_refuse(self):
        entry = {**self.entry, "publisher_md5": "0" * 32}
        with patch.object(datasets, "open_public", return_value=Response(b"col\none\n")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                datasets.acquire(entry, self.root)
        (self.root / "test.csv").write_bytes(b"col\none\n")
        with self.assertRaisesRegex(ValueError, "no receipt"):
            datasets.acquire(self.entry, self.root)

    def test_path_escape_and_symlink_refuse(self):
        with self.assertRaises(ValueError):
            datasets.contained(self.root, "../outside")
        (self.root / "link").symlink_to(self.root / "target")
        with self.assertRaises(ValueError):
            datasets.contained(self.root, "link")

    def test_extract_exact_member_and_verify_existing(self):
        folder = self.root / "hikari-2021"
        folder.mkdir()
        with zipfile.ZipFile(folder / (datasets.CSV_NAME + ".zip"), "w") as archive:
            archive.writestr(datasets.CSV_NAME, "col\none\n")
            archive.writestr("../untrusted.txt", "not extracted")
        receipt = datasets.extract_hikari(self.root)
        self.assertEqual(datasets.extract_hikari(self.root, receipt), receipt)
        self.assertFalse((self.root / "untrusted.txt").exists())
        (folder / datasets.CSV_NAME).write_text("col\ntwo\n")
        with self.assertRaises(ValueError):
            datasets.extract_hikari(self.root)

    def test_manifest_conflict_refuses(self):
        path = self.root / "lock.json"
        datasets.save_new(path, {"revision": 1})
        datasets.save_new(path, {"revision": 1})
        with self.assertRaisesRegex(ValueError, "overwrite"):
            datasets.save_new(path, {"revision": 2})
        self.assertEqual(json.loads(path.read_text()), {"revision": 1})

    def test_html_is_not_published_as_csv(self):
        payload = b"<html/>"
        with patch.object(datasets, "open_public", return_value=Response(payload)):
            with self.assertRaisesRegex(ValueError, "HTML returned"):
                datasets.acquire({**self.entry, "bytes": len(payload)}, self.root)
        self.assertFalse((self.root / "test.csv").exists())

    def test_fresh_download_preserves_original_lock(self):
        lock = self.root / "datasets.lock.json"
        plan = {"files": [self.entry], "derived": {"path": "hikari-2021/data.csv"}}
        datasets.save_new(lock, plan)
        with patch.object(datasets, "LOCK", lock), patch.object(datasets, "DATA", self.root), \
                patch.object(datasets, "acquire", return_value={**self.entry, "retrieved_at": "new"}), \
                patch.object(datasets, "extract_hikari", return_value=plan["derived"]), \
                patch.object(datasets, "verify"):
            datasets.download()
        self.assertEqual(json.loads(lock.read_text()), plan)

    def test_development_sample_profile_is_repeatable_and_bounded(self):
        path = self.root / "probe.csv"
        path.write_text('timestamp,label,value\n1,benign,\n1,benign,\n2,attack,"a,b"\n3,unseen,last\n')
        result = profile_csv(path, 3)
        self.assertEqual(result, profile_csv(path, 3))
        self.assertEqual(result["sample_rows"], 3)
        self.assertEqual(result["exact_duplicate_sample_rows"], 1)
        self.assertEqual(result["missing_sample_values"], {"value": 2})
        self.assertEqual(result["label_candidates"]["label"]["top_values"], [("benign", 2), ("attack", 1)])
        self.assertEqual(result["time_column_candidates"], ["timestamp"])

    def test_profile_reports_malformed_rows_and_refuses_duplicate_headers(self):
        path = self.root / "probe.csv"
        path.write_text("label,value\nattack\n")
        self.assertEqual(profile_csv(path, 2)["malformed_sample_rows"], 1)
        path.write_text("label,label\nattack,benign\n")
        with self.assertRaises(ValueError):
            profile_csv(path, 2)

    def test_explicit_label_column_closes_uwf_probe_gap(self):
        path = self.root / "uwf.csv"
        path.write_text("ts,mitre_attack_tactics\n1,Discovery\n2,Reconnaissance\n")
        self.assertEqual(profile_csv(path, 2)["label_candidates"], {})
        profile = profile_csv(path, 2, ["mitre_attack_tactics"])
        self.assertEqual(profile["label_candidates"]["mitre_attack_tactics"]["top_values"],
                         [("Discovery", 1), ("Reconnaissance", 1)])

    def test_reservoir_exposes_nonprefix_labels_and_retains_membership(self):
        path = self.root / "ordered.csv"
        path.write_text("label,value\n" + "benign,0\n" * 50 + "attack,1\n" * 50)
        prefix = profile_csv(path, 20)
        sampled = profile_csv(path, 20, sampling="reservoir", seed=7)
        self.assertEqual(prefix["label_candidates"]["label"]["distinct_sample_values"], 1)
        self.assertEqual(sampled["label_candidates"]["label"]["distinct_sample_values"], 2)
        self.assertEqual(sampled, profile_csv(path, 20, sampling="reservoir", seed=7))
        self.assertEqual(sampled["population_rows"], 100)
        self.assertEqual(len(set(sampled["development_row_ordinals"])), 20)
        self.assertGreater(max(sampled["development_row_ordinals"]), 50)
        with self.assertRaises(ValueError):
            profile_csv(path, 0, sampling="reservoir")
        with self.assertRaises(ValueError):
            profile_csv(path, 20, sampling="unknown")

    def test_population_aggregates_and_sample_membership_are_separate(self):
        path = self.root / "ordered.csv"
        path.write_text("label,value\n" + "benign,0\n" * 50 + "attack,1\n" * 50)
        columns, prefix, sample, population = csv_survey(path, 20, 7, [])
        self.assertEqual(population, {"rows": 100, "malformed_rows": 0,
                                     "label_counts": {"label": {"attack": 50, "benign": 50}}})
        self.assertEqual(len(sample), 20)
        self.assertEqual(len(prefix), 20)
        self.assertEqual(columns, ["label", "value"])

    def test_exact_overlap_retains_index_and_labels_and_never_coerces(self):
        samples = [{"path": "left", "columns": ["index", "label", "value"], "labels": ["label"],
                    "rows": [(1, ["0", "attack", "1"]), (2, ["0", "attack", "1"]), (3, ["1", "attack", "1"])]},
                   {"path": "right", "columns": ["value", "label", "index"], "labels": ["label"],
                    "rows": [(1, ["1", "attack", "0"]), (2, ["1", "benign", "0"]), (3, [1, "attack", "0"])]}]
        result = selected_overlap(samples)
        self.assertEqual(result["per_file"]["left"]["duplicate_excess_rows"], 1)
        self.assertEqual(result["pairs"][0]["shared_distinct_rows"], 1)
        self.assertEqual(result["pairs"][0]["right_occurrences"], 1)
        self.assertEqual(selected_overlap(samples, True)["pairs"][0]["right_occurrences"], 2)

    def test_time_hypotheses_do_not_promote_units_to_facts(self):
        result = semantic_observations(["ts", "label", "id.orig_h"],
                                      [(1, ["1640995200", "attack", "host"]),
                                       (2, ["nan", "benign", "host"])], [])
        timestamp = result["time_checks"]["ts"]
        self.assertEqual(timestamp["finite_numeric"], 1)
        self.assertEqual(timestamp["epoch_hypotheses"]["seconds"]["min_utc"], "2022-01-01T00:00:00+00:00")
        self.assertTrue(timestamp["semantics"].startswith("unknown"))
        self.assertEqual(result["entity_checks"]["id.orig_h"]["distinct_sample_values"], 1)

    def test_calendar_offset_and_naive_split_leakage_remain_diagnostic(self):
        result = semantic_observations(["ts", "datetime", "src_ip_zeek", "dest_ip", "flow_duration"],
                                      [(1, ["1640995200", "2021-12-31 18:00:00", "source", "destination", "12.5"])], [])
        calendar = result["time_checks"]["datetime"]["iso8601"]
        self.assertEqual(calendar["timezone_naive"], 1)
        self.assertEqual(calendar["datetime_minus_ts_seconds"]["min"], -21600)
        self.assertEqual(result["time_checks"]["flow_duration"]["finite_numeric"], 1)
        self.assertIn("src_ip_zeek", result["entity_checks"])
        self.assertIn("dest_ip", result["entity_checks"])
        overlap = selected_overlap([{"path": "source", "columns": ["label"], "labels": ["label"],
                                     "rows": [(1, ["attack"]), (5, ["attack"]), (6, ["benign"])]}])
        self.assertEqual(overlap["diagnostic_row_split"]["distinct_groups_in_both"], 1)

    def test_parquet_survey_repeat_readback_and_refusals(self):
        import pyarrow
        import pyarrow.parquet as parquet

        csv_path = self.root / "input.csv"
        csv_path.write_text("ts,label\n1640995200,benign\n1640995201,attack\n" * 1)
        parquet_path = self.root / "input.parquet"
        parquet.write_table(pyarrow.table({"ts": [1640995200, 1640995201, 1640995202],
                                          "label": ["benign", "attack", "attack"]}), parquet_path, row_group_size=2)
        lock = self.root / "lock.json"
        datasets.save_new(lock, {"derived": {"path": csv_path.name, **datasets.fingerprint(csv_path)},
                                 "files": [{"path": parquet_path.name, **datasets.fingerprint(parquet_path)}]})
        constitution = self.root / "constitution/constitution.yaml"
        constitution.parent.mkdir()
        constitution.write_text("revision: 7\nstatus: exploring\n")
        args = argparse.Namespace(output=self.root / "results/first.json", constitution_sha256=datasets.fingerprint(constitution)["sha256"],
                                  rows=2, batch_size=2, seconds=30, seed=7, label_column=[], file=[], compare=None)
        with patch.object(explore_data, "MISSION", self.root), patch.object(explore_data, "DATA", self.root), \
                patch.object(explore_data, "LOCK", lock), redirect_stdout(io.StringIO()):
            self.assertEqual(explore_data.survey(args), 0)
            first = explore_data.read_evidence(args.output)
            self.assertEqual(first["observations"]["profiles"][1]["population"]["label_counts"], {"label": {"attack": 2, "benign": 1}})
            self.assertEqual(first["observations"]["profiles"][1]["population"]["row_groups"], 2)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                explore_data.survey(args)
            args.compare = args.output
            args.output = self.root / "results/repeat.json"
            self.assertEqual(explore_data.survey(args), 0)
            self.assertTrue(explore_data.read_evidence(args.output)["repeat_matches"])
            args.output = self.root / "results/failed.json"
            args.seed = 9
            self.assertEqual(explore_data.survey(args), 2)
            self.assertEqual(json.loads(args.output.read_text())["error"]["message"], "Repeated observations differ")
            args.output = self.root / "results/wrong-pin.json"
            args.constitution_sha256 = "0" * 64
            with self.assertRaisesRegex(ValueError, "matching"):
                explore_data.survey(args)
            self.assertFalse(args.output.exists())
            with self.assertRaises(ValueError):
                explore_data.evidence_path(self.root / "outside.json")
            tampered = json.loads(args.compare.read_text())
            tampered["observations"]["seed"] = 99
            args.compare.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                explore_data.read_evidence(args.compare)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if not args.evidence:
        unittest.main(argv=[__file__], verbosity=2)
    else:
        output = explore_data.evidence_path(args.evidence)
        if output.exists():
            raise ValueError("Refusing to overwrite test evidence")
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        captured = io.StringIO()
        with redirect_stdout(captured):
            result = unittest.TextTestRunner(stream=captured, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DatasetTests))
        evidence = {"stage": "data-understanding", "evidence_class": "exploratory", "started_at": started_at,
                    "elapsed_seconds": time.monotonic() - started, "tests_run": result.testsRun,
                    "failures": len(result.failures), "errors": len(result.errors), "successful": result.wasSuccessful(),
                    "stdout_and_runner": captured.getvalue(),
                    "source_pins": {name: datasets.fingerprint(Path(__file__).with_name(name))["sha256"]
                                    for name in ("test_datasets.py", "explore_data.py", "datasets.sh", "datasets.py")},
                    "constitution_sha256": datasets.fingerprint(explore_data.MISSION / "constitution/constitution.yaml")["sha256"]}
        datasets.save_new(output, evidence)
        assert json.loads(output.read_text()) == evidence
        print(captured.getvalue())
        print(json.dumps({"evidence": str(output), "sha256": datasets.fingerprint(output)["sha256"]}))
        raise SystemExit(0 if result.wasSuccessful() else 1)