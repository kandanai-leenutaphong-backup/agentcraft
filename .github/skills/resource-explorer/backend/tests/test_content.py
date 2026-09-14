"""Contents: what a node says, and how a byte string is typed.

The typing rules are tested directly, because they decide what a browser
renders and getting one wrong is silently ugly rather than loudly broken.
The end-to-end reads are tested by walking to the node first, so a content
route that answers for a node the tree cannot produce would not pass here.
"""

from __future__ import annotations

import base64
import json

import pytest
from conftest import (
    COSMOS_TYPE,
    GROUP,
    KUSTO_TYPE,
    LOCKED_GROUP,
    LOGS_TYPE,
    SEARCH_TYPE,
    STORAGE,
    STORAGE_TYPE,
    children,
    make_service,
    resource_node,
)

from resource_explorer_api.content import hex_preview, type_content
from resource_explorer_api.fixtures import DEMO_CONTAINER, DEPTH_MARKER, PRIMARY_INDEX
from resource_explorer_api.tree import PROPERTIES_LABEL


@pytest.fixture
def service():
    return make_service()


async def demo_blobs(service) -> dict:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    facets = await children(service, account.id)
    containers = await children(service, facets["Blob containers"].id)
    return await children(service, containers[DEMO_CONTAINER].id)


# -- typing rules --------------------------------------------------------


def test_a_claimed_type_settles_it() -> None:
    typed = type_content(b"# Title\n", media_type="text/markdown", name="x")
    assert typed.content_kind == "markdown"
    assert typed.text == "# Title\n"


def test_json_is_pretty_printed_not_echoed() -> None:
    typed = type_content(b'{"b":1,"a":[2]}', media_type="application/json", name="x.json")
    assert typed.content_kind == "json"
    assert "\n" in (typed.text or "")
    assert json.loads(typed.text or "") == {"b": 1, "a": [2]}


def test_an_uninformative_claim_falls_back_to_the_name() -> None:
    typed = type_content(
        b"day,count\n1,2\n", media_type="application/octet-stream", name="metrics.csv"
    )
    assert typed.content_kind == "csv"
    assert typed.media_type == "text/csv"


def test_an_uninformative_claim_and_no_name_falls_back_to_the_bytes() -> None:
    typed = type_content(b'{"a": 1}', media_type="", name="")
    assert typed.content_kind == "json"


def test_a_png_magic_number_wins_over_a_missing_header() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    typed = type_content(png, media_type="application/octet-stream", name="mystery")
    assert typed.content_kind == "image"
    assert typed.media_type == "image/png"
    assert base64.b64decode(typed.data_base64 or "") == png
    assert typed.text is None


def test_svg_is_never_returned_as_an_image() -> None:
    """It is a script-bearing document; rendering one would be stored XSS."""
    typed = type_content(b"<svg onload='x()'/>", media_type="image/svg+xml", name="a.svg")
    assert typed.content_kind != "image"


def test_binary_returns_a_preview_and_the_bytes() -> None:
    data = bytes(range(256))
    typed = type_content(data, media_type="application/octet-stream", name="x.bin")
    assert typed.content_kind == "binary"
    assert (typed.text or "").startswith("00000000  00 01 02")
    assert base64.b64decode(typed.data_base64 or "") == data


def test_a_file_claiming_text_that_is_not_decodable_becomes_binary() -> None:
    typed = type_content(b"\xff\xfe\x00\x01", media_type="text/plain", name="a.txt")
    assert typed.content_kind == "binary"


def test_truncated_json_degrades_to_text_rather_than_failing() -> None:
    typed = type_content(b'{"a": 1', media_type="application/json", name="a.json")
    assert typed.content_kind == "text"
    assert typed.text == '{"a": 1'


def test_a_hex_preview_is_capped_and_says_how_much_was_dropped() -> None:
    preview = hex_preview(b"\x00" * 1024, limit=32)
    assert preview.endswith("992 more bytes")


def test_text_is_capped() -> None:
    from resource_explorer_api.settings import MAX_TEXT_CHARS

    typed = type_content(b"a" * (MAX_TEXT_CHARS + 100), media_type="text/plain", name="a.txt")
    assert len(typed.text or "") == MAX_TEXT_CHARS
    assert (typed.text or "").endswith("…")


# -- reads through the tree ----------------------------------------------


async def test_a_nested_blob_returns_its_text(service) -> None:
    top = await demo_blobs(service)
    nested = await children(service, top["nested"].id)
    deep = await children(service, nested["deep"].id)
    body = await service.read_content(deep["file.txt"].id)
    assert body.status == "ok"
    assert body.content_kind == "text"
    assert (body.text or "").startswith("Depth marker:")
    assert body.size_bytes == len(DEPTH_MARKER.encode("utf-8"))
    assert body.breadcrumb[-1] == "file.txt"


