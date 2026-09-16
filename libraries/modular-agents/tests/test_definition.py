"""Offline contract checks; callable directly with the standard library runner."""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from hostedagents import DefinitionError, ToolRegistry, load_definition
from toolshape import MemorySink, Param, ToolSpec, classify, one_of, purpose_built, set_sink, turn


_SHAPED_CALLS: list[str] = []
_PRIVATE_FAILURE = "credential=g3-fake-token prompt=g3-private-prompt path=/private/g3/input.txt"


def _shaped_result(mode: str):
    _SHAPED_CALLS.append(mode)
    if mode == "failure":
        raise RuntimeError(_PRIVATE_FAILURE)
    if mode == "missing":
        return None
    if mode == "empty":
        return []
    if mode == "cancelled":
        raise asyncio.CancelledError()
    return [{"value": "available"}]


def _shaped_spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name, purpose="Check native result preservation.",
        call_when="During offline tool contract checks.",
        params=[Param("mode", "Synthetic result mode.", validator=one_of(
            ("productive", "empty", "missing", "failure", "cancelled")))],
        dedupe_on=("mode",),
    )


@purpose_built(_shaped_spec("shaped_sync"))
def shaped_sync(mode: str):
    return _shaped_result(mode)


@purpose_built(_shaped_spec("shaped_async"))
async def shaped_async(mode: str):
    return _shaped_result(mode)


def credential_tool(token: str) -> dict:
    """An intentionally invalid tool contract used to prove credential refusal."""
    return {}


