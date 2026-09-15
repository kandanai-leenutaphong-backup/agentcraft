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

import logging
import os
import threading
from typing import Any

from azdata import AsyncTransport, ConnectorConfig, Policy
from template_foundations.azure_search import SearchError, SearchReadClient, safe_key

from ..config import settings

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
        self._lock = threading.Lock()
        self._key: tuple[str, str] | None = None
        self._client: Any = None
        self._binding: tuple[Any, ...] | None = None
        self._owned = False

    def coordinates(self) -> tuple[str, str]:
        with self._lock:
            if self._key is not None:
                return self._key
        return (_setting("CYBEREYE_SEARCH_ENDPOINT", settings.search_endpoint),
                _setting("CYBEREYE_MITRE_SEARCH_INDEX", settings.knowledge_index))

    def configure(self, config: ConnectorConfig | None, *, credential: Any,
                  policy: Policy, transport: AsyncTransport | None = None) -> SearchReadClient | None:
        binding = (config, id(credential), policy, id(transport))
        with self._lock:
            if (self._owned and self._binding == binding and self._client is not None
                    and not self._client.describe()["closed"]):
                return self._client
            client = (SearchReadClient(config, credential=credential, policy=policy, transport=transport)
                      if config is not None else None)
            self._reset()
            self._client = client
            self._owned = client is not None
            self._binding = binding
            self._key = (config.endpoint, config.target.coordinates["index"]) if config is not None else None
            return client

    def get(self) -> tuple[Any, str]:
        with self._lock:
            if self._client is None or self._key is None or not all(self._key):
                raise KnowledgeUnavailable(
                    "the knowledge index is not configured; set CYBEREYE_SEARCH_ENDPOINT and "
                    "CYBEREYE_MITRE_SEARCH_INDEX and inject the read credential"
                )
            return self._client, self._key[1]

    def set_client(self, client: Any) -> None:
        """Install a client directly. The seam tests drive a fake through."""
        target = (_setting("CYBEREYE_SEARCH_ENDPOINT", settings.search_endpoint),
                  _setting("CYBEREYE_MITRE_SEARCH_INDEX", settings.knowledge_index))
        with self._lock:
            self._reset()
            self._client = client
            self._key = target

    def reset(self) -> None:
        with self._lock:
            self._reset()

    def _reset(self) -> None:
        try:
            if self._owned and self._client is not None:
                self._client.close()
        finally:
            self._client = None
            self._key = None
            self._binding = None
            self._owned = False


_CACHE = _ClientCache()

set_client = _CACHE.set_client
reset_client = _CACHE.reset
configure = _CACHE.configure


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


def retrieve(*, doc_kind: str, query: str, terms: dict[str, list[str]],
             top: int) -> tuple[list[dict[str, Any]], list[str], str]:
    """Filtered query first; relax one term at a time rather than return nothing.

    Returns the hits, the names of the terms that had to be dropped, and the filter that
    actually ran. Raises `KnowledgeUnavailable` rather than answering from anywhere else.
    """
    client, index = _CACHE.get()
    text = (query or "").strip() or "*"
    active = {name: list(values) for name, values in terms.items()}
    relaxed: list[str] = []
    order = [name for name in terms if any(str(value).strip() for value in active.get(name, []))]
    try:
        for step in range(len(order) + 1):
            if step:
                dropped = order[step - 1]
                active[dropped] = []
                relaxed.append(dropped)
            expression = build_filter(doc_kind, active)
            hits = client.search(index, text, top=top, filter=expression,
                                 select=SELECT)
            if hits:
                return hits, relaxed, expression
        expression = build_filter(doc_kind, active)
        return [], relaxed, expression
    except SearchError as exc:
        raise KnowledgeUnavailable(f"knowledge index {index!r}: {exc}") from exc
    except OSError as exc:
        raise KnowledgeUnavailable(f"knowledge index {index!r} unreachable: {exc}") from exc


def get_by_doc_id(doc_kind: str, doc_id: str) -> dict[str, Any] | None:
    """One document by its normalised id, fetched by key so a citation opens exactly."""
    client, index = _CACHE.get()
    try:
        return client.get_document(index, safe_key(f"{doc_kind}:{doc_id}"))
    except SearchError as exc:
        raise KnowledgeUnavailable(f"knowledge index {index!r}: {exc}") from exc
    except OSError as exc:
        raise KnowledgeUnavailable(f"knowledge index {index!r} unreachable: {exc}") from exc


def status() -> dict[str, Any]:
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
        client, _ = _CACHE.get()
        report["documents"] = client.search_count(index)
        report["situation_types"] = client.search_count(
            index, filter=f"doc_kind eq {_quote(SITUATION_TYPE)}")
        report["analytics"] = client.search_count(
            index, filter=f"doc_kind eq {_quote(ANALYTIC)}")
        report["available"] = report["documents"] > 0
    except (KnowledgeUnavailable, SearchError, OSError) as exc:
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
    "endpoint",
    "get_by_doc_id",
    "index_name",
    "reset_client",
    "retrieve",
    "set_client",
    "status",
]
