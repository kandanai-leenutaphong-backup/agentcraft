"""test_discover — the discover plane, with no SDKs, no network, no cloud.

Run: ``python3 -m pytest tests/unit/test_discover.py``.

Every Azure SDK is substituted through ``azdata.core.optional.override``,
the same seam the rest of the suite uses. What is proven here is the
contract in CONTRACT.md §11, one test per invariant:

* ``discover`` never raises — every failure is a status;
* ``ok`` means non-empty; zero items is ``empty``, never ``ok``;
* ``truncated`` is set from the N+1 probe, on either side of the boundary;
* nodes are ordered ``(kind, name)`` and two reads differ only in
  ``collected_at``;
* a returned ``path`` is exactly the scope path that expands it;
* no URL survives into ``detail`` or into ``attributes``;
* construction performs no I/O at all, not even building a credential.

The fakes assert on what the discoverer *sent* — the ARM api_version, the
two Search methods, the single Kusto command — so this is a contract test
rather than a smoke test.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import socket
import sys
import time
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.arm.discover import ArmDiscoverer  # noqa: E402
from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.core.discover import (  # noqa: E402
    DISCOVERY_STATUSES,
    Discoverer,
    DiscovererRegistry,
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryScope,
    bounded_discovery,
    build_discovery_registry,
    classify_discovery_failure,
    normalize_attributes,
)
from azdata.core.optional import (  # noqa: E402
    MissingDependency,
    override,
    override_missing,
)
from azdata.cosmos.discover import CosmosDiscoverer  # noqa: E402
from azdata.gremlin.discover import GremlinDiscoverer  # noqa: E402
from azdata.kusto.discover import (  # noqa: E402
    ALLOWED_COMMANDS,
    KustoDiscoverer,
    cluster_name_from_uri,
)
from azdata.search.discover import MAX_FIELD_DEPTH, SearchDiscoverer  # noqa: E402

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

CONFIG = AzureDataConfig(
    subscription_id="sub-1",
    resource_group="rg-x",
    search_endpoint="https://srch.search.windows.net",
    cosmos_account_name="cosmos-acct",
    gremlin_account_name="gremlin-acct",
    kql_query_uri="https://adx-azdatalive.eastus.kusto.windows.net",
)


class ExplodingCredential:
    """Building one is the failure. Construction must never reach here."""

    def __init__(self) -> None:  # pragma: no cover - the assertion is the point
        raise AssertionError("credential built during construction")


def credential_calls() -> tuple[list[int], object]:
    """A provider that records every call, so laziness is observable."""
    calls: list[int] = []

    def provider() -> object:
        calls.append(1)
        return object()

    return calls, provider


def provider() -> object:
    return object()


# ── SDK fakes ────────────────────────────────────────────────────────────────


class HttpResponseError(Exception):
    """Named as the SDK's, because the mapper matches on shape and name."""

    def __init__(self, message: str = "", status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ClientAuthenticationError(Exception):
    pass


class ServiceRequestError(Exception):
    pass


class ServiceRequestTimeoutError(ServiceRequestError):
    pass


class ResourceNotFoundError(HttpResponseError):
    def __init__(self, message: str = "absent") -> None:
        super().__init__(message, status_code=404)


AZURE_CORE = types.SimpleNamespace(
    HttpResponseError=HttpResponseError,
    ClientAuthenticationError=ClientAuthenticationError,
    ServiceRequestError=ServiceRequestError,
    ServiceRequestTimeoutError=ServiceRequestTimeoutError,
    ResourceNotFoundError=ResourceNotFoundError,
)


class FakeArmResources:
    def __init__(self, items=(), error: BaseException | None = None) -> None:
        self.items = list(items)
        self.error = error
        self.calls: list[tuple] = []

    def list_by_resource_group(self, resource_group, **kwargs):
        self.calls.append((resource_group, kwargs))
        if self.error is not None:
            raise self.error
        return iter(self.items)


def arm_module(resources: FakeArmResources, built: list | None = None):
    class ResourceManagementClient:
        def __init__(self, credential, subscription_id):
            if built is not None:
                built.append((credential, subscription_id))
            self.resources = resources

    return types.SimpleNamespace(ResourceManagementClient=ResourceManagementClient)


def arm_resource(name, **overrides):
    fields = {
        "id": f"/subscriptions/sub-1/resourceGroups/rg-x/providers/x/{name}",
        "name": name,
        "type": "Microsoft.Search/searchServices",
        "location": "eastus",
        "kind": None,
        "sku": types.SimpleNamespace(name="standard"),
        "provisioning_state": "Succeeded",
        "tags": {"secret-ish": "operator free text"},
    }
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


class FakeSearchIndexClient:
    """Exactly two reachable methods. Anything else is a test failure.

    The claim "this cannot write" is only worth making if it is checkable,
    so every other attribute raises rather than returning a mock.
    """

    def __init__(self, *, index_names=(), index=None, error=None, log=None) -> None:
        self._index_names = list(index_names)
        self._index = index
        self._error = error
        self.log = log if log is not None else []

    def list_index_names(self):
        self.log.append(("list_index_names", ()))
        if self._error is not None:
            raise self._error
        return iter(self._index_names)

    def get_index(self, name):
        self.log.append(("get_index", (name,)))
        if self._error is not None:
            raise self._error
        return self._index

    def __getattr__(self, item):
        raise AssertionError(f"search discovery reached {item!r}")


def search_module(client: FakeSearchIndexClient):
    def factory(*, endpoint, credential):
        client.endpoint = endpoint
        return client

    return types.SimpleNamespace(SearchIndexClient=factory)


def search_field(name, **overrides):
    fields = {
        "name": name,
        "type": "Edm.String",
        "key": False,
        "searchable": True,
        "filterable": False,
        "sortable": False,
        "facetable": False,
        "hidden": False,
        "analyzer_name": None,
        "vector_search_dimensions": None,
        "fields": (),
    }
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


class FakeCosmosResources:
    def __init__(self, databases=(), containers=(), error=None) -> None:
        self.databases = list(databases)
        self.containers = list(containers)
        self.error = error
        self.calls: list[tuple] = []

    def _answer(self, name, args, items):
        self.calls.append((name, args))
        if self.error is not None:
            raise self.error
        return iter(items)

    def list_sql_databases(self, rg, account):
        return self._answer("list_sql_databases", (rg, account), self.databases)

    def list_sql_containers(self, rg, account, database):
        return self._answer(
            "list_sql_containers", (rg, account, database), self.containers
        )

    def list_gremlin_databases(self, rg, account):
        return self._answer("list_gremlin_databases", (rg, account), self.databases)

    def list_gremlin_graphs(self, rg, account, database):
        return self._answer(
            "list_gremlin_graphs", (rg, account, database), self.containers
        )


def cosmos_module(resources: FakeCosmosResources):
    class CosmosDBManagementClient:
        def __init__(self, credential, subscription_id):
            self.sql_resources = resources
            self.gremlin_resources = resources

    return types.SimpleNamespace(CosmosDBManagementClient=CosmosDBManagementClient)


class FakeKustoDatabases:
    def __init__(self, items=(), error=None) -> None:
        self.items = list(items)
        self.error = error
        self.calls: list[tuple] = []

    def list_by_cluster(self, rg, cluster):
        self.calls.append((rg, cluster))
        if self.error is not None:
            raise self.error
        return iter(self.items)


def kusto_mgmt_module(databases: FakeKustoDatabases):
    class KustoManagementClient:
        def __init__(self, credential, subscription_id):
            self.databases = databases

    return types.SimpleNamespace(KustoManagementClient=KustoManagementClient)


def kusto_response(rows):
    columns = [
        types.SimpleNamespace(column_name=name, column_type="string")
        for name in ("TableName", "DatabaseName", "Folder", "DocString")
    ]

    class Primary:
        def __init__(self) -> None:
            self.columns = columns

        def __iter__(self):
            return iter(rows)

    return types.SimpleNamespace(primary_results=[Primary()])


class FakeKustoData:
    """The data-plane module, recording every command it is ever asked for."""

    def __init__(self, rows=(), error=None) -> None:
        self.commands: list[tuple[str, str]] = []
        self.rows = list(rows)
        self.error = error
        module_self = self

        class KustoConnectionStringBuilder:
            @staticmethod
            def with_azure_token_credential(uri, credential):
                return types.SimpleNamespace(uri=uri)

        class KustoClient:
            def __init__(self, kcsb):
                self.kcsb = kcsb

            def execute_mgmt(self, database, command):
                module_self.commands.append((database, command))
                if module_self.error is not None:
                    raise module_self.error
                return kusto_response(module_self.rows)

            def execute(self, *args, **kwargs):  # pragma: no cover
                raise AssertionError("kusto discovery must not run a query")

        self.module = types.SimpleNamespace(
            KustoConnectionStringBuilder=KustoConnectionStringBuilder,
            KustoClient=KustoClient,
        )


def kusto_row(name, folder="", doc=""):
    return {
        "TableName": name,
        "DatabaseName": "db",
        "Folder": folder,
        "DocString": doc,
    }


# ── Registry and construction ────────────────────────────────────────────────


async def test_registry_registers_all_five_even_when_unconfigured():
    registry = build_discovery_registry(AzureDataConfig(), provider)
    assert registry.services() == ("arm", "search", "cosmos", "gremlin", "kusto")
    for service, level in (
        ("arm", "resource_group"),
        ("search", "service"),
        ("cosmos", "account"),
        ("gremlin", "account"),
        ("kusto", "cluster"),
    ):
        discoverer = registry.get(service)
        assert isinstance(discoverer, Discoverer)
        result = await discoverer.discover(level, DiscoveryScope())
        assert result.status == "unconfigured", service
        assert result.nodes == ()
        assert result.detail


def test_registry_get_unknown_service_is_none():
    assert build_discovery_registry(CONFIG, provider).get("nope") is None


def test_construction_performs_no_io():
    calls, recording = credential_calls()
    registry = build_discovery_registry(CONFIG, recording)
    assert calls == []
    # No SDK override is installed and nothing raised MissingDependency,
    # which is only true if no client was built either.
    assert len(registry.services()) == 5
    ArmDiscoverer(credential_provider=ExplodingCredential)


def test_default_credential_provider_is_not_invoked_at_build():
    # No credential_provider passed: the registry derives one from config
    # and must not call it.
    registry = build_discovery_registry(CONFIG)
    assert registry.services()[0] == "arm"


def test_child_level_matches_declared_levels():
    expected = {
        ArmDiscoverer(credential_provider=provider): {"resource_group": None},
        SearchDiscoverer(credential_provider=provider): {
            "service": "index",
            "index": None,
        },
        CosmosDiscoverer(credential_provider=provider): {
            "account": "database",
            "database": None,
        },
        GremlinDiscoverer(credential_provider=provider): {
            "account": "database",
            "database": None,
        },
        KustoDiscoverer(credential_provider=provider): {
            "cluster": "database",
            "database": None,
        },
    }
    for discoverer, mapping in expected.items():
        assert set(discoverer.levels) == set(mapping)
        for level, child in mapping.items():
            assert discoverer.child_level(level) == child
            assert child is None or child in discoverer.levels


# ── ARM ──────────────────────────────────────────────────────────────────────


def arm_discoverer(resources, built=None, **kwargs):
    override("azure.mgmt.resource.resources", arm_module(resources, built))
    return ArmDiscoverer.from_config(CONFIG, provider, **kwargs)


async def test_arm_lists_resources_ordered_and_normalised():
    resources = FakeArmResources(
        [arm_resource("zeta"), arm_resource("alpha"), arm_resource("mid")]
    )
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope()
    )

    assert result.status == "ok"
    assert result.detail == ""
    assert result.truncated is False
    assert ISO_Z.match(result.collected_at)
    assert [node.name for node in result.nodes] == ["alpha", "mid", "zeta"]
    assert {node.kind for node in result.nodes} == {"arm_resource"}
    assert all(node.has_children is False for node in result.nodes)
    assert result.nodes[0].path == ("alpha",)
    assert set(result.nodes[0].attributes) == {
        "id",
        "type",
        "location",
        "kind",
        "sku",
        "provisioning_state",
    }
    assert result.nodes[0].attributes["sku"] == "standard"
    assert resources.calls == [("rg-x", {})]


