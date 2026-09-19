import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

import httpx
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "optimization_framework/adapters/investigation/adapter.py"
MODULE_SPEC = importlib.util.spec_from_file_location("investigation_adapter", MODULE)
adapter = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(adapter)
sys.path.insert(0, str(adapter.APP))


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("CYBEREYE_ALLOW_MODEL_CALLS", "false")
    monkeypatch.setenv("CYBEREYE_AGENT_STORE_DIR", str(tmp_path / "settings-agents"))

    def refuse(*args, **kwargs):
        raise AssertionError("network refused: native fixture tests must use MockTransport")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def record(task, detail):
    output = os.environ.get("INVESTIGATION_TASK_EVIDENCE")
    if output:
        path = Path(output)
        records = json.loads(path.read_text()) if path.exists() else {}
        records[task] = {"status": "offline_native_passed", **detail}
        path.write_text(json.dumps(records, indent=2) + "\n")


class FixtureAdx:
    def __init__(self):
        self.calls = []

    async def parameterized(self, query, params, max_rows):
        from app.cybereye.backend.models import QueryResponse

        self.calls.append({"query": query, "params": params, "max_rows": max_rows})
        return QueryResponse(columns=["product", "event_type", "event_count"],
                             rows=[["fixture-product", "fixture-event", 2]], row_count=1,
                             truncated=False, max_rows=max_rows, elapsed_ms=1,
                             client_request_id="offline-investigation")


def arguments(max_rows=2):
    return {"host": "fixture-host", "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T01:00:00Z", "max_rows": max_rows}


async def native_run(spec, *, name="profile_host_activity", params=None, refused=False):
    from app.cybereye.backend.agents.service import AgentService
    from app.cybereye.tests.test_native_agent import completion
    from llm_interface import Limits, LlmError, connect

    requests = []
    adx = FixtureAdx()

    async def handle(request):
        assert request.url.host == "fixture.invalid"
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            assert {tool["function"]["name"] for tool in body["tools"]} == {
                tool.metadata.name for tool in spec.tools}
            for tool in spec.tools:
                advertised = next(item["function"] for item in body["tools"] if item["function"]["name"] == tool.metadata.name)
                assert advertised["parameters"] == tool.metadata.parameters
            assert any(message.get("content") == spec.instructions for message in body["messages"])
            return completion([({"role": "assistant", "tool_calls": [{"index": 0, "id": "call-real-tool",
                "type": "function", "function": {"name": name, "arguments": json.dumps(params or arguments())}}]}, None),
                ({}, "tool_calls")])
        assert len(requests) == 2
        assert any(message["role"] == "tool" for message in body["messages"])
        return completion([({"role": "assistant", "content": "Fixture evidence only."}, None), ({}, "stop")])

    async with connect("https://fixture.invalid/v1", spec.model, provider="openai_completions",
                       credential="offline-fixture", allow_model_calls=True,
                       allowed_tools=tuple(tool.metadata.name for tool in spec.tools),
                       limits=Limits(max_output_tokens=spec.max_output_tokens),
                       transport=httpx.MockTransport(handle)) as model:
        service = AgentService(adx, SimpleNamespace(), spec, connection=model)
        session = service.create_session(principal="fixture-owner")
        frames = []

        async def consume():
            async for frame in service.stream_turn("Read fixture host history", principal="fixture-owner",
                                                   session=session, situation=None):
                frames.append(frame)

        if refused:
            with pytest.raises(LlmError):
                await consume()
            assert len(requests) == 1
            assert adx.calls == []
            assert session.result(principal="fixture-owner") is None
        else:
            await consume()
            assert len(requests) == 2 and len(adx.calls) == 1
            assert session.result(principal="fixture-owner").text == "Fixture evidence only."
            with pytest.raises(LlmError):
                session.result(principal="foreign-owner")
            assert frames[-1][0] == "done"
    return adx, requests, frames


@pytest.mark.asyncio
async def test_tool_availability_native_selection_dispatch_and_assignment(tmp_path):
    from app.cybereye.backend.agents.config import load_agent_spec
    from app.cybereye.backend.agents.editor import AgentEditor, INVESTIGATOR_TOOLS
    from app.cybereye.backend.agents.library import AssignInvestigator, LibraryError, SaveAgent
    from app.cybereye.backend.security.principal import Principal

    config = adapter.copy_control(tmp_path / "control")
    baseline = load_agent_spec(config)
    await native_run(baseline)
    adapter.select_tools(config, remove=("profile_host_activity",))
    removed = load_agent_spec(config)
    await native_run(removed, refused=True)
    adapter.select_tools(config, add=("profile_host_activity",))
    restored = load_agent_spec(config)
    await native_run(restored)
    assert {tool.metadata.name for tool in restored.tools} == {tool.metadata.name for tool in baseline.tools}
    adapter.select_tools(config, remove=("profile_host_activity", "get_dns_activity"))
    adapter.select_tools(config, add=("get_dns_activity",))
    replaced = load_agent_spec(config)
    await native_run(replaced, name="get_dns_activity", params={
        "source_address": "192.0.2.1", "start": arguments()["start"], "end": arguments()["end"], "max_rows": 2})
    await native_run(replaced, refused=True)
    assert INVESTIGATOR_TOOLS <= {tool.metadata.name for tool in replaced.tools}
    editor = AgentEditor(tmp_path / "agents", baseline)
    owner = Principal("fixture-owner", issuer="local-preview")
    original = editor.library.assignment(owner)
    draft = SaveAgent(name="Optional selection", model=baseline.model,
                      system_prompt=baseline.instructions,
                      tool_ids=[tool.metadata.name for tool in removed.tools])
    saved = editor.library.save(owner, draft)
    assigned = editor.library.assign(owner, AssignInvestigator(agent_id=saved.agent_id, version=1,
                                                              expected_revision=original.revision))
    restarted = AgentEditor(tmp_path / "agents", baseline)
    assert restarted.library.get(owner, saved.agent_id, 1) == saved
    assert restarted.library.assignment(owner) == assigned
    assert "profile_host_activity" not in {tool.metadata.name for tool in restarted.investigator_spec(owner).tools}
    refusals = []
    for required in sorted(INVESTIGATOR_TOOLS):
        invalid = editor.library.save(owner, draft.model_copy(update={
            "tool_ids": [name for name in draft.tool_ids if name != required]}))
        with pytest.raises(LibraryError, match="Investigator requires") as error:
            editor.library.assign(owner, AssignInvestigator(agent_id=invalid.agent_id, version=1,
                                                            expected_revision=assigned.revision))
        assert error.value.status == 422
        assert editor.library.assignment(owner) == assigned
        assert editor.library.get(owner, saved.agent_id, 1) == saved
        refusals.append(required)
    record("tool_availability", {"variants": ["baseline", "remove", "add_registered", "replace_selection"],
        "required_refusals": refusals, "saved_version_readback": True,
        "config_digests": [spec.config_digest for spec in (baseline, removed, restored, replaced)],
        "candidate_control_hashes": adapter.tree_hashes(config.parent)})