async def test_an_image_blob_returns_viewable_bytes(service) -> None:
    top = await demo_blobs(service)
    body = await service.read_content(top["diagram.png"].id)
    assert body.content_kind == "image"
    assert body.media_type == "image/png"
    assert base64.b64decode(body.data_base64 or "").startswith(b"\x89PNG")
    assert body.text is None


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("README.md", "markdown"),
        ("config.json", "json"),
        ("metrics.csv", "csv"),
        ("notes.txt", "text"),
        ("payload.bin", "binary"),
    ],
)
async def test_each_blob_is_typed_for_rendering(service, name, kind) -> None:
    top = await demo_blobs(service)
    body = await service.read_content(top[name].id)
    assert body.status == "ok"
    assert body.content_kind == kind


async def test_a_capped_read_reports_the_true_size(service) -> None:
    narrow = make_service(max_content_bytes=8)
    top = await demo_blobs(narrow)
    body = await narrow.read_content(top["notes.txt"].id)
    assert body.truncated is True
    assert body.size_bytes > 8


async def test_arm_properties_are_the_universal_content(service) -> None:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    facets = await children(service, account.id)
    body = await service.read_content(facets[PROPERTIES_LABEL].id)
    assert body.status == "ok"
    assert body.content_kind == "json"
    document = json.loads(body.text or "{}")
    assert document["name"] == STORAGE
    assert document["properties"]["primaryKey"] == "(redacted)"


async def test_cosmos_documents_come_back_as_rows(service) -> None:
    account = await resource_node(service, GROUP, COSMOS_TYPE, "cosmos-fixture")
    facets = await children(service, account.id)
    databases = await children(service, facets["SQL databases"].id)
    containers = await children(service, databases["hcdb"].id)
    body = await service.read_content(containers["items"].id)
    assert body.content_kind == "rows"
    assert body.columns == ["id", "name", "tags"]
    assert len(body.rows or []) == 2


async def test_a_gremlin_graph_reads_as_documents(service) -> None:
    account = await resource_node(service, GROUP, COSMOS_TYPE, "cosmos-fixture")
    facets = await children(service, account.id)
    databases = await children(service, facets["Gremlin databases"].id)
    graphs = await children(service, databases["graphdb"].id)
    body = await service.read_content(graphs["people"].id)
    assert body.status == "ok"
    assert body.content_kind == "rows"


async def test_an_empty_container_reads_empty_not_broken(service) -> None:
    account = await resource_node(service, GROUP, COSMOS_TYPE, "cosmos-fixture")
    facets = await children(service, account.id)
    databases = await children(service, facets["SQL databases"].id)
    containers = await children(service, databases["hcdb"].id)
    body = await service.read_content(containers["empty-container"].id)
    assert body.status == "empty"
    assert body.error is None


async def test_kusto_rows_carry_the_declared_columns(service) -> None:
    cluster = await resource_node(service, GROUP, KUSTO_TYPE, "adx-fixture")
    facets = await children(service, cluster.id)
    databases = await children(service, facets["Databases"].id)
    tables = await children(service, databases["telemetry"].id)
    body = await service.read_content(tables["Events"].id)
    assert body.content_kind == "rows"
    assert body.columns == ["Timestamp", "Level", "Message"]


async def test_search_documents_come_back_as_rows(service) -> None:
    node = await resource_node(service, GROUP, SEARCH_TYPE, "srch-fixture")
    facets = await children(service, node.id)
    indexes = await children(service, facets["Indexes"].id)
    body = await service.read_content(indexes[PRIMARY_INDEX].id)
    assert body.content_kind == "rows"
    assert "@search.score" in (body.columns or [])


async def test_log_rows_come_back_as_rows(service) -> None:
    node = await resource_node(service, GROUP, LOGS_TYPE, "log-fixture")
    facets = await children(service, node.id)
    tables = await children(service, facets["Log tables"].id)
    body = await service.read_content(tables["AppTraces"].id)
    assert body.content_kind == "rows"


async def test_a_node_without_contents_answers_none(service) -> None:
    account = await resource_node(service, GROUP, STORAGE_TYPE, STORAGE)
    body = await service.read_content(account.id)
    assert body.status == "empty"
    assert body.content_kind == "none"
    assert body.text is None and body.rows is None and body.data_base64 is None


async def test_a_network_blocked_blob_read_is_a_status_not_an_exception(service) -> None:
    from resource_explorer_api.nodes import NodeRef, encode_node

    account = await resource_node(service, LOCKED_GROUP, STORAGE_TYPE, "stlockedfixture")
    blob = encode_node(
        NodeRef("blob", "blob", (decode(account), DEMO_CONTAINER, "README.md"), "blob")
    )
    body = await service.read_content(blob)
    assert body.status == "unreachable"
    assert "public network access" in (body.error or "")


async def test_arm_properties_survive_a_network_blocked_data_plane(service) -> None:
    """The management plane is a different reachability question entirely."""
    account = await resource_node(service, LOCKED_GROUP, STORAGE_TYPE, "stlockedfixture")
    facets = await children(service, account.id)
    body = await service.read_content(facets[PROPERTIES_LABEL].id)
    assert body.status == "ok"
    assert body.content_kind == "json"


def decode(node) -> str:
    from resource_explorer_api.nodes import decode_node

    return decode_node(node.id).path[0]


async def test_the_root_has_no_contents(service) -> None:
    from resource_explorer_api.nodes import InvalidNode

    with pytest.raises(InvalidNode):
        await service.read_content(None)
