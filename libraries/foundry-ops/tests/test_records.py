import json
import os
from pathlib import Path
import tempfile
import unittest

from foundry_ops.core import (EvidenceLedger, ReadbackError, RefusedError, UnresolvedIntentError, encode_json,
                              error_summary, pin, read_pinned, read_receipt, redact_text, sanitize, sha256_hex,
                              to_plain)

from fakes import HTTPError, Model


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = EvidenceLedger(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_retain_writes_exact_bytes_and_refuses_overwrite(self):
        receipt = self.ledger.retain("a.json", {"b": 1, "a": [1]})
        self.assertEqual((self.root / "a.json").read_bytes(), encode_json({"a": [1], "b": 1}))
        self.assertEqual(receipt["sha256"], sha256_hex((self.root / "a.json").read_bytes()))
        with self.assertRaises(RefusedError) as caught:
            self.ledger.retain("a.json", {"b": 1, "a": [1]})
        self.assertEqual(caught.exception.code, "record_exists")

    def test_allow_identical_only_for_same_bytes(self):
        self.ledger.retain("m.json", {"x": 1})
        self.assertEqual(self.ledger.retain("m.json", {"x": 1}, allow_identical=True)["name"], "m.json")
        with self.assertRaises(RefusedError):
            self.ledger.retain("m.json", {"x": 2}, allow_identical=True)
        self.assertEqual(self.ledger.read("m.json"), {"x": 1})

    def test_unsafe_names_and_symlinks_refused(self):
        for name in ("../escape.json", "a/b.json", "", ".hidden"):
            with self.assertRaises(RefusedError):
                self.ledger.retain(name, {})
        outside = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(os.unlink, outside.name)
        os.symlink(outside.name, self.root / "link.json")
        with self.assertRaises(RefusedError):
            self.ledger.retain("link.json", {})
        linked = self.root.parent / (self.root.name + "-link")
        os.symlink(self.root, linked)
        self.addCleanup(os.unlink, linked)
        with self.assertRaises(RefusedError):
            EvidenceLedger(linked)

    def test_nan_refused(self):
        with self.assertRaises(ValueError):
            self.ledger.retain("nan.json", {"x": float("nan")})
        self.assertFalse(self.ledger.exists("nan.json"))

    def test_intent_is_written_once(self):
        self.ledger.intent("deploy-x", {"a": 1}, context={"decision_sha256": "d"})
        record = self.ledger.read("deploy-x-intent.json")
        self.assertEqual((record["request"], record["decision_sha256"]), ({"a": 1}, "d"))
        with self.assertRaises(UnresolvedIntentError):
            self.ledger.intent("deploy-x", {"a": 1})

    def test_once_runs_action_once_and_refuses_dangling_intent(self):
        calls = []
        self.assertEqual(self.ledger.once("op", {"r": 1}, lambda: calls.append(1) or {"ok": True}), {"ok": True})
        self.assertEqual(self.ledger.once("op", {"r": 1}, lambda: calls.append(1) or {"ok": False}), {"ok": True})
        self.assertEqual(len(calls), 1)

        def fail():
            raise RuntimeError("transport lost")

        with self.assertRaises(RuntimeError):
            self.ledger.once("lost", {}, fail)
        with self.assertRaises(UnresolvedIntentError):
            self.ledger.once("lost", {}, lambda: {"ok": True})


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "r.json"
        self.path.write_text(json.dumps({"action": "deploy", "status": "complete", "target": {"t": 1}, "result": {"v": "3"}}))

    def tearDown(self):
        self.temp.cleanup()

    def test_owned_complete_receipt(self):
        digest = sha256_hex(self.path.read_bytes())
        self.assertEqual(read_receipt(self.path, root=self.root, action="deploy", expected_sha256=digest,
                                      expect={"target": {"t": 1}}), {"v": "3"})

    def test_receipt_refusals(self):
        cases = [dict(action="build"), dict(action="deploy", expected_sha256="0" * 64),
                 dict(action="deploy", expect={"target": {"t": 2}})]
        for kwargs in cases:
            with self.assertRaises(RefusedError):
                read_receipt(self.path, root=self.root, **kwargs)
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(RefusedError) as caught:
                read_receipt(self.path, root=other, action="deploy")
            self.assertEqual(caught.exception.code, "foreign_path")
        self.path.write_text(json.dumps({"action": "deploy", "status": "blocked"}))
        with self.assertRaises(RefusedError):
            read_receipt(self.path, root=self.root, action="deploy")

    def test_read_pinned_and_pin(self):
        digest = sha256_hex(self.path.read_bytes())
        self.assertEqual(read_pinned(self.path, root=self.root, expected_sha256=digest)["action"], "deploy")
        self.assertEqual(pin(self.path, root=self.root), {"path": "r.json", "sha256": digest,
                                                          "bytes": self.path.stat().st_size})


class SafeShapeTests(unittest.TestCase):
    def test_sanitize_drops_credentials_and_url_queries(self):
        value = {"sas_uri": "https://a.blob.core.windows.net/c?sig=abc", "Authorization": "Bearer x",
                 "blob": "see https://user:pw@a.blob.core.windows.net/c/d?sv=1&sig=secret#frag now",
                 "items": [{"credential": 1, "keep": 2}]}
        self.assertEqual(sanitize(value), {"blob": "see https://a.blob.core.windows.net/c/d now",
                                           "items": [{"keep": 2}]})

    def test_redact_text(self):
        text = redact_text("Bearer abc.def token=xyz eyJhbGciOi.payload.sig sig=zzz ok")
        for secret in ("abc.def", "xyz", "eyJhbGciOi", "zzz"):
            self.assertNotIn(secret, text)
        self.assertIn("ok", text)

    def test_error_summary_is_bounded_and_redacted(self):
        error = HTTPError(400, "bad https://h/x?sig=leak password=hunter2 " + "y" * 5000)
        summary = error_summary(error, limit=200)
        self.assertEqual((summary["type"], summary["status_code"]), ("HTTPError", 400))
        self.assertLessEqual(len(summary["reason"]), 200)
        self.assertNotIn("leak", summary["reason"])
        self.assertNotIn("hunter2", summary["reason"])

    def test_to_plain_converts_nested_models(self):
        self.assertEqual(to_plain([Model(a=Model(b=1))]), [{"a": {"b": 1}}])


if __name__ == "__main__":
    unittest.main()
