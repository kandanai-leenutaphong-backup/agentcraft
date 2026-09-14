"""The content plane: bounded reads of what a thing actually contains.

Every reader here is exercised against a fake SDK client, because what is
worth pinning is the plane's contract — the cap is applied before the read,
the true size survives truncation, a failure is a status, and a caller-shaped
identifier is refused rather than escaped — and none of that needs a network.
"""

from __future__ import annotations

from typing import Any

import pytest

from azdata import (
    ContentBounds,
    ContentPayload,
    DiscoveryBounds,
    DiscoveryScope,
    bounded_content,
    content_failure,
    normalize_rows,
)
from azdata.blobs.discover import BlobDiscoverer, blob_endpoint
from azdata.blobs.read import BlobReader
from azdata.cosmos.content import CosmosReader, cosmos_endpoint
from azdata.core.optional import MissingDependency
from azdata.kusto.content import KustoReader
from azdata.logs.read import LogsDiscoverer, LogsReader, _flatten
from azdata.registry.discover import RegistryDiscoverer
from azdata.search.content import SearchReader

WORKSPACE_ID = (
    "/subscriptions/s-1/resourceGroups/rg-one"
    "/providers/Microsoft.OperationalInsights/workspaces/log-one"
)


# -- the wrapper ---------------------------------------------------------


def test_bounds_are_clamped_not_validated() -> None:
    bounds = ContentBounds(max_bytes=0, max_rows=0, timeout_secs=0)
    assert bounds.max_bytes == 1
    assert bounds.max_rows == 1
    assert bounds.timeout_secs > 0


async def test_bounded_content_reports_ok_and_empty_from_the_payload() -> None:
    full = await bounded_content(
        service="s",
        kind="k",
        bounds=ContentBounds(),
        fetch=lambda: (ContentPayload(form="bytes", data=b"x", size_bytes=1), False),
    )
    assert full.status == "ok"
    blank = await bounded_content(
        service="s", kind="k", bounds=ContentBounds(), fetch=lambda: (ContentPayload(), False)
    )
    assert blank.status == "empty"


async def test_bounded_content_classifies_a_failure_rather_than_raising() -> None:
    denied = RuntimeError("nope")
    denied.status_code = 403  # type: ignore[attr-defined]

    def fetch() -> Any:
        raise denied

    result = await bounded_content(
        service="s", kind="k", bounds=ContentBounds(), fetch=fetch
    )
    assert result.status == "forbidden"
    assert result.payload.is_empty


async def test_bounded_content_reports_a_missing_sdk_as_unavailable() -> None:
    def fetch() -> Any:
        raise MissingDependency("azure.storage.blob", "azure-storage-blob")

    result = await bounded_content(
        service="s", kind="k", bounds=ContentBounds(), fetch=fetch
    )
    assert result.status == "unavailable"
    assert "azure-storage-blob" in result.detail


async def test_bounded_content_turns_an_overrun_into_unreachable() -> None:
    import time

    result = await bounded_content(
        service="s",
        kind="k",
        bounds=ContentBounds(timeout_secs=0.01),
        fetch=lambda: (time.sleep(0.5), (ContentPayload(), False))[1],
    )
    assert result.status == "unreachable"
    assert "exceeded" in result.detail


def test_content_failure_sanitises_its_detail() -> None:
    result = content_failure(
        service="s", kind="k", status="unreachable", detail="see https://host/path"
    )
    assert "https://host/path" not in result.detail


def test_normalize_rows_keeps_first_appearance_column_order() -> None:
    rows, columns, truncated = normalize_rows(
        [{"b": 1, "a": 2}, {"c": 3, "a": 4}], max_rows=10
    )
    assert columns == ("b", "a", "c")
    assert truncated is False
    assert rows[1]["c"] == 3


def test_normalize_rows_caps_and_reports_truncation() -> None:
    rows, _, truncated = normalize_rows([{"a": n} for n in range(10)], max_rows=3)
    assert len(rows) == 3
    assert truncated is True


