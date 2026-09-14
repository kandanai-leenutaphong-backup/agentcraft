"""The estate plane: generic ARM reads, Resource Graph, and estate search.

WHY A FAKE TRANSPORT AND NOT A FAKE ``ArmApi``
----------------------------------------------
The interesting behaviour is which URL is requested, with which api-version,
and what happens when the answer is a 403. Faking ``ArmApi`` itself would
test the fake. These tests replace only the HTTP client, so api-version
resolution, ``nextLink`` following and the Resource Graph body are all the
real implementations.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from azdata import (
    ContentBounds,
    DiscoveryBounds,
    DiscoveryScope,
    build_estate_access,
)
from azdata.core.config import AzureDataConfig
from azdata.core.discover import DiscoveryAbsent
from azdata.estate.armapi import (
    ArmApi,
    child_type_of,
    kql_literal,
    name_of,
    resource_group_of,
    subscription_of,
    type_of,
)
from azdata.estate.discover import EstateDiscoverer
from azdata.estate.read import EstateReader, redact_credentials

SUBSCRIPTION = "s-1"
STORAGE_ID = (
    "/subscriptions/s-1/resourceGroups/rg-one"
    "/providers/Microsoft.Storage/storageAccounts/stone"
)


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self) -> Any:
        return self._payload


class FakeHttp:
    """Records every request and answers from a routing table."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.gets: list[tuple[str, dict[str, Any]]] = []
        self.posts: list[tuple[str, Any]] = []

    def get(self, url: str, params: Any = None, headers: Any = None) -> FakeResponse:
        self.gets.append((url, dict(params or {})))
        # Longest fragment first: a provider-metadata URL is a prefix of every
        # resource URL under it, so declaration order would route both to it.
        for fragment in sorted(self.routes, key=len, reverse=True):
            if fragment in url:
                payload = self.routes[fragment]
                if isinstance(payload, Exception):
                    raise payload
                return FakeResponse(payload)
        return FakeResponse({}, status_code=404)

    def post(self, url: str, params: Any = None, headers: Any = None, json: Any = None) -> FakeResponse:
        self.posts.append((url, json))
        payload = self.routes.get("resourceGraph", {"data": []})
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)


class FakeToken:
    token = "not-a-real-token"
    expires_on = 4_102_444_800  # far future, so the cache is exercised


class FakeCredential:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_token(self, scope: str) -> FakeToken:
        self.calls.append(scope)
        return FakeToken()


def build_api(routes: dict[str, Any]) -> tuple[ArmApi, FakeHttp, FakeCredential]:
    credential = FakeCredential()
    api = ArmApi(credential_provider=lambda: credential)
    http = FakeHttp(routes)
    api._client = http  # the transport is the only thing replaced
    return api, http, credential


# -- id arithmetic -------------------------------------------------------


def test_type_of_reads_every_other_segment_after_providers() -> None:
    assert type_of(STORAGE_ID) == "Microsoft.Storage/storageAccounts"
    assert (
        type_of(STORAGE_ID + "/blobServices/default/containers/demo")
        == "Microsoft.Storage/storageAccounts/blobServices/containers"
    )


def test_type_of_is_empty_without_a_provider_segment() -> None:
    assert type_of("/subscriptions/s-1/resourceGroups/rg-one") == ""
    assert type_of("") == ""


def test_child_type_of_drops_the_name_segments_of_a_nested_collection() -> None:
    assert (
        child_type_of("Microsoft.Storage/storageAccounts", "blobServices/default/containers")
        == "Microsoft.Storage/storageAccounts/blobServices/containers"
    )
    assert child_type_of("Microsoft.App/jobs", "executions") == "Microsoft.App/jobs/executions"


def test_id_segments_are_read_case_insensitively() -> None:
    assert subscription_of(STORAGE_ID) == "s-1"
    assert resource_group_of(STORAGE_ID) == "rg-one"
    assert resource_group_of(STORAGE_ID.replace("resourceGroups", "resourcegroups")) == "rg-one"
    assert name_of(STORAGE_ID) == "stone"


