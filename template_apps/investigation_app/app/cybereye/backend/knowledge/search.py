"""The one retrieval seam: pinned MITRE ATT&CK knowledge, read from Azure AI Search.

There is no local corpus and no BM25 fallback. Retrieval either reaches the index and
returns what the service ranked, or it fails honestly — a knowledge answer assembled from
an on-disk copy while the configured index is unreachable is an answer whose provenance
nobody can check.

`tools/knowledge_base.py` asks for ATT&CK analytics and detection strategies;
`situation_types.py` asks for ATT&CK techniques and tactics as candidate situation
types. Both are `doc_kind` slices of the same index, so the client, the filter rendering
and the envelope live here once.

Nothing retrieved is ever executed, and nothing here reads telemetry.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import replace
from typing import Any

from azdata import (AsyncTransport, ConnectorConfig, DataConnector, Limits, Policy,
                    QueryRequest, ReadRequest, RecordKey, connect)

from ..config import settings
from .keys import safe_key

logger = logging.getLogger(__name__)

SITUATION_TYPE = "situation_type"
ANALYTIC = "analytic"

#: Every field a citation needs, plus the ranked text. `content` is not selected: it is a
#: join of fields already returned and would double every payload.
SELECT = (
    "id", "doc_kind", "doc_id", "source", "doc_type", "title", "family", "definition",
    "summary", "body", "symptoms", "keywords", "log_sources", "platforms",
    "technique_ids", "behaviour_class", "maturity", "native_id", "attack_url",
    "path", "commit", "license", "retrieved_at",
)


class KnowledgeUnavailable(RuntimeError):
    """The knowledge index could not answer. Never downgraded to a local result."""


def _setting(key: str, fallback: str) -> str:
    # An explicitly empty variable means unconfigured, not "use the built-in default".
    return os.environ[key].strip() if key in os.environ else fallback


def endpoint() -> str:
    return _CACHE.coordinates()[0]


def index_name() -> str:
    return _CACHE.coordinates()[1]


class _ClientCache:
    """One explicitly bound owned client, or one borrowed test double."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._key: tuple[str, str] | None = None
        self._client: Any = None
        self._binding: tuple[Any, ...] | None = None
        self._owned = False
        self.policy = Policy("investigation-knowledge", {"query", "read"}, max_concurrency=1,
                             limits=Limits(max_attempts=1))
        self._metrics = self._new_metrics()

    @staticmethod
    def _new_metrics():
        return {"submitted": 0, "completed": 0, "known_attempts": 0,
                "unknown_attempt_operations": 0, "operations": {"query": 0, "read": 0}}

    def coordinates(self) -> tuple[str, str]:
        if self._key is not None:
            return self._key
        return (_setting("CYBEREYE_SEARCH_ENDPOINT", settings.search_endpoint),
                _setting("CYBEREYE_MITRE_SEARCH_INDEX", settings.knowledge_index))

    async def configure(self, config: ConnectorConfig | None, *, credential: Any,
                        policy: Policy, transport: AsyncTransport | None = None) -> DataConnector | None:
        binding = (config, id(credential), policy, id(transport))
        async with self._lock:
            if self._owned and self._binding == binding and self._client is not None:
                return self._client
            client = (connect("search", config, credential=credential, policy=policy, transport=transport)
                      if config is not None else None)
            await self._reset()
            self._client = client
            self._owned = client is not None
            self._binding = binding
            self.policy = policy
            self._key = (config.endpoint, config.target.coordinates["index"]) if config is not None else None
            return client

    def get(self) -> tuple[Any, str]:
        if self._client is None or self._key is None or not all(self._key):
            raise KnowledgeUnavailable("knowledge index or explicit identity is not configured")
        return self._client, self._key[1]

    async def set_client(self, client: Any) -> None:
        """Install a client directly. The seam tests drive a fake through."""
        target = (_setting("CYBEREYE_SEARCH_ENDPOINT", settings.search_endpoint),
                  _setting("CYBEREYE_MITRE_SEARCH_INDEX", settings.knowledge_index))
        async with self._lock:
            await self._reset()
            self._client = client
            self._key = target

    async def reset(self) -> None:
        async with self._lock:
            await self._reset()

    async def _reset(self) -> None:
        try:
            if self._owned and self._client is not None:
                await self._client.aclose()
        finally:
            self._client = None
            self._key = None
            self._binding = None
            self._owned = False
            self._metrics = self._new_metrics()

    async def operation(self, request: QueryRequest | ReadRequest):
        client, _ = self.get()
        operation = "query" if isinstance(request, QueryRequest) else "read"
        result = None
        metrics = self._metrics
        metrics["submitted"] += 1
        metrics["operations"][operation] += 1
        try:
            result = await (client.query(request) if operation == "query" else client.read(request))
        except OSError:
            raise KnowledgeUnavailable("knowledge_transport_unavailable") from None
        finally:
            metrics["completed"] += 1
            attempts = result.metrics.get("attempts") if result is not None else None
            if type(attempts) is int and attempts >= 0:
                metrics["known_attempts"] += attempts
            else:
                metrics["unknown_attempt_operations"] += 1
        if result.status != "success":
            code = result.errors[0].code if result.errors else result.status
            raise KnowledgeUnavailable(f"knowledge_read_failed:{code}")
        if result.truncated and not result.continuation:
            raise KnowledgeUnavailable("knowledge_result_incomplete")
        return result

    def describe(self) -> dict[str, Any]:
        return {"configured": self._client is not None, "endpoint": self.coordinates()[0],
                "index": self.coordinates()[1], "transport": "azdata-native",
                "grants": sorted(self.policy.grants), "closed": self._client is None,
                "metrics": {**self._metrics, "operations": dict(self._metrics["operations"])}}


