import json

from app.cybereye.backend.knowledge import Knowledge, describe_capabilities


def test_discovery_uses_real_source_and_tool_registries_without_expanding_access():
    knowledge = Knowledge("https://example.search.windows.net", "attack-reference", None)
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