import importlib.util
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import tempfile
import unittest
from urllib.parse import urlsplit


SPEC = importlib.util.spec_from_file_location("report_summary", Path(__file__).parents[1] / "report_summary.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ReportSummaryTests(unittest.TestCase):
    def receipt(self, root, owner, value):
        path = root / report.RECEIPTS[owner]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_golden_counts_unknown_and_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.receipt(root, "overseer", {"timing_and_calls": {
                "observed_model_requests": 1, "time_to_verified_acceptance_seconds": 14.294516274996568},
                "credential": "PRIVATE_SENTINEL", "reasoning": "PRIVATE_SENTINEL"})
            self.receipt(root, "smoke", {"stats": {"expected": 2, "unexpected": 0}})
            self.receipt(root, "profile", {"browser": {"checks": 58}, "checks": [
                {"result": "84 passed; one existing Starlette deprecation warning"},
                {"command": "npm test", "result": "29 passed"}]})
            summary = report.build_summary(root)
            metrics = {row["label"]: row["value"] for row in summary["metrics"]}
            self.assertEqual(metrics["Overseer observed model requests"], 1)
            self.assertEqual(metrics["Overseer acceptance time"], 14.294516274996568)
            self.assertEqual(metrics["Dashboard smoke passed"], 2)
            self.assertEqual(metrics["Dashboard smoke failed"], 0)
            self.assertEqual(metrics["Profile browser checks"], 58)
            self.assertIsNone(metrics["Prompt observed model requests"])
            self.assertEqual(summary["evidence"][0]["state"], "unknown: missing receipt")
            self.assertNotIn("PRIVATE_SENTINEL", json.dumps(summary))
            self.assertIn("14.295", report.render_html(summary))
            self.assertEqual([row["result"] for row in summary["recorded_checks"][-2:]], ["84 passed", "29 passed"])
            self.assertEqual([row["result"] for row in summary["recorded_checks"][:3]], ["152 passed", "4 passed", "7 passed"])
            self.receipt(root, "profile", {"checks": []})
            self.assertEqual(report.build_summary(root)["recorded_checks"][-2]["result"], "unknown")

    def test_html_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = report.build_summary(Path(directory))
            summary["observations"][0]["detail"] = '<script>alert("x")</script>&'
            rendered = report.render_html(summary)
            self.assertNotIn("<script>", rendered)
            self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;&amp;", rendered)

    def test_publish_identical_or_refuse_without_clobber(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = report.publish(root)
            self.assertEqual(paths, ["optimization_framework/reports/implementation-summary.json",
                                     "optimization_framework/reports/implementation-report.html"])
            self.assertFalse((root / "reports").exists())
            before = {name: (root / name).read_bytes() for name in paths}
            self.assertEqual(report.publish(root), paths)
            self.receipt(root, "smoke", {"stats": {"expected": 2}})
            with self.assertRaises(FileExistsError):
                report.publish(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in paths})

    def test_framework_receipts_and_relative_html_links(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.targets = []

            def handle_starttag(self, tag, attrs):
                self.targets.extend(value for name, value in attrs if name in ("href", "src"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for owner, relative in report.RECEIPTS.items():
                self.assertEqual(Path(relative).parent, Path("optimization_framework/reports"))
                self.receipt(root, owner, {})
            summary = report.build_summary(root)
            self.assertTrue(all(row["state"] == "available" for row in summary["evidence"]))
            parser = Links()
            parser.feed(report.render_html(summary))
            targets = {posixpath.normpath(posixpath.join("optimization_framework/reports", urlsplit(target).path))
                       for target in parser.targets if not urlsplit(target).scheme and urlsplit(target).path}
            self.assertEqual(targets, set(report.RECEIPTS.values()) | {
                "optimization_framework/reports/implementation-summary.json",
                "optimization_framework/reports/IMPLEMENTATION_REPORT.md",
                summary["links"]["desktop"], summary["links"]["mobile"],
            })

    def test_invalid_numbers_and_symlinks_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.receipt(root, "smoke", {"stats": {"expected": "secret", "unexpected": True}})
            summary = report.build_summary(root)
            self.assertTrue(all(row["value"] is None for row in summary["metrics"]))
            (root / report.RECEIPTS["profile"]).symlink_to(root / "missing-receipt.json")
            with self.assertRaisesRegex(ValueError, "symlink_refused"):
                report.build_summary(root)


if __name__ == "__main__":
    unittest.main()