class DefinitionTests(unittest.TestCase):
    def load(self):
        return load_definition(ROOT / "examples/control", allowed_prefixes=("agent_tools.",))

    def test_configuration_preserves_the_prompt_model_and_tools(self):
        definition = self.load()
        self.assertEqual(definition.spec.model, "example-deployment")
        self.assertIn("Answer only from available evidence", definition.spec.instructions)
        self.assertIn("Cite note titles", definition.spec.instructions)
        self.assertEqual(definition.tools.names, ("list_topics", "search_notes"))
        schema = definition.tools.schemas[1]["function"]["parameters"]
        self.assertEqual(schema["properties"]["limit"]["type"], "integer")
        self.assertFalse(schema["additionalProperties"])

    def test_configuration_does_not_inherit_a_previous_import_grant(self):
        self.load()
        with self.assertRaises(ValueError):
            load_definition(ROOT / "examples/control")

    def test_sync_async_and_domain_refusal(self):
        tools = self.load().tools
        self.assertEqual(len(asyncio.run(tools.invoke("list_topics", {}))["rows"]), 3)
        self.assertEqual(len(asyncio.run(tools.invoke("search_notes", {"query": "hosting"}))["rows"]), 1)
        self.assertTrue(asyncio.run(tools.invoke("search_notes", {"query": "hosting", "limit": 9}))["refused"])

    def test_signature_refusals_do_not_execute_the_tool_body(self):
        tools = self.load().tools
        for arguments in ([], {}, {"query": "x", "limit": True}, {"query": "x", "extra": "x"}):
            with self.subTest(arguments=arguments):
                self.assertTrue(asyncio.run(tools.invoke("search_notes", arguments))["refused"])
        self.assertTrue(asyncio.run(tools.invoke("missing", {}))["refused"])

    def test_turn_ledger_survives_sync_thread_execution(self):
        async def calls():
            tools = self.load().tools
            with turn(run_id="test-turn"):
                first = await tools.invoke("search_notes", {"query": "hosting"})
                second = await tools.invoke("search_notes", {"query": "hosting"})
            return first, second

        first, second = asyncio.run(calls())
        self.assertEqual(len(first["rows"]), 1)
        self.assertTrue(second["duplicate"])

    def test_toolshape_results_share_the_direct_and_hosted_rule(self):
        async def calls(function, mode):
            registry = ToolRegistry((function,))
            with turn(run_id="direct"):
                direct = function(mode=mode)
                if inspect.isawaitable(direct):
                    direct = await direct
            with turn(run_id="hosted"):
                hosted = await registry.invoke(function.__toolspec__.name, {"mode": mode})
                repeat = await registry.invoke(function.__toolspec__.name, {"mode": mode})
            return json.loads(direct), hosted, repeat

        for function in (shaped_sync, shaped_async):
            for mode, expected in (("productive", "productive"), ("empty", "empty"),
                                   ("missing", "missing"), ("failure", "error"),
                                   ("invalid", "refused")):
                with self.subTest(tool=function.__name__, mode=mode):
                    _SHAPED_CALLS.clear()
                    sink = MemorySink()
                    previous = set_sink(sink)
                    try:
                        capture = (self.assertLogs("toolshape", level="WARNING") if mode == "failure"
                                   else self.assertNoLogs("toolshape", level="WARNING"))
                        with capture as logs:
                            direct, hosted, repeat = asyncio.run(calls(function, mode))
                    finally:
                        set_sink(previous)
                    self.assertEqual(hosted, direct)
                    self.assertEqual(classify(hosted), expected)
                    repeat_class = "refused" if mode == "invalid" else "duplicate"
                    self.assertEqual(classify(repeat), repeat_class)
                    self.assertEqual([record.result_class for record in sink.records],
                                     [expected, expected, repeat_class])
                    self.assertEqual(_SHAPED_CALLS, [] if mode == "invalid" else [mode, mode])
                    if mode == "missing":
                        self.assertEqual(hosted, {"missing": True})
                    if mode == "empty":
                        self.assertEqual(hosted["scope"]["row_count"], 0)
                    if mode == "failure":
                        self.assertEqual(hosted["code"], "tool_failed")
                        self.assertEqual(hosted["category"], "failed")
                        self.assertEqual(hosted["effect"], "unknown")
                        self.assertEqual(hosted["retry"], "read_back_first")
                        self.assertEqual(len(logs.records), 2)
                        self.assertTrue(all(record.exc_info is None and record.stack_info is None
                                            for record in logs.records))
                        observed = repr((hosted, logs.output, sink.records))
                        for sensitive in (*_PRIVATE_FAILURE.split(), "RuntimeError"):
                            self.assertNotIn(sensitive, observed)

    def test_toolshape_cancellation_propagates_through_hosted_invocation(self):
        async def cancelled(function):
            registry = ToolRegistry((function,))
            with self.assertRaises(asyncio.CancelledError):
                await registry.invoke(function.__toolspec__.name, {"mode": "cancelled"})

        for function in (shaped_sync, shaped_async):
            with self.subTest(tool=function.__name__):
                sink = MemorySink()
                previous = set_sink(sink)
                try:
                    with self.assertNoLogs("toolshape", level="WARNING"):
                        asyncio.run(cancelled(function))
                    self.assertEqual(sink.records, [])
                finally:
                    set_sink(previous)

    def test_duplicate_and_nonportable_tools_fail_during_build(self):
        from agent_tools.notes import search_notes

        with self.assertRaises(DefinitionError):
            ToolRegistry((search_notes, search_notes))
        with self.assertRaises(DefinitionError):
            ToolRegistry((lambda: None,))

    def test_headless_adapter_does_not_drop_interactive_approval_or_accept_credentials(self):
        import agentconfig
        from agent_tools.notes import list_topics

        metadata = getattr(list_topics, agentconfig.TOOL_MARKER)
        original = dict(metadata)
        try:
            metadata["approval_mode"] = "always_require"
            with self.assertRaisesRegex(DefinitionError, "interactive approval"):
                ToolRegistry((list_topics,))
        finally:
            metadata.clear()
            metadata.update(original)
        with self.assertRaisesRegex(DefinitionError, "credentials"):
            ToolRegistry((credential_tool,))


if __name__ == "__main__":
    unittest.main()