def test_kql_literal_cannot_be_terminated_early() -> None:
    assert kql_literal("rg-one") == "@'rg-one'"
    assert kql_literal("o'neill") == "@'o''neill'"
    # A backslash is an ordinary character in the verbatim form.
    assert kql_literal("a\\b") == "@'a\\b'"


def test_kql_literal_strips_control_characters() -> None:
    assert kql_literal("a\nb\x00c") == "@'abc'"


# -- api-version resolution ---------------------------------------------


def test_api_version_prefers_the_newest_stable() -> None:
    api, _, _ = build_api(
        {
            "/providers/Microsoft.Storage": {
                "resourceTypes": [
                    {
                        "resourceType": "storageAccounts",
                        "apiVersions": ["2024-01-01", "2025-01-01-preview", "2023-01-01"],
                    }
                ]
            }
        }
    )
    assert api.api_version("Microsoft.Storage/storageAccounts", SUBSCRIPTION) == "2024-01-01"


def test_api_version_falls_back_to_a_preview_when_that_is_all_there_is() -> None:
    api, _, _ = build_api(
        {
            "/providers/Microsoft.App": {
                "resourceTypes": [
                    {"resourceType": "jobs/executions", "apiVersions": ["2023-05-01-preview"]}
                ]
            }
        }
    )
    assert api.api_version("Microsoft.App/jobs/executions", SUBSCRIPTION) == "2023-05-01-preview"


def test_api_version_is_absent_for_a_type_the_provider_does_not_declare() -> None:
    api, _, _ = build_api({"/providers/Microsoft.App": {"resourceTypes": []}})
    with pytest.raises(DiscoveryAbsent):
        api.api_version("Microsoft.App/jobs", SUBSCRIPTION)


def test_an_undeclared_child_collection_falls_back_to_its_parent() -> None:
    """``Microsoft.App`` omits ``containerApps/revisions``, which is readable."""
    api, _, _ = build_api(
        {
            "/providers/Microsoft.App": {
                "resourceTypes": [
                    {"resourceType": "containerApps", "apiVersions": ["2026-03-02-preview"]}
                ]
            }
        }
    )
    assert (
        api.resolve_api_version(
            "Microsoft.App/containerApps/revisions", SUBSCRIPTION
        )
        == "2026-03-02-preview"
    )
    # Two levels down resolves to the same declared ancestor.
    assert (
        api.resolve_api_version(
            "Microsoft.App/containerApps/revisions/replicas", SUBSCRIPTION
        )
        == "2026-03-02-preview"
    )


def test_a_type_with_no_declared_ancestor_is_still_absent() -> None:
    api, _, _ = build_api({"/providers/Microsoft.App": {"resourceTypes": []}})
    with pytest.raises(DiscoveryAbsent):
        api.resolve_api_version(
            "Microsoft.App/containerApps/revisions", SUBSCRIPTION
        )


def test_provider_versions_are_resolved_once_per_namespace() -> None:
    api, http, _ = build_api(
        {
            "/providers/Microsoft.Storage": {
                "resourceTypes": [
                    {"resourceType": "storageaccounts", "apiVersions": ["2024-01-01"]}
                ]
            }
        }
    )
    api.api_version("Microsoft.Storage/storageAccounts", SUBSCRIPTION)
    api.api_version("Microsoft.Storage/storageAccounts", SUBSCRIPTION)
    assert len(http.gets) == 1


def test_token_is_minted_once_and_never_appears_in_a_result() -> None:
    api, _, credential = build_api({})
    first = api.token()
    second = api.token()
    assert first == second
    assert len(credential.calls) == 1


# -- generic reads -------------------------------------------------------


