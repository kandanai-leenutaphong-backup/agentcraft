"""Cosmos documents — a bounded sample of one container's actual items.

WHY THE SQL ENDPOINT READS A GRAPH
----------------------------------
A Gremlin graph is stored as documents in the same account, and the SQL
endpoint returns them with an AAD token like any other container. Only
``g.V()`` *traversal* requires a key, and traversal is not what a browser
needs: it needs to see what is in there. So one reader covers both the NoSQL
and the Gremlin branches, and neither needs a key.

WHY ``SELECT TOP n``
--------------------
The cap has to be in the query, not in the loop that drains it. A
``SELECT *`` bounded only by client-side slicing still makes the service
compute and charge for the whole container.

DEPENDENCIES
------------
``azure-cosmos`` (``cosmos`` extra), loaded on first call.
"""

from __future__ import annotations

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

#: Public-cloud Cosmos endpoint. Overridden by an explicit endpoint for
#: sovereign clouds and for accounts reached through a private endpoint alias.
COSMOS_SUFFIX = "documents.azure.com"


def cosmos_endpoint(account_name: str) -> str:
    return f"https://{account_name}.{COSMOS_SUFFIX}:443/" if account_name else ""


class CosmosReader:
    """A bounded document sample from one container or graph."""

    service = "cosmos"

    def __init__(self, *, credential_provider: Callable[[], Any]) -> None:
        self._credential_provider = credential_provider
        self._clients: dict[str, Any] = {}

    def _client(self, endpoint: str) -> Any:
        client = self._clients.get(endpoint)
        if client is None:
            sdk = load("azure.cosmos", dist="azure-cosmos>=4.5,<5")
            client = sdk.CosmosClient(endpoint, credential=self._credential_provider())
            self._clients[endpoint] = client
        return client

    async def documents(
        self,
        *,
        account_name: str = "",
        endpoint: str = "",
        database: str,
        container: str,
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """At most ``bounds.max_rows`` items of one container. Never raises."""
        resolved = endpoint or cosmos_endpoint(account_name)
        if not resolved or not database or not container:
            return content_failure(
                service=self.service,
                kind="documents",
                status="unconfigured",
                detail="document read not configured: account, database and container",
            )

        def fetch() -> tuple[ContentPayload, bool]:
            handle = (
                self._client(resolved)
                .get_database_client(database)
                .get_container_client(container)
            )
            query = f"SELECT TOP {int(bounds.max_rows) + 1} * FROM c"
            try:
                pager = handle.query_items(
                    query=query, enable_cross_partition_query=True
                )
                items = list(pager)
            except TypeError:
                # The kwarg was removed in newer SDKs; cross-partition is the
                # default there, so the same query works without it.
                items = list(handle.query_items(query=query))
            rows, columns, truncated = normalize_rows(items, max_rows=bounds.max_rows)
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=rows,
                    columns=columns,
                    size_bytes=len(rows),
                ),
                truncated,
            )

        return await bounded_content(
            service=self.service, kind="documents", bounds=bounds, fetch=fetch
        )


__all__ = ["COSMOS_SUFFIX", "CosmosReader", "cosmos_endpoint"]
