"""Kusto observe plane — table details, ingestion failures, cluster shape.

WHY THIS EXISTS
---------------
Every number worth having about a Kusto table comes from a control
command, and control commands are exactly what the read guardrails refuse.
``.show table T details`` is allow-listed; ``.show ingestion failures`` is
not, and widening the allow-list would widen it for caller-supplied text
too.

So this module follows the pattern ``GremlinElements`` already
established: it builds a second connector with the guard disabled, and
uses it *only* for commands it assembles itself. Caller text never reaches
it — the table name is validated against an identifier pattern before it is
interpolated, and nothing else is interpolated at all.

DEPENDENCIES
------------
Standard library. The connector loads ``azure-kusto-data`` on first use.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any, Mapping

from azdata.core.envelope import is_error
from azdata.core.metrics import DEFAULT_METRIC_WINDOW, MetricsReader, read_stats
from azdata.core.observe import (
    Probe,
    StatSource,
    StatUnavailable,
    collector,
    stats_envelope,
)
from azdata.kusto.read import KqlConnector

logger = logging.getLogger(__name__)

#: Monitor metric -> stat name.
KUSTO_METRICS: Mapping[str, str] = {
    "CacheUtilization": "cache_utilisation_pct",
    "CPU": "cpu_pct",
    "StageLatency": "ingestion_latency_s",
}

TABLE_STATS = ("table_row_count", "table_extent_bytes", "hot_extent_bytes")
MANAGEMENT_STATS = ("cluster_state", "sku", "instance_count")

# The only caller value that reaches a generated control command. Anything
# outside this shape is refused rather than escaped: Kusto identifier
# quoting has enough corners that a rejection is the safer contract.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _field(source: Any, *names: str) -> Any:
    for name in names:
        if isinstance(source, Mapping):
            if name in source:
                return source[name]
        elif hasattr(source, name):
            return getattr(source, name)
    return None


class KustoStats:
    """Key stats for one Kusto table and its cluster.

    Args:
        connector: A configured :class:`KqlConnector`. Its coordinates,
            credential and gate are reused; a second connector with the
            read-only guard disabled is built from them for the control
            commands this module generates.
        table: Table these stats describe. Must be a plain identifier.
        mgmt_client: Optional ``azure-mgmt-kusto`` client.
        metrics: Optional :class:`MetricsReader`.
    """

    service = "kusto"

    def __init__(
        self,
        *,
        connector: KqlConnector,
        table: str = "",
        mgmt_client: Any = None,
        cluster_name: str = "",
        resource_group: str = "",
        metrics: MetricsReader | None = None,
        resource_id: str = "",
        metric_window: timedelta = DEFAULT_METRIC_WINDOW,
    ) -> None:
        self._table = table
        self._mgmt = mgmt_client
        self._cluster = cluster_name
        self._resource_group = resource_group
        self._metrics = metrics
        self._resource_id = resource_id
        self._window = metric_window
        # A separate connector rather than a flag on the shared one: a flag
        # is process-wide mutable state an unrelated concurrent read would
        # observe, so one stats call would silently un-guard every caller.
        self._commands = KqlConnector(
            resolve_target=connector._resolve_target,
            credential_provider=connector._credential_provider,
            gate_provider=connector._gate_provider,
            validate_fn=None,       # generated control commands are not queries
            transform_query=None,   # '| take' on a control command changes it
            error_detail_prefix="Kusto control command failed",
        )

    async def stats(self, target: str | None = None) -> str:
        table = target or self._table
        data, partial = await collector(self._data_probes(table))
        management, management_partial = await collector(self._management_probes())
        monitor, monitor_partial = await collector(self._monitor_probes())
        data.update(management)
        data.update(monitor)
        partial.extend(management_partial)
        partial.extend(monitor_partial)
        return stats_envelope(
            service=self.service,
            target=table,
            source=StatSource.DATA_PLANE,
            stats=data,
            partial=partial,
        )

    # ------------------------------------------------------------------
    # Probes.
    # ------------------------------------------------------------------

    def _data_probes(self, table: str) -> list[Probe]:
        return [
            (TABLE_STATS, lambda: self._table_details(table)),
            (("ingestion_failures_24h",), self._ingestion_failures),
        ]

    def _management_probes(self) -> list[Probe]:
        return [(MANAGEMENT_STATS, self._management)]

    def _monitor_probes(self) -> list[Probe]:
        return [
            (
                tuple(KUSTO_METRICS.values()),
                lambda: read_stats(
                    self._metrics,
                    self._resource_id,
                    KUSTO_METRICS,
                    window=self._window,
                ),
            )
        ]

    @staticmethod
    def _identifier(table: str) -> str:
        if not table:
            raise StatUnavailable("no table name was supplied")
        if not _IDENTIFIER.match(table):
            raise StatUnavailable(
                f"'{table}' is not a plain Kusto identifier and will not be "
                "interpolated into a control command"
            )
        return table

    async def _command(self, command: str) -> list[dict]:
        payload = await self._commands.execute(command)
        if is_error(payload):
            raise StatUnavailable(json.loads(payload).get("detail", "command failed"))
        shaped = json.loads(payload)
        return list(shaped.get("rows") or []) if isinstance(shaped, dict) else []

    async def _table_details(self, table: str) -> dict[str, Any]:
        rows = await self._command(f".show table {self._identifier(table)} details")
        if not rows:
            raise StatUnavailable(f"'{table}' reported no details; it may not exist")
        row = rows[0]
        found: dict[str, Any] = {}
        for stat, columns in (
            ("table_row_count", ("TotalRowCount", "RowCount")),
            ("table_extent_bytes", ("TotalExtentSize", "ExtentSize")),
            ("hot_extent_bytes", ("HotExtentSize",)),
        ):
            value = _field(row, *columns)
            if value is not None:
                found[stat] = value
        return found

    async def _ingestion_failures(self) -> int:
        rows = await self._command(
            ".show ingestion failures | where FailedOn > ago(24h) | count"
        )
        if not rows:
            raise StatUnavailable("the ingestion failure count returned no row")
        value = _field(rows[0], "Count", "count")
        if value is None:
            raise StatUnavailable("the ingestion failure count returned no Count column")
        return int(value)

    async def _management(self) -> dict[str, Any]:
        if self._mgmt is None:
            raise StatUnavailable("no Kusto management client is wired for this cluster")
        if not self._resource_group or not self._cluster:
            raise StatUnavailable(
                "resource_group and cluster_name are required for the "
                "management-plane stats"
            )
        cluster = self._mgmt.clusters.get(self._resource_group, self._cluster)
        found: dict[str, Any] = {}
        state = _field(cluster, "state")
        if state is not None:
            found["cluster_state"] = state
        sku = _field(cluster, "sku")
        if sku is not None:
            name = _field(sku, "name")
            if name is not None:
                found["sku"] = name
            capacity = _field(sku, "capacity")
            if capacity is not None:
                found["instance_count"] = capacity
        return found


__all__ = ["KUSTO_METRICS", "MANAGEMENT_STATS", "TABLE_STATS", "KustoStats"]
