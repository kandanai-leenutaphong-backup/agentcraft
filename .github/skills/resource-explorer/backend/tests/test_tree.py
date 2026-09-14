"""Hierarchy composition against the fixture subscription.

Every node kind the contract declares is reached here by expansion from the
root, the way a user reaches it — not by minting a token in the test. A kind
that cannot be reached by walking is not in the tree, whatever the enum says.
"""

from __future__ import annotations

import pytest
from conftest import (
    ACR_TYPE,
    APP_TYPE,
    COSMOS_TYPE,
    EMPTY_GROUP,
    GROUP,
    IDENTITY_TYPE,
    KUSTO_TYPE,
    LOCKED_GROUP,
    LOGS_TYPE,
    SEARCH_TYPE,
    STORAGE,
    STORAGE_TYPE,
    VAULT_TYPE,
    children,
    make_service,
    resource_node,
)

from resource_explorer_api.fixtures import (
    AWKWARD_INDEX,
    DEMO_CONTAINER,
    EMPTY_INDEX,
    LARGE_INDEX,
    PRIMARY_INDEX,
)
from resource_explorer_api.nodes import NODE_KINDS, NodeRef, decode_node, encode_node
from resource_explorer_api.tree import PROPERTIES_LABEL, ROOT_LABEL, ExplorerService


@pytest.fixture
def service() -> ExplorerService:
    return make_service()


# -- the spine -----------------------------------------------------------


async def test_the_root_is_the_subscription_and_lists_every_group(service) -> None:
    response = await service.expand(None)
    assert response.kind == "root"
    assert response.status == "ok"
    assert response.breadcrumb == [ROOT_LABEL]
    assert {child.label for child in response.children} == {GROUP, LOCKED_GROUP, EMPTY_GROUP}
    assert all(child.kind == "resource_group" for child in response.children)
    assert response.fixtures is True


async def test_a_configured_resource_group_narrows_the_root() -> None:
    scoped = make_service(
        azure=type(make_service()._settings.azure)(
            subscription_id="fixture-subscription", resource_group=GROUP
        )
    )
    response = await scoped.expand(None)
    assert [child.label for child in response.children] == [GROUP]


async def test_an_unconfigured_root_names_the_variable_it_needs() -> None:
    from azdata import AzureDataConfig

    bare = make_service(fake_discovery=False, azure=AzureDataConfig())
    response = await bare.expand(None)
    assert response.status == "unconfigured"
    assert "AZDATA_SUBSCRIPTION_ID" in (response.error or "")
    assert response.fixtures is False


async def test_a_group_groups_its_resources_by_type_with_counts(service) -> None:
    groups = await children(service, None)
    types = await children(service, groups[GROUP].id)
    assert f"{COSMOS_TYPE} (2)" in types
    assert f"{STORAGE_TYPE} (1)" in types
    assert all(child.kind == "resource_type" for child in types.values())
    assert sorted(types) == list(types), "type groups render in a stable order"


async def test_a_type_group_lists_only_its_own_resources(service) -> None:
    groups = await children(service, None)
    types = await children(service, groups[GROUP].id)
    listing = await children(service, types[f"{COSMOS_TYPE} (2)"].id)
    assert set(listing) == {"cosmos-fixture", "cosmos-forbidden"}
    assert all(child.kind == "resource" for child in listing.values())


async def test_an_empty_group_is_empty_and_not_an_error(service) -> None:
    groups = await children(service, None)
    response = await service.expand(groups[EMPTY_GROUP].id)
    assert response.status == "empty"
    assert response.children == []
    assert response.error is None


async def test_the_group_listing_is_fetched_once_per_group(service) -> None:
    groups = await children(service, None)
    estate = service._access.discoverers.get("estate")
    before = len(estate.calls)
    types = await children(service, groups[GROUP].id)
    for label in list(types)[:3]:
        await service.expand(types[label].id)
    calls = [call for call in estate.calls[before:] if call[0] == "resource_group"]
    assert len(calls) == 1, "one listing serves the group and its type groups"


# -- the universal leaf ---------------------------------------------------


@pytest.mark.parametrize(
    ("resource_type", "name"),
    [
        (IDENTITY_TYPE, "id-fixture"),
        (STORAGE_TYPE, STORAGE),
        (APP_TYPE, "app-fixture"),
    ],
)
async def test_every_resource_opens_into_its_arm_properties(service, resource_type, name) -> None:
    node = await resource_node(service, GROUP, resource_type, name)
    listing = await children(service, node.id)
    assert PROPERTIES_LABEL in listing
    leaf = listing[PROPERTIES_LABEL]
    assert leaf.kind == "properties"
    assert leaf.expandable is False
    assert leaf.has_content is True


async def test_a_type_with_no_data_plane_has_only_the_universal_leaf(service) -> None:
    node = await resource_node(service, GROUP, IDENTITY_TYPE, "id-fixture")
    listing = await children(service, node.id)
    assert list(listing) == [PROPERTIES_LABEL]