def test_normalize_rows_renders_bytes_and_structures_as_bounded_text() -> None:
    rows, _, _ = normalize_rows([{"raw": b"1234", "nested": {"x": 1}}], max_rows=1)
    assert rows[0]["raw"] == "<4 bytes>"
    assert isinstance(rows[0]["nested"], str)


# -- blobs ---------------------------------------------------------------


class FakeBlobProperties:
    def __init__(self, size: int, content_type: str) -> None:
        self.size = size
        self.content_settings = type("S", (), {"content_type": content_type})()


class FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class FakeBlobClient:
    def __init__(self, data: bytes, content_type: str) -> None:
        self._data = data
        self._content_type = content_type
        self.ranges: list[tuple[int, int]] = []

    def get_blob_properties(self) -> FakeBlobProperties:
        return FakeBlobProperties(len(self._data), self._content_type)

    def download_blob(self, offset: int = 0, length: int | None = None) -> FakeDownload:
        self.ranges.append((offset, length or 0))
        return FakeDownload(self._data[offset : offset + (length or len(self._data))])


class FakeBlobService:
    def __init__(self, blob: FakeBlobClient) -> None:
        self.blob = blob
        self.containers: list[Any] = []

    def get_blob_client(self, container: str, name: str) -> FakeBlobClient:
        return self.blob

    def get_container_client(self, container: str) -> Any:
        return self

    def list_containers(self) -> Any:
        return self.containers

    def walk_blobs(self, name_starts_with: str | None = None, delimiter: str = "/") -> Any:
        return [entry for entry in self.entries if entry["name"].startswith(name_starts_with or "")]


def blob_reader(data: bytes, content_type: str) -> tuple[BlobReader, FakeBlobClient]:
    blob = FakeBlobClient(data, content_type)
    reader = BlobReader(credential_provider=lambda: None)
    reader._clients[blob_endpoint("acct")] = FakeBlobService(blob)
    return reader, blob


async def test_blob_read_returns_the_declared_media_type_and_bytes() -> None:
    reader, _ = blob_reader(b"Depth marker: hello", "text/plain")
    result = await reader.read(account_name="acct", container="c", blob="nested/deep/file.txt")
    assert result.status == "ok"
    assert result.payload.media_type == "text/plain"
    assert result.payload.data == b"Depth marker: hello"
    assert result.truncated is False


async def test_blob_read_is_a_ranged_request_and_keeps_the_true_size() -> None:
    reader, blob = blob_reader(b"x" * 5000, "application/octet-stream")
    result = await reader.read(
        account_name="acct", container="c", blob="big.bin", bounds=ContentBounds(max_bytes=64)
    )
    assert blob.ranges == [(0, 64)]
    assert len(result.payload.data) == 64
    assert result.payload.size_bytes == 5000
    assert result.truncated is True


async def test_blob_read_without_coordinates_is_unconfigured() -> None:
    reader = BlobReader(credential_provider=lambda: None)
    assert (await reader.read(container="c", blob="b")).status == "unconfigured"


async def test_blob_walk_separates_folders_from_blobs() -> None:
    service = FakeBlobService(FakeBlobClient(b"", ""))
    service.entries = [  # type: ignore[attr-defined]
        {"name": "nested/", "content_settings": None},
        {
            "name": "README.md",
            "size": 42,
            "content_settings": type("S", (), {"content_type": "text/markdown"})(),
            "last_modified": None,
            "blob_type": "BlockBlob",
            "access_tier": "Hot",
        },
    ]
    discoverer = BlobDiscoverer(credential_provider=lambda: None)
    discoverer._clients[blob_endpoint("acct")] = service
    result = await discoverer.discover(
        "container", DiscoveryScope(account_name="acct", path=("demo-container", ""))
    )
    kinds = {node.name: (node.kind, node.has_children) for node in result.nodes}
    assert kinds["nested"] == ("blob_folder", True)
    assert kinds["README.md"] == ("blob", False)
    paths = {node.name: node.path for node in result.nodes}
    assert paths["README.md"] == ("demo-container", "README.md")
    assert paths["nested"] == ("demo-container", "nested/")


