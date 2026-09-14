"""Cosmos DB Gremlin discovery — databases, then graphs, from ARM.

Management plane, same reasoning as the Cosmos NoSQL discoverer and one
more besides: the Gremlin data plane is a WebSocket, and a WebSocket
against a private-only account fails at the upgrade with no useful
diagnostic (GOTCHAS.md G12). Nothing here opens one.

DEPENDENCIES
------------
``azure-mgmt-cosmosdb`` (``discover`` extra), loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from azdata.core.config import AzureDataConfig
from azdata.core.discover import (
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    bounded_discovery,
    discovery_failure,
    model_field,
    normalize_attributes,
)
from azdata.cosmos.deploy import build_management_client
from azdata.cosmos.discover import model_name, resource_block


class GremlinDiscoverer:
    """Gremlin databases of one account, and the graphs of one database."""

    service = "gremlin"
    levels = ("account", "database")

    def __init__(
        self,
        *,
        subscription_id: str = "",
        resource_group: str = "",
        account_name: str = "",
        credential_provider: Callable[[], Any],
    ) -> None:
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._account_name = account_name
        self._credential_provider = credential_provider
        self._clients: dict[str, Any] = {}

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
    ) -> "GremlinDiscoverer":
        return cls(
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            account_name=config.gremlin_account_name,
            credential_provider=credential_provider,
        )

    def child_level(self, level: str) -> str | None:
        return "database" if level == "account" else None

    def _client(self, subscription_id: str) -> Any:
        client = self._clients.get(subscription_id)
        if client is None:
            client = build_management_client(
                self._credential_provider(), subscription_id
            )
            self._clients[subscription_id] = client
        return client

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate Gremlin databases or graphs. Never raises."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service gremlin",
            )

        subscription_id = scope.subscription_id or self._subscription_id
        resource_group = scope.resource_group or self._resource_group
        account = scope.account_name or self._account_name
        database = scope.path[0] if scope.path else ""
        for name, value in (
            ("subscription_id", subscription_id),
            ("resource_group", resource_group),
            ("gremlin_account_name", account),
        ) + ((("database", database),) if level == "database" else ()):
            if not value:
                return discovery_failure(
                    service=self.service,
                    level=level,
                    scope=scope,
                    status="unconfigured",
                    detail=f"gremlin discovery not configured: {name}",
                )

        def collect() -> Iterator[DiscoveryNode]:
            resources = self._client(subscription_id).gremlin_resources
            if level == "account":
                listing = resources.list_gremlin_databases(resource_group, account)
                build = _database_node
            else:
                listing = resources.list_gremlin_graphs(
                    resource_group, account, database
                )
                build = _graph_node
            emitted = 0
            for model in listing:
                yield build(model, scope)
                emitted += 1
                if emitted > bounds.max_items:
                    return

        return await bounded_discovery(
            service=self.service,
            level=level,
            scope=scope,
            bounds=bounds,
            collect=collect,
        )


def _database_node(model: Any, scope: DiscoveryScope) -> DiscoveryNode:
    name = model_name(model)
    return DiscoveryNode(
        kind="gremlin_database",
        name=name,
        path=(*scope.path, name),
        has_children=True,
        attributes=normalize_attributes({"id": model_field(model, "id")}),
    )


def _graph_node(model: Any, scope: DiscoveryScope) -> DiscoveryNode:
    name = model_name(model)
    resource = resource_block(model)
    partition_key = model_field(resource, "partition_key")
    paths = model_field(partition_key, "paths") or ()
    return DiscoveryNode(
        kind="gremlin_graph",
        name=name,
        path=(*scope.path, name),
        has_children=False,
        attributes=normalize_attributes(
            {
                "partition_key_paths": ",".join(str(path) for path in paths),
                "default_ttl": model_field(resource, "default_ttl"),
                "indexing_mode": model_field(
                    model_field(resource, "indexing_policy"), "indexing_mode"
                ),
            }
        ),
    )


__all__ = [
    "GremlinDiscoverer",
]