async def test_expanding_a_leaf_is_empty_and_costs_no_call(service) -> None:
    node = await resource_node(service, GROUP, IDENTITY_TYPE, "id-fixture")
    listing = await children(service, node.id)
    estate = service._access.discoverers.get("estate")
    before = len(estate.calls)
    response = await service.expand(listing[PROPERTIES_LABEL].id)
    assert response.status == "empty"
    assert response.children == []
    assert len(estate.calls) == before


# -- blob: prefix-to-tree synthesis ---------------------------------------


async def test_a_storage_account_lists_its_containers(service) -> None:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    facets = await children(service, account.id)
    containers = await children(service, facets["Blob containers"].id)
    assert set(containers) == {DEMO_CONTAINER, AWKWARD_INDEX}
    assert all(child.kind == "blob_container" for child in containers.values())


async def test_a_flat_blob_name_renders_as_folders(service) -> None:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    facets = await children(service, account.id)
    containers = await children(service, facets["Blob containers"].id)
    top = await children(service, containers[DEMO_CONTAINER].id)
    assert top["nested"].kind == "blob_folder"
    assert top["nested"].expandable is True
    assert top["README.md"].kind == "blob"
    assert top["README.md"].expandable is False
    assert "nested/deep/file.txt" not in top, "a nested blob is not a top-level child"

    nested = await children(service, top["nested"].id)
    assert set(nested) == {"deep"}
    deep = await children(service, nested["deep"].id)
    assert set(deep) == {"file.txt", "manifest.json"}
    assert all(child.has_content for child in deep.values())


async def test_a_blob_node_carries_the_whole_flat_name(service) -> None:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    facets = await children(service, account.id)
    containers = await children(service, facets["Blob containers"].id)
    top = await children(service, containers[DEMO_CONTAINER].id)
    nested = await children(service, top["nested"].id)
    deep = await children(service, nested["deep"].id)
    ref = decode_node(deep["file.txt"].id)
    assert ref.path[1:] == (DEMO_CONTAINER, "nested/deep/file.txt")


async def test_a_blob_breadcrumb_shows_the_folders(service) -> None:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    facets = await children(service, account.id)
    containers = await children(service, facets["Blob containers"].id)
    top = await children(service, containers[DEMO_CONTAINER].id)
    nested = await children(service, top["nested"].id)
    response = await service.expand(nested["deep"].id)
    assert response.breadcrumb == [
        ROOT_LABEL,
        GROUP,
        STORAGE,
        "Blob containers",
        DEMO_CONTAINER,
        "nested",
        "deep",
    ]


