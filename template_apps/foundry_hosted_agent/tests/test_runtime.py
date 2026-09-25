import asyncio
import hashlib
import json
import os
import ssl
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
import tool_calls
from agent_tools import MAX_TEXT_CHARACTERS, UnknownUnitError, count_words, describe_unit
from composition import ROOT, apply_optimization, load_optimized_spec, load_spec, package_manifest, package_root
from fakes import FakeModel, FixtureCredential

CONFIG = (ROOT / "configuration.yaml").read_text()
IDENTITY = {"source_sha256": "s" * 64, "config_sha256": "c" * 64, "agent_name": "example-hosted-agent",
            "agent_version": "3"}


class NullCredential:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class ConfigurationTests(unittest.TestCase):
    def test_spec_loads_one_agent_and_tool(self):
        spec = load_spec()
        self.assertEqual((spec.agent_id, spec.name, spec.model), ("example-agent", "example-agent",
                                                                  "example-model-deployment"))
        self.assertEqual([tool.__name__ for tool in spec.tools], ["count_words", "describe_unit"])
        self.assertIn("count_words", spec.instructions)

    def assert_refused(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.yaml"
            path.write_text(content)
            with self.assertRaises(ValueError):
                load_spec(path)

    def test_unknown_tool_refused(self):
        for spec in ("os:system", "agent_tools:missing", "agent_tools_evil:count_words", "@server:shell"):
            with self.subTest(spec=spec):
                self.assert_refused(CONFIG.replace("agent_tools:count_words", spec))

    def test_unknown_fields_and_roster_refused(self):
        self.assert_refused(CONFIG + "credential: forbidden\n")
        self.assert_refused(CONFIG.replace("    model:", "    api_key: x\n    model:"))
        self.assert_refused(CONFIG.replace("  default: example-agent", "  default: other-agent"))
        self.assert_refused(CONFIG.replace("prompts_dir: prompts", "prompts_dir: ../elsewhere"))

    def test_duplicate_key_refused(self):
        self.assert_refused(CONFIG.replace("    model: example-model-deployment",
                                           "    model: example-model-deployment\n    model: other"))


class ToolTests(unittest.TestCase):
    def test_deterministic_result(self):
        self.assertEqual(count_words("one two  three"), {"words": 3, "characters": 14})
        self.assertEqual(count_words(""), {"words": 0, "characters": 0})

    def test_bounds_refused(self):
        for value in (None, 7, "x" * (MAX_TEXT_CHARACTERS + 1)):
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                count_words(value)

    def test_native_maf_schema(self):
        from agent_framework import tool

        schema = tool(count_words).to_json_schema_spec()
        self.assertEqual(schema["function"]["name"], "count_words")
        self.assertEqual(schema["function"]["parameters"]["required"], ["text"])

    def test_describe_unit_declares_error_code(self):
        self.assertEqual(describe_unit("kg"), {"symbol": "kg", "name": "kilogram", "quantity": "mass"})
        with self.assertRaises(UnknownUnitError) as raised:
            describe_unit("furlong")
        self.assertEqual(raised.exception.error_code, "unknown_unit")


class InstrumentationTests(unittest.TestCase):
    def call(self, recorder, name, call_id="call_1", **arguments):
        from llm_interface import ToolCall

        async def exercise():
            tool = {function.__name__: function for function in recorder.tools}[name]
            allowed = recorder.authorize(ToolCall(name, dict(arguments), call_id=call_id))
            return allowed, (await tool(**arguments) if allowed else None)

        return asyncio.run(exercise())

    def test_instrumented_schema_is_native_schema(self):
        from agent_framework import tool

        spec = load_spec()
        wrapped = tool_calls.ToolCallRecorder(spec.tools).tools
        self.assertEqual([tool(function).to_json_schema_spec() for function in wrapped],
                         [tool(function).to_json_schema_spec() for function in spec.tools])

    def test_success_declared_and_undeclared_failures_are_structured(self):
        def broken(value: str) -> dict:
            raise RuntimeError("secret internal detail")

        recorder = tool_calls.ToolCallRecorder((count_words, describe_unit, broken))
        self.assertEqual(self.call(recorder, "count_words", "c1", text="a b"),
                         (True, {"words": 2, "characters": 3}))
        self.assertEqual(self.call(recorder, "describe_unit", "c2", symbol="furlong")[1],
                         {"error": {"code": "unknown_unit", "message": "not an SI base unit symbol"}})
        self.assertEqual(self.call(recorder, "broken", "c3", value="x")[1],
                         {"error": {"code": "RuntimeError", "message": "tool failed"}})
        records = recorder.records
        self.assertEqual([(r["call_id"], r["status"], r["error_code"]) for r in records.values()],
                         [("c1", "ok", None), ("c2", "error", "unknown_unit"), ("c3", "error", "RuntimeError")])
        self.assertEqual(records["c1"]["arguments"], {"text": "a b"})
        for record in records.values():
            self.assertGreaterEqual(record["duration_ms"], 0)
            self.assertLessEqual(record["started_at"], record["ended_at"])
            entry = tool_calls.metadata_entry(record)
            self.assertLessEqual(len(entry), 512)
            self.assertEqual(set(json.loads(entry)), set(tool_calls.METADATA_FIELDS))

    def test_unknown_duplicate_or_unbound_call_refused(self):
        recorder = tool_calls.ToolCallRecorder((count_words,))
        self.assertEqual(self.call(recorder, "count_words", "c1", text="a")[0], True)
        self.assertEqual(self.call(recorder, "count_words", "c1", text="a")[0], False)
        self.assertEqual(self.call(recorder, "count_words", "x" * 129, text="a")[0], False)
        from llm_interface import ToolCall
        self.assertFalse(recorder.authorize(ToolCall("os_system", {}, call_id="c9")))
        with self.assertRaises(LookupError):
            asyncio.run(recorder.tools[0](text="unbound"))


class HostTests(unittest.TestCase):
    def test_input_bounds(self):
        self.assertEqual(main.parse_input("  hello "), "hello")
        for value in (None, "", "   ", "x" * (main.MAX_INPUT_CHARACTERS + 1)):
            with self.subTest(value=repr(value)[:10]), self.assertRaises(ValueError):
                main.parse_input(value)

    def test_platform_tls_remains_verified(self):
        with patch("main.ssl.create_default_context", wraps=ssl.create_default_context) as context:
            main.create_server(main.SELF_CHECK_ENDPOINT, load_spec(), IDENTITY, configure_observability=None)
            context.assert_called_once_with()
        verified = ssl.create_default_context()
        self.assertEqual(verified.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(verified.check_hostname)

    def test_real_host_returns_text_and_identity_metadata(self):
        from starlette.testclient import TestClient

        seen = {}

        async def fake_agent(text, endpoint, spec, credential, tls_context, emit):
            seen.update(text=text, endpoint=endpoint, verify=tls_context.verify_mode)
            await emit(("text", "3 words"))
            return "3 words"

        with patch.object(main, "run_agent", fake_agent), patch.object(main, "platform_credential", NullCredential):
            server = main.create_server(main.SELF_CHECK_ENDPOINT, load_spec(), IDENTITY, configure_observability=None)
            with TestClient(server, raise_server_exceptions=False) as client:
                self.assertEqual(client.get("/readiness").status_code, 200)
                reply = client.post("/responses", json={"input": "one two three", "stream": False, "store": False})
                refused = client.post("/responses", json={"input": " ", "stream": False, "store": False})
        body = reply.json()
        self.assertEqual(reply.status_code, 200, body)
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["metadata"], IDENTITY)
        texts = [part["text"] for item in body["output"] if item.get("type") == "message"
                 for part in item["content"] if part.get("type") == "output_text"]
        self.assertEqual(texts, ["3 words"])
        self.assertEqual(seen, {"text": "one two three", "endpoint": main.SELF_CHECK_ENDPOINT,
                                "verify": ssl.CERT_REQUIRED})
        self.assertTrue(refused.status_code >= 400 or refused.json().get("status") == "failed")

    def test_run_agent_wires_llm_interface(self):
        import httpx
        import llm_interface

        captured = {}

        class Stream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def get_final_response(self):
                return SimpleNamespace(text="ok")

        class Agent:
            def run(self, text, stream):
                captured.update(run=text, stream=stream)
                return Stream()

        class Model:
            def __init__(self, *args, **kwargs):
                captured.update(args=args, kwargs=kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def agent(self, **options):
                captured["agent"] = options
                return Agent()

        spec = load_spec()
        credential = object()
        async def emit(event):
            raise AssertionError("no events expected")

        with patch.object(llm_interface, "connect", Model):
            result = asyncio.run(main.run_agent("hi", "https://e.invalid/api/projects/p", spec, credential,
                                                ssl.create_default_context(), emit))
        self.assertEqual(result, "ok")
        self.assertEqual(captured["args"], ("https://e.invalid/api/projects/p", spec.model))
        kwargs = captured["kwargs"]
        self.assertIs(kwargs["credential"], credential)
        self.assertTrue(kwargs["allow_model_calls"])
        self.assertEqual(kwargs["allowed_tools"], ("count_words", "describe_unit"))
        self.assertIsInstance(kwargs["transport"], httpx.AsyncHTTPTransport)
        self.assertEqual(kwargs["limits"].max_tool_calls, main.LIMITS["max_tool_calls"])
        self.assertEqual([tool.__wrapped__ for tool in captured["agent"]["tools"]], list(spec.tools))
        self.assertTrue(callable(captured["agent"]["authorize_tool"]))
        self.assertEqual((captured["run"], captured["stream"]), ("hi", True))

    def test_cancellation_cancels_and_joins_work(self):
        async def exercise():
            signal, entered, finished = asyncio.Event(), asyncio.Event(), []

            async def work():
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    finished.append("closed")

            task = asyncio.create_task(main.run_cancellable(work(), signal))
            await asyncio.wait_for(entered.wait(), 2)
            signal.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            self.assertEqual(finished, ["closed"])
            self.assertEqual([t for t in asyncio.all_tasks() if t is not asyncio.current_task()], [])

        asyncio.run(exercise())

    def test_identity_from_staged_manifest_and_platform_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source-manifest.json"
            path.write_text('{"sha256": "s", "files": {"app/configuration.yaml": "c"}}')
            identity = main.load_identity({"FOUNDRY_AGENT_NAME": "a", "FOUNDRY_AGENT_VERSION": "2"}, path)
            self.assertEqual(identity, {"source_sha256": "s", "config_sha256": "c", "agent_name": "a",
                                        "agent_version": "2"})
            with self.assertRaises(KeyError):
                main.load_identity({}, path)

    def test_image_self_check(self):
        with patch.dict(os.environ, {}, clear=True):
            result = main.self_check()
        self.assertEqual(result["readiness"], 200)
        self.assertEqual(result["tools"], ["count_words", "describe_unit"])
        self.assertEqual(result["optimization"], "none")

    def test_identity_and_tool_records_fit_metadata_limit(self):
        oversized = {f"k{index}": "v" for index in range(main.MAX_METADATA_KEYS - main.LIMITS["max_tool_calls"] + 1)}
        with self.assertRaises(ValueError):
            main.create_server(main.SELF_CHECK_ENDPOINT, load_spec(), oversized, configure_observability=None)

    def test_main_applies_optimization_to_spec_and_identity(self):
        captured = {}

        class Server:
            def run(self):
                captured["ran"] = True

        def create(endpoint, spec, identity):
            captured.update(spec=spec, identity=identity)
            return Server()

        class SyncCredential:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        environ = {"FOUNDRY_PROJECT_ENDPOINT": main.SELF_CHECK_ENDPOINT}
        with patch.dict(os.environ, {"OPTIMIZATION_CONFIG": '{"instructions": "optimized"}'}, clear=True), \
                patch.object(main, "platform_credential", lambda asynchronous=True: SyncCredential()), \
                patch.object(main, "load_identity", lambda environ: dict(IDENTITY)), \
                patch.object(main, "create_server", create):
            main.main([], environ)
        self.assertEqual(captured["spec"].instructions, "optimized")
        self.assertEqual({key: captured["identity"][key] for key in IDENTITY}, IDENTITY)
        self.assertEqual(captured["identity"]["optimization_config_sha256"], optimized_digest("optimized"))
        self.assertTrue(captured["ran"])


def optimized_digest(instructions, model="example-model-deployment"):
    return hashlib.sha256(json.dumps({"instructions": instructions, "model": model}, sort_keys=True).encode()).hexdigest()


@contextmanager
def hosted(model, identity=IDENTITY, spec=None):
    """Real host, real llm_interface/MAF loop and tools; only the model endpoint is a synthetic SSE fixture."""
    import httpx
    from starlette.testclient import TestClient

    transports = []

    def transport(**options):
        transports.append(options)
        return httpx.MockTransport(model.handle)

    with patch.object(httpx, "AsyncHTTPTransport", transport), \
            patch.object(main, "platform_credential", FixtureCredential), \
            patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
        server = main.create_server(main.SELF_CHECK_ENDPOINT, spec or load_spec(), identity,
                                    configure_observability=None)
        with TestClient(server, raise_server_exceptions=False) as client:
            yield client
    for options in transports:
        assert options["verify"].verify_mode == ssl.CERT_REQUIRED


def stream_events(client, text):
    with client.stream("POST", "/responses", json={"input": text, "stream": True, "store": True}) as reply:
        assert reply.status_code == 200, reply.status_code
        return [json.loads(line[5:]) for line in reply.iter_lines() if line.startswith("data:")]


def tool_view(response):
    """Join native function_call / function_call_output items with the custom metadata record by call_id."""
    calls = {item["call_id"]: item for item in response["output"] if item["type"] == "function_call"}
    outputs = {item["call_id"]: item for item in response["output"] if item["type"] == "function_call_output"}
    records = [json.loads(value) for key, value in (response.get("metadata") or {}).items()
               if key.startswith(tool_calls.METADATA_PREFIX)]
    return [{**record, "arguments": json.loads(calls[record["call_id"]]["arguments"]),
             "result": json.loads(outputs[record["call_id"]]["output"])} for record in records]


class ToolCallObservabilityTests(unittest.TestCase):
    def test_tool_call_captured_in_stream_and_stored_response(self):
        model = FakeModel("count_words", {"text": "one two three"}, answer="3 words")
        with hosted(model) as client:
            events = stream_events(client, "How many words: one two three")
            stored = client.get("/responses/" + events[-1]["response"]["id"]).json()
            unstreamed = client.post("/responses", json={"input": "again", "stream": False, "store": True}).json()
        kinds = [(event["type"], (event.get("item") or {}).get("type")) for event in events]
        self.assertEqual(kinds, [
            ("response.created", None), ("response.in_progress", None),
            ("response.output_item.added", "function_call"), ("response.function_call_arguments.delta", None),
            ("response.function_call_arguments.done", None), ("response.output_item.done", "function_call"),
            ("response.output_item.added", "function_call_output"),
            ("response.output_item.done", "function_call_output"),
            ("response.output_item.added", "message"), ("response.content_part.added", None),
            ("response.output_text.delta", None), ("response.output_text.done", None),
            ("response.content_part.done", None), ("response.output_item.done", "message"),
            ("response.completed", None)])
        for response in (events[-1]["response"], stored, unstreamed):
            self.assertEqual(response["status"], "completed")
            self.assertEqual({key: response["metadata"][key] for key in IDENTITY}, IDENTITY)
            [view] = tool_view(response)
            self.assertEqual({key: view[key] for key in ("call_id", "name", "arguments", "result", "status",
                                                         "error_code")},
                             {"call_id": "call_fixture_1", "name": "count_words",
                              "arguments": {"text": "one two three"}, "result": {"words": 3, "characters": 13},
                              "status": "ok", "error_code": None})
            self.assertGreaterEqual(view["duration_ms"], 0)
            self.assertLessEqual(view["started_at"], view["ended_at"])
        self.assertEqual(stored["output"], events[-1]["response"]["output"])
        self.assertEqual([part["text"] for item in stored["output"] if item["type"] == "message"
                          for part in item["content"]], ["3 words"])

    def test_failing_tool_completes_turn_with_error_code(self):
        model = FakeModel("describe_unit", {"symbol": "furlong"}, answer="unknown_unit")
        with hosted(model) as client:
            events = stream_events(client, "What is a furlong?")
            stored = client.get("/responses/" + events[-1]["response"]["id"]).json()
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual(stored["status"], "completed")
        [view] = tool_view(stored)
        error = {"error": {"code": "unknown_unit", "message": "not an SI base unit symbol"}}
        self.assertEqual((view["status"], view["error_code"], view["result"]), ("error", "unknown_unit", error))
        self.assertEqual([json.loads(item["output"]) for item in model.tool_outputs()], [error])

    def test_unregistered_tool_refused_without_execution(self):
        model = FakeModel("os_system", {"command": "id"})
        with hosted(model) as client:
            events = stream_events(client, "run a command")
            stored = client.get("/responses/" + events[-1]["response"]["id"]).json()
        self.assertEqual(events[-1]["type"], "response.failed")
        self.assertEqual((stored["status"], stored["output"]), ("failed", []))
        self.assertFalse([key for key in stored["metadata"] if key.startswith(tool_calls.METADATA_PREFIX)])
        self.assertEqual(model.tool_outputs(), [])


class OptimizationTests(unittest.TestCase):
    def load(self, environ, directory=None):
        with tempfile.TemporaryDirectory() as empty, patch.dict(os.environ, environ, clear=True):
            return load_optimized_spec(None, config_dir=directory or Path(empty) / "absent")

    def candidate(self, root, name, instructions="candidate prompt", metadata="", extra=None):
        folder = Path(root) / name
        folder.mkdir(parents=True)
        (folder / "instructions.md").write_text(instructions)
        (folder / "metadata.yaml").write_text(metadata)
        for relative, content in (extra or {}).items():
            (folder / relative).parent.mkdir(parents=True, exist_ok=True)
            (folder / relative).write_text(content)

    def test_absent_is_baseline_unchanged(self):
        spec, identity = self.load({})
        self.assertEqual((spec, identity), (load_spec(), {}))

    def test_inline_candidate_applied_with_digest(self):
        spec, identity = self.load({"OPTIMIZATION_CONFIG": json.dumps(
            {"instructions": "inline prompt", "model": "example-model-deployment"})})
        self.assertEqual(spec.instructions, "inline prompt")
        self.assertEqual(spec.tools, load_spec().tools)
        self.assertEqual(identity, {"optimization_source": "env", "optimization_candidate_id": "inline",
                                    "optimization_config_sha256": optimized_digest("inline prompt")})

    def test_baked_candidate_and_baseline_applied(self):
        with tempfile.TemporaryDirectory() as root:
            self.candidate(root, "baseline", "baseline prompt")
            self.candidate(root, "cand-7", "candidate prompt", "model: example-model-deployment\n")
            spec, identity = self.load({"OPTIMIZATION_CANDIDATE_ID": "cand-7"}, root)
            self.assertEqual((spec.instructions, identity["optimization_candidate_id"], identity["optimization_source"]),
                             ("candidate prompt", "cand-7", "local"))
            self.assertEqual(identity["optimization_config_sha256"], optimized_digest("candidate prompt"))
            spec, identity = self.load({}, root)
            self.assertEqual((spec.instructions, identity["optimization_candidate_id"]), ("baseline prompt", "baseline"))

    def test_requested_candidate_never_silently_falls_back_to_baseline(self):
        with tempfile.TemporaryDirectory() as root:
            self.candidate(root, "baseline", "baseline prompt")
            with self.assertRaises(ValueError):
                self.load({"OPTIMIZATION_CANDIDATE_ID": "missing"}, root)
        with self.assertRaises(ValueError):
            self.load({"OPTIMIZATION_CANDIDATE_ID": "missing"})

    def test_disallowed_fields_and_unsafe_inputs_refused(self):
        for environ in ({"OPTIMIZATION_CANDIDATE_ID": "../escape"},
                        {"OPTIMIZATION_CONFIG": "[]"},
                        {"OPTIMIZATION_CONFIG": "not json"},
                        {"OPTIMIZATION_CONFIG": '{"instructions": "x", "skills_dir": "/tmp/skills"}'},
                        {"OPTIMIZATION_CONFIG": '{"instructions": "x", "model": "foreign"}'},
                        {"OPTIMIZATION_CONFIG": '{"instructions": "x", "temperature": 1}'},
                        {"OPTIMIZATION_CONFIG": '{"instructions": "x", "skills": [{"name": "s"}]}'},
                        {"OPTIMIZATION_CONFIG": '{"instructions": "x", "tools": [{"type": "function"}]}'},
                        {"OPTIMIZATION_CONFIG": '{"instructions": "  "}'}):
            with self.subTest(environ=environ), self.assertRaises(ValueError):
                self.load(environ)
        for extra in ({"tools.json": '[{"type": "function", "function": {"name": "count_words"}}]'},
                      {"skills/extra/SKILL.md": "# extra"}):
            with self.subTest(extra=list(extra)), tempfile.TemporaryDirectory() as root:
                self.candidate(root, "baseline", extra=extra)
                with self.assertRaises(ValueError):
                    self.load({}, root)

    def test_apply_refuses_typed_drift(self):
        from azure.ai.agentserver.optimization import CandidateConfig

        for fields in ({"skills": {}}, {"tool_definitions": ""}, {"model": []}, {"instructions": 42}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                apply_optimization(load_spec(), CandidateConfig(**{"instructions": "x", **fields}))
        with self.assertRaises(ValueError):
            apply_optimization(load_spec(), None)

    def test_candidate_digest_reaches_response_metadata(self):
        spec_identity = self.load({"OPTIMIZATION_CONFIG": '{"instructions": "inline prompt"}'})[1]
        model = FakeModel("count_words", {"text": "a"})
        with hosted(model, {**IDENTITY, **spec_identity}) as client:
            body = client.post("/responses", json={"input": "a", "stream": False, "store": True}).json()
        self.assertEqual(body["metadata"]["optimization_config_sha256"], optimized_digest("inline prompt"))
        self.assertEqual(body["metadata"]["optimization_candidate_id"], "inline")


PACKAGE_TOOLS = '''
from os.path import join as reexported


class NotListedError(LookupError):
    error_code = "E_NOT_LISTED"


def lookup_code(code: str) -> dict:
    """Value for a listed code; other codes fail with E_NOT_LISTED."""
    if code != "K1":
        raise NotListedError("code not listed")
    return {"code": code, "value": 7}
'''
PACKAGE_CONFIG = CONFIG.replace("example-agent", "package-agent").replace(
    "      - agent_tools:count_words\n      - agent_tools:describe_unit\n", "      - pkg_probe_tools:lookup_code\n")


def write_package(root, config=PACKAGE_CONFIG):
    root = Path(root)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "prompts/agent.md").write_text("Use lookup_code.\n")
    (root / "pkg_probe_tools.py").write_text(PACKAGE_TOOLS)
    (root / "configuration.yaml").write_text(config)
    return root.resolve()


class PackageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.package = write_package(directory.name)

    def test_package_loads_and_tool_calls_are_captured(self):
        spec = load_spec(package=self.package)
        self.assertEqual((spec.name, [tool.__name__ for tool in spec.tools]), ("package-agent", ["lookup_code"]))
        self.assertEqual(spec.instructions, "Use lookup_code.")
        identity = {**IDENTITY, "package_sha256": package_manifest(self.package)["sha256"]}
        with hosted(FakeModel("lookup_code", {"code": "K1"}, answer="7"), identity, spec) as client:
            events = stream_events(client, "value of K1")
            stored = client.get("/responses/" + events[-1]["response"]["id"]).json()
        failing = FakeModel("lookup_code", {"code": "K9"}, answer="E_NOT_LISTED")
        with hosted(failing, identity, spec) as client:
            failed = client.post("/responses", json={"input": "value of K9", "stream": False, "store": True}).json()
        self.assertEqual(stored["metadata"]["package_sha256"], identity["package_sha256"])
        [ok] = tool_view(stored)
        self.assertEqual((ok["name"], ok["arguments"], ok["result"], ok["status"], ok["error_code"]),
                         ("lookup_code", {"code": "K1"}, {"code": "K1", "value": 7}, "ok", None))
        [error] = tool_view(failed)
        self.assertEqual(failed["status"], "completed")
        self.assertEqual((error["status"], error["error_code"], error["result"]),
                         ("error", "E_NOT_LISTED", {"error": {"code": "E_NOT_LISTED", "message": "code not listed"}}))

    def test_main_and_self_check_serve_package_with_digest(self):
        captured = {}

        class SyncCredential:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def create(endpoint, spec, identity):
            captured.update(spec=spec, identity=identity)
            return SimpleNamespace(run=lambda: None)

        environ = {"FOUNDRY_PROJECT_ENDPOINT": main.SELF_CHECK_ENDPOINT, "AGENT_PACKAGE_DIR": str(self.package)}
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(main, "platform_credential", lambda asynchronous=True: SyncCredential()), \
                patch.object(main, "load_identity", lambda environ: dict(IDENTITY)), \
                patch.object(main, "create_server", create):
            main.main([], environ)
        digest = package_manifest(self.package)["sha256"]
        self.assertEqual([tool.__name__ for tool in captured["spec"].tools], ["lookup_code"])
        self.assertEqual(captured["identity"], {**IDENTITY, "package_sha256": digest})
        with patch.dict(os.environ, {}, clear=True):
            checked = main.self_check({"AGENT_PACKAGE_DIR": str(self.package)})
            builtin = main.self_check({})
        self.assertEqual((checked["tools"], checked["package_sha256"]), (["lookup_code"], digest))
        self.assertEqual((builtin["tools"], builtin["package_sha256"]),
                         (["count_words", "describe_unit"], package_manifest()["sha256"]))

    def test_missing_package_refused_loudly(self):
        self.assertIsNone(package_root({}))
        self.assertEqual(package_root({"AGENT_PACKAGE_DIR": str(self.package)}), self.package)
        with tempfile.TemporaryDirectory() as empty:
            for value in ("/nonexistent/agent-package", "", "  ", empty, str(self.package / "configuration.yaml")):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "AGENT_PACKAGE_DIR"):
                    package_root({"AGENT_PACKAGE_DIR": value})
        started = []
        with patch.object(main, "create_server", lambda *args: started.append(args)), \
                self.assertRaisesRegex(ValueError, "/nonexistent/agent-package"):
            main.main([], {"FOUNDRY_PROJECT_ENDPOINT": main.SELF_CHECK_ENDPOINT,
                           "AGENT_PACKAGE_DIR": "/nonexistent/agent-package"})
        self.assertEqual(started, [])

    def test_escaping_shadowing_or_foreign_tool_refused(self):
        outside = self.package.parent / "outside_tools.py"
        outside.write_text(PACKAGE_TOOLS)
        self.addCleanup(outside.unlink)
        (self.package / "linked_tools.py").symlink_to(outside)
        for entry in ("../pkg_probe_tools:lookup_code", "prompts/pkg_probe_tools:lookup_code",
                      "pkg_probe_tools.sub:lookup_code", "os:system", "json:loads", "composition:load_spec",
                      "tool_calls:classify_error", "agent_tools:count_words", "httpx:get", "absent_tools:lookup",
                      "linked_tools:lookup_code", "outside_tools:lookup_code", "pkg_probe_tools:missing",
                      "pkg_probe_tools:reexported", "pkg_probe_tools:NotListedError", "pkg_probe_tools",
                      "@server:shell"):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                (self.package / "configuration.yaml").write_text(
                    PACKAGE_CONFIG.replace("pkg_probe_tools:lookup_code", entry))
                load_spec(package=self.package)

    def test_package_digest_stable_and_changes_on_edit(self):
        first = package_manifest(self.package)
        expected = {path: hashlib.sha256((self.package / path).read_bytes()).hexdigest()
                    for path in ("configuration.yaml", "pkg_probe_tools.py", "prompts/agent.md")}
        self.assertEqual(first, {"files": expected,
                                 "sha256": hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()})
        load_spec(package=self.package)
        (self.package / "__pycache__").mkdir(exist_ok=True)
        (self.package / "__pycache__/pkg_probe_tools.cpython-312.pyc").write_bytes(b"x")
        self.assertEqual(package_manifest(self.package), first)
        prompt = self.package / "prompts/agent.md"
        prompt.write_text("Use lookup_code twice.\n")
        edited = package_manifest(self.package)
        self.assertNotEqual(edited["sha256"], first["sha256"])
        self.assertEqual(set(edited["files"]), set(first["files"]))
        prompt.write_text("Use lookup_code.\n")
        self.assertEqual(package_manifest(self.package), first)
        (self.package / "notes.txt").write_text("added")
        self.assertIn("notes.txt", package_manifest(self.package)["files"])
        (self.package / "notes.txt").unlink()
        (self.package / "prompts/linked.md").symlink_to(prompt)
        with self.assertRaises(ValueError):
            package_manifest(self.package)

    def test_builtin_package_members(self):
        self.assertEqual(set(package_manifest()["files"]), {"configuration.yaml", "prompts/agent.md", "agent_tools.py"})
        self.assertEqual(package_manifest(), package_manifest())


if __name__ == "__main__":
    unittest.main()
