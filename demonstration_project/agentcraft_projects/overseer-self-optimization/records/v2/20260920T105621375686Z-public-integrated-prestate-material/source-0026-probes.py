"""Bind library probes to this deployment's configured read-only sources."""

from collections.abc import Callable, Mapping
from typing import Any

from resource_explorer.probes import AdxProbe, GremlinProbe, SearchProbe

from ..config import settings
from ..data.graph import GraphService
from ..data.graph_binding import bind_graph


def default_probes(*, credential_provider: Callable[[], Any] | None = None) -> Mapping[str, Any]:
    def graph_reader(target):
        return GraphService(account=target.account, database=target.database, graph=target.graph,
            connector=bind_graph(account=target.account, database=target.database, graph=target.graph,
                subscription=settings.graph_subscription_id, resource_group=settings.graph_resource_group,
                credential=credential_provider() if credential_provider is not None else None))

    return {
        "adx": AdxProbe(credential_provider=credential_provider),
        "gremlin": GremlinProbe(service_factory=graph_reader, deployment_account=settings.graph_account),
        "search": SearchProbe(credential_provider=credential_provider),
    }