"""test_observe_plane — the stats contract, with no SDKs and no cloud account.

Run: ``python3 -m pytest tests/unit/test_observe_plane.py``.

Every Azure SDK is replaced through ``azdata.core.optional.override``, the
same seam ``tests/unit/selftest.py`` uses. What is being proven is the two
sentences the observe plane exists for:

* a stats call never fails wholesale because one counter was unavailable;
* a stats call never omits a counter silently.

Each service test drives off a declared tuple of the stat names in
SPEC.md §6.2, so an implementation that quietly stops producing one fails
here rather than drifting.
"""

from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.breaker import get_gate, reset_gates  # noqa: E402
from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.core.journal import JournalRecord, OperationJournal  # noqa: E402
from azdata.core.metrics import (  # noqa: E402
    MetricRead,
    MetricsReader,
    MetricsUnavailable,
    read_stats,
)
from azdata.core.observe import (  # noqa: E402
    StatSource,
    StatUnavailable,
    collector,
    stats_envelope,
)
from azdata.core.optional import clear_overrides, override, override_missing  # noqa: E402
from azdata.cosmos.observe import CosmosStats  # noqa: E402
from azdata.fabric_graph.observe import GraphStats  # noqa: E402
from azdata.fabric_graph.read import GraphConnector  # noqa: E402
from azdata.gremlin.observe import CHARGE_ATTRIBUTE, GremlinStats  # noqa: E402
from azdata.gremlin.read import GremlinConnector  # noqa: E402
from azdata.kusto.observe import KustoStats  # noqa: E402
from azdata.kusto.read import KqlConnector  # noqa: E402
from azdata.search.observe import SEARCH_COUNTERS, SearchStats  # noqa: E402

# ── The spec's per-service stat tables, as data ──────────────────────────────

SEARCH_EXPECTED = (
    "document_count",
    "storage_bytes",
    "vector_index_bytes",
    "index_count",
    "indexer_count",
    "synonym_map_count",
    "semantic_query_usage",
    "search_latency_p50_ms",
    "throttled_query_pct",
) + tuple(
    f"{prefix}_{suffix}"
    for _, suffix in SEARCH_COUNTERS
    for prefix in ("quota", "usage")
)

COSMOS_EXPECTED = (
    "item_count",
    "throughput_ru",
    "autoscale_max_ru",
    "is_serverless",
    "partition_key_paths",
    "indexing_mode",
    "ttl_seconds",
    "last_request_charge_ru",
    "session_token",
    "total_request_units",
    "normalized_ru_pct",
    "server_side_latency_ms",
)

GREMLIN_EXPECTED = (
    "vertex_count",
    "edge_count",
    "label_histogram",
    "last_request_charge_ru",
    "throughput_ru",
    "graph_partition_key",
)

KUSTO_EXPECTED = (
    "cluster_state",
    "sku",
    "instance_count",
    "table_row_count",
    "table_extent_bytes",
    "hot_extent_bytes",
    "ingestion_failures_24h",
    "cache_utilisation_pct",
    "cpu_pct",
    "ingestion_latency_s",
)

