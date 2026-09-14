"""Search documents — a bounded sample of what one index actually holds.

WHY ``*`` AND NOT AN EMPTY QUERY
--------------------------------
An empty search text matches nothing in some analyzer configurations and
everything in others. ``*`` is the documented match-all and behaves the same
on every index, which is what a browser needs from a "show me what is in
here" call.

WHY THE ``@search.*`` KEYS SURVIVE
----------------------------------
They are the service's own answer about the document — its score, its
reranker score, its highlights. Dropping them would hide the one part of the
row the index itself produced.

Index *documents* need ``Search Index Data Reader``, which is a different
grant from the ``Search Service Contributor`` grade that lists index
definitions. An identity with one and not the other gets ``forbidden`` on
exactly the branch it lacks, which is the distinction worth preserving.

DEPENDENCIES
------------
``azure-search-documents`` (``search`` extra), loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
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

#: The documented match-all. Not a caller-supplied default.
MATCH_ALL = "*"


class SearchReader:
    """A bounded document sample from one Azure AI Search index."""

    service = "search"

    def __init__(self, *, credential_provider: Callable[[], Any]) -> None:
        self._credential_provider = credential_provider
        self._clients: dict[tuple[str, str], Any] = {}

    def _client(self, endpoint: str, index: str) -> Any:
        client = self._clients.get((endpoint, index))
        if client is None:
            sdk = load("azure.search.documents", dist="azure-search-documents>=11.5")
            client = sdk.SearchClient(
                endpoint=endpoint,
                index_name=index,
                credential=self._credential_provider(),
            )
            self._clients[(endpoint, index)] = client
        return client

    async def documents(
        self,
        *,
        endpoint: str,
        index: str,
        text: str = MATCH_ALL,
        filter: str = "",  # noqa: A002 - the service's own parameter name
        select: Sequence[str] = (),
        query_type: str = "",
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """At most ``bounds.max_rows`` documents of one index. Never raises.

        ``filter``, ``select`` and ``query_type`` are the service's own
        read-side parameters, passed through unchanged. They are optional and
        absent by default: an omitted parameter is not the same as an empty
        one to the service, so an empty value is not sent.
        """
        if not endpoint or not index:
            return content_failure(
                service=self.service,
                kind="documents",
                status="unconfigured",
                detail="document read not configured: endpoint and index",
            )
        query = str(text or MATCH_ALL)
        extra: dict[str, Any] = {}
        if filter:
            extra["filter"] = str(filter)
        if select:
            extra["select"] = [str(field) for field in select]
        if query_type:
            extra["query_type"] = str(query_type)

        def fetch() -> tuple[ContentPayload, bool]:
            results = self._client(endpoint, index).search(
                search_text=query, top=int(bounds.max_rows) + 1, **extra
            )
            items = [dict(document) for document in results]
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


__all__ = ["MATCH_ALL", "SearchReader"]
