from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import agentconfig
import yaml

from app.cybereye.backend.agents.config import CONFIG_PATH, ConfigError, _resolve_callable, describe_agent, load_agent_spec
from app.cybereye.backend.models import QueryResponse
from app.cybereye.backend.agents.tools.activity import get_authentication_activity
from app.cybereye.backend.agents.tools.base import ToolContext, ToolMetadata, agent_tool, metadata
from app.cybereye.backend.agents.tools.raw_kql import query_events_kql


class AgentConfigurationTests(unittest.TestCase):
    def test_metadata_reuses_generic_stamp_without_wrapping_or_schema_inference(self) -> None:
        def function(context, **arguments):
            return arguments

        parameters = {"type": "object", "properties": {"evidence": {"type": "string"}},
                      "required": ["evidence"], "additionalProperties": False}
        decorated = agent_tool(name="probe", description="  Explicit description.  ",
                               parameters=parameters, category="test", fallback=True,
                               datasource=("adx", "search"))(function)
        self.assertIs(decorated, function)
        self.assertTrue(agentconfig.is_tool(function))
        value = metadata(function)
        self.assertIsInstance(value, ToolMetadata)
        self.assertIs(metadata(function), value)
        self.assertIs(agentconfig.tool_metadata(function)["cybereye"], value)
        self.assertFalse(hasattr(function, "__cybereye_tool__"))
        self.assertIs(value.parameters, parameters)
        self.assertEqual(value.openai_schema(), {
            "type": "function", "name": "probe", "description": "Explicit description.",
            "parameters": parameters, "strict": True,
        })
        self.assertEqual(function(None, evidence="test"), {"evidence": "test"})
        self.assertTrue(value.fallback)
        self.assertEqual(value.datasource, ("adx", "search"))

    def test_metadata_preserves_typed_refusal_for_missing_or_invalid_host_contract(self) -> None:
        for function in (lambda: {}, agentconfig.tool(lambda: {}),
                         agentconfig.tool(cybereye={"name": "not typed"})(lambda: {})):
            with self.subTest(function=function), self.assertRaisesRegex(TypeError, "no declarative CyberEye metadata"):
                metadata(function)

    def test_local_resolution_reuses_library_and_preserves_identity(self) -> None:
        spec = "app.cybereye.backend.agents.tools.activity:get_authentication_activity"
        with patch("app.cybereye.backend.agents.config.resolve_tool", wraps=agentconfig.resolve_tool) as resolve:
            self.assertIs(_resolve_callable(spec), get_authentication_activity)
        resolve.assert_called_once_with(spec, allowed_prefixes=("app.cybereye.backend.agents.tools.",))

    def test_local_guard_refuses_before_library_resolution(self) -> None:
        with patch("app.cybereye.backend.agents.config.resolve_tool") as resolve:
            for spec in ("@server:probe", "app.cybereye.backend.agents.tools_extra:probe",
                         "app.cybereye.backend.agents.tools:probe", "invalid",
                         "app.cybereye.backend.agents.tools.activity:"):
                with self.subTest(spec=spec), self.assertRaises(ConfigError):
                    _resolve_callable(spec)
        resolve.assert_not_called()

    def test_resolution_errors_remain_config_errors(self) -> None:
        for spec, message in (
            ("app.cybereye.backend.agents.tools.missing:probe", "cannot resolve"),
            ("app.cybereye.backend.agents.tools.activity:missing", "cannot resolve"),
            ("app.cybereye.backend.agents.tools.activity:__name__", "not callable"),
        ):
            with self.subTest(spec=spec), self.assertRaisesRegex(ConfigError, message):
                _resolve_callable(spec)

    def test_composes_prompts_model_tools_and_display_names(self) -> None:
        spec = load_agent_spec()
        self.assertEqual(spec.agent_id, "cyber_defender")
        self.assertEqual(spec.model, "gpt-5.6-luna")
        self.assertEqual(len(spec.tools), 13)
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
        for name in ("record_situation_diagnosis", "record_sequence_step", "complete_sequence_of_events",
                 "get_suspect_profile", "update_suspect_profile"):
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
        self.assertEqual(len(tools), 5)
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


class StrictConfigReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(agentconfig.invalidate_config_cache)
        self.control = Path(temporary.name) / "control"
        shutil.copytree(CONFIG_PATH.parent, self.control)
        self.config_path = self.control / CONFIG_PATH.name

    def update_base(self, **changes: Any) -> dict[str, Any]:
        document = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        document.update(changes)
        self.config_path.write_text(yaml.safe_dump(document), encoding="utf-8")
        agentconfig.invalidate_config_cache()
        return document

    def test_raw_digest_prompt_metadata_and_repeated_sources_match_legacy_order(self) -> None:
        base = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        empty = self.control / "agents" / "empty.yaml"
        empty.write_bytes(b"agents: {}\r\n")
        base = self.update_base(include=[*base["include"], "agents/empty.yaml", "agents/empty.yaml"],
                                foundation_prompts=[*base["foundation_prompts"], base["foundation_prompts"][0]])
        fragment = self.control / base["include"][0]
        fragment.write_bytes(fragment.read_bytes() + b"\r\n# source digest marker\r\n")
        definition = yaml.safe_load(fragment.read_text(encoding="utf-8"))["agents"][base["agents"]["default"]]
        refs = [*base["foundation_prompts"], *definition["instructions"]]
        prompts = [self.control / base["prompts_dir"] / ref for ref in refs]
        prompts[0].write_bytes(b" \r\n" + prompts[0].read_bytes().replace(b"\n", b"\r\n") + b"\r\n ")
        paths = [self.config_path, *(self.control / ref for ref in base["include"]), *prompts]
        expected_digest = hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()[:12]
        texts = [path.read_text(encoding="utf-8").strip() for path in prompts]
        spec = load_agent_spec(self.config_path)
        self.assertEqual(spec.config_digest, expected_digest)
        self.assertEqual(spec.instructions, "\n\n".join(texts))
        count = len(base["foundation_prompts"])
        self.assertEqual(spec.foundation_files, tuple((path.name, text) for path, text in zip(prompts[:count], texts[:count])))
        self.assertEqual(spec.instruction_files, tuple((path.name, text) for path, text in zip(prompts[count:], texts[count:])))
        sources: list[tuple[Path, bytes]] = []
        agentconfig.load_agent_config(self.config_path, strict=True, sources=sources)
        composed = agentconfig.load_instructions(refs, self.control / base["prompts_dir"], strict=True, sources=sources)
        self.assertEqual(composed, spec.instructions)
        self.assertEqual(sources, [(path, path.read_bytes()) for path in paths])

    def test_duplicate_yaml_stays_permissive_by_default_but_both_strict_callers_refuse(self) -> None:
        with self.config_path.open("a", encoding="utf-8") as output:
            output.write("\nversion: 1\n")
        self.assertEqual(agentconfig.load_agent_config(self.config_path)["version"], 1)
        with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
            agentconfig.load_agent_config(self.config_path, strict=True)
        with self.assertRaisesRegex(ConfigError, "duplicate YAML key"):
            load_agent_spec(self.config_path)

    def test_include_escape_stays_permissive_by_default_but_both_strict_callers_refuse(self) -> None:
        outside = self.control.parent / "outside.yaml"
        outside.write_text("agents: {outside_probe: {model: fixture}}\n", encoding="utf-8")
        self.update_base(include=["agents/cyber.yaml", "../outside.yaml"])
        self.assertIn("outside_probe", agentconfig.load_agent_config(self.config_path)["agents"])
        with self.assertRaisesRegex(ValueError, "escapes"):
            agentconfig.load_agent_config(self.config_path, strict=True)
        with self.assertRaisesRegex(ConfigError, "escapes"):
            load_agent_spec(self.config_path)
        (self.control / "agents" / "escape.yaml").symlink_to(outside)
        self.update_base(include=["agents/cyber.yaml", "agents/escape.yaml"])
        with self.assertRaisesRegex(ConfigError, "escapes"):
            load_agent_spec(self.config_path)

    def test_partial_foundation_load_is_legacy_only_and_strict_empty_grants_stay_empty(self) -> None:
        refs = ["foundation/historical_replay.md", "foundation/missing-probe.md"]
        self.update_base(foundation_prompts=refs)
        self.assertTrue(agentconfig.load_instructions(refs, self.control / "prompts"))
        with self.assertRaisesRegex(ValueError, "prompt not found"):
            agentconfig.load_instructions(refs, self.control / "prompts", strict=True)
        with self.assertRaisesRegex(ConfigError, "prompt not found"):
            load_agent_spec(self.config_path)
        self.assertEqual(agentconfig.load_instructions([], self.control / "prompts", strict=True), "")

    def test_strict_prompts_refuse_empty_directory_symlink_escape_and_missing_preamble(self) -> None:
        prompts = self.control / "prompts"
        (prompts / "empty.md").write_text(" \n", encoding="utf-8")
        outside = self.control.parent / "outside.md"
        outside.write_text("Outside prompt", encoding="utf-8")
        (prompts / "escape.md").symlink_to(outside)
        for ref in ("empty.md", "foundation", "escape.md", "", "missing.md"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                agentconfig.load_instructions(["foundation/historical_replay.md", ref], prompts, strict=True)
        with self.assertRaisesRegex(ValueError, "prompt not found"):
            agentconfig.load_instructions([], prompts, prompts / "missing.md", strict=True)
        self.update_base(foundation_prompts=["empty.md"])
        with self.assertRaisesRegex(ConfigError, "prompt is empty"):
            load_agent_spec(self.config_path)

    def test_display_collision_refuses_in_strict_mode_without_changing_default_merge(self) -> None:
        fragment = self.control / "agents" / "cyber.yaml"
        document = yaml.safe_load(fragment.read_text(encoding="utf-8"))
        document["tool_display_names"] = {"scan_situations": "Replacement"}
        fragment.write_text(yaml.safe_dump(document), encoding="utf-8")
        self.assertEqual(agentconfig.load_agent_config(self.config_path)["tool_display_names"]["scan_situations"],
                         "Replacement")
        with self.assertRaisesRegex(ConfigError, "duplicate tool display name"):
            load_agent_spec(self.config_path)

    def test_empty_tools_and_local_only_resolution_never_enter_server_factories(self) -> None:
        fragment = self.control / "agents" / "cyber.yaml"
        document = yaml.safe_load(fragment.read_text(encoding="utf-8"))
        definition = document["agents"]["cyber_defender"]
        definition["tools"] = []
        fragment.write_text(yaml.safe_dump(document), encoding="utf-8")
        self.assertEqual(load_agent_spec(self.config_path).tools, ())
        calls: list[dict[str, Any]] = []
        agentconfig.register_server_tool("strict_config_reuse_test", lambda parameters: calls.append(parameters))
        definition["tools"] = ["@server:strict_config_reuse_test"]
        fragment.write_text(yaml.safe_dump(document), encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "outside allowed prefix"):
            load_agent_spec(self.config_path)
        self.assertEqual(calls, [])
        with self.assertRaisesRegex(ValueError, "allowlist is currently empty"):
            agentconfig.resolve_tool("app.cybereye.backend.agents.tools.scanner:scan_situations", allowed_prefixes=())


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
