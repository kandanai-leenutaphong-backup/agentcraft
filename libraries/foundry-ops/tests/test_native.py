"""Native eval / evaluator / optimization / tool-trace steps (items 11-14) over offline fakes."""

import json
import tempfile
from types import SimpleNamespace
import unittest

from foundry_ops.core import (BoundExceededError, EvidenceLedger, OutcomeUnknownError, RefusedError,
                              UnresolvedIntentError, VerificationError)
from foundry_ops.evaluation import (agent_eval_definition, agent_run_request, code_evaluator_definition,
                                    infer_item_schema, local_canary, register_code_evaluator, run_agent_eval,
                                    run_code_evaluator_canary, submit_run, summarize_criteria)
from foundry_ops.hosting import invoke, tool_calls
from foundry_ops.optimization import (list_candidates, optimization_job, resolve_candidate_config,
                                      submit_optimization, wait_optimization)

from fakes import Clock, Event, FakeOpenAI, Model, Page, Pager, ResponseModel

AGENT = "agentcraft-example"
CRITERIA = [{"type": "azure_ai_evaluator", "name": "exact", "evaluator_name": "ev", "evaluator_version": "1",
             "data_mapping": {"response": "{{sample.output_text}}", "ground_truth": "{{item.ground_truth}}"}}]
ITEMS = [{"query": "q1", "ground_truth": "a"}, {"query": "q2", "ground_truth": "b"}]


