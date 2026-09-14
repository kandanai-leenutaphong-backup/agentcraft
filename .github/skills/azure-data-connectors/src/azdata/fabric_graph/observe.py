"""Fabric GraphModel observe plane — schema metadata and the last GQL status.

WHY THIS EXISTS
---------------
A GraphModel has no data plane to count and no ARM resource to query, so
there are exactly two things worth reporting: what the published schema
says, and whether the last query the process ran actually succeeded.

The second matters more than it looks. HTTP 200 does not mean the query
succeeded (GOTCHAS.md G7) — the GQL status code lives in the response body.
``last_query_status_code`` is that code, retained by the connector. Before
any query has run it is None, and the stat is named in ``partial`` rather
than reported as ``"00000"``: an unrun query is not a successful one.

DEPENDENCIES
------------
Standard library, plus ``httpx`` loaded on first metadata read.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from azdata.core.observe import (
    Probe,
    StatSource,
    StatUnavailable,
    collector,
    stats_envelope,
)
from azdata.core.optional import load

logger = logging.getLogger(__name__)

SCHEMA_STATS = ("node_types", "edge_types", "schema_version")

#: Metadata key aliases. The endpoint's casing is not contractual here, so
#: each stat is looked up under the spellings the API has used.
_SCHEMA_KEYS: Mapping[str, tuple[str, ...]] = {
    "node_types": ("nodeTypes", "node_types", "nodes"),
    "edge_types": ("edgeTypes", "edge_types", "edges"),
    "schema_version": ("schemaVersion", "schema_version", "version"),
}


class GraphStats:
    """Key stats for one published Fabric GraphModel.

    Args:
        connector: The :class:`~azdata.fabric_graph.read.GraphConnector`, read
            for its last GQL status code.
        metadata_url_provider: Callable returning the GraphModel metadata
            URL. Empty means unconfigured.
        token_provider: Async callable returning a bearer token.
    """

    service = "fabric_graph"

    def __init__(
        self,
        *,
        connector: Any = None,
        metadata_url_provider: Any = None,
        token_provider: Any = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._connector = connector
        self._metadata_url_provider = metadata_url_provider
        self._token_provider = token_provider
        self._timeout = timeout_seconds

    async def stats(self, target: str | None = None) -> str:
        data, partial = await collector(self._data_probes())
        return stats_envelope(
            service=self.service,
            target=target,
            source=StatSource.DATA_PLANE,
            stats=data,
            partial=partial,
        )

    def _data_probes(self) -> list[Probe]:
        return [
            (SCHEMA_STATS, self._schema),
            (("last_query_status_code",), self._last_status_code),
        ]

    async def _schema(self) -> dict[str, Any]:
        if self._metadata_url_provider is None or self._token_provider is None:
            raise StatUnavailable(
                "no metadata URL or token provider is wired for this GraphModel"
            )
        url = self._metadata_url_provider()
        if not url:
            raise StatUnavailable(
                "Fabric GraphModel not configured: set the workspace id and "
                "graph model id"
            )
        httpx = load("httpx", dist="httpx")
        token = await self._token_provider()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
        status = getattr(response, "status_code", None)
        if status != 200:
            raise StatUnavailable(f"the metadata endpoint answered HTTP {status}")
        try:
            body = response.json()
        except Exception as exc:  # noqa: BLE001 - a non-JSON body is an absence
            raise StatUnavailable(
                f"the metadata endpoint returned a non-JSON body: {exc}"
            ) from exc
        if not isinstance(body, Mapping):
            raise StatUnavailable("the metadata endpoint returned a non-object body")

        found: dict[str, Any] = {}
        for stat, aliases in _SCHEMA_KEYS.items():
            for alias in aliases:
                if alias in body:
                    found[stat] = body[alias]
                    break
        return found

    async def _last_status_code(self) -> str:
        code = getattr(self._connector, "last_query_status_code", None)
        if code is None:
            raise StatUnavailable(
                "no GQL query has run in this process, so there is no status "
                "code to report"
            )
        return code


__all__ = ["SCHEMA_STATS", "GraphStats"]