async def test_blob_walk_names_a_nested_leaf_relative_to_its_prefix() -> None:
    service = FakeBlobService(FakeBlobClient(b"", ""))
    service.entries = [  # type: ignore[attr-defined]
        {
            "name": "nested/deep/file.txt",
            "size": 116,
            "content_settings": type("S", (), {"content_type": "text/plain"})(),
            "last_modified": None,
            "blob_type": "BlockBlob",
            "access_tier": None,
        }
    ]
    discoverer = BlobDiscoverer(credential_provider=lambda: None)
    discoverer._clients[blob_endpoint("acct")] = service
    result = await discoverer.discover(
        "container", DiscoveryScope(account_name="acct", path=("demo", "nested/deep/"))
    )
    assert result.nodes[0].name == "file.txt"
    assert result.nodes[0].path == ("demo", "nested/deep/file.txt")


async def test_blob_discovery_without_an_account_is_unconfigured() -> None:
    discoverer = BlobDiscoverer(credential_provider=lambda: None)
    result = await discoverer.discover("account", DiscoveryScope())
    assert result.status == "unconfigured"


class Denied(Exception):
    """Shaped like the SDK's error: a 403 carrying a distinguishing code."""

    def __init__(self, error_code: str) -> None:
        super().__init__(f"This request is not authorized. ErrorCode:{error_code}")
        self.error_code = error_code
        self.status_code = 403


class DeniedService:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def list_containers(self):
        raise self._error

    def get_container_client(self, container: str):
        return self

    def walk_blobs(self, name_starts_with=None, delimiter="/"):
        raise self._error

    def get_blob_client(self, container: str, blob: str):
        return self

    def get_blob_properties(self):
        raise self._error


async def test_a_network_rule_denial_is_unreachable_not_forbidden() -> None:
    """Both are HTTP 403; only one of them is fixed by a role grant."""
    discoverer = BlobDiscoverer(credential_provider=lambda: None)
    discoverer._clients[blob_endpoint("acct")] = DeniedService(Denied("AuthorizationFailure"))
    result = await discoverer.discover("account", DiscoveryScope(account_name="acct"))
    assert result.status == "unreachable"
    assert "public network access" in result.detail
    assert "RequestId" not in result.detail


async def test_a_role_denial_is_still_forbidden() -> None:
    discoverer = BlobDiscoverer(credential_provider=lambda: None)
    discoverer._clients[blob_endpoint("acct")] = DeniedService(
        Denied("AuthorizationPermissionMismatch")
    )
    result = await discoverer.discover("account", DiscoveryScope(account_name="acct"))
    assert result.status == "forbidden"


async def test_a_network_rule_denial_on_a_prefix_walk_is_unreachable() -> None:
    discoverer = BlobDiscoverer(credential_provider=lambda: None)
    discoverer._clients[blob_endpoint("acct")] = DeniedService(Denied("AuthorizationFailure"))
    result = await discoverer.discover(
        "container", DiscoveryScope(account_name="acct", path=("c", ""))
    )
    assert result.status == "unreachable"


async def test_a_network_rule_denial_on_a_blob_read_is_unreachable() -> None:
    reader = BlobReader(credential_provider=lambda: None)
    reader._clients[blob_endpoint("acct")] = DeniedService(Denied("AuthorizationFailure"))
    result = await reader.read(account_name="acct", container="c", blob="b")
    assert result.status == "unreachable"


# -- cosmos --------------------------------------------------------------


class FakeCosmosContainer:
    def __init__(self, items: list[dict[str, Any]], *, legacy_kwarg: bool) -> None:
        self.items = items
        self.legacy = legacy_kwarg
        self.queries: list[str] = []

    def query_items(self, query: str, enable_cross_partition_query: bool | None = None) -> Any:
        if enable_cross_partition_query is not None and not self.legacy:
            raise TypeError("unexpected keyword argument")
        self.queries.append(query)
        return list(self.items)


