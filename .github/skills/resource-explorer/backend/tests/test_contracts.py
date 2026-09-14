"""The pydantic models and ``contracts/tree.schema.json`` agree.

Both directions, because either alone is half a contract: every payload the
server produces must validate, and every field either side declares must
exist on the other. A schema nobody's payload can violate is decoration, so
each mutation below is asserted to be rejected.
"""

from __future__ import annotations

import json

import pytest
from conftest import (
    GROUP,
    LOCKED_GROUP,
    PRINCIPAL,
    SCHEMA_PATH,
    STORAGE,
    STORAGE_TYPE,
    client,
    make_settings,
)
from jsonschema import Draft202012Validator

from resource_explorer_api.app import create_app
from resource_explorer_api.contracts import (
    ContentResponse,
    SearchHit,
    SearchResponse,
    TreeNode,
    TreeResponse,
)
from resource_explorer_api.fixtures import DEMO_CONTAINER
from resource_explorer_api.nodes import NODE_KINDS
from resource_explorer_api.tree import PROPERTIES_LABEL


@pytest.fixture
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def definition(name: str) -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"][name]


async def get(path: str, **params: object) -> dict:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get(path, params=params, headers=PRINCIPAL)
    assert response.status_code == 200, response.text
    return response.json()


def find(body: dict, label: str) -> dict:
    for entry in body["children"]:
        if entry["label"] == label or entry["label"].startswith(f"{label} ("):
            return entry
    raise AssertionError(f"no child {label!r} in {[c['label'] for c in body['children']]}")


async def blob_node(name: str) -> dict:
    root = await get("/api/tree")
    group = await get("/api/tree", node=find(root, GROUP)["id"])
    types = await get("/api/tree", node=find(group, STORAGE_TYPE)["id"])
    account = await get("/api/tree", node=find(types, STORAGE)["id"])
    containers = await get("/api/tree", node=find(account, "Blob containers")["id"])
    listing = await get("/api/tree", node=find(containers, DEMO_CONTAINER)["id"])
    return find(listing, name)


# -- every payload validates ---------------------------------------------


async def test_the_root_payload_validates(validator) -> None:
    errors = sorted(validator.iter_errors(await get("/api/tree")), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


async def test_a_deep_payload_validates(validator) -> None:
    root = await get("/api/tree")
    group = await get("/api/tree", node=find(root, GROUP)["id"])
    types = await get("/api/tree", node=find(group, STORAGE_TYPE)["id"])
    account = await get("/api/tree", node=find(types, STORAGE)["id"])
    assert not list(validator.iter_errors(account))


async def test_a_dark_branch_payload_validates(validator) -> None:
    root = await get("/api/tree")
    group = await get("/api/tree", node=find(root, LOCKED_GROUP)["id"])
    types = await get("/api/tree", node=find(group, STORAGE_TYPE)["id"])
    account = await get("/api/tree", node=find(types, "stlockedfixture")["id"])
    body = await get("/api/tree", node=find(account, "Blob containers")["id"])
    assert body["status"] == "unreachable"
    assert not list(validator.iter_errors(body))


async def test_every_content_rendering_validates(validator) -> None:
    for name in ("README.md", "config.json", "metrics.csv", "diagram.png", "payload.bin"):
        node = await blob_node(name)
        body = await get("/api/content", node=node["id"])
        errors = list(validator.iter_errors(body))
        assert not errors, f"{name}: " + "; ".join(e.message for e in errors)


async def test_a_rows_payload_validates(validator) -> None:
    root = await get("/api/tree")
    group = await get("/api/tree", node=find(root, GROUP)["id"])
    types = await get("/api/tree", node=find(group, "Microsoft.Kusto/clusters")["id"])
    cluster = await get("/api/tree", node=find(types, "adx-fixture")["id"])
    databases = await get("/api/tree", node=find(cluster, "Databases")["id"])
    tables = await get("/api/tree", node=find(databases, "telemetry")["id"])
    body = await get("/api/content", node=find(tables, "Events")["id"])
    assert body["contentKind"] == "rows"
    assert not list(validator.iter_errors(body))


async def test_a_properties_payload_validates(validator) -> None:
    root = await get("/api/tree")
    group = await get("/api/tree", node=find(root, GROUP)["id"])
    types = await get("/api/tree", node=find(group, STORAGE_TYPE)["id"])
    account = await get("/api/tree", node=find(types, STORAGE)["id"])
    body = await get("/api/content", node=find(account, PROPERTIES_LABEL)["id"])
    assert not list(validator.iter_errors(body))


async def test_a_search_payload_validates(validator) -> None:
    body = await get("/api/search", q="fixture")
    assert not list(validator.iter_errors(body))


async def test_the_rejection_bodies_validate(validator) -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        node = await http.get("/api/tree", params={"node": "!!"}, headers=PRINCIPAL)
        query = await http.get("/api/search", params={"q": ""}, headers=PRINCIPAL)
    assert node.status_code == 400 and query.status_code == 400
    assert not list(validator.iter_errors(node.json()))
    assert not list(validator.iter_errors(query.json()))


# -- both directions ------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (TreeResponse, "treeResponse"),
        (TreeNode, "treeNode"),
        (ContentResponse, "contentResponse"),
        (SearchResponse, "searchResponse"),
        (SearchHit, "searchHit"),
    ],
)
def test_the_model_and_the_schema_declare_the_same_fields(model, name) -> None:
    declared = set(definition(name)["properties"])
    fields = {
        (field.alias or key)
        for key, field in model.model_fields.items()
    }
    assert fields == declared, f"model {sorted(fields - declared)} schema {sorted(declared - fields)}"


def test_the_schema_lists_every_node_kind() -> None:
    assert definition("nodeKind")["enum"] == list(NODE_KINDS)


def test_the_schema_lists_every_status_the_planes_can_return() -> None:
    from azdata import DISCOVERY_STATUSES

    assert set(definition("nodeStatus")["enum"]) == set(DISCOVERY_STATUSES)


def test_the_schema_lists_every_content_kind() -> None:
    from resource_explorer_api.contracts import ContentKind

    assert set(definition("contentKind")["enum"]) == set(ContentKind.__args__)


# -- the schema is discriminating -----------------------------------------


@pytest.mark.parametrize(
    "mutation",
    [
        {"status": "sideways"},
        {"kind": "not_a_kind"},
        {"schemaVersion": 2},
        {"observedAt": "yesterday"},
        {"children": "not-a-list"},
        {"surprise": True},
    ],
)
async def test_a_mutated_tree_payload_is_rejected(validator, mutation) -> None:
    body = await get("/api/tree")
    body.update(mutation)
    assert list(validator.iter_errors(body)), f"{mutation} slipped through"


@pytest.mark.parametrize(
    "mutation",
    [{"contentKind": "hologram"}, {"sizeBytes": -1}, {"rows": 3}, {"surprise": 1}],
)
async def test_a_mutated_content_payload_is_rejected(validator, mutation) -> None:
    node = await blob_node("README.md")
    body = await get("/api/content", node=node["id"])
    body.update(mutation)
    assert list(validator.iter_errors(body)), f"{mutation} slipped through"


async def test_a_mutated_search_payload_is_rejected(validator) -> None:
    body = await get("/api/search", q="fixture")
    body["hits"][0].pop("node")
    assert list(validator.iter_errors(body))