async def test_arm_never_exposes_tags():
    resources = FakeArmResources([arm_resource("one")])
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope()
    )
    assert "tags" not in result.nodes[0].attributes


async def test_arm_missing_resource_group_is_named_not_raised():
    resources = FakeArmResources(error=ResourceNotFoundError())
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope()
    )
    assert result.status == "unavailable"
    assert result.detail == "resource group rg-x not found"


async def test_arm_scope_overrides_config_coordinates():
    resources = FakeArmResources([arm_resource("one")])
    scope = DiscoveryScope(subscription_id="sub-2", resource_group="rg-other")
    result = await arm_discoverer(resources).discover("resource_group", scope)
    assert result.status == "ok"
    assert resources.calls[0][0] == "rg-other"


async def test_arm_unknown_level_is_unavailable():
    resources = FakeArmResources([arm_resource("one")])
    result = await arm_discoverer(resources).discover("resource", DiscoveryScope())
    assert result.status == "unavailable"
    assert resources.calls == []


async def test_arm_attributes_carry_no_url():
    resources = FakeArmResources(
        [arm_resource("one", kind="see https://srch.search.windows.net/admin")]
    )
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope()
    )
    assert "https://" not in str(result.nodes[0].attributes["kind"])
    assert "<redacted-url>" in str(result.nodes[0].attributes["kind"])


