"""Azure AI Search observe plane — index and service counters, plus Monitor.

WHY THIS EXISTS
---------------
Search reports its state through two calls that answer different
questions and fail independently. ``get_index_statistics`` is per index and
tells you how much is in it. ``get_service_statistics`` is per service and
tells you how close the whole thing is to its tier limits — which is the
number that explains why an upload started failing.

Both are separate probes, so an index that has just been deleted still
returns the service counters, and a service-level permission problem still
returns the document count.

Quota and usage names are enumerated from a fixed counter list rather than
from whatever the response happens to contain. A counter the service did
not report is named in ``partial``; discovering the names from the response
would make an unreported counter indistinguishable from one that does not
exist.

DEPENDENCIES
------------
Standard library, plus ``azure-search-documents`` loaded on first call.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Mapping

from azdata.core.config import AzureDataConfig
from azdata.core.metrics import DEFAULT_METRIC_WINDOW, MetricsReader, read_stats
from azdata.core.observe import (
    Probe,
    StatSource,
    StatUnavailable,
    collector,
    stats_envelope,
)
from azdata.core.optional import load

logger = logging.getLogger(__name__)

#: SDK counter attribute -> the suffix used in ``quota_*`` / ``usage_*``.
#: Fixed, not discovered: an unreported counter must be nameable.
SEARCH_COUNTERS: tuple[tuple[str, str], ...] = (
    ("document_counter", "documents"),
    ("index_counter", "indexes"),
    ("indexer_counter", "indexers"),
    ("data_source_counter", "data_sources"),
    ("storage_size_counter", "storage_size"),
    ("synonym_map_counter", "synonym_maps"),
    ("skillset_counter", "skillsets"),
    ("vector_index_size_counter", "vector_index_size"),
)

#: Monitor metric -> stat name.
SEARCH_METRICS: Mapping[str, str] = {
    "SearchLatency": "search_latency_p50_ms",
    "ThrottledSearchQueriesPercentage": "throttled_query_pct",
}

INDEX_STATS = ("document_count", "storage_bytes", "vector_index_bytes")
SERVICE_STATS = (
    "index_count",
    "indexer_count",
    "synonym_map_count",
    "semantic_query_usage",
)


def _field(source: Any, *names: str) -> Any:
    """First present attribute or mapping key among ``names``, else None.

    SDK models and the raw REST dicts disagree on casing, and a fake need
    not reproduce either faithfully to be a useful test double.
    """
    for name in names:
        if isinstance(source, Mapping):
            if name in source:
                return source[name]
        elif hasattr(source, name):
            return getattr(source, name)
    return None


class SearchStats:
    """Key stats for one Azure AI Search index and its service.

    Args:
        endpoint: Search service endpoint.
        index_name: The index these stats describe.
        credential: A ``TokenCredential``.
        indexes_client: Optional pre-built ``SearchIndexClient``. Injected
            in tests; built lazily from the endpoint otherwise.
        metrics: Optional :class:`MetricsReader`. Absent means every
            Monitor stat is reported in ``partial`` and every data-plane
            stat still returns.
        resource_id: ARM id of the search service, needed only by Monitor.
    """

    service = "search"

    def __init__(
        self,
        *,
        endpoint: str = "",
        index_name: str = "",
        credential: Any = None,
        indexes_client: Any = None,
        metrics: MetricsReader | None = None,
        resource_id: str = "",
        metric_window: timedelta = DEFAULT_METRIC_WINDOW,
    ) -> None:
        self._endpoint = endpoint
        self._index_name = index_name
        self._credential = credential
        self._client = indexes_client
        self._metrics = metrics
        self._resource_id = resource_id
        self._window = metric_window

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Any,
        *,
        index_name: str,
        **kwargs: Any,
    ) -> "SearchStats":
        kwargs.setdefault("endpoint", config.search_endpoint)
        kwargs.setdefault("metrics", MetricsReader.from_config(config, credential_provider))
        return cls(
            index_name=index_name,
            credential=credential_provider(),
            **kwargs,
        )

    def _indexes(self) -> Any:
        if self._client is None:
            if not self._endpoint:
                raise StatUnavailable(
                    "search endpoint is not configured (search_endpoint is empty)"
                )
            indexes = load(
                "azure.search.documents.indexes", dist="azure-search-documents"
            )
            self._client = indexes.SearchIndexClient(
                endpoint=self._endpoint, credential=self._credential
            )
        return self._client

    async def stats(self, target: str | None = None) -> str:
        """Return the ``stats`` envelope for ``target`` or the bound index."""
        index = target or self._index_name
        data, partial = await collector(self._data_probes(index))
        monitor, monitor_partial = await collector(self._monitor_probes())
        data.update(monitor)
        partial.extend(monitor_partial)
        return stats_envelope(
            service=self.service,
            target=index,
            source=StatSource.DATA_PLANE,
            stats=data,
            partial=partial,
        )

    # ------------------------------------------------------------------
    # Probes.
    # ------------------------------------------------------------------

    def _data_probes(self, index: str) -> list[Probe]:
        counter_names = tuple(
            f"{prefix}_{suffix}"
            for _, suffix in SEARCH_COUNTERS
            for prefix in ("quota", "usage")
        )
        return [
            (INDEX_STATS, lambda: self._index_statistics(index)),
            (SERVICE_STATS + counter_names, self._service_statistics),
        ]

    def _monitor_probes(self) -> list[Probe]:
        return [
            (
                tuple(SEARCH_METRICS.values()),
                lambda: read_stats(
                    self._metrics,
                    self._resource_id,
                    SEARCH_METRICS,
                    window=self._window,
                ),
            )
        ]

    async def _index_statistics(self, index: str) -> dict[str, Any]:
        if not index:
            raise StatUnavailable("no index name was supplied")
        client = self._indexes()
        raw = await asyncio.to_thread(client.get_index_statistics, index)
        found: dict[str, Any] = {}
        for stat, names in (
            ("document_count", ("document_count", "documentCount")),
            ("storage_bytes", ("storage_size", "storageSize")),
            ("vector_index_bytes", ("vector_index_size", "vectorIndexSize")),
        ):
            value = _field(raw, *names)
            if value is not None:
                found[stat] = value
        return found

    async def _service_statistics(self) -> dict[str, Any]:
        client = self._indexes()
        raw = await asyncio.to_thread(client.get_service_statistics)
        counters = _field(raw, "counters") or {}

        found: dict[str, Any] = {}
        for attribute, suffix in SEARCH_COUNTERS:
            counter = _field(counters, attribute, suffix, f"{suffix}_count")
            if counter is None:
                continue
            quota = _field(counter, "quota")
            usage = _field(counter, "usage")
            if quota is not None:
                found[f"quota_{suffix}"] = quota
            if usage is not None:
                found[f"usage_{suffix}"] = usage

        for stat, suffix in (
            ("index_count", "indexes"),
            ("indexer_count", "indexers"),
            ("synonym_map_count", "synonym_maps"),
        ):
            usage = found.get(f"usage_{suffix}")
            if usage is not None:
                found[stat] = usage

        semantic = _field(
            counters, "semantic_query_counter", "semantic_query_usage"
        )
        if semantic is not None:
            usage = _field(semantic, "usage")
            found["semantic_query_usage"] = semantic if usage is None else usage
        return found


__all__ = [
    "INDEX_STATS",
    "SEARCH_COUNTERS",
    "SEARCH_METRICS",
    "SERVICE_STATS",
    "SearchStats",
]
