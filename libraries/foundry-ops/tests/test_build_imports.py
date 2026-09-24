import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from foundry_ops.build import az_json, parse_queued_build_id, resolve_image, submit_build, wait_build
from foundry_ops.errors import ReadbackError, UnresolvedIntentError, VerificationError
from foundry_ops.records import EvidenceLedger

from fakes import Clock

SRC = Path(__file__).resolve().parents[1] / "src"


class AzTests(unittest.TestCase):
    def test_queued_id_parsing(self):
        self.assertEqual(parse_queued_build_id("WARNING: Queued a build with ID: ca1\n"), "ca1")
        self.assertIsNone(parse_queued_build_id("Queued a build with ID: a\nQueued a build with ID: b\n"))
        self.assertIsNone(parse_queued_build_id(""))

    def test_az_json_records_and_redacts(self):
        events = []
        ok = lambda command, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr="Queued a build with ID: ca9\n")
        self.assertEqual(az_json(["acr", "build", "--no-wait"], events=events, runner=ok), {"runId": "ca9"})
        self.assertEqual(events[0]["command"][:1] + events[0]["command"][-2:], ["az", "-o", "json"])
        bad = lambda command, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="denied Bearer abc.def")
        with self.assertRaises(RuntimeError):
            az_json(["account", "show"], events=events, runner=bad)
        self.assertNotIn("abc.def", events[1]["diagnostic"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = EvidenceLedger(self.temp.name)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, reply):
        def az(arguments):
            self.calls.append(arguments)
            return reply
        return submit_build(az, self.ledger, key="k", subscription="sub", registry="reg", image="repo:tag",
                            context_dir="/ctx")

    def test_submit_once_under_intent(self):
        self.assertEqual(self.submit({"runId": "ca1"}), "ca1")
        self.assertEqual(self.submit({"runId": "other"}), "ca1")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("--no-wait", self.calls[0])
        self.assertTrue(self.ledger.exists("build-k-intent.json"))

    def test_unknown_outcome_is_never_resubmitted(self):
        with self.assertRaises(ReadbackError):
            self.submit(None)
        with self.assertRaises(UnresolvedIntentError):
            self.submit({"runId": "ca2"})
        self.assertEqual(len(self.calls), 1)

    def test_wait_and_resolve(self):
        states = iter(["Queued", "Running", "Succeeded"])
        image = {"registry": "reg.azurecr.io", "repository": "repo", "tag": "tag", "digest": "sha256:" + "a" * 64}

        def az(arguments):
            if arguments[:3] == ["acr", "task", "show-run"]:
                return {"runId": "ca1", "status": next(states), "outputImages": [image]}
            return {"digest": image["digest"]}

        clock = Clock()
        run = wait_build(az, subscription="s", registry="reg", run_id="ca1", sleep=clock.sleep, clock=clock)
        self.assertEqual(resolve_image(az, run, subscription="s", registry="reg", registry_host="reg.azurecr.io",
                                       repository="repo", tag="tag"), "reg.azurecr.io/repo@" + image["digest"])
        with self.assertRaises(VerificationError):
            resolve_image(lambda a: {"digest": "sha256:" + "b" * 64}, run, subscription="s", registry="reg",
                          registry_host="reg.azurecr.io", repository="repo", tag="tag")
        with self.assertRaises(VerificationError):
            resolve_image(az, run, subscription="s", registry="reg", registry_host="reg.azurecr.io", repository="repo", tag="x")
        with self.assertRaises(VerificationError):
            wait_build(lambda a: {"runId": "ca1", "status": "Failed"}, subscription="s", registry="reg", run_id="ca1")
        with self.assertRaises(VerificationError):
            wait_build(lambda a: {"runId": "foreign", "status": "Running"}, subscription="s", registry="reg", run_id="ca1")


class ImportIsolationTests(unittest.TestCase):
    def test_all_modules_import_with_sdks_blocked(self):
        script = """
import importlib, json, sys
BLOCKED = ("azure", "openai", "httpx")
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError("blocked " + name)
sys.meta_path.insert(0, Block())
for module in ("records", "manifest", "bounds", "logs", "verify", "hosted", "evals", "build", "errors"):
    importlib.import_module("foundry_ops." + module)
print(json.dumps(sorted(name for name in sys.modules if name.split(".")[0] in BLOCKED)))
"""
        result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=60,
                                env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
