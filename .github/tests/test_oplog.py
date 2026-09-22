import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "oplog", Path(__file__).resolve().parents[1] / "tools" / "oplog.py")
oplog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oplog)


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / "events.jsonl"

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            oplog.main([*args, "--log", str(self.log)])
        return output.getvalue().strip()

    def observed(self, seconds, boot="boot-one"):
        return {"checked_at": "2026-09-22T10:00:00+00:00",
                "monotonic": seconds, "boot_id": boot}

    def test_deadline_penalties_and_completion_freeze(self):
        with patch.object(oplog, "clock", return_value=self.observed(100)):
            run = self.invoke("start", "task", "--limit-seconds", "120")
        for moment, penalty in [(160, 0), (220, 0), (221, 1), (280, 1), (281, 2)]:
            with self.subTest(moment=moment), patch.object(
                    oplog, "clock", return_value=self.observed(moment)):
                result = json.loads(self.invoke("check", "--run", run))
                self.assertEqual(result["elapsed_seconds"], moment - 100)
                self.assertEqual(result["penalty_minutes"], penalty)
                self.assertEqual(result["clock_basis"], "monotonic")
        with patch.object(oplog, "clock", return_value=self.observed(282)):
            ended = json.loads(self.invoke("end", "--run", run, "--achieved"))
        with patch.object(oplog, "clock", return_value=self.observed(900)):
            checked = json.loads(self.invoke("check", "--run", run))
        self.assertEqual(checked["elapsed_seconds"], ended["elapsed_seconds"])
        self.assertEqual(checked["penalty_minutes"], ended["penalty_minutes"])
        self.assertEqual(checked["completed_at"], ended["completed_at"])
        self.assertEqual(checked["monotonic"], 900)
        self.assertTrue(ended["objective_achieved"])
        self.assertEqual(len(oplog.read(self.log)), 8)

    def test_no_limit_and_incomplete_end(self):
        with patch.object(oplog, "clock", return_value=self.observed(100)):
            run = self.invoke("start", "task")
        with patch.object(oplog, "clock", return_value=self.observed(150)):
            self.invoke("end", "--run", run)
        with patch.object(oplog, "clock", return_value=self.observed(200)):
            result = json.loads(self.invoke("check", "--run", run))
        self.assertEqual(result["elapsed_seconds"], 100)
        self.assertIsNone(result["remaining_seconds"])
        self.assertEqual(result["penalty_minutes"], 0)
        self.assertFalse(result["objective_achieved"])

    def test_legacy_clock_fallback_and_unknown_run(self):
        oplog.append({"event": "run_start", "run": "old", "task": "legacy"}, self.log)
        result = oplog.timing(self.log, "old")
        self.assertEqual(result["clock_basis"], "wall_clock_fallback")
        with self.assertRaisesRegex(SystemExit, "unknown run"):
            oplog.timing(self.log, "missing")

    def test_refuse_deadline_reset_and_ambiguous_check(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for args in [("check",), ("check", "--run", "missing", "--limit-seconds", "60"),
                         ("start", "task", "--limit-seconds", "nan"),
                         ("check", "--run", "missing", "--achieved")]:
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    self.invoke(*args)


if __name__ == "__main__":
    unittest.main()