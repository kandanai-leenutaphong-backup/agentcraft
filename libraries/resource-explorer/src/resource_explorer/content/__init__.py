"""Bounded content and discovery contracts shared by catalogue probes."""

from .content import (
    DEFAULT_CONTENT_TIMEOUT_SECS, DEFAULT_MAX_BYTES, DEFAULT_MAX_CELL_CHARS,
    DEFAULT_MAX_COLUMNS, DEFAULT_MAX_ROWS, ContentBounds, ContentForm, ContentPayload,
    ContentResult, RowSample, bounded_content, content_failure, normalize_rows,
    normalize_sample,
)
from .discover import (
    DISCOVERY_STATUSES, DiscoveryAbsent, DiscoveryBounds, DiscoveryNode, DiscoveryResult,
    DiscoveryScope, DiscoveryStatus, DiscoveryUnreachable, bounded_discovery,
    classify_discovery_failure, collected_now, discovery_failure, model_field,
    normalize_attributes,
)
from .envelope import (
    degraded_envelope, error_envelope, is_error, is_ok, sanitize_detail, success_envelope,
)
from .optional import (
    KNOWN_DISTRIBUTIONS, MissingDependency, load,
)
from .graph import (GraphElement, GraphElementSource, GraphInspection, GraphInspectionUnavailable,
                    GraphReader, GraphTarget, graph_properties)

__all__ = [
    "DEFAULT_CONTENT_TIMEOUT_SECS", "DEFAULT_MAX_BYTES", "DEFAULT_MAX_CELL_CHARS",
    "DEFAULT_MAX_COLUMNS", "DEFAULT_MAX_ROWS", "DISCOVERY_STATUSES", "KNOWN_DISTRIBUTIONS",
    "ContentBounds", "ContentForm", "ContentPayload", "ContentResult", "DiscoveryAbsent",
    "DiscoveryBounds", "DiscoveryNode", "DiscoveryResult", "DiscoveryScope", "DiscoveryStatus",
    "DiscoveryUnreachable", "GraphElement", "GraphElementSource", "GraphReader", "GraphTarget",
    "GraphInspection", "GraphInspectionUnavailable", "graph_properties",
    "MissingDependency", "RowSample", "bounded_content", "bounded_discovery",
    "classify_discovery_failure", "collected_now", "content_failure",
    "degraded_envelope", "discovery_failure", "error_envelope", "is_error", "is_ok", "load",
    "model_field", "normalize_attributes", "normalize_rows", "normalize_sample",
    "sanitize_detail", "success_envelope",
]