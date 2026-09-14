import json
import tempfile
import unittest
from pathlib import Path

from data_collection import ScrapeOptions, ScrapeResult
from data_collection.storage import save_result, verify_result


class StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.result = ScrapeResult(url="https://example.test/page", ok=True, status=200,
                                   html='<meta charset="windows-1252"><p>caf\u00e9</p>')

    def test_html_metadata_and_provenance_are_read_back(self):
        directory = save_result(self.result, self.root, ScrapeOptions())
        self.assertEqual((directory / "page.html").read_text(encoding="utf-8-sig"), self.result.html)
        self.assertTrue((directory / "page.html").read_bytes().startswith(b"\xef\xbb\xbf"))
        metadata = json.loads((directory / "result.json").read_text())
        self.assertNotIn("html", metadata)
        self.assertEqual(metadata["artifacts"]["html"], "page.html")
        self.assertEqual(verify_result(directory)["checked"], 2)
        self.assertTrue(verify_result(directory)["ok"])

    def test_repeat_runs_never_overwrite_previous_acquisition(self):
        first = save_result(self.result, self.root, ScrapeOptions())
        second = save_result(self.result, self.root, ScrapeOptions())
        self.assertNotEqual(first, second)
        self.assertTrue(verify_result(first)["ok"])
        self.assertTrue(verify_result(second)["ok"])

    def test_modified_html_and_metadata_are_detected(self):
        for filename in ("page.html", "result.json"):
            with self.subTest(filename=filename):
                directory = save_result(self.result, self.root, ScrapeOptions())
                with (directory / filename).open("ab") as stream:
                    stream.write(b"modified")
                self.assertFalse(verify_result(directory)["ok"])

    def test_failed_acquisition_has_receipt_but_no_success_html(self):
        self.result.ok = False
        self.result.error_code = "access_denied"
        directory = save_result(self.result, self.root, ScrapeOptions())
        self.assertFalse((directory / "page.html").exists())
        self.assertTrue(verify_result(directory)["ok"])
        self.assertFalse(verify_result(directory)["acquisition_ok"])

    def test_missing_manifest_and_escaping_artifacts_refuse(self):
        self.assertFalse(verify_result(self.root)["ok"])
        directory = save_result(self.result, self.root, ScrapeOptions())
        manifest = directory / "manifest.json"
        payload = json.loads(manifest.read_text())
        payload["entries"][0]["artefact"] = "../outside"
        manifest.write_text(json.dumps(payload))
        self.assertFalse(verify_result(directory)["ok"])

    def test_source_and_screenshot_are_catalogued(self):
        self.result.source_html = "<div></div>"
        self.result.screenshot = b"fixture PNG bytes"
        directory = save_result(self.result, self.root, ScrapeOptions(screenshot=True))
        self.assertEqual(verify_result(directory)["checked"], 4)
        self.assertTrue(verify_result(directory)["ok"])


if __name__ == "__main__":
    unittest.main()