"""Run the actual deployment artifact outside this checkout and exercise the SDK offline."""

from __future__ import annotations

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
from hostedagents.model import connect_model
from hostedagents.packaging import build_bundle
from hostedagents.policy import RuntimePolicy, RuntimeTarget


class PortabilityTests(BundleFixture, unittest.TestCase):
    def test_extracted_bundle_imports_installed_libraries_and_runs_the_host_tool(self):
        bundle = build_bundle(
            self.definition, package_sources={"agent_tools": ROOT / "examples/agent_tools"},
            output_dir=self.work / "artifacts", policy=RuntimePolicy(allowed_tools=self.definition.tools.names),
        )
        destination = self.work / "flat"
        with zipfile.ZipFile(bundle.zip_path) as archive:
            archive.extractall(destination)
        probe = """
import json
from pathlib import Path
root = Path.cwd()
import agentconfig, toolshape, hostedagents, agent_tools
for package in (agentconfig, toolshape, hostedagents):
    assert not Path(package.__file__).is_relative_to(root), package.__file__
assert Path(agent_tools.__file__).is_relative_to(root)
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
print('PASS extracted flat bundle: installed libraries, auth refusal, host tool, model denial')
"""
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        environment.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, "-c", probe], cwd=destination,
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
                [sys.executable, "-c", server_code, str(listener.fileno())],
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

    def test_native_connection_receives_the_configured_target_and_policy_without_io(self):
        import asyncio

        class Credential:
            def get_token(self, *args, **kwargs):
                raise AssertionError("Binding must not acquire a token")

        policy = RuntimePolicy(allowed_tools=self.definition.tools.names)
        target = RuntimeTarget(model_endpoint="https://example.openai.azure.com/openai/v1")
        connection = connect_model(target, policy, model=self.definition.spec.model, credential=Credential())
        self.assertEqual(connection.config.model, self.definition.spec.model)
        self.assertEqual(connection.config.endpoint, target.model_endpoint + "/")
        self.assertEqual(connection.policy, policy.execution_policy())
        self.assertFalse(connection.policy.allow_model_calls)
        asyncio.run(connection.aclose())


if __name__ == "__main__":
    unittest.main()