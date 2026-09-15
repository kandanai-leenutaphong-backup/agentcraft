"""Datastore capability for Azure Data Explorer, Cosmos DB for Gremlin, and Azure AI Search.

Two planes, deliberately kept apart:

* **Read plane** — bounded, read-only content and discovery. Failure is a value,
  never an exception, and six statuses survive to whatever renders them. Adopted
  from `azdata` 3.4.0 as a subset; `PROVENANCE.md` records the origin of each file.
* **CRUD plane** — the full connector surface: ADX query, command, ingest,
  provision and repository operations; Gremlin read and idempotent upsert; Azure
  AI Search index and document CRUD. It raises typed errors, as its callers expect.

A reader never widens into a writer, and a writer never inherits the reader's
"failure is a value" contract. `KustoReader` and `AdxConnector` both reach ADX and
neither is the other's replacement.

**Azure AI Search is re-exported, not reimplemented.** `SearchIndexClient` and its
values are the objects defined in `template_foundations.azure_search`; this module makes
them reachable from one import without a second copy of the write path.

IMPORT COST
-----------
Importing this module touches the standard library and nothing else. The read
plane loads its SDK on first call through `load()`; the CRUD plane resolves through
a module `__getattr__`, so `from ... import ContentBounds` costs nothing on a
machine with no Azure SDK, while `from ... import AdxConnector` imports
`azure-kusto-data` and `azure-kusto-ingest` at that moment — exactly as the
connector's own package did. `GremlinGraph` needs `gremlinpython` only when one is
constructed. Azure AI Search is REST over the standard library and needs no SDK.

`DEFAULT_BATCH` here is the Gremlin traversal-chain batch of 20. Azure AI Search's
document batch size is `template_foundations.azure_search.client.DEFAULT_BATCH` and is
deliberately not re-exported under the same name.

PUBLIC SURFACE
--------------
    Read plane:
    ContentBounds / ContentPayload / ContentResult / ContentForm
    bounded_content / content_failure / normalize_sample / RowSample
    normalize_rows
    DiscoveryStatus / DISCOVERY_STATUSES / DiscoveryBounds / DiscoveryScope
    DiscoveryNode / DiscoveryResult / bounded_discovery / discovery_failure
    classify_discovery_failure / collected_now / normalize_attributes
    DiscoveryAbsent / DiscoveryUnreachable
    sanitize_detail / error_envelope / degraded_envelope / is_error
    KustoReader / KustoTableInspector / SearchReader
    GraphReader / GraphTarget / GraphElementSource
    MissingDependency and the optional-SDK test seam

    CRUD plane:
    AdxConnector / AdxClient / AdxConfig / AdxProvisioner / ClusterInfo
    CrudRepository / UpsertStrategy / Ingestor / IngestMode / IngestResult
    ColumnSpec / TableSchema / QueryResult and the Adx* error hierarchy
    GremlinGraph / GremlinSettings / GremlinError / encode_properties
    PROPERTY_TEXT_LIMIT / DEFAULT_BATCH
    SearchIndexClient / SearchConfig / IndexSpec / FieldSpec / VectorSpec
    render_index / safe_key / valid_index_name / SearchError / SearchConfigError

Everything above imports from this module. Reaching into a submodule from outside
`app/components/` crosses the boundary's public surface.

DEPENDENCIES
------------
Standard library, plus one Azure SDK per surface actually used: `azure-kusto-data`
(`KustoReader`, `AdxClient`), `azure-kusto-ingest` (`Ingestor`), `azure-mgmt-kusto`
(`AdxProvisioner`), `azure-search-documents` (`SearchReader`), `gremlinpython`
(`GremlinGraph`). `GraphReader` imports nothing — its transport is injected, and
Azure AI Search CRUD is REST over the standard library.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from template_foundations.azure_search import (
    DEFAULT_SEARCH_API_VERSION,
    SEARCH_SCOPE,
    FieldSpec,
    IndexSpec,
    SearchConfig,
    SearchConfigError,
    SearchError,
    SearchIndexClient,
    Transport,
    VectorSpec,
    render_index,
    safe_key,
    valid_index_name,
)
from .core.content import (
    DEFAULT_CONTENT_TIMEOUT_SECS,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_CELL_CHARS,
    DEFAULT_MAX_COLUMNS,
    DEFAULT_MAX_ROWS,
    ContentBounds,
    ContentForm,
    ContentPayload,
    ContentResult,
    RowSample,
    bounded_content,
    content_failure,
    normalize_rows,
    normalize_sample,
)
from .core.discover import (
    DISCOVERY_STATUSES,
    DiscoveryAbsent,
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    DiscoveryStatus,
    DiscoveryUnreachable,
    bounded_discovery,
    classify_discovery_failure,
    collected_now,
    discovery_failure,
    model_field,
    normalize_attributes,
)
from .core.envelope import (
    degraded_envelope,
    error_envelope,
    is_error,
    is_ok,
    sanitize_detail,
    success_envelope,
)
from .core.optional import (
    KNOWN_DISTRIBUTIONS,
    MissingDependency,
    clear_overrides,
    load,
    override,
    override_missing,
)
from .graph.content import GraphElement, GraphElementSource, GraphReader, GraphTarget
from .kusto.content import TABLE_NAME, KustoReader
from .kusto.metadata import KustoTableInspector, TableFacts
from .kusto.read import shape_kusto_response
from .search.content import MATCH_ALL, SearchReader

if TYPE_CHECKING:  # the same names, resolved statically; at runtime they are lazy
    from .graph.control import cosmos_ensure_graph, cosmos_primary_key
    from .graph.connector import (
        DEFAULT_BATCH,
        PROPERTY_TEXT_LIMIT,
        GremlinError,
        GremlinGraph,
        GremlinSettings,
        encode_properties,
    )
    from .kusto.client import AdxClient
    from .kusto.config import AdxConfig
    from .kusto.connector import AdxConnector
    from .kusto.crud import CrudRepository, UpsertStrategy
    from .kusto.errors import (
        AdxAuthError,
        AdxConfigError,
        AdxError,
        AdxIdentifierError,
        AdxIngestionError,
        AdxProvisioningError,
        AdxQueryError,
        AdxTimeoutError,
    )
    from .kusto.ingest import IngestMode, IngestResult, Ingestor
    from .kusto.models import ColumnSpec, QueryResult, TableSchema
    from .kusto.provision import AdxProvisioner, ClusterInfo

__version__ = "3.4.0+perth.2"

# Public name -> the submodule that defines it, resolved on first attribute access.
# `kusto.client`, `kusto.ingest` and `kusto.retry` import their SDK at module scope,
# so eagerly re-exporting one name from them would make `import ContentBounds` fail
# on a machine that has no Kusto SDK.
_LAZY_EXPORTS: dict[str, str] = {
    "AdxAuthError": ".kusto.errors",
    "AdxClient": ".kusto.client",
    "AdxConfig": ".kusto.config",
    "AdxConfigError": ".kusto.errors",
    "AdxConnector": ".kusto.connector",
    "AdxError": ".kusto.errors",
    "AdxIdentifierError": ".kusto.errors",
    "AdxIngestionError": ".kusto.errors",
    "AdxProvisioner": ".kusto.provision",
    "AdxProvisioningError": ".kusto.errors",
    "AdxQueryError": ".kusto.errors",
    "AdxTimeoutError": ".kusto.errors",
    "ClusterInfo": ".kusto.provision",
    "ColumnSpec": ".kusto.models",
    "CrudRepository": ".kusto.crud",
    "DEFAULT_BATCH": ".graph.connector",
    "GremlinError": ".graph.connector",
    "GremlinGraph": ".graph.connector",
    "GremlinSettings": ".graph.connector",
    "IngestMode": ".kusto.ingest",
    "IngestResult": ".kusto.ingest",
    "Ingestor": ".kusto.ingest",
    "PROPERTY_TEXT_LIMIT": ".graph.connector",
    "QueryResult": ".kusto.models",
    "TableSchema": ".kusto.models",
    "UpsertStrategy": ".kusto.crud",
    "cosmos_ensure_graph": ".graph.control",
    "cosmos_primary_key": ".graph.control",
    "encode_properties": ".graph.connector",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_path, __name__), name)
    globals()[name] = value  # bind it, so a second access skips this entirely
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "DEFAULT_BATCH",
    "DEFAULT_CONTENT_TIMEOUT_SECS",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_CELL_CHARS",
    "DEFAULT_MAX_COLUMNS",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_SEARCH_API_VERSION",
    "DISCOVERY_STATUSES",
    "KNOWN_DISTRIBUTIONS",
    "MATCH_ALL",
    "PROPERTY_TEXT_LIMIT",
    "SEARCH_SCOPE",
    "TABLE_NAME",
    "AdxAuthError",
    "AdxClient",
    "AdxConfig",
    "AdxConfigError",
    "AdxConnector",
    "AdxError",
    "AdxIdentifierError",
    "AdxIngestionError",
    "AdxProvisioner",
    "AdxProvisioningError",
    "AdxQueryError",
    "AdxTimeoutError",
    "ClusterInfo",
    "ColumnSpec",
    "ContentBounds",
    "ContentForm",
    "ContentPayload",
    "ContentResult",
    "CrudRepository",
    "DiscoveryAbsent",
    "DiscoveryBounds",
    "DiscoveryNode",
    "DiscoveryResult",
    "DiscoveryScope",
    "DiscoveryStatus",
    "DiscoveryUnreachable",
    "FieldSpec",
    "GraphElement",
    "GraphElementSource",
    "GraphReader",
    "GraphTarget",
    "GremlinError",
    "GremlinGraph",
    "GremlinSettings",
    "IndexSpec",
    "IngestMode",
    "IngestResult",
    "Ingestor",
    "KustoReader",
    "KustoTableInspector",
    "MissingDependency",
    "QueryResult",
    "RowSample",
    "SearchConfig",
    "SearchConfigError",
    "SearchError",
    "SearchIndexClient",
    "SearchReader",
    "TableFacts",
    "TableSchema",
    "Transport",
    "UpsertStrategy",
    "VectorSpec",
    "__version__",
    "bounded_content",
    "bounded_discovery",
    "classify_discovery_failure",
    "clear_overrides",
    "collected_now",
    "content_failure",
    "degraded_envelope",
    "discovery_failure",
    "encode_properties",
    "error_envelope",
    "is_error",
    "is_ok",
    "load",
    "model_field",
    "normalize_attributes",
    "normalize_rows",
    "normalize_sample",
    "override",
    "override_missing",
    "render_index",
    "safe_key",
    "sanitize_detail",
    "shape_kusto_response",
    "success_envelope",
    "valid_index_name",
]
