"""Exercise provenance defaults, guarded browser routing and read-only verification."""

from __future__ import annotations

import contextlib
import io
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "lib"))
import webres


class Portability(unittest.TestCase):
    def test_acquisition_catalogues_raw_and_text_output_by_default(self) -> None:
        script = runpy.run_path(str(SKILL / "scripts/fetch-page/fetch_page.py"))
        payload = b"<title>Fixture</title><p>Public documentation</p>"
        provenance = webres.Provenance("https://example.test/docs", "fixture", 200, "text/html",
                                       webres.sha256_bytes(payload), len(payload), title="Fixture")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch.dict(script["main"].__globals__, {"fetch": Mock(return_value=(payload, provenance))}):
                with patch.object(sys, "argv", ["fetch", "--url", provenance.source_url, "--out", directory, "--text"]), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(script["main"](), 0)
            catalogue = webres.Catalogue(output / "manifest.json")
            self.assertEqual(len(catalogue.entries), 2)
            for key, entry in catalogue.entries.items():
                self.assertEqual(entry["sha256"], webres.sha256_bytes((output / key).read_bytes()))
            before = (output / "manifest.json").read_bytes()
            verifier = runpy.run_path(str(SKILL / "scripts/catalogue/catalogue.py"))
            with patch.object(sys, "argv", ["catalogue", "--catalogue", str(output / "manifest.json"), "--verify"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verifier["main"](), 0)
            self.assertEqual((output / "manifest.json").read_bytes(), before)

    def test_untrusted_catalogue_cannot_escape_its_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            for path in ("../private.txt", "/etc/passwd"):
                manifest.write_text(json.dumps({"entries": [{"artefact": path}]}), encoding="utf-8")
                with self.assertRaises(webres.AcquisitionError):
                    webres.Catalogue(manifest)

    def test_browser_refusal_aborts_without_continuing(self) -> None:
        script = runpy.run_path(str(SKILL / "scripts/capture-screenshot/capture_screenshot.py"))
        route = Mock()
        route.request.url = "http://127.0.0.1/private"
        route.request.method = "GET"
        blocked = []
        with patch.dict(script["fulfill_public"].__globals__, {"open_public": Mock(side_effect=webres.AcquisitionError("private"))}):
            script["fulfill_public"](route, obey_robots=True, blocked=blocked)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()
        route.fulfill.assert_not_called()
        self.assertEqual(len(blocked), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)