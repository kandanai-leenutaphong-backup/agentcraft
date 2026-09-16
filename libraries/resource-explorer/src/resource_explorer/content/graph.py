"""Graph elements — a bounded sample of one graph's vertices or edges.

NEW IN THIS REPOSITORY, not adopted from upstream. Rationale: `README.md`,
"The graph reader imports nothing".

Upstream ``azdata`` authenticates its Gremlin plane with an Entra token, which
is unverified in this tenant. Only the *shape* is adopted here — the same
``ContentBounds`` in, the same ``ContentResult`` and six statuses out — while
the connection stays with the caller, so a graph preview renders through
exactly the code path a table or index preview does.

The reader never learns an account key, a graph vocabulary or a label set. It
is handed a resolver that returns something able to sample elements, and an
unresolvable target is ``unconfigured`` rather than an exception.

DEPENDENCIES
------------
Standard library, plus the content plane.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

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

    def sample(self, element: GraphElement, limit: int) -> Sequence[Mapping[str, Any]]:
        """At most ``limit`` vertices or edges, as flat renderable mappings."""


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


__all__ = ["GraphElement", "GraphElementSource", "GraphReader", "GraphTarget"]
