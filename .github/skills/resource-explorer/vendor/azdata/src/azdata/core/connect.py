"""The injection seam — one call wires every connector.

WHY THIS EXISTS
---------------
Adoption cost is what decides whether a box gets used. Everything else in
this package is constructor-injected and individually testable, which is
correct and verbose. :func:`connect` is the one-line path: hand it a
config and, optionally, a credential provider, and take connectors off the
result.

    connectors = connect(AzureDataConfig.from_env())
    rows = await connectors.kql.execute("Events | take 10")

Connectors are built lazily and cached, so an unconfigured service costs
nothing and a missing SDK is never imported. Everything is overridable:
pass your own credential provider for a cross-tenant identity, or build a
connector directly when you need per-request targets.

THE MUTATING PLANES ARE NOT PROPERTIES
--------------------------------------
``connectors.search`` is a property because a process has one search
endpoint. ``connectors.documents(...)`` and ``connectors.provision_*(...)``
are methods that take an explicit :class:`WritePolicy` or
:class:`ProvisionPolicy`, because there is no safe default grant and a
property would have to invent one. Asking for a writer is the moment the
caller states what it intends to mutate.

DEPENDENCIES
------------
Standard library. The SDKs load on first use, per connector.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from azdata.core.config import AzureDataConfig
from azdata.cosmos.read import CosmosContainer
from azdata.cosmos.write import CosmosItems
from azdata.cosmos.deploy import (
    CosmosAccountProvisioner,
    CosmosContainerProvisioner,
    CosmosDatabaseProvisioner,
)
from azdata.core.credentials import credential_provider_for
from azdata.core.crud import WritePolicy
from azdata.fabric_graph.read import GraphConnector
from azdata.gremlin.read import GremlinConnector
from azdata.gremlin.write import GremlinElements
from azdata.gremlin.deploy import GremlinDatabaseProvisioner, GremlinGraphProvisioner
from azdata.kusto.read import KqlConnector
from azdata.core.provision import ProvisionPolicy, Provisioner
from azdata.search.read import SearchConnector
from azdata.search.write import SearchDocuments
from azdata.search.deploy import SearchIndexProvisioner, SearchServiceProvisioner

logger = logging.getLogger(__name__)


class UnconfiguredProvisioner(Provisioner):
    """Stands in for a provisioner whose coordinates are unset.

    A ``from_config`` that cannot build returns an error envelope string,
    which is honest but gives the caller a union type to unpack at every
    call site. This restores one type: every method answers with the same
    envelope explaining what is missing, and ``exists`` is False.
    """

    resource_kind = "unconfigured"

    def __init__(self, detail: str) -> None:
        super().__init__(name="", policy=ProvisionPolicy.read_only())
        self._detail = detail

    async def _do_describe(self) -> Any | None:
        return None

    async def _do_ensure(self, spec: Any) -> Any:
        raise RuntimeError(self._detail)

    async def _do_teardown(self) -> Any:
        raise RuntimeError(self._detail)

    async def describe(self) -> str:
        return self._detail

    async def ensure(self, spec: Any, *, verify: bool | None = None) -> str:
        return self._detail

    async def teardown(self, *, verify: bool | None = None) -> str:
        return self._detail


def _or_unconfigured(built: Any) -> Any:
    """Normalise a ``from_config`` that answered with an error envelope."""
    return UnconfiguredProvisioner(built) if isinstance(built, str) else built


def _policy_key(policy: WritePolicy) -> str:
    """A cache-key fragment that distinguishes one grant from another."""
    return (
        f"w{int(policy.allow_write)}d{int(policy.allow_delete)}"
        f"v{int(policy.verify_writes)}b{policy.max_batch}"
    )


class Connectors:
    """Lazily built, cached connectors sharing one config and credential.

    Attribute access constructs on first use. Construction does not
    connect: the first ``execute`` does. So building this object is safe
    at import time and in a health check.
    """

    def __init__(
        self,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
    ) -> None:
        self.config = config
        self.credential_provider = credential_provider
        self._cache: dict[str, Any] = {}

    def _build(self, key: str, factory: Callable[[], Any]) -> Any:
        cached = self._cache.get(key)
        if cached is None:
            cached = factory()
            self._cache[key] = cached
        return cached

    @property
    def gremlin(self) -> GremlinConnector:
        """Cosmos DB Gremlin graph."""
        return self._build(
            "gremlin",
            lambda: GremlinConnector.from_config(
                self.config, self.credential_provider
            ),
        )

    @property
    def kql(self) -> KqlConnector:
        """Fabric Eventhouse / Azure Data Explorer."""
        return self._build(
            "kql",
            lambda: KqlConnector.from_config(self.config, self.credential_provider),
        )

    @property
    def search(self) -> SearchConnector:
        """Azure AI Search."""
        return self._build(
            "search",
            lambda: SearchConnector.from_config(
                self.config, self.credential_provider
            ),
        )

    @property
    def graph(self) -> GraphConnector:
        """Fabric GraphModel (GQL over HTTPS)."""
        return self._build(
            "graph",
            lambda: GraphConnector.from_config(self.config, self.credential_provider),
        )

    def cosmos(self, database: str, container: str, **kwargs) -> CosmosContainer:
        """Return a Cosmos NoSQL container handle, cached per (db, container).

        Not a property because a process holds several containers, and each
        needs its own breaker so one failing container does not fail the
        others.
        """
        key = f"cosmos::{database}::{container}"
        return self._build(
            key,
            lambda: CosmosContainer.from_config(
                self.config,
                self.credential_provider(),
                database=database,
                container=container,
                breaker_name=f"cosmos:{database}.{container}",
                **kwargs,
            ),
        )

    def configured(self) -> dict[str, bool]:
        """Which services this config can reach. Cheap; performs no I/O."""
        c = self.config
        return {
            "gremlin": bool(c.gremlin_endpoint and c.gremlin_database and c.gremlin_graph),
            "kql": bool(c.kql_query_uri and c.kql_database),
            "search": bool(c.search_endpoint),
            "cosmos": bool(c.cosmos_endpoint),
            "graph": bool(c.fabric_graph_url),
            "management": bool(c.subscription_id and c.resource_group),
        }

    # ------------------------------------------------------------------
    # Write plane. Each takes an explicit policy; there is no safe default.
    #
    # The policy is part of every cache key. Keyed on the target alone, a
    # second request for the same index with a *narrower* policy would be
    # served the earlier, wider object — a caller that asked to be
    # read-only would silently hold a delete grant.
    # ------------------------------------------------------------------

    def documents(
        self,
        index_name: str,
        *,
        policy: WritePolicy,
        **kwargs: Any,
    ) -> SearchDocuments:
        """Azure AI Search document CRUD over one index."""
        return self._build(
            f"documents::{index_name}::{_policy_key(policy)}",
            lambda: SearchDocuments.from_config(
                self.config,
                self.credential_provider,
                index_name=index_name,
                policy=policy,
                **kwargs,
            ),
        )

    def items(
        self,
        database: str,
        container: str,
        *,
        partition_key_field: str,
        policy: WritePolicy,
        **kwargs: Any,
    ) -> CosmosItems:
        """Cosmos NoSQL item CRUD over one container.

        ``partition_key_field`` has no default. A wrong partition key makes
        a delete succeed while deleting nothing, so guessing it is worse
        than refusing to construct.
        """
        return self._build(
            f"items::{database}::{container}::{partition_key_field}::{_policy_key(policy)}",
            lambda: CosmosItems.from_config(
                self.config,
                self.credential_provider,
                database=database,
                container=container,
                partition_key_field=partition_key_field,
                policy=policy,
                **kwargs,
            ),
        )

    def elements(
        self,
        label: str,
        *,
        partition_key_field: str,
        policy: WritePolicy,
        **kwargs: Any,
    ) -> GremlinElements:
        """Cosmos Gremlin vertex CRUD over the configured graph."""
        return self._build(
            f"elements::{label}::{partition_key_field}::{_policy_key(policy)}",
            lambda: GremlinElements.from_config(
                self.config,
                self.credential_provider,
                label=label,
                partition_key_field=partition_key_field,
                policy=policy,
                **kwargs,
            ),
        )

    # ------------------------------------------------------------------
    # Deploy plane. Unconfigured coordinates yield a provisioner that
    # answers every call with the envelope naming what is missing.
    # ------------------------------------------------------------------

    def provision_search_service(self, *, policy: ProvisionPolicy) -> Any:
        return _or_unconfigured(
            SearchServiceProvisioner.from_config(
                self.config, self.credential_provider, policy=policy
            )
        )

    def provision_search_index(self, index_name: str, *, policy: ProvisionPolicy) -> Any:
        return _or_unconfigured(
            SearchIndexProvisioner.from_config(
                self.config, self.credential_provider, index_name=index_name, policy=policy
            )
        )

    def provision_cosmos_account(self, *, policy: ProvisionPolicy, name: str = "") -> Any:
        return _or_unconfigured(
            CosmosAccountProvisioner.from_config(
                self.config, self.credential_provider, policy=policy, name=name
            )
        )

    def provision_cosmos_database(self, database: str, *, policy: ProvisionPolicy) -> Any:
        return _or_unconfigured(
            CosmosDatabaseProvisioner.from_config(
                self.config, self.credential_provider, database=database, policy=policy
            )
        )

    def provision_cosmos_container(
        self, database: str, container: str, *, policy: ProvisionPolicy
    ) -> Any:
        return _or_unconfigured(
            CosmosContainerProvisioner.from_config(
                self.config,
                self.credential_provider,
                database=database,
                container=container,
                policy=policy,
            )
        )

    def provision_gremlin_database(self, *, policy: ProvisionPolicy, name: str = "") -> Any:
        return _or_unconfigured(
            GremlinDatabaseProvisioner.from_config(
                self.config, self.credential_provider, name=name, policy=policy
            )
        )

    def provision_gremlin_graph(
        self, *, policy: ProvisionPolicy, name: str = "", database_name: str = ""
    ) -> Any:
        return _or_unconfigured(
            GremlinGraphProvisioner.from_config(
                self.config,
                self.credential_provider,
                name=name,
                database_name=database_name,
                policy=policy,
            )
        )

    async def aclose(self) -> None:
        """Close every built connector. The credential is not closed (G8)."""
        for key, connector in list(self._cache.items()):
            close = getattr(connector, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                logger.warning("azdata.close_failed connector=%s: %s", key, exc)
        self._cache.clear()


def connect(
    config: AzureDataConfig | None = None,
    *,
    credential_provider: Callable[[], Any] | None = None,
) -> Connectors:
    """Wire every connector from one config. This is the integration point.

    Args:
        config: Coordinates. Defaults to :meth:`AzureDataConfig.from_env`.
        credential_provider: Zero-argument callable returning a
            ``TokenCredential``. Defaults to the three-tier resolver,
            carrying the config's service principal when one is set.
    """
    resolved_config = config if config is not None else AzureDataConfig.from_env()
    provider = credential_provider or credential_provider_for(resolved_config)
    return Connectors(resolved_config, provider)


__all__ = ["Connectors", "UnconfiguredProvisioner", "connect"]
