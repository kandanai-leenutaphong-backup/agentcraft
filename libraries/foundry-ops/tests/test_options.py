"""Additive keyword options (items 1-10): positive path plus matching refusal per option."""

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from foundry_ops.build import submit_build
from foundry_ops.core import (EvidenceLedger, OutcomeUnknownError, ReadbackError, RefusedError,
                              UnresolvedIntentError, VerificationError, error_summary, load_run_manifest, sha256_hex,
                              validate_version_label)
from foundry_ops.evaluation import PartialRowsError, check_criterion, collect_rows, wait_for_run
from foundry_ops.hosting import accepted_response_id, cancel_response, invoke, reconcile_cancellation

from fakes import Clock, Event, FakeOpenAI, HTTPError, Page, ResponseModel, eval_client

AGENT = "agentcraft-migration-a"


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = EvidenceLedger(self.temp.name)
        self.clock = Clock()

    def tearDown(self):
        self.temp.cleanup()


class BuildContextTests(Base):
    def test_context_forwarded_to_intent_and_cannot_replace_request(self):
        submit_build(lambda a: {"runId": "ca1"}, self.ledger, key="k", subscription="s", registry="r", image="i:t",
                     context_dir="/ctx", context={"archive_sha256": "abc", "request": "forged"})
        intent = self.ledger.read("build-k-intent.json")
        self.assertEqual(intent["archive_sha256"], "abc")
        self.assertEqual(intent["request"]["image"], "i:t")
        self.assertIn("/ctx", intent["request"]["command"])
        submit_build(lambda a: {"runId": "ca2"}, self.ledger, key="plain", subscription="s", registry="r",
                     image="i:t", context_dir="/ctx")
        self.assertEqual(set(self.ledger.read("build-plain-intent.json")), {"request", "recorded_at"})

    def test_unknown_outcome_is_value_error_and_unresolved_message(self):
        with self.assertRaises(ValueError) as caught:
            submit_build(lambda a: {}, self.ledger, key="k", subscription="s", registry="r", image="i:t", context_dir="/c")
        self.assertIsInstance(caught.exception, OutcomeUnknownError)
        self.assertIsInstance(caught.exception, ReadbackError)
        with self.assertRaises(UnresolvedIntentError) as again:
            submit_build(lambda a: {"runId": "ca1"}, self.ledger, key="k", subscription="s", registry="r",
                         image="i:t", context_dir="/c")
        self.assertIn("unresolved", str(again.exception))


class CancelTests(Base):
    def queued_client(self):
        client = FakeOpenAI()
        created = []

        def create(**request):
            client.responses.calls.append(("create", request))
            created.append(request)
            client.responses.store["resp_q"] = ResponseModel(id="resp_q", status="queued", output=[])
            return client.responses.store["resp_q"]

        client.responses.create = create
        return client, created

    def test_non_streaming_cancel_and_custom_prefix(self):
        client, created = self.queued_client()
        result = cancel_response(client, self.ledger, key="v1", agent_name=AGENT, version="1", input="q",
                                 stream=False, record_prefix="probe-v1", sleep=self.clock.sleep)
        self.assertEqual((result["response_id"], result["readback"]["status"]), ("resp_q", "cancelled"))
        self.assertEqual((created[0]["stream"], created[0]["background"]), (False, True))
        for name in ("probe-v1-intent.json", "probe-v1-accepted.json", "probe-v1-request-intent.json",
                     "probe-v1-result.json"):
            self.assertTrue(self.ledger.exists(name), name)
        self.assertFalse(self.ledger.list("cancel-*"))
        cancel_response(client, self.ledger, key="v1", agent_name=AGENT, version="1", input="q", stream=False,
                        record_prefix="probe-v1", sleep=self.clock.sleep)
        self.assertEqual([c[0] for c in client.responses.calls].count("create"), 1)
        self.assertEqual([c[0] for c in client.responses.calls].count("cancel"), 1)

    def test_non_streaming_without_identity_refuses(self):
        client = FakeOpenAI()
        client.responses.create = lambda **request: ResponseModel(status="queued")
        with self.assertRaises(ReadbackError):
            cancel_response(client, self.ledger, key="v9", agent_name=AGENT, version="1", input="q", stream=False)
        with self.assertRaises(UnresolvedIntentError):
            cancel_response(client, self.ledger, key="v9", agent_name=AGENT, version="1", input="q", stream=False)

    def test_legacy_accepted_intent_and_cancellation_prefix_are_readable(self):
        client = FakeOpenAI()
        client.responses.store["resp_owned"] = ResponseModel(id="resp_owned", status="queued", output=[])
        (Path(self.temp.name) / "cancel-v2-accepted-intent.json").write_text(json.dumps({"response_id": "resp_owned"}))
        result = cancel_response(client, self.ledger, key="v2", agent_name=AGENT, version="1", input="q",
                                 sleep=self.clock.sleep)
        self.assertEqual(result["response_id"], "resp_owned")
        self.assertNotIn("create", [c[0] for c in client.responses.calls])
        wrapped = {"request": {"response_id": "resp_w"}, "recorded_at": "t"}
        (Path(self.temp.name) / "x-accepted-intent.json").write_text(json.dumps(wrapped))
        self.assertEqual(accepted_response_id(self.ledger, "x"), "resp_w")
        client = FakeOpenAI()
        client.responses.store["resp_c"] = ResponseModel(id="resp_c", status="in_progress", output=[])
        (Path(self.temp.name) / "cancellation-v2-accepted.json").write_text(json.dumps({"response_id": "resp_c"}))
        (Path(self.temp.name) / "cancellation-v2-cancel-intent.json").write_text(json.dumps({"response_id": "resp_c"}))
        client.responses.store["resp_c"] = ResponseModel(id="resp_c", status="cancelled", output=[])
        proved = reconcile_cancellation(client, self.ledger, record_prefix="cancellation-v2", sleep=self.clock.sleep)
        self.assertTrue(proved["cancelled"])
        self.assertNotIn("cancel", [c[0] for c in client.responses.calls])

    def test_reconcile_refusals(self):
        client = FakeOpenAI()
        with self.assertRaises(ReadbackError):
            reconcile_cancellation(client, self.ledger, record_prefix="none")
        (Path(self.temp.name) / "bad-accepted.json").write_text(json.dumps({"response": {}}))
        with self.assertRaises(ReadbackError):
            reconcile_cancellation(client, self.ledger, record_prefix="bad")
        client.responses.store["resp_d"] = ResponseModel(id="resp_d", status="completed", output=[{"type": "message"}])
        with self.assertRaises(VerificationError):
            reconcile_cancellation(client, self.ledger, record_prefix="done", response_id="resp_d",
                                   sleep=self.clock.sleep)