# ── Bounds: truncation, empty, ordering, determinism ─────────────────────────


@pytest.mark.parametrize(
    ("available", "expected_truncated", "expected_count"),
    [(3, False, 3), (4, True, 3)],
)
async def test_truncation_on_both_sides_of_the_boundary(
    available, expected_truncated, expected_count
):
    resources = FakeArmResources(
        [arm_resource(f"r{index:02d}") for index in range(available)]
    )
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope(), bounds=DiscoveryBounds(max_items=3)
    )
    assert result.status == "ok"
    assert result.truncated is expected_truncated
    assert len(result.nodes) == expected_count


async def test_zero_items_is_empty_not_ok():
    result = await arm_discoverer(FakeArmResources([])).discover(
        "resource_group", DiscoveryScope()
    )
    assert result.status == "empty"
    assert result.nodes == ()
    assert result.detail == ""
    assert result.truncated is False


async def test_two_reads_differ_only_in_collected_at():
    resources = FakeArmResources(
        [arm_resource("b"), arm_resource("a"), arm_resource("c")]
    )
    discoverer = arm_discoverer(resources)
    first = await discoverer.discover("resource_group", DiscoveryScope())
    resources.items.reverse()
    second = await discoverer.discover("resource_group", DiscoveryScope())
    blank = {"collected_at": ""}
    assert dataclasses.replace(first, **blank) == dataclasses.replace(second, **blank)


