from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import InvalidInput, craft_dataset, read_artifacts
from craft import MODES, load_dataset, main
from fixtures import OWNED_ROOT, TinyPack


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OWNED_ROOT, prefix=".test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = TinyPack(self.root).write()

    def craft(self, output):
        return craft_dataset(mode_id="operations", registry=MODES, resources=self.fixture.pack, source_root=self.fixture.source, output=output)

    def test_tiny_end_to_end_outputs_are_identical_and_nonoverwriting(self):
        first, second = self.root / "first", self.root / "second"
        self.craft(first)
        self.craft(second)
        self.assertEqual(read_artifacts(first), read_artifacts(second))
        self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
        _, inputs, labels = load_dataset(first)
        self.assertEqual(len(inputs), 3)
        self.assertEqual(len(labels), 3)
        self.assertNotIn("expected", inputs[0])
        with self.assertRaisesRegex(InvalidInput, "output already exists"):
            self.craft(first)

    def test_cli_craft_replay_and_compare(self):
        run = self.root / "crafted"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--mode", "operations", "--resources", str(self.fixture.pack), "--source-root", str(self.fixture.source), "--output", str(run)]), 0)
            self.assertEqual(main(["--replay", str(run), "--output", str(self.root / "replayed")]), 0)
            self.assertEqual(main(["--compare", str(run), "--output", str(self.root / "compared")]), 0)
        self.assertTrue((self.root / "compared" / "replay" / "metrics.csv").is_file())

    def test_unknown_mode_cli_does_not_inspect_paths(self):
        with patch.object(Path, "exists", side_effect=AssertionError("filesystem access")), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--mode", "__import__('os')", "--output", "not-created"]), 2)

    def test_invalid_input_has_no_output_and_replay_detects_tampering(self):
        run = self.root / "invalid"
        (self.fixture.pack / "assets.json").write_bytes(b"{}")
        with self.assertRaises(InvalidInput):
            self.craft(run)
        self.assertFalse(run.exists())
        self.fixture.write()
        self.craft(run)
        with (run / "detection.inputs.jsonl").open("ab") as stream:
            stream.write(b"{}\n")
        with self.assertRaisesRegex(InvalidInput, "SHA-256"):
            load_dataset(run)

    def test_host_injected_mode_runs_through_same_integrity_pipeline(self):
        class TestMode:
            id = "test_mode"
            version = 1
            input_resources = frozenset({"assets"})

            def build(self, bundle):
                return {"test.json": b'{"test_mode": true}\n'}

        output = self.root / "test-mode"
        manifest = craft_dataset(mode_id="test_mode", registry={"test_mode": TestMode()}, resources=self.fixture.pack,
                                 source_root=self.fixture.source, output=output)
        self.assertEqual(manifest["mode"]["id"], "test_mode")
        self.assertTrue((output / "provenance.json").exists())


if __name__ == "__main__":
    unittest.main()