class Obj(Model):
    """SDK-like model: attribute access plus `as_dict`."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class FakeEvals:
    """`client.evals` shaped like openai 3.13: create/retrieve, runs.create/retrieve, runs.output_items.list."""

    def __init__(self, rows, statuses=("queued", "completed"), run_id="run_1"):
        self.calls, self.definitions, self.rows = [], {}, rows
        self.statuses, self.run_id = list(statuses), run_id
        self.runs = SimpleNamespace(create=self._run_create, retrieve=self._run_retrieve,
                                    output_items=SimpleNamespace(list=self._items))

    def create(self, **request):
        self.calls.append(("create", request))
        self.definitions["eval_1"] = dict(request, id="eval_1")
        return SimpleNamespace(id="eval_1")

    def retrieve(self, eval_id):
        self.calls.append(("retrieve", eval_id))
        return Model(self.definitions[eval_id])

    def _run_create(self, **request):
        self.calls.append(("run_create", request))
        return SimpleNamespace(id=self.run_id)

    def _run_retrieve(self, run_id, eval_id):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return Obj(id=run_id, eval_id=eval_id, status=status, error=None,
                     result_counts={"total": len(self.rows), "passed": 1, "failed": 1, "errored": 0, "skipped": 0})

    def _items(self, **kwargs):
        return Pager([Page([Model(row) for row in self.rows], "last")])


def result_row(identifier, query, passed, **result):
    return {"id": identifier, "eval_id": "eval_1", "run_id": "run_1", "status": "completed", "error": None,
            "datasource_item": {"query": query},
            "results": [{"name": "exact", "metric": "exact", "type": "azure_ai_evaluator", "status": "completed",
                         "score": 1.0 if passed else 0.0, "passed": passed, **result}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = EvidenceLedger(self.temp.name)
        self.clock = Clock()

    def tearDown(self):
        self.temp.cleanup()


class AgentEvalTests(Base):
    def run_eval(self, evals, **kwargs):
        client = SimpleNamespace(evals=evals)
        return run_agent_eval(client, self.ledger, key="k1", name="smoke", agent_name=AGENT, agent_version="3",
                              testing_criteria=CRITERIA, items=ITEMS, sleep=self.clock.sleep, clock=self.clock, **kwargs)

    def test_create_run_wait_collect_summarize_and_resume(self):
        evals = FakeEvals([result_row("o1", "q1", True), result_row("o2", "q2", False)])
        seen = []
        result = self.run_eval(evals, on_event=seen.append)
        self.assertEqual((result["settled"], result["complete"]), (True, True))
        self.assertEqual(result["summary"]["exact"], {"passed": 1, "failed": 1, "errored": 0, "missing": 0,
                                                      "total": 2, "pass_rate": 0.5})
        create = next(request for name, request in evals.calls if name == "create")
        self.assertEqual(create["data_source_config"]["item_schema"]["required"], ["ground_truth", "query"])
        self.assertTrue(create["data_source_config"]["include_sample_schema"])
        source = next(request for name, request in evals.calls if name == "run_create")["data_source"]
        self.assertEqual(source["type"], "azure_ai_target_completions")
        self.assertEqual(source["source"], {"type": "file_content", "content": [{"item": item} for item in ITEMS]})
        self.assertEqual(source["target"], {"type": "azure_ai_agent", "name": AGENT, "version": "3"})
        self.assertNotIn("evaluation_level", json.dumps(evals.calls))
        self.assertIn("poll", {event["operation"] for event in seen})
        count = len(evals.calls)
        self.assertEqual(self.run_eval(evals), result)
        self.assertEqual(len(evals.calls), count)

    def test_unsettled_is_returned_not_resubmitted(self):
        evals = FakeEvals([], statuses=["in_progress"])
        result = self.run_eval(evals, attempts=2)
        self.assertEqual((result["settled"], result["status"]), (False, "in_progress"))
        evals.statuses = ["completed"]
        resumed = self.run_eval(evals)
        self.assertEqual((resumed["settled"], resumed["run_id"]), (True, result["run_id"]))
        self.assertEqual([name for name, _ in evals.calls].count("run_create"), 1)

    def test_criteria_readback_drift_and_foreign_rows_refused(self):
        evals = FakeEvals([result_row("o1", "q1", True)])
        original = evals.create

        def drifting(**request):
            created = original(**request)
            evals.definitions["eval_1"]["testing_criteria"] = [dict(CRITERIA[0], evaluator_version="2")]
            return created

        evals.create = drifting
        with self.assertRaises(VerificationError):
            self.run_eval(evals)
        rows = [dict(result_row("o1", "q1", True), run_id="foreign"), result_row("o2", "q2", True)]
        self.tearDown()
        self.setUp()
        with self.assertRaises(VerificationError):
            self.run_eval(FakeEvals(rows))

    def test_request_builders_refuse(self):
        with self.assertRaises(RefusedError):
            agent_eval_definition("n", testing_criteria=[], item_schema={})
        with self.assertRaises(RefusedError):
            agent_eval_definition("n", testing_criteria=CRITERIA * 2, item_schema={})
        with self.assertRaises(RefusedError):
            agent_run_request("e", name="n", agent_name=AGENT, agent_version="1", items=ITEMS, file_id="f")
        with self.assertRaises(RefusedError):
            agent_run_request("e", name="n", agent_name=AGENT, agent_version="1", items=ITEMS, max_items=1)
        with self.assertRaises(RefusedError):
            agent_run_request("e", name="n", agent_name="../x", agent_version="1", file_id="f")
        self.assertEqual(agent_run_request("e", name="n", agent_name=AGENT, agent_version="1", file_id="f")
                         ["data_source"]["source"], {"type": "file_id", "id": "f"})
        with self.assertRaises(RefusedError):
            infer_item_schema([{"query": "a"}, {"query": 1}])
        with self.assertRaises(RefusedError):
            infer_item_schema([])

    def test_run_without_identity_is_outcome_unknown(self):
        client = SimpleNamespace(evals=SimpleNamespace(runs=SimpleNamespace(create=lambda **r: SimpleNamespace(id=""))))
        with self.assertRaises(OutcomeUnknownError):
            submit_run(client, self.ledger, key="r", request={"eval_id": "e"})
        with self.assertRaises(UnresolvedIntentError):
            submit_run(client, self.ledger, key="r", request={"eval_id": "e"})

    def test_summary_counts_errored_missing_and_duplicate(self):
        rows = [result_row("1", "a", True), result_row("2", "b", True, status="failed"), {"id": "3", "results": []}]
        summary = summarize_criteria(rows, criteria_names=["exact"])["exact"]
        self.assertEqual((summary["passed"], summary["errored"], summary["missing"]), (1, 1, 1))
        duplicated = dict(result_row("1", "a", True))
        duplicated["results"] = duplicated["results"] * 2
        with self.assertRaises(VerificationError):
            summarize_criteria([duplicated], criteria_names=["exact"])


GRADER = "def grade(sample, item):\n    return 1.0 if sample['output_text'] == item['ground_truth'] else 0.0\n"
SCHEMA = {"type": "object", "properties": {"sample": {"type": "object"}, "item": {"type": "object"}}}


class FakeEvaluators:
    def __init__(self, drift=False):
        self.store, self.calls, self.drift = {}, [], drift

    def create_version(self, name, evaluator_version):
        self.calls.append(("create_version", name))
        body = dict(evaluator_version, name=name, version="1")
        if self.drift:
            body["definition"] = dict(body["definition"], code_text="def grade(s, i):\n    return 1\n")
        self.store[(name, "1")] = body
        return Model(body)

    def get_version(self, name, version):
        return Model(self.store[(name, version)])


class EvaluatorTests(Base):
    def definition(self):
        return code_evaluator_definition(GRADER, metric="exact", data_schema=SCHEMA, display_name="Exact")

    def test_register_once_and_read_back(self):
        project = SimpleNamespace(beta=SimpleNamespace(evaluators=FakeEvaluators()))
        result = register_code_evaluator(project, self.ledger, name="exact-match", definition=self.definition())
        self.assertEqual(result["version"], "1")
        self.assertEqual(register_code_evaluator(project, self.ledger, name="exact-match",
                                                 definition=self.definition())["version"], "1")
        self.assertEqual(len(project.beta.evaluators.calls), 1)
        metric = self.definition()["definition"]["metrics"]["exact"]
        self.assertTrue(metric["is_primary"])

    def test_readback_drift_and_bad_source_refused(self):
        project = SimpleNamespace(beta=SimpleNamespace(evaluators=FakeEvaluators(drift=True)))
        with self.assertRaises(VerificationError):
            register_code_evaluator(project, self.ledger, name="exact-match", definition=self.definition())
        with self.assertRaises(RefusedError):
            code_evaluator_definition("x = 1", metric="m", data_schema={}, display_name="d")
        with self.assertRaises(RefusedError):
            register_code_evaluator(project, self.ledger, name="bad/name", definition=self.definition())

    def test_local_canary(self):
        cases = [{"sample": {"output_text": "a"}, "item": {"ground_truth": "a"}, "expected": 1.0},
                 {"sample": {"output_text": "b"}, "item": {"ground_truth": "a"}, "expected": 0.0}]
        self.assertTrue(local_canary(GRADER, cases)["passed"])
        with self.assertRaises(VerificationError):
            local_canary(GRADER, [dict(cases[1], expected=1.0)])
        with self.assertRaises(RefusedError):
            local_canary("def other():\n    pass\n", cases)

    def canary(self, scores):
        rows = [{"id": f"o{i}", "eval_id": "eval_1", "run_id": "run_1", "status": "completed", "error": None,
                 "datasource_item": {"sample.output_text": text},
                 "results": [{"name": "exact", "metric": "exact", "type": "azure_ai_evaluator", "status": "completed",
                              "score": score}]} for i, (text, score) in enumerate(scores)]
        cases = [{"item": {"sample.output_text": "right", "ground_truth": "right"}, "expected": 1.0},
                 {"item": {"sample.output_text": "wrong", "ground_truth": "right"}, "expected": 0.0}]
        return run_code_evaluator_canary(
            SimpleNamespace(evals=FakeEvals(rows)), self.ledger, key="c1", evaluator_name="exact-match",
            evaluator_version="1", criterion_name="exact", item_schema={"type": "object"},
            data_mapping={"response": "{{item.sample.output_text}}"}, cases=cases, match_field="sample.output_text",
            sleep=self.clock.sleep, clock=self.clock)

    def test_native_canary_passes_and_fails(self):
        result = self.canary([("right", 1.0), ("wrong", 0.0)])
        self.assertTrue(result["passed"])
        self.tearDown()
        self.setUp()
        with self.assertRaises(VerificationError):
            self.canary([("right", 1.0), ("wrong", 1.0)])
        self.assertFalse(self.ledger.read("evaluator-canary-c1-result.json")["passed"])


def job_state(status="succeeded", candidates=None, baseline="base"):
    default = [{"candidate_id": "base", "eval_id": "e1", "eval_run_id": "r1", "avg_score": 0.5, "avg_tokens": 10},
               {"candidate_id": "cand1", "eval_id": "e2", "eval_run_id": "r2", "avg_score": 0.7, "avg_tokens": 12}]
    return Model(id="job_1", status=status, error=None,
                 result={"baseline": baseline, "best": "cand1", "candidates": default if candidates is None else candidates})


class FakeOptimizeAgents:
    def __init__(self, job_id="job_1", states=None):
        self.job_id, self.calls = job_id, []
        self.states = list(states or [job_state()])

    def begin_create_optimization_job(self, job, operation_id, polling):
        self.calls.append(("create", job, operation_id, polling))
        return SimpleNamespace(details={"job_id": self.job_id})

    def get_optimization_job(self, job_id):
        self.calls.append(("get", job_id))
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class OptimizeTests(Base):
    def job(self, **kwargs):
        return optimization_job(AGENT, "3", train_items=[{"query": "q", "ground_truth": "a"}],
                                validation_items=[{"query": "v"}], evaluators=[{"name": "ev", "version": 1}],
                                optimization_model="gpt", max_candidates=2, **kwargs)

    def test_wire_shaped_job(self):
        job = self.job(max_stalls=2, eval_model="judge", optimization_config={"system_prompt": "p"})
        inputs = job["inputs"]
        self.assertEqual(inputs["agent"], {"agent_name": AGENT, "agent_version": "3"})
        self.assertEqual(inputs["train_dataset"], {"type": "inline", "items": [{"query": "q", "ground_truth": "a"}]})
        self.assertEqual(inputs["evaluators"], [{"name": "ev", "version": "1"}])
        self.assertEqual(inputs["options"]["max_stalls"], 2)
        self.assertNotIn("evaluation_level", json.dumps(job))
        self.assertNotIn("dataset_items", json.dumps(job))

    def test_job_refusals(self):
        with self.assertRaises(RefusedError):
            self.job(extra_options={"evaluation_level": "turn"})
        for kwargs in ({"train_items": {"dataset_items": []}}, {"train_items": [{"prompt": "x"}]},
                       {"train_items": []}, {"evaluators": []}, {"max_candidates": 0}):
            base = dict(train_items=[{"query": "q"}], validation_items=[{"query": "v"}],
                        evaluators=[{"name": "ev", "version": "1"}], optimization_model="gpt", max_candidates=1)
            base.update(kwargs)
            with self.assertRaises(RefusedError):
                optimization_job(AGENT, "1", **base)

    def test_submit_once_then_wait_and_list(self):
        agents = FakeOptimizeAgents(states=[job_state("running"), job_state()])
        project = SimpleNamespace(beta=SimpleNamespace(agents=agents))
        submitted = submit_optimization(project, self.ledger, key="o1", job=self.job(), operation_id="op-1")
        self.assertEqual((submitted["job_id"], submitted["operation_id"]), ("job_1", "op-1"))
        self.assertFalse(agents.calls[0][3])
        self.assertEqual(submit_optimization(project, self.ledger, key="o1", job=self.job())["job_id"], "job_1")
        self.assertEqual([call[0] for call in agents.calls].count("create"), 1)
        seen = []
        polled = wait_optimization(project, job_id="job_1", interval=1, sleep=self.clock.sleep, clock=self.clock,
                                   on_event=seen.append)
        self.assertTrue(polled.settled)
        listing = list_candidates(polled.value)
        self.assertEqual([(c["candidate_id"], c["is_baseline"]) for c in listing["candidates"]],
                         [("base", True), ("cand1", False)])
        self.assertEqual((listing["generated"], listing["candidates"][1]["generation"]), (1, None))
        self.assertTrue(seen)

    def test_submit_without_job_id_and_unsettled_wait(self):
        project = SimpleNamespace(beta=SimpleNamespace(agents=FakeOptimizeAgents(job_id=None)))
        with self.assertRaises(OutcomeUnknownError):
            submit_optimization(project, self.ledger, key="o2", job=self.job())
        with self.assertRaises(UnresolvedIntentError):
            submit_optimization(project, self.ledger, key="o2", job=self.job())
        running = SimpleNamespace(beta=SimpleNamespace(agents=FakeOptimizeAgents(states=[job_state("running")])))
        polled = wait_optimization(running, job_id="job_1", interval=1, attempts=3, sleep=self.clock.sleep,
                                   clock=self.clock)
        self.assertFalse(polled.settled)
        foreign = SimpleNamespace(beta=SimpleNamespace(agents=FakeOptimizeAgents(states=[Model(id="other")])))
        with self.assertRaises(VerificationError):
            wait_optimization(foreign, job_id="job_1", interval=1, attempts=1)

    def test_candidate_refusals(self):
        duplicate = [{"candidate_id": "base", "eval_id": "e", "eval_run_id": "r", "avg_score": 1, "avg_tokens": 1}] * 2
        nan = [{"candidate_id": "base", "eval_id": "e", "eval_run_id": "r", "avg_score": float("nan"), "avg_tokens": 1}]
        for job in (job_state("failed"), job_state(candidates=[]), job_state(candidates=duplicate),
                    job_state(candidates=nan), job_state(baseline="missing"), job_state(candidates=duplicate[:1])):
            with self.assertRaises(VerificationError):
                list_candidates(job)
        self.assertEqual(list_candidates(job_state(candidates=duplicate[:1]), require_generated=False)["generated"], 0)

    def test_resolve_candidate_config(self):
        requests = []

        def project_with(status, payload):
            def send_request(request, **kwargs):
                requests.append((request, kwargs))
                return SimpleNamespace(status_code=status, read=lambda: payload)
            return SimpleNamespace(send_request=send_request)

        factory = lambda method, url: (method, url)
        config = resolve_candidate_config(project_with(200, b'{"instructions": "x"}'), endpoint="https://p/",
                                          job_id="job_1", candidate_id="cand1", request_factory=factory)
        self.assertEqual(config, {"instructions": "x"})
        self.assertEqual(requests[0][0], ("GET", "https://p/agent_optimization_jobs/job_1/candidates/cand1/config"
                                          "?api-version=2025-11-15-preview"))
        for status, payload, error in ((404, b"{}", VerificationError), (200, b'{"secret": 1}', VerificationError),
                                       (200, b"[]", VerificationError), (200, b"{" + b" " * 40 + b"}", BoundExceededError)):
            with self.assertRaises(error):
                resolve_candidate_config(project_with(status, payload), endpoint="https://p", job_id="job_1",
                                         candidate_id="cand1", request_factory=factory, max_bytes=30)
        with self.assertRaises(RefusedError):
            resolve_candidate_config(project_with(200, b"{}"), endpoint="https://p", job_id="../x",
                                     candidate_id="c", request_factory=factory)


class TraceTests(Base):
    CALL = {"type": "function_call", "call_id": "c1", "name": "count_words", "arguments": '{"text": "a b"}',
            "status": "completed"}
    OUTPUT = {"type": "function_call_output", "call_id": "c1", "output": '{"words": 2}'}

    def test_native_items_from_stored_response(self):
        response = ResponseModel(id="r", output=[self.CALL, self.OUTPUT, {"type": "message", "content": []}])
        [record] = tool_calls(response, expected=["count_words"])
        self.assertEqual({key: record[key] for key in ("call_id", "name", "arguments", "output", "status")},
                         {"call_id": "c1", "name": "count_words", "arguments": {"text": "a b"},
                          "output": '{"words": 2}', "status": "completed"})
        self.assertEqual((record["error_code"], record["duration_ms"], record["sources"]), (None, None, ["output"]))

    def test_metadata_fallback_fills_timing_and_failure(self):
        entry = {"call_id": "c1", "name": "count_words", "status": "error", "error_code": "ValueError",
                 "started_at": "2026-09-24T00:00:00.000Z", "ended_at": "2026-09-24T00:00:00.010Z", "duration_ms": 10.0}
        response = {"output": [self.CALL, self.OUTPUT], "metadata": {"tool_call.c1": json.dumps(entry), "other": "x"}}
        [record] = tool_calls(response, metadata_prefix="tool_call.")
        self.assertEqual((record["status"], record["error_code"], record["duration_ms"]), ("error", "ValueError", 10.0))
        self.assertEqual(record["started_at"], entry["started_at"])
        self.assertEqual(record["sources"], ["output", "metadata"])
        [only] = tool_calls({"output": [], "metadata": {"tool_call.c9": json.dumps(dict(entry, call_id="c9"))}},
                            metadata_prefix="tool_call.", expected=["count_words"])
        self.assertEqual(only["call_id"], "c9")

    def test_streamed_invoke_result_gives_timing(self):
        client = FakeOpenAI()
        done = ResponseModel(id="resp_s", status="completed", output=[self.CALL, self.OUTPUT])
        client.responses.stream_events = [Event(type="response.output_item.added", item=self.CALL),
                                          Event(type="response.output_item.done", item=self.CALL),
                                          Event(type="response.completed", response=done)]
        result = invoke(client, self.ledger, key="s", agent_name=AGENT, version="1", input="q", stream=True,
                        clock=Clock(step=0.5))
        [record] = tool_calls(result)
        self.assertEqual(record["duration_ms"], 500.0)
        self.assertEqual(record["sources"], ["output", "stream"])

    def test_hosted_events(self):
        events = [{"kind": "tool.call.ready", "data": {"call_id": "c2", "name": "t", "arguments": {"x": 1}}},
                  {"kind": "tool.started", "data": {"call_id": "c2", "name": "t"}, "timestamp": 1.0},
                  {"kind": "tool.failed", "data": {"call_id": "c2", "name": "t", "code": "timeout"}, "timestamp": 1.25}]
        [record] = tool_calls(None, events=events)
        self.assertEqual((record["status"], record["error_code"], record["duration_ms"]), ("failed", "timeout", 250.0))

    def test_refusals(self):
        with self.assertRaises(VerificationError) as caught:
            tool_calls({"output": [self.CALL]}, expected=["count_words", "describe_unit"])
        self.assertEqual(caught.exception.code, "tool_call_missing")
        with self.assertRaises(VerificationError):
            tool_calls({"output": [self.CALL, dict(self.CALL, type="function_call_output", name=None)]},
                       events=[{"call_id": "c1", "name": "other"}])
        with self.assertRaises(VerificationError):
            tool_calls({"output": [self.CALL, self.CALL]})
        with self.assertRaises(VerificationError):
            tool_calls({"output": [], "metadata": {"tool_call.c1": "not-json"}}, metadata_prefix="tool_call.")
        with self.assertRaises(VerificationError):
            tool_calls({"output": []}, metadata_key="tool_events")
        with self.assertRaises(VerificationError):
            tool_calls({"output": [dict(self.CALL, call_id="")]})
        with self.assertRaises(BoundExceededError):
            tool_calls({"output": [dict(self.CALL, call_id=f"c{i}") for i in range(3)]}, max_calls=2)


if __name__ == "__main__":
    unittest.main()