def test_bounds_are_clamped_not_rejected():
    assert DiscoveryBounds(max_items=0).max_items == 1
    assert DiscoveryBounds(max_items=-5).max_items == 1
    assert DiscoveryBounds(timeout_secs=0).timeout_secs > 0
    assert DiscoveryBounds(timeout_secs=-1).timeout_secs > 0
    assert DiscoveryBounds().max_items == 500
    assert DiscoveryBounds().timeout_secs == 15.0


# ── Search ───────────────────────────────────────────────────────────────────


def search_discoverer(client):
    override("azure.search.documents.indexes", search_module(client))
    return SearchDiscoverer.from_config(CONFIG, provider)


async def test_search_lists_index_names():
    client = FakeSearchIndexClient(index_names=["azdata-assets", "abandoned"])
    result = await search_discoverer(client).discover("service", DiscoveryScope())
    assert result.status == "ok"
    assert [node.name for node in result.nodes] == ["abandoned", "azdata-assets"]
    assert all(node.has_children for node in result.nodes)
    assert result.nodes[0].path == ("abandoned",)
    assert client.log == [("list_index_names", ())]


async def test_search_flattens_fields_and_caps_depth():
    deep = search_field(
        "a",
        type="Edm.ComplexType",
        fields=[
            search_field(
                "b",
                type="Edm.ComplexType",
                fields=[
                    search_field(
                        "c", type="Edm.ComplexType", fields=[search_field("d")]
                    )
                ],
            )
        ],
    )
    index = types.SimpleNamespace(
        name="azdata-assets",
        fields=[
            search_field("id", key=True),
            deep,
            search_field(
                "vector", type="Collection(Edm.Single)", vector_search_dimensions=1536
            ),
        ],
    )
    client = FakeSearchIndexClient(index=index)
    result = await search_discoverer(client).discover(
        "index", DiscoveryScope(path=("azdata-assets",))
    )

    names = [node.name for node in result.nodes]
    assert names == ["a", "a/b", "a/b/c", "id", "vector"]
    assert max(name.count("/") for name in names) == MAX_FIELD_DEPTH - 1
    assert client.log == [("get_index", ("azdata-assets",))]
    by_name = {node.name: node for node in result.nodes}
    assert by_name["id"].attributes["key"] is True
    assert by_name["id"].attributes["retrievable"] is True
    assert by_name["vector"].attributes["vector_dimensions"] == 1536
    assert by_name["a/b"].path == ("azdata-assets", "a/b")
    assert all(node.has_children is False for node in result.nodes)


