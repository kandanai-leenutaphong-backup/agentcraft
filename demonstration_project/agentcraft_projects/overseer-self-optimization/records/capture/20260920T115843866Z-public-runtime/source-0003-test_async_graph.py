import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from azdata import ContentValue, ItemResult, OperationResult, ResourceAddress
from agentcraft_core import CallerContext, ExecutionContext
from app.cybereye.backend.data.graph import GraphNotFound, GraphService, GraphUnavailable
from app.cybereye.backend.data.graph_binding import bind_graph
from resource_explorer import ResultCache
from resource_explorer.probes import GremlinProbe


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [0, 100, 101])
async def test_graph_preview_extra_row_preserves_host_sample_clamp(available):
    async def query(request):
        limit = int(request.expression.split(".limit(")[1].split(")")[0])
        return result([{"id": str(index), "label": "Host"} for index in range(min(limit, available))])

    connector = SimpleNamespace(query=AsyncMock(side_effect=query), aclose=AsyncMock())
    graph = GraphService(account="account", database="db", graph="graph", connector=connector)
    assert len(await graph.sample("vertices", 101)) == min(available, 100)
    assert ".limit(100)" in connector.query.call_args.args[0].expression
    probe = GremlinProbe(service_factory=lambda target: graph, deployment_account="account")
    source = SimpleNamespace(binding=SimpleNamespace(coordinates={
        "account": "account", "database": "db", "graph": "graph"}))
    preview = await probe.preview(source, limit=100)
    assert preview.status == ("empty" if available == 0 else "ok")
    assert len(preview.payload.rows) == min(available, 100)
    assert preview.truncated is (available > 100)
    assert ".limit(101)" in connector.query.call_args.args[0].expression
    await probe.aclose()
    await graph.aclose()
    connector.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_graph_host_can_borrow_connector():
    connector = SimpleNamespace(query=AsyncMock(return_value=result([1])), aclose=AsyncMock())
    graph = GraphService(connector=connector, owns_connector=False)
    assert await graph.element_count("vertices") == 1
    await graph.aclose()
    connector.aclose.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("origin, expires", [("started", 120), ("completed", 130)])
async def test_cache_clock_origin_singleflight_and_failure(origin, expires):
    now = [0.0]
    cache = ResultCache(ttl_secs=120, clock=lambda: now[0], ttl_origin=origin)
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch():
        entered.set()
        await release.wait()
        now[0] = 10
        return {"status": "failure"}

    build = AsyncMock(side_effect=fetch)
    first = asyncio.create_task(cache.get("key", build))
    await entered.wait()
    second = asyncio.create_task(cache.get("key", build))
    release.set()
    assert await first == await second == {"status": "failure"}
    assert build.await_count == 1
    now[0] = expires - 1
    await cache.get("key", build)
    assert build.await_count == 1
    now[0] = expires
    await cache.get("key", build)
    assert build.await_count == 2
    failing = AsyncMock(side_effect=[RuntimeError("offline"), 7])
    with pytest.raises(RuntimeError, match="offline"):
        await cache.get("failed", failing)
    assert await cache.get("failed", failing) == 7
    cache.invalidate()
    assert await cache.get("key", AsyncMock(return_value=None)) is None


@pytest.mark.asyncio
async def test_graph_cache_preserves_started_ttl_and_keys():
    now = [0.0]
    graph = GraphService(clock=lambda: now[0])

    async def build():
        now[0] += 10
        return object()

    fetch = AsyncMock(side_effect=build)
    value = await graph._cached("overview", fetch)
    now[0] = 119
    assert await graph._cached("overview", fetch) is value
    now[0] = 120
    assert await graph._cached("overview", fetch) is not value
    await graph._cached("count:vertices", fetch)
    assert fetch.await_count == 3


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
    execution = ExecutionContext.create(CallerContext("fixture"), limits={"data_calls": 3})
    with execution.activate(), patch("azure.mgmt.cosmosdb.aio.CosmosDBManagementClient", return_value=management) as factory, \
            patch("gremlin_python.driver.client.Client", return_value=native):
        assert await graph.element_count("vertices") == 7
        assert await graph.element_count("edges") == 7
    assert execution.budget.snapshot()["reserved"] == {"data_calls": 3}
    factory.assert_called_once()
    assert factory.call_args.args == (credential, "subscription")
    management.database_accounts.list_read_only_keys.assert_awaited_once_with("group", "fixture")
    management.database_accounts.list_keys.assert_not_called()
    management.__aexit__.assert_awaited_once()
    await graph.aclose()
    credential.close.assert_not_called()