class InvokeStreamTests(Base):
    def events(self, terminal=True):
        call = {"type": "function_call", "call_id": "c1", "name": "count_words", "arguments": '{"text": "a b"}'}
        completed = ResponseModel(id="resp_s", status="completed", output=[call], _text="Hi there")
        events = [Event(type="response.created", response=ResponseModel(id="resp_s", status="queued"), sequence_number=0),
                  Event(type="response.output_item.added", item=call, output_index=0),
                  Event(type="response.output_item.done", item=call, output_index=0),
                  Event(type="response.output_text.delta", delta="Hi ", item_id="m1"),
                  Event(type="response.output_text.delta", delta="there", item_id="m1")]
        return events + ([Event(type="response.completed", response=completed)] if terminal else [])

    def test_stream_returns_ordered_events_timing_and_completed_response(self):
        client = FakeOpenAI()
        client.responses.stream_events = self.events()
        result = invoke(client, self.ledger, key="n1", agent_name=AGENT, version="1", input="q", stream=True,
                        record_name="turn-1", clock=Clock(step=1.0))
        stream = result["stream"]
        self.assertEqual(stream["types"], ["response.created", "response.output_item.added", "response.output_item.done",
                                           "response.output_text.delta", "response.output_text.delta",
                                           "response.completed"])
        self.assertEqual([entry["index"] for entry in stream["events"]], list(range(6)))
        self.assertEqual(stream["text"], "Hi there")
        self.assertEqual(result["output_text"], "Hi there")
        self.assertEqual(result["response"]["id"], "resp_s")
        self.assertEqual([item["type"] for item in stream["items"]],
                         ["response.output_item.added", "response.output_item.done"])
        self.assertLess(stream["first_event_seconds"], stream["first_delta_seconds"])
        self.assertTrue(self.ledger.exists("turn-1-result.json"))
        self.assertFalse(self.ledger.list("invoke-*"))
        self.assertTrue(client.responses.calls[0][1]["stream"])

    def test_non_stream_default_unchanged_and_raw_response_dict(self):
        client = FakeOpenAI()
        result = invoke(client, self.ledger, key="n2", agent_name=AGENT, version="1", input="q")
        self.assertEqual(set(result), {"response", "output_text", "seconds"})
        self.assertEqual(result["response"]["id"], "resp_1")
        self.assertTrue(self.ledger.exists("invoke-n2-result.json"))

    def test_stream_without_terminal_retains_partial_and_never_replays(self):
        client = FakeOpenAI()
        client.responses.stream_events = self.events(terminal=False)
        with self.assertRaises(ReadbackError):
            invoke(client, self.ledger, key="n3", agent_name=AGENT, version="1", input="q", stream=True)
        partial = self.ledger.read("invoke-n3-stream-partial.json")
        self.assertEqual(partial["stream"]["text"], "Hi there")
        with self.assertRaises(UnresolvedIntentError):
            invoke(client, self.ledger, key="n3", agent_name=AGENT, version="1", input="q", stream=True)
        client.responses.stream_events = self.events()
        with self.assertRaises(Exception) as caught:
            invoke(client, self.ledger, key="n4", agent_name=AGENT, version="1", input="q", stream=True, max_events=2)
        self.assertEqual(caught.exception.code, "stream_events")


