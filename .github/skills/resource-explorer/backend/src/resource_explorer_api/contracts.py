"""The wire shape. One authority, mirrored in ``contracts/tree.schema.json``.

WHY ``status`` APPEARS TWICE
----------------------------
The response's ``status`` describes *this expansion*. A child's ``status``
describes only what is already known about that child — a child is never
speculatively probed, so a successfully discovered child is ``ok`` even when
expanding it would fail. Collapsing the two would make a reachable branch of
unreachable children indistinguishable from an unreachable branch.

WHY THE SIX STATUSES SURVIVE TO THE BROWSER
-------------------------------------------
They are the operator's whole diagnosis. ``forbidden`` is fixed by a role
grant; ``unreachable`` is a network or private-DNS path and a role grant does
nothing for it; ``unavailable`` is the service saying no or an SDK missing;
``unconfigured`` is a coordinate nobody set; ``empty`` is a true answer.
``truncated`` is a boolean beside them rather than a seventh status, because
a truncated listing did succeed. Rendering any of them as "no items" throws
the diagnosis away.

WHY ``hasContent`` IS A SEPARATE FLAG FROM ``expandable``
---------------------------------------------------------
Having nothing below you and having nothing to say are different facts. A
Kusto table has no children and a page of rows; a Search index has both
fields and documents. One boolean could express neither.

``fixtures`` is mandatory on every response. Numbers from nowhere presented
as real is exactly the failure a fixture mode exists to avoid.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = 1

NodeStatus = Literal[
    "ok", "empty", "forbidden", "unreachable", "unconfigured", "unavailable"
]

NodeKind = Literal[
    "root",
    "resource_group",
    "resource_type",
    "resource",
    "collection",
    "arm_child",
    "properties",
    "blob_container",
    "blob_folder",
    "blob",
    "cosmos_database",
    "cosmos_container",
    "gremlin_database",
    "gremlin_graph",
    "kusto_database",
    "kusto_table",
    "search_index",
    "search_field",
    "log_table",
    "registry_repository",
    "registry_tag",
]

#: How the bytes or rows behind a node should be rendered. Decided by this
#: component from the media type the service claimed plus a sniff of the
#: bytes; ``azdata`` reports what the service said and never interprets it.
ContentKind = Literal[
    "none", "text", "json", "csv", "markdown", "image", "binary", "rows"
]

DetailValue = str | int | float | bool | None


class Wire(BaseModel):
    """JSON keys are camelCase; Python attributes are snake_case."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class TreeNode(Wire):
    """One child. ``id`` is opaque and only this server can mint it."""

    id: str
    label: str
    kind: NodeKind
    expandable: bool
    has_content: bool = False
    status: NodeStatus
    detail: dict[str, DetailValue] | None = None
    error: str | None = None


class TreeResponse(Wire):
    """One expansion's outcome, whatever happened."""

    schema_version: Literal[1] = SCHEMA_VERSION
    fixtures: bool
    node: str
    label: str
    kind: NodeKind
    breadcrumb: list[str]
    status: NodeStatus
    children: list[TreeNode]
    truncated: bool
    has_content: bool = False
    detail: dict[str, DetailValue] | None = None
    error: str | None = None
    observed_at: str


class ContentResponse(Wire):
    """One node's contents: text, an image, raw bytes, or rows.

    Exactly one of ``text``, ``dataBase64`` and ``rows`` carries the payload,
    named by ``contentKind``. ``sizeBytes`` is the size of the *underlying*
    object, so a truncated read can say "64 KiB of 4 GiB" rather than implying
    the file is small.
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    fixtures: bool
    node: str
    label: str
    kind: NodeKind
    breadcrumb: list[str]
    status: NodeStatus
    content_kind: ContentKind
    media_type: str
    text: str | None = None
    data_base64: str | None = None
    rows: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    size_bytes: int = 0
    truncated: bool = False
    detail: dict[str, DetailValue] | None = None
    error: str | None = None
    observed_at: str


class SearchHit(Wire):
    """One estate-wide match, addressable by the node id it carries."""

    node: str
    label: str
    kind: NodeKind
    resource_group: str = ""
    type: str = ""
    location: str = ""
    matched_in: str = ""
    detail: dict[str, DetailValue] | None = None


class SearchResponse(Wire):
    """One estate-wide query's outcome. A failure is still a 200."""

    schema_version: Literal[1] = SCHEMA_VERSION
    fixtures: bool
    query: str
    status: NodeStatus
    hits: list[SearchHit]
    truncated: bool
    error: str | None = None
    observed_at: str


class InvalidNodeError(Wire):
    """The only body a 400 carries. It echoes nothing that was submitted."""

    error: Literal["invalid_node"] = "invalid_node"
    schema_version: Literal[1] = SCHEMA_VERSION


class InvalidQueryError(Wire):
    """A search term outside the accepted bounds. It echoes nothing either."""

    error: Literal["invalid_query"] = "invalid_query"
    schema_version: Literal[1] = SCHEMA_VERSION


class LiveHealth(Wire):
    status: Literal["live"] = "live"


class ReadyHealth(Wire):
    status: Literal["ready"] = "ready"


__all__ = [
    "SCHEMA_VERSION",
    "ContentKind",
    "ContentResponse",
    "DetailValue",
    "InvalidNodeError",
    "InvalidQueryError",
    "LiveHealth",
    "NodeKind",
    "NodeStatus",
    "ReadyHealth",
    "SearchHit",
    "SearchResponse",
    "TreeNode",
    "TreeResponse",
    "Wire",
]
