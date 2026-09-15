"""Cosmos Gremlin control-plane operations, shared by graph-producing pipelines."""

from __future__ import annotations

from functools import cache
from urllib.parse import quote

from app.components.azure_arm import ArmClient, ArmConfig, resource_path

API_VERSION = "2024-11-15"


@cache
def _client() -> ArmClient:
    from azure.identity import DefaultAzureCredential

    return ArmClient(
        ArmConfig(timeout_seconds=120, max_attempts=1),
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
    )


def _account_path(subscription: str, resource_group: str, account: str) -> str:
    return resource_path(subscription, resource_group, "Microsoft.DocumentDB", "databaseAccounts", account)


def cosmos_primary_key(subscription: str, resource_group: str, account: str,
                       *, client: ArmClient | None = None) -> str:
    arm = client or _client()
    _, payload = arm.post(
        f"{_account_path(subscription, resource_group, account)}/listKeys?api-version={API_VERSION}",
        absent_ok=True,
    )
    key = str(payload.get("primaryMasterKey", ""))
    if not key:
        raise RuntimeError("ARM returned no account key")
    return key


def cosmos_ensure_graph(subscription: str, resource_group: str, account: str,
                        database: str, graph: str, partition_key: str,
                        *, max_throughput: int = 4000, wait_seconds: int = 300,
                        client: ArmClient | None = None) -> str:
    arm = client or _client()
    base = _account_path(subscription, resource_group, account)
    database_path = f"{base}/gremlinDatabases/{quote(database, safe='')}"
    graph_path = f"{database_path}/graphs/{quote(graph, safe='')}?api-version={API_VERSION}"
    database_path += f"?api-version={API_VERSION}"
    if arm.get(graph_path, absent_ok=True)[0] == 200:
        return "existing"
    if arm.get(database_path, absent_ok=True)[0] == 404:
        arm.put(database_path, body={"properties": {"resource": {"id": database}, "options": {}}})
        arm.await_provisioned(database_path, wait_seconds=wait_seconds)
    arm.put(graph_path, body={"properties": {
        "resource": {"id": graph, "partitionKey": {"paths": [f"/{partition_key}"], "kind": "Hash"}},
        "options": {"autoscaleSettings": {"maxThroughput": max_throughput}},
    }})
    arm.await_provisioned(graph_path, wait_seconds=wait_seconds)
    return "created"