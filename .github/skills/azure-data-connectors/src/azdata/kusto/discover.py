"""Kusto discovery — databases from ARM, tables from one allowlisted command.

WHY THIS EXISTS
---------------
Databases are an ARM listing. Tables are not: no management-plane
operation enumerates them, so the only way to answer is a control command
against the cluster.

That makes the command surface the thing to bound. ``validate_read_only``
is the wrong tool here — ``.show`` is a control command and the query
guardrail rejects it by design. The substitute is narrower: a literal
allowlist of exactly one command, no interpolation, no caller-supplied
text, no f-string. The database name is passed as the client's database
argument, not concatenated into the command, so no hostile level, scope
or path can cause a second command to be emitted.

DEPENDENCIES
------------
``azure-mgmt-kusto`` and ``azure-kusto-data`` (``discover`` extra), both
loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urlparse

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
from azdata.core.optional import load
from azdata.kusto.deploy import build_management_client
from azdata.kusto.read import shape_kusto_response

#: The complete set of commands this module can emit. Indexed, never
#: formatted. A test drives hostile input through every level and asserts
#: nothing outside this tuple reaches the client.
ALLOWED_COMMANDS: tuple[str, ...] = (".show tables",)


def cluster_name_from_uri(query_uri: str) -> str:
    """``https://adx-x.eastus.kusto.windows.net`` -> ``adx-x``.

    The config carries a query URI, not a cluster resource name, and the
    ARM listing needs the latter. The first host label is the cluster name
    for every Azure Data Explorer endpoint; a Fabric Eventhouse URI has no
    ARM cluster at all, and then the caller supplies the name in the scope.
    """
    host = urlparse(query_uri).hostname or ""
    return host.split(".")[0] if host else ""


class KustoDiscoverer:
    """Databases of one cluster, and the tables of one database."""

    service = "kusto"
    levels = ("cluster", "database")

    def __init__(
        self,
        *,
        subscription_id: str = "",
        resource_group: str = "",
        cluster_name: str = "",
        query_uri: str = "",
        credential_provider: Callable[[], Any],
    ) -> None:
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._cluster_name = cluster_name
        self._query_uri = query_uri
        self._mgmt_clients: dict[str, Any] = {}
        self._data_clients: dict[str, Any] = {}
        self._credential_provider = credential_provider

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        cluster_name: str = "",
    ) -> "KustoDiscoverer":
        return cls(
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            cluster_name=cluster_name or cluster_name_from_uri(config.kql_query_uri),
            query_uri=config.kql_query_uri,
            credential_provider=credential_provider,
        )

    def child_level(self, level: str) -> str | None:
        return "database" if level == "cluster" else None

    def _mgmt(self, subscription_id: str) -> Any:
        client = self._mgmt_clients.get(subscription_id)
        if client is None:
            client = build_management_client(
                self._credential_provider(), subscription_id
            )
            self._mgmt_clients[subscription_id] = client
        return client

    def _data(self, query_uri: str) -> Any:
        client = self._data_clients.get(query_uri)
        if client is None:
            kusto = load("azure.kusto.data", dist="azure-kusto-data")
            kcsb = kusto.KustoConnectionStringBuilder.with_azure_token_credential(
                query_uri, self._credential_provider()
            )
            client = kusto.KustoClient(kcsb)
            self._data_clients[query_uri] = client
        return client

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate databases or tables. Never raises, never improvises a command."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service kusto",
            )
        return await (
            self._databases(scope, bounds)
            if level == "cluster"
            else self._tables(scope, bounds)
        )

    async def _databases(
        self, scope: DiscoveryScope, bounds: DiscoveryBounds
    ) -> DiscoveryResult:
        subscription_id = scope.subscription_id or self._subscription_id
        resource_group = scope.resource_group or self._resource_group
        cluster = scope.account_name or self._cluster_name
        for name, value in (
            ("subscription_id", subscription_id),
            ("resource_group", resource_group),
            ("cluster_name", cluster),
        ):
            if not value:
                return discovery_failure(
                    service=self.service,
                    level="cluster",
                    scope=scope,
                    status="unconfigured",
                    detail=f"kusto discovery not configured: {name}",
                )

        def collect() -> Iterator[DiscoveryNode]:
            client = self._mgmt(subscription_id)
            emitted = 0
            for model in client.databases.list_by_cluster(resource_group, cluster):
                yield _database_node(model, scope)
                emitted += 1
                if emitted > bounds.max_items:
                    return

        return await bounded_discovery(
            service=self.service,
            level="cluster",
            scope=scope,
            bounds=bounds,
            collect=collect,
        )

    async def _tables(
        self, scope: DiscoveryScope, bounds: DiscoveryBounds
    ) -> DiscoveryResult:
        query_uri = scope.endpoint or self._query_uri
        database = scope.path[0] if scope.path else ""
        for name, value in (("kql_query_uri", query_uri), ("database", database)):
            if not value:
                return discovery_failure(
                    service=self.service,
                    level="database",
                    scope=scope,
                    status="unconfigured",
                    detail=f"kusto discovery not configured: {name}",
                )

        def collect() -> Iterator[DiscoveryNode]:
            client = self._data(query_uri)
            response = client.execute_mgmt(database, ALLOWED_COMMANDS[0])
            emitted = 0
            for row in shape_kusto_response(response).get("rows", ()):
                yield _table_node(row, scope)
                emitted += 1
                if emitted > bounds.max_items:
                    return

        return await bounded_discovery(
            service=self.service,
            level="database",
            scope=scope,
            bounds=bounds,
            collect=collect,
        )


def _database_node(model: Any, scope: DiscoveryScope) -> DiscoveryNode:
    """One database. ARM names it ``cluster/database``; the tree wants the leaf."""
    full = str(model_field(model, "name") or "")
    name = full.split("/")[-1]
    return DiscoveryNode(
        kind="kusto_database",
        name=name,
        path=(*scope.path, name),
        has_children=True,
        attributes=normalize_attributes(
            {
                "soft_delete_period": model_field(model, "soft_delete_period"),
                "hot_cache_period": model_field(model, "hot_cache_period"),
            }
        ),
    )


def _table_node(row: dict, scope: DiscoveryScope) -> DiscoveryNode:
    name = str(row.get("TableName") or "")
    return DiscoveryNode(
        kind="kusto_table",
        name=name,
        path=(*scope.path, name),
        has_children=False,
        attributes=normalize_attributes(
            {"folder": row.get("Folder"), "doc_string": row.get("DocString")}
        ),
    )


__all__ = [
    "ALLOWED_COMMANDS",
    "KustoDiscoverer",
    "cluster_name_from_uri",
]
