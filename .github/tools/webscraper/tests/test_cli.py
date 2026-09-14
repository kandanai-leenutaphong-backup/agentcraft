import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from data_collection.cli import main
from data_collection.models import HTTPResponse


class CLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.response = HTTPResponse("https://example.test/final", 200, {"content-type": "text/html"}, b"<h1>CLI HTML</h1>")

    def test_cli_acquires_saves_and_verifies(self):
        output = io.StringIO()
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock, return_value=self.response), contextlib.redirect_stdout(output):
            code = main(["https://example.test", "--out", str(self.root)])
        self.assertEqual(code, 0)
        receipt = json.loads(output.getvalue())
        self.assertTrue(receipt["verified"])
        self.assertEqual(Path(receipt["html_path"]).read_text(encoding="utf-8-sig"), "<h1>CLI HTML</h1>")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--verify", receipt["directory"]])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())["ok"])

    def test_raw_stdout_contains_html_only(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock, return_value=self.response), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(["https://example.test", "--raw", "--out", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "<h1>CLI HTML</h1>")
        self.assertTrue(json.loads(errors.getvalue())["verified"])

    def test_batch_json_and_failure_exit_code(self):
        input_path = self.root / "urls.json"
        input_path.write_text(json.dumps(["https://example.test/a", "https://example.test/b"]))
        response = HTTPResponse("https://example.test", 403, {}, b"")
        output = io.StringIO()
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock, return_value=response), contextlib.redirect_stdout(output):
            code = main(["--input", str(input_path), "--out", str(self.root)])
        self.assertEqual(code, 1)
        receipts = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(receipt["error_code"] == "access_denied" for receipt in receipts))

    def test_invalid_config_fails_before_network(self):
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock) as request, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["https://example.test", "--concurrency", "0"])
        self.assertEqual(raised.exception.code, 2)
        request.assert_not_awaited()

    def test_persistence_failure_is_not_success(self):
        output = io.StringIO()
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock, return_value=self.response), patch("data_collection.cli.save_result", side_effect=OSError("fixture")), contextlib.redirect_stdout(output):
            code = main(["https://example.test", "--out", str(self.root)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["error_code"], "persistence_failed")


if __name__ == "__main__":
    unittest.main()