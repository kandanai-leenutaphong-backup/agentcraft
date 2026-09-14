"""Composition — a node id in, one response out, always.

WHAT THIS MODULE OWNS
---------------------
The hierarchy, and nothing below it. ``azdata`` returns a flat, service-blind
enumeration per level and a bounded read per item; which branches exist, in
what order they render, how a resource group's resources are grouped by type,
what a child's id is, and what a byte string is rendered as are all
presentation decisions that belong with the explorer. Pushing any of them
down into the library would make the next consumer inherit this tree's shape.

THE SHAPE
---------
``root`` is the subscription. Below it: resource groups, then one group per
ARM type, then the resources themselves. Every resource — of every type,
known or unknown — opens into a ``properties`` leaf carrying its complete ARM
JSON, plus whatever branches :mod:`resource_explorer_api.facets` declares for
its type. That universal leaf is what makes this general rather than a fixed
demo: a type nobody anticipated is still fully browsable the day it appears.

WHY A DISCOVERY FAILURE IS STILL A 200
--------------------------------------
The payload's job is to explain the estate, including the parts of it that do
not answer. A 403 branch rendered as an HTTP error loses the one thing the
operator needed to read. The only non-200 answers are a malformed node id, an
unusable search term, and a missing principal.

WHY LEAVES ARE NOT EXPANDED
---------------------------
A leaf's id encodes the level that *produced* it, so expanding it would
re-run its parent's enumeration and answer with its own siblings. Leaves
therefore answer ``empty`` without a discovery call, which is also true.
Several of them still have contents — that is ``/api/content``, not
``/api/tree``.

WHY EVERY COORDINATE IS DERIVED FROM AN ARM RESOURCE ID
-------------------------------------------------------
A node id carries the resource id and nothing service-specific. The
subscription, resource group, account name, blob endpoint, Cosmos endpoint,
search endpoint and registry login server are all computed from it here. Only
the Kusto query URI cannot be — it carries a region — so it is read from ARM
once per cluster and cached.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from azdata import (
    ContentBounds,
    ContentResult,
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    blob_endpoint,
    collected_now,
    cosmos_endpoint,
    name_of,
    resource_group_of,
    sanitize_detail,
    subscription_of,
    type_of,
)

from resource_explorer_api.cache import ResultCache
from resource_explorer_api.content import type_content
from resource_explorer_api.contracts import (
    ContentResponse,
    SearchHit,
    SearchResponse,
    TreeNode,
    TreeResponse,
)
from resource_explorer_api.facets import ARM, Facet, facets_for
from resource_explorer_api.nodes import (
    InvalidNode,
    NodeRef,
    ROOT_ID,
    decode_node,
    encode_node,
    is_root,
)
from resource_explorer_api.settings import (
    MAX_DETAIL_KEYS,
    MAX_DETAIL_VALUE_CHARS,
    MAX_SEARCH_HITS,
    MAX_SEARCH_TERM_CHARS,
    REQUIRED_VARIABLE,
    Settings,
)

ROOT_LABEL = "Azure subscription"

PROPERTIES_LABEL = "Properties (ARM)"

#: Read when a plane returned a status with no detail of its own. Never
#: replaces a detail the plane produced: that string is the only description
#: of the failure the operator will ever see.
STATUS_TEXT: dict[str, str] = {
    "forbidden": "Forbidden — the app identity lacks read access",
    "unreachable": "Unreachable — network or private DNS",
    "unavailable": "Unavailable",
    "unconfigured": "Not configured",
}

#: What one data-plane level's children are called. ARM child collections are
#: absent because their kind is always ``arm_child``, whatever the provider.
#: Blob is absent too: ``walk_blobs`` returns folders and blobs at the same
#: level, so the node's own kind decides, not its parent's.
CHILD_KIND: dict[tuple[str, str], str] = {
    ("cosmos", "account"): "cosmos_database",
    ("cosmos", "database"): "cosmos_container",
    ("gremlin", "account"): "gremlin_database",
    ("gremlin", "database"): "gremlin_graph",
    ("kusto", "cluster"): "kusto_database",
    ("kusto", "database"): "kusto_table",
    ("search", "service"): "search_index",
    ("search", "index"): "search_field",
    ("logs", "workspace"): "log_table",
    ("acr", "registry"): "registry_repository",
    ("acr", "repository"): "registry_tag",
}

#: The level a data-plane child is addressed at, and whether it expands.
CHILD_LEVEL: dict[tuple[str, str], tuple[str, bool]] = {
    ("cosmos", "account"): ("database", True),
    ("cosmos", "database"): ("container", False),
    ("gremlin", "account"): ("database", True),
    ("gremlin", "database"): ("graph", False),
    ("kusto", "cluster"): ("database", True),
    ("kusto", "database"): ("table", False),
    ("search", "service"): ("index", True),
    ("search", "index"): ("field", False),
    ("logs", "workspace"): ("table", False),
    ("acr", "registry"): ("repository", True),
    ("acr", "repository"): ("tag", False),
}

#: How many leading segments of a discovered node's path are a coordinate the
#: explorer already holds. Most discoverers return a path relative to the
#: account; ``logs`` and ``acr`` return one that starts with it.
CHILD_PATH_OFFSET: dict[str, int] = {"logs": 1, "acr": 1}

#: An ARM resource whose type the plane did not report still has to group
#: somewhere; silently dropping it would make the inventory count wrong.
UNKNOWN_TYPE = "(unknown type)"


class InvalidQuery(Exception):
    """The search term is outside the accepted bounds. The reason stays here."""


class ExplorerService:
    """Expands one node, reads one node's contents, searches one estate."""

    def __init__(self, *, settings: Settings, access: Any) -> None:
        self._settings = settings
        self._access = access
        self._listings = ResultCache(ttl_secs=settings.inventory_ttl_secs)
        self._clusters = ResultCache(ttl_secs=settings.inventory_ttl_secs)

    def invalidate(self) -> None:
        self._listings.invalidate()
        self._clusters.invalidate()

    # -- tree ---------------------------------------------------------------

    async def expand(self, token: str | None) -> TreeResponse:
        budget = self._settings.request_timeout_secs
        if is_root(token):
            try:
                return await asyncio.wait_for(self._root(), budget)
            except (asyncio.TimeoutError, TimeoutError):
                return self._root_response(
                    status="unreachable",
                    children=[],
                    truncated=False,
                    error=f"Unreachable — expansion exceeded {budget}s",
                )
        ref = decode_node(str(token))
        try:
            return await asyncio.wait_for(self._expand(ref), budget)
        except (asyncio.TimeoutError, TimeoutError):
            return self._response(
                ref,
                status="unreachable",
                children=[],
                truncated=False,
                error=f"Unreachable — expansion exceeded {budget}s",
            )

    async def _root(self) -> TreeResponse:
        settings = self._settings
        if not settings.configured:
            return self._root_response(
                status="unconfigured",
                children=[],
                truncated=False,
                error=f"Not configured — set {REQUIRED_VARIABLE}",
            )
        if settings.resource_group:
            # A deployment may scope an operator to one group. The root then
            # holds exactly that group rather than a listing nobody may read.
            return self._root_response(
                status="ok",
                children=[self._group_node(settings.resource_group, {})],
                truncated=False,
            )
        result = await self._discover("estate", "subscription", ())
        children = [
            self._group_node(node.name, node.attributes) for node in result.nodes
        ]
        return self._root_response(
            status=result.status,
            children=children,
            truncated=result.truncated,
            error=self._error(result.status, result.detail),
            observed_at=result.collected_at,
        )

    async def _expand(self, ref: NodeRef) -> TreeResponse:
        if ref.is_leaf:
            return self._response(ref, status="empty", children=[], truncated=False)
        if ref.service == "estate":
            return await self._expand_estate(ref)
        return await self._expand_service(ref)

    # -- estate: groups, type groups, resources, ARM children ---------------

    async def _expand_estate(self, ref: NodeRef) -> TreeResponse:
        if ref.kind == "resource_group":
            return await self._expand_group(ref, resource_type="")
        if ref.kind == "resource_type":
            group = ref.path[0] if ref.path else ""
            wanted = ref.path[1] if len(ref.path) > 1 else ""
            return await self._expand_group(
                NodeRef(service="estate", level="resource_group", path=(group,), kind="resource_group"),
                resource_type=wanted,
                as_ref=ref,
            )
        if ref.kind in ("resource", "arm_child"):
            return self._facet_response(ref)
        return await self._expand_collection(ref)

    async def _expand_group(
        self, ref: NodeRef, *, resource_type: str, as_ref: NodeRef | None = None
    ) -> TreeResponse:
        answer = as_ref or ref
        group = ref.path[0] if ref.path else ""
        result = await self._group_listing(group)
        if result.status not in ("ok", "empty"):
            return self._response(
                answer,
                status=result.status,
                children=[],
                truncated=result.truncated,
                error=self._error(result.status, result.detail),
                observed_at=result.collected_at,
            )
        if resource_type:
            children = [
                self._resource_node(node)
                for node in result.nodes
                if _type_of(node) == resource_type
            ]
        else:
            children = self._type_children(group, result.nodes)
        clamped = len(children) > self._settings.max_children
        return self._response(
            answer,
            status="ok" if children else "empty",
            children=children[: self._settings.max_children],
            truncated=result.truncated or clamped,
            observed_at=result.collected_at,
        )

    async def _group_listing(self, group: str) -> DiscoveryResult:
        async def fetch() -> DiscoveryResult:
            return await self._discover("estate", "resource_group", (group,))

        return await self._listings.get(("group", group), fetch)

    def _type_children(
        self, group: str, nodes: Sequence[DiscoveryNode]
    ) -> list[TreeNode]:
        counts: dict[str, int] = {}
        for node in nodes:
            counts[_type_of(node)] = counts.get(_type_of(node), 0) + 1
        return [
            TreeNode(
                id=encode_node(
                    NodeRef(
                        service="estate",
                        level="type",
                        path=(group, resource_type),
                        kind="resource_type",
                    )
                ),
                label=f"{resource_type} ({count})",
                kind="resource_type",
                expandable=True,
                has_content=False,
                status="ok",
                detail=self._detail({"type": resource_type, "count": count}),
                error=None,
            )
            for resource_type, count in sorted(counts.items())
        ]

    def _facet_response(self, ref: NodeRef) -> TreeResponse:
        """A resource's branches. Composed locally: no call, no failure."""
        resource_id = ref.path[0] if ref.path else ""
        resource_type = type_of(resource_id)
        children = [self._properties_node(resource_id)]
        children.extend(
            self._facet_node(resource_id, facet) for facet in facets_for(resource_type)
        )
        return self._response(
            ref, status="ok", children=children, truncated=False
        )

    def _facet_node(self, resource_id: str, facet: Facet) -> TreeNode:
        path = (
            (resource_id, facet.collection) if facet.service == ARM else (resource_id,)
        )
        return TreeNode(
            id=encode_node(
                NodeRef(
                    service=facet.service,
                    level=facet.level,
                    path=path,
                    kind="collection",
                )
            ),
            label=facet.label,
            kind="collection",
            expandable=True,
            has_content=False,
            status="ok",
            detail=self._detail(
                {"service": facet.service, "collection": facet.collection or None}
            ),
            error=None,
        )

    def _properties_node(self, resource_id: str) -> TreeNode:
        return TreeNode(
            id=encode_node(
                NodeRef(
                    service="estate",
                    level="properties",
                    path=(resource_id,),
                    kind="properties",
                )
            ),
            label=PROPERTIES_LABEL,
            kind="properties",
            expandable=False,
            has_content=True,
            status="ok",
            detail=self._detail({"type": type_of(resource_id) or None}),
            error=None,
        )

    async def _expand_collection(self, ref: NodeRef) -> TreeResponse:
        """One ARM child collection of one resource."""
        resource_id = ref.path[0] if ref.path else ""
        collection = ref.path[1] if len(ref.path) > 1 else ""
        result = await self._discover("estate", "collection", (resource_id, collection))
        children = [
            self._arm_child_node(node) for node in result.nodes[: self._settings.max_children]
        ]
        return self._response(
            ref,
            status=result.status,
            children=children,
            truncated=result.truncated or len(result.nodes) > self._settings.max_children,
            error=self._error(result.status, result.detail),
            observed_at=result.collected_at,
        )

    def _arm_child_node(self, node: DiscoveryNode) -> TreeNode:
        child_id = str(node.attributes.get("id") or "")
        return TreeNode(
            id=encode_node(
                NodeRef(
                    service="estate", level="child", path=(child_id,), kind="arm_child"
                )
            ),
            label=node.name,
            kind="arm_child",
            # An ARM child always has at least its own properties leaf.
            expandable=bool(child_id),
            has_content=False,
            status="ok",
            detail=self._detail(node.attributes),
            error=None,
        )

    # -- data planes ---------------------------------------------------------

    async def _expand_service(self, ref: NodeRef) -> TreeResponse:
        resource_id = ref.path[0] if ref.path else ""
        try:
            scope = await self._scope(ref.service, ref.level, ref.path)
        except LookupError as exc:
            return self._response(
                ref,
                status="unavailable",
                children=[],
                truncated=False,
                error=sanitize_detail(str(exc)),
            )
        result = await self._discover_scoped(ref.service, ref.level, scope)
        children = [
            self._service_child(ref, node, resource_id)
            for node in result.nodes[: self._settings.max_children]
        ]
        return self._response(
            ref,
            status=result.status,
            children=children,
            truncated=result.truncated
            or len(result.nodes) > self._settings.max_children,
            error=self._error(result.status, result.detail),
            observed_at=result.collected_at,
        )

    def _service_child(
        self, ref: NodeRef, node: DiscoveryNode, resource_id: str
    ) -> TreeNode:
        if ref.service == "blob":
            kind, child_level, expandable = _blob_child(ref.level, node.kind)
        else:
            kind = CHILD_KIND[(ref.service, ref.level)]
            child_level, expandable = CHILD_LEVEL[(ref.service, ref.level)]
        offset = CHILD_PATH_OFFSET.get(ref.service, 0)
        child_ref = NodeRef(
            service=ref.service,
            level=child_level,
            path=(resource_id, *node.path[offset:]),
            kind=kind,
        )
        return TreeNode(
            id=encode_node(child_ref),
            label=node.name,
            kind=kind,  # type: ignore[arg-type]
            expandable=expandable,
            has_content=child_ref.content is not None,
            # A child is never speculatively probed; it is known to exist,
            # which is all "ok" claims here.
            status="ok",
            detail=self._detail(node.attributes),
            error=None,
        )

    async def _scope(
        self, service: str, level: str, path: tuple[str, ...]
    ) -> DiscoveryScope:
        """Every service coordinate, derived from the resource id in ``path[0]``."""
        resource_id = path[0] if path else ""
        name = name_of(resource_id)
        subscription = subscription_of(resource_id)
        group = resource_group_of(resource_id)
        tail = path[1:]
        if service == "blob":
            return DiscoveryScope(endpoint=blob_endpoint(name), path=tail)
        if service in ("cosmos", "gremlin"):
            return DiscoveryScope(
                subscription_id=subscription,
                resource_group=group,
                account_name=name,
                path=tail,
            )
        if service == "search":
            return DiscoveryScope(
                endpoint=f"https://{name}.search.windows.net", path=tail
            )
        if service == "logs":
            return DiscoveryScope(path=(resource_id, *tail))
        if service == "acr":
            return DiscoveryScope(
                subscription_id=subscription,
                endpoint=f"{name.lower()}.azurecr.io",
                path=(f"{name.lower()}.azurecr.io", *tail),
            )
        if service == "kusto":
            if level == "cluster":
                return DiscoveryScope(
                    subscription_id=subscription,
                    resource_group=group,
                    account_name=name,
                    path=tail,
                )
            return DiscoveryScope(
                endpoint=await self._cluster_uri(resource_id), path=tail
            )
        raise LookupError(f"no coordinate for service {service}")

    async def _cluster_uri(self, resource_id: str) -> str:
        """A Kusto query URI carries a region, so it is read, never composed."""

        async def fetch() -> str:
            document = await asyncio.to_thread(self._access.arm.read, resource_id)
            properties = document.get("properties")
            properties = properties if isinstance(properties, dict) else {}
            return str(properties.get("uri") or "")

        return await self._clusters.get(("cluster", resource_id), fetch)

    # -- contents ------------------------------------------------------------

    async def read_content(self, token: str | None) -> ContentResponse:
        if is_root(token):
            raise InvalidNode("root has no contents")
        ref = decode_node(str(token))
        target = ref.content
        if target is None:
            return self._content_response(
                ref, status="empty", content_kind="none", media_type=""
            )
        try:
            result = await asyncio.wait_for(
                self._read(ref, target), self._settings.request_timeout_secs
            )
        except (asyncio.TimeoutError, TimeoutError):
            return self._content_response(
                ref,
                status="unreachable",
                content_kind="none",
                media_type="",
                error=(
                    "Unreachable — read exceeded "
                    f"{self._settings.request_timeout_secs}s"
                ),
            )
        return self._shape_content(ref, result)

    async def _read(self, ref: NodeRef, target: tuple[str, str]) -> ContentResult:
        service, kind = target
        bounds = ContentBounds(
            max_bytes=self._settings.max_content_bytes,
            max_rows=self._settings.max_content_rows,
            timeout_secs=self._settings.content_timeout_secs,
        )
        resource_id = ref.path[0] if ref.path else ""
        name = name_of(resource_id)
        tail = ref.path[1:]
        if kind == "properties":
            return await self._access.properties.properties(resource_id, bounds=bounds)
        if service == "blob":
            return await self._access.blob.read(
                endpoint=blob_endpoint(name),
                container=tail[0] if tail else "",
                blob=tail[1] if len(tail) > 1 else "",
                bounds=bounds,
            )
        if service in ("cosmos", "gremlin"):
            return await self._access.cosmos.documents(
                endpoint=cosmos_endpoint(name),
                database=tail[0] if tail else "",
                container=tail[1] if len(tail) > 1 else "",
                bounds=bounds,
            )
        if service == "kusto":
            return await self._access.kusto.rows(
                query_uri=await self._cluster_uri(resource_id),
                database=tail[0] if tail else "",
                table=tail[1] if len(tail) > 1 else "",
                bounds=bounds,
            )
        if service == "search":
            return await self._access.search.documents(
                endpoint=f"https://{name}.search.windows.net",
                index=tail[0] if tail else "",
                bounds=bounds,
            )
        if service == "logs":
            return await self._access.logs.rows(
                workspace_id=resource_id,
                table=tail[0] if tail else "",
                bounds=bounds,
            )
        raise InvalidNode("no reader for this node")

    def _shape_content(self, ref: NodeRef, result: ContentResult) -> ContentResponse:
        payload = result.payload
        if payload.form == "rows":
            return self._content_response(
                ref,
                status=result.status,
                content_kind="rows",
                media_type=payload.media_type or "application/json",
                rows=[dict(row) for row in payload.rows],
                columns=list(payload.columns),
                size_bytes=payload.size_bytes,
                truncated=result.truncated,
                error=self._error(result.status, result.detail),
                observed_at=result.collected_at,
            )
        if payload.form == "bytes":
            typed = type_content(
                payload.data,
                media_type=payload.media_type,
                name=ref.path[-1] if ref.path else "",
            )
            return self._content_response(
                ref,
                status=result.status,
                content_kind=typed.content_kind,
                media_type=typed.media_type,
                text=typed.text,
                data_base64=typed.data_base64,
                size_bytes=payload.size_bytes,
                truncated=result.truncated,
                error=self._error(result.status, result.detail),
                observed_at=result.collected_at,
            )
        return self._content_response(
            ref,
            status=result.status,
            content_kind="none",
            media_type=payload.media_type,
            truncated=result.truncated,
            error=self._error(result.status, result.detail),
            observed_at=result.collected_at,
        )

    # -- search --------------------------------------------------------------

    async def search(self, query: str | None, limit: int | None = None) -> SearchResponse:
        term = str(query or "").strip()
        if not term or len(term) > MAX_SEARCH_TERM_CHARS:
            raise InvalidQuery("term length")
        rows = max(1, min(int(limit or MAX_SEARCH_HITS), MAX_SEARCH_HITS))
        if not self._settings.configured:
            return SearchResponse(
                fixtures=self._settings.fake_discovery,
                query=term,
                status="unconfigured",
                hits=[],
                truncated=False,
                error=f"Not configured — set {REQUIRED_VARIABLE}",
                observed_at=collected_now(),
            )
        try:
            result = await asyncio.wait_for(
                self._access.properties.search(
                    term,
                    bounds=ContentBounds(
                        max_rows=rows, timeout_secs=self._settings.content_timeout_secs
                    ),
                ),
                self._settings.request_timeout_secs,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return SearchResponse(
                fixtures=self._settings.fake_discovery,
                query=term,
                status="unreachable",
                hits=[],
                truncated=False,
                error=(
                    "Unreachable — search exceeded "
                    f"{self._settings.request_timeout_secs}s"
                ),
                observed_at=collected_now(),
            )
        return SearchResponse(
            fixtures=self._settings.fake_discovery,
            query=term,
            status=result.status,  # type: ignore[arg-type]
            hits=[self._hit(row) for row in result.payload.rows],
            truncated=result.truncated,
            error=self._error(result.status, result.detail),
            observed_at=result.collected_at or collected_now(),
        )

    def _hit(self, row: Mapping[str, Any]) -> SearchHit:
        resource_id = str(row.get("id") or "")
        resource_type = str(row.get("type") or "")
        is_group = resource_type.lower() == "microsoft.resources/subscriptions/resourcegroups"
        name = str(row.get("name") or name_of(resource_id))
        ref = (
            NodeRef(
                service="estate", level="resource_group", path=(name,), kind="resource_group"
            )
            if is_group
            else NodeRef(
                service="estate", level="resource", path=(resource_id,), kind="resource"
            )
        )
        return SearchHit(
            node=encode_node(ref),
            label=name,
            kind=ref.kind,  # type: ignore[arg-type]
            resource_group=str(row.get("resourceGroup") or ""),
            type=resource_type,
            location=str(row.get("location") or ""),
            matched_in=str(row.get("matchedIn") or ""),
            detail=self._detail(
                {"kind": row.get("kind") or None, "sku": row.get("skuName") or None}
            ),
        )

    # -- discovery -----------------------------------------------------------

    async def _discover(
        self, service: str, level: str, path: tuple[str, ...]
    ) -> DiscoveryResult:
        return await self._discover_scoped(service, level, DiscoveryScope(path=path))

    async def _discover_scoped(
        self, service: str, level: str, scope: DiscoveryScope
    ) -> DiscoveryResult:
        discoverer = self._access.discoverers.get(service)
        if discoverer is None:
            return DiscoveryResult(
                service=service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"{service} is not registered",
                collected_at=collected_now(),
            )
        if not scope.subscription_id and self._settings.subscription_id:
            scope = DiscoveryScope(
                subscription_id=self._settings.subscription_id,
                resource_group=scope.resource_group,
                endpoint=scope.endpoint,
                account_name=scope.account_name,
                path=scope.path,
            )
        return await discoverer.discover(
            level,
            scope,
            bounds=DiscoveryBounds(
                max_items=self._settings.max_children,
                timeout_secs=self._settings.discovery_timeout_secs,
            ),
        )

    # -- shaping -------------------------------------------------------------

    def _group_node(self, name: str, attributes: Mapping[str, Any]) -> TreeNode:
        return TreeNode(
            id=encode_node(
                NodeRef(
                    service="estate",
                    level="resource_group",
                    path=(name,),
                    kind="resource_group",
                )
            ),
            label=name,
            kind="resource_group",
            expandable=True,
            has_content=False,
            status="ok",
            detail=self._detail(attributes),
            error=None,
        )

    def _resource_node(self, node: DiscoveryNode) -> TreeNode:
        resource_id = str(node.attributes.get("id") or "")
        return TreeNode(
            id=encode_node(
                NodeRef(
                    service="estate",
                    level="resource",
                    path=(resource_id,),
                    kind="resource",
                )
            ),
            label=node.name,
            kind="resource",
            expandable=True,
            has_content=False,
            status="ok",
            detail=self._detail(node.attributes),
            error=None,
        )

    def _detail(self, attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not attributes:
            return None
        detail: dict[str, Any] = {}
        for name, value in list(attributes.items())[:MAX_DETAIL_KEYS]:
            if value is None:
                continue
            if isinstance(value, (bool, int, float)):
                detail[str(name)] = value
                continue
            text = sanitize_detail(str(value))
            if len(text) > MAX_DETAIL_VALUE_CHARS:
                text = text[: MAX_DETAIL_VALUE_CHARS - 1] + "…"
            detail[str(name)] = text
        return detail or None

    @staticmethod
    def _error(status: str, detail: str) -> str | None:
        if status in ("ok", "empty"):
            return None
        text = sanitize_detail(detail) if detail else ""
        return text or STATUS_TEXT.get(status, "Unavailable")

    def _root_response(
        self,
        *,
        status: str,
        children: list[TreeNode],
        truncated: bool,
        error: str | None = None,
        observed_at: str = "",
    ) -> TreeResponse:
        return TreeResponse(
            fixtures=self._settings.fake_discovery,
            node=ROOT_ID,
            label=ROOT_LABEL,
            kind="root",
            breadcrumb=[ROOT_LABEL],
            status=status,  # type: ignore[arg-type]
            children=children,
            truncated=truncated,
            has_content=False,
            detail=self._detail(
                {
                    "subscription": self._settings.subscription_id or None,
                    "resourceGroup": self._settings.resource_group or None,
                }
            ),
            error=error,
            observed_at=observed_at or collected_now(),
        )

    def _response(
        self,
        ref: NodeRef,
        *,
        status: str,
        children: list[TreeNode],
        truncated: bool,
        error: str | None = None,
        observed_at: str = "",
    ) -> TreeResponse:
        breadcrumb = breadcrumb_for(ref)
        return TreeResponse(
            fixtures=self._settings.fake_discovery,
            node=encode_node(ref),
            label=breadcrumb[-1],
            kind=ref.kind,  # type: ignore[arg-type]
            breadcrumb=breadcrumb,
            status=status,  # type: ignore[arg-type]
            children=children,
            truncated=truncated,
            has_content=ref.content is not None,
            detail=None,
            error=error,
            observed_at=observed_at or collected_now(),
        )

    def _content_response(
        self,
        ref: NodeRef,
        *,
        status: str,
        content_kind: str,
        media_type: str,
        text: str | None = None,
        data_base64: str | None = None,
        rows: list[dict[str, Any]] | None = None,
        columns: list[str] | None = None,
        size_bytes: int = 0,
        truncated: bool = False,
        error: str | None = None,
        observed_at: str = "",
    ) -> ContentResponse:
        breadcrumb = breadcrumb_for(ref)
        return ContentResponse(
            fixtures=self._settings.fake_discovery,
            node=encode_node(ref),
            label=breadcrumb[-1],
            kind=ref.kind,  # type: ignore[arg-type]
            breadcrumb=breadcrumb,
            status=status,  # type: ignore[arg-type]
            content_kind=content_kind,  # type: ignore[arg-type]
            media_type=media_type,
            text=text,
            data_base64=data_base64,
            rows=rows,
            columns=columns,
            size_bytes=size_bytes,
            truncated=truncated,
            detail=None,
            error=error,
            observed_at=observed_at or collected_now(),
        )


def breadcrumb_for(ref: NodeRef) -> list[str]:
    """Labels from the root to this node, derived from the coordinate alone.

    No lookup and no call: a breadcrumb that needed a listing would make every
    deep link cost the whole path above it.
    """
    trail = [ROOT_LABEL]
    if not ref.path:
        return trail
    if ref.kind == "resource_group":
        return trail + [ref.path[0]]
    if ref.kind == "resource_type":
        return trail + list(ref.path[:2])

    resource_id = ref.path[0]
    trail.append(resource_group_of(resource_id) or "(subscription)")
    trail.extend(_arm_names(resource_id) or [name_of(resource_id)])
    if ref.kind == "properties":
        trail.append(PROPERTIES_LABEL)
        return trail
    if ref.service == ARM and ref.kind == "collection":
        trail.append(ref.path[1] if len(ref.path) > 1 else "children")
        return trail
    if ref.kind == "collection":
        trail.append(_facet_label(resource_id, ref.service))
        return trail
    trail.append(_facet_label(resource_id, ref.service))
    for segment in ref.path[1:]:
        if not segment:
            continue
        if ref.service == "blob":
            # Only in blob storage is a slash a folder boundary. An index
            # named ``assets/v1: beta`` is one name, and splitting it would
            # invent two levels that do not exist.
            trail.extend(part for part in segment.split("/") if part)
        else:
            trail.append(segment)
    return trail


def _facet_label(resource_id: str, service: str) -> str:
    for facet in facets_for(type_of(resource_id)):
        if facet.service == service:
            return facet.label
    return service


def _blob_child(level: str, node_kind: str) -> tuple[str, str, bool]:
    """``(kind, child level, expandable)`` for one entry of a blob listing.

    A folder re-enters the ``container`` level with a longer prefix rather
    than descending to a level of its own: in blob storage depth *is* the
    prefix, and a level per folder would be unbounded.
    """
    if level == "account":
        return "blob_container", "container", True
    if node_kind == "blob_folder":
        return "blob_folder", "container", True
    return "blob", "blob", False


def _arm_names(resource_id: str) -> list[str]:
    """The name segments after ``providers``: ``app``, ``rev`` for a replica."""
    parts = [part for part in str(resource_id).split("/") if part]
    lowered = [part.lower() for part in parts]
    if "providers" not in lowered:
        return []
    tail = parts[lowered.index("providers") + 1 :]
    return [tail[index] for index in range(2, len(tail), 2)]


def _type_of(node: DiscoveryNode) -> str:
    return str(node.attributes.get("type") or UNKNOWN_TYPE)


__all__ = [
    "CHILD_KIND",
    "CHILD_LEVEL",
    "CHILD_PATH_OFFSET",
    "ExplorerService",
    "InvalidNode",
    "InvalidQuery",
    "PROPERTIES_LABEL",
    "ROOT_LABEL",
    "STATUS_TEXT",
    "UNKNOWN_TYPE",
    "breadcrumb_for",
]