async def test_search_index_level_without_a_name_is_unconfigured():
    client = FakeSearchIndexClient(index_names=[])
    result = await search_discoverer(client).discover("index", DiscoveryScope())
    assert result.status == "unconfigured"
    assert client.log == []


async def test_search_path_round_trips_into_the_child_level():
    client = FakeSearchIndexClient(
        index_names=["azdata-assets"],
        index=types.SimpleNamespace(name="azdata-assets", fields=[search_field("id")]),
    )
    discoverer = search_discoverer(client)
    parent = await discoverer.discover("service", DiscoveryScope())
    child_scope = DiscoveryScope(path=parent.nodes[0].path)
    child = await discoverer.discover(
        discoverer.child_level("service"), child_scope
    )
    assert child.status == "ok"
    assert client.log[-1] == ("get_index", ("azdata-assets",))


async def test_search_uses_only_list_and_get():
    client = FakeSearchIndexClient(
        index_names=["azdata-assets"],
        index=types.SimpleNamespace(name="azdata-assets", fields=[search_field("id")]),
    )
    discoverer = search_discoverer(client)
    await discoverer.discover("service", DiscoveryScope())
    await discoverer.discover("index", DiscoveryScope(path=("azdata-assets",)))
    assert {call for call, _ in client.log} == {"list_index_names", "get_index"}


# ── Cosmos and Gremlin: management plane only ────────────────────────────────


def cosmos_resources_fake(databases=(), containers=(), error=None):
    resources = FakeCosmosResources(databases, containers, error)
    override("azure.mgmt.cosmosdb", cosmos_module(resources))
    # If either discoverer ever reached the data plane, the load would
    # raise MissingDependency and the status would not be ok.
    override_missing("azure.cosmos.aio")
    override_missing("gremlin_python.driver.client")
    return resources


def mgmt_database(name):
    """The v10 shape: a Mapping whose values sit under ``properties``."""
    return {
        "id": f"/subscriptions/sub-1/.../{name}",
        "name": name,
        "type": "Microsoft.DocumentDB/databaseAccounts/sqlDatabases",
        "properties": {"resource": {"id": name}},
    }


def mgmt_container(name):
    return {
        "id": f"/subscriptions/sub-1/.../{name}",
        "name": name,
        "properties": {
            "resource": {
                "id": name,
                "partitionKey": {"paths": ["/tenant", "/id"], "kind": "MultiHash"},
                "defaultTtl": 3600,
                "analyticalStorageTtl": -1,
                "indexingPolicy": {"indexingMode": "consistent"},
            }
        },
    }


