"""Offline replay: retained live records through the migrated verification/extraction path (spec R, testbed H).

Retained bytes under deploy/records are only read; every mutation happens on a temporary copy.
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deploy import experiment
from foundry_ops.core import EvidenceLedger, RefusedError, VerificationError, read_receipt, redact, safe_identifier
from foundry_ops.hosting import check_active_version, check_identity, hosted, require_refusal, traces
from main import TOOLS

RECORDS = experiment.DEPLOY / "records"
SERIES = RECORDS / "migration-h-v1"
SPEC_VERIFY = ("20260922T184312034351Z-verify.json", "384576ed47bce4cf0834663ef067a4cf84464dbcb251b47a9529cd4626ccd8b4")
VERIFY_RECEIPTS = ("20260922T175841720508Z-verify.json", "20260922T180112557621Z-verify.json",
                   "20260922T182056738572Z-verify.json", "20260922T183659245318Z-verify.json",
                   "20260922T184257733774Z-verify.json", "20260922T184312034351Z-verify.json")
CANCEL_RECEIPTS = {"20260922T182020296700Z-invoke.json": ("cancel-v2", False, False),
                   "20260922T182442985551Z-invoke.json": ("cancel-stream-v2", True, False),
                   "20260922T183227243161Z-invoke.json": ("cancel-stream-v3", True, False),
                   "20260922T185121107291Z-invoke.json": ("cancel-work-v3", True, True)}
LOG_RECEIPTS = ("20260922T184026308654Z-logs.json", "20260922T184703056918Z-logs.json", "20260922T190351658635Z-logs.json")
IDENTITY = ("agent_name", "agent_version", "source_sha256", "config_sha256", "nonce")


def load(root, name):
    return json.loads((Path(root) / name).read_bytes())


def observation(receipt, operation):
    return [item for item in receipt["observations"] if isinstance(item, dict) and item.get("operation") == operation]


def invocation_for(root, receipt):
    """The complete invoke receipt that produced this verify receipt's response, read through foundry_ops."""
    found = []
    for name in EvidenceLedger(root).list("2026*-invoke.json"):
        try:
            result = read_receipt(Path(root) / name, root=root, action="invoke", expect={"target": receipt["target"]})
        except RefusedError:
            continue
        if result.get("response_id") == receipt["result"]["response_id"]:
            found.append(result)
    if len(found) != 1:
        raise AssertionError(f"expected one owning invocation, found {len(found)}")
    return found[0]


def replay_verify(root, name):
    """(derived, recorded): derived from the stored response by migrated code; recorded from retained fields."""
    receipt = load(root, name)
    recorded = receipt["result"]
    invocation = invocation_for(root, receipt)
    (stored,) = [item["response"] for item in observation(receipt, "stored_response")]
    tool, nonce = invocation["tool"], invocation["nonce"]
    with patch.object(experiment, "TARGET", receipt["target"]):
        envelope = experiment.verify_response(stored, nonce, invocation["deployed"], tool)
    (call,) = traces.tool_calls(stored, envelope_key="tool_events", expected=[tool])
    derived = {
        "response_id": stored["id"],
        "readback": stored["status"] == "completed" and stored["output"] == invocation["response_output"]
        and (stored.get("metadata") or {}) == (invocation["response_metadata"] or {}),
        "tool_evidence": envelope,
        "tool_name": call["name"], "tool_call_id": call["call_id"], "tool_arguments": call["arguments"],
        "tool_output": call["output"], "tool_status": call["status"], "tool_sources": call["sources"],
        "nonce_result": TOOLS[tool](nonce),
        "identity": {key: envelope[key] for key in IDENTITY},
        "anonymous_status": require_refusal(invocation["anonymous_status"]),
    }
    events = {event["kind"]: event["data"] for event in recorded["tool_evidence"]["tool_events"]}
    deployed = invocation["deployed"]
    expected = {
        "response_id": recorded["response_id"],
        "readback": recorded["readback"],
        "tool_evidence": recorded["tool_evidence"],
        "tool_name": recorded["tool_evidence"]["requested_tool"],
        "tool_call_id": events["tool.call.ready"]["call_id"],
        "tool_arguments": events["tool.call.ready"]["arguments"],
        "tool_output": events["tool.result"]["result"],
        "tool_status": "completed" if "tool.result" in events and "tool.failed" not in events else "failed",
        "tool_sources": ["envelope"],
        "nonce_result": events["tool.result"]["result"],
        "identity": {"agent_name": receipt["target"]["agent_name"], "agent_version": recorded["version"]["version"],
                     "source_sha256": receipt["source_sha256"],
                     "config_sha256": deployed["metadata"]["config_sha256"], "nonce": nonce},
        "anonymous_status": recorded["anonymous_status"],
    }
    return derived, expected


