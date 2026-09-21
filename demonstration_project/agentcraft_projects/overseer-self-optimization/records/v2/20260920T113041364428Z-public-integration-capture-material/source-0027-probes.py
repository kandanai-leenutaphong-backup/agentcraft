"""Bind library probes to this deployment's configured read-only sources."""

from collections.abc import Callable, Mapping
from typing import Any

from resource_explorer.probes import AdxProbe, CosmosProbe, GremlinProbe, SearchProbe

from ..config import settings
from ..data.graph import GraphService
from ..data.graph_binding import bind_graph


def default_probes(*, credential_provider: Callable[[], Any] | None = None,
                   public_telemetry=None, public_graph=None) -> Mapping[str, Any]:
    def graph_reader(target):
        if public_telemetry is not None:
            from ..data.public_graph import PublicGraphService
            if public_graph is None or (target.account, target.database, target.graph) != public_graph.target:
                raise ValueError("public graph target mismatch")
            return PublicGraphService(telemetry=public_telemetry, account=target.account,
                database=target.database, graph=target.graph, connector=public_graph.connector, owns_connector=False)
        return GraphService(account=target.account, database=target.database, graph=target.graph,
            connector=bind_graph(account=target.account, database=target.database, graph=target.graph,
                subscription=settings.graph_subscription_id, resource_group=settings.graph_resource_group,
                credential=credential_provider() if credential_provider is not None else None))

    return {
        **({"cosmos": CosmosProbe(credential_provider=credential_provider)} if public_telemetry is not None
           else {"adx": AdxProbe(credential_provider=credential_provider)}),
        "gremlin": GremlinProbe(service_factory=graph_reader, deployment_account=settings.graph_account),
        "search": SearchProbe(credential_provider=credential_provider),
    }