async def test_cosmos_lists_databases_then_containers_from_arm():
    resources = cosmos_resources_fake(
        databases=[mgmt_database("orders"), mgmt_database("assets")],
        containers=[mgmt_container("events")],
    )
    discoverer = CosmosDiscoverer.from_config(CONFIG, provider)

    accounts = await discoverer.discover("account", DiscoveryScope())
    assert accounts.status == "ok"
    assert [node.name for node in accounts.nodes] == ["assets", "orders"]
    assert all(node.kind == "cosmos_database" for node in accounts.nodes)
    assert all(node.has_children for node in accounts.nodes)

    child = await discoverer.discover(
        discoverer.child_level("account"),
        DiscoveryScope(path=accounts.nodes[0].path),
    )
    assert child.status == "ok"
    node = child.nodes[0]
    assert node.kind == "cosmos_container"
    assert node.has_children is False
    assert node.path == ("assets", "events")
    assert node.attributes == {
        "partition_key_paths": "/tenant,/id",
        "partition_key_kind": "MultiHash",
        "default_ttl": 3600,
        "indexing_mode": "consistent",
        "analytical_ttl": -1,
    }
    assert [call for call, _ in resources.calls] == [
        "list_sql_databases",
        "list_sql_containers",
    ]
    assert resources.calls[1][1] == ("rg-x", "cosmos-acct", "assets")


async def test_cosmos_container_level_without_a_database_is_unconfigured():
    resources = cosmos_resources_fake(containers=[mgmt_container("events")])
    result = await CosmosDiscoverer.from_config(CONFIG, provider).discover(
        "database", DiscoveryScope()
    )
    assert result.status == "unconfigured"
    assert resources.calls == []


async def test_cosmos_unconfigured_account_names_the_field():
    cosmos_resources_fake()
    bare = AzureDataConfig(subscription_id="sub-1", resource_group="rg-x")
    result = await CosmosDiscoverer.from_config(bare, provider).discover(
        "account", DiscoveryScope()
    )
    assert result.status == "unconfigured"
    assert "cosmos_account_name" in result.detail


async def test_gremlin_lists_databases_then_graphs_without_a_websocket():
    resources = cosmos_resources_fake(
        databases=[mgmt_database("graphdb")],
        containers=[mgmt_container("people")],
    )
    discoverer = GremlinDiscoverer.from_config(CONFIG, provider)

    accounts = await discoverer.discover("account", DiscoveryScope())
    assert accounts.status == "ok"
    assert accounts.nodes[0].kind == "gremlin_database"

    graphs = await discoverer.discover(
        "database", DiscoveryScope(path=accounts.nodes[0].path)
    )
    assert graphs.status == "ok"
    node = graphs.nodes[0]
    assert node.kind == "gremlin_graph"
    assert node.attributes == {
        "partition_key_paths": "/tenant,/id",
        "default_ttl": 3600,
        "indexing_mode": "consistent",
    }
    assert [call for call, _ in resources.calls] == [
        "list_gremlin_databases",
        "list_gremlin_graphs",
    ]
    assert resources.calls[1][1] == ("rg-x", "gremlin-acct", "graphdb")


# ── Kusto: ARM databases, one allowlisted command for tables ─────────────────


def kusto_discoverer(databases=None, data=None):
    override("azure.mgmt.kusto", kusto_mgmt_module(databases or FakeKustoDatabases()))
    override("azure.kusto.data", (data or FakeKustoData()).module)
    return KustoDiscoverer.from_config(CONFIG, provider)


def test_cluster_name_comes_from_the_query_uri_host():
    assert cluster_name_from_uri(CONFIG.kql_query_uri) == "adx-azdatalive"
    assert cluster_name_from_uri("") == ""
    assert cluster_name_from_uri("not a uri") == ""


async def test_kusto_lists_databases_from_arm():
    databases = FakeKustoDatabases(
        [
            types.SimpleNamespace(
                name="adx-azdatalive/telemetry",
                soft_delete_period="P31D",
                hot_cache_period="P7D",
            )
        ]
    )
    result = await kusto_discoverer(databases).discover("cluster", DiscoveryScope())
    assert result.status == "ok"
    node = result.nodes[0]
    assert node.kind == "kusto_database"
    assert node.name == "telemetry"
    assert node.path == ("telemetry",)
    assert node.attributes == {
        "soft_delete_period": "P31D",
        "hot_cache_period": "P7D",
    }
    assert databases.calls == [("rg-x", "adx-azdatalive")]


