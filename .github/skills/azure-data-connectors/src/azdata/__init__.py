"""azdata — connect to Azure data services with identity, limits and a
failure model already in place.

WHY THIS EXISTS
---------------
The distance between "the SDK sample works" and "this survives a shared
capacity, an expiring token and a bad month for the service" is about a
thousand lines, and every team writes them again. This package is those
lines, extracted from a running system, for five services:

| Connector           | Service                                    |
| ------------------- | ------------------------------------------ |
| ``GremlinConnector``| Cosmos DB Gremlin (TinkerPop, WebSocket)   |
| ``KqlConnector``    | Fabric Eventhouse / Azure Data Explorer    |
| ``SearchConnector`` | Azure AI Search (keyword + vector + semantic) |
| ``GraphConnector``  | Fabric GraphModel (GQL over HTTPS)         |
| ``CosmosContainer`` | Cosmos DB NoSQL                            |

THREE PLANES
------------
The read plane above answers questions. Two more exist because an agent
that has to stand a service up, load it, query it and tear it down inside
one run has no deployment pipeline in that loop.

* **Read** — ``execute`` on a connector. Guarded read-only, row-capped.
* **Write** — ``SearchDocuments`` / ``CosmosItems`` / ``GremlinElements`` /
  ``BlobObjects``. Create, Retrieve, Upload, Delete. Denied until a
  :class:`WritePolicy` grants it, and verified by reading the state back.
  ``BlobObjects`` writes objects and has no container verb at all: the role
  that grants a blob write also grants container lifecycle, so the only
  place that line can be drawn is in code.
* **Deploy** — the ``*Provisioner`` classes. Idempotent ``ensure``, gated
  ``teardown``, and a mandatory read-back because ARM returns
  ``Succeeded`` for writes an Azure Policy silently reverts.
* **Observe** — the ``*Stats`` classes. Key counters for a target, from
  the data plane, the management plane and Azure Monitor. A stats call
  never fails wholesale because one counter was unavailable, and never
  omits one silently: what could not be collected is named in ``partial``.
* **Verify** — ``verify_effect`` and the ``*Keys`` classes. Snapshot,
  operate, snapshot, diff. It answers the question the write plane cannot:
  *did anything change that I did not ask for*. A mismatch is an error
  envelope, never ``ok`` with ``matched: false``.
* **Discover** — the ``*Discoverer`` classes and ``build_discovery_registry``.
  Enumerate one level at a time, bounded in items and seconds, ordered
  deterministically. A failure is a ``DiscoveryStatus``, never an
  exception, because a browsable tree renders a dark branch rather than
  losing the view — and it distinguishes ``forbidden`` from ``unreachable``
  because a role grant fixes one and does nothing for the other.* **Content** — the ``*Reader`` classes and ``build_estate_access``. The
  discover plane answers "what is here"; this one answers "what does it
  say". One bounded read of one addressable item — a blob's bytes, a
  container's documents, a table's rows, a resource's own ARM JSON — with
  the same six statuses, because a forbidden blob and a forbidden container
  are the same operator problem. It reports the media type the service
  claimed and never decides what the bytes *mean*: sniffing is presentation.
Common behaviour across all three:

* **Identity, never keys.** ``TokenCredential`` and RBAC. Same code path
  for managed identity in Azure and ``az login`` locally.
* **Failure is a value.** Connectors return an error or degraded envelope
  rather than raising an SDK exception into a caller that cannot handle one.
* **Bounded work.** Read-only guards and row caps by default; a circuit
  breaker per endpoint; a semaphore where capacity is shared.
* **Denied by default.** Nothing mutates data or infrastructure until a
  policy object says it may, and delete is always a separate grant.
* **Nothing imported until used.** SDKs load per connector on first call.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
The single injection seam is :func:`connect`, taking an
:class:`AzureDataConfig` and a credential provider. Nothing here reads an
application's settings object, and result projection is always an injected
callable, so no field name from a caller's schema appears in this package.

PUBLIC SURFACE
--------------
``connect`` / ``Connectors``       — wire everything from one config.
``AzureDataConfig``                — coordinates, ``from_env()`` included.
``GremlinConnector`` and friends   — build one connector directly.
``SearchDocuments`` / ``CosmosItems`` / ``GremlinElements`` — the write plane.
``BlobObjects``                    — blob object writes, never the container.
``WritePolicy`` / ``ProvisionPolicy`` — the grants that unlock mutation.
``*Provisioner``                   — the deploy plane.
``ThrottleGate`` / ``CircuitBreaker`` / ``registry`` — resilience primitives.
``build_discovery_registry`` / ``*Discoverer`` — the discover plane.
``DiscoveryScope`` / ``DiscoveryBounds`` / ``DiscoveryResult`` — its types.
``build_estate_access`` / ``EstateAccess`` — subscription-wide browsing.
``ArmApi``                         — ``GET`` any resource, any api-version.
``kql_literal``                    — escape a value for a Resource Graph query.
``EstateReader`` / ``BlobReader`` / ``CosmosReader`` / ``KustoReader`` /
``SearchReader`` / ``LogsReader``  — the content plane.
``ContentBounds`` / ``ContentPayload`` / ``ContentResult`` — its types.
``validate_read_only`` / ``ensure_limit`` — query guardrails, usable alone.
``error_envelope`` / ``degraded_envelope`` / ``is_error`` — the result shape.
``MissingDependency``              — an SDK for a used connector is absent.

DEPENDENCIES
------------
Standard library, plus one SDK per connector actually used. See
``requirements.txt``.

READ NEXT
---------
``SKILL.md`` to use it, ``GOTCHAS.md`` when something is wrong,
``CONTRACT.md`` to reimplement it, ``README.md`` for why it is shaped this
way.
"""