def differing(derived, expected):
    return sorted(key for key in derived.keys() | expected.keys() if derived.get(key) != expected.get(key))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReplayEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.pins = {path: sha256(path) for path in SERIES.iterdir() if path.is_file()}

    def tearDown(self):
        self.assertEqual({path: sha256(path) for path in SERIES.iterdir() if path.is_file()}, self.pins)

    def test_spec_pinned_receipt_identity(self):
        self.assertEqual(sha256(SERIES / SPEC_VERIFY[0]), SPEC_VERIFY[1])

    def test_verify_receipts_replay_with_zero_differing_fields(self):
        self.assertEqual([name for name in EvidenceLedger(SERIES).list("2026*-verify.json")
                          if load(SERIES, name)["status"] == "complete"], list(VERIFY_RECEIPTS))
        tools = set()
        for name in VERIFY_RECEIPTS:
            with self.subTest(receipt=name):
                derived, expected = replay_verify(SERIES, name)
                self.assertEqual(differing(derived, expected), [])
                receipt = load(SERIES, name)
                check_identity(receipt["result"]["tool_evidence"], expected["identity"], what="retained identity")
                invocation = invocation_for(SERIES, receipt)
                self.assertEqual(receipt["result"]["tool_evidence"], invocation["envelope"])
                self.assertEqual(receipt["result"]["version"], invocation["deployed"]["readback"])
                self.assertEqual([item["http_status"] for item in observation(load(SERIES, next(
                    item for item in EvidenceLedger(SERIES).list("2026*-invoke.json")
                    if (load(SERIES, item).get("result") or {}).get("response_id") == receipt["result"]["response_id"])),
                    "anonymous_probe")], [401])
                tools.add((derived["tool_name"], derived["identity"]["agent_version"]))
        self.assertEqual(tools, {("nonce_digest", "1"), ("nonce_statistics", "1"), ("nonce_reverse", "2"),
                                 ("nonce_digest", "3"), ("nonce_statistics", "3"), ("nonce_reverse", "3")})

    def test_invoke_receipts_rederive_envelope_from_proof_response(self):
        for name in EvidenceLedger(SERIES).list("2026*-invoke.json"):
            receipt = load(SERIES, name)
            result = receipt.get("result") or {}
            if receipt["status"] != "complete" or "envelope" not in result:
                continue
            with self.subTest(receipt=name), patch.object(experiment, "TARGET", receipt["target"]):
                (response,) = [item["response"] for item in observation(receipt, "proof_response")]
                self.assertEqual(response["output"], result["response_output"])
                self.assertEqual(experiment.verify_response(response, result["nonce"], result["deployed"], result["tool"]),
                                 result["envelope"])

    def test_active_version_readback_replay(self):
        receipt = load(RECORDS, "20260922T055527010328Z-deploy.json")
        deployed = receipt["result"]
        raw = [item["result"] for item in receipt["observations"] if isinstance(item, dict)
               and isinstance(item.get("result"), dict) and item["result"].get("status") == "active"]
        self.assertTrue(raw)
        for actual in raw:
            derived = check_active_version(actual, version=deployed["version"], image=deployed["image"],
                                           metadata=deployed["metadata"], definition=deployed["definition"])
            recorded = deployed["readback"]
            # Pre-foundry_ops readback named the version state `state`; foundry_ops names it `status`.
            self.assertEqual(derived, {"version": recorded["version"], "status": recorded["state"],
                                       "definition": recorded["definition"]})
        for name in EvidenceLedger(SERIES).list("2026*-deploy.json"):
            with self.subTest(receipt=name):
                receipt = load(SERIES, name)
                deployed = receipt["result"]
                (created,) = [item["result"] for item in observation(receipt, "create_hosted_agent")]
                with self.assertRaisesRegex(VerificationError, r"^exact version not active: status$"):
                    check_active_version(created, version=deployed["version"], image=deployed["image"],
                                         metadata=deployed["metadata"], definition=deployed["definition"])

    def test_cancellation_receipts_reconcile_without_create_or_cancel(self):
        ledger = EvidenceLedger(SERIES)
        for name, (prefix, streaming, during_work) in CANCEL_RECEIPTS.items():
            receipt = load(SERIES, name)
            (before,) = [item["response"] for item in observation(receipt, "before_cancel")]
            (after,) = [item["response"] for item in observation(receipt, "cancel_readback")]
            self.assertEqual(hosted.accepted_response_id(ledger, prefix), before["id"])
            with self.subTest(receipt=name), tempfile.TemporaryDirectory() as directory:
                for path in SERIES.glob(prefix + "-*.json"):
                    shutil.copyfile(path, Path(directory) / path.name)
                client = MagicMock()
                client.responses.retrieve.side_effect = [SimpleNamespace(model_dump=lambda state=state, **kwargs: state)
                                                         for state in (before, after, after)]
                project = MagicMock()
                project.get_openai_client.return_value = nullcontext(client)
                deployed = (receipt.get("result") or {}).get("deployed") or {
                    "agent": receipt["target"]["agent_name"], "version": before["agent_reference"]["version"]}
                with patch.object(experiment, "RECORDS", Path(directory)), \
                     patch.object(experiment, "RUN_MANIFEST", {"series": "migration-h-v1"}), \
                     patch.object(experiment, "OBSERVATIONS", []), \
                     patch.object(experiment, "read_receipt", return_value=deployed), \
                     patch.object(experiment, "check_version"), \
                     patch.object(experiment, "project_client", return_value=nullcontext(project)):
                    if receipt["status"] == "complete":
                        derived = experiment.cancellation_probe("receipt", streaming, during_work)
                        recorded = receipt["result"]
                        self.assertEqual({key: derived[key] for key in recorded}, recorded)
                        self.assertEqual(derived["readback"]["status"], "cancelled")
                    else:
                        self.assertTrue(receipt["error"].startswith("cancellation not proved"))
                        with self.assertRaisesRegex(VerificationError, "^cancellation not proved"):
                            experiment.cancellation_probe("receipt", streaming, during_work)
                        self.assertEqual(experiment.OBSERVATIONS[-1]["response"], after)
                client.responses.create.assert_not_called()
                client.responses.cancel.assert_not_called()
                self.assertEqual(sorted(path.name for path in Path(directory).iterdir()),
                                 sorted(path.name for path in SERIES.glob(prefix + "-*.json")))

    def test_log_receipts_bounds_and_session_version(self):
        sessions = {}
        for name in EvidenceLedger(SERIES).list("2026*-invoke.json"):
            for item in observation(load(SERIES, name), "cancel_readback"):
                sessions[item["response"]["agent_session_id"]] = item["response"]["agent"]["version"]
        for name in LOG_RECEIPTS:
            with self.subTest(receipt=name):
                receipt = load(SERIES, name)
                recorded = receipt["result"]
                session = safe_identifier(recorded["session_id"], "session id")
                self.assertEqual(sessions[session], recorded["version"])
                self.assertLessEqual(len(recorded["exception_lines"]), 100)
                self.assertTrue(all(line == redact(line) for line in recorded["exception_lines"]))
                project = MagicMock()
                project.agents.get_session.return_value = {"version_indicator": {"agent_version": sessions[session]}}
                project.agents.get_session_log_stream.return_value = iter(())
                derived = hosted.session_log_excerpt(project, agent_name=receipt["target"]["agent_name"],
                                                     agent_version=recorded["version"], session_id=session)
                # Pre-foundry_ops receipts named the excerpt `exception_lines`; foundry_ops names it `lines`.
                self.assertEqual((derived["session_id"], derived["version"], derived["lines"]),
                                 (recorded["session_id"], recorded["version"], recorded["exception_lines"]))
                (bounded,) = observation(receipt, "bounded_session_logs")
                self.assertIn(bounded["termination"], {"ValueError", "ServiceResponseTimeoutError"})
                with self.assertRaisesRegex(VerificationError, "session version mismatch"):
                    hosted.session_log_excerpt(project, agent_name=receipt["target"]["agent_name"],
                                               agent_version=str(int(recorded["version"]) - 1), session_id=session)

    def test_mutated_copy_fails(self):
        verify_name, _ = SPEC_VERIFY
        invoke_name = "20260922T184032990976Z-invoke.json"
        with tempfile.TemporaryDirectory() as directory:
            for name in (verify_name, invoke_name):
                shutil.copyfile(SERIES / name, Path(directory) / name)
            self.assertEqual(differing(*replay_verify(directory, verify_name)), [])
            receipt = load(directory, verify_name)
            (stored,) = [item["response"] for item in observation(receipt, "stored_response")]
            text = stored["output"][0]["content"][0]["text"]
            envelope = json.loads(text)
            result = next(event for event in envelope["tool_events"] if event["kind"] == "tool.result")
            result["data"]["result"]["reversed_hex"] = result["data"]["result"]["reversed_hex"][::-1]
            stored["output"][0]["content"][0]["text"] = json.dumps(envelope)
            (Path(directory) / verify_name).write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "tool evidence does not match"):
                replay_verify(directory, verify_name)
            shutil.copyfile(SERIES / verify_name, Path(directory) / verify_name)
            receipt = load(directory, verify_name)
            receipt["result"]["anonymous_status"] = 200
            receipt["result"]["tool_evidence"]["agent_version"] = "2"
            (Path(directory) / verify_name).write_text(json.dumps(receipt))
            self.assertEqual(differing(*replay_verify(directory, verify_name)), ["anonymous_status", "tool_evidence"])


if __name__ == "__main__":
    unittest.main()
