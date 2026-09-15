"""Cosmos DB for Gremlin connector: connection, provisioning, and batched upsert.

Values are always passed as Gremlin bindings, never interpolated into the script, so no
telemetry string can alter the traversal.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Cosmos rejects a request whose script chains too many traversal steps. Measured ceiling
#: is between 32 and 40 chained upserts, so the default leaves headroom.
DEFAULT_BATCH = 20
#: Free-text properties are truncated here. A value that must survive a round trip is handed
#: over as a list or a mapping instead, which is serialised whole and never chopped.
PROPERTY_TEXT_LIMIT = 1000
#: Matched against the server fault text. Kept specific: bare status numbers also occur
#: inside activity ids and HResults, which would retry a permanent syntax error five times.
RETRYABLE = ("RequestRateTooLarge", "TooManyRequests", "ServerTimeout", "ServiceUnavailable",
             "Service is currently unavailable", "x-ms-status-code': 429", "x-ms-status-code': 503")


class GremlinError(RuntimeError):
    """A Gremlin operation failed after exhausting retries."""


@dataclass(frozen=True, slots=True)
class GremlinSettings:
    account: str
    database: str
    graph: str
    partition_key: str
    partition_value: str
    resource_group: str
    subscription_id: str
    batch_size: int = DEFAULT_BATCH
    max_retries: int = 5

    @property
    def endpoint(self) -> str:
        return f"wss://{self.account}.gremlin.cosmos.azure.com:443/gremlin"

    @property
    def username(self) -> str:
        return f"/dbs/{self.database}/colls/{self.graph}"

    @classmethod
    def from_env(cls) -> GremlinSettings:
        missing = [name for name in ("GREMLIN_ACCOUNT", "GREMLIN_DATABASE", "GREMLIN_GRAPH")
                   if not os.environ.get(name)]
        if missing:
            raise GremlinError(f"missing environment variables: {', '.join(missing)}")
        return cls(
            account=os.environ["GREMLIN_ACCOUNT"],
            database=os.environ["GREMLIN_DATABASE"],
            graph=os.environ["GREMLIN_GRAPH"],
            partition_key=os.environ.get("GREMLIN_PARTITION_KEY", "pk"),
            partition_value=os.environ.get("GREMLIN_PARTITION_VALUE", "perth"),
            resource_group=os.environ.get("GREMLIN_RESOURCE_GROUP", ""),
            subscription_id=os.environ.get("GREMLIN_SUBSCRIPTION_ID", ""),
            batch_size=int(os.environ.get("GREMLIN_BATCH_SIZE", DEFAULT_BATCH)),
            max_retries=int(os.environ.get("GREMLIN_MAX_RETRIES", 5)),
        )


class GremlinGraph:
    """Thin, retrying wrapper over one Cosmos Gremlin graph."""

    def __init__(self, settings: GremlinSettings, key: str) -> None:
        from gremlin_python.driver import client, serializer

        self.settings = settings
        self._client = client.Client(
            settings.endpoint, "g",
            username=settings.username, password=key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GremlinGraph:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def submit(self, script: str, bindings: dict[str, Any] | None = None) -> list[Any]:
        last: Exception | None = None
        for attempt in range(self.settings.max_retries):
            try:
                return self._client.submit(script, bindings or {}).all().result()
            except Exception as exc:  # gremlinpython wraps every server fault
                last = exc
                text = str(exc)
                if not any(marker in text for marker in RETRYABLE):
                    raise GremlinError(f"gremlin request failed: {text[:400]}") from exc
                delay = min(2 ** attempt * 0.4, 8.0)
                logger.warning("gremlin retry %d after %.1fs: %s", attempt + 1, delay, text[:160])
                time.sleep(delay)
        raise GremlinError(f"gremlin request failed after {self.settings.max_retries} attempts: "
                           f"{str(last)[:400]}")

    # ---- writes -------------------------------------------------------------

    def upsert_vertices(self, vertices: Sequence[dict[str, Any]]) -> int:
        written = 0
        for batch in _chunks(vertices, self.settings.batch_size):
            script, bindings = self._vertex_script(batch)
            self.submit(script, bindings)
            written += len(batch)
        return written

    def upsert_edges(self, edges: Sequence[dict[str, Any]]) -> int:
        written = 0
        for batch in _chunks(edges, self.settings.batch_size):
            script, bindings = self._edge_script(batch)
            self.submit(script, bindings)
            written += len(batch)
        return written

    def _vertex_script(self, batch: Sequence[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        bindings: dict[str, Any] = {}
        for index, vertex in enumerate(batch):
            vid, label = f"vi{index}", f"vl{index}"
            bindings[vid] = vertex["id"]
            bindings[label] = vertex["label"]
            assignments = []
            for position, (name, value) in enumerate(encode_properties(vertex.get("properties", {})).items()):
                key = f"vp{index}_{position}"
                bindings[key] = value
                assignments.append(f".property('{_safe_name(name)}', {key})")
            # The partition key is immutable, so it may only be set on the create branch.
            parts.append(
                f"V({vid}).fold().coalesce(unfold(), addV({label}).property('id', {vid})"
                f".property('{self.settings.partition_key}', pk))"
                + "".join(assignments)
            )
        bindings["pk"] = self.settings.partition_value
        return "g." + ".".join(parts), bindings

    def _edge_script(self, batch: Sequence[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        bindings: dict[str, Any] = {}
        for index, edge in enumerate(batch):
            eid, src, dst, label = f"ei{index}", f"es{index}", f"ed{index}", f"el{index}"
            bindings[eid] = edge["id"]
            bindings[src] = edge["from"]
            bindings[dst] = edge["to"]
            bindings[label] = edge["label"]
            assignments = []
            for position, (name, value) in enumerate(encode_properties(edge.get("properties", {})).items()):
                key = f"ep{index}_{position}"
                bindings[key] = value
                assignments.append(f".property('{_safe_name(name)}', {key})")
            parts.append(
                f"V({src}).outE().hasId({eid}).fold()"
                f".coalesce(unfold(), addE({label}).from(__.V({src})).to(__.V({dst})).property('id', {eid}))"
                + "".join(assignments)
            )
        return "g." + ".".join(parts), bindings

    # ---- reads --------------------------------------------------------------

    def counts(self) -> dict[str, int]:
        vertices = self.submit("g.V().count()")
        edges = self.submit("g.E().count()")
        return {"vertices": int(vertices[0]), "edges": int(edges[0])}

    def label_counts(self) -> dict[str, dict[str, int]]:
        vertices = self.submit("g.V().groupCount().by(label)")
        edges = self.submit("g.E().groupCount().by(label)")
        return {
            "vertices": {str(k): int(v) for k, v in (vertices[0] if vertices else {}).items()},
            "edges": {str(k): int(v) for k, v in (edges[0] if edges else {}).items()},
        }

    def drop_all(self) -> None:
        while int(self.submit("g.V().count()")[0]) > 0:
            self.submit("g.V().limit(400).drop()")


def _chunks(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def encode_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Cosmos vertex properties take scalars; encode lists and mappings as JSON text.

    Public because it is the caller's half of the contract: what a producer hands over
    decides whether the value survives, and only a list or a mapping is serialised whole.
    """
    flattened: dict[str, Any] = {}
    for name, value in properties.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple, set)):
            flattened[name] = json.dumps(sorted(str(item) for item in value), separators=(",", ":"))
        elif isinstance(value, dict):
            flattened[name] = json.dumps(value, sort_keys=True, separators=(",", ":"))
        elif isinstance(value, bool):
            flattened[name] = value
        elif isinstance(value, (int, float)):
            flattened[name] = value
        else:
            # Free text only. Anything that has to survive a round trip must arrive as a
            # list or a mapping above, where it is serialised whole.
            flattened[name] = str(value)[:PROPERTY_TEXT_LIMIT]
    return flattened


def _safe_name(name: str) -> str:
    """Property names are the only interpolated fragment, so restrict them to a safe alphabet."""
    cleaned = "".join(char for char in name if char.isalnum() or char == "_")
    if not cleaned or cleaned[0].isdigit():
        raise GremlinError(f"unsafe property name: {name!r}")
    return cleaned[:60]


__all__ = ["GremlinError", "GremlinGraph", "GremlinSettings", "DEFAULT_BATCH",
           "PROPERTY_TEXT_LIMIT", "encode_properties"]
