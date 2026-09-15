"""Kusto table metadata — row count and declared schema, from fixed queries.

NEW IN THIS REPOSITORY. Not adopted from upstream.

WHY IT EXISTS
-------------
The adopted content plane samples rows. It cannot say how many rows the table
holds or what its columns are declared as, and a preview that cannot say
"25 of 15,520" is a page of numbers with no scale.

WHY THE QUERIES ARE COMPOSED AND NOT ACCEPTED
----------------------------------------------
No caller-supplied text reaches Kusto. Two queries exist, both built here
from a table name that has already been refused unless it matches
:data:`~.content.TABLE_NAME`, the character set Kusto itself allows for a
table. There is no parameter that widens either query, and nothing here can
run a third.

An invalid name is ``unavailable`` with the reason, not a raised exception:
this plane's contract is that failure is a value.

DEPENDENCIES
------------
``azure-kusto-data``, loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.content import ContentBounds, bounded_content
from ..core.content import ContentPayload, ContentResult
from ..core.content import content_failure
from ..core.optional import load
from .content import TABLE_NAME
from .read import shape_kusto_response


@dataclass(frozen=True, slots=True)
class TableFacts:
    """What one table says about itself. Empty fields mean "not observed"."""

    row_count: int | None = None
    columns: tuple[dict[str, str], ...] = field(default_factory=tuple)


class KustoTableInspector:
    """Row count and declared schema for one Azure Data Explorer table."""

    service = "kusto"

    def __init__(self, *, credential_provider: Callable[[], Any]) -> None:
        self._credential_provider = credential_provider
        self._clients: dict[str, Any] = {}

    def _client(self, query_uri: str) -> Any:
        client = self._clients.get(query_uri)
        if client is None:
            kusto = load("azure.kusto.data", dist="azure-kusto-data>=4.3")
            builder = kusto.KustoConnectionStringBuilder.with_azure_token_credential(
                query_uri, self._credential_provider()
            )
            client = kusto.KustoClient(builder)
            self._clients[query_uri] = client
        return client

    def close(self) -> None:
        for client in self._clients.values():
            closer = getattr(client, "close", None)
            if closer is not None:
                try:
                    closer()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    pass
        self._clients.clear()

    async def facts(
        self,
        *,
        query_uri: str,
        database: str,
        table: str,
        bounds: ContentBounds = ContentBounds(),
    ) -> tuple[ContentResult, TableFacts]:
        """Count and schema in one call. The result carries the status."""
        if not query_uri or not database or not table:
            return (
                content_failure(
                    service=self.service,
                    kind="facts",
                    status="unconfigured",
                    detail="metadata read not configured: cluster uri, database and table",
                ),
                TableFacts(),
            )
        if not TABLE_NAME.match(table):
            return (
                content_failure(
                    service=self.service,
                    kind="facts",
                    status="unavailable",
                    detail="table name is not a Kusto identifier",
                ),
                TableFacts(),
            )

        observed: dict[str, Any] = {}

        def fetch() -> tuple[ContentPayload, bool]:
            client = self._client(query_uri)
            counted = shape_kusto_response(
                client.execute(database, f'["{table}"] | count')
            )
            rows = counted.get("rows", [])
            if rows:
                first = rows[0]
                value = first.get("Count", next(iter(first.values()), None))
                observed["row_count"] = int(value) if value is not None else None
            described = shape_kusto_response(
                client.execute(database, f'["{table}"] | getschema')
            )
            observed["columns"] = tuple(
                {
                    "name": str(row.get("ColumnName", "")),
                    "type": str(row.get("ColumnType") or row.get("DataType") or ""),
                }
                for row in described.get("rows", [])
                if str(row.get("ColumnName", ""))
            )
            # The payload itself is not rendered; the facts are returned beside
            # it. One row keeps the status "ok" rather than "empty".
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=({"observed": True},),
                    columns=("observed",),
                    size_bytes=1,
                ),
                False,
            )

        result = await bounded_content(
            service=self.service, kind="facts", bounds=bounds, fetch=fetch
        )
        return result, TableFacts(
            row_count=observed.get("row_count"),
            columns=observed.get("columns", ()),
        )


__all__ = ["KustoTableInspector", "TableFacts"]
