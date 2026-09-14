"""The inventory service — registry in, wire payloads out.

NEW IN THIS COMPONENT, over the adopted wire contract, node codec and cache.
Usage and the shape of each answer: `README.md`.

Three answers and no fourth: ``tree``, ``resource``, ``content``. There is no
query endpoint, no filter expression, no free-text parameter and no write. The
only caller input that reaches a reader is a node token decoding to two
allowlisted identifiers, plus a row bound the route already clamped.

A source declares which connector answers for it and the composing application
registers a probe under that name, so this module never learns what an ADX
table is. A connector with no probe is reported ``unavailable`` naming it.

A read failure is a 200 carrying its status: a dark branch has to render, and
the operator's next action differs for ``forbidden``, ``unreachable``,
``unconfigured`` and ``empty``. Only a malformed request and a scope conflict
are non-200.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .._content import (
    ContentResult,
    DiscoveryStatus,
    collected_now,
    sanitize_detail,
)

from .cache import ResultCache
from .contracts import (
    ConnectorIdentity,
    ContentResponse,
    DetailValue,
    ResourceResponse,
    SelectionResponse,
    SelectionSource,
    TreeNode,
    TreeResponse,
)
from .nodes import (
    InvalidNode,
    NodeRef,
    ROOT_ID,
    decode_node,
    is_root,
    source_node,
    use_case_node,
)
from .registry import InventoryRegistry, InventorySource, UseCase
from .selection import SELECTION_SCOPE, Selection

#: What a preview returns when the caller does not say. Small enough to read.
DEFAULT_PREVIEW_ROWS = 25

#: The ceiling. A route clamps to this before the service is called; the
#: service clamps again because a second caller must not be able to skip it.
MAX_PREVIEW_ROWS = 100

#: How long a metadata read is reused. Long enough to survive a click that
#: opens the tree, the detail pane and the preview together; short enough
#: that a count is still "read now" in any useful sense.
DEFAULT_METADATA_TTL_SECS = 30.0

#: Said on every resource and content payload unless a source overrides it.
DEFAULT_PROVENANCE = (
    "Historical replay of a fixed export. Not live monitoring, and not evidence "
    "of current activity."
)


class SourceDisabled(Exception):
    """The source is real and this request's selection switched it off."""


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """One source's metadata, as a probe observed it. Never an exception."""

    status: DiscoveryStatus
    metrics: Mapping[str, DetailValue] = field(default_factory=dict)
    #: ``{"name": ..., "type": ...}`` per column or property, where the
    #: source can report them.
    schema_fields: tuple[Mapping[str, str], ...] = ()
    #: Non-secret coordinates the probe resolved, merged over the declared
    #: ones. A probe that resolved nothing returns an empty mapping.
    coordinates: Mapping[str, DetailValue] = field(default_factory=dict)
    detail: str = ""
    #: The population a preview would be a sample of, when the probe knows
    #: it. ``None`` means unknown, which is not the same as zero.
    total_rows: int | None = None
    collected_at: str = ""


@runtime_checkable
class SourceProbe(Protocol):
    """What the composing application registers per connector."""

    async def metadata(self, source: InventorySource) -> ProbeReport:
        """Read this source's metadata now. Never raises."""

    async def preview(self, source: InventorySource, *, limit: int) -> ContentResult:
        """Read at most ``limit`` rows now. Never raises."""


def _type_label(source_type: str) -> str:
    return {
        "adx_table": "ADX table",
        "gremlin_graph": "Cosmos graph",
        "search_index": "Azure AI Search index",
        "local_table": "Local table",
    }.get(source_type, source_type)


#: One coordinate, rendered. Longer than any endpoint, database or table name.
_COORDINATE_CAP = 200


