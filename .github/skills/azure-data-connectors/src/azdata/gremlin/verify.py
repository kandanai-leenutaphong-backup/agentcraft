"""Gremlin verify plane — a vertex id is the addressable unit.

WHY THIS EXISTS
---------------
Edges are deliberately not part of the key space. A vertex drop takes its
edges with it, so counting edges as addressable items would report one
delete as many removals and make every delta unreadable. Edge counts are a
stat, reported by ``gremlin/observe.py``; vertices are the state.

Enumeration goes through the read-only connector like every other
traversal, with an explicit ``.limit()`` so the guardrail's injected cap
cannot silently replace this module's own bound.

DEPENDENCIES
------------
Standard library. The connector loads ``gremlinpython`` on first use.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from azdata.core.config import DEFAULT_VERIFY_MAX_KEYS, AzureDataConfig
from azdata.core.envelope import is_error


class GremlinVerifyError(RuntimeError):
    """A traversal that a snapshot depends on was refused or failed."""


class GremlinKeys:
    """Enumerate the vertex ids of one Cosmos DB graph.

    Args:
        connector: The read-only ``GremlinConnector``.
        key_field: Property carrying the caller's id. Defaults to the
            Gremlin element id itself.
        stats_provider: The graph's observe plane.
    """

    service = "gremlin"

    def __init__(
        self,
        *,
        connector: Any,
        database: str = "",
        graph: str = "",
        key_field: str = "id",
        stats_provider: Any = None,
        max_keys: int = DEFAULT_VERIFY_MAX_KEYS,
    ) -> None:
        self._connector = connector
        self._database = database
        self._graph = graph
        self._key_field = key_field
        self._stats = stats_provider
        self.max_keys = max_keys

    @classmethod
    def from_config(
        cls, config: AzureDataConfig, connector: Any, **kwargs: Any
    ) -> "GremlinKeys":
        kwargs.setdefault("database", config.gremlin_database)
        kwargs.setdefault("graph", config.gremlin_graph)
        kwargs.setdefault("max_keys", config.verify_max_keys)
        return cls(connector=connector, **kwargs)

    @property
    def target(self) -> str:
        return f"{self._database}/{self._graph}".strip("/")

    async def enumerate_keys(self, target: str | None = None) -> dict[str, str]:
        """Return ``{vertex id: property digest}``, capped."""
        rows = await self._traverse(
            f"g.V().valueMap(true).limit({self.max_keys + 1})"
        )
        keys: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            key = row.get(self._key_field)
            if key is None:
                continue
            keys[str(key)] = _property_digest(row, self._key_field)
        return keys

    async def count(self, target: str | None = None) -> int:
        rows = await self._traverse("g.V().count()")
        return int(rows[0]) if rows else -1

    async def stats(self, target: str | None = None) -> Any:
        if self._stats is None:
            return {}
        return await self._stats.stats(target)

    async def _traverse(self, traversal: str) -> list:
        payload = await self._connector.execute(traversal)
        if is_error(payload):
            raise GremlinVerifyError(
                json.loads(payload).get("detail", "traversal failed")
            )
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, list) else [parsed]


def _property_digest(row: Mapping[str, Any], key_field: str) -> str:
    """sha256 over a vertex's properties, excluding its identity."""
    payload = {
        name: value
        for name, value in row.items()
        if name not in (key_field, "id", "label")
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


__all__ = ["GremlinKeys", "GremlinVerifyError"]