async def test_kusto_lists_tables_with_exactly_one_command():
    data = FakeKustoData([kusto_row("Signals", folder="raw", doc="events")])
    result = await kusto_discoverer(data=data).discover(
        "database", DiscoveryScope(path=("telemetry",))
    )
    assert result.status == "ok"
    assert result.nodes[0].kind == "kusto_table"
    assert result.nodes[0].name == "Signals"
    assert result.nodes[0].attributes == {"folder": "raw", "doc_string": "events"}
    assert data.commands == [("telemetry", ".show tables")]
    assert ALLOWED_COMMANDS == (".show tables",)


@pytest.mark.parametrize(
    ("level", "path"),
    [
        (".drop table Signals", ("telemetry",)),
        ("database; .drop table Signals", ("telemetry",)),
        ("cluster", ("telemetry'; .drop table Signals //",)),
        ("", ()),
    ],
)
async def test_kusto_hostile_input_cannot_emit_another_command(level, path):
    data = FakeKustoData([kusto_row("Signals")])
    databases = FakeKustoDatabases([])
    result = await kusto_discoverer(databases, data).discover(
        level, DiscoveryScope(path=path)
    )
    assert result.status in DISCOVERY_STATUSES
    emitted = {command for _, command in data.commands}
    assert emitted <= set(ALLOWED_COMMANDS)


async def test_kusto_database_level_without_a_name_is_unconfigured():
    data = FakeKustoData()
    result = await kusto_discoverer(data=data).discover("database", DiscoveryScope())
    assert result.status == "unconfigured"
    assert data.commands == []


# ── Degradation table ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MissingDependency("azure.mgmt.resource.resources", "azure-mgmt-resource"),
         "unavailable"),
        (HttpResponseError("denied", status_code=403), "forbidden"),
        (HttpResponseError("no token", status_code=401), "forbidden"),
        (ClientAuthenticationError("no credential"), "forbidden"),
        (ServiceRequestError("dns"), "unreachable"),
        (ServiceRequestTimeoutError("slow"), "unreachable"),
        (socket.gaierror("name or service not known"), "unreachable"),
        (OSError("network is unreachable"), "unreachable"),
        (HttpResponseError("gone", status_code=404), "unavailable"),
        (HttpResponseError("slow down", status_code=429), "unavailable"),
        (HttpResponseError("boom", status_code=503), "unavailable"),
        (ValueError("something else entirely"), "unavailable"),
    ],
)
async def test_every_degradation_row_maps_to_its_status(error, expected):
    override("azure.core.exceptions", AZURE_CORE)
    resources = FakeArmResources(error=error)
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope()
    )
    assert result.status == expected
    assert result.nodes == ()
    assert result.detail


def test_classify_works_without_azure_core_installed():
    override_missing("azure.core.exceptions")
    assert classify_discovery_failure(ClientAuthenticationError("x"))[0] == "forbidden"
    assert classify_discovery_failure(ServiceRequestError("x"))[0] == "unreachable"
    assert classify_discovery_failure(RuntimeError("x"))[0] == "unavailable"