@pytest.mark.asyncio
async def test_tool_definition_real_callable_wrapper_and_native_schema(tmp_path):
    from app.cybereye.backend.agents.config import load_agent_spec
    from app.cybereye.backend.agents.tools.base import ToolContext

    baseline = load_agent_spec(adapter.copy_control(tmp_path / "control"))
    candidate = adapter.definition_candidate(baseline)
    await native_run(baseline, params=arguments(3))
    adx, requests, frames = await native_run(candidate)
    result = next(data["result"] for event, data in frames if event == "tool_result")
    assert result["candidate_definition"] == "investigation-row-cap-v1"
    assert result["candidate_implementation_sha256"] == adapter.sha256(MODULE)
    assert result["historical_replay"] is True
    assert result["scope"]["host"] == "fixture-host" and result["scope"]["max_rows"] == 2
    assert result["rows"] == [{"product": "fixture-product", "event_type": "fixture-event", "event_count": 2}]
    assert adx.calls[0]["params"]["host"] == "fixture-host"
    assert "target_host_name" in adx.calls[0]["query"] and "summarize event_count=count()" in adx.calls[0]["query"]
    await native_run(candidate, params=arguments(3), refused=True)
    function = next(tool.function for tool in candidate.tools if tool.metadata.name == "profile_host_activity")
    direct = FixtureAdx()
    with pytest.raises(ValueError, match="end must be after start"):
        await function(ToolContext(direct, SimpleNamespace()), **{**arguments(), "end": arguments()["start"]})
    with pytest.raises(ValueError, match="candidate max_rows"):
        await function(ToolContext(direct, SimpleNamespace()), **arguments(3))
    assert direct.calls == []
    record("tool_definition", {"candidate_kind": "callable_wrapper", "production_source_change": False,
        "implementation_sha256": adapter.sha256(MODULE),
        "real_tool_sha256": adapter.sha256(adapter.APP / "app/cybereye/backend/agents/tools/activity.py"),
        "observed_result": result, "schema_max_rows": 2, "invalid_input_refused_before_data": True})


@pytest.mark.asyncio
async def test_prompt_copy_digest_and_native_delivery_not_model_behavior(tmp_path):
    from app.cybereye.backend.agents.config import load_agent_spec

    source = adapter.APP / "app/cybereye/control"
    original = adapter.tree_hashes(source)
    config = adapter.copy_control(tmp_path / "control")
    baseline = load_agent_spec(config)
    contract = yaml.safe_load((adapter.TASKS / "prompt.yaml").read_text())
    prompt = config.parent / "prompts/cyber/cyber_defender.md"
    prompt.write_text(prompt.read_text() + "\n\n" + contract["instruction"] + "\n")
    candidate = load_agent_spec(config)
    assert candidate.config_digest != baseline.config_digest
    assert candidate.instructions != baseline.instructions
    assert candidate.foundation_files == baseline.foundation_files
    assert candidate.tools == baseline.tools
    adx, requests, frames = await native_run(candidate)
    assert contract["instruction"] in candidate.instructions
    assert any("fixture-product" in message.get("content", "")
               for message in requests[-1]["messages"] if message["role"] == "tool")
    assert adapter.tree_hashes(source) == original
    record("prompt", {"behavior_acceptance": "pending_model_trials",
        "observation": "native request delivery and fixture evidence only; not prompt behavioral proof",
        "baseline_config_digest": baseline.config_digest, "candidate_config_digest": candidate.config_digest,
        "baseline_instructions_sha256": hashlib.sha256(baseline.instructions.encode()).hexdigest(),
        "candidate_instructions_sha256": hashlib.sha256(candidate.instructions.encode()).hexdigest(),
        "candidate_control_hashes": adapter.tree_hashes(config.parent)})


def test_task_contracts_and_source_pin_refusal(tmp_path):
    contracts = {path.stem: yaml.safe_load(path.read_text()) for path in adapter.TASKS.glob("*.yaml")}
    assert len(contracts) == 4
    assert contracts["suspect_profile"]["status"] == "offline_native_passed"
    refused = adapter.verify(sys.executable, tmp_path / "artifacts", {"wrong": "digest"})
    assert refused["status"] == "failed" and "source pins changed" in refused["error"]
    assert refused["commands"] == []
    with pytest.raises(ValueError, match="outside checkout"):
        adapter.verify(sys.executable, adapter.REPO / "forbidden-artifacts")