from __future__ import annotations

from azdata.arm import ArmDiscoverer
from azdata.blobs import BlobDiscoverer, BlobObjects, BlobReader, blob_endpoint
from azdata.core.breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    ThrottleError,
    ThrottleGate,
    get_gate,
    registry,
    reset_gates,
)
from azdata.core.config import AzureDataConfig
from azdata.core.connect import Connectors, connect
from azdata.core.content import (
    DEFAULT_CONTENT_TIMEOUT_SECS,
    DEFAULT_MAX_BYTES,
    ContentBounds,
    ContentForm,
    ContentPayload,
    ContentResult,
    bounded_content,
    content_failure,
    normalize_rows,
)
from azdata.core.credentials import (
    credential_provider_for,
    default_credential_provider,
    reset_credential_cache,
    running_in_azure,
)
from azdata.core.discover import (
    DISCOVERY_STATUSES,
    Discoverer,
    DiscovererRegistry,
    DiscoveryAbsent,
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    DiscoveryStatus,
    DiscoveryUnreachable,
    bounded_discovery,
    build_discovery_registry,
    classify_discovery_failure,
    collected_now,
    discovery_failure,
)
from azdata.core.crud import (
    DEFAULT_MAX_BATCH,
    CrudConnector,
    IngestConnector,
    VerificationFailed,
    WritePolicy,
    WriteRefused,
)
from azdata.core.envelope import (
    degraded_envelope,
    error_envelope,
    is_error,
    is_ok,
    sanitize_detail,
    success_envelope,
)
from azdata.core.guardrails import (
    DEFAULT_MAX_ROWS,
    LANGUAGES,
    ensure_limit,
    limit_injector,
    read_only_validator,
    validate_read_only,
)
from azdata.core.journal import JournalRecord, OperationJournal, journal
from azdata.core.metrics import (
    MetricRead,
    MetricsReader,
    MetricsUnavailable,
    read_stats,
)
from azdata.core.observe import (
    StatSource,
    StatsProvider,
    StatUnavailable,
    collector,
    stats_envelope,
)
from azdata.core.optional import MissingDependency
from azdata.core.provision import (
    ProvisionDrift,
    ProvisionPolicy,
    ProvisionRefused,
    Provisioner,
    find_drift,
)
from azdata.core.token import TokenCache
from azdata.core.verify import (
    Effect,
    KeySource,
    StateDelta,
    StateSnapshot,
    capture,
    key_digest,
    snapshot,
    verify_effect,
)
from azdata.cosmos import (
    CosmosAccountProvisioner,
    CosmosContainer,
    CosmosContainerProvisioner,
    CosmosDatabaseProvisioner,
    CosmosDiscoverer,
    CosmosItems,
    CosmosKeys,
    CosmosStats,
    CosmosUnavailable,
)
from azdata.cosmos.content import CosmosReader, cosmos_endpoint
from azdata.estate import (
    ArmApi,
    EstateAccess,
    EstateDiscoverer,
    EstateReader,
    build_estate_access,
    kql_literal,
    name_of,
    redact_credentials,
    resource_group_of,
    subscription_of,
    type_of,
)
from azdata.fabric_graph import GraphConnector, GraphRetryBudget, GraphStats
from azdata.gremlin import (
    GremlinConnector,
    GremlinDatabaseProvisioner,
    GremlinDiscoverer,
    GremlinElements,
    GremlinGraphProvisioner,
    GremlinKeys,
    GremlinStats,
    GremlinTarget,
    GremlinVerifyError,
    GremlinWriteError,
)
from azdata.kusto import (
    ALLOWED_COMMANDS,
    KqlConnector,
    KqlTarget,
    KustoClusterProvisioner,
    KustoDatabaseProvisioner,
    KustoDeployError,
    KustoDiscoverer,
    KustoIngest,
    KustoIngestError,
    KustoKeys,
    KustoStats,
    KustoTableProvisioner,
    KustoVerifyError,
    shape_kusto_response,
)
from azdata.kusto.content import KustoReader
from azdata.live import (
    Environment,
    LiveEnvironmentError,
    NameUnavailable,
    ResourcePlan,
    RolePlan,
    TeardownRefused,
)
from azdata.logs import LogsDiscoverer, LogsReader
from azdata.registry import RegistryDiscoverer
from azdata.search import (
    SearchConnector,
    SearchDiscoverer,
    SearchDocuments,
    SearchIndexProvisioner,
    SearchKeys,
    SearchServiceProvisioner,
    SearchStats,
)
from azdata.search.content import SearchReader
from azdata.sqldb import (
    DEFAULT_TSQL_MAX_ROWS,
    SQL_SCOPE,
    SqlConnector,
    SqlGrantFailed,
    SqlGrantState,
    SqlPrincipals,
    SqlTarget,
    SqlUnavailable,
    TsqlRefused,
    bind_names,
    entra_sid,
    guard_tsql,
    list_tables,
    owned_user_name,
    quote_identifier,
    sql_server_host,
    sql_target_from_resource_id,
    validate_tsql_read_only,
)

