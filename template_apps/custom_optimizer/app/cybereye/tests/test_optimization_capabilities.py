import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from azdata import ConfigurationError, DataConnector, HttpResponse, Limits, Policy

from app.cybereye.backend.knowledge import Knowledge, describe_capabilities


def test_discovery_uses_real_source_and_tool_registries_without_expanding_access():
    knowledge = Knowledge("https://example.search.windows.net", "attack-reference", SimpleNamespace(get_token=Mock()))
    dataset = {"dataset_id": "fixture", "features": ["category"], "counts": {"evidence": 9}}
    experiment = {"workflow": {"version": 1}, "versions": [{"version": 1, "knowledge_access": True}, {"version": 2, "knowledge_access": False}]}
    result = describe_capabilities(dataset, experiment, knowledge)
    assert {source["id"] for source in result["sources"]} == {
        "guide.sqlite.evidence", "guide.sqlite.training_profile", "guide.sqlite.labels", "cyberkb.search.mitre_attack"}
    assert {tool["name"] for tool in result["tools"]} == {"search_mitre_attack"}
    sources = {source["id"]: source for source in result["sources"]}
    assert sources["guide.sqlite.evidence"]["access"] == "development_only"
    assert sources["guide.sqlite.labels"]["access"] == "evaluator_only"
    assert sources["guide.sqlite.labels"]["operations"] == []
    assert not any(source["type"] in {"adx_table", "gremlin_graph"} for source in sources.values())
    assert sources["cyberkb.search.mitre_attack"]["operations"] == ["./opt knowledge"]
    assert result["knowledge"]["enabled_agent_versions"] == [1]
    callable_tools = [tool for tool in result["tools"] if tool["callable"]]
    assert [tool["name"] for tool in callable_tools] == ["search_mitre_attack"]
    assert callable_tools[0]["source_ids"] == ["cyberkb.search.mitre_attack"]
    assert "question" in callable_tools[0]["parameters"]["properties"]
    assert len(json.dumps(result).encode()) < 131072
    experiment.pop("workflow")
    result = describe_capabilities(dataset, experiment, knowledge)
    assert not any(tool["callable"] for tool in result["tools"])
    assert next(source for source in result["sources"] if source["id"] == "cyberkb.search.mitre_attack")["operations"] == []


@pytest.mark.asyncio
async def test_canonical_knowledge_preserves_projection_relaxation_and_scored_rows():
    credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)), close=Mock())
    hit = {"doc_id": "T1001", "title": None, "summary": "  discovery ", "body": " evidence  ",
           "technique_ids": ["T1001"], "path": "source.yaml", "commit": "a" * 40,
           "license": "fixture", "attack_url": None, "@search.score": 1.234567}
    transport = SimpleNamespace(request=AsyncMock(side_effect=[HttpResponse(200, {"value": []}),
                            HttpResponse(200, {"value": [hit]}), HttpResponse(200, {"value": [hit]})]), aclose=AsyncMock())
    knowledge = Knowledge("https://unit.search.windows.net", "fixture", credential, transport=transport,
                           policy=Policy("optimizer-offline", max_concurrency=1, limits=Limits(max_attempts=1)))
    assert isinstance(knowledge.client, DataConnector)
    try:
        arguments = {"question": " ", "technique_ids": ["t9999"], "behaviour_classes": ["discovery"], "max_results": 1}
        result = await knowledge.search(arguments)
        repeated = await knowledge.search({"question": "discovery", "max_results": 1})
        assert result["rows"] == repeated["rows"] == [{"doc_id": "T1001", "title": None,
            "technique_ids": ["T1001"], "path": "source.yaml", "commit": "a" * 12,
            "license": "fixture", "attack_url": None, "snippet": "discovery evidence", "score": 1.2346}]
        assert result["scope"]["relaxed_filters"] == ["technique_ids"]
        requests = [call.args[0] for call in transport.request.call_args_list]
        assert requests[0].body["filter"] == "doc_kind eq 'analytic' and technique_ids/any(v: search.in(v, 'T9999', ',')) and behaviour_class/any(v: search.in(v, 'discovery', ','))"
        assert requests[1].body["filter"] == "doc_kind eq 'analytic' and behaviour_class/any(v: search.in(v, 'discovery', ','))"
        assert requests[0].body["search"] == "*"
        assert requests[0].body["select"] == "doc_id,title,summary,body,technique_ids,path,commit,license,attack_url"
    finally:
        await knowledge.aclose()
        await knowledge.aclose()
    credential.close.assert_not_called()
    transport.aclose.assert_not_called()


@pytest.mark.parametrize("response", [HttpResponse(403), HttpResponse(429), HttpResponse(500)])
@pytest.mark.asyncio
async def test_canonical_failure_is_unavailable_without_relaxation(response):
    transport = SimpleNamespace(request=AsyncMock(return_value=response))
    credential = SimpleNamespace(get_token=lambda *args: SimpleNamespace(token="offline", expires_on=2**31))
    knowledge = Knowledge("https://unit.search.windows.net", "fixture", credential, transport=transport)
    try:
        result = await knowledge.search({"question": "x", "technique_ids": ["T9999"]})
        assert result["category"] == "mitre_attack_unavailable"
        assert result["rows"] == []
        assert transport.request.call_count == 1
    finally:
        await knowledge.aclose()


def test_configured_credentialless_knowledge_refuses_without_ambient_fallback():
    transport = SimpleNamespace(request=AsyncMock(side_effect=AssertionError("service touched")))
    with pytest.raises(ConfigurationError, match="injected token credential"):
        Knowledge("https://unit.search.windows.net", "fixture", None, transport=transport)
    transport.request.assert_not_called()