def test_read_resolves_the_api_version_from_the_id() -> None:
    api, http, _ = build_api(
        {
            "/providers/Microsoft.Storage": {
                "resourceTypes": [
                    {"resourceType": "storageaccounts", "apiVersions": ["2024-01-01"]}
                ]
            },
            STORAGE_ID: {"id": STORAGE_ID, "properties": {"tier": "Hot"}},
        }
    )
    document = api.read(STORAGE_ID)
    assert document["properties"]["tier"] == "Hot"
    assert http.gets[-1][1]["api-version"] == "2024-01-01"


def test_list_children_follows_next_link_without_re_adding_params() -> None:
    api, http, _ = build_api({})

    pages = [
        {"value": [{"id": "a", "name": "a"}], "nextLink": "https://arm/page2"},
        {"value": [{"id": "b", "name": "b"}]},
    ]

    def get(url: str, params: Any = None, headers: Any = None) -> FakeResponse:
        http.gets.append((url, dict(params or {})))
        return FakeResponse(pages.pop(0))

    http.get = get  # type: ignore[method-assign]
    items = api.list_children(STORAGE_ID, "blobServices/default/containers", api_version="v")
    assert [item["name"] for item in items] == ["a", "b"]
    assert http.gets[1][1] == {}


def test_resource_graph_clamps_the_page_size() -> None:
    api, http, _ = build_api({"resourceGraph": {"data": [{"name": "one"}]}})
    rows = api.resource_graph("Resources", subscriptions=(SUBSCRIPTION,), top=99_999)
    assert rows == [{"name": "one"}]
    assert http.posts[-1][1]["options"]["$top"] == 1000


# -- discovery -----------------------------------------------------------


class FakeArm:
    """Answers the three calls ``EstateDiscoverer`` makes, and records them."""

    def __init__(self, **answers: Any) -> None:
        self.answers = answers
        self.queries: list[str] = []
        self.children: list[tuple[str, str]] = []

    def resource_graph(self, query: str, *, subscriptions: Any, top: int = 0, skip: int = 0) -> Any:
        self.queries.append(query)
        answer = self.answers.get("graph")
        if isinstance(answer, Exception):
            raise answer
        return answer or []

    def list_resource_groups(self, subscription_id: str) -> Any:
        return self.answers.get("groups", [])

    def list_resources(self, subscription_id: str, group: str) -> Any:
        return self.answers.get("resources", [])

    def list_children(self, resource_id: str, collection: str, **_: Any) -> Any:
        self.children.append((resource_id, collection))
        answer = self.answers.get("children")
        if isinstance(answer, Exception):
            raise answer
        return answer or []


def estate(**answers: Any) -> tuple[EstateDiscoverer, FakeArm]:
    arm = FakeArm(**answers)
    return (
        EstateDiscoverer(
            subscription_id=SUBSCRIPTION,
            credential_provider=lambda: None,
            arm=arm,  # type: ignore[arg-type]
        ),
        arm,
    )


async def test_subscription_level_lists_resource_groups() -> None:
    discoverer, _ = estate(
        graph=[
            {"id": "/subscriptions/s-1/resourceGroups/rg-b", "name": "rg-b", "location": "eastus", "resources": 3},
            {"id": "/subscriptions/s-1/resourceGroups/rg-a", "name": "rg-a", "location": "westus", "resources": 0},
        ]
    )
    result = await discoverer.discover("subscription", DiscoveryScope())
    assert result.status == "ok"
    assert [node.name for node in result.nodes] == ["rg-a", "rg-b"]
    assert result.nodes[0].attributes["resources"] == 0


async def test_resource_groups_fall_back_to_arm_when_resource_graph_fails() -> None:
    discoverer, _ = estate(
        graph=RuntimeError("no Resource Graph provider"),
        groups=[{"id": "/subscriptions/s-1/resourceGroups/rg-a", "name": "rg-a", "location": "eastus"}],
    )
    result = await discoverer.discover("subscription", DiscoveryScope())
    assert result.status == "ok"
    assert result.nodes[0].name == "rg-a"
    # The counts are lost, not the tree.
    assert result.nodes[0].attributes["resources"] is None


