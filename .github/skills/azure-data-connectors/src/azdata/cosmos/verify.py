"""Cosmos NoSQL verify plane — the id is the key, the etag is the version.

WHY THIS EXISTS
---------------
Cosmos hands out both halves of a state snapshot cheaply, which no other
service here does: ``_etag`` changes on every write to an item, so the
content digest costs nothing beyond projecting one more field.

Enumeration is ordered by id and capped at one past the limit. Ordered,
because ``SELECT TOP n`` without an ``ORDER BY`` is not a deterministic
sample — Cosmos may return a different n each call, and two snapshots that
sampled differently would report churn that never happened. One past,
because a result of exactly the cap must be distinguishable from a
truncated one.

DEPENDENCIES
------------
Standard library. The container comes from the caller.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from azdata.core.config import DEFAULT_VERIFY_MAX_KEYS, AzureDataConfig


class CosmosKeys:
    """Enumerate the item ids of one Cosmos container.

    Args:
        container: An async ``ContainerProxy``.
        key_field: The item id field. ``"id"`` in every Cosmos container,
            a parameter so no schema knowledge is baked in.
        stats_provider: The container's observe plane.
        max_keys: Enumeration cap. Defaults to ``AZDATA_VERIFY_MAX_KEYS``.
    """

    service = "cosmos"

    def __init__(
        self,
        *,
        container: Any,
        database: str = "",
        container_name: str = "",
        key_field: str = "id",
        stats_provider: Any = None,
        max_keys: int = DEFAULT_VERIFY_MAX_KEYS,
    ) -> None:
        self._container = container
        self._database = database
        self._container_name = container_name
        self._key_field = key_field
        self._stats = stats_provider
        self.max_keys = max_keys

    @classmethod
    def from_config(
        cls, config: AzureDataConfig, container: Any, **kwargs: Any
    ) -> "CosmosKeys":
        kwargs.setdefault("max_keys", config.verify_max_keys)
        return cls(container=container, **kwargs)

    @property
    def target(self) -> str:
        return f"{self._database}/{self._container_name}".strip("/")

    async def enumerate_keys(self, target: str | None = None) -> dict[str, str]:
        """Return ``{item id: etag}``, ordered by id and capped."""
        field = self._key_field
        query = (
            f"SELECT TOP {self.max_keys + 1} c.{field}, c._etag FROM c "
            f"ORDER BY c.{field}"
        )
        keys: dict[str, str] = {}
        async for row in self._container.query_items(query=query, parameters=[]):
            item_id = row.get(field) if hasattr(row, "get") else None
            if item_id is None:
                continue
            etag = row.get("_etag")
            keys[str(item_id)] = (
                str(etag) if etag is not None else _row_digest(row, field)
            )
        return keys

    async def count(self, target: str | None = None) -> int:
        rows = []
        async for row in self._container.query_items(
            query="SELECT VALUE COUNT(1) FROM c", parameters=[]
        ):
            rows.append(row)
        return int(rows[0]) if rows else -1

    async def stats(self, target: str | None = None) -> Any:
        if self._stats is None:
            return {}
        return await self._stats.stats(target)


def _row_digest(row: Any, key_field: str) -> str:
    """Fallback content digest for a container with no ``_etag`` projected."""
    payload = {
        name: value
        for name, value in dict(row).items()
        if not str(name).startswith("_") and name != key_field
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


__all__ = ["CosmosKeys"]
