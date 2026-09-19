import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import datasets
from explore_data import profile_csv


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


if __name__ == "__main__":
    unittest.main()