class EvalOptionTests(unittest.TestCase):
    CRITERION = {"name": "C", "metric": "c", "type": "azure_ai_evaluator", "status": "completed", "score": 1,
                 "passed": True, "evaluator_version": "7"}

    def test_strict_version(self):
        self.assertTrue(check_criterion(self.CRITERION, name="C", metric="c"))
        self.assertTrue(check_criterion(self.CRITERION, name="C", metric="c", evaluator_version="7", strict_version=True))
        with self.assertRaises(VerificationError):
            check_criterion(self.CRITERION, name="C", metric="c", strict_version=True)

    def test_on_event_callbacks(self):
        clock, seen = Clock(), []
        runs = [SimpleNamespace(status="queued"), SimpleNamespace(status="completed")]
        wait_for_run(eval_client(runs=runs), eval_id="e", run_id="r", sleep=clock.sleep, clock=clock, on_event=seen.append)
        self.assertEqual([(e["operation"], e["attempt"], e["status"]) for e in seen],
                         [("poll", 0, "queued"), ("poll", 1, "completed")])
        pages = [Page([{"id": "1"}], "1"), Page([{"id": "2"}], "2")]
        seen.clear()
        collect_rows(eval_client(pages), eval_id="e", run_id="r", expected_count=2, on_event=seen.append)
        self.assertEqual([(e["index"], e["total"], e["last_id"]) for e in seen], [(0, 1, "1"), (1, 2, "2")])

    def failing_client(self):
        def pages():
            yield Page([{"id": "1"}], "1")
            raise HTTPError(503, "transport")
        pager = SimpleNamespace(iter_pages=pages)
        runs = SimpleNamespace(output_items=SimpleNamespace(list=lambda **kwargs: pager))
        return SimpleNamespace(evals=SimpleNamespace(runs=runs))

    def test_transport_failure_keeps_partial_rows_only_when_asked(self):
        with self.assertRaises(PartialRowsError) as caught:
            collect_rows(self.failing_client(), eval_id="e", run_id="r", expected_count=3, partial_on_error=True)
        self.assertEqual(caught.exception.code, "row_transport")
        self.assertEqual([row["id"] for row in caught.exception.partial["rows"]], ["1"])
        self.assertEqual(caught.exception.partial["error"]["status_code"], 503)
        self.assertIsInstance(caught.exception.__cause__, HTTPError)
        with self.assertRaises(HTTPError):
            collect_rows(self.failing_client(), eval_id="e", run_id="r", expected_count=3)


class RecordOptionTests(Base):
    def test_error_summary_keeps_sanitized_provider_errors_and_details(self):
        body = {"error": None, "code": "invalid", "message": "bad", "errors": [
            {"field": "items[0]", "message": "see https://h/x?sig=leak token=abc", "api_key": "k"}],
            "details": {"reason": "Bearer eyJhbGciOi.x.y"}}
        error = HTTPError(400)
        error.response = SimpleNamespace(json=lambda: body)
        detail = error_summary(error)["provider_detail"]
        self.assertEqual(detail["errors"][0]["field"], "items[0]")
        self.assertEqual(detail["code"], "invalid")
        text = json.dumps(detail)
        for secret in ("leak", "abc", "eyJhbGciOi", "api_key"):
            self.assertNotIn(secret, text)
        plain = HTTPError(400)
        plain.response = SimpleNamespace(json=lambda: {"code": "x"})
        self.assertNotIn("errors", error_summary(plain)["provider_detail"])

    def test_version_label(self):
        self.assertEqual(validate_version_label("v" * 50), "v" * 50)
        self.assertEqual(validate_version_label("abc", 3), "abc")
        for bad, limit in (("v" * 51, 50), ("abcd", 3), ("", 50), (None, 50)):
            with self.assertRaises(RefusedError):
                validate_version_label(bad, limit)

    def test_ledger_list(self):
        for name in ("a-intent.json", "a-result.json", "b-intent.json"):
            self.ledger.retain(name, {})
        os.symlink(Path(self.temp.name) / "a-result.json", Path(self.temp.name) / "a-link.json")
        self.assertEqual(self.ledger.list("a-*"), ["a-intent.json", "a-result.json"])
        self.assertEqual(self.ledger.list("*-intent.json"), ["a-intent.json", "b-intent.json"])
        for bad in ("", "../*", "x/*", "..", "a\\b"):
            with self.assertRaises(RefusedError):
                self.ledger.list(bad)


class ManifestFieldTests(Base):
    def test_allowed_fields(self):
        value = {"schema_version": 1, "purpose": "migration-development", "actions": ["deploy"],
                 "series": "migration-a", "agent": AGENT, "note": "x"}
        path = Path(self.temp.name) / "run.json"
        path.write_text(json.dumps(value))
        digest = sha256_hex(path.read_bytes())
        load = lambda **kw: load_run_manifest(path, expected_sha256=digest, action="deploy",
                                             allowed_root=self.temp.name, **kw)
        self.assertEqual(load().series, "migration-a")
        self.assertEqual(load(allowed_fields=set(value)).series, "migration-a")
        with self.assertRaises(RefusedError) as caught:
            load(allowed_fields=set(value) - {"note"})
        self.assertEqual(caught.exception.code, "manifest_field")
        self.assertIn("note", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
