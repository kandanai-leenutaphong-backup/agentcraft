"""A use-case-rooted, read-only inventory of the data a deployment is connected to.

Adopted from the `resource_explorer` component (backend `resource_explorer_api`,
React 19 + TypeScript frontend). `PROVENANCE.md` records what came from where.

WHAT IT IS
----------
A two-level tree — use cases, then the sources filed under each — with live
metadata and a bounded preview per source. Everything it will ever serve is
declared in a registry the composing application supplies; a request can name
only what the registry declares.

WHAT IT IS NOT
--------------
Not an Azure estate browser. Upstream roots at a subscription and discovers
downward, which is right for exploring an estate and wrong for answering
"what is behind this use case". Nothing here can address a resource nobody
declared, and there is no discovery walk to widen.

Not an application. No settings object, no principal guard, no static mount,
no development authentication bypass. The host owns all four; this component
contributes one router and a set of React components.

PUBLIC SURFACE
--------------
Registry, so the host can declare what exists:

    InventoryRegistry, UseCase, InventorySource, SourceBinding, SourceType
    CAPABILITIES, InventoryDefinitionError

Service and its injection seam:

    InventoryService, SourceProbe, ProbeReport, SourceDisabled
    DEFAULT_PREVIEW_ROWS, MAX_PREVIEW_ROWS, DEFAULT_PROVENANCE

Selection, which is per request and never stored:

    Selection, parse_selection, InvalidSelection
    SELECTION_HEADER, SELECTION_SCOPE

Node ids, which only this component mints:

    decode_node, encode_node, is_root, source_node, use_case_node
    NodeRef, InvalidNode, ROOT_ID, MAX_TOKEN_CHARS, token_digest

Wire contract and HTTP:

    TreeResponse, TreeNode, ResourceResponse, ContentResponse,
    SelectionResponse, SelectionSource, ConnectorIdentity,
    InvalidNodeError, InvalidSelectionError, SourceDisabledError,
    NodeStatus, NodeKind, ContentKind, SCHEMA_VERSION
    build_inventory_router, NO_STORE

The frontend half lives in `frontend/` and is imported by the host's Vite
build through the `@components/` alias, not from here.

DEPENDENCIES
------------
`fastapi` and `pydantic` for the wire and the router;
`app/components/data_connector_library` for the content plane and the six
statuses. Nothing else, and nothing outside `app/components/`.
"""

from __future__ import annotations

from .backend.contracts import (
    SCHEMA_VERSION,
    ConnectorIdentity,
    ContentKind,
    ContentResponse,
    DetailValue,
    InvalidLimitError,
    InvalidNodeError,
    InvalidSelectionError,
    NodeKind,
    NodeStatus,
    ResourceResponse,
    SelectionResponse,
    SelectionSource,
    SourceDisabledError,
    TreeNode,
    TreeResponse,
)
from .backend.nodes import (
    MAX_TOKEN_CHARS,
    ROOT_ID,
    InvalidNode,
    NodeRef,
    decode_node,
    encode_node,
    is_root,
    source_node,
    token_digest,
    use_case_node,
)
from .backend.registry import (
    CAPABILITIES,
    InventoryDefinitionError,
    InventoryRegistry,
    InventorySource,
    SourceBinding,
    SourceType,
    UseCase,
)
from .backend.router import NO_STORE, build_inventory_router
from .backend.selection import (
    SELECTION_HEADER,
    SELECTION_SCOPE,
    InvalidSelection,
    Selection,
    parse_selection,
)
from .backend.service import (
    DEFAULT_PREVIEW_ROWS,
    DEFAULT_PROVENANCE,
    MAX_PREVIEW_ROWS,
    InventoryService,
    ProbeReport,
    SourceDisabled,
    SourceProbe,
)

from ._content import ContentPayload, ContentResult, collected_now, content_failure

__all__ = [
    "ContentPayload", "ContentResult", "collected_now", "content_failure",
    "CAPABILITIES",
    "DEFAULT_PREVIEW_ROWS",
    "DEFAULT_PROVENANCE",
    "MAX_PREVIEW_ROWS",
    "MAX_TOKEN_CHARS",
    "NO_STORE",
    "ROOT_ID",
    "SCHEMA_VERSION",
    "SELECTION_HEADER",
    "SELECTION_SCOPE",
    "ConnectorIdentity",
    "ContentKind",
    "ContentResponse",
    "DetailValue",
    "InvalidNode",
    "InvalidLimitError",
    "InvalidNodeError",
    "InvalidSelection",
    "InvalidSelectionError",
    "InventoryDefinitionError",
    "InventoryRegistry",
    "InventoryService",
    "InventorySource",
    "NodeKind",
    "NodeRef",
    "NodeStatus",
    "ProbeReport",
    "ResourceResponse",
    "Selection",
    "SelectionResponse",
    "SelectionSource",
    "SourceBinding",
    "SourceDisabled",
    "SourceDisabledError",
    "SourceProbe",
    "SourceType",
    "TreeNode",
    "TreeResponse",
    "UseCase",
    "build_inventory_router",
    "decode_node",
    "encode_node",
    "is_root",
    "parse_selection",
    "source_node",
    "token_digest",
    "use_case_node",
]
