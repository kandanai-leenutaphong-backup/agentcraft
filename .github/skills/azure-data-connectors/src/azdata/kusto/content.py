"""Kusto rows — a bounded sample of one table, composed not accepted.

WHY THE TABLE NAME IS VALIDATED AND NOT ESCAPED
-----------------------------------------------
The only caller-supplied value in the query is a table name, and the safe
form of a KQL identifier depends on which characters are in it. Rather than
implement a quoting scheme that has to be right every time, this refuses any
name outside the character set Kusto itself allows for a table, and composes
``["name"] | take n`` from a name that cannot terminate the literal.

An invalid name is ``unavailable`` with the reason, not a raised exception:
this plane's contract is that failure is a value.

DEPENDENCIES
------------
``azure-kusto-data`` (``kusto`` extra), loaded on first call.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from azdata.core.content import (
    ContentBounds,
    ContentPayload,
    ContentResult,
    bounded_content,
    content_failure,
    normalize_rows,
)
from azdata.core.optional import load
from azdata.kusto.read import shape_kusto_response

#: What Kusto permits in a table name. Anything else is refused rather than
#: escaped, because a name outside this set cannot exist in the cluster.
TABLE_NAME = re.compile(r"^[A-Za-z0-9_\- .]{1,1024}$")


class KustoReader:
    """A bounded row sample from one Azure Data Explorer table."""

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

    async def rows(
        self,
        *,
        query_uri: str,
        database: str,
        table: str,
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """At most ``bounds.max_rows`` rows of one table. Never raises."""
        if not query_uri or not database or not table:
            return content_failure(
                service=self.service,
                kind="rows",
                status="unconfigured",
                detail="row read not configured: cluster uri, database and table",
            )
        if not TABLE_NAME.match(table):
            return content_failure(
                service=self.service,
                kind="rows",
                status="unavailable",
                detail="table name is not a Kusto identifier",
            )
        query = f'["{table}"] | take {int(bounds.max_rows)}'

        def fetch() -> tuple[ContentPayload, bool]:
            response = self._client(query_uri).execute(database, query)
            shaped = shape_kusto_response(response)
            rows, columns, truncated = normalize_rows(
                shaped.get("rows", ()), max_rows=bounds.max_rows
            )
            declared = tuple(
                str(column.get("name"))
                for column in shaped.get("columns", ())
                if isinstance(column, dict)
            )
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=rows,
                    # The table's declared column order, which survives an
                    # all-null column that no row would reveal.
                    columns=declared or columns,
                    size_bytes=len(rows),
                ),
                truncated,
            )

        return await bounded_content(
            service=self.service, kind="rows", bounds=bounds, fetch=fetch
        )


__all__ = ["TABLE_NAME", "KustoReader"]
