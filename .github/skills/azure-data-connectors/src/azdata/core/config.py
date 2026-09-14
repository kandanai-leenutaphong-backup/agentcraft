"""Connection coordinates — one frozen config object, resolved once.

WHY THIS EXISTS
---------------
Endpoint strings read straight from ``os.environ`` deep inside a client
factory are unreviewable and untestable: nothing lists what the process
needs, and a typo surfaces as a runtime 401 rather than a startup error.
:class:`AzureDataConfig` is the single place environment is read. Build it
at the composition root, freeze it, and pass it down.

Every field defaults to empty. An unset service is *not configured*, and
its connector answers with an error envelope naming the missing variable
instead of raising deep inside an SDK.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Field names describe Azure services, never a consuming application. The
env prefix is a parameter (``AZDATA_`` by default), so a repository that
already ships ``COSMOS_GREMLIN_ENDPOINT`` can adopt the box without
renaming anything: ``AzureDataConfig.from_env(prefix="")``.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any

# Cosmos issues access tokens valid ~1 hour. Rebuild the Gremlin client when
# fewer than this many seconds remain so a query cannot race an expiry
# (GOTCHAS.md G1).
DEFAULT_TOKEN_REFRESH_MARGIN_SECS = 300

# Fabric REST tokens are cached and refreshed well before the 60-90 minute
# Entra expiry (GOTCHAS.md G9).
DEFAULT_TOKEN_STALE_SECS = 2700.0

# Ceiling on the keys a verification snapshot enumerates. Above it the
# snapshot samples deterministically and says so; a verification that
# silently degrades to a count comparison is the failure being designed out.
DEFAULT_VERIFY_MAX_KEYS = 5000


@dataclass(frozen=True)
class AzureDataConfig:
    """Every coordinate the connectors need. Empty string means unconfigured.

    Construct once at startup. Frozen so a request handler cannot mutate
    shared state; use :meth:`with_overrides` for a per-request variant.
    """

    # Cosmos DB Gremlin (Apache TinkerPop over WebSocket).
    gremlin_endpoint: str = ""
    gremlin_database: str = ""
    gremlin_graph: str = ""

    # Fabric Eventhouse / Azure Data Explorer (Kusto).
    kql_query_uri: str = ""
    kql_database: str = ""

    # Azure AI Search.
    search_endpoint: str = ""

    # Cosmos DB NoSQL.
    cosmos_endpoint: str = ""

    # Management plane. Empty means the deploy plane is unconfigured and its
    # provisioners answer with an error envelope naming what is missing,
    # rather than constructing a management client that 401s on first use.
    subscription_id: str = ""
    resource_group: str = ""
    location: str = ""
    search_service_name: str = ""
    cosmos_account_name: str = ""
    gremlin_account_name: str = ""

    # Fabric GraphModel (GQL over HTTPS).
    fabric_api_url: str = "https://api.fabric.microsoft.com/v1"
    fabric_workspace_id: str = ""
    fabric_graph_model_id: str = ""
    fabric_scope: str = "https://api.fabric.microsoft.com/.default"

    # Cross-tenant service principal, all three or none. Empty means use the
    # ambient identity (managed identity in Azure, az login locally).
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = field(default="", repr=False)  # never echo a secret

    # Shared-capacity throttle. Fabric bills concurrency against a fixed
    # capacity unit, so the semaphore matters more than the retry budget.
    max_concurrent: int = 2
    breaker_threshold: int = 3
    breaker_cooldown_secs: float = 60.0
    breaker_max_cooldown_secs: float = 300.0

    # Row caps injected into queries that arrive without one.
    max_rows: int = 500
    token_refresh_margin_secs: int = DEFAULT_TOKEN_REFRESH_MARGIN_SECS
    token_stale_secs: float = DEFAULT_TOKEN_STALE_SECS

    # Verification bound. Clamped to >= 1: a cap of 0 would enumerate
    # nothing and digest the empty set, which matches every state.
    verify_max_keys: int = DEFAULT_VERIFY_MAX_KEYS

    @property
    def service_principal(self) -> tuple[str, str, str] | None:
        """The SP triple when complete, else None. Partial config is ignored.

        Returning None on a partial triple is deliberate: a half-set service
        principal must fall through to the ambient identity rather than
        construct a credential that fails on first use.
        """
        if self.tenant_id and self.client_id and self.client_secret:
            return (self.tenant_id, self.client_id, self.client_secret)
        return None

    @property
    def fabric_graph_url(self) -> str:
        """The GQL executeQuery URL, or "" when the graph is unconfigured."""
        if not self.fabric_workspace_id or not self.fabric_graph_model_id:
            return ""
        return (
            f"{self.fabric_api_url.rstrip('/')}"
            f"/workspaces/{self.fabric_workspace_id}"
            f"/graphmodels/{self.fabric_graph_model_id}/executeQuery"
        )

    def fabric_metadata_url(self) -> str:
        """The GraphModel metadata URL used by the health probe."""
        if not self.fabric_workspace_id or not self.fabric_graph_model_id:
            return ""
        return (
            f"{self.fabric_api_url.rstrip('/')}"
            f"/workspaces/{self.fabric_workspace_id}"
            f"/graphmodels/{self.fabric_graph_model_id}"
        )

    def with_overrides(self, **kwargs: Any) -> "AzureDataConfig":
        """Return a copy with fields replaced — per-request coordinates."""
        return replace(self, **kwargs)

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        prefix: str = "AZDATA_",
    ) -> "AzureDataConfig":
        """Build from environment variables.

        Args:
            env: Mapping to read. Defaults to ``os.environ``. Injectable so
                tests never mutate process state.
            prefix: Variable prefix. Pass ``""`` to adopt names a repository
                already sets (``GREMLIN_ENDPOINT`` and friends).

        Note:
            ``max_concurrent`` is clamped to a minimum of 1. An operator
            typo of ``0`` would otherwise build ``asyncio.Semaphore(0)`` and
            deadlock every call for the process lifetime (GOTCHAS.md G6).
        """
        src = os.environ if env is None else env

        def get(name: str, default: str = "") -> str:
            return src.get(f"{prefix}{name}", default).strip()

        def get_int(name: str, default: int) -> int:
            raw = get(name)
            try:
                return int(raw) if raw else default
            except ValueError:
                return default

        def get_float(name: str, default: float) -> float:
            raw = get(name)
            try:
                return float(raw) if raw else default
            except ValueError:
                return default

        defaults = cls()
        return cls(
            gremlin_endpoint=get("GREMLIN_ENDPOINT"),
            gremlin_database=get("GREMLIN_DATABASE"),
            gremlin_graph=get("GREMLIN_GRAPH"),
            kql_query_uri=get("KQL_QUERY_URI"),
            kql_database=get("KQL_DATABASE"),
            search_endpoint=get("SEARCH_ENDPOINT"),
            cosmos_endpoint=get("COSMOS_ENDPOINT"),
            subscription_id=get("SUBSCRIPTION_ID"),
            resource_group=get("RESOURCE_GROUP"),
            location=get("LOCATION"),
            search_service_name=get("SEARCH_SERVICE_NAME"),
            cosmos_account_name=get("COSMOS_ACCOUNT_NAME"),
            gremlin_account_name=get("GREMLIN_ACCOUNT_NAME"),
            fabric_api_url=get("FABRIC_API_URL", defaults.fabric_api_url),
            fabric_workspace_id=get("FABRIC_WORKSPACE_ID"),
            fabric_graph_model_id=get("FABRIC_GRAPH_MODEL_ID"),
            fabric_scope=get("FABRIC_SCOPE", defaults.fabric_scope),
            tenant_id=get("TENANT_ID"),
            client_id=get("CLIENT_ID"),
            client_secret=get("CLIENT_SECRET"),
            max_concurrent=max(1, get_int("MAX_CONCURRENT", defaults.max_concurrent)),
            breaker_threshold=get_int("BREAKER_THRESHOLD", defaults.breaker_threshold),
            breaker_cooldown_secs=get_float(
                "BREAKER_COOLDOWN_SECS", defaults.breaker_cooldown_secs
            ),
            max_rows=get_int("MAX_ROWS", defaults.max_rows),
            verify_max_keys=max(
                1, get_int("VERIFY_MAX_KEYS", defaults.verify_max_keys)
            ),
        )


__all__ = ["DEFAULT_VERIFY_MAX_KEYS", "AzureDataConfig"]