FABRIC_EXPECTED = (
    "node_types",
    "edge_types",
    "schema_version",
    "last_query_status_code",
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def named(payload: dict) -> set[str]:
    """Every stat name the envelope accounts for, collected or partial."""
    return set(payload["stats"]) | {entry["stat"] for entry in payload["partial"]}


def assert_covers(envelope: str, expected: tuple[str, ...]) -> dict:
    """No spec stat may be silently absent, and the call must still be ok."""
    payload = json.loads(envelope)
    assert payload["ok"] is True
    assert payload["operation"] == "stats"
    missing = sorted(set(expected) - named(payload))
    assert not missing, f"stats omitted with no partial entry: {missing}"
    return payload


def partial_detail(payload: dict, stat: str) -> str:
    for entry in payload["partial"]:
        if entry["stat"] == stat:
            return entry["detail"]
    raise AssertionError(f"{stat} is not in partial: {payload['partial']}")


class FakeCredential:
    def get_token(self, scope: str):
        return types.SimpleNamespace(token="tok", expires_on=time.time() + 3600)


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_overrides()
    reset_gates()


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeIndexesClient:
    """The Search index-management plane, as far as stats are concerned."""

    def __init__(self, *, index_stats=None, service_stats=None, service_error=""):
        self.index_stats = index_stats
        self.service_stats = service_stats
        self.service_error = service_error
        self.calls: list[str] = []

    def get_index_statistics(self, name):
        self.calls.append(f"index:{name}")
        if self.index_stats is None:
            raise RuntimeError("index statistics unavailable")
        return self.index_stats

    def get_service_statistics(self):
        self.calls.append("service")
        if self.service_error:
            raise RuntimeError(self.service_error)
        return self.service_stats


def search_service_statistics(include_semantic: bool = True) -> dict:
    counters = {
        attribute: {"usage": index * 10, "quota": 1000 + index}
        for index, (attribute, _) in enumerate(SEARCH_COUNTERS)
    }
    if include_semantic:
        counters["semantic_query_counter"] = {"usage": 7, "quota": 1000}
    return {"counters": counters}


class FakeCosmosContainer:
    """An async ContainerProxy, only the parts the observe plane touches."""

    def __init__(self, *, items=(), properties=None, headers=None):
        self.items = list(items)
        self.properties = properties
        self.queries: list[str] = []
        self.client_connection = types.SimpleNamespace(
            last_response_headers=headers
        ) if headers is not None else types.SimpleNamespace()

    def query_items(self, query=None, parameters=None):
        self.queries.append(query)
        rows = self._rows_for(query)

        async def _iterate():
            for row in rows:
                yield row

        return _iterate()

    def _rows_for(self, query: str):
        if "COUNT(1)" in query:
            return [len(self.items)]
        return sorted(self.items, key=lambda row: str(row.get("id")))

    async def read(self):
        if self.properties is None:
            raise RuntimeError("container properties unavailable")
        return self.properties


def fake_gremlin_modules(responses, status_attributes=None):
    """Driver fakes keyed on the exact traversal the connector submits."""
    log = {"queries": [], "clients": 0}

    class _Result:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _Future:
        def __init__(self, value):
            self._value = value

        def all(self):
            return _Result(self._value)

    class _ResultSet(_Future):
        pass

    class _Client:
        def __init__(self, **kwargs):
            log["clients"] += 1

        def submit(self, query):
            log["queries"].append(query)
            if query not in responses:
                raise RuntimeError(f"unexpected traversal: {query}")
            result_set = _ResultSet(responses[query])
            if status_attributes is not None:
                result_set.status_attributes = status_attributes
            return result_set

        def close(self):
            pass

    return (
        types.SimpleNamespace(Client=_Client),
        types.SimpleNamespace(GraphSONSerializersV2d0=lambda: "serializer"),
        log,
    )


def install_gremlin(responses, status_attributes=None):
    client_mod, serializer_mod, log = fake_gremlin_modules(responses, status_attributes)
    override("gremlin_python.driver.client", client_mod)
    override("gremlin_python.driver.serializer", serializer_mod)
    return log


def gremlin_connector(responses, status_attributes=None):
    log = install_gremlin(responses, status_attributes)
    config = AzureDataConfig(
        gremlin_endpoint="wss://example/gremlin",
        gremlin_database="db",
        gremlin_graph="assets",
    )
    return GremlinConnector.from_config(config, lambda: FakeCredential()), log


def fake_kusto_module(responses):
    """Kusto fake keyed on the exact command text."""
    log = {"queries": []}

    class _Col:
        def __init__(self, name):
            self.column_name = name
            self.column_type = "string"

    class _Primary:
        def __init__(self, rows):
            self.rows = rows
            self.columns = [_Col(name) for name in (rows[0] if rows else {})]

        def __iter__(self):
            return iter(self.rows)

    class _Response:
        def __init__(self, rows):
            self.primary_results = [_Primary(rows)]

    class _Client:
        def __init__(self, kcsb):
            pass

        def execute(self, database, query):
            log["queries"].append(query)
            if query not in responses:
                raise RuntimeError(f"unexpected command: {query}")
            return _Response(responses[query])

    class _Kcsb:
        @staticmethod
        def with_azure_token_credential(uri, credential):
            return {"uri": uri}

    override(
        "azure.kusto.data",
        types.SimpleNamespace(KustoClient=_Client, KustoConnectionStringBuilder=_Kcsb),
    )
    return log


def kusto_connector(responses):
    log = fake_kusto_module(responses)
    config = AzureDataConfig(
        kql_query_uri="https://cluster.kusto.windows.net",
        kql_database="azdatalive",
    )
    return (
        KqlConnector.from_config(
            config, lambda: FakeCredential(), gate_name="observe-kusto"
        ),
        log,
    )


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def install_httpx(responses):
    log = {"gets": [], "posts": []}

    class _AsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            log["gets"].append(url)
            return responses.pop(0)

        async def post(self, url, json=None, headers=None):
            log["posts"].append(url)
            return responses.pop(0)

    override("httpx", types.SimpleNamespace(AsyncClient=_AsyncClient))
    return log


def install_monitor(*, values=None, raises=""):
    """A fake azure-mgmt-monitor. ``raises`` models a denied read."""
    log = {"calls": []}

    class _Point:
        def __init__(self, average):
            self.average = average

    class _Series:
        def __init__(self, values):
            self.data = [_Point(value) for value in values]

    class _Metric:
        def __init__(self, name, values):
            self.name = types.SimpleNamespace(value=name)
            self.timeseries = [_Series(values)]

    class _Response:
        def __init__(self, mapping):
            self.value = [_Metric(name, [value]) for name, value in mapping.items()]

    class _Metrics:
        def list(self, resource_id, **kwargs):
            log["calls"].append(kwargs)
            if raises:
                raise RuntimeError(raises)
            return _Response(values or {})

    class _Client:
        def __init__(self, credential, subscription_id):
            self.metrics = _Metrics()

    override(
        "azure.mgmt.monitor", types.SimpleNamespace(MonitorManagementClient=_Client)
    )
    return log


def metrics_reader() -> MetricsReader:
    return MetricsReader(
        credential_provider=lambda: FakeCredential(), subscription_id="sub"
    )


# ── The collector contract ───────────────────────────────────────────────────


async def test_a_raising_probe_lands_in_partial_and_the_call_survives():
    def boom():
        raise RuntimeError("counter offline")

    stats, partial = await collector(
        [(("alive",), lambda: 1), (("dead",), boom)]
    )
    assert stats == {"alive": 1}
    assert partial == [{"stat": "dead", "detail": "RuntimeError: counter offline"}]


async def test_a_raising_probe_still_produces_an_ok_envelope():
    stats, partial = await collector([(("dead",), _raise)])
    payload = json.loads(
        stats_envelope(
            service="search",
            target="azdata-assets",
            source=StatSource.DATA_PLANE,
            stats=stats,
            partial=partial,
        )
    )
    assert payload["ok"] is True
    assert payload["partial"][0]["stat"] == "dead"


def _raise():
    raise StatUnavailable("no value exists for this")


async def test_a_declared_name_the_probe_omitted_is_named_in_partial():
    stats, partial = await collector(
        [(("present", "absent"), lambda: {"present": 3})]
    )
    assert stats == {"present": 3}
    assert partial == [{"stat": "absent", "detail": "not reported by the service"}]


async def test_an_undeclared_extra_counter_is_kept():
    stats, _ = await collector([(("a", "b"), lambda: {"a": 1, "b": 2, "c": 3})])
    assert stats["c"] == 3


async def test_a_probe_detail_is_sanitised():
    def leak():
        raise RuntimeError("failed against https://acct.search.windows.net/x")

    _, partial = await collector([(("leaky",), leak)])
    assert "search.windows.net" not in partial[0]["detail"]
    assert "<redacted-url>" in partial[0]["detail"]


def test_the_stats_envelope_key_order_is_the_contract():
    payload = json.loads(
        stats_envelope(
            service="cosmos",
            target="hc/items",
            source="data-plane",
            stats={"item_count": 40},
            partial=[],
            collected_at="2026-08-30T12:00:00Z",
        )
    )
    assert list(payload) == [
        "ok",
        "operation",
        "service",
        "target",
        "collected_at",
        "source",
        "stats",
        "partial",
    ]
    assert payload["source"] == "data-plane"


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError):
        stats_envelope(
            service="cosmos", target="x", source="guessed", stats={}, partial=[]
        )


