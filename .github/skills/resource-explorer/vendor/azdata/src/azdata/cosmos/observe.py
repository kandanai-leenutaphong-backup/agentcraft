"""Cosmos NoSQL observe plane — counts, container shape, RU signal.

WHY THIS EXISTS
---------------
Cosmos splits the numbers an operator needs across three planes that need
three different grants, and the one that matters most during an incident —
the RU charge — is not a metric at all. It arrives as a response header on
the last request and is gone.

**The charge is never invented.** ``last_request_charge_ru`` is read from
``x-ms-request-charge`` on the most recent response. When the header is
absent — no request has been made through this container yet, or the SDK
did not retain it — the stat is named in ``partial``. A zero would read as
a free query, which no Cosmos query is.

**Throughput needs the management plane.** ``throughput_ru`` and
``autoscale_max_ru`` are ARM reads behind a different role assignment than
the data-plane contributor role that lets you count items. Without a
management client wired, the three management stats appear in ``partial``
and every data-plane stat still returns.

DEPENDENCIES
------------
Standard library, plus ``azure-cosmos`` on the caller's container.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Mapping

from azdata.core.metrics import DEFAULT_METRIC_WINDOW, MetricsReader, read_stats
from azdata.core.observe import (
    Probe,
    StatSource,
    StatUnavailable,
    collector,
    stats_envelope,
)

logger = logging.getLogger(__name__)

#: Monitor metric -> stat name.
COSMOS_METRICS: Mapping[str, str] = {
    "TotalRequestUnits": "total_request_units",
    "NormalizedRUConsumption": "normalized_ru_pct",
    "ServerSideLatency": "server_side_latency_ms",
}

CONTAINER_STATS = ("partition_key_paths", "indexing_mode", "ttl_seconds")
HEADER_STATS = ("last_request_charge_ru", "session_token")
MANAGEMENT_STATS = ("throughput_ru", "autoscale_max_ru", "is_serverless")

_CHARGE_HEADER = "x-ms-request-charge"
_SESSION_HEADER = "x-ms-session-token"


def _field(source: Any, *names: str) -> Any:
    for name in names:
        if isinstance(source, Mapping):
            if name in source:
                return source[name]
        elif hasattr(source, name):
            return getattr(source, name)
    return None


class CosmosStats:
    """Key stats for one Cosmos NoSQL container.

    Args:
        container: An async ``ContainerProxy``, the same object
            :class:`~azdata.cosmos.write.CosmosItems` writes through.
        database: Database name, used only to label the target.
        container_name: Container name, used only to label the target.
        mgmt_client: Optional ``azure-mgmt-cosmosdb`` client. Absent means
            the three management stats are reported in ``partial``.
        account_name / resource_group: Coordinates for the management read.
        metrics: Optional :class:`MetricsReader`.
        resource_id: ARM id of the account, needed only by Monitor.
    """

    service = "cosmos"

    def __init__(
        self,
        *,
        container: Any,
        database: str = "",
        container_name: str = "",
        mgmt_client: Any = None,
        account_name: str = "",
        resource_group: str = "",
        metrics: MetricsReader | None = None,
        resource_id: str = "",
        metric_window: timedelta = DEFAULT_METRIC_WINDOW,
    ) -> None:
        self._container = container
        self._database = database
        self._container_name = container_name
        self._mgmt = mgmt_client
        self._account = account_name
        self._resource_group = resource_group
        self._metrics = metrics
        self._resource_id = resource_id
        self._window = metric_window

    @property
    def target(self) -> str:
        return f"{self._database}/{self._container_name}".strip("/")

    async def stats(self, target: str | None = None) -> str:
        data, partial = await collector(self._data_probes())
        management, management_partial = await collector(self._management_probes())
        monitor, monitor_partial = await collector(self._monitor_probes())
        data.update(management)
        data.update(monitor)
        partial.extend(management_partial)
        partial.extend(monitor_partial)
        return stats_envelope(
            service=self.service,
            target=target or self.target,
            source=StatSource.DATA_PLANE,
            stats=data,
            partial=partial,
        )

    # ------------------------------------------------------------------
    # Probes.
    # ------------------------------------------------------------------

    def _data_probes(self) -> list[Probe]:
        return [
            (("item_count",), self._item_count),
            (CONTAINER_STATS, self._container_properties),
            (HEADER_STATS, self._response_headers),
        ]

    def _management_probes(self) -> list[Probe]:
        return [(MANAGEMENT_STATS, self._management)]

    def _monitor_probes(self) -> list[Probe]:
        return [
            (
                tuple(COSMOS_METRICS.values()),
                lambda: read_stats(
                    self._metrics,
                    self._resource_id,
                    COSMOS_METRICS,
                    window=self._window,
                ),
            )
        ]

    async def _item_count(self) -> int:
        rows = []
        async for row in self._container.query_items(
            query="SELECT VALUE COUNT(1) FROM c", parameters=[]
        ):
            rows.append(row)
        if not rows:
            raise StatUnavailable("the count query returned no row")
        return int(rows[0])

    async def _container_properties(self) -> dict[str, Any]:
        props = await self._container.read()
        found: dict[str, Any] = {}
        partition_key = _field(props, "partitionKey", "partition_key")
        paths = _field(partition_key, "paths") if partition_key is not None else None
        if paths is not None:
            found["partition_key_paths"] = list(paths)
        policy = _field(props, "indexingPolicy", "indexing_policy")
        mode = _field(policy, "indexingMode", "indexing_mode") if policy else None
        if mode is not None:
            found["indexing_mode"] = mode
        ttl = _field(props, "defaultTtl", "default_ttl", "ttl_seconds")
        if ttl is not None:
            found["ttl_seconds"] = ttl
        return found

    async def _response_headers(self) -> dict[str, Any]:
        """Read the charge and session token off the last response.

        Returns only what the headers actually carried. A missing header is
        a ``partial`` entry, made by the collector from the declared names.
        """
        connection = getattr(self._container, "client_connection", None)
        headers = getattr(connection, "last_response_headers", None)
        if not isinstance(headers, Mapping):
            raise StatUnavailable(
                "the container client exposes no response headers; no request "
                "has been made through it yet"
            )
        found: dict[str, Any] = {}
        charge = headers.get(_CHARGE_HEADER)
        if charge is not None:
            found["last_request_charge_ru"] = float(charge)
        session = headers.get(_SESSION_HEADER)
        if session is not None:
            found["session_token"] = session
        return found

    async def _management(self) -> dict[str, Any]:
        if self._mgmt is None:
            raise StatUnavailable(
                "no Cosmos management client is wired for this container"
            )
        if not self._resource_group or not self._account:
            raise StatUnavailable(
                "resource_group and account_name are required for the "
                "management-plane stats"
            )
        found: dict[str, Any] = {}
        throughput = self._mgmt.sql_resources.get_sql_container_throughput(
            self._resource_group,
            self._account,
            self._database,
            self._container_name,
        )
        resource = _field(throughput, "resource") or throughput
        value = _field(resource, "throughput")
        if value is not None:
            found["throughput_ru"] = value
        autoscale = _field(resource, "autoscale_settings", "autoscaleSettings")
        if autoscale is not None:
            maximum = _field(autoscale, "max_throughput", "maxThroughput")
            if maximum is not None:
                found["autoscale_max_ru"] = maximum

        account = self._mgmt.database_accounts.get(self._resource_group, self._account)
        capabilities = _field(account, "capabilities") or []
        found["is_serverless"] = any(
            _field(capability, "name") == "EnableServerless"
            for capability in capabilities
        )
        return found


__all__ = [
    "CONTAINER_STATS",
    "COSMOS_METRICS",
    "HEADER_STATS",
    "MANAGEMENT_STATS",
    "CosmosStats",
]
