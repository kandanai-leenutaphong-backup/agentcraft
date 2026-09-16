"""Offline contract checks; callable directly with the standard library runner."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from hostedagents import DefinitionError, ToolRegistry, load_definition
from toolshape import turn


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