# ── Search ───────────────────────────────────────────────────────────────────


async def test_search_stats_name_every_spec_stat():
    client = FakeIndexesClient(
        index_stats={
            "document_count": 40,
            "storage_size": 8192,
            "vector_index_size": 2048,
        },
        service_stats=search_service_statistics(),
    )
    install_monitor(
        values={"SearchLatency": 12.5, "ThrottledSearchQueriesPercentage": 0.0}
    )
    stats = SearchStats(
        indexes_client=client,
        index_name="azdata-assets",
        metrics=metrics_reader(),
        resource_id="/subscriptions/sub/rg/srch",
    )
    payload = assert_covers(await stats.stats(), SEARCH_EXPECTED)
    assert payload["stats"]["document_count"] == 40
    assert payload["stats"]["storage_bytes"] == 8192
    assert payload["stats"]["search_latency_p50_ms"] == 12.5
    assert payload["partial"] == []


async def test_search_index_and_service_statistics_fail_independently():
    client = FakeIndexesClient(
        index_stats=None,  # this call raises
        service_stats=search_service_statistics(),
    )
    stats = SearchStats(indexes_client=client, index_name="azdata-assets")
    payload = assert_covers(await stats.stats(), SEARCH_EXPECTED)
    assert "index statistics unavailable" in partial_detail(payload, "document_count")
    assert payload["stats"]["quota_documents"] == 1000


