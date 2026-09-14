"""Azure Monitor metric reads — one service-blind call, never load-bearing.

WHY THIS EXISTS
---------------
Half the stats worth having are not on the data plane. Latency,
throttling, normalized RU consumption and cache utilisation live in Azure
Monitor, behind a *separate* role assignment (``Monitoring Reader``) and a
*separate* SDK (``azure-mgmt-monitor``) that most callers of this library
will never install.

That makes Monitor the one source guaranteed to be unavailable in normal
use, which is precisely why it must not be able to fail a stats call.
:meth:`MetricsReader.read` therefore does not raise. Ever. It returns what
it obtained and, when it obtained nothing, the reason — and the observe
plane turns that reason into ``partial`` entries naming exactly the stats
the caller did not get.

The alternative, an exception crossing into the data-plane collector,
means a missing role assignment deletes the document count from an
operator's screen.

DEPENDENCIES
------------
Standard library, plus ``azure-mgmt-monitor`` loaded on first read.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from azdata.core.config import AzureDataConfig
from azdata.core.envelope import sanitize_detail
from azdata.core.optional import load

logger = logging.getLogger(__name__)

#: Short enough that a value is recent, long enough that a sparse metric
#: has a datapoint in it at all.
DEFAULT_METRIC_WINDOW = timedelta(minutes=30)

#: Monitor names its datapoint attributes after the aggregation, lowercased.
_AGGREGATION_ATTRS = {
    "Average": "average",
    "Total": "total",
    "Minimum": "minimum",
    "Maximum": "maximum",
    "Count": "count",
}


class MetricsUnavailable(RuntimeError):
    """Monitor could not be read at all — no SDK, no role, no subscription.

    Raised by nothing in this module. It exists for the observe planes,
    which raise it inside a probe closure so :func:`azdata.core.observe.collector`
    routes every Monitor stat name into ``partial`` with the reason
    attached, rather than each service inventing its own signalling.
    """


@dataclass(frozen=True)
class MetricRead:
    """What a Monitor read obtained, and why it obtained no more.

    ``detail`` is empty when the read reached Monitor. A non-empty
    ``detail`` with an empty ``values`` is the normal shape here: no SDK
    installed, or no ``Monitoring Reader`` on the resource.
    """

    values: Mapping[str, Any] = field(default_factory=dict)
    detail: str = ""

    @property
    def available(self) -> bool:
        return not self.detail


class MetricsReader:
    """Read Azure Monitor metrics for any resource id. Service-blind.

    Args:
        credential_provider: Returns a ``TokenCredential``.
        subscription_id: Required by the management client. Empty means
            unconfigured, and every read answers with that as its detail
            rather than constructing a client that 401s on first use.
    """

    def __init__(
        self,
        *,
        credential_provider: Callable[[], Any],
        subscription_id: str = "",
    ) -> None:
        self._credential_provider = credential_provider
        self._subscription_id = subscription_id
        self._client: Any = None

    @classmethod
    def from_config(
        cls, config: AzureDataConfig, credential_provider: Callable[[], Any]
    ) -> "MetricsReader":
        return cls(
            credential_provider=credential_provider,
            subscription_id=config.subscription_id,
        )

    async def read(
        self,
        resource_id: str,
        names: Sequence[str],
        window: timedelta = DEFAULT_METRIC_WINDOW,
        aggregation: str = "Average",
    ) -> MetricRead:
        """Read ``names`` for ``resource_id`` over ``window``.

        Returns the latest non-null datapoint per metric. Never raises: a
        missing SDK, a missing role assignment and a malformed response all
        arrive as a :class:`MetricRead` with a detail and no values.
        """
        if not resource_id:
            return MetricRead(detail="no resource id for this target")
        if not self._subscription_id:
            return MetricRead(detail="subscription id not configured")
        if not names:
            return MetricRead()

        try:
            client = self._get_client()
        except Exception as exc:  # noqa: BLE001 - absence is the expected case
            return MetricRead(detail=sanitize_detail(f"{type(exc).__name__}: {exc}"))

        end = datetime.now(timezone.utc)
        timespan = f"{(end - window).isoformat()}/{end.isoformat()}"
        try:
            response = await asyncio.to_thread(
                client.metrics.list,
                resource_id,
                timespan=timespan,
                metricnames=",".join(names),
                aggregation=aggregation,
            )
        except Exception as exc:  # noqa: BLE001 - a denied read is a value here
            logger.info(
                "metrics.read_failed names=%s: %s: %s",
                ",".join(names), type(exc).__name__, exc,
            )
            return MetricRead(detail=sanitize_detail(f"{type(exc).__name__}: {exc}"))

        return MetricRead(values=_latest_values(response, aggregation))

    def _get_client(self) -> Any:
        if self._client is None:
            monitor = load("azure.mgmt.monitor", dist="azure-mgmt-monitor")
            self._client = monitor.MonitorManagementClient(
                self._credential_provider(), self._subscription_id
            )
        return self._client


async def read_stats(
    reader: "MetricsReader | None",
    resource_id: str,
    metric_to_stat: Mapping[str, str],
    *,
    window: timedelta = DEFAULT_METRIC_WINDOW,
    aggregation: str = "Average",
) -> dict[str, Any]:
    """Adapt a Monitor read into a probe body for the observe collector.

    Returns ``{stat_name: value}`` for the metrics Monitor actually
    returned. Raises :class:`MetricsUnavailable` when Monitor could not be
    reached at all, so the collector routes every declared stat name into
    ``partial`` with the reason attached instead of the caller losing a
    data-plane count to a missing role assignment.

    A metric Monitor reached but did not report is simply absent from the
    result; the collector reports it as a missing declared name.
    """
    if reader is None:
        raise MetricsUnavailable(
            "no Azure Monitor reader is wired for this target"
        )
    read = await reader.read(resource_id, list(metric_to_stat), window, aggregation)
    if not read.available:
        raise MetricsUnavailable(read.detail)
    return {
        stat: read.values[metric]
        for metric, stat in metric_to_stat.items()
        if metric in read.values
    }


def _latest_values(response: Any, aggregation: str) -> dict[str, Any]:
    """Map a Monitor response onto ``{metric_name: latest datapoint}``.

    A metric with no datapoint in the window is *omitted*, not zeroed: the
    observe plane reports an absent metric in ``partial``, and a zero would
    read as a measurement.
    """
    attr = _AGGREGATION_ATTRS.get(aggregation, aggregation.lower())
    values: dict[str, Any] = {}
    for metric in getattr(response, "value", None) or []:
        name = getattr(getattr(metric, "name", None), "value", None)
        if name is None:
            continue
        latest: Any = None
        for series in getattr(metric, "timeseries", None) or []:
            for point in getattr(series, "data", None) or []:
                value = getattr(point, attr, None)
                if value is not None:
                    latest = value
        if latest is not None:
            values[name] = latest
    return values


__all__ = [
    "DEFAULT_METRIC_WINDOW",
    "MetricRead",
    "MetricsReader",
    "MetricsUnavailable",
    "read_stats",
]
