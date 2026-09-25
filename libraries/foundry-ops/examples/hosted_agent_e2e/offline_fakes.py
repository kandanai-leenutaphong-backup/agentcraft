"""Offline stand-ins shaped like the azure-ai-projects 2.6.1 / openai 3.13 surfaces the pipeline calls, plus a
fixture repository (package, pinned inputs, run spec). No network, no Azure SDK."""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from foundry_ops import pipeline  # noqa: E402
from foundry_ops.core import sha256_hex  # noqa: E402

HERE = Path(__file__).resolve().parent
SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
TENANT = "66666666-7777-8888-9999-000000000000"
PRINCIPAL = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ACCOUNT, PROJECT, RESOURCE_GROUP = "fake-account", "fake-project", "rg-fake"
ENDPOINT = f"https://{ACCOUNT}.services.ai.azure.com/api/projects/{PROJECT}"
LOGIN, REPOSITORY = "fakeregistry.azurecr.io", "fake-agent"
MODEL, JUDGE, OPTIMIZER = "runtime-model", "judge-model", "optimizer-model"
DIGEST = "sha256:" + "ab" * 32
PLACEHOLDERS = {"<series>": "demo-v1", "<tenant-guid>": TENANT, "<subscription-guid>": SUBSCRIPTION,
                "<resource-group>": RESOURCE_GROUP, "<account>": ACCOUNT, "<project-name>": PROJECT,
                "<registry-name>": "fakeregistry", "<image-repository>": REPOSITORY, "<agent-name>": "demo-agent",
                "<project>": "demo", "<runtime-model-deployment>": MODEL, "<judge-model-deployment>": JUDGE,
                "<optimizer-model-deployment>": OPTIMIZER}

