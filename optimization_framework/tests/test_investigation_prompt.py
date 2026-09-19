import json
from pathlib import Path
import socket
import sys

import pytest
import yaml
import httpx


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "optimization_framework/adapters/investigation"
sys.path.insert(0, str(ROOT / "template_apps/investigation_app"))
sys.path.insert(0, str(ADAPTER))
import prompt_live


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("CYBEREYE_ALLOW_MODEL_CALLS", "false")
    monkeypatch.setenv("CYBEREYE_AGENT_STORE_DIR", str(tmp_path / "agents"))

    def refuse(*args, **kwargs):
        raise AssertionError("external network refused in offline prompt tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def valid_output(scenario):
    row = scenario["rows"][0]
    return {"observation": f'{row["host"]} {row["account"]}: {row["event"]}.',
            "inference": "The observed event alone does not establish compromise.",
            "unknowns": scenario["unknown"], "scope": scenario["scope"],
            "citation_ids": [row["resource_id"]]}


def test_copy_loads_actual_prompt_and_changes_only_prompt(tmp_path):
    source = ROOT / "template_apps/investigation_app/app/cybereye/control"
    before = prompt_live.hashes(source)
    contract = yaml.safe_load((ROOT / "optimization_framework/tasks/investigation/prompt.yaml").read_text())
    specs, receipt = prompt_live.prepare_controls(source, tmp_path, contract["instruction"])
    assert prompt_live.hashes(source) == before
    assert receipt["changed_control_paths"] == [prompt_live.PROMPT_PATH]
    assert specs["candidate"].instructions.startswith(specs["baseline"].instructions)
    assert specs["candidate"].instructions.endswith(contract["instruction"])
    assert specs["baseline"].tools == specs["candidate"].tools
    assert specs["baseline"].foundation_files == specs["candidate"].foundation_files


@pytest.mark.parametrize("scenario", prompt_live.SCENARIOS)
def test_acceptance_and_matching_negatives(scenario):
    payload = valid_output(scenario)
    assert prompt_live.evaluate(json.dumps(payload), scenario)["passed"]
    for changed in ({**payload, "citation_ids": ["invented"]},
                    {**payload, "scope": "unbounded"},
                    {**payload, "unknowns": ""},
                    {**payload, "observation": "invented host"},
                    {**payload, "extra": True}):
        assert not prompt_live.evaluate(json.dumps(changed), scenario)["passed"]
    assert not prompt_live.evaluate("- Historical observation only.", scenario)["passed"]


@pytest.mark.asyncio
async def test_permission_refuses_before_any_identity_or_network():
    result = await prompt_live.prompt_live(allow_model_calls=False)
    assert result["status"] == "refusal" and result["model_request_count"] == 0


@pytest.mark.asyncio
async def test_native_service_delivery_owner_and_transport_budget(tmp_path):
    from app.cybereye.tests.test_native_agent import completion
    from llm_interface import Limits, LlmError, connect

    source = ROOT / "template_apps/investigation_app/app/cybereye/control"
    contract = yaml.safe_load((ROOT / "optimization_framework/tasks/investigation/prompt.yaml").read_text())
    specs, _ = prompt_live.prepare_controls(source, tmp_path, contract["instruction"])
    scenario = prompt_live.SCENARIOS[0]
    spec = specs["candidate"]

    async def handle(request):
        return completion([({"role": "assistant", "content": json.dumps(valid_output(scenario))}, None), ({}, "stop")])

    transport = prompt_live.CountedTransport(httpx.MockTransport(handle))
    transport.active = {"spec": spec, "scenario": scenario["id"], "variant": "candidate", "requests": 0}
    async with connect("https://fixture.invalid/v1", spec.model, provider="openai_completions",
                       credential="offline-fixture", transport=transport, allow_model_calls=True,
                       allowed_tools=tuple(tool.metadata.name for tool in spec.tools),
                       limits=Limits(max_model_calls=1, max_output_tokens=spec.max_output_tokens)) as model:
        result = await prompt_live.run_variant(spec, scenario, model)
    assert result["evaluation"]["passed"] and result["foreign_owner_refused"]
    assert len(transport.requests) == 1
    with pytest.raises(LlmError, match="prompt_request_budget"):
        await transport.handle_async_request(httpx.Request("POST", "https://fixture.invalid/v1"))
    transport.active["requests"] = 0
    transport.requests *= 4
    with pytest.raises(LlmError, match="prompt_request_budget"):
        await transport.handle_async_request(httpx.Request("POST", "https://fixture.invalid/v1"))
    await transport.aclose()


def test_sanitized_failure_never_includes_exception_payload():
    failure = prompt_live.safe_failure(RuntimeError("secret must not appear"))
    assert "secret" not in json.dumps(failure)
    assert prompt_live.safe_code("Bearer secret") == "unavailable"


@pytest.mark.asyncio
async def test_provider_auth_refusal_stops_and_cleans_up(monkeypatch):
    import azure.identity.aio
    from azure.core.credentials import AccessToken

    closed = []

    class Credential:
        def __init__(self, **kwargs):
            assert kwargs == {"exclude_interactive_browser_credential": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.append(True)

        async def get_token(self, *scopes, **kwargs):
            return AccessToken("offline-not-a-real-token", 4102444800)

    async def handle(request):
        return httpx.Response(401, json={"error": {"code": "Unauthorized", "message": "secret-error-payload"}})

    monkeypatch.setenv("CYBEREYE_OPENAI_ENDPOINT", "https://fixture.openai.azure.com/openai/v1/")
    monkeypatch.setattr(azure.identity.aio, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(handle))
    result = await prompt_live.prompt_live(allow_model_calls=True)
    assert result["status"] == "refusal"
    assert len(result["trials"]) == 1
    assert result["model_request_count"] == 1
    assert result["requests"][0]["http_status"] == 401
    assert result["requests"][0]["provider_error_code"] == "Unauthorized"
    assert result["source_unchanged"] and result["original_local_state_unchanged"]
    assert result["temporary_candidate_state_removed"] and closed == [True]
    assert "secret-error-payload" not in json.dumps(result)
    assert "offline-not-a-real-token" not in json.dumps(result)
    assert result["failure"]["category"] == "auth"