async def test_search_reports_an_unreported_counter_rather_than_dropping_it():
    client = FakeIndexesClient(
        index_stats={"document_count": 1},
        service_stats=search_service_statistics(include_semantic=False),
    )
    stats = SearchStats(indexes_client=client, index_name="azdata-assets")
    payload = assert_covers(await stats.stats(), SEARCH_EXPECTED)
    assert partial_detail(payload, "semantic_query_usage")
    assert partial_detail(payload, "storage_bytes") == "not reported by the service"


# ── Cosmos ───────────────────────────────────────────────────────────────────


def cosmos_stats(**kwargs) -> CosmosStats:
    container = kwargs.pop(
        "container",
        FakeCosmosContainer(
            items=[{"id": "a"}, {"id": "b"}],
            properties={
                "partitionKey": {"paths": ["/site"]},
                "indexingPolicy": {"indexingMode": "consistent"},
                "defaultTtl": 3600,
            },
            headers={"x-ms-request-charge": "2.89", "x-ms-session-token": "0:1#42"},
        ),
    )
    kwargs.setdefault("database", "azdatalive")
    kwargs.setdefault("container_name", "assets")
    return CosmosStats(container=container, **kwargs)


class FakeCosmosMgmt:
    def __init__(self, *, throughput=400, autoscale=None, serverless=False):
        self.sql_resources = types.SimpleNamespace(
            get_sql_container_throughput=lambda *args: {
                "resource": (
                    {"throughput": throughput, "autoscaleSettings": {"maxThroughput": autoscale}}
                    if autoscale
                    else {"throughput": throughput}
                )
            }
        )
        self.database_accounts = types.SimpleNamespace(
            get=lambda *args: {
                "capabilities": [{"name": "EnableServerless"}] if serverless else []
            }
        )


async def test_cosmos_stats_name_every_spec_stat():
    install_monitor(
        values={
            "TotalRequestUnits": 91.0,
            "NormalizedRUConsumption": 4.0,
            "ServerSideLatency": 3.1,
        }
    )
    stats = cosmos_stats(
        mgmt_client=FakeCosmosMgmt(autoscale=4000, serverless=True),
        account_name="cosmos-azdata-nosql",
        resource_group="rg",
        metrics=metrics_reader(),
        resource_id="/subscriptions/sub/rg/cosmos",
    )
    payload = assert_covers(await stats.stats(), COSMOS_EXPECTED)
    assert payload["stats"]["item_count"] == 2
    assert payload["stats"]["partition_key_paths"] == ["/site"]
    assert payload["stats"]["last_request_charge_ru"] == 2.89
    assert payload["stats"]["is_serverless"] is True
    assert payload["target"] == "azdatalive/assets"


async def test_cosmos_absent_charge_header_is_partial_never_zero():
    container = FakeCosmosContainer(
        items=[{"id": "a"}],
        properties={"partitionKey": {"paths": ["/site"]}},
        headers={"x-ms-session-token": "0:1#42"},
    )
    payload = assert_covers(
        await cosmos_stats(container=container).stats(), COSMOS_EXPECTED
    )
    assert "last_request_charge_ru" not in payload["stats"]
    assert partial_detail(payload, "last_request_charge_ru")
    assert payload["stats"]["session_token"] == "0:1#42"


async def test_cosmos_without_a_management_client_keeps_the_data_plane():
    payload = assert_covers(await cosmos_stats().stats(), COSMOS_EXPECTED)
    assert payload["stats"]["item_count"] == 2
    for stat in ("throughput_ru", "autoscale_max_ru", "is_serverless"):
        assert "management client" in partial_detail(payload, stat)