CONFIG = f"""prompts_dir: prompts
agents:
  default: demo-agent
  demo-agent:
    name: demo-agent
    model: {MODEL}
    instructions: [agent.md]
    tools: [tools:lookup_zone, tools:quote_parcel]
"""
TOOLS = '''class ZoneError(LookupError):
    error_code = "E_ZONE"


def lookup_zone(zone: str) -> dict:
    if zone != "Z1":
        raise ZoneError("unknown zone")
    return {"rate": 3}


def quote_parcel(grams: int, rate: int) -> dict:
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
GRADE = "def grade(sample, item):\n    return 1.0 if item['sample.output_text'].strip() == item['ground_truth'] else 0.0\n"
CANARIES = {"canaries": [
    {"name": "positive", "item": {"ground_truth": "A", "sample.output_text": " A\n"}, "expected": 1.0},
    {"name": "wrong", "item": {"ground_truth": "A", "sample.output_text": "B"}, "expected": 0.0}]}
ROWS = '{"query": "q1", "ground_truth": "a1", "ok": true}\n{"query": "q2", "ground_truth": "a2", "ok": false}\n'
RULE = {"status": "frozen", "score": "avg_score", "eligibility": "strictly_above_baseline",
        "tie_break": "earliest_observation", "fallback": "baseline",
        "demonstration": {"allowed": True, "label": "demonstration"}}


def model(**fields):
    return SimpleNamespace(**fields, model_dump=lambda mode="json": copy.deepcopy(fields))


class NotFound(Exception):
    status_code = 404


class FakeAz:
    def __init__(self, account=None):
        self.calls, self.staged, self.tag = [], None, None
        self.account = account or {"subscriptionId": SUBSCRIPTION, "tenantId": TENANT}

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        head = tuple(arguments[:3])
        if head[:2] == ("account", "show"):
            return self.account
        if head[:2] == ("resource", "show"):
            return {"state": "Succeeded", "endpoints": {"AI Foundry API": ENDPOINT}, "principal": PRINCIPAL}
        if head[:2] == ("acr", "show"):
            return {"id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}/providers/"
                          "Microsoft.ContainerRegistry/registries/fakeregistry", "loginServer": LOGIN}
        if head[:3] == ("role", "assignment", "list"):
            return [{"role": "AcrPull", "condition": None}]
        if head[0] == "cognitiveservices":
            return [{"name": MODEL, "state": "Succeeded"}]
        if head[:2] == ("acr", "build"):
            context = Path(arguments[-1])
            self.staged = sorted(path.relative_to(context).as_posix() for path in context.rglob("*") if path.is_file())
            self.tag = arguments[arguments.index("--image") + 1].split(":", 1)[1]
            return {"runId": "run1"}
        if head[:3] == ("acr", "task", "show-run"):
            return {"runId": "run1", "status": "Succeeded",
                    "outputImages": [{"registry": LOGIN, "repository": REPOSITORY, "tag": self.tag, "digest": DIGEST}]}
        if head[:3] == ("acr", "repository", "show"):
            return {"digest": DIGEST}
        raise AssertionError(f"unexpected az command {arguments[:3]}")

    def count(self, *prefix):
        return sum(1 for call in self.calls if tuple(call[:len(prefix)]) == prefix)


class FakeAgents:
    def __init__(self, log):
        self.log, self.versions, self.sessions = log, {}, {"session1"}

    def get(self, agent_name):
        if not self.versions:
            raise NotFound()
        return {"name": agent_name, "versions": {"latest": self.versions[max(self.versions, key=int)]}}

    def create_version(self, agent_name, body):
        self.log.append("create_version")
        version = str(len(self.versions) + 1)
        self.versions[version] = {"version": version, "status": "active", **copy.deepcopy(body)}
        return {"version": version, "status": "creating"}

    def get_version(self, agent_name, agent_version):
        if agent_version not in self.versions:
            raise NotFound()
        return copy.deepcopy(self.versions[agent_version])

    def list_versions(self, agent_name, limit, include_drafts=None):
        return list(self.versions.values())

    def delete_version(self, agent_name, agent_version):
        self.log.append("delete_version")
        self.versions.pop(agent_version)

    def list_sessions(self, agent_name, limit):
        return [{"agent_session_id": session} for session in sorted(self.sessions)]

    def get_session(self, agent_name, session_id):
        if session_id not in self.sessions:
            raise NotFound()
        return {"agent_session_id": session_id, "status": "idle"}

    def stop_session(self, agent_name, session_id):
        self.log.append("stop_session")

    def delete_session(self, agent_name, session_id):
        self.log.append("delete_session")
        self.sessions.discard(session_id)


def grade(item):
    if "sample.output_text" in item:
        return 1.0 if item["sample.output_text"].strip() == item["ground_truth"] else 0.0
    return 1.0 if item.get("ok") else 0.0


class FakeRuns:
    def __init__(self, evals):
        self.evals, self.rows, self.created, self.requests = evals, {}, 0, []
        self.output_items = SimpleNamespace(list=self.list_items)

    def create(self, **request):
        self.created += 1
        self.requests.append(request)
        run_id = f"run_{self.created}"
        criteria = self.evals.definitions[request["eval_id"]]["testing_criteria"]
        source = request["data_source"]["source"]
        entries = source["content"] if source["type"] == "file_content" else [
            {"item": row} for row in self.evals.datasets[source["id"]]]
        self.rows[run_id] = [
            {"id": f"row_{run_id}_{index}", "eval_id": request["eval_id"], "run_id": run_id, "status": "completed",
             "datasource_item": entry["item"],
             "results": [{"name": criterion["name"], "metric": criterion["name"], "type": criterion["type"],
                          "status": "completed", "score": grade(entry["item"]), "passed": grade(entry["item"]) >= 1}
                         for criterion in criteria]}
            for index, entry in enumerate(entries)]
        return model(id=run_id)

    def retrieve(self, run_id, eval_id):
        return model(id=run_id, eval_id=eval_id, status="completed", error=None,
                     result_counts={"total": len(self.rows[run_id])}, per_testing_criteria_results=[])

    def list_items(self, eval_id, run_id, limit):
        page = SimpleNamespace(data=[model(**row) for row in self.rows[run_id]], last_id=None)
        return SimpleNamespace(iter_pages=lambda: [page])


class FakeEvals:
    """Project OpenAI client: `evals` with runs and output items; `datasets` maps registered ids to rows."""

    def __init__(self):
        self.definitions, self.datasets = {}, {}
        self.evals = self
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
    """One job; each candidate's native validation rows land in the eval fake under `r_<candidate>`."""

    def __init__(self, evals, scores):
        self.evals, self.scores, self.jobs = evals, scores, []

    def begin_create_optimization_job(self, job, operation_id, polling):
        self.jobs.append(copy.deepcopy(job))
        items = job["inputs"]["validation_dataset"].get("items") or [{"query": "q1"}, {"query": "q2"}]
        for candidate, score in self.scores.items():
            self.evals.runs.rows[f"r_{candidate}"] = [
                {"id": f"row_{candidate}_{index}", "eval_id": "e", "run_id": f"r_{candidate}", "status": "completed",
                 "datasource_item": {**item, "sample.output_text": "out"},
                 "results": [{"name": "exact", "status": "completed", "score": score}]}
                for index, item in enumerate(items)]
        return SimpleNamespace(details={"job_id": "job1"})

    def get_optimization_job(self, job_id):
        candidates = [{"candidate_id": candidate, "eval_id": "e", "eval_run_id": f"r_{candidate}", "avg_score": score,
                       "avg_tokens": 10} for candidate, score in self.scores.items()]
        return {"id": job_id, "status": "succeeded", "error": None,
                "result": {"baseline": "base", "best": None, "candidates": candidates}}


class FakeProject:
    def __init__(self, log, evals, scores=None):
        self.log = log
        self.agents = FakeAgents(log)
        self.beta = SimpleNamespace(evaluators=FakeEvaluators(),
                                    agents=FakeOptimizer(evals, scores or {"base": 0.5, "c1": 0.7, "c2": 0.7}))

    def send_request(self, request, connection_timeout, read_timeout):
        candidate = request[1].split("/candidates/")[1].split("/")[0]
        body = json.dumps({"instructions": f"  prompt for {candidate}\n", "model": MODEL}).encode()
        return SimpleNamespace(status_code=200, read=lambda: body)


class ToolResponses:
    """Runtime-shaped responses: native function_call items, `tool_call.<n>` metadata and identity metadata read
    from the version the request pins, so any deployed version answers with its own identity."""

    def __init__(self, store, log, project):
        self.store, self.log, self.project, self.requests = store, log, project, []

    def _identity(self, request):
        reference = request["extra_body"]["agent_reference"]
        metadata = self.project.agents.versions[reference["version"]]["metadata"]
        keys = ("source_sha256", "config_sha256", "package_sha256", "optimization_config_sha256")
        return {**{key: metadata[key] for key in keys if key in metadata}, "agent_name": reference["name"],
                "agent_version": reference["version"]}

    def create(self, **request):
        self.log.append("responses.create")
        self.requests.append(request)
        response_id = f"resp_{len(self.requests)}"
        output, metadata = [], self._identity(request)
        for index, (name, status, code) in enumerate(SCENARIOS.get(request["input"], []), 1):
            call_id = f"call_{index}"
            result = {"error": {"code": code, "message": "declared"}} if status == "error" else {"ok": True}
            output += [{"type": "function_call", "id": f"fc_{index}", "call_id": call_id, "name": name,
                        "arguments": "{}", "status": "completed"},
                       {"type": "function_call_output", "id": f"fco_{index}", "call_id": call_id,
                        "output": json.dumps(result), "status": "completed"}]
            metadata[f"tool_call.{index}"] = json.dumps(
                {"call_id": call_id, "duration_ms": 1.5, "ended_at": "2026-09-25T00:00:01.000Z", "error_code": code,
                 "name": name, "started_at": "2026-09-25T00:00:00.000Z", "status": status},
                sort_keys=True, separators=(",", ":"))
        output.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "DONE"}]})
        response = {"id": response_id, "status": "completed", "metadata": metadata, "output": output}
        self.store[response_id] = copy.deepcopy(response)
        if not request["stream"]:
            return SimpleNamespace(model_dump=lambda mode="json": copy.deepcopy(response), output_text="DONE")
        events = [SimpleNamespace(type="response.created", response={"id": response_id, "status": "in_progress"})]
        for item in output[:-1]:
            events += [SimpleNamespace(type="response.output_item.added", item={**item, "status": "in_progress"}),
                       SimpleNamespace(type="response.output_item.done", item=item)]
        events += [SimpleNamespace(type="response.output_text.delta", delta="DONE", item_id="msg"),
                   SimpleNamespace(type="response.completed", response=copy.deepcopy(response))]
        return contextlib.nullcontext(events)

    def cancel(self, response_id):
        self.log.append("responses.cancel")

    def delete(self, response_id):
        self.log.append("responses.delete")
        self.store.pop(response_id, None)
        return {"id": response_id, "deleted": True}


class FakeOpenAI:
    base_url = ENDPOINT + "/agents/demo-agent/endpoint/protocols/openai/"
    default_query = {"api-version": "v1"}

    def __init__(self, store, log, project):
        self.responses = ToolResponses(store, log, project)


class Reply:
    def __init__(self, status_code, body):
        self.status_code, self.body = status_code, body

    def json(self):
        return self.body


class FakeHttp:
    def __init__(self, store, anonymous_status=401):
        self.store, self.anonymous_status = store, anonymous_status

    def post(self, url, json):
        return Reply(self.anonymous_status, {})

    def get(self, url, params, headers):
        response_id = url.rsplit("/", 1)[1]
        if response_id in self.store:
            return Reply(200, copy.deepcopy(self.store[response_id]))
        return Reply(404, {"error": {"code": "not_found", "message": "missing"}})


class FakeLayout:
    """`pipeline.ImageLayout` for a bare package: package files under `package/` plus one Dockerfile."""

    def __init__(self, root):
        self.dockerfile = Path(root) / "Dockerfile"
        self.dockerfile.write_text("FROM scratch\n")
        self.checks = 0

    def build_inputs(self, package):
        files = {f"{pipeline.PACKAGE_IMAGE_DIR}/{name}": path for name, path in pipeline.package_inputs(package).items()}
        return {**files, "Dockerfile": self.dockerfile}

    def package_config(self, package):
        files = pipeline.package_inputs(package)
        text = files["configuration.yaml"].read_text()
        tools = re.search(r"tools: \[(.*)\]", text)[1].replace(" ", "").split(",")
        return {"agent": "demo-agent", "model": re.search(r"model: (\S+)", text)[1],
                "tools": pipeline.check_package_tools(tools, files)}

    def self_check(self):
        self.checks += 1
        return {"tests": 0}


class FakeData:
    """Stand-in for `foundry_ops.data` (same names and return keys); registered rows become readable by the eval
    fake through their `azureai://` id."""

    def __init__(self, evals):
        self.evals, self.registered, self.readbacks = evals, [], []

    @staticmethod
    def _id(name, version):
        return f"azureai://accounts/{ACCOUNT}/projects/{PROJECT}/data/{name}/versions/{version}"

    def register_jsonl_dataset(self, project, ledger, *, name, rows, fields=None, version=None):
        rows = [dict(row) for row in rows]
        data = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode()
        digest = sha256_hex(data)
        version = version or "sha-" + digest[:32]
        identifier = self._id(name, version)
        reused = identifier in self.evals.datasets
        self.evals.datasets[identifier] = rows
        self.registered.append((name, version))
        return {"id": identifier, "name": name, "version": version, "sha256": digest, "bytes": len(data),
                "rows": len(rows), "data_uri": f"https://blob.example/{name}.jsonl", "reused": reused}

    def readback_dataset(self, project, *, name, version, expected_sha256):
        self.readbacks.append((name, version, expected_sha256))
        return {"id": self._id(name, version), "name": name, "version": version, "sha256": expected_sha256,
                "bytes": 1, "remote_bytes_verified": True, "data_uri": f"https://blob.example/{name}.jsonl"}


class Rig:
    """Fixture repository + fakes. `spec()` renders the example run spec with fixture targets and real pins."""

    def __init__(self, root, scores=None):
        self.root = Path(root)
        self.project_dir = self.root / "agentcraft_projects/demo"
        package = self.project_dir / "agent"
        (package / "prompts").mkdir(parents=True)
        (package / "configuration.yaml").write_text(CONFIG)
        (package / "prompts/agent.md").write_text("Answer with tools.\n")
        (package / "tools.py").write_text(TOOLS)
        inputs, dataset = self.project_dir / "inputs", self.project_dir / "dataset"
        inputs.mkdir()
        dataset.mkdir()
        (inputs / "grade.py").write_text(GRADE)
        (inputs / "canaries.json").write_text(json.dumps(CANARIES))
        files = {
            "journeys.json": JOURNEYS,
            "criteria.json": {"name": "demo-eval", "testing_criteria": [
                {"type": "azure_ai_evaluator", "name": "exact", "evaluator_name": "demo-exact", "data_mapping": {}}]},
            "evaluator.json": {"name": "demo-exact", "metric": "exact", "display_name": "Exact",
                               "data_schema": {"type": "object"}, "code_file": "grade.py",
                               "code_sha256": sha256_hex(GRADE.encode()),
                               "canary": {"criterion_name": "exact", "item_schema": {"type": "object"},
                                          "data_mapping": {"ground_truth": "{{item.ground_truth}}"},
                                          "match_field": "sample.output_text", "cases_file": "canaries.json",
                                          "cases_sha256": sha256_hex(json.dumps(CANARIES).encode())}},
            "optimization.json": {"evaluators": [{"name": "demo-exact", "version": "1"}], "max_candidates": 2},
            "selection-rule.json": RULE}
        for name, value in files.items():
            (inputs / name).write_text(json.dumps(value))
        for name in ("train.jsonl", "validation.jsonl"):
            (dataset / name).write_text(ROWS)
        (self.project_dir / "records").mkdir()
        self.log, self.store = [], {}
        self.az, self.evals = FakeAz(), FakeEvals()
        self.project = FakeProject(self.log, self.evals, scores)
        self.openai, self.http = FakeOpenAI(self.store, self.log, self.project), FakeHttp(self.store)
        self.layout = FakeLayout(self.root)
        self.clients = pipeline.Clients(az=self.az, project=self.project, openai=self.openai, evals=self.evals,
                                        http=self.http, token=lambda: "offline-token", layout=self.layout,
                                        request_factory=lambda method, url: (method, url),
                                        sleep=lambda seconds: None)

    def spec_value(self, **overrides):
        text = (HERE / "run-spec.example.json").read_text()
        for placeholder, value in PLACEHOLDERS.items():
            text = text.replace(placeholder, value)
        value = json.loads(text)

        def pin(ref):
            if isinstance(ref, dict) and ref.get("sha256") == "<sha256>":
                return {**ref, "sha256": sha256_hex((self.root / ref["path"]).read_bytes())}
            return ref

        value["inputs"] = {kind: pin(ref) for kind, ref in value["inputs"].items()}
        for name in pipeline.spec.FILE_SECTIONS:
            value[name] = pin(value[name])
        value.update(overrides)
        return value

    def spec(self, name="run-spec.json", **overrides):
        path = self.root / name
        path.write_text(json.dumps(self.spec_value(**overrides), indent=2, sort_keys=True))
        spec = pipeline.load_run_spec(path, expected_sha256=sha256_hex(path.read_bytes()), repo=self.root,
                                      available=False)
        return spec, pipeline.open_ledger(spec)
