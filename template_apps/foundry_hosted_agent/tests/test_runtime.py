import asyncio
import ssl
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
from agent_tools import MAX_TEXT_CHARACTERS, count_words
from composition import ROOT, load_spec

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
        self.assertEqual([tool.__name__ for tool in spec.tools], ["count_words"])
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

        async def fake_agent(text, endpoint, spec, credential, tls_context):
            seen.update(text=text, endpoint=endpoint, verify=tls_context.verify_mode)
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

        class Agent:
            async def run(self, text):
                captured["run"] = text
                return SimpleNamespace(text="ok")

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
        with patch.object(llm_interface, "connect", Model):
            result = asyncio.run(main.run_agent("hi", "https://e.invalid/api/projects/p", spec, credential,
                                                ssl.create_default_context()))
        self.assertEqual(result, "ok")
        self.assertEqual(captured["args"], ("https://e.invalid/api/projects/p", spec.model))
        kwargs = captured["kwargs"]
        self.assertIs(kwargs["credential"], credential)
        self.assertTrue(kwargs["allow_model_calls"])
        self.assertEqual(kwargs["allowed_tools"], ("count_words",))
        self.assertIsInstance(kwargs["transport"], httpx.AsyncHTTPTransport)
        self.assertEqual(kwargs["limits"].max_tool_calls, main.LIMITS["max_tool_calls"])
        self.assertEqual(captured["agent"]["tools"], spec.tools)
        self.assertEqual(captured["run"], "hi")

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
        result = main.self_check()
        self.assertEqual(result["readiness"], 200)
        self.assertEqual(result["tools"], ["count_words"])


if __name__ == "__main__":
    unittest.main()
