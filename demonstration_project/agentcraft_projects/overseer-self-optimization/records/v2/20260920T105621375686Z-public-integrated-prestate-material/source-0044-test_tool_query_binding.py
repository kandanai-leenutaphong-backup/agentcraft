"""Every tool-declared query reaches ADX bound to the configured table.

A tool that forgets `bind()` ships KQL still carrying the literal `{TABLE}`. That is not a
syntax error anywhere in the tool layer: it is caught only by the read-only guard inside
`ReadOnlyAdx`, at runtime, on the deployed system, on every call. `get_privileged_session_activity`
shipped that way, so these tests drive the real guard rather than a stub of it.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from azdata import ContentValue, ItemResult, OperationResult, ResourceAddress

from app.cybereye.backend.data.adx import ReadOnlyAdx
from app.cybereye.backend.config import settings

from app.cybereye.backend.agents.tools import activity, base
from app.cybereye.backend.agents.tools.base import ToolContext

TOOLS_DIR = Path(base.__file__).parent
PLACEHOLDER = "{TABLE}"

#: One representative call per ADX-querying tool. A new tool belongs here too.
TOOL_CALLS: tuple[tuple[Any, dict[str, Any]], ...] = (
    (activity.profile_host_activity, {"host": "svpmn082"}),
    (activity.get_authentication_activity, {"host": "svpmn082"}),
    (activity.get_privileged_session_activity, {"host": "svpmn082"}),
    (activity.get_dns_activity, {"source_address": "10.20.30.40"}),
)


class _Connector:
    """Stands in for the Kusto client so the guard runs but the network does not."""

    def __init__(self) -> None:
        self.query_text = ""
        self.params: dict[str, Any] = {}

    async def query(self, request):
        self.query_text = request.expression
        self.params = dict(request.parameters)
        return OperationResult(request.request_id, "query", "adx", ResourceAddress({"database": "Fixture"}), "success",
            items=(ItemResult(0, None, "success", ContentValue({"source_time": "2026-08-13T02:31:00Z"})),),
            metadata={"columns": [[{"name": "source_time", "type": "datetime"}]]}, metrics={"attempts": 1})


class GuardedAdx(ReadOnlyAdx):
    """The real `ReadOnlyAdx`, over a stubbed connector: same guard, same bounding, no network."""

    def __init__(self) -> None:  # deliberately does not call super(): that would build a Kusto client
        super().__init__(credential=SimpleNamespace(get_token=lambda *args: None))
        self.connector = _Connector()  # type: ignore[assignment]


class ToolQueryBindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.adx = GuardedAdx()
        self.context = ToolContext(adx=self.adx, scanner=object())  # type: ignore[arg-type]

    async def _invoke(self, tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
        return (await tool(self.context, start="2026-08-13T02:30:00Z", end="2026-08-13T03:40:59Z",
                    max_rows=10, **arguments))

    async def test_privileged_session_query_survives_the_read_only_guard(self) -> None:
        """The exact failure: an unbound query raised on every call, so 0 rows ever returned."""
        result = (await self._invoke(activity.get_privileged_session_activity, {"host": "svpmn082"}))

        emitted = self.adx.connector.query_text
        self.assertNotIn(PLACEHOLDER, emitted)
        self.assertTrue(emitted.startswith(settings.table), emitted[:80])
        self.assertIn('product == "CYBERARK"', emitted)
        self.assertEqual(self.adx.connector.params["host"], "svpmn082")
        self.assertEqual(result["category"], "privileged_session")

    async def test_every_adx_tool_emits_a_query_the_guard_accepts(self) -> None:
        for tool, arguments in TOOL_CALLS:
            with self.subTest(tool=tool.__name__):
                (await self._invoke(tool, arguments))
                emitted = self.adx.connector.query_text
                self.assertNotIn(PLACEHOLDER, emitted)
                self.assertTrue(emitted.startswith(settings.table), emitted[:80])

    async def test_unbound_placeholder_is_rejected_by_the_guard(self) -> None:
        """The negative case: proves the assertions above are not passing vacuously."""
        with self.assertRaisesRegex(ValueError, "read-only"):
            (await self.adx.parameterized(f"{PLACEHOLDER}\n| count", {}, 10))


class TablePlaceholderIsAlwaysBoundTests(unittest.IsolatedAsyncioTestCase):
    """`{TABLE}` outside base.py must be lexically inside a `bind(...)` call, with no exceptions."""

    @staticmethod
    def _unbound_placeholders(source: str) -> list[int]:
        tree = ast.parse(source)
        bound: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bind":
                bound.update(id(inner) for inner in ast.walk(node) if isinstance(inner, ast.Constant))
        return [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and PLACEHOLDER in node.value and id(node) not in bound
        ]

    def test_no_module_declares_an_unbound_table_placeholder(self) -> None:
        offenders: dict[str, list[int]] = {}
        for path in sorted(TOOLS_DIR.glob("*.py")):
            if path.name == "base.py":  # defines bind() and names the token to substitute
                continue
            lines = self._unbound_placeholders(path.read_text(encoding="utf-8"))
            if lines:
                offenders[path.name] = lines
        self.assertEqual(offenders, {}, f"unbound {PLACEHOLDER} literals: {offenders}")

    def test_the_check_detects_the_defect_it_exists_to_catch(self) -> None:
        """The negative case, written as the shipped bug: `query = '{TABLE}...'` with no bind()."""
        self.assertEqual(
            self._unbound_placeholders('def t():\n    query = """{TABLE}\n| count"""\n'), [2],
        )
        self.assertEqual(
            self._unbound_placeholders('def t():\n    query = bind("""{TABLE}\n| count""")\n'), [],
        )


if __name__ == "__main__":
    unittest.main()