def _safe_coordinates(source: InventorySource) -> dict[str, DetailValue]:
    """Declared coordinates, capped. Nothing is added that was not declared.

    Capped but deliberately **not** URL-stripped. `sanitize_detail` removes
    URL-shaped tokens because an SDK exception message leaks endpoints the
    caller never asked about; a coordinate is the opposite case — the operator
    declared it, and an inventory that answers `<redacted-url>` when asked
    which cluster it reads has failed at its one job. Free text still goes
    through `sanitize_detail`; declared coordinates do not.
    """
    return {
        str(key): str(value)[:_COORDINATE_CAP]
        for key, value in source.binding.coordinates.items()
        if str(value).strip()
    }


class InventoryService:
    """Serves the tree, one source's metadata, and one source's preview."""

    def __init__(
        self,
        registry: InventoryRegistry,
        probes: Mapping[str, SourceProbe],
        *,
        metadata_ttl_secs: float = DEFAULT_METADATA_TTL_SECS,
        max_preview_rows: int = MAX_PREVIEW_ROWS,
    ) -> None:
        self._registry = registry
        self._probes = dict(probes)
        self._max_preview_rows = max(1, int(max_preview_rows))
        self._cache = ResultCache(ttl_secs=metadata_ttl_secs)

    @property
    def registry(self) -> InventoryRegistry:
        return self._registry

    # ---- selection ---------------------------------------------------------

    def selection_report(self, selection: Selection) -> SelectionResponse:
        """What this request's selection is, and what it does."""
        order = self._registry.source_ids()
        return SelectionResponse(
            mode=selection.mode,
            enabled=list(selection.enabled_ids(order)),
            sources=[
                SelectionSource(
                    source_id=source.source_id,
                    use_case_id=source.use_case_id,
                    label=source.name,
                    source_type=source.source_type,
                    configured=source.is_configured,
                    enabled=selection.enabled(source.source_id),
                )
                for source in self._registry.sources()
            ],
            scope=SELECTION_SCOPE,
            observed_at=collected_now(),
        )

    # ---- tree --------------------------------------------------------------

    async def tree(self, token: str | None, selection: Selection) -> TreeResponse:
        """Expand the root or one use case. Never probes a source."""
        if is_root(token):
            return self._root(selection)
        ref = self._resolve(token or "")
        if ref.kind == "source":
            # A leaf. Answering "empty" without a call is the true answer.
            source = self._source(ref)
            return TreeResponse(
                node=token or ROOT_ID,
                label=source.name,
                kind="source",
                breadcrumb=self._breadcrumb(ref),
                status="empty",
                children=[],
                has_content=self._readable(source, selection),
                selection_scope=SELECTION_SCOPE,
                observed_at=collected_now(),
            )
        use_case = self._use_case(ref)
        return TreeResponse(
            node=token or ROOT_ID,
            label=use_case.name,
            kind="use_case",
            breadcrumb=self._breadcrumb(ref),
            status="ok" if use_case.sources else "empty",
            children=[
                self._source_node(source, selection) for source in use_case.sources
            ],
            detail={"summary": use_case.summary, "sources": len(use_case.sources)},
            selection_scope=SELECTION_SCOPE,
            observed_at=collected_now(),
        )

    def _root(self, selection: Selection) -> TreeResponse:
        children = [
            TreeNode(
                id=use_case_node(use_case.use_case_id),
                label=use_case.name,
                kind="use_case",
                expandable=True,
                has_content=False,
                status="ok" if use_case.sources else "empty",
                use_case_id=use_case.use_case_id,
                tags=[f"{len(use_case.sources)} sources"],
                detail={
                    "summary": use_case.summary,
                    "enabled": len(
                        [
                            source
                            for source in use_case.sources
                            if selection.enabled(source.source_id)
                        ]
                    ),
                },
            )
            for use_case in self._registry.use_cases
        ]
        return TreeResponse(
            node=ROOT_ID,
            label="Data sources",
            kind="root",
            breadcrumb=["Data sources"],
            status="ok" if children else "empty",
            children=children,
            selection_scope=SELECTION_SCOPE,
            observed_at=collected_now(),
        )

    def _source_node(self, source: InventorySource, selection: Selection) -> TreeNode:
        configured = source.is_configured
        return TreeNode(
            id=source_node(source.use_case_id, source.source_id),
            label=source.name,
            kind="source",
            expandable=False,
            has_content=self._readable(source, selection),
            status="ok" if configured else "unconfigured",
            use_case_id=source.use_case_id,
            source_id=source.source_id,
            source_type=source.source_type,
            tags=[_type_label(source.source_type)],
            enabled=selection.enabled(source.source_id),
            configured=configured,
            detail=_safe_coordinates(source),
            error=source.unconfigured_detail or None,
        )

    def _readable(self, source: InventorySource, selection: Selection) -> bool:
        return source.is_configured and selection.enabled(source.source_id) and "preview" in source.capabilities

    # ---- one source --------------------------------------------------------

    async def resource(self, token: str, selection: Selection) -> ResourceResponse:
        """One source's metadata, read now. Raises only on a rejected request."""
        ref = self._resolve(token)
        if ref.kind != "source":
            raise InvalidNode("resource is addressable on a source only")
        source = self._source(ref)
        self._require_enabled(source, selection)

        report = await self._report(source)
        coordinates = _safe_coordinates(source)
        coordinates.update(
            {str(key): value for key, value in report.coordinates.items()}
        )
        return ResourceResponse(
            node=token,
            label=source.name,
            kind="source",
            breadcrumb=self._breadcrumb(ref),
            use_case_id=source.use_case_id,
            source_id=source.source_id,
            source_type=source.source_type,
            status=report.status,
            configured=source.is_configured,
            enabled=True,
            holds=source.holds,
            capabilities=list(source.capabilities),
            connector=ConnectorIdentity(
                id=source.binding.connector,
                name=source.binding.connector_name or source.binding.connector,
                reached_by=source.binding.reached_by,
            ),
            coordinates=coordinates,
            metrics=dict(report.metrics),
            schema_fields=[dict(item) for item in report.schema_fields] or None,
            settings=list(source.binding.settings),
            provenance=source.provenance or DEFAULT_PROVENANCE,
            error=sanitize_detail(report.detail) or None,
            observed_at=report.collected_at or collected_now(),
        )

    async def content(
        self, token: str, selection: Selection, *, limit: int = DEFAULT_PREVIEW_ROWS
    ) -> ContentResponse:
        """One source's bounded preview. Raises only on a rejected request."""
        ref = self._resolve(token)
        if ref.kind != "source":
            raise InvalidNode("content is addressable on a source only")
        source = self._source(ref)
        self._require_enabled(source, selection)

        bound = max(1, min(int(limit), self._max_preview_rows))
        if "preview" not in source.capabilities:
            return self._empty_content(token, ref, source, status="forbidden",
                                       detail="This source exposes metadata only; row preview is not authorized.", row_limit=bound)
        if not source.is_configured:
            return self._empty_content(
                token,
                ref,
                source,
                status="unconfigured",
                detail=source.unconfigured_detail,
                row_limit=bound,
            )
        probe = self._probes.get(source.binding.connector)
        if probe is None:
            return self._empty_content(
                token,
                ref,
                source,
                status="unavailable",
                detail=f"no reader is registered for connector {source.binding.connector!r}",
                row_limit=bound,
            )

        result = await probe.preview(source, limit=bound)
        rows = [dict(row) for row in result.payload.rows]
        report = await self._report(source)
        total = report.total_rows
        beyond_sample = total is not None and len(rows) < total
        notes = list(result.payload.notes)
        if beyond_sample and not notes:
            notes.append(
                f"{len(rows)} of {total} row(s) were read; the rest are not in "
                "this sample"
            )
        return ContentResponse(
            node=token,
            label=source.name,
            kind="source",
            breadcrumb=self._breadcrumb(ref),
            use_case_id=source.use_case_id,
            source_id=source.source_id,
            status=result.status,
            content_kind="rows" if rows else "none",
            media_type=result.payload.media_type,
            rows=rows or None,
            columns=list(result.payload.columns) or None,
            size_bytes=len(rows),
            row_limit=bound,
            sample_of=total,
            truncated=result.truncated or beyond_sample,
            sample_notes=notes,
            provenance=source.provenance or DEFAULT_PROVENANCE,
            error=sanitize_detail(result.detail) or None,
            observed_at=result.collected_at or collected_now(),
        )

    # ---- internals ---------------------------------------------------------

    async def _report(self, source: InventorySource) -> ProbeReport:
        """One source's metadata, deduplicated and briefly cached."""
        if not source.is_configured:
            return ProbeReport(
                status="unconfigured",
                detail=source.unconfigured_detail,
                collected_at=collected_now(),
            )
        probe = self._probes.get(source.binding.connector)
        if probe is None:
            return ProbeReport(
                status="unavailable",
                detail=f"no reader is registered for connector {source.binding.connector!r}",
                collected_at=collected_now(),
            )

        async def fetch() -> ProbeReport:
            return await probe.metadata(source)

        report = await self._cache.get(("metadata", source.source_id), fetch)
        return report

    def _resolve(self, token: str) -> NodeRef:
        ref = decode_node(token)
        if ref.kind == "use_case":
            if self._registry.use_case(ref.use_case_id) is None:
                raise InvalidNode("unknown use case")
        elif ref.kind == "source":
            if self._registry.source(ref.use_case_id, ref.source_id) is None:
                # Covers both "no such source" and "that source belongs to a
                # different use case". The client is told neither.
                raise InvalidNode("unknown source")
        return ref

    def _use_case(self, ref: NodeRef) -> UseCase:
        use_case = self._registry.use_case(ref.use_case_id)
        if use_case is None:
            raise InvalidNode("unknown use case")
        return use_case

    def _source(self, ref: NodeRef) -> InventorySource:
        source = self._registry.source(ref.use_case_id, ref.source_id)
        if source is None:
            raise InvalidNode("unknown source")
        return source

    def _require_enabled(self, source: InventorySource, selection: Selection) -> None:
        if not selection.enabled(source.source_id):
            raise SourceDisabled(source.source_id)

    def _breadcrumb(self, ref: NodeRef) -> list[str]:
        trail = ["Data sources"]
        use_case = self._registry.use_case(ref.use_case_id)
        if use_case is not None:
            trail.append(use_case.name)
            source = self._registry.source(ref.use_case_id, ref.source_id)
            if source is not None:
                trail.append(source.name)
        return trail

    def _empty_content(
        self,
        token: str,
        ref: NodeRef,
        source: InventorySource,
        *,
        status: DiscoveryStatus,
        detail: str,
        row_limit: int,
    ) -> ContentResponse:
        return ContentResponse(
            node=token,
            label=source.name,
            kind="source",
            breadcrumb=self._breadcrumb(ref),
            use_case_id=source.use_case_id,
            source_id=source.source_id,
            status=status,
            content_kind="none",
            row_limit=row_limit,
            provenance=source.provenance or DEFAULT_PROVENANCE,
            error=sanitize_detail(detail) or None,
            observed_at=collected_now(),
        )


def probe_names(probes: Mapping[str, SourceProbe]) -> Sequence[str]:
    """Registered connector names, for a startup log or a health payload."""
    return tuple(sorted(probes))


__all__ = [
    "DEFAULT_METADATA_TTL_SECS",
    "DEFAULT_PREVIEW_ROWS",
    "DEFAULT_PROVENANCE",
    "MAX_PREVIEW_ROWS",
    "InventoryService",
    "ProbeReport",
    "SourceDisabled",
    "SourceProbe",
    "probe_names",
]