class FakeCosmosClient:
    def __init__(self, container: FakeCosmosContainer) -> None:
        self.container = container

    def get_database_client(self, name: str) -> "FakeCosmosClient":
        return self

    def get_container_client(self, name: str) -> FakeCosmosContainer:
        return self.container


def cosmos_reader(items: list[dict[str, Any]], *, legacy_kwarg: bool = True) -> tuple[CosmosReader, FakeCosmosContainer]:
    container = FakeCosmosContainer(items, legacy_kwarg=legacy_kwarg)
    reader = CosmosReader(credential_provider=lambda: None)
    reader._clients[cosmos_endpoint("acct")] = FakeCosmosClient(container)
    return reader, container


async def test_cosmos_documents_cap_in_the_query_not_the_loop() -> None:
    reader, container = cosmos_reader([{"id": "1", "name": "a"}])
    result = await reader.documents(
        account_name="acct", database="db", container="c", bounds=ContentBounds(max_rows=5)
    )
    assert result.status == "ok"
    assert container.queries == ["SELECT TOP 6 * FROM c"]
    assert result.payload.columns == ("id", "name")


async def test_cosmos_documents_survive_the_removed_cross_partition_kwarg() -> None:
    reader, container = cosmos_reader([{"id": "1"}], legacy_kwarg=False)
    result = await reader.documents(account_name="acct", database="db", container="c")
    assert result.status == "ok"
    assert result.payload.rows[0]["id"] == "1"


async def test_cosmos_documents_without_coordinates_are_unconfigured() -> None:
    reader = CosmosReader(credential_provider=lambda: None)
    assert (await reader.documents(database="", container="")).status == "unconfigured"


def test_cosmos_endpoint_is_empty_without_an_account() -> None:
    assert cosmos_endpoint("") == ""
    assert cosmos_endpoint("acct").startswith("https://acct.")


# -- kusto ---------------------------------------------------------------


class FakeColumn:
    def __init__(self, name: str) -> None:
        self.column_name = name
        self.column_type = "string"


class FakePrimary:
    def __init__(self, columns: list[str], rows: list[dict[str, Any]]) -> None:
        self.columns = [FakeColumn(name) for name in columns]
        self._rows = rows

    def __iter__(self) -> Any:
        return iter(self._rows)


class FakeKustoResponse:
    def __init__(self, columns: list[str], rows: list[dict[str, Any]]) -> None:
        self.primary_results = [FakePrimary(columns, rows)]


class FakeKustoClient:
    def __init__(self, response: FakeKustoResponse) -> None:
        self.response = response
        self.queries: list[tuple[str, str]] = []

    def execute(self, database: str, query: str) -> FakeKustoResponse:
        self.queries.append((database, query))
        return self.response


def kusto_reader(columns: list[str], rows: list[dict[str, Any]]) -> tuple[KustoReader, FakeKustoClient]:
    client = FakeKustoClient(FakeKustoResponse(columns, rows))
    reader = KustoReader(credential_provider=lambda: None)
    reader._clients["https://adx.kusto.windows.net"] = client
    return reader, client


async def test_kusto_rows_compose_a_take_query_from_the_bound() -> None:
    reader, client = kusto_reader(["Name", "Count"], [{"Name": "a", "Count": 1}])
    result = await reader.rows(
        query_uri="https://adx.kusto.windows.net",
        database="db",
        table="Events",
        bounds=ContentBounds(max_rows=25),
    )
    assert result.status == "ok"
    assert client.queries == [("db", '["Events"] | take 25')]
    assert result.payload.columns == ("Name", "Count")


async def test_kusto_declared_columns_survive_an_all_null_column() -> None:
    reader, _ = kusto_reader(["Name", "Empty"], [{"Name": "a", "Empty": None}])
    result = await reader.rows(
        query_uri="https://adx.kusto.windows.net", database="db", table="Events"
    )
    assert result.payload.columns == ("Name", "Empty")


@pytest.mark.parametrize("table", ['Ev"ents', "Events]|drop", "Ev\nents", ""])
async def test_kusto_refuses_a_table_name_that_is_not_an_identifier(table: str) -> None:
    reader, client = kusto_reader(["a"], [])
    result = await reader.rows(
        query_uri="https://adx.kusto.windows.net", database="db", table=table
    )
    assert result.status in ("unavailable", "unconfigured")
    assert client.queries == []


