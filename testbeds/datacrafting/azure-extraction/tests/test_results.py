from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "azure-extraction"))
sys.path.insert(0, str(ROOT / "deploy"))

from azure_extraction.contracts import Refusal, documents_from_manifest
from verify_results import ACCEPTED_RECEIPTS, normalize, phrase_present, source_observations, verify_all, verify_receipt


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.documents = documents_from_manifest(json.loads((ROOT / "source_data/manifest.json").read_text()))
        self.receipt = ROOT / "content-understanding/results/murray" / ACCEPTED_RECEIPTS["murray"] / "receipt.json"

    def test_frozen_cu_receipts_and_source_facts(self):
        result = verify_all(ROOT)
        self.assertEqual(result["successful_method_document_pairs"], 2)
        self.assertTrue(result["frozen_artifact_hashes_verified"])
        self.assertEqual(sum(item["pages"] for item in result["results"]), 13)
        self.assertEqual(sum(item["source_facts"]["narrative"]["passed"] for item in result["results"]), 32)
        self.assertEqual(sum(item["source_facts"]["table_relationships"]["passed"] for item in result["results"]), 6)
        self.assertEqual({item["method"] for item in result["results"]}, {"content-understanding"})

    def test_retired_receipt_method_refuses_before_read(self):
        with self.assertRaises(Refusal):
            verify_receipt(Path("absent"), self.documents["murray"], "document-intelligence-layout")

    def test_receipt_provider_and_source_identity_refuse(self):
        for field, value in (("provider", {"api_version": "2024-11-30", "model_id": "prebuilt-layout"}),
                             ("provider", {"api_version": "2025-11-01", "model_id": "prebuilt-documentSearch"}),
                             ("method", "document-intelligence-read"), ("execution", "local")):
            with self.subTest(field=field, value=value), TemporaryDirectory() as temporary:
                receipt = json.loads(self.receipt.read_text())
                receipt[field] = value
                path = Path(temporary) / "receipt.json"
                path.write_text(json.dumps(receipt))
                with self.assertRaises(Refusal):
                    verify_receipt(path, self.documents["murray"], "content-understanding")

    def test_native_api_and_analyzer_identity_refuse(self):
        for field, value in (("apiVersion", "2024-11-30"), ("analyzerId", "prebuilt-documentSearch")):
            with self.subTest(field=field), TemporaryDirectory() as temporary:
                directory = Path(temporary) / "result"
                shutil.copytree(self.receipt.parent, directory)
                native = json.loads((directory / "native.json").read_text())
                native["result"][field] = value
                (directory / "native.json").write_text(json.dumps(native))
                with self.assertRaises(Refusal):
                    verify_receipt(directory / "receipt.json", self.documents["murray"], "content-understanding")

    def test_artifact_escape_and_symlink_escape_refuse(self):
        for mode in ("traversal", "symlink"):
            with self.subTest(mode=mode), TemporaryDirectory() as temporary:
                directory = Path(temporary) / "result"
                shutil.copytree(self.receipt.parent, directory)
                outside = Path(temporary) / "outside.txt"
                outside.write_text((directory / "content.txt").read_text())
                receipt = json.loads((directory / "receipt.json").read_text())
                if mode == "traversal":
                    receipt["outputs"]["text"] = "../outside.txt"
                    (directory / "receipt.json").write_text(json.dumps(receipt))
                else:
                    (directory / "content.txt").unlink()
                    (directory / "content.txt").symlink_to(outside)
                with self.assertRaises(Refusal):
                    verify_receipt(directory / "receipt.json", self.documents["murray"], "content-understanding")

    def test_markup_decimal_and_whole_token_normalization(self):
        self.assertEqual(normalize("<!-- hidden --><td>At 1334.29 hrs</td><td>unit 4 &amp; 3</td>"), "at 1334.29 hrs unit 4 3")
        self.assertTrue(phrase_present(normalize("Jeeralang units A2, A3 and B3"), "Jeeralang units A2 A3 and B3"))
        self.assertFalse(phrase_present("1597 megawatts", "597 megawatts"))
        self.assertFalse(phrase_present("at 1334.32 hrs", "at 1334.29 hrs"))

    def test_row_span_and_missing_facts_refuse(self):
        native = {"result": {"contents": [{"tables": [{"cells": [
            {"rowIndex": 0, "columnIndex": 0, "rowSpan": 2, "content": "Market information"},
            {"rowIndex": 0, "columnIndex": 1, "content": "MN 133160 at 1042 hrs"},
            {"rowIndex": 1, "columnIndex": 1, "content": "MN 133163 at 1128 hrs"},
            {"rowIndex": 2, "columnIndex": 1, "content": "910 MVA"},
        ]}]}]}}
        probes = [{"id": "time", "category": "narrative", "phrases": ["1128 hrs"]}]
        relationships = [{"id": "notices", "label": "Market information", "phrases": ["MN 133160", "1128 hrs"]}]
        self.assertEqual(source_observations(native, "1128 hrs", probes, relationships)["table_relationships"]["passed"], 1)
        outside_row = deepcopy(relationships)
        outside_row[0]["phrases"].append("910 MVA")
        for text, rows in (("missing", relationships), ("1128 hrs", outside_row)):
            with self.assertRaises(Refusal):
                source_observations(native, text, probes, rows)
        with self.assertRaises(Refusal):
            source_observations({"result": {"contents": [{}]}}, "1128 hrs", probes, relationships)


if __name__ == "__main__":
    unittest.main()