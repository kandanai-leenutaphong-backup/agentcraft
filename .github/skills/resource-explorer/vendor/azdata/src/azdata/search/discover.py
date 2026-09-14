"""Azure AI Search discovery — index names, then one index's field schema.

WHY THIS EXISTS
---------------
An operator browsing a search service needs two facts before anything
else: which indexes exist, and what a given index is shaped like. Both are
read from the index-management data plane with ``list``/``get`` only;
nothing here can create, update or delete an index, and the reachable call
set is exactly two methods so that claim is checkable by reading the file.

Document counts are not collected here. They are the observe plane's
counter (``SearchStats``), and two numbers for the same quantity
eventually disagree.

Permission note: reading index *definitions* needs ``Search Service
Contributor``-grade access. ``Search Index Data Reader`` can read
documents and cannot read the schema (GOTCHAS.md).

DEPENDENCIES
------------
``azure-search-documents`` (``discover`` extra), loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from azdata.core.config import AzureDataConfig
from azdata.core.discover import (
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    bounded_discovery,
    discovery_failure,
    model_field,
    normalize_attributes,
)
from azdata.search.deploy import load_indexes

#: Complex Search fields nest arbitrarily. Three levels is what a tree can
#: show without becoming a schema browser, and it bounds the flattening.
MAX_FIELD_DEPTH = 3


class SearchDiscoverer:
    """Indexes of one search service, and the fields of one index.

    Args:
        endpoint: Fallback when the scope does not carry one.
        credential_provider: Called on the first ``discover``, never at
            construction.
    """

    service = "search"
    levels = ("service", "index")

    def __init__(
        self,
        *,
        endpoint: str = "",
        credential_provider: Callable[[], Any],
    ) -> None:
        self._endpoint = endpoint
        self._credential_provider = credential_provider
        self._clients: dict[str, Any] = {}

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
    ) -> "SearchDiscoverer":
        return cls(
            endpoint=config.search_endpoint,
            credential_provider=credential_provider,
        )

    def child_level(self, level: str) -> str | None:
        return "index" if level == "service" else None

    def _client(self, endpoint: str) -> Any:
        client = self._clients.get(endpoint)
        if client is None:
            indexes = load_indexes()
            client = indexes.SearchIndexClient(
                endpoint=endpoint, credential=self._credential_provider()
            )
            self._clients[endpoint] = client
        return client

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate indexes or fields. Never raises."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service search",
            )

        endpoint = scope.endpoint or self._endpoint
        if not endpoint:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail="search discovery not configured: search_endpoint",
            )
        index_name = scope.path[0] if scope.path else ""
        if level == "index" and not index_name:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail="search index discovery not configured: index name",
            )

        def collect() -> Iterator[DiscoveryNode]:
            client = self._client(endpoint)
            if level == "service":
                emitted = 0
                for name in client.list_index_names():
                    yield DiscoveryNode(
                        kind="search_index",
                        name=str(name),
                        path=(str(name),),
                        has_children=True,
                        attributes=normalize_attributes({"name": str(name)}),
                    )
                    emitted += 1
                    if emitted > bounds.max_items:
                        return
                return
            index = client.get_index(index_name)
            emitted = 0
            for node in _field_nodes(
                model_field(index, "fields") or (), prefix="", depth=1, scope=scope
            ):
                yield node
                emitted += 1
                if emitted > bounds.max_items:
                    return

        return await bounded_discovery(
            service=self.service,
            level=level,
            scope=scope,
            bounds=bounds,
            collect=collect,
        )


def _field_nodes(
    fields: Any, *, prefix: str, depth: int, scope: DiscoveryScope
) -> Iterator[DiscoveryNode]:
    """Flatten complex fields as ``parent/child``, capped at three levels."""
    if depth > MAX_FIELD_DEPTH:
        return
    for field in fields or ():
        name = f"{prefix}{model_field(field, 'name')}"
        yield DiscoveryNode(
            kind="search_field",
            name=name,
            path=(*scope.path, name),
            has_children=False,
            attributes=normalize_attributes(_field_attributes(field)),
        )
        yield from _field_nodes(
            model_field(field, "fields") or (),
            prefix=f"{name}/",
            depth=depth + 1,
            scope=scope,
        )


def _field_attributes(field: Any) -> dict[str, Any]:
    """The flags an operator reads a schema for.

    ``retrievable`` is derived from ``hidden``: the SDK renamed the flag
    and inverted it, and the tree should show the question actually being
    asked — can this field come back in a result.
    """
    hidden = model_field(field, "hidden")
    retrievable = model_field(field, "retrievable")
    if retrievable is None and hidden is not None:
        retrievable = not hidden
    return {
        "type": model_field(field, "type"),
        "key": model_field(field, "key"),
        "searchable": model_field(field, "searchable"),
        "filterable": model_field(field, "filterable"),
        "sortable": model_field(field, "sortable"),
        "facetable": model_field(field, "facetable"),
        "retrievable": retrievable,
        "analyzer": model_field(field, "analyzer_name"),
        "vector_dimensions": model_field(field, "vector_search_dimensions"),
    }


__all__ = [
    "MAX_FIELD_DEPTH",
    "SearchDiscoverer",
]
