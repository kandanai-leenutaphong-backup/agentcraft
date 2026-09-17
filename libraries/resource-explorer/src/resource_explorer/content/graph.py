"""Graph inspection and bounded previews over explicitly injected sources.

GraphReader accepts any GraphElementSource. GraphInspection implements that
contract with a caller-bound azdata connector, loaded only when dispatched.
Neither owns credential discovery, graph ontology or account authorization.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from azdata import DataConnector

from .content import (
    ContentBounds,
    ContentPayload,
    ContentResult,
    bounded_content,
    content_failure,
    normalize_sample,
)

#: Which half of the graph to sample. A graph has two, and a preview that
#: only ever shows one hides half of what was loaded.
GraphElement = Literal["vertices", "edges"]


@dataclass(frozen=True, slots=True)
class GraphTarget:
    """Which graph to read. Coordinates only; never a credential.

    All three name the graph, so all three are part of its identity: two
    accounts holding a database and graph of the same name are two different
    graphs. A resolver that keys a client on fewer than these serves one
    target's contents under another's name.
    """

    account: str = ""
    database: str = ""
    graph: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.account and self.database and self.graph)


@runtime_checkable
class GraphElementSource(Protocol):
    """An async graph sampler; explicit synchronous sources run off the event loop."""

    def sample(
        self, element: GraphElement, limit: int,
    ) -> Sequence[Mapping[str, Any]] | Awaitable[Sequence[Mapping[str, Any]]]:
        """At most ``limit`` vertices or edges, as flat renderable mappings."""


class GraphInspectionUnavailable(RuntimeError):
    """A graph inspection was refused, incomplete, or unavailable."""


def graph_properties(row: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten singleton valueMap lists without coercing scalar or native values."""
    return {name: value[0] if isinstance(value, list) and len(value) == 1 else value
            for name, value in row.items()}


class GraphInspection:
    """Count and sample through an injected connector; no identity lookup or ontology.

    Samples accept 1 through 101 rows, including the preview reader's extra
    row. Connector policy still bounds dispatch. The connector is borrowed
    unless explicitly owned; closing this source never closes a borrowed one.
    """

    def __init__(self, connector: DataConnector | None, *, owns_connector: bool = False) -> None:
        self.connector = connector
        self._owns_connector = owns_connector
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def aclose(self) -> None:
        async with self._close_lock:
            if not self._closed:
                self._closed = True
                if self._owns_connector and self.connector is not None:
                    await self.connector.aclose()

    async def submit(self, script: str, bindings: Mapping[str, Any] | None = None) -> list[Any]:
        if self._closed:
            raise GraphInspectionUnavailable("graph_inspection_closed")
        if self.connector is None:
            raise GraphInspectionUnavailable("graph_target_or_readonly_key_provider_unconfigured")
        try:
            from azdata import QueryRequest

            result = await self.connector.query(QueryRequest(
                dialect="gremlin", expression=script, parameters=bindings or {}))
        except Exception as error:
            raise GraphInspectionUnavailable("graph_query_failed") from error
        if result.status != "success" or result.truncated or result.errors:
            code = result.errors[0].code if result.errors else "graph_result_incomplete"
            raise GraphInspectionUnavailable(code)
        rows = []
        for item in result.items:
            if item.status != "success" or item.error is not None or item.content is None:
                raise GraphInspectionUnavailable("graph_result_item_invalid")
            rows.append(item.content.to_native())
        return rows

    @staticmethod
    def _root(element: str) -> str:
        if element not in {"vertices", "edges"}:
            raise ValueError("unknown_graph_element")
        return "g.E()" if element == "edges" else "g.V()"

    async def element_count(self, element: str) -> int:
        rows = await self.submit(self._root(element) + ".count()")
        if len(rows) != 1 or type(rows[0]) is not int or rows[0] < 0:
            raise GraphInspectionUnavailable("graph_count_unknown")
        return rows[0]

    async def sample(self, element: str, limit: int) -> list[dict[str, Any]]:
        root = self._root(element)
        if type(limit) is not int or not 1 <= limit <= 101:
            raise ValueError("graph_sample_limit_invalid")
        traversal = (".project('e','from','to').by(__.valueMap(true))"
                     ".by(__.outV().id()).by(__.inV().id())" if element == "edges" else ".valueMap(true)")
        rows = await self.submit(f"{root}.limit({limit}){traversal}")
        if len(rows) > limit or any(not isinstance(row, Mapping) for row in rows):
            raise GraphInspectionUnavailable("graph_sample_invalid")
        if element == "vertices":
            return [graph_properties(row) for row in rows]
        if any(not isinstance(row.get("e"), Mapping) or "from" not in row or "to" not in row for row in rows):
            raise GraphInspectionUnavailable("graph_sample_invalid")
        return [{**graph_properties(row["e"]), "outV": str(row["from"]), "inV": str(row["to"])}
                for row in rows]


class GraphReader:
    """A bounded element sample from one graph, over an injected source."""

    service = "gremlin"

    def __init__(
        self, *, resolve: Callable[[GraphTarget], GraphElementSource | None]
    ) -> None:
        self._resolve = resolve

    async def elements(
        self,
        *,
        target: GraphTarget,
        element: GraphElement = "vertices",
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """At most ``bounds.max_rows`` graph elements. Never raises."""
        kind = str(element)
        if kind not in ("vertices", "edges"):
            return content_failure(
                service=self.service,
                kind="elements",
                status="unavailable",
                detail="element must be 'vertices' or 'edges'",
            )
        if not target.is_complete:
            return content_failure(
                service=self.service,
                kind=kind,
                status="unconfigured",
                detail="graph read not configured: account, database and graph",
            )
        source = self._resolve(target)
        if source is None:
            return content_failure(
                service=self.service,
                kind=kind,
                status="unconfigured",
                detail="no graph client is configured for this target",
            )

        async def fetch() -> tuple[ContentPayload, bool]:
            # One more than asked for, so truncation is observed and not guessed.
            if inspect.iscoroutinefunction(source.sample):
                raw = await source.sample(element, int(bounds.max_rows) + 1)
            else:
                raw = await asyncio.to_thread(source.sample, element, int(bounds.max_rows) + 1)
            if inspect.isawaitable(raw):
                raw = await raw
            sample = normalize_sample(
                [dict(item) for item in raw],
                max_rows=bounds.max_rows,
                max_bytes=bounds.max_bytes,
            )
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=sample.rows,
                    columns=sample.columns,
                    size_bytes=sample.size_bytes,
                    notes=sample.notes,
                ),
                sample.truncated,
            )

        return await bounded_content(
            service=self.service, kind=kind, bounds=bounds, fetch=fetch
        )


__all__ = ["GraphElement", "GraphElementSource", "GraphInspection", "GraphInspectionUnavailable",
           "GraphReader", "GraphTarget", "graph_properties"]
