"""Gremlin observe plane — counts through the guarded read connector.

WHY THIS EXISTS
---------------
Two things make graph stats different from every other service here.

**The counts are traversals, so they go through the guardrails.** Every
count below is submitted through the read-only :class:`GremlinConnector`,
which validates and row-caps it like any other traversal. A stats path
that bypassed the guard would be a second, unreviewed way to submit
arbitrary Gremlin, and the whole point of the read connector is that there
is exactly one.

**The RU charge is not in the result.** Cosmos reports it in the
traversal's status attributes, which the driver hangs on the result set;
the rows carry no trace of it. ``GremlinConnector.last_status_attributes``
retains the last set, and when it holds no charge — no traversal has run,
or the service did not send one — ``last_request_charge_ru`` is named in
``partial``. It is never zero, because no traversal is free.

DEPENDENCIES
------------
Standard library. The connector loads ``gremlinpython`` on first use.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Mapping

from azdata.core.envelope import is_error
from azdata.core.metrics import DEFAULT_METRIC_WINDOW, MetricsReader
from azdata.core.observe import (
    Probe,
    StatSource,
    StatUnavailable,
    collector,
    stats_envelope,
)

logger = logging.getLogger(__name__)

#: Cosmos reports the total charge for a traversal under this attribute.
CHARGE_ATTRIBUTE = "x-ms-total-request-charge"

MANAGEMENT_STATS = ("throughput_ru", "graph_partition_key")


def _field(source: Any, *names: str) -> Any:
    for name in names:
        if isinstance(source, Mapping):
            if name in source:
                return source[name]
        elif hasattr(source, name):
            return getattr(source, name)
    return None


class GremlinStats:
    """Key stats for one Cosmos DB graph.

    Args:
        connector: The read-only ``GremlinConnector``. Counts are submitted
            through it, guardrails included.
        database / graph: Coordinates, used to label the target and to read
            the management plane.
        mgmt_client: Optional ``azure-mgmt-cosmosdb`` client. Absent means
            the management stats are reported in ``partial``.
        metrics: Optional :class:`MetricsReader`. Gremlin has no
            graph-scoped Monitor metric worth naming here; the account's
            metrics belong to the Cosmos observe plane.
    """

    service = "gremlin"

    def __init__(
        self,
        *,
        connector: Any,
        database: str = "",
        graph: str = "",
        mgmt_client: Any = None,
        account_name: str = "",
        resource_group: str = "",
        metrics: MetricsReader | None = None,
        resource_id: str = "",
        metric_window: timedelta = DEFAULT_METRIC_WINDOW,
    ) -> None:
        self._connector = connector
        self._database = database
        self._graph = graph
        self._mgmt = mgmt_client
        self._account = account_name
        self._resource_group = resource_group
        self._metrics = metrics
        self._resource_id = resource_id
        self._window = metric_window

    @property
    def target(self) -> str:
        return f"{self._database}/{self._graph}".strip("/")

    async def stats(self, target: str | None = None) -> str:
        data, partial = await collector(self._data_probes())
        management, management_partial = await collector(self._management_probes())
        data.update(management)
        partial.extend(management_partial)
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
            (("vertex_count",), lambda: self._scalar("g.V().count()")),
            (("edge_count",), lambda: self._scalar("g.E().count()")),
            (("label_histogram",), self._label_histogram),
            (("last_request_charge_ru",), self._request_charge),
        ]

    def _management_probes(self) -> list[Probe]:
        return [(MANAGEMENT_STATS, self._management)]

    async def _traverse(self, traversal: str) -> list:
        payload = await self._connector.execute(traversal)
        if is_error(payload):
            raise StatUnavailable(json.loads(payload).get("detail", "traversal failed"))
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, list) else [parsed]

    async def _scalar(self, traversal: str) -> int:
        rows = await self._traverse(traversal)
        if not rows:
            raise StatUnavailable(f"{traversal} returned no row")
        return int(rows[0])

    async def _label_histogram(self) -> dict:
        rows = await self._traverse("g.V().groupCount().by(label)")
        if not rows:
            raise StatUnavailable("the label histogram returned no row")
        histogram = rows[0]
        if not isinstance(histogram, Mapping):
            raise StatUnavailable(
                f"the label histogram returned {type(histogram).__name__}, "
                "not a mapping"
            )
        return dict(histogram)

    async def _request_charge(self) -> float:
        attributes = getattr(self._connector, "last_status_attributes", None) or {}
        charge = attributes.get(CHARGE_ATTRIBUTE)
        if charge is None:
            raise StatUnavailable(
                f"the last traversal reported no {CHARGE_ATTRIBUTE}; no charge "
                "is knowable without one"
            )
        return float(charge)

    async def _management(self) -> dict[str, Any]:
        if self._mgmt is None:
            raise StatUnavailable(
                "no Cosmos management client is wired for this graph"
            )
        if not self._resource_group or not self._account:
            raise StatUnavailable(
                "resource_group and account_name are required for the "
                "management-plane stats"
            )
        found: dict[str, Any] = {}
        throughput = self._mgmt.gremlin_resources.get_gremlin_graph_throughput(
            self._resource_group, self._account, self._database, self._graph
        )
        resource = _field(throughput, "resource") or throughput
        value = _field(resource, "throughput")
        if value is not None:
            found["throughput_ru"] = value

        graph = self._mgmt.gremlin_resources.get_gremlin_graph(
            self._resource_group, self._account, self._database, self._graph
        )
        graph_resource = _field(graph, "resource") or graph
        partition_key = _field(graph_resource, "partition_key", "partitionKey")
        paths = _field(partition_key, "paths") if partition_key is not None else None
        if paths:
            found["graph_partition_key"] = list(paths)[0]
        return found


__all__ = ["CHARGE_ATTRIBUTE", "MANAGEMENT_STATS", "GremlinStats"]