__version__ = "3.4.0"

__all__ = [
    "ALLOWED_COMMANDS",
    "ArmApi",
    "ArmDiscoverer",
    "AzureDataConfig",
    "BlobDiscoverer",
    "BlobObjects",
    "BlobReader",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitState",
    "Connectors",
    "ContentBounds",
    "ContentForm",
    "ContentPayload",
    "ContentResult",
    "CosmosAccountProvisioner",
    "CosmosContainer",
    "CosmosContainerProvisioner",
    "CosmosDatabaseProvisioner",
    "CosmosDiscoverer",
    "CosmosItems",
    "CosmosKeys",
    "CosmosReader",
    "CosmosStats",
    "CosmosUnavailable",
    "CrudConnector",
    "DEFAULT_CONTENT_TIMEOUT_SECS",
    "DEFAULT_MAX_BATCH",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_TSQL_MAX_ROWS",
    "DISCOVERY_STATUSES",
    "Discoverer",
    "DiscovererRegistry",
    "DiscoveryAbsent",
    "DiscoveryBounds",
    "DiscoveryNode",
    "DiscoveryResult",
    "DiscoveryScope",
    "DiscoveryStatus",
    "DiscoveryUnreachable",
    "Effect",
    "Environment",
    "EstateAccess",
    "EstateDiscoverer",
    "EstateReader",
    "GraphConnector",
    "GraphRetryBudget",
    "GraphStats",
    "GremlinConnector",
    "GremlinDatabaseProvisioner",
    "GremlinDiscoverer",
    "GremlinElements",
    "GremlinGraphProvisioner",
    "GremlinKeys",
    "GremlinStats",
    "GremlinTarget",
    "GremlinVerifyError",
    "GremlinWriteError",
    "IngestConnector",
    "JournalRecord",
    "KeySource",
    "KqlConnector",
    "KqlTarget",
    "KustoClusterProvisioner",
    "KustoDatabaseProvisioner",
    "KustoDeployError",
    "KustoDiscoverer",
    "KustoIngest",
    "KustoIngestError",
    "KustoKeys",
    "KustoReader",
    "KustoStats",
    "KustoTableProvisioner",
    "KustoVerifyError",
    "LANGUAGES",
    "LiveEnvironmentError",
    "LogsDiscoverer",
    "LogsReader",
    "MetricRead",
    "MetricsReader",
    "MetricsUnavailable",
    "MissingDependency",
    "NameUnavailable",
    "OperationJournal",
    "ProvisionDrift",
    "ProvisionPolicy",
    "ProvisionRefused",
    "Provisioner",
    "RegistryDiscoverer",
    "ResourcePlan",
    "RolePlan",
    "SQL_SCOPE",
    "SearchConnector",
    "SearchDiscoverer",
    "SearchDocuments",
    "SearchIndexProvisioner",
    "SearchKeys",
    "SearchReader",
    "SearchServiceProvisioner",
    "SearchStats",
    "SqlConnector",
    "SqlGrantFailed",
    "SqlGrantState",
    "SqlPrincipals",
    "SqlTarget",
    "SqlUnavailable",
    "StatSource",
    "StatUnavailable",
    "StateDelta",
    "StateSnapshot",
    "StatsProvider",
    "TeardownRefused",
    "ThrottleError",
    "ThrottleGate",
    "TokenCache",
    "TsqlRefused",
    "VerificationFailed",
    "WritePolicy",
    "WriteRefused",
    "bind_names",
    "blob_endpoint",
    "bounded_content",
    "bounded_discovery",
    "build_discovery_registry",
    "build_estate_access",
    "capture",
    "classify_discovery_failure",
    "collected_now",
    "collector",
    "connect",
    "content_failure",
    "cosmos_endpoint",
    "credential_provider_for",
    "default_credential_provider",
    "degraded_envelope",
    "discovery_failure",
    "ensure_limit",
    "entra_sid",
    "error_envelope",
    "find_drift",
    "get_gate",
    "guard_tsql",
    "is_error",
    "is_ok",
    "journal",
    "key_digest",
    "kql_literal",
    "limit_injector",
    "list_tables",
    "name_of",
    "normalize_rows",
    "owned_user_name",
    "quote_identifier",
    "read_only_validator",
    "read_stats",
    "redact_credentials",
    "registry",
    "reset_credential_cache",
    "reset_gates",
    "resource_group_of",
    "running_in_azure",
    "sanitize_detail",
    "shape_kusto_response",
    "snapshot",
    "sql_server_host",
    "sql_target_from_resource_id",
    "stats_envelope",
    "subscription_of",
    "success_envelope",
    "type_of",
    "validate_read_only",
    "validate_tsql_read_only",
    "verify_effect",
]
