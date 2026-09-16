from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.cybereye.backend.agents.config import CONFIG_PATH, ConfigError, describe_agent, load_agent_spec
from app.cybereye.backend.models import QueryResponse
from app.cybereye.backend.agents.tools.activity import get_authentication_activity
from app.cybereye.backend.agents.tools.base import ToolContext
from app.cybereye.backend.agents.tools.raw_kql import query_events_kql


class AgentConfigurationTests(unittest.TestCase):
    def test_composes_prompts_model_tools_and_display_names(self) -> None:
        spec = load_agent_spec()
        self.assertEqual(spec.agent_id, "cyber_defender")
        self.assertEqual(spec.model, "gpt-5.6-luna")
        self.assertEqual(len(spec.tools), 11)
        self.assertEqual(spec.reasoning_effort, "high")
        self.assertEqual(spec.reasoning_summary, "auto")
        self.assertEqual(spec.reasoning_request(), {"effort": "high"})
        self.assertEqual(spec.reasoning_request(summarize=True),
                         {"effort": "high", "summary": "auto"})
        self.assertEqual(spec.max_output_tokens, 1600)
        self.assertEqual(spec.diagnosis_max_tool_iterations, 10)
        self.assertEqual(spec.diagnosis_max_output_tokens, 2600)
        self.assertTrue(spec.parallel_tool_calls)
        self.assertLess(spec.instructions.index("# Historical replay boundary"),
                        spec.instructions.index("# Tool selection policy"))
        self.assertLess(spec.instructions.index("# Tool selection policy"),
                        spec.instructions.index("# CyberDefender"))
        self.assertEqual(spec.tools[0].metadata.name, "scan_situations")
        self.assertEqual(spec.tools[0].display_name, "Scan situations")
        self.assertTrue(all(tool.openai_schema()["strict"] for tool in spec.tools))

    def test_loaded_tools_declare_their_datasources_without_changing_model_schemas(self) -> None:
        tools = load_agent_spec().tools
        sources = {tool.metadata.name: tool.metadata.datasource for tool in tools}
        self.assertEqual(sources["search_mitre_attack"], "search")
        for name in ("record_situation_diagnosis", "record_sequence_step", "complete_sequence_of_events"):
            self.assertEqual(sources.pop(name), "none")
        sources.pop("search_mitre_attack")
        self.assertEqual(set(sources.values()), {"adx"})
        self.assertTrue(all("datasource" not in tool.openai_schema() for tool in tools))

    def test_purpose_built_tools_precede_explicit_fallback(self) -> None:
        spec = load_agent_spec()
        fallback = [tool for tool in spec.tools if tool.metadata.fallback]
        self.assertEqual([tool.metadata.name for tool in fallback], ["query_events_kql"])
        self.assertIs(spec.tools[-1], fallback[0])
        self.assertIn("only when no purpose-built tool", fallback[0].metadata.description)
        self.assertIn("Purpose-built tools are preferred", spec.instructions)

    def test_catalogue_uses_loaded_tools_and_function_only_source(self) -> None:
        spec = load_agent_spec()
        catalogue = describe_agent(spec, {"adx": {"kind": "adx", "target": "Other.Events"}})
        self.assertEqual(catalogue["config_digest"], spec.config_digest)
        self.assertEqual(len(catalogue["tools"]), len(spec.tools))
        tool = next(item for item in catalogue["tools"] if item["id"] == "get_authentication_activity")
        self.assertEqual(tool["datasource"]["target"], "Other.Events")
        self.assertEqual(tool["source"]["path"], "app/cybereye/backend/agents/tools/activity.py")
        self.assertTrue(tool["source"]["available"])
        self.assertIn("def get_authentication_activity(", tool["source"]["code"])
        self.assertNotIn("def get_dns_activity(", tool["source"]["code"])
        self.assertGreater(tool["source"]["start_line"], 0)
        self.assertFalse(tool["source"]["truncated"])
        self.assertIn("host", tool["parameters"]["required"])

    def test_catalogue_never_previews_code_outside_registered_tools(self) -> None:
        spec = load_agent_spec()
        outside = replace(spec.tools[0], function=lambda: {})
        catalogue = describe_agent(replace(spec, tools=(outside,)), {})
        self.assertFalse(catalogue["tools"][0]["source"]["available"])
        self.assertEqual(catalogue["tools"][0]["source"]["code"], "")
        self.assertEqual(catalogue["tools"][0]["datasource"]["kind"], "unknown")
        self.assertEqual(catalogue["tools"][0]["datasource_ids"], [])

    def test_catalogue_supports_multiple_exact_source_dependencies(self) -> None:
        spec = load_agent_spec()
        tool = replace(spec.tools[0], metadata=replace(
            spec.tools[0].metadata, datasource=("adx", "search", "adx"),
        ))
        catalogue = describe_agent(replace(spec, tools=(tool,)), {
            "adx": {"kind": "adx", "source_ids": ["telemetry.events", "telemetry.events"]},
            "search": {"kind": "search", "source_ids": ["knowledge.index"]},
        })
        entry = catalogue["tools"][0]
        self.assertEqual(entry["datasource_ids"], ["telemetry.events", "knowledge.index"])
        self.assertEqual([source["kind"] for source in entry["datasources"]], ["adx", "search"])
        self.assertEqual(entry["datasource"], entry["datasources"][0])

    def test_output_tools_have_no_source_dependencies(self) -> None:
        catalogue = describe_agent(load_agent_spec(), {"none": {"kind": "none"}})
        tools = [tool for tool in catalogue["tools"] if tool["datasource"]["kind"] == "none"]
        self.assertEqual(len(tools), 3)
        self.assertTrue(all(tool["datasource_ids"] == [] for tool in tools))

    def test_import_outside_tools_prefix_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "control"
            shutil.copytree(CONFIG_PATH.parent, control)
            fragment = control / "agents" / "cyber.yaml"
            text = fragment.read_text(encoding="utf-8")
            fragment.write_text(text.replace(
                "app.cybereye.backend.agents.tools.scanner:scan_situations",
                "app.cybereye.backend.scanner:Scanner",
            ), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "outside allowed prefix"):
                load_agent_spec(control / "agent_config.yaml")

    def test_non_target_model_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "control"
            shutil.copytree(CONFIG_PATH.parent, control)
            fragment = control / "agents" / "cyber.yaml"
            text = fragment.read_text(encoding="utf-8")
            fragment.write_text(text.replace("gpt-5.6-luna", "gpt-other"), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "model must be gpt-5.6-luna"):
                load_agent_spec(control / "agent_config.yaml")

    def test_prompt_path_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "control"
            shutil.copytree(CONFIG_PATH.parent, control)
            config = control / "agent_config.yaml"
            text = config.read_text(encoding="utf-8")
            config.write_text(text.replace(
                "foundation/historical_replay.md", "../../outside.md"
            ), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "escapes"):
                load_agent_spec(config)

    def test_duplicate_yaml_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "agent_config.yaml"
            config.write_text("version: 1\nversion: 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "duplicate YAML key"):
                load_agent_spec(config)


class FakeAdx:
    def __init__(self) -> None:
        self.query_text = ""
        self.params: dict[str, Any] = {}

    async def parameterized(self, query: str, params: dict[str, Any], max_rows: int) -> QueryResponse:
        self.query_text = query
        self.params = params
        return QueryResponse(
            columns=["event_id", "event_count"], rows=[["4624", 2]], row_count=1,
            truncated=False, max_rows=max_rows, elapsed_ms=1, client_request_id="test",
        )

    async def query(self, query: str, max_rows: int) -> QueryResponse:
        self.query_text = query
        return QueryResponse(
            columns=["n"], rows=[[1]], row_count=1, truncated=False,
            max_rows=max_rows, elapsed_ms=1, client_request_id="test",
        )


class PurposeBuiltToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.adx = FakeAdx()
        self.context = ToolContext(adx=self.adx, scanner=object())  # type: ignore[arg-type]

    async def test_authentication_tool_binds_scope_and_returns_bounded_envelope(self) -> None:
        result = await get_authentication_activity(
            self.context, host="svpmn082", start="2026-08-13T02:30:00Z",
            end="2026-08-13T03:40:59Z", max_rows=25,
        )
        self.assertIn("win_event_id in", self.adx.query_text)
        self.assertEqual(self.adx.params["host"], "svpmn082")
        self.assertEqual(result["category"], "authentication")
        self.assertEqual(result["scope"]["max_rows"], 25)
        self.assertEqual(result["rows"], [{"event_id": "4624", "event_count": 2}])
        self.assertFalse(result["fallback"])

    async def test_raw_kql_remains_available_and_annotated_as_fallback(self) -> None:
        result = await query_events_kql(
            self.context, query="EventsUnified | summarize n=count()", max_rows=10,
        )
        self.assertEqual(result["category"], "raw_kql_fallback")
        self.assertEqual(result["scope"]["reason"], "no_purpose_built_tool_fit")
        self.assertTrue(result["fallback"])


if __name__ == "__main__":
    unittest.main()