async def test_resource_group_level_lists_resources_with_their_ids() -> None:
    discoverer, arm = estate(
        graph=[
            {
                "id": STORAGE_ID,
                "name": "stone",
                "type": "microsoft.storage/storageaccounts",
                "location": "eastus",
                "kind": "StorageV2",
                "skuName": "Standard_LRS",
            }
        ]
    )
    result = await discoverer.discover("resource_group", DiscoveryScope(path=("rg-one",)))
    assert result.nodes[0].path == (STORAGE_ID,)
    assert result.nodes[0].attributes["sku"] == "Standard_LRS"
    assert "@'rg-one'" in arm.queries[0]


async def test_resource_group_level_without_a_group_is_unconfigured() -> None:
    discoverer, _ = estate()
    result = await discoverer.discover("resource_group", DiscoveryScope())
    assert result.status == "unconfigured"
    assert "resource group" in result.detail


async def test_collection_level_lists_any_arm_child() -> None:
    discoverer, arm = estate(
        children=[
            {
                "id": STORAGE_ID + "/blobServices/default/containers/demo",
                "name": "demo",
                "type": "Microsoft.Storage/storageAccounts/blobServices/containers",
                "properties": {"provisioningState": "Succeeded", "leaseState": "Available"},
            }
        ]
    )
    result = await discoverer.discover(
        "collection",
        DiscoveryScope(path=(STORAGE_ID, "blobServices/default/containers")),
    )
    assert result.status == "ok"
    assert result.nodes[0].name == "demo"
    assert result.nodes[0].attributes["provisioningState"] == "Succeeded"
    # An unlisted property is not copied into the node.
    assert "leaseState" not in result.nodes[0].attributes
    assert arm.children == [(STORAGE_ID, "blobServices/default/containers")]


async def test_a_forbidden_collection_is_a_status_not_an_exception() -> None:
    failure = RuntimeError("denied")
    failure.status_code = 403  # type: ignore[attr-defined]
    discoverer, _ = estate(children=failure)
    result = await discoverer.discover(
        "collection", DiscoveryScope(path=(STORAGE_ID, "revisions"))
    )
    assert result.status == "forbidden"
    assert result.nodes == ()


async def test_an_unknown_level_is_unavailable() -> None:
    discoverer, _ = estate()
    result = await discoverer.discover("nope", DiscoveryScope())
    assert result.status == "unavailable"


async def test_collection_listing_is_bounded_and_reports_truncation() -> None:
    discoverer, _ = estate(
        children=[{"id": f"x/{n}", "name": f"n{n:03d}"} for n in range(10)]
    )
    result = await discoverer.discover(
        "collection",
        DiscoveryScope(path=(STORAGE_ID, "revisions")),
        bounds=DiscoveryBounds(max_items=4),
    )
    assert len(result.nodes) == 4
    assert result.truncated is True


# -- content: properties and search ---------------------------------------


class ReadingArm(FakeArm):
    def read(self, resource_id: str, *, api_version: str = "") -> Any:
        return self.answers.get("document", {})


async def test_properties_returns_the_whole_arm_document_as_json() -> None:
    arm = ReadingArm(document={"id": STORAGE_ID, "properties": {"tier": "Hot"}})
    reader = EstateReader(arm=arm, subscription_id=SUBSCRIPTION)  # type: ignore[arg-type]
    result = await reader.properties(STORAGE_ID)
    assert result.status == "ok"
    assert json.loads(result.payload.data)["properties"]["tier"] == "Hot"
    assert result.payload.media_type == "application/json"


async def test_properties_redacts_credential_shaped_keys_at_any_depth() -> None:
    arm = ReadingArm(
        document={
            "properties": {
                "primaryKey": "abc",
                "nested": [{"connectionString": "xyz"}],
                "location": "eastus",
            }
        }
    )
    reader = EstateReader(arm=arm, subscription_id=SUBSCRIPTION)  # type: ignore[arg-type]
    result = await reader.properties(STORAGE_ID)
    body = result.payload.data.decode("utf-8")
    assert "abc" not in body and "xyz" not in body
    assert "(redacted)" in body
    assert "eastus" in body