async def test_an_index_name_with_a_slash_is_not_split_into_folders(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-fixture")
    facets = await children(service, node.id)
    indexes = await children(service, facets["Indexes"].id)
    response = await service.expand(indexes[AWKWARD_INDEX].id)
    assert response.breadcrumb[-1] == AWKWARD_INDEX


# -- the remaining data planes -------------------------------------------


async def test_a_cosmos_account_shows_both_apis(service) -> None:
    node = await resource_node(service, GROUP, COSMOS_TYPE, "cosmos-fixture")
    facets = await children(service, node.id)
    assert "SQL databases" in facets and "Gremlin databases" in facets

    databases = await children(service, facets["SQL databases"].id)
    containers = await children(service, databases["hcdb"].id)
    assert containers["items"].kind == "cosmos_container"
    assert containers["items"].has_content is True

    graphs = await children(service, facets["Gremlin databases"].id)
    people = await children(service, graphs["graphdb"].id)
    assert people["people"].kind == "gremlin_graph"
    assert people["people"].has_content is True


async def test_a_search_index_has_fields_and_contents(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-fixture")
    facets = await children(service, node.id)
    indexes = await children(service, facets["Indexes"].id)
    assert indexes[PRIMARY_INDEX].expandable is True
    assert indexes[PRIMARY_INDEX].has_content is True
    fields = await children(service, indexes[PRIMARY_INDEX].id)
    assert "body/summary" in fields
    assert all(child.kind == "search_field" for child in fields.values())


async def test_a_kusto_cluster_reaches_tables(service) -> None:
    node = await resource_node(service, GROUP, KUSTO_TYPE, "adx-fixture")
    facets = await children(service, node.id)
    databases = await children(service, facets["Databases"].id)
    tables = await children(service, databases["telemetry"].id)
    assert tables["Events"].kind == "kusto_table"
    assert tables["Events"].expandable is False
    assert tables["Events"].has_content is True


async def test_a_workspace_lists_log_tables(service) -> None:
    node = await resource_node(service, GROUP, LOGS_TYPE, "log-fixture")
    facets = await children(service, node.id)
    tables = await children(service, facets["Log tables"].id)
    assert tables["AppTraces"].kind == "log_table"
    assert tables["AppTraces"].has_content is True
    ref = decode_node(tables["AppTraces"].id)
    assert len(ref.path) == 2, "the workspace id appears once, not twice"


async def test_a_registry_reaches_tags(service) -> None:
    node = await resource_node(service, GROUP, ACR_TYPE, "acrfixture")
    facets = await children(service, node.id)
    repositories = await children(service, facets["Repositories"].id)
    tags = await children(service, repositories["explorer/api"].id)
    assert set(tags) == {"latest", "v1"}
    assert all(child.kind == "registry_tag" for child in tags.values())
    ref = decode_node(tags["v1"].id)
    assert len(ref.path) == 3, "the login server appears once, not twice"


# -- generic ARM children -------------------------------------------------


async def test_an_arm_collection_lists_children_that_open_further(service) -> None:
    node = await resource_node(service, GROUP, APP_TYPE, "app-fixture")
    facets = await children(service, node.id)
    revisions = await children(service, facets["Revisions"].id)
    assert set(revisions) == {"app-fixture--rev1", "app-fixture--rev2"}
    assert all(child.kind == "arm_child" for child in revisions.values())

    inner = await children(service, revisions["app-fixture--rev1"].id)
    assert PROPERTIES_LABEL in inner and "Replicas" in inner
    replicas = await children(service, inner["Replicas"].id)
    assert set(replicas) == {"app-fixture--rev1-abc"}


async def test_a_vault_lists_names_and_never_values(service) -> None:
    node = await resource_node(service, GROUP, VAULT_TYPE, "kv-fixture")
    facets = await children(service, node.id)
    assert "Secrets (names only)" in facets
    secrets = await children(service, facets["Secrets (names only)"].id)
    assert set(secrets) == {"storage-connection", "signing-key-name"}
    for child in secrets.values():
        assert child.has_content is False
        assert "value" not in (child.detail or {})


async def test_an_empty_arm_collection_is_empty(service) -> None:
    node = await resource_node(service, GROUP, VAULT_TYPE, "kv-fixture")
    facets = await children(service, node.id)
    response = await service.expand(facets["Keys (names only)"].id)
    assert response.status == "empty"


# -- the degradation vocabulary ------------------------------------------


async def test_a_network_blocked_account_is_unreachable_with_a_cause(service) -> None:
    node = await resource_node(service, LOCKED_GROUP, STORAGE_TYPE, "stlockedfixture")
    facets = await children(service, node.id)
    response = await service.expand(facets["Blob containers"].id)
    assert response.status == "unreachable"
    assert "public network access" in (response.error or "")
    assert response.children == []


async def test_a_denied_account_is_forbidden(service) -> None:
    node = await resource_node(service, GROUP, COSMOS_TYPE, "cosmos-forbidden")
    facets = await children(service, node.id)
    response = await service.expand(facets["SQL databases"].id)
    assert response.status == "forbidden"
    assert "Cosmos DB Account Reader" in (response.error or "")


async def test_a_missing_sdk_is_unavailable(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-broken")
    facets = await children(service, node.id)
    response = await service.expand(facets["Indexes"].id)
    assert response.status == "unavailable"


async def test_a_missing_coordinate_is_unconfigured(service) -> None:
    node = await resource_node(service, GROUP, KUSTO_TYPE, "adx-unconfigured")
    facets = await children(service, node.id)
    response = await service.expand(facets["Databases"].id)
    assert response.status == "unconfigured"


async def test_an_empty_listing_is_empty_not_an_error(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-fixture")
    facets = await children(service, node.id)
    indexes = await children(service, facets["Indexes"].id)
    response = await service.expand(indexes[EMPTY_INDEX].id)
    assert response.status == "empty"
    assert response.error is None


async def test_an_oversized_listing_is_clamped_and_says_so(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-fixture")
    facets = await children(service, node.id)
    indexes = await children(service, facets["Indexes"].id)
    response = await service.expand(indexes[LARGE_INDEX].id)
    assert response.status == "ok"
    assert response.truncated is True
    assert len(response.children) == 500


async def test_a_lower_clamp_is_honoured(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-fixture")
    facets = await children(service, node.id)
    indexes = await children(service, facets["Indexes"].id)
    narrow = make_service(max_children=3)
    response = await narrow.expand(indexes[LARGE_INDEX].id)
    assert len(response.children) == 3
    assert response.truncated is True


async def test_a_slow_expansion_renders_unreachable_rather_than_raising() -> None:
    slow = make_service(request_timeout_secs=0.001, discovery_timeout_secs=0.001)
    response = await slow.expand(
        encode_node(NodeRef("estate", "resource_group", (GROUP,), "resource_group"))
    )
    assert response.status in ("unreachable", "ok")


# -- coverage of the declared vocabulary ---------------------------------


async def test_every_declared_kind_is_reachable_by_walking(service) -> None:
    """A kind in the enum that no expansion produces is a lie in the contract."""
    seen: set[str] = {"root"}
    visited: set[str] = set()
    frontier: list[tuple[str | None, int]] = [(None, 0)]
    budget = 400

    while frontier and budget > 0:
        node_id, depth = frontier.pop(0)
        if depth > 7:
            continue
        budget -= 1
        response = await service.expand(node_id)
        for child in response.children:
            seen.add(child.kind)
            if child.expandable and child.id not in visited:
                visited.add(child.id)
                frontier.append((child.id, depth + 1))

    assert set(NODE_KINDS) - seen == set()
