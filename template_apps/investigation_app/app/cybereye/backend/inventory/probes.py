"""Bind library probes to this deployment's configured read-only sources."""

from collections.abc import Callable, Mapping
from typing import Any

from azdata.graph_read import GraphReadConfig, GremlinReader
from resource_explorer.probes import AdxProbe, GremlinProbe, SearchProbe

from ..config import settings


def default_probes(*, credential_provider: Callable[[], Any] | None = None) -> Mapping[str, Any]:
    def graph_reader(target):
        return GremlinReader(
            GraphReadConfig(target.account, target.database, target.graph,
                            settings.graph_subscription_id, settings.graph_resource_group),
            credential=credential_provider() if credential_provider is not None else None,
            allow_reads=True,
        )

    return {
        "adx": AdxProbe(credential_provider=credential_provider),
        "gremlin": GremlinProbe(service_factory=graph_reader, deployment_account=settings.graph_account),
        "search": SearchProbe(credential_provider=credential_provider),
    }