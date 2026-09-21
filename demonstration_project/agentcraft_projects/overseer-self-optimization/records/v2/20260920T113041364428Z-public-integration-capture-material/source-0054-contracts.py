"""The wire shape of the use-case data inventory. One authority.

ADAPTED from `resource_explorer_api/contracts.py`. See `PROVENANCE.md`.

WHY ``status`` APPEARS TWICE
----------------------------
The response's ``status`` describes *this call*. A child's ``status``
describes only what is already known about that child — a child is never
speculatively probed, so a source discovered from the manifest is ``ok``
even when reading it would fail. Collapsing the two would make a reachable
group of unreachable sources indistinguishable from an unreachable group.

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
source is a leaf with a page of rows; a use case has children and no rows of
its own. One boolean could express neither.

``fixtures`` is mandatory on every response and is ``false`` on every path
this component can currently take. It exists so that a fixture mode, if one
is ever added, cannot be added silently: numbers from nowhere presented as
real is the failure the flag exists to prevent.

WHAT THIS COMPONENT DOES NOT DECLARE
------------------------------------
No use case, source, table, graph or index name appears here or anywhere
else in this component. Those are the composing application's, supplied as a
registry. This module declares only the shapes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = 1

NodeStatus = Literal[
    "ok", "empty", "forbidden", "unreachable", "unconfigured", "unavailable"
]

#: The inventory hierarchy is two levels under a literal root. It is not an
#: Azure estate: nothing here can address a resource the registry does not
#: declare.
NodeKind = Literal["root", "use_case", "source"]

#: What a preview can be. This component reads rows and nothing else — no
#: bytes, no images, no blobs — so the enum names exactly what it produces.
ContentKind = Literal["none", "rows", "json"]

#: How a source is reached. Descriptive, and the discriminator the service
#: uses to pick a reader.
SourceType = Literal["adx_table", "cosmos_container", "gremlin_graph", "search_index", "local_table"]

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
    #: Stable identifiers, never derived from the label. Name matching is how
    #: a source ends up filed under the wrong use case.
    use_case_id: str = ""
    source_id: str = ""
    source_type: SourceType | None = None
    #: Human-readable classification, rendered as chips. Derived from the
    #: identifiers above, never the reverse.
    tags: list[str] = []
    #: Whether this browser session has this source switched on. ``None`` on
    #: anything that is not a source.
    enabled: bool | None = None
    #: True when the registry has every coordinate this source needs.
    configured: bool = True
    detail: dict[str, DetailValue] | None = None
    error: str | None = None


class TreeResponse(Wire):
    """One expansion's outcome, whatever happened."""

    schema_version: Literal[1] = SCHEMA_VERSION
    fixtures: bool = False
    node: str
    label: str
    kind: NodeKind
    breadcrumb: list[str]
    status: NodeStatus
    children: list[TreeNode]
    truncated: bool = False
    has_content: bool = False
    #: What the selection currently scopes, in the server's words. The client
    #: renders it rather than inventing its own claim.
    selection_scope: str = ""
    detail: dict[str, DetailValue] | None = None
    error: str | None = None
    observed_at: str


class ConnectorIdentity(Wire):
    """Which code actually answers for a source. Not a label."""

    id: str
    name: str
    reached_by: str


class ResourceResponse(Wire):
    """One source's live metadata, read now.

    Every number here was observed during this call. A count that could not
    be read is absent, never carried over from a previous run or a document.
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    fixtures: bool = False
    node: str
    label: str
    kind: NodeKind
    breadcrumb: list[str]
    use_case_id: str
    source_id: str
    source_type: SourceType
    status: NodeStatus
    configured: bool
    enabled: bool
    holds: str = ""
    capabilities: list[str] = []
    connector: ConnectorIdentity
    #: Endpoint, database, table, graph, index. Non-secret coordinates only.
    coordinates: dict[str, DetailValue] = {}
    #: Counts and sizes observed during this call.
    metrics: dict[str, DetailValue] = {}
    #: Column or property names where the source can report them.
    schema_fields: list[dict[str, str]] | None = None
    #: Environment keys an operator must set. Names only, never values.
    settings: list[str] = []
    #: What this data is and is not. A replay is not live monitoring.
    provenance: str = ""
    detail: dict[str, DetailValue] | None = None
    error: str | None = None
    observed_at: str


class ContentResponse(Wire):
    """One source's bounded preview.

    ``sizeBytes`` is the number of rows returned. ``truncated`` says the
    source holds more than was shown, and ``sampleOf`` says how many more
    when the total is known. ``sampleNotes`` says *what* was cut — rows,
    columns, cell length or the byte budget — because a boolean cannot tell a
    reader whether to widen the bound or narrow the query.
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    fixtures: bool = False
    node: str
    label: str
    kind: NodeKind
    breadcrumb: list[str]
    use_case_id: str
    source_id: str
    status: NodeStatus
    content_kind: ContentKind
    media_type: str = ""
    text: str | None = None
    rows: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    size_bytes: int = 0
    #: The bound that was applied to this read, and the population it was
    #: drawn from when that is known.
    row_limit: int = 0
    sample_of: int | None = None
    truncated: bool = False
    #: Every bound that made this sample less than the source, in the words a
    #: reader is shown. Empty means nothing was cut.
    sample_notes: list[str] = []
    provenance: str = ""
    detail: dict[str, DetailValue] | None = None
    error: str | None = None
    observed_at: str


class SelectionSource(Wire):
    """One selectable source and whether this session has it switched on."""

    source_id: str
    use_case_id: str
    label: str
    source_type: SourceType
    configured: bool
    enabled: bool


class SelectionResponse(Wire):
    """What this request's selection is, and what it does."""

    schema_version: Literal[1] = SCHEMA_VERSION
    mode: Literal["all", "none", "explicit"]
    enabled: list[str]
    sources: list[SelectionSource]
    #: Plain English, from the server. The client must not invent a claim
    #: about what disabling a source does.
    scope: str
    observed_at: str


class InvalidNodeError(Wire):
    """The only body a rejected node id gets. It echoes nothing submitted."""

    error: Literal["invalid_node"] = "invalid_node"
    schema_version: Literal[1] = SCHEMA_VERSION


class InvalidSelectionError(Wire):
    """A selection header outside the accepted bounds. Echoes nothing either."""

    error: Literal["invalid_selection"] = "invalid_selection"
    schema_version: Literal[1] = SCHEMA_VERSION


class InvalidLimitError(Wire):
    """A row bound outside the accepted range.

    Carries the accepted range rather than the rejected value: the caller
    already knows what it sent, and the only new information is the bound.
    """

    error: Literal["invalid_limit"] = "invalid_limit"
    schema_version: Literal[1] = SCHEMA_VERSION
    minimum: int
    maximum: int


class SourceDisabledError(Wire):
    """The source exists and this session switched it off.

    A distinct code from ``invalid_node``: the client needs to tell "you
    turned this off" apart from "that is not a thing", and only the first is
    fixed by re-enabling it.
    """

    error: Literal["source_disabled"] = "source_disabled"
    schema_version: Literal[1] = SCHEMA_VERSION


__all__ = [
    "SCHEMA_VERSION",
    "ConnectorIdentity",
    "ContentKind",
    "ContentResponse",
    "DetailValue",
    "InvalidLimitError",
    "InvalidNodeError",
    "InvalidSelectionError",
    "NodeKind",
    "NodeStatus",
    "ResourceResponse",
    "SelectionResponse",
    "SelectionSource",
    "SourceDisabledError",
    "SourceType",
    "TreeNode",
    "TreeResponse",
    "Wire",
]