# ── Gremlin ──────────────────────────────────────────────────────────────────

GREMLIN_RESPONSES = {
    "g.V().count()": [12],
    "g.E().count()": [20],
    "g.V().groupCount().by(label).limit(500)": [{"asset": 8, "site": 4}],
}


class FakeGremlinMgmt:
    def __init__(self):
        self.gremlin_resources = types.SimpleNamespace(
            get_gremlin_graph_throughput=lambda *args: {"resource": {"throughput": 400}},
            get_gremlin_graph=lambda *args: {
                "resource": {"partitionKey": {"paths": ["/site"]}}
            },
        )


async def test_gremlin_stats_name_every_spec_stat():
    connector, log = gremlin_connector(
        GREMLIN_RESPONSES, status_attributes={CHARGE_ATTRIBUTE: 5.25}
    )
    stats = GremlinStats(
        connector=connector,
        database="azdatalive",
        graph="assets",
        mgmt_client=FakeGremlinMgmt(),
        account_name="cosmos-azdata-gremlin",
        resource_group="rg",
    )
    payload = assert_covers(await stats.stats(), GREMLIN_EXPECTED)
    assert payload["stats"]["vertex_count"] == 12
    assert payload["stats"]["edge_count"] == 20
    assert payload["stats"]["label_histogram"] == {"asset": 8, "site": 4}
    assert payload["stats"]["last_request_charge_ru"] == 5.25
    assert payload["stats"]["graph_partition_key"] == "/site"
    # Through the read connector, so the guardrails saw every traversal: the
    # aggregates keep their shape and the histogram picks up the row cap.
    assert log["queries"][0] == "g.V().count()"
    assert log["queries"][-1].endswith(".limit(500)")


async def test_gremlin_absent_charge_attribute_is_partial():
    connector, _ = gremlin_connector(GREMLIN_RESPONSES)  # no status attributes
    stats = GremlinStats(connector=connector, database="db", graph="assets")
    payload = assert_covers(await stats.stats(), GREMLIN_EXPECTED)
    assert "last_request_charge_ru" not in payload["stats"]
    assert CHARGE_ATTRIBUTE in partial_detail(payload, "last_request_charge_ru")
    assert payload["stats"]["vertex_count"] == 12


async def test_gremlin_a_refused_count_does_not_take_the_others_down():
    responses = dict(GREMLIN_RESPONSES)
    responses.pop("g.E().count()")
    connector, _ = gremlin_connector(responses)
    stats = GremlinStats(connector=connector, database="db", graph="assets")
    payload = assert_covers(await stats.stats(), GREMLIN_EXPECTED)
    assert payload["stats"]["vertex_count"] == 12
    assert partial_detail(payload, "edge_count")


# ── Kusto ────────────────────────────────────────────────────────────────────

KUSTO_RESPONSES = {
    ".show table Assets details": [
        {"TotalRowCount": 40, "TotalExtentSize": 4096, "HotExtentSize": 1024}
    ],
    ".show ingestion failures | where FailedOn > ago(24h) | count": [{"Count": 0}],
}


class FakeKustoMgmt:
    def __init__(self):
        self.clusters = types.SimpleNamespace(
            get=lambda *args: types.SimpleNamespace(
                state="Running",
                sku=types.SimpleNamespace(name="Standard_E2a_v4", capacity=1),
            )
        )


async def test_kusto_stats_name_every_spec_stat():
    connector, log = kusto_connector(KUSTO_RESPONSES)
    install_monitor(
        values={"CacheUtilization": 88.0, "CPU": 12.0, "StageLatency": 4.4}
    )
    stats = KustoStats(
        connector=connector,
        table="Assets",
        mgmt_client=FakeKustoMgmt(),
        cluster_name="adx-azdatalive",
        resource_group="rg",
        metrics=metrics_reader(),
        resource_id="/subscriptions/sub/rg/adx",
    )
    payload = assert_covers(await stats.stats(), KUSTO_EXPECTED)
    assert payload["stats"]["table_row_count"] == 40
    assert payload["stats"]["ingestion_failures_24h"] == 0
    assert payload["stats"]["cluster_state"] == "Running"
    assert payload["stats"]["cpu_pct"] == 12.0
    # The control commands reach the service verbatim: a '| take' appended to
    # '.show table ... details' would change what it returns.
    assert log["queries"][0] == ".show table Assets details"


