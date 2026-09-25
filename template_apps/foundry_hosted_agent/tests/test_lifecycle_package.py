"""External agent package through the whole lifecycle over fakes: package build context, journeys with tool records,
native eval, evaluator canary, optimization, frozen selection, promoted redeploy and CLI refusals."""

import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import lifecycle
from fakes import MODEL, VALID_ENV, FakeAz, FakeHttp, FakeOpenAI, FakeProject
from foundry_ops.core import RefusedError, VerificationError, sha256_hex

LIBRARIES = Path(os.environ.get("AGENTCRAFT_LIBRARIES") or lifecycle.REPO / "libraries")
ACTIONS = list(lifecycle.CLOUD_ACTIONS)
NO_SLEEP = {"sleep": lambda seconds: None}
CONFIG = f"""prompts_dir: prompts
agents:
  default: pkg-agent
  pkg-agent:
    name: pkg-agent
    description: Package fixture with two tools.
    model: {MODEL}
    instructions:
      - agent.md
    tools:
      - quote_tools:lookup_zone
      - quote_tools:quote_parcel
"""
TOOLS = '''class ZoneError(LookupError):
    error_code = "E_ZONE"


def lookup_zone(zone: str) -> dict:
    """Rate for a zone."""
    if zone != "Z1":
        raise ZoneError("unknown zone")
    return {"rate": 3}


def quote_parcel(grams: int, rate: int) -> dict:
    """Price a parcel."""
    return {"cents": grams * rate}
'''
OK_INPUT, STREAM_INPUT, FAIL_INPUT = "price 2 kg to Z1", "stream price 1 kg to Z1", "price 1 kg to Z9"
OK_TOOLS = [("lookup_zone", "ok", None), ("quote_parcel", "ok", None)]
SCENARIOS = {OK_INPUT: OK_TOOLS, STREAM_INPUT: OK_TOOLS, FAIL_INPUT: [("lookup_zone", "error", "E_ZONE")]}
JOURNEYS = {"journeys": [
    {"id": "J1", "input": OK_INPUT, "stream": False, "expected_answer": "DONE",
     "expected_tools": [{"name": "lookup_zone", "status": "ok"}, {"name": "quote_parcel", "status": "ok"}]},
    {"id": "J2", "input": STREAM_INPUT, "stream": True,
     "expected_tools": [{"name": "lookup_zone", "status": "ok"}, {"name": "quote_parcel", "status": "ok"}]},
    {"id": "J3", "input": FAIL_INPUT, "stream": False,
     "expected_tools": [{"name": "lookup_zone", "status": "error", "error_code": "E_ZONE"}]}]}
RULE = {"status": "frozen", "score": "avg_score", "eligibility": "strictly_above_baseline",
        "tie_break": "earliest_observation", "fallback": "baseline",
        "demonstration": {"allowed": True, "label": "demonstration"}}
GRADE = "def grade(sample, item):\n    return 1.0 if item['sample.output_text'].strip() == item['ground_truth'] else 0.0\n"
CANARIES = {"canaries": [
    {"name": "positive", "item": {"ground_truth": "A", "sample.output_text": " A\n"}, "expected": 1.0},
    {"name": "wrong", "item": {"ground_truth": "A", "sample.output_text": "B"}, "expected": 0.0}]}


def env_text(values):
    return "".join(f"{key}={value}\n" for key, value in values.items())


def write_package(root, files=None):
    root.mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "configuration.yaml").write_text(CONFIG)
    (root / "prompts/agent.md").write_text("Answer with tools.\n")
    (root / "quote_tools.py").write_text(TOOLS)
    for name, content in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content if isinstance(content, bytes) else content.encode())


class Repo:
    """Temporary repository: package under pkg/agent, caller inputs, env dir and records root."""

    def __init__(self, directory):
        self.root = Path(directory)
        self.env_dir, self.records, self.inputs = self.root / "env", self.root / "records", self.root / "inputs"
        self.env_dir.mkdir()
        self.inputs.mkdir()
        self.package = self.root / "pkg/agent"
        write_package(self.package)

    def file(self, name, value):
        path = self.inputs / name
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def manifest(self, environment="dev", series="pkg-v1", pins=None, package_dir="pkg/agent", **extra):
        env = self.env_dir / f"{environment}.env"
        env.write_text(env_text(VALID_ENV))
        value = {"schema_version": 1, "purpose": "foundry-hosted-agent", "series": series, "agent": "pkg-agent",
                 "actions": ACTIONS, "env_sha256": sha256_hex(env.read_bytes()), "previous_version": None,
                 "previous_image": None,
                 "inputs": {kind: sha256_hex(Path(path).read_bytes()) for kind, path in (pins or {}).items()},
                 **({"package_dir": package_dir} if package_dir is not None else {}), **extra}
        path = self.env_dir / f"{environment}.run.json"
        path.write_text(json.dumps(value, sort_keys=True))
        return sha256_hex(path.read_bytes())

    def context(self, sha, environment="dev", action="build"):
        return lifecycle.load_context(environment, sha, action, libraries=LIBRARIES, env_dir=self.env_dir,
                                      records=self.records, repo=self.root)


