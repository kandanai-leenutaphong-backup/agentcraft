"""Kusto verify plane — an addressable key exists only where a caller names one.

WHY THIS EXISTS
---------------
Kusto has no primary key. A table is an append-only extent store, rows are
not individually addressable, and there is no update. So the key column is
a *parameter*: the caller names the column that identifies a row in their
schema, and this module enumerates it.

``changed`` is empty unless the caller also names content columns. That is
not a limitation being worked around — an immutable row that "changed" did
not change, it was re-ingested, and reporting it as a modification would be
a lie about how the service works.

Both the table and every column name are validated as plain identifiers
before interpolation. Nothing else from the caller reaches the query.

DEPENDENCIES
------------
Standard library. The connector loads ``azure-kusto-data`` on first use.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Sequence

from azdata.core.config import DEFAULT_VERIFY_MAX_KEYS, AzureDataConfig
from azdata.core.envelope import is_error

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class KustoVerifyError(RuntimeError):
    """A query a snapshot depends on was refused or failed."""


def _identifier(name: str, what: str) -> str:
    if not name or not _IDENTIFIER.match(name):
        raise KustoVerifyError(
            f"'{name}' is not a plain Kusto identifier and will not be "
            f"interpolated as a {what}"
        )
    return name


class KustoKeys:
    """Enumerate the key column of one Kusto table.

    Args:
        connector: A read-plane :class:`KqlConnector`. The queries below
            are ordinary tabular expressions and keep its guardrails.
        table: Table to snapshot.
        key_column: Column identifying a row in the caller's schema.
        content_columns: Columns whose values form the content digest.
            Empty means ``changed`` is never reported, which is the honest
            default for an append-only store.
    """

    service = "kusto"

    def __init__(
        self,
        *,
        connector: Any,
        table: str = "",
        key_column: str = "",
        content_columns: Sequence[str] = (),
        stats_provider: Any = None,
        max_keys: int = DEFAULT_VERIFY_MAX_KEYS,
    ) -> None:
        self._connector = connector
        self._table = table
        self._key_column = key_column
        self._content_columns = tuple(content_columns)
        self._stats = stats_provider
        self.max_keys = max_keys

    @classmethod
    def from_config(
        cls, config: AzureDataConfig, connector: Any, **kwargs: Any
    ) -> "KustoKeys":
        kwargs.setdefault("max_keys", config.verify_max_keys)
        return cls(connector=connector, **kwargs)

    @property
    def target(self) -> str:
        return self._table

    async def enumerate_keys(self, target: str | None = None) -> dict[str, str]:
        table = _identifier(target or self._table, "table")
        key = _identifier(self._key_column, "key column")
        projected = [key] + [
            _identifier(column, "content column") for column in self._content_columns
        ]
        rows = await self._query(
            f"{table} | project {', '.join(projected)} "
            f"| order by {key} asc | take {self.max_keys + 1}"
        )
        keys: dict[str, str] = {}
        for row in rows:
            value = row.get(key)
            if value is None:
                continue
            keys[str(value)] = _content_digest(row, self._content_columns)
        return keys

    async def count(self, target: str | None = None) -> int:
        table = _identifier(target or self._table, "table")
        rows = await self._query(f"{table} | count")
        if not rows:
            return -1
        row = rows[0]
        value = row.get("Count", row.get("count"))
        return int(value) if value is not None else -1

    async def stats(self, target: str | None = None) -> Any:
        if self._stats is None:
            return {}
        return await self._stats.stats(target or self._table)

    async def _query(self, query: str) -> list[dict]:
        payload = await self._connector.execute(query)
        if is_error(payload):
            raise KustoVerifyError(json.loads(payload).get("detail", "query failed"))
        shaped = json.loads(payload)
        return list(shaped.get("rows") or []) if isinstance(shaped, dict) else []


def _content_digest(row: dict, columns: Sequence[str]) -> str:
    """sha256 over the named content columns, or the empty digest."""
    payload = {column: row.get(column) for column in columns}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


__all__ = ["KustoKeys", "KustoVerifyError"]
