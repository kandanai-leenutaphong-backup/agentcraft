"""Cosmos DB NoSQL discovery — databases, then containers, from ARM.

WHY THIS EXISTS
---------------
The obvious implementation asks the data plane. This one asks the
management plane deliberately: DDL and metadata are control-plane
concerns for Cosmos, and an account with ``publicNetworkAccess=Disabled``
answers ARM perfectly well while refusing every data-plane connection.
Discovery therefore works with ARM ``Reader`` alone and is independent of
private endpoints, which is exactly what makes an ``unreachable`` status
meaningful when a *data*-plane level is added later.

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


def resource_block(model: Any) -> Any:
    """The ``resource`` sub-model, whether lifted or under ``properties``.

    A v10 management model is a ``Mapping`` whose interesting values sit
    one level down under ``properties``, while the same object exposes
    ``.resource`` as an attribute and a test double usually has neither
    layer. Both shapes resolve here so no discoverer carries the branch.
    """
    direct = model_field(model, "resource")
    if direct is not None:
        return direct
    return model_field(model_field(model, "properties"), "resource")


def model_name(model: Any, fallback: Any = "") -> str:
    """The addressable name: the top-level one wins over the resource id."""
    name = model_field(model, "name")
    if not name:
        name = model_field(resource_block(model), "id")
    return str(name or fallback)


class CosmosDiscoverer:
    """SQL databases of one account, and the containers of one database."""

    service = "cosmos"
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
    ) -> "CosmosDiscoverer":
        return cls(
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            account_name=config.cosmos_account_name,
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
        """Enumerate databases or containers. Never raises."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service cosmos",
            )

        subscription_id = scope.subscription_id or self._subscription_id
        resource_group = scope.resource_group or self._resource_group
        account = scope.account_name or self._account_name
        database = scope.path[0] if scope.path else ""
        missing = _missing(
            (
                ("subscription_id", subscription_id),
                ("resource_group", resource_group),
                ("cosmos_account_name", account),
            )
            + ((("database", database),) if level == "database" else ())
        )
        if missing:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail=f"cosmos discovery not configured: {missing}",
            )

        def collect() -> Iterator[DiscoveryNode]:
            resources = self._client(subscription_id).sql_resources
            if level == "account":
                listing = resources.list_sql_databases(resource_group, account)
                build = _database_node
            else:
                listing = resources.list_sql_containers(
                    resource_group, account, database
                )
                build = _container_node
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


def _missing(pairs: tuple[tuple[str, str], ...]) -> str:
    for name, value in pairs:
        if not value:
            return name
    return ""


def _database_node(model: Any, scope: DiscoveryScope) -> DiscoveryNode:
    name = model_name(model)
    return DiscoveryNode(
        kind="cosmos_database",
        name=name,
        path=(*scope.path, name),
        has_children=True,
        attributes=normalize_attributes({"id": model_field(model, "id")}),
    )


def _container_node(model: Any, scope: DiscoveryScope) -> DiscoveryNode:
    name = model_name(model)
    resource = resource_block(model)
    partition_key = model_field(resource, "partition_key")
    paths = model_field(partition_key, "paths") or ()
    return DiscoveryNode(
        kind="cosmos_container",
        name=name,
        path=(*scope.path, name),
        has_children=False,
        attributes=normalize_attributes(
            {
                "partition_key_paths": ",".join(str(path) for path in paths),
                "partition_key_kind": model_field(partition_key, "kind"),
                "default_ttl": model_field(resource, "default_ttl"),
                "indexing_mode": model_field(
                    model_field(resource, "indexing_policy"), "indexing_mode"
                ),
                "analytical_ttl": model_field(resource, "analytical_storage_ttl"),
            }
        ),
    )


__all__ = [
    "CosmosDiscoverer",
    "model_name",
    "resource_block",
]
