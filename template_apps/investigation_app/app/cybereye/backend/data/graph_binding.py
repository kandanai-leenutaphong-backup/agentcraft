"""Exact-target Cosmos read-only-key binding owned by the application host."""

from __future__ import annotations

import asyncio
from typing import Any

from azdata import ConnectorConfig, DataConnector, Limits, Policy, ResourceAddress, connect
from agentcraft_core import current_execution, reserve


def bind_graph(*, account: str, database: str, graph: str, subscription: str,
               resource_group: str, credential: Any, readonly_key_value: str = "",
               require_injected_key: bool = False) -> DataConnector | None:
    if require_injected_key and not readonly_key_value.strip():
        raise ValueError("graph_readonly_key_absent")
    if not all((account, database, graph, subscription, resource_group)):
        if require_injected_key:
            raise ValueError("graph_target_absent")
        return None
    host = f"{account}.gremlin.cosmos.azure.com"
    config = ConnectorConfig(f"wss://{host}", ResourceAddress({"database": database, "container": graph}),
                             (host,), credential_kind="readonly_key")
    key = readonly_key_value or None
    lock = asyncio.Lock()

    async def readonly_key(target: ConnectorConfig) -> str:
        nonlocal key
        if target != config:
            raise ValueError("graph_key_target_outside_scope")
        async with lock:
            if key is None:
                from azure.mgmt.cosmosdb.aio import CosmosDBManagementClient

                execution = current_execution()
                reserve("data_calls")
                try:
                    async with CosmosDBManagementClient(credential, subscription, retry_total=0,
                            connection_timeout=20, read_timeout=20, logging_enable=False) as management:
                        result = await management.database_accounts.list_read_only_keys(resource_group, account)
                        candidate = result.primary_readonly_master_key
                except BaseException:
                    if execution is not None:
                        execution.budget.mark_unknown("data_calls")
                    raise
                if not isinstance(candidate, str) or not candidate:
                    raise ValueError("graph_readonly_key_absent")
                key = candidate
            return key

    return connect("gremlin", config, credential=credential, gremlin_readonly_key_provider=readonly_key,
                   policy=Policy("investigation:graph", {"query"}, max_concurrency=1,
                                 limits=Limits(timeout_seconds=60, max_items=2500,
                                               max_output_bytes=4_194_304, max_attempts=2)))