@pytest.mark.parametrize(
    "build",
    [
        lambda: (
            override(
                "azure.mgmt.resource.resources",
                arm_module(FakeArmResources(error=RuntimeError("fake exploded"))),
            ),
            ArmDiscoverer.from_config(CONFIG, provider),
            "resource_group",
            DiscoveryScope(),
        ),
        lambda: (
            override(
                "azure.search.documents.indexes",
                search_module(FakeSearchIndexClient(error=RuntimeError("boom"))),
            ),
            SearchDiscoverer.from_config(CONFIG, provider),
            "service",
            DiscoveryScope(),
        ),
        lambda: (
            override(
                "azure.mgmt.cosmosdb",
                cosmos_module(FakeCosmosResources(error=RuntimeError("boom"))),
            ),
            CosmosDiscoverer.from_config(CONFIG, provider),
            "account",
            DiscoveryScope(),
        ),
        lambda: (
            override(
                "azure.mgmt.cosmosdb",
                cosmos_module(FakeCosmosResources(error=RuntimeError("boom"))),
            ),
            GremlinDiscoverer.from_config(CONFIG, provider),
            "account",
            DiscoveryScope(),
        ),
        lambda: (
            override(
                "azure.mgmt.kusto",
                kusto_mgmt_module(FakeKustoDatabases(error=RuntimeError("boom"))),
            ),
            KustoDiscoverer.from_config(CONFIG, provider),
            "cluster",
            DiscoveryScope(),
        ),
    ],
)
async def test_no_discoverer_leaks_an_exception(build):
    _, discoverer, level, scope = build()
    result = await discoverer.discover(level, scope)
    assert result.status == "unavailable"
    assert result.nodes == ()
    assert result.service == discoverer.service


async def test_a_missing_sdk_is_unavailable_not_a_crash():
    override_missing("azure.mgmt.resource.resources")
    result = await ArmDiscoverer.from_config(CONFIG, provider).discover(
        "resource_group", DiscoveryScope()
    )
    assert result.status == "unavailable"
    assert "azure-mgmt-resource" in result.detail


async def test_a_url_in_an_exception_does_not_survive_into_detail():
    resources = FakeArmResources(
        error=RuntimeError("failed calling https://srch.search.windows.net/indexes")
    )
    result = await arm_discoverer(resources).discover(
        "resource_group", DiscoveryScope()
    )
    assert "https://" not in result.detail
    assert "<redacted-url>" in result.detail


# ── The bounded wrapper itself ───────────────────────────────────────────────


async def test_timeout_is_unreachable_with_the_budget_named():
    def slow():
        time.sleep(0.3)
        return []

    result = await bounded_discovery(
        service="arm",
        level="resource_group",
        scope=DiscoveryScope(),
        bounds=DiscoveryBounds(timeout_secs=0.01),
        collect=slow,
    )
    assert result.status == "unreachable"
    assert result.detail == "discovery exceeded 0.01s"
    assert ISO_Z.match(result.collected_at)


async def test_slow_but_inside_the_budget_is_still_ok():
    def slow():
        time.sleep(0.05)
        return [
            DiscoveryNode(kind="k", name="n", path=("n",), has_children=False)
        ]

    result = await bounded_discovery(
        service="arm",
        level="resource_group",
        scope=DiscoveryScope(),
        bounds=DiscoveryBounds(timeout_secs=5.0),
        collect=slow,
    )
    assert result.status == "ok"


async def test_the_wrapper_does_not_block_the_event_loop():
    ticks = 0

    async def tick():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    ticker = asyncio.create_task(tick())
    await bounded_discovery(
        service="arm",
        level="resource_group",
        scope=DiscoveryScope(),
        bounds=DiscoveryBounds(timeout_secs=5.0),
        collect=lambda: (time.sleep(0.1), [])[1],
    )
    ticker.cancel()
    assert ticks > 1


def test_attributes_are_coerced_to_renderable_scalars():
    clean = normalize_attributes(
        {
            "flag": True,
            "count": 7,
            "nothing": None,
            "ratio": 1.5,
            "blob": ["a", "b"],
            "url": "see https://x.example/y",
            "long": "x" * 900,
        }
    )
    assert clean["flag"] is True
    assert clean["count"] == 7
    assert clean["nothing"] is None
    assert clean["ratio"] == "1.5"
    assert clean["blob"] == "['a', 'b']"
    assert "https://" not in clean["url"]
    assert len(clean["long"]) == 500


def test_registry_registration_replaces_by_service_name():
    registry = DiscovererRegistry()
    first = ArmDiscoverer(credential_provider=provider)
    second = ArmDiscoverer(credential_provider=provider)
    registry.register(first)
    registry.register(second)
    assert registry.services() == ("arm",)
    assert registry.get("arm") is second