async def test_properties_truncates_and_still_reports_the_true_size() -> None:
    arm = ReadingArm(document={"properties": {"blob": "x" * 5000}})
    reader = EstateReader(arm=arm, subscription_id=SUBSCRIPTION)  # type: ignore[arg-type]
    result = await reader.properties(STORAGE_ID, bounds=ContentBounds(max_bytes=100))
    assert result.truncated is True
    assert len(result.payload.data) == 100
    assert result.payload.size_bytes > 5000


async def test_properties_without_an_id_is_unconfigured() -> None:
    reader = EstateReader(arm=ReadingArm(), subscription_id=SUBSCRIPTION)  # type: ignore[arg-type]
    result = await reader.properties("")
    assert result.status == "unconfigured"


async def test_search_returns_rows_from_both_queries() -> None:
    arm = FakeArm(graph=[{"id": "a", "name": "hc-one", "type": "t", "matchedIn": "name"}])
    reader = EstateReader(arm=arm, subscription_id=SUBSCRIPTION)  # type: ignore[arg-type]
    result = await reader.search("hc")
    assert result.status == "ok"
    assert result.payload.form == "rows"
    assert result.payload.columns[:2] == ("id", "name")
    assert len(arm.queries) == 2
    assert all("@'hc'" in query for query in arm.queries)


async def test_search_without_a_term_is_unconfigured() -> None:
    reader = EstateReader(arm=FakeArm(), subscription_id=SUBSCRIPTION)  # type: ignore[arg-type]
    assert (await reader.search("   ")).status == "unconfigured"


async def test_search_without_a_subscription_is_unconfigured() -> None:
    reader = EstateReader(arm=FakeArm())  # type: ignore[arg-type]
    assert (await reader.search("hc")).status == "unconfigured"


def test_redact_credentials_stops_at_the_depth_bound() -> None:
    document: Any = {"leaf": "value"}
    for _ in range(40):
        document = {"nest": document}
    assert "(redacted)" in json.dumps(redact_credentials(document))


def test_redact_credentials_leaves_ordinary_values_alone() -> None:
    assert redact_credentials({"location": "eastus", "count": 3}) == {
        "location": "eastus",
        "count": 3,
    }


def test_a_boolean_policy_flag_is_not_a_credential() -> None:
    """``allowSharedKeyAccess`` is the posture, not the key."""
    assert redact_credentials(
        {"allowSharedKeyAccess": False, "keyPolicy": {"keyExpirationPeriodInDays": 7}}
    ) == {"allowSharedKeyAccess": False, "keyPolicy": {"keyExpirationPeriodInDays": 7}}


def test_a_string_under_the_same_key_is_still_redacted() -> None:
    assert redact_credentials({"sharedKey": "abc"}) == {"sharedKey": "(redacted)"}
    assert redact_credentials({"connectionString": ["abc"]}) == {
        "connectionString": "(redacted)"
    }


# -- the bundle ----------------------------------------------------------


def test_build_estate_access_registers_every_browsable_service() -> None:
    access = build_estate_access(AzureDataConfig(subscription_id=SUBSCRIPTION), lambda: None)
    assert set(access.discoverers.services()) == {
        "estate",
        "blob",
        "search",
        "cosmos",
        "gremlin",
        "kusto",
        "logs",
        "acr",
    }


def test_build_estate_access_shares_one_arm_client() -> None:
    access = build_estate_access(AzureDataConfig(subscription_id=SUBSCRIPTION), lambda: None)
    assert access.discoverer("estate").arm is access.arm
    assert access.discoverer("logs").arm is access.arm


def test_build_estate_access_builds_no_credential_and_no_client() -> None:
    calls: list[int] = []
    access = build_estate_access(
        AzureDataConfig(subscription_id=SUBSCRIPTION), lambda: calls.append(1)
    )
    assert calls == []
    assert access.arm._client is None