async def test_kusto_refuses_to_interpolate_a_non_identifier_table():
    connector, log = kusto_connector(KUSTO_RESPONSES)
    stats = KustoStats(connector=connector, table="Assets; .drop table Assets")
    payload = assert_covers(await stats.stats(), KUSTO_EXPECTED)
    assert "not a plain Kusto identifier" in partial_detail(payload, "table_row_count")
    assert not any("drop" in query for query in log["queries"])


# ── Fabric GraphModel ────────────────────────────────────────────────────────


async def test_fabric_graph_stats_name_every_spec_stat():
    install_httpx(
        [
            FakeResponse(
                200,
                {
                    "nodeTypes": ["Asset", "Site"],
                    "edgeTypes": ["LOCATED_AT"],
                    "schemaVersion": "3",
                },
            )
        ]
    )
    stats = GraphStats(
        connector=types.SimpleNamespace(last_query_status_code="00000"),
        metadata_url_provider=lambda: "https://api.example/v1/graphmodels/gm",
        token_provider=_token,
    )
    payload = assert_covers(await stats.stats(), FABRIC_EXPECTED)
    assert payload["stats"]["node_types"] == ["Asset", "Site"]
    assert payload["stats"]["last_query_status_code"] == "00000"


async def test_fabric_graph_status_code_comes_from_a_real_query():
    reset_gates()
    install_httpx(
        [
            FakeResponse(
                200,
                {"status": {"code": "00000"}, "result": {"columns": [], "data": []}},
            ),
            FakeResponse(200, {"nodeTypes": [], "edgeTypes": [], "schemaVersion": "1"}),
        ]
    )
    connector = GraphConnector(
        resolve_url=lambda: "https://api.example/v1/executeQuery",
        token_provider=_token,
        gate_provider=_gate,
        metadata_url_provider=lambda: "https://api.example/v1/graphmodels/gm",
    )
    assert connector.last_query_status_code is None
    await connector.execute("MATCH (n) RETURN n")
    assert connector.last_query_status_code == "00000"

    stats = GraphStats(
        connector=connector,
        metadata_url_provider=lambda: "https://api.example/v1/graphmodels/gm",
        token_provider=_token,
    )
    payload = assert_covers(await stats.stats(), FABRIC_EXPECTED)
    assert payload["stats"]["last_query_status_code"] == "00000"


async def test_fabric_graph_reports_an_unrun_query_rather_than_a_success_code():
    install_httpx([FakeResponse(500, {})])
    stats = GraphStats(
        connector=GraphConnector(
            resolve_url=lambda: "",
            token_provider=_token,
            gate_provider=_gate,
        ),
        metadata_url_provider=lambda: "https://api.example/v1/graphmodels/gm",
        token_provider=_token,
    )
    payload = assert_covers(await stats.stats(), FABRIC_EXPECTED)
    assert "no GQL query has run" in partial_detail(payload, "last_query_status_code")
    assert "HTTP 500" in partial_detail(payload, "node_types")


async def _token() -> str:
    return "tok"


async def _gate():
    return get_gate("observe-fabric", max_concurrent=2)


# ── Azure Monitor ────────────────────────────────────────────────────────────


async def test_metrics_reader_with_no_sdk_never_raises():
    override_missing("azure.mgmt.monitor")
    read = await metrics_reader().read("/subscriptions/sub/x", ["SearchLatency"])
    assert isinstance(read, MetricRead)
    assert read.values == {}
    assert "azure-mgmt-monitor" in read.detail


async def test_every_data_plane_stat_returns_with_the_monitor_sdk_absent():
    override_missing("azure.mgmt.monitor")
    client = FakeIndexesClient(
        index_stats={"document_count": 40, "storage_size": 1, "vector_index_size": 2},
        service_stats=search_service_statistics(),
    )
    stats = SearchStats(
        indexes_client=client,
        index_name="azdata-assets",
        metrics=metrics_reader(),
        resource_id="/subscriptions/sub/rg/srch",
    )
    payload = assert_covers(await stats.stats(), SEARCH_EXPECTED)
    assert payload["stats"]["document_count"] == 40
    assert payload["stats"]["usage_documents"] == 0
    assert "azure-mgmt-monitor" in partial_detail(payload, "search_latency_p50_ms")
    assert "azure-mgmt-monitor" in partial_detail(payload, "throttled_query_pct")


