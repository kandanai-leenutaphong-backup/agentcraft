"""The node codec: round-trip, opacity, and every rejection the contract lists.

A node id is the one value a client sends back. Every row of the rejection
table in ``CONTRACT.md`` is a test here, because the codec is what stands
between a crafted string and a discovery call.
"""

from __future__ import annotations

import base64
import json

import pytest

from resource_explorer_api.nodes import (
    CONTENT_BY_KIND,
    KINDS_BY_COORDINATE,
    LEAF_KINDS,
    LEVELS_BY_SERVICE,
    MAX_PATH_SEGMENT_CHARS,
    MAX_PATH_SEGMENTS,
    MAX_TOKEN_CHARS,
    NODE_KINDS,
    InvalidNode,
    NodeRef,
    ROOT_ID,
    decode_node,
    encode_node,
    is_root,
    token_digest,
)

RESOURCE_ID = (
    "/subscriptions/fixture-subscription/resourceGroups/rg-fixture"
    "/providers/Microsoft.Storage/storageAccounts/hcfixturestore"
)


def token(**payload: object) -> str:
    body = {"v": 1, "s": "estate", "l": "resource", "p": [RESOURCE_ID], "k": "resource"}
    body.update(payload)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# -- round trip ----------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    [
        NodeRef("estate", "resource_group", ("rg-fixture",), "resource_group"),
        NodeRef("estate", "type", ("rg-a", "Microsoft.Storage/storageAccounts"), "resource_type"),
        NodeRef("estate", "resource", (RESOURCE_ID,), "resource"),
        NodeRef("estate", "properties", (RESOURCE_ID,), "properties"),
        NodeRef("estate", "collection", (RESOURCE_ID, "blobServices/default/containers"), "collection"),
        NodeRef("estate", "child", (RESOURCE_ID + "/revisions/rev1",), "arm_child"),
        NodeRef("blob", "container", (RESOURCE_ID, "assets/v1: beta", "nested/deep/"), "blob_folder"),
        NodeRef("blob", "blob", (RESOURCE_ID, "demo", "nested/deep/file.txt"), "blob"),
        NodeRef("search", "index", (RESOURCE_ID, "assets/v1: beta"), "search_index"),
        NodeRef("kusto", "table", (RESOURCE_ID, "db", "Events"), "kusto_table"),
        NodeRef("acr", "tag", (RESOURCE_ID, "explorer/api", "v1"), "registry_tag"),
    ],
)
def test_a_ref_round_trips_through_its_token(ref: NodeRef) -> None:
    assert decode_node(encode_node(ref)) == ref


def test_a_token_is_query_safe_and_stable() -> None:
    ref = NodeRef("search", "index", (RESOURCE_ID, "assets/v1: beta"), "search_index")
    first = encode_node(ref)
    assert first == encode_node(ref)
    assert set(first) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )


def test_unicode_and_delimiters_survive() -> None:
    ref = NodeRef("blob", "blob", (RESOURCE_ID, "c", "ünïcode/名前: 1.txt"), "blob")
    assert decode_node(encode_node(ref)).path[2] == "ünïcode/名前: 1.txt"


@pytest.mark.parametrize("value", [None, "", ROOT_ID])
def test_the_root_is_the_only_literal_id(value: str | None) -> None:
    assert is_root(value) is True


def test_a_token_is_not_the_root() -> None:
    assert is_root(encode_node(NodeRef("estate", "resource", (RESOURCE_ID,), "resource"))) is False


# -- rejection table -----------------------------------------------------


def test_a_token_over_the_length_cap_is_refused_before_decoding() -> None:
    with pytest.raises(InvalidNode):
        decode_node("a" * (MAX_TOKEN_CHARS + 1))


@pytest.mark.parametrize("bad", ["not base64!", "abc$", "a b", "café", "=="])
def test_a_token_outside_the_alphabet_is_refused(bad: str) -> None:
    with pytest.raises(InvalidNode):
        decode_node(bad)


def test_undecodable_bytes_are_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(base64.urlsafe_b64encode(b"\xff\xfe\xfd").decode().rstrip("="))


def test_a_payload_that_is_not_an_object_is_refused() -> None:
    raw = base64.urlsafe_b64encode(b"[1,2,3]").decode().rstrip("=")
    with pytest.raises(InvalidNode):
        decode_node(raw)


@pytest.mark.parametrize("version", [None, 0, 2, "1"])
def test_a_wrong_version_is_refused(version: object) -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(v=version))


def test_an_unknown_service_is_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(s="mystery"))


def test_a_level_the_service_does_not_declare_is_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(l="index"))


def test_the_root_level_of_the_estate_is_not_addressable() -> None:
    """``estate/subscription`` is expanded only by the literal root id."""
    assert "subscription" not in LEVELS_BY_SERVICE["estate"]
    with pytest.raises(InvalidNode):
        decode_node(token(l="subscription", k="resource_group"))


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(k="mystery"))


def test_a_kind_inconsistent_with_its_coordinate_is_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(k="blob"))


@pytest.mark.parametrize("path", ["not-a-list", [1, 2], [{"a": 1}]])
def test_a_path_that_is_not_a_list_of_strings_is_refused(path: object) -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(p=path))


def test_a_path_deeper_than_the_cap_is_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(p=["x"] * (MAX_PATH_SEGMENTS + 1)))


def test_a_path_segment_over_the_cap_is_refused() -> None:
    with pytest.raises(InvalidNode):
        decode_node(token(p=["x" * (MAX_PATH_SEGMENT_CHARS + 1)]))


def test_a_segment_at_exactly_the_cap_is_accepted() -> None:
    assert decode_node(token(p=["x" * MAX_PATH_SEGMENT_CHARS])).path[0].startswith("x")


# -- the vocabulary itself -----------------------------------------------


def test_every_declared_coordinate_names_only_declared_kinds() -> None:
    for (service, level), kinds in KINDS_BY_COORDINATE.items():
        assert service in LEVELS_BY_SERVICE, service
        assert level in LEVELS_BY_SERVICE[service], (service, level)
        assert kinds <= set(NODE_KINDS), kinds - set(NODE_KINDS)


def test_every_declared_level_has_at_least_one_kind() -> None:
    missing = [
        (service, level)
        for service, levels in LEVELS_BY_SERVICE.items()
        for level in levels
        if not KINDS_BY_COORDINATE.get((service, level))
    ]
    assert missing == []


def test_every_leaf_and_content_kind_is_a_declared_kind() -> None:
    assert LEAF_KINDS <= set(NODE_KINDS)
    assert set(CONTENT_BY_KIND) <= set(NODE_KINDS)


def test_a_leaf_is_a_leaf_and_may_still_have_contents() -> None:
    table = NodeRef("kusto", "table", (RESOURCE_ID, "db", "Events"), "kusto_table")
    assert table.is_leaf is True
    assert table.content == ("kusto", "rows")


def test_an_index_has_children_and_contents_at_once() -> None:
    index = NodeRef("search", "index", (RESOURCE_ID, "azdata-assets"), "search_index")
    assert index.is_leaf is False
    assert index.content == ("search", "documents")


def test_a_structural_node_has_no_contents() -> None:
    assert NodeRef("estate", "resource", (RESOURCE_ID,), "resource").content is None


# -- logging -------------------------------------------------------------


def test_a_digest_is_short_stable_and_not_the_token() -> None:
    value = token()
    digest = token_digest(value)
    assert len(digest) == 12
    assert digest == token_digest(value)
    assert digest not in value
