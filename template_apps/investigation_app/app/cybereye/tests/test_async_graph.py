from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from azdata import ContentValue, ItemResult, OperationResult, ResourceAddress
from app.cybereye.backend.data.graph import GraphNotFound, GraphService, GraphUnavailable
from app.cybereye.backend.data.graph_binding import bind_graph


def result(rows=(), *, truncated=False):
    return OperationResult(request_id="fixture", service="gremlin", operation="query", status="success",
                           target=ResourceAddress({"database": "database", "container": "graph"}),
                           items=tuple(ItemResult(index, None, "success", ContentValue(row))
                                       for index, row in enumerate(rows)), truncated=truncated)


@pytest.mark.asyncio
async def test_async_graph_counts_cache_absence_partial_and_cleanup():
    connector = SimpleNamespace(query=AsyncMock(side_effect=[result([3]), result([4]), result(), result([1], truncated=True)]),
                                aclose=AsyncMock())
    graph = GraphService(connector=connector)
    assert (await graph.status())["vertices"] == 3
    assert (await graph.status())["edges"] == 4
    assert connector.query.await_count == 2
    with pytest.raises(GraphNotFound):
        await graph.neighbourhood("missing")
    with pytest.raises(GraphUnavailable, match="incomplete"):
        await graph._submit("g.V()")
    await graph.aclose()
    connector.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_readonly_lookup_borrows_identity_and_reads_exact_account():
    credential = SimpleNamespace(get_token=AsyncMock(), close=AsyncMock())
    management = MagicMock()
    management.__aenter__ = AsyncMock(return_value=management)
    management.__aexit__ = AsyncMock()
    management.database_accounts.list_read_only_keys = AsyncMock(
        return_value=SimpleNamespace(primary_readonly_master_key="synthetic-readonly-key"))
    native = MagicMock()
    native.submit.return_value.all.return_value.result.return_value = [7]
    connector = bind_graph(account="fixture", database="database", graph="graph", subscription="subscription",
                           resource_group="group", credential=credential)
    graph = GraphService(connector=connector)
    with patch("azure.mgmt.cosmosdb.aio.CosmosDBManagementClient", return_value=management) as factory, \
            patch("gremlin_python.driver.client.Client", return_value=native):
        assert await graph.element_count("vertices") == 7
        assert await graph.element_count("edges") == 7
    factory.assert_called_once()
    assert factory.call_args.args == (credential, "subscription")
    management.database_accounts.list_read_only_keys.assert_awaited_once_with("group", "fixture")
    management.database_accounts.list_keys.assert_not_called()
    management.__aexit__.assert_awaited_once()
    await graph.aclose()
    credential.close.assert_not_called()