# -- search --------------------------------------------------------------


class FakeSearchClient:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.calls: list[tuple[str, int]] = []

    def search(self, search_text: str, top: int) -> Any:
        self.calls.append((search_text, top))
        return list(self.documents)


async def test_search_documents_ask_for_one_more_than_the_bound() -> None:
    client = FakeSearchClient([{"id": "1", "@search.score": 1.0}])
    reader = SearchReader(credential_provider=lambda: None)
    reader._clients[("https://srch.search.windows.net", "idx")] = client
    result = await reader.documents(
        endpoint="https://srch.search.windows.net", index="idx", bounds=ContentBounds(max_rows=3)
    )
    assert result.status == "ok"
    assert client.calls == [("*", 4)]
    assert "@search.score" in result.payload.columns


async def test_search_documents_without_an_index_are_unconfigured() -> None:
    reader = SearchReader(credential_provider=lambda: None)
    assert (await reader.documents(endpoint="", index="")).status == "unconfigured"


# -- logs ----------------------------------------------------------------


class FakeLogsArm:
    def __init__(self, *, document: Any = None, query: Any = None, tables: Any = None) -> None:
        self.document = document or {}
        self.query = query or {}
        self.tables = tables or []
        self.reads = 0
        self.requests: list[tuple[str, dict[str, Any], str]] = []

    def read(self, resource_id: str, *, api_version: str = "") -> Any:
        self.reads += 1
        return self.document

    def get_json(self, url: str, *, params: Any = None, scope: str = "", headers: Any = None) -> Any:
        self.requests.append((url, dict(params or {}), scope))
        return self.query

    def list_children(self, resource_id: str, collection: str, **_: Any) -> Any:
        return self.tables


def test_flatten_pairs_columns_with_row_positions() -> None:
    rows, columns = _flatten(
        {"tables": [{"columns": [{"name": "TimeGenerated"}, {"name": "Level"}], "rows": [["t", "Info"]]}]}
    )
    assert columns == ("TimeGenerated", "Level")
    assert rows == [{"TimeGenerated": "t", "Level": "Info"}]


def test_flatten_of_an_empty_document_is_empty() -> None:
    assert _flatten({}) == ([], ())


async def test_log_rows_resolve_the_customer_id_once() -> None:
    arm = FakeLogsArm(
        document={"properties": {"customerId": "w-guid"}},
        query={"tables": [{"columns": [{"name": "Level"}], "rows": [["Info"]]}]},
    )
    reader = LogsReader(arm=arm)  # type: ignore[arg-type]
    await reader.rows(workspace_id=WORKSPACE_ID, table="AppTraces")
    await reader.rows(workspace_id=WORKSPACE_ID, table="AppTraces")
    assert arm.reads == 1
    url, params, scope = arm.requests[-1]
    assert "w-guid" in url
    assert params["query"] == "AppTraces | take 100"
    assert scope.startswith("https://api.loganalytics.io")


async def test_log_rows_refuse_a_table_name_that_is_not_an_identifier() -> None:
    arm = FakeLogsArm(document={"properties": {"customerId": "w"}})
    reader = LogsReader(arm=arm)  # type: ignore[arg-type]
    result = await reader.rows(workspace_id=WORKSPACE_ID, table="App | drop")
    assert result.status == "unavailable"
    assert arm.requests == []


async def test_log_tables_come_from_the_management_plane() -> None:
    arm = FakeLogsArm(
        tables=[
            {
                "name": "AppTraces",
                "properties": {"plan": "Analytics", "retentionInDays": 30, "schema": {"tableType": "Microsoft"}},
            }
        ]
    )
    discoverer = LogsDiscoverer(credential_provider=lambda: None, arm=arm)  # type: ignore[arg-type]
    result = await discoverer.discover("workspace", DiscoveryScope(path=(WORKSPACE_ID,)))
    assert result.status == "ok"
    assert result.nodes[0].name == "AppTraces"
    assert result.nodes[0].attributes["plan"] == "Analytics"
    assert result.nodes[0].path == (WORKSPACE_ID, "AppTraces")


