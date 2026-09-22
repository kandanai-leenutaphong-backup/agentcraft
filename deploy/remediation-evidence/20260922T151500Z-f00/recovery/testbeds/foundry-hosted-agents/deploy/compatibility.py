"""Offline real-SDK handler smoke; never evidence of hosted tool execution."""

import importlib.metadata
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_framework import tool
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.models import ContainerConfiguration, HostedAgentDefinition
from starlette.testclient import TestClient

from composition import load_spec
from main import create_server


def check():
    spec = load_spec()
    schemas = [tool(function).to_json_schema_spec() for function in spec.tools]
    definition = HostedAgentDefinition(cpu="1", memory="2Gi", protocol_versions=[],
                                       container_configuration=ContainerConfiguration(image="smoke.invalid/image"))
    assert definition.as_dict()["kind"] == "hosted"
    assert callable(FoundryChatClient)
    server = create_server("https://smoke.invalid/api/projects/smoke", {}, configure_observability=None)
    with TestClient(server, raise_server_exceptions=False) as client:
        readiness = client.get("/readiness")
        assert readiness.status_code == 200, readiness.status_code
        refused = client.post("/responses", json={"input": "invalid-nonce", "stream": False, "store": False})
        body = refused.json()
        assert refused.status_code >= 400 or body.get("status") == "failed", body
    return {"readiness": readiness.status_code, "invalid_input_status": refused.status_code,
            "invalid_input_response_status": body.get("status"), "schemas": schemas,
            "versions": {name: importlib.metadata.version(name) for name in (
                "agent-framework-core", "agent-framework-foundry", "azure-ai-projects",
                "azure-ai-agentserver-responses", "openai")}}


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))