class ToolResponses:
    """Responses shaped like the template runtime: native function_call items plus `tool_call.<n>` metadata."""

    def __init__(self, store, log, scenarios, omit_metadata=False):
        self.store, self.log, self.scenarios, self.omit_metadata = store, log, scenarios, omit_metadata
        self.metadata, self.requests, self.answer = {}, [], "DONE"

    def _build(self, text):
        output, metadata = [], dict(self.metadata)
        for index, (name, status, code) in enumerate(self.scenarios.get(text, []), 1):
            call_id = f"call_{index}"
            result = {"error": {"code": code, "message": "declared"}} if status == "error" else {"ok": True}
            output += [{"type": "function_call", "id": f"fc_{index}", "call_id": call_id, "name": name,
                        "arguments": "{}", "status": "completed"},
                       {"type": "function_call_output", "id": f"fco_{index}", "call_id": call_id,
                        "output": json.dumps(result), "status": "completed"}]
            if not self.omit_metadata:
                metadata[f"tool_call.{index}"] = json.dumps(
                    {"call_id": call_id, "duration_ms": 1.5, "ended_at": "2026-09-24T00:00:01.000Z", "error_code": code,
                     "name": name, "started_at": "2026-09-24T00:00:00.000Z", "status": status},
                    sort_keys=True, separators=(",", ":"))
        output.append({"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": self.answer}]})
        return output, metadata

    def create(self, **request):
        self.log.append("responses.create")
        self.requests.append(request)
        response_id = f"resp_{len(self.requests)}"
        output, metadata = self._build(request["input"])
        response = {"id": response_id, "status": "completed", "metadata": metadata, "output": output}
        self.store[response_id] = copy.deepcopy(response)
        if not request["stream"]:
            return SimpleNamespace(model_dump=lambda mode="json": copy.deepcopy(response), output_text=self.answer)
        events = [SimpleNamespace(type="response.created", response={"id": response_id, "status": "in_progress"})]
        for item in output[:-1]:
            events += [SimpleNamespace(type="response.output_item.added", item={**item, "status": "in_progress"}),
                       SimpleNamespace(type="response.output_item.done", item=item)]
        events += [SimpleNamespace(type="response.output_text.delta", delta=self.answer, item_id="msg"),
                   SimpleNamespace(type="response.completed", response=copy.deepcopy(response))]
        return contextlib.nullcontext(events)


class ToolOpenAI(FakeOpenAI):
    def __init__(self, store, log, scenarios=SCENARIOS, **options):
        self.responses = ToolResponses(store, log, scenarios, **options)


def model(**fields):
    return SimpleNamespace(**fields, model_dump=lambda mode="json": copy.deepcopy(fields))


def grade(item):
    if "sample.output_text" in item:
        return 1.0 if item["sample.output_text"].strip() == item["ground_truth"] else 0.0
    return 1.0 if item.get("ok") else 0.0


class FakeRuns:
    def __init__(self, evals):
        self.evals, self.rows, self.created = evals, {}, 0
        self.output_items = SimpleNamespace(list=self.list_items)

    def create(self, **request):
        self.created += 1
        run_id = f"run_{self.created}"
        criteria = self.evals.definitions[request["eval_id"]]["testing_criteria"]
        self.rows[run_id] = [
            {"id": f"row_{run_id}_{index}", "eval_id": request["eval_id"], "run_id": run_id, "status": "completed",
             "datasource_item": entry["item"],
             "results": [{"name": criterion["name"], "metric": criterion["name"], "type": criterion["type"],
                          "status": "completed", "score": grade(entry["item"]), "passed": grade(entry["item"]) >= 1}
                         for criterion in criteria]}
            for index, entry in enumerate(request["data_source"]["source"]["content"])]
        self.evals.run_eval[run_id] = request["eval_id"]
        return model(id=run_id)

    def retrieve(self, run_id, eval_id):
        return model(id=run_id, eval_id=eval_id, status="completed", error=None,
                     result_counts={"total": len(self.rows[run_id])}, per_testing_criteria_results=[])

    def list_items(self, eval_id, run_id, limit):
        page = SimpleNamespace(data=[model(**row) for row in self.rows[run_id]], last_id=None)
        return SimpleNamespace(iter_pages=lambda: [page])


class FakeEvals:
    def __init__(self):
        self.definitions, self.run_eval = {}, {}
        self.runs = FakeRuns(self)

    def create(self, **request):
        eval_id = f"eval_{len(self.definitions) + 1}"
        self.definitions[eval_id] = request
        return model(id=eval_id)

    def retrieve(self, eval_id):
        return {"id": eval_id, "testing_criteria": copy.deepcopy(self.definitions[eval_id]["testing_criteria"])}


class FakeEvaluators:
    def __init__(self):
        self.versions = {}

    def create_version(self, name, evaluator_version):
        self.versions[name] = {"name": name, "version": "1", **copy.deepcopy(evaluator_version)}
        return dict(self.versions[name])

    def get_version(self, name, version):
        return copy.deepcopy(self.versions[name])


class FakeOptimizer:
    def __init__(self, scores):
        self.scores, self.jobs = scores, []

    def begin_create_optimization_job(self, job, operation_id, polling):
        self.jobs.append(copy.deepcopy(job))
        return SimpleNamespace(details={"job_id": "job1"})

    def get_optimization_job(self, job_id):
        candidates = [{"candidate_id": candidate, "eval_id": "e", "eval_run_id": f"r_{candidate}", "avg_score": score,
                       "avg_tokens": 10} for candidate, score in self.scores.items()]
        return {"id": job_id, "status": "succeeded", "error": None,
                "result": {"baseline": "base", "best": None, "candidates": candidates}}


class NativeProject(FakeProject):
    def __init__(self, log, scores=None):
        super().__init__(log)
        self.beta = SimpleNamespace(evaluators=FakeEvaluators(),
                                    agents=FakeOptimizer(scores or {"base": 0.5, "c1": 0.7, "c2": 0.7}))
        self.fetched = []

    def send_request(self, request, connection_timeout, read_timeout):
        candidate = request[1].split("/candidates/")[1].split("/")[0]
        self.fetched.append(candidate)
        body = json.dumps({"instructions": f"  prompt for {candidate}\n", "model": MODEL}).encode()
        return SimpleNamespace(status_code=200, read=lambda: body)


def request_factory(method, url):
    return method, url


class PackageSourceTests(unittest.TestCase):
    def test_external_package_replaces_example_in_build_context(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            write_package(repo.root / "copy", {"__pycache__/quote_tools.cpython-312.pyc": b"\x00"})
            inputs = lifecycle.source_inputs(LIBRARIES, repo.package)
            manifest = lifecycle.source_manifest(inputs)
            moved = lifecycle.source_manifest(lifecycle.source_inputs(LIBRARIES, repo.root / "copy"))
            tools = lifecycle.package_config(repo.package)["tools"]
        names = set(inputs)
        self.assertTrue({"package/configuration.yaml", "package/prompts/agent.md", "package/quote_tools.py",
                         "app/main.py"} <= names)
        self.assertFalse(names & {"package/agent_tools.py", "app/agent_tools.py", "app/configuration.yaml"})
        self.assertFalse([name for name in names if "pycache" in name or name.startswith(("inputs/", "env/"))])
        self.assertEqual(manifest["package_sha256"], moved["package_sha256"])
        self.assertEqual(manifest["package_sha256"], sha256_hex(json.dumps(
            {"configuration.yaml": sha256_hex(CONFIG.encode()), "prompts/agent.md": sha256_hex(b"Answer with tools.\n"),
             "quote_tools.py": sha256_hex(TOOLS.encode())}, sort_keys=True).encode()))
        label = lifecycle.release_label(manifest)
        self.assertEqual(label, f"src-{manifest['sha256'][:24]}-pkg-{manifest['package_sha256'][:16]}")
        self.assertEqual(tools, ["quote_tools:lookup_zone", "quote_tools:quote_parcel"])

    def test_package_outside_allowlist_or_secret_shaped_refused(self):
        cases = [({"data.csv": "a,b"}, "package_file"), ({".env": "A=1"}, "package_file"),
                 ({"prompts/notes.json": "{}"}, "package_file"), ({"dataset/train.jsonl": "{}"}, "package_file"),
                 ({"bad-name.py": "x = 1"}, "package_file"),
                 ({"keys.py": 'PEM = "-----BEGIN PRIVATE KEY-----"'}, "package_secret"),
                 ({"prompts/extra.md": "AccountKey=***REMOVED***"}, "package_secret"),
                 ({"creds.py": 'password = "hunter2hunter2"'}, "package_secret"),
                 ({"blob.py": b"\xff\xfe\x00"}, "package_binary")]
        for files, code in cases:
            with self.subTest(files=list(files)), tempfile.TemporaryDirectory() as directory:
                write_package(Path(directory) / "p", files)
                with self.assertRaises(RefusedError) as refused:
                    lifecycle.package_inputs(Path(directory) / "p")
                self.assertEqual(refused.exception.code, code)
                for content in files.values():
                    if isinstance(content, str) and code == "package_secret":
                        self.assertNotIn(content, str(refused.exception))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "p"
            write_package(root)
            (root / "link.py").symlink_to(root / "quote_tools.py")
            with self.assertRaises(RefusedError) as refused:
                lifecycle.package_inputs(root)
            self.assertEqual(refused.exception.code, "package_symlink")
        for config, code in ((CONFIG.replace("quote_tools:quote_parcel", "os:getcwd"), "package_tool"),
                             (CONFIG.replace("quote_tools:quote_parcel", "quote_tools:../x"), "package_tool"),
                             ("agents: []\n", "package_config")):
            with self.subTest(code=code, config=config[-30:]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "p"
                write_package(root)
                (root / "configuration.yaml").write_text(config)
                with self.assertRaises(RefusedError) as refused:
                    lifecycle.package_config(root)
                self.assertEqual(refused.exception.code, code)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "p"
            write_package(root)
            (root / "configuration.yaml").unlink()
            with self.assertRaises(RefusedError) as refused:
                lifecycle.package_inputs(root)
            self.assertEqual(refused.exception.code, "package_config")

    def test_manifest_package_dir_and_inputs_refused_before_evidence(self):
        for extra, code in (({"package_dir": "/abs"}, "manifest_package"), ({"package_dir": "../x"}, "manifest_package"),
                            ({"package_dir": "pkg/missing"}, "manifest_package"),
                            ({"inputs": {"unknown": "0" * 64}}, "manifest_inputs"),
                            ({"inputs": {"journeys": "not-a-digest"}}, "manifest_inputs")):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                repo = Repo(directory)
                sha = repo.manifest(**{"package_dir": None, **extra})
                with self.assertRaises(RefusedError) as refused:
                    repo.context(sha)
                self.assertEqual(refused.exception.code, code)
                self.assertFalse(repo.records.exists())


class Harness(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Repo(self.directory.name)
        self.log, self.store = [], {}
        self.az, self.project = FakeAz(), NativeProject(self.log)
        self.http, self.evals = FakeHttp(self.store), SimpleNamespace(evals=FakeEvals())
        tests = patch.object(lifecycle, "run_offline_tests", return_value={"tests": 0})
        tests.start()
        self.addCleanup(tests.stop)
        self.addCleanup(self.directory.cleanup)

    def deployed(self, pins=None, scenarios=SCENARIOS, **options):
        ctx = self.repo.context(self.repo.manifest(pins=pins))
        lifecycle.build(ctx, self.az, self.project)
        deployed = lifecycle.deploy(ctx, self.project, **NO_SLEEP)
        openai = ToolOpenAI(self.store, self.log, scenarios, **options)
        openai.responses.metadata = lifecycle.expected_identity(ctx, deployed)
        return ctx, deployed, openai

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(RefusedError) as refused:
            call(*args, **kwargs)
        self.assertEqual(refused.exception.code, code)


class PackageLifecycleTests(Harness):
    def test_package_build_deploy_journeys_streaming_and_tool_records(self):
        journeys = self.repo.file("journeys.json", JOURNEYS)
        ctx = self.repo.context(self.repo.manifest(pins={"journeys": journeys}))
        self.assertEqual(lifecycle.preflight(ctx, self.az, self.project)["package"]["dir"], "pkg/agent")
        built = lifecycle.build(ctx, self.az, self.project)
        self.assertIn("package/quote_tools.py", self.az.staged)
        self.assertFalse([name for name in self.az.staged if name.startswith(("inputs/", "env/", "records/"))
                          or name in ("package/agent_tools.py", "app/configuration.yaml")])
        self.assertIn(built["package_sha256"][:16], self.az.tag)
        deployed = lifecycle.deploy(ctx, self.project, **NO_SLEEP)
        self.assertEqual(deployed["metadata"]["package_sha256"], built["package_sha256"])
        openai = ToolOpenAI(self.store, self.log)
        openai.responses.metadata = lifecycle.expected_identity(ctx, deployed)

        invoked = lifecycle.invoke_journeys(ctx, openai, journeys)
        self.assertEqual([(entry["id"], entry["stream"]) for entry in invoked], [("J1", False), ("J2", True), ("J3", False)])
        self.assertEqual(lifecycle.invoke_journeys(ctx, openai, journeys), invoked)
        self.assertEqual(self.log.count("responses.create"), 3)
        self.assertEqual([request["stream"] for request in openai.responses.requests], [False, True, False])

        verified = lifecycle.verify(ctx, self.project, openai, "t", http_client=self.http, journeys=journeys)
        self.assertEqual(verified["identity"]["package_sha256"], built["package_sha256"])
        by_id = {entry["id"]: entry for entry in verified["invocations"]}
        self.assertTrue(by_id["J1"]["answer_match"])
        failed = by_id["J3"]["tool_calls"][0]
        self.assertEqual((failed["name"], failed["status"], failed["error_code"], failed["duration_ms"]),
                         ("lookup_zone", "error", "E_ZONE", 1.5))
        self.assertEqual([record["call_id"] for record in by_id["J2"]["tool_calls"]], ["call_1", "call_2"])

    def test_verify_refuses_missing_or_mismatched_tool_records(self):
        cases = ((OK_TOOLS[:1], {}, VerificationError, "tool_call_missing"),
                 ([("lookup_zone", "error", "E_ZONE"), OK_TOOLS[1]], {}, VerificationError, "tool_call_mismatch"),
                 ([("lookup_zone", "ok", None), ("quote_parcel", "error", "E_OTHER")], {}, VerificationError,
                  "tool_call_mismatch"),
                 (OK_TOOLS, {"omit_metadata": True}, VerificationError, "tool_record_incomplete"))
        for tools, options, error, code in cases:
            with self.subTest(code=code, tools=tools), tempfile.TemporaryDirectory() as directory:
                self.repo, self.store = Repo(directory), {}
                self.http = FakeHttp(self.store)
                self.project = NativeProject(self.log)
                journeys = self.repo.file("journeys.json", {"journeys": JOURNEYS["journeys"][:1]})
                ctx, _, openai = self.deployed({"journeys": journeys}, {OK_INPUT: tools}, **options)
                lifecycle.invoke_journeys(ctx, openai, journeys)
                with self.assertRaises(error) as refused:
                    lifecycle.verify(ctx, self.project, openai, "t", http_client=self.http, journeys=journeys)
                self.assertEqual(refused.exception.code, code)

    def test_journey_files_must_be_pinned_well_formed_and_invoked(self):
        journeys = self.repo.file("journeys.json", JOURNEYS)
        ctx, _, openai = self.deployed({"journeys": journeys})
        self.refused("journey_not_invoked", lifecycle.verify, ctx, self.project, openai, "t",
                     http_client=self.http, journeys=journeys)
        journeys.write_text(json.dumps({"journeys": [{**JOURNEYS["journeys"][0], "stream": "yes"}]}))
        self.refused("input_pin", lifecycle.invoke_journeys, ctx, openai, journeys)
        unpinned = self.repo.file("other.json", JOURNEYS)
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            ctx = repo.context(repo.manifest())
            self.refused("input_path", lifecycle.invoke_journeys, ctx, openai, unpinned)
            inside = repo.file("journeys.json", JOURNEYS)
            self.refused("input_unpinned", lifecycle.invoke_journeys, ctx, openai, inside)
            self.refused("journeys_missing", lifecycle.invoke_journeys, ctx, openai, None)
        for bad in ({"journeys": []}, {"journeys": [{**JOURNEYS["journeys"][0], "stream": "yes"}]},
                    {"journeys": [{**JOURNEYS["journeys"][2], "expected_tools": [{"name": "x", "status": "error"}]}]},
                    {"journeys": [JOURNEYS["journeys"][0], JOURNEYS["journeys"][0]]}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                repo = Repo(directory)
                path = repo.file("journeys.json", bad)
                ctx = repo.context(repo.manifest(pins={"journeys": path}))
                with self.assertRaises(RefusedError) as refused:
                    lifecycle.load_journeys(ctx, path)
                self.assertIn(refused.exception.code, ("journeys_missing", "journeys_shape"))


class NativeEvaluationTests(Harness):
    def test_evaluate_refuses_missing_criteria_or_items_then_runs_once(self):
        criteria = self.repo.file("criteria.json", {"name": "pkg-eval", "testing_criteria": [
            {"type": "azure_ai_evaluator", "name": "exact", "evaluator_name": "pkg-exact", "data_mapping": {}}]})
        empty_criteria = self.repo.file("empty-criteria.json", {"testing_criteria": []})
        items = self.repo.file("items.jsonl", '{"query": "q1", "ok": true}\n{"query": "q2", "ok": false}\n')
        empty_items = self.repo.file("empty.jsonl", "\n")
        pins = {"criteria": criteria, "items": items}
        ctx, _, _ = self.deployed(pins)
        self.refused("criteria_missing", lifecycle.evaluate, ctx, self.evals, None, items)
        self.refused("items_missing", lifecycle.evaluate, ctx, self.evals, criteria, None)
        ctx2 = self.repo.context(self.repo.manifest(environment="alt", series="pkg-alt",
                                                    pins={"criteria": empty_criteria, "items": empty_items}),
                                 environment="alt")
        self.refused("criteria_missing", lifecycle.evaluate, ctx2, self.evals, empty_criteria, items)
        result = lifecycle.evaluate(ctx, self.evals, criteria, items, **NO_SLEEP)
        self.assertTrue(result["complete"])
        self.assertEqual((result["summary"]["exact"]["passed"], result["summary"]["exact"]["failed"]), (1, 1))
        run = self.evals.evals.runs
        target = self.evals.evals.definitions["eval_1"]
        self.assertEqual(target["name"], "pkg-eval")
        self.assertEqual(lifecycle.evaluate(ctx, self.evals, criteria, items, **NO_SLEEP), result)
        self.assertEqual(run.created, 1)
        self.assertEqual(ctx.observed_inputs["criteria"]["sha256"], sha256_hex(criteria.read_bytes()))

    def test_evaluate_refuses_empty_items(self):
        criteria = self.repo.file("criteria.json", {"testing_criteria": [{"type": "x", "name": "exact"}]})
        empty = self.repo.file("empty.jsonl", "\n")
        ctx, _, _ = self.deployed({"criteria": criteria, "items": empty})
        self.refused("items_missing", lifecycle.evaluate, ctx, self.evals, criteria, empty)

    def test_register_evaluator_with_native_canary(self):
        (self.repo.inputs / "grade.py").write_text(GRADE)
        (self.repo.inputs / "canaries.json").write_text(json.dumps(CANARIES))
        spec = {"name": "pkg-exact", "metric": "exact", "display_name": "Exact", "data_schema": {"type": "object"},
                "code_file": "grade.py", "code_sha256": sha256_hex(GRADE.encode()),
                "canary": {"criterion_name": "exact", "item_schema": {"type": "object"},
                           "data_mapping": {"ground_truth": "{{item.ground_truth}}"},
                           "match_field": "sample.output_text", "cases_file": "canaries.json",
                           "cases_sha256": sha256_hex(json.dumps(CANARIES).encode())}}
        good = self.repo.file("evaluator.json", spec)
        drifted = self.repo.file("drifted.json", {**spec, "code_sha256": "0" * 64})
        flipped = {"canaries": [{**CANARIES["canaries"][0], "expected": 0.0}, CANARIES["canaries"][1]]}
        wrong = self.repo.file("wrong.json", {**spec, "name": "pkg-wrong",
                                              "canary": {**spec["canary"], "cases": flipped["canaries"]}})
        ctx = self.repo.context(self.repo.manifest(pins={"evaluator": good}))
        result = lifecycle.register_evaluator(ctx, self.project, self.evals, good, **NO_SLEEP)
        self.assertEqual((result["evaluator"]["version"], result["canary"]["passed"]), ("1", True))
        self.assertEqual(result["evaluator"]["code_sha256"], sha256_hex(GRADE.encode()))
        for path, environment, error, code in ((drifted, "d", RefusedError, "evaluator_code_pin"),
                                               (wrong, "w", VerificationError, "canary_failed")):
            with self.subTest(code=code):
                other = self.repo.context(self.repo.manifest(environment=environment, series=f"pkg-{environment}",
                                                             pins={"evaluator": path}), environment=environment)
                with self.assertRaises(error) as refused:
                    lifecycle.register_evaluator(other, self.project, self.evals, path, **NO_SLEEP)
                self.assertEqual(refused.exception.code, code)


class OptimizationMixin:
    def files(self):
        rows = '{"query": "q1", "ground_truth": "a1", "case": "ok"}\n{"query": "q2", "ground_truth": "a2"}\n'
        return {"optimization": self.repo.file("optimization.json", {
                    "evaluators": [{"name": "pkg-exact", "version": "1"}], "optimization_model": "opt-model",
                    "max_candidates": 2}),
                "train": self.repo.file("train.jsonl", rows), "validation": self.repo.file("validation.jsonl", rows),
                "selection_rule": self.repo.file("rule.json", RULE)}

    def optimized(self, scores=None):
        files = self.files()
        if scores:
            self.project = NativeProject(self.log, scores)
        ctx, deployed, _ = self.deployed(files)
        result = lifecycle.optimize(ctx, self.project, files["optimization"], files["train"], files["validation"],
                                    request_factory=request_factory, **NO_SLEEP)
        return ctx, files, result


class OptimizationTests(OptimizationMixin, Harness):
    def test_optimize_refuses_missing_items_or_evaluators(self):
        files = self.files()
        no_evaluators = self.repo.file("no-evaluators.json", {"optimization_model": "m", "max_candidates": 1})
        ctx, _, _ = self.deployed({**files, "optimization": no_evaluators})
        self.refused("optimization_missing", lifecycle.optimize, ctx, self.project, None, files["train"],
                     files["validation"])
        self.refused("evaluators_missing", lifecycle.optimize, ctx, self.project, no_evaluators, files["train"],
                     files["validation"])
        self.assertEqual(self.project.beta.agents.jobs, [])

    def test_optimize_retains_every_candidate_and_never_resubmits(self):
        ctx, files, result = self.optimized()
        self.assertEqual([item["candidate_id"] for item in result["candidates"]], ["base", "c1", "c2"])
        self.assertEqual(self.project.fetched, ["base", "c1", "c2"])
        job = self.project.beta.agents.jobs[0]
        self.assertEqual(job["inputs"]["train_dataset"]["items"][0], {"query": "q1", "ground_truth": "a1"})
        again = lifecycle.optimize(ctx, self.project, files["optimization"], files["train"], files["validation"],
                                   request_factory=request_factory, **NO_SLEEP)
        self.assertEqual((len(self.project.beta.agents.jobs), again["job_id"]), (1, "job1"))
        self.refused("train_missing", lifecycle.optimize, ctx, self.project, files["optimization"], None,
                     files["validation"])

    def test_select_applies_frozen_rule(self):
        ctx, files, _ = self.optimized()
        selected = lifecycle.select(ctx, files["selection_rule"])
        self.assertEqual((selected["decision"], selected["candidate_id"], selected["score"]), ("selected", "c1", 0.7))
        self.assertEqual(selected["config_sha256"], sha256_hex(lifecycle._canonical(selected["config"])))
        self.assertEqual(lifecycle.select(ctx, files["selection_rule"])["record"], selected["record"])

    def test_select_refuses_unfrozen_or_unpinned_rule(self):
        files = self.files()
        unfrozen = self.repo.file("unfrozen.json", {**RULE, "status": "draft"})
        changed = self.repo.file("changed.json", {**RULE, "eligibility": "at_least_baseline"})
        ctx, _, _ = self.deployed({**files, "selection_rule": unfrozen})
        self.refused("rule_unfrozen", lifecycle.select, ctx, unfrozen)
        self.refused("input_pin", lifecycle.select, ctx, changed)
        self.refused("selection_rule_missing", lifecycle.select, ctx, None)
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            rule = repo.file("rule.json", RULE)
            other = repo.context(repo.manifest())
            self.refused("input_unpinned", lifecycle.select, other, rule)
            changed = repo.file("changed.json", {**RULE, "eligibility": "at_least_baseline"})
            pinned = repo.context(repo.manifest(environment="p", series="p-v1", pins={"selection_rule": changed}),
                                  environment="p")
            self.refused("rule_unsupported", lifecycle.select, pinned, changed)
            fresh = repo.context(repo.manifest(environment="q", series="q-v1", pins={"selection_rule": rule}),
                                 environment="q")
            self.refused("optimization_missing", lifecycle.select, fresh, rule)

    def test_no_candidate_beats_baseline_keeps_baseline_unless_labelled_demonstration(self):
        ctx, files, _ = self.optimized({"base": 0.8, "c1": 0.8, "c2": 0.6})
        kept = lifecycle.select(ctx, files["selection_rule"])
        self.assertEqual((kept["decision"], kept["candidate_id"], kept["config"]), ("baseline", None, None))
        demo = lifecycle.select(ctx, files["selection_rule"], demonstration=True)
        self.assertEqual((demo["decision"], demo["label"], demo["candidate_id"]), ("demonstration", "demonstration", "c1"))
        closed = self.repo.file("closed.json", {**RULE, "demonstration": {"allowed": False}})
        other = self.repo.context(self.repo.manifest(environment="c", series="pkg-c",
                                                     pins={**files, "selection_rule": closed}), environment="c")
        self.refused("demonstration_refused", lifecycle.select, other, closed, demonstration=True)

    def test_optimize_previous_version_retains_native_rows_and_selects_by_criterion(self):
        files = self.files()
        rule = self.repo.file("criterion-rule.json", {**RULE, "score": "criterion_mean", "criterion": "pkg-exact"})
        self.project = NativeProject(self.log, {"base": 0.9, "c1": 0.1, "c2": 0.2})
        exact = {"base": [0.0, 0.0], "c1": [1.0, None], "c2": [1.0, 1.0]}
        native = {f"r_{candidate}": [
            {"id": f"row_{candidate}_{index}", "eval_id": "e", "run_id": f"r_{candidate}", "status": "completed",
             "datasource_item": {"query": f"q{index + 1}", "ground_truth": f"a{index + 1}",
                                 "sample.output_text": "out"},
             "results": [{"name": "pkg-exact", "status": "completed" if score is not None else "error",
                          "score": score}, {"name": "pkg-graded", "status": "completed", "score": 0.5}]}
            for index, score in enumerate(scores)] for candidate, scores in exact.items()}
        rows_client = SimpleNamespace(evals=SimpleNamespace(runs=SimpleNamespace(output_items=SimpleNamespace(
            list=lambda eval_id, run_id, limit: SimpleNamespace(iter_pages=lambda: [SimpleNamespace(
                data=[model(**row) for row in native[run_id]], last_id=None)])))))
        ctx = self.repo.context(self.repo.manifest(series="pkg-opt-only", previous_version="1",
                                                   pins={**files, "selection_rule": rule}))
        self.refused("stage_missing", lifecycle.optimize, ctx, self.project, files["optimization"], files["train"],
                     files["validation"], eval_client=rows_client, request_factory=request_factory, **NO_SLEEP)
        result = lifecycle.optimize(ctx, self.project, files["optimization"], files["train"], files["validation"],
                                    eval_client=rows_client, previous=True, request_factory=request_factory, **NO_SLEEP)
        self.assertEqual(self.project.beta.agents.jobs[0]["inputs"]["agent"]["agent_version"], "1")
        retained = ctx.ledger.read(result["record"])
        self.assertEqual(retained["validation_count"], 2)
        self.assertEqual(retained["rows"]["c1"][1]["scores"], {"pkg-exact": None, "pkg-graded": 0.5})
        self.assertEqual(retained["rows"]["base"][0]["output_text"], "out")
        selected = lifecycle.select(ctx, rule)
        self.assertEqual((selected["decision"], selected["candidate_id"], selected["score"]), ("selected", "c2", 1.0))
        self.assertEqual([item["score"] for item in selected["candidates"]], [0.5, 1.0])
        self.assertEqual(selected["baseline"]["score"], 0.0)
        self.assertIn("pkg-exact", selected["score_kind"])
        plain = self.repo.context(self.repo.manifest(environment="n", series="pkg-n", pins=files), environment="n")
        self.refused("previous_missing", lifecycle.optimize, plain, self.project, files["optimization"],
                     files["train"], files["validation"], previous=True)

    def test_criterion_rule_needs_rows_and_criterion(self):
        files = self.files()
        rules = [self.repo.file("criterion-rule.json", {**RULE, "score": "criterion_mean", "criterion": "pkg-exact"}),
                 self.repo.file("loose-rule.json", {**RULE, "score": "criterion_mean"}),
                 self.repo.file("extra-rule.json", {**RULE, "criterion": "pkg-exact"})]
        pins = {kind: sha256_hex(Path(path).read_bytes()) for kind, path in files.items()}
        pins["selection_rule"] = [sha256_hex(path.read_bytes()) for path in rules]
        ctx = self.repo.context(self.repo.manifest(inputs=pins))
        lifecycle.build(ctx, self.az, self.project)
        lifecycle.deploy(ctx, self.project, **NO_SLEEP)
        lifecycle.optimize(ctx, self.project, files["optimization"], files["train"], files["validation"],
                           request_factory=request_factory, **NO_SLEEP)
        self.refused("criterion_rows_missing", lifecycle.select, ctx, rules[0])
        for path in rules[1:]:
            with self.subTest(rule=path.name):
                self.refused("rule_unsupported", lifecycle.select, ctx, path)


class PromotionTests(OptimizationMixin, Harness):
    def promoted_series(self, record, previous="1"):
        record_path = Path(record)
        journeys = self.repo.file("opt-journeys.json", JOURNEYS)
        sha = self.repo.manifest(environment="opt", series="pkg-opt-v1", previous_version=previous,
                                 pins={"candidate_record": record_path, "journeys": journeys})
        return self.repo.context(sha, environment="opt", action="deploy"), journeys

    def test_selected_candidate_redeployed_as_overlay_and_reverified(self):
        baseline_ctx, files, _ = self.optimized()
        selected = lifecycle.select(baseline_ctx, files["selection_rule"])
        ctx, journeys = self.promoted_series(selected["record"])
        deployed = lifecycle.deploy(ctx, self.project, candidate_record=selected["record"], **NO_SLEEP)
        self.assertEqual(self.az.count("acr", "build"), 1)
        self.assertEqual(deployed["version"], "2")
        served = json.loads(deployed["definition"]["environment_variables"]["OPTIMIZATION_CONFIG"])
        self.assertEqual(served, {"instructions": "prompt for c1", "model": MODEL})
        metadata = deployed["metadata"]
        self.assertEqual((metadata["promotion"], metadata["optimization_candidate_id"]), ("selected", "c1"))
        self.assertEqual(metadata["optimization_config_sha256"],
                         sha256_hex(json.dumps(served, sort_keys=True).encode()))
        openai = ToolOpenAI(self.store, self.log)
        openai.responses.metadata = lifecycle.expected_identity(ctx, deployed)
        lifecycle.invoke_journeys(ctx, openai, journeys)
        verified = lifecycle.verify(ctx, self.project, openai, "t", http_client=self.http, journeys=journeys)
        self.assertEqual(verified["identity"]["optimization_config_sha256"], metadata["optimization_config_sha256"])
        self.assertIn("environment_variables", verified["version"]["definition"])
        for response in self.store.values():
            response["metadata"].pop("optimization_config_sha256", None)
        with self.assertRaises(VerificationError) as refused:
            lifecycle.verify(ctx, self.project, openai, "t", http_client=self.http, journeys=journeys)
        self.assertEqual(refused.exception.code, "identity_mismatch")

    def test_baseline_decision_and_bad_overlays_refused(self):
        baseline_ctx, files, _ = self.optimized({"base": 0.9, "c1": 0.1, "c2": 0.2})
        kept = lifecycle.select(baseline_ctx, files["selection_rule"])
        ctx, _ = self.promoted_series(kept["record"])
        self.refused("baseline_retained", lifecycle.deploy, ctx, self.project, candidate_record=kept["record"])
        for body, code in (({"instructions": "x", "tools": []}, "overlay_fields"),
                           ({"instructions": "x", "model": "other"}, "overlay_model"),
                           ({"instructions": "  "}, "overlay_instructions")):
            with self.subTest(code=code):
                path = self.repo.file(f"{code}.json", body)
                environment = code.replace("_", "-")
                other = self.repo.context(self.repo.manifest(environment=environment, series=environment,
                                                             previous_version="1", pins={"optimization_config": path}),
                                          environment=environment)
                self.refused(code, lifecycle.deploy, other, self.project, optimization_config=path)
        self.refused("overlay_choice", lifecycle.deploy, ctx, self.project, optimization_config="a",
                     candidate_record="b")

    def test_promoted_series_evaluates_several_pinned_item_sets_and_previous_version(self):
        baseline_ctx, files, _ = self.optimized()
        selected = lifecycle.select(baseline_ctx, files["selection_rule"])
        criteria = self.repo.file("criteria.json", {"testing_criteria": [{"type": "x", "name": "exact"}]})
        first = self.repo.file("first.jsonl", '{"query": "q1", "ok": true}\n')
        second = self.repo.file("second.jsonl", '{"query": "q2", "ok": false}\n')
        unpinned = self.repo.file("third.jsonl", '{"query": "q3", "ok": true}\n')
        pins = {"candidate_record": sha256_hex(Path(selected["record"]).read_bytes()),
                "criteria": sha256_hex(criteria.read_bytes()),
                "items": [sha256_hex(first.read_bytes()), sha256_hex(second.read_bytes())]}
        ctx = self.repo.context(self.repo.manifest(environment="opt", series="pkg-opt-v1", previous_version="1",
                                                   inputs=pins), environment="opt")
        lifecycle.deploy(ctx, self.project, candidate_record=selected["record"], **NO_SLEEP)
        runs = self.evals.evals.runs
        new = lifecycle.evaluate(ctx, self.evals, criteria, first, **NO_SLEEP)
        old = lifecycle.evaluate(ctx, self.evals, criteria, second, previous=True, **NO_SLEEP)
        self.assertEqual(runs.created, 2)
        targets = [definition["name"] for definition in self.evals.evals.definitions.values()]
        self.assertEqual(targets, ["pkg-agent-v2", "pkg-agent-v1"])
        self.assertEqual((new["summary"]["exact"]["passed"], old["summary"]["exact"]["failed"]), (1, 1))
        self.assertEqual(ctx.observed_inputs["items"]["sha256"], sha256_hex(second.read_bytes()))
        self.refused("input_pin", lifecycle.evaluate, ctx, self.evals, criteria, unpinned)
        plain = self.repo.context(self.repo.manifest(environment="p", series="p-v1",
                                                     pins={"criteria": criteria, "items": first}), environment="p")
        self.refused("previous_missing", lifecycle.evaluate, plain, self.evals, criteria, first, previous=True)
        for bad in ([], ["0" * 64, "0" * 64], ["nope"]):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                repo = Repo(directory)
                with self.assertRaises(RefusedError) as refused:
                    repo.context(repo.manifest(package_dir=None, inputs={"items": bad}))
                self.assertEqual(refused.exception.code, "manifest_inputs")


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments):
        with tempfile.TemporaryDirectory() as bin_dir:
            marker = Path(bin_dir) / "az-called"
            fake = Path(bin_dir) / "az"
            fake.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
            fake.chmod(0o755)
            environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(["bash", str(lifecycle.DEPLOY / "deploy.sh"), *arguments], capture_output=True,
                                    text=True, env=environment, timeout=120)
            self.assertFalse(marker.exists(), "az must not be called on refusal")
        return result

    def test_new_actions_refuse_before_any_cloud_call(self):
        sha = sha256_hex((lifecycle.ENV_DIR / "example.run.json").read_bytes())
        write = ("--authorize-cloud-write",)
        for arguments, message in (
                (("evaluate", "-e", "example", "--manifest-sha256", sha, "--criteria", "c", "--items", "i"),
                 "--authorize-cloud-write"),
                (("optimize", "-e", "example"), "--authorize-cloud-write"),
                (("register-evaluator", "-e", "example"), "--authorize-cloud-write"),
                (("evaluate", "-e", "example", "--manifest-sha256", sha, *write, "--items", "i"), "criteria_missing"),
                (("evaluate", "-e", "example", "--manifest-sha256", sha, *write, "--criteria", "c"), "items_missing"),
                (("optimize", "-e", "example", "--manifest-sha256", sha, *write, "--optimization", "o",
                  "--validation", "v"), "train_missing"),
                (("register-evaluator", "-e", "example", "--manifest-sha256", sha, *write), "evaluator_missing"),
                (("select", "-e", "example", "--manifest-sha256", sha), "rule_missing"),
                (("select", "-e", "example", "--manifest-sha256", sha, "--rule", "r", *write), "does not apply"),
                (("verify", "-e", "example", "--manifest-sha256", sha, "--stream"), "--stream does not apply"),
                (("deploy", "-e", "example", "--manifest-sha256", sha, *write, "--rule", "r"), "--rule does not apply"),
                (("invoke", "-e", "example", "--manifest-sha256", sha, *write, "--input", "x", "--journeys", "j"),
                 "not both"),
                (("inspect", "-e", "example", "--manifest-sha256", sha, *write), "does not apply"),
                (("inspect", "-e", "example", "--manifest-sha256", sha), "env_placeholder")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