_CACHE = _ClientCache()

set_client = _CACHE.set_client
reset_client = _CACHE.reset
configure = _CACHE.configure
describe = _CACHE.describe


def _quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_filter(doc_kind: str, terms: dict[str, list[str]]) -> str:
    """OData filter: kind, then any non-empty collection term, ANDed."""
    clauses = [f"doc_kind eq {_quote(doc_kind)}"]
    for field, values in terms.items():
        wanted = [value for value in values if str(value).strip()]
        if not wanted:
            continue
        # search.in takes one delimited string, not one argument per value: passing several
        # quoted arguments is the shape the service rejects with "no function signature".
        joined = _quote(",".join(str(value).strip() for value in wanted))
        clauses.append(f"{field}/any(v: search.in(v, {joined}, ','))")
    return " and ".join(clauses)


async def retrieve(*, doc_kind: str, query: str, terms: dict[str, list[str]],
             top: int) -> tuple[list[dict[str, Any]], list[str], str]:
    """Filtered query first; relax one term at a time rather than return nothing.

    Returns the hits, the names of the terms that had to be dropped, and the filter that
    actually ran. Raises `KnowledgeUnavailable` rather than answering from anywhere else.
    """
    _CACHE.get()
    if type(top) is not int or not 1 <= top <= _CACHE.policy.limits.max_items:
        raise KnowledgeUnavailable("knowledge_result_bound_invalid")
    text = (query or "").strip() or "*"
    active = {name: list(values) for name, values in terms.items()}
    relaxed: list[str] = []
    order = [name for name in terms if any(str(value).strip() for value in active.get(name, []))]
    for step in range(len(order) + 1):
        if step:
            dropped = order[step - 1]
            active[dropped] = []
            relaxed.append(dropped)
        expression = build_filter(doc_kind, active)
        result = await _CACHE.operation(QueryRequest(dialect="search", expression=text, projection=SELECT,
            limits=replace(_CACHE.policy.limits, max_items=top), service_options={"search": {"filter": expression}}))
        hits = [item["content"]["data"] for item in result.to_dict()["items"] if item["content"] is not None]
        if hits:
            return hits, relaxed, expression
    return [], relaxed, expression


async def get_by_doc_id(doc_kind: str, doc_id: str) -> dict[str, Any] | None:
    """One document by its normalised id, fetched by key so a citation opens exactly."""
    key = safe_key(f"{doc_kind}:{doc_id}")
    result = await _CACHE.operation(ReadRequest(keys=(RecordKey({"id": key}),), missing="ok"))
    if len(result.items) != 1:
        raise KnowledgeUnavailable("knowledge_keyed_result_invalid")
    content = result.to_dict()["items"][0]["content"]
    if content is None:
        return None
    document = content["data"]
    if document.get("id") != key or document.get("doc_kind") != doc_kind or document.get("doc_id") != doc_id:
        raise KnowledgeUnavailable("knowledge_keyed_identity_invalid")
    return document


async def status() -> dict[str, Any]:
    """Availability report for the health endpoint. One counting query, no documents."""
    target, index = endpoint(), index_name()
    report: dict[str, Any] = {
        "available": False, "endpoint": target, "index": index,
        "retrieval": "azure-ai-search", "local_fallback": False, "advisory_only": True,
    }
    if not target or not index:
        report["reason"] = ("not configured; set CYBEREYE_SEARCH_ENDPOINT and "
                            "CYBEREYE_MITRE_SEARCH_INDEX")
        return report
    try:
        for name, kind in (("documents", None), ("situation_types", SITUATION_TYPE), ("analytics", ANALYTIC)):
            options: dict[str, Any] = {"count": True}
            if kind:
                options["filter"] = f"doc_kind eq {_quote(kind)}"
            result = await _CACHE.operation(QueryRequest(dialect="search", expression="*", projection=("id",),
                limits=replace(_CACHE.policy.limits, max_items=1), service_options={"search": options}))
            count = result.metadata.get("count")
            if type(count) is not int or count < 0:
                raise KnowledgeUnavailable("knowledge_count_unknown")
            report[name] = count
        report["available"] = report["documents"] > 0
    except KnowledgeUnavailable as exc:
        logger.warning("cybereye.knowledge.status_failed %s", exc)
        report["reason"] = str(exc)
    return report


__all__ = [
    "ANALYTIC",
    "SELECT",
    "SITUATION_TYPE",
    "KnowledgeUnavailable",
    "build_filter",
    "configure",
    "describe",
    "endpoint",
    "get_by_doc_id",
    "index_name",
    "reset_client",
    "retrieve",
    "set_client",
    "status",
]