async def test_a_denied_monitor_read_degrades_into_partial():
    install_monitor(raises="(AuthorizationFailed) Monitoring Reader is required")
    client = FakeIndexesClient(
        index_stats={"document_count": 40, "storage_size": 1, "vector_index_size": 2},
        service_stats=search_service_statistics(),
    )
    stats = SearchStats(
        indexes_client=client,
        index_name="azdata-assets",
        metrics=metrics_reader(),
        resource_id="/subscriptions/sub/rg/srch",
    )
    payload = assert_covers(await stats.stats(), SEARCH_EXPECTED)
    assert payload["ok"] is True
    assert payload["stats"]["document_count"] == 40
    assert "AuthorizationFailed" in partial_detail(payload, "throttled_query_pct")


async def test_no_monitor_reader_wired_is_a_partial_not_a_failure():
    with pytest.raises(MetricsUnavailable):
        await read_stats(None, "/x", {"CPU": "cpu_pct"})


async def test_a_metric_monitor_did_not_report_is_named():
    install_monitor(values={"SearchLatency": 1.0})
    client = FakeIndexesClient(
        index_stats={"document_count": 1, "storage_size": 1, "vector_index_size": 1},
        service_stats=search_service_statistics(),
    )
    stats = SearchStats(
        indexes_client=client,
        index_name="azdata-assets",
        metrics=metrics_reader(),
        resource_id="/subscriptions/sub/rg/srch",
    )
    payload = assert_covers(await stats.stats(), SEARCH_EXPECTED)
    assert payload["stats"]["search_latency_p50_ms"] == 1.0
    assert partial_detail(payload, "throttled_query_pct") == (
        "not reported by the service"
    )


async def test_an_unconfigured_subscription_is_not_a_client_that_401s():
    reader = MetricsReader(credential_provider=lambda: FakeCredential())
    read = await reader.read("/subscriptions/sub/x", ["CPU"])
    assert read.detail == "subscription id not configured"


async def test_from_config_wires_the_endpoint_and_the_monitor_reader():
    override_missing("azure.search.documents.indexes")
    override_missing("azure.mgmt.monitor")
    config = AzureDataConfig(
        search_endpoint="https://srch.example.net", subscription_id="sub"
    )
    stats = SearchStats.from_config(
        config, lambda: FakeCredential(), index_name="azdata-assets"
    )
    payload = json.loads(await stats.stats())
    # No SDK installed, so both planes degrade — and both name what is missing
    # rather than answering with a zero.
    assert payload["ok"] is True
    assert "azure-search-documents" in partial_detail(payload, "document_count")
    assert "no resource id" in partial_detail(payload, "search_latency_p50_ms")


# ── Journal ──────────────────────────────────────────────────────────────────


def record(journal: OperationJournal, index: int) -> JournalRecord | None:
    return journal.record(
        operation="upload",
        service="search",
        target="azdata-assets",
        outcome="ok",
        elapsed_ms=float(index),
    )


def test_the_journal_is_off_by_default_and_records_nothing():
    journal = OperationJournal(capacity=4)
    seen: list[JournalRecord] = []
    journal.subscribe(seen.append)

    assert journal.enabled is False
    assert record(journal, 1) is None
    assert journal.records() == ()
    assert seen == []


def test_the_journal_evicts_the_oldest_and_keeps_the_order():
    journal = OperationJournal(capacity=3)
    journal.enable()
    for index in range(5):
        record(journal, index)

    assert journal.capacity == 3
    assert [r.elapsed_ms for r in journal.records()] == [2.0, 3.0, 4.0]


def test_the_journal_reports_an_absent_charge_as_none_not_zero():
    journal = OperationJournal()
    journal.enable()
    entry = journal.record(
        operation="verify",
        service="kusto",
        target="Assets",
        outcome="ok",
        elapsed_ms=1.0,
    )
    assert entry.request_charge is None
    assert entry.verified is None
    assert entry.as_dict()["request_charge"] is None


def test_a_subscriber_that_raises_does_not_fail_the_call():
    journal = OperationJournal()
    journal.enable()
    delivered: list[JournalRecord] = []

    def _explode(entry):
        raise RuntimeError("telemetry sink is down")

    journal.subscribe(_explode)
    unsubscribe = journal.subscribe(delivered.append)

    assert record(journal, 1) is not None
    assert len(delivered) == 1

    unsubscribe()
    record(journal, 2)
    assert len(delivered) == 1
    assert len(journal.records()) == 2