async def test_a_workspaces_own_tables_sort_ahead_of_the_builtin_catalogue() -> None:
    """The catalogue is larger than the bound; the custom tables must survive it."""
    arm = FakeLogsArm(
        tables=[
            {"name": f"AAD{n:03d}", "properties": {"schema": {"tableType": "Microsoft"}}}
            for n in range(5)
        ]
        + [
            {"name": "ContainerAppConsoleLogs_CL", "properties": {"schema": {"tableType": "CustomLog"}}},
            {"name": "AppEvents_CL", "properties": {"schema": {"tableType": "Microsoft"}}},
        ]
    )
    discoverer = LogsDiscoverer(credential_provider=lambda: None, arm=arm)  # type: ignore[arg-type]
    result = await discoverer.discover(
        "workspace",
        DiscoveryScope(path=(WORKSPACE_ID,)),
        bounds=DiscoveryBounds(max_items=3),
    )
    assert [node.name for node in result.nodes][:2] == [
        "AppEvents_CL",
        "ContainerAppConsoleLogs_CL",
    ]
    assert result.truncated is True


async def test_log_tables_without_a_workspace_are_unconfigured() -> None:
    discoverer = LogsDiscoverer(credential_provider=lambda: None, arm=FakeLogsArm())  # type: ignore[arg-type]
    assert (await discoverer.discover("workspace", DiscoveryScope())).status == "unconfigured"


# -- container registry ---------------------------------------------------


class FakeRegistryClient:
    def __init__(self, repositories: list[str], tags: list[dict[str, Any]]) -> None:
        self._repositories = repositories
        self._tags = tags
        self.scopes: list[str] = []

    def repositories(self, login_server: str, tenant_id: str) -> list[str]:
        self.scopes.append("catalog")
        return self._repositories

    def tags(self, login_server: str, tenant_id: str, repository: str) -> list[dict[str, Any]]:
        self.scopes.append(f"tags:{repository}")
        return self._tags


class TenantArm:
    def tenant_id(self, subscription_id: str) -> str:
        return "t-1"


def registry_discoverer(repositories: list[str], tags: list[dict[str, Any]]) -> RegistryDiscoverer:
    return RegistryDiscoverer(
        subscription_id="s-1",
        credential_provider=lambda: None,
        arm=TenantArm(),  # type: ignore[arg-type]
        client=FakeRegistryClient(repositories, tags),  # type: ignore[arg-type]
    )


async def test_registry_lists_repositories_then_tags() -> None:
    discoverer = registry_discoverer(
        ["explorer/api"],
        [{"name": "v1", "digest": "sha256:abc", "changeableAttributes": {"writeEnabled": True}}],
    )
    repositories = await discoverer.discover(
        "registry", DiscoveryScope(path=("acr.azurecr.io",))
    )
    assert repositories.nodes[0].name == "explorer/api"
    assert repositories.nodes[0].path == ("acr.azurecr.io", "explorer/api")

    tags = await discoverer.discover(
        "repository", DiscoveryScope(path=("acr.azurecr.io", "explorer/api"))
    )
    assert tags.nodes[0].name == "v1"
    assert tags.nodes[0].attributes["digest"] == "sha256:abc"
    assert tags.nodes[0].has_children is False


async def test_registry_without_a_login_server_is_unconfigured() -> None:
    discoverer = registry_discoverer([], [])
    assert (await discoverer.discover("registry", DiscoveryScope())).status == "unconfigured"


async def test_registry_tags_are_bounded() -> None:
    discoverer = registry_discoverer([], [{"name": f"v{n}"} for n in range(10)])
    result = await discoverer.discover(
        "repository",
        DiscoveryScope(path=("acr.azurecr.io", "repo")),
        bounds=DiscoveryBounds(max_items=3),
    )
    assert len(result.nodes) == 3
    assert result.truncated is True
