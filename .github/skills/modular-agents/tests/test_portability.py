"""Run the actual deployment artifact outside this checkout and exercise the SDK offline."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import socket
import sys
import unittest
import zipfile

from test_definition import ROOT
from test_packaging import BundleFixture
import httpx
from hostedagents.model import OpenAIModel
from hostedagents.packaging import build_bundle
from hostedagents.policy import RuntimePolicy


class PortabilityTests(BundleFixture, unittest.TestCase):
    def test_extracted_bundle_imports_its_own_packages_and_runs_the_tool(self):
        bundle = build_bundle(
            self.definition, package_sources={"agent_tools": ROOT / "examples/agent_tools"},
            output_dir=self.work / "artifacts", policy=RuntimePolicy(allowed_tools=self.definition.tools.names),
        )
        destination = self.work / "flat"
        with zipfile.ZipFile(bundle.zip_path) as archive:
            archive.extractall(destination)
        probe = """
import asyncio, json, sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root))
import agentconfig, toolshape, hostedagents, agent_tools
for package in (agentconfig, toolshape, hostedagents, agent_tools):
    assert Path(package.__file__).is_relative_to(root), package.__file__
from hostedagents.application import load_runtime, create_app, local_authorizer
from starlette.testclient import TestClient
runtime = load_runtime(root)
token = 'offline-copy-out-fixture-not-a-credential'
with TestClient(create_app(runtime, authorize=local_authorizer(token))) as client:
    assert client.post('/invocations', json={}).status_code == 401
    client.headers['Authorization'] = 'Bearer ' + token
    response = client.post('/invocations', json={'op':'call', 'tool':'search_notes', 'arguments':{'query':'hosting'}})
    assert response.status_code == 200, response.status_code
    assert response.json()['rows'][0]['title'] == 'Hosting', response.json()
    assert client.post('/invocations', json={'op':'chat', 'message':'hello'}).status_code == 403
    assert client.post('/invocations', json={'op':'health'}).json()['agent'] == 'notes'
print('PASS extracted flat bundle: own sources, auth refusal, real tool, model denial, recovery')
"""
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        environment.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, "-I", "-c", probe], cwd=destination,
                                env=environment, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS extracted flat bundle", result.stdout)

    def test_extracted_service_over_a_real_localhost_socket(self):
        bundle = build_bundle(
            self.definition, package_sources={"agent_tools": ROOT / "examples/agent_tools"},
            output_dir=self.work / "artifacts", policy=RuntimePolicy(allowed_tools=self.definition.tools.names),
        )
        destination = self.work / "socket-runtime"
        with zipfile.ZipFile(bundle.zip_path) as archive:
            archive.extractall(destination)
        server_code = """
import socket, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import uvicorn
from hostedagents.application import create_app, load_runtime, local_authorizer
application = create_app(load_runtime(Path.cwd()), authorize=local_authorizer('offline-socket-fixture-not-a-credential'))
listener = socket.socket(fileno=int(sys.argv[1]))
uvicorn.Server(uvicorn.Config(application, log_level='error')).run(sockets=[listener])
"""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(8)
            endpoint = f"http://127.0.0.1:{listener.getsockname()[1]}"
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            environment.pop("PYTHONPATH", None)
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", server_code, str(listener.fileno())],
                cwd=destination, env=environment, pass_fds=(listener.fileno(),),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                with httpx.Client(base_url=endpoint, timeout=15) as client:
                    self.assertEqual(client.get("/readiness").status_code, 200)
                    self.assertEqual(client.post("/invocations", json={}).status_code, 401)
                    client.headers["Authorization"] = "Bearer offline-socket-fixture-not-a-credential"
                    self.assertEqual(client.post("/invocations", json=[]).status_code, 400)
                    result = client.post("/invocations", json={
                        "op": "call", "tool": "search_notes", "arguments": {"query": "hosting"},
                    })
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()["rows"][0]["title"], "Hosting")
                    health = client.post("/invocations", json={"op": "health"}).json()
                    self.assertEqual(health["artifact_id"], bundle.runtime_sha256)
            finally:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
            self.assertIn(process.returncode, (0, -15), stdout + stderr)

    def test_changed_runtime_source_fails_before_readiness(self):
        bundle = build_bundle(
            self.definition, package_sources={"agent_tools": ROOT / "examples/agent_tools"},
            output_dir=self.work / "artifacts",
        )
        destination = self.work / "changed-runtime"
        with zipfile.ZipFile(bundle.zip_path) as archive:
            archive.extractall(destination)
        (destination / "agent_tools/notes.py").write_text("changed")
        from hostedagents.application import load_runtime

        with self.assertRaisesRegex(ValueError, "differs from its build manifest"):
            load_runtime(destination)

    def test_official_model_sdk_receives_the_configured_contract(self):
        from openai import AsyncOpenAI

        observed = []

        def handle(request):
            observed.append(request)
            return httpx.Response(200, json={
                "id": "offline", "object": "chat.completion", "created": 0,
                "model": "example-deployment", "choices": [{
                    "index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "fixture"},
                }],
            })

        async def run():
            async def credential():
                return "offline-sdk-fixture"

            sdk = AsyncOpenAI(base_url="https://example.openai.azure.com/openai/v1", api_key=credential,
                              http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)), max_retries=0)
            model = OpenAIModel(sdk)
            result = await model.complete(model=self.definition.spec.model,
                                          messages=[{"role": "system", "content": self.definition.spec.instructions}],
                                          tools=self.definition.tools.schemas, max_tokens=500)
            self.assertEqual(result["content"], "fixture")
            await model.close()

        asyncio.run(run())
        self.assertEqual(observed[0].url.path, "/openai/v1/chat/completions")
        body = json.loads(observed[0].content)
        self.assertEqual(body["model"], "example-deployment")
        self.assertIn("Cite note titles", body["messages"][0]["content"])
        self.assertEqual(body["tools"], self.definition.tools.schemas)
        self.assertFalse(body["parallel_tool_calls"])


if __name__ == "__main__":
    unittest.main()