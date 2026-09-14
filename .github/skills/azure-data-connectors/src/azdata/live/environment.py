"""The live conformance environment — topology as data, lifecycle as code.

WHY THIS EXISTS
---------------
The deploy plane claims it can stand a data estate up, prove it, and take
it down. This module is that claim executed. It describes the five
resources of SPEC 7.1 declaratively and drives every one of them through
the package's own provisioners, so the environment *is* the test of the
provisioners. Nothing here shells out to ``az`` for anything the library
can do: a subprocess call would prove that the Azure CLI works, which was
never in doubt.

Four decisions are load-bearing.

**Every creation is followed by a read-back before the next step.** ARM
returns ``Succeeded`` for writes an Azure Policy reverts moments later, so
a create whose only evidence is the write response is not evidence. The
provisioners already re-read; ``up`` additionally re-reads the resource
group and records what it actually saw.

**``up`` is idempotent and resumable.** It is expected to be re-run after
a partial failure — an ADX cluster takes ten to fifteen minutes and an
agent run may end first. Every step tolerates its resource already
existing, and the cluster provisioner waits on an in-flight deployment
rather than starting a second one.

**Role propagation is polled, never slept.** RBAC is eventually
consistent; ``time.sleep(30)`` after an assignment is a guess that fails
under load and wastes half a minute when it would have worked instantly.
Each assignment is followed by a real data-plane call, retried against a
bounded budget, and the wait actually observed is reported and recorded.

**``down`` is tag-gated and cannot be reached by accident.** It refuses
unless the resource group carries ``azdata-live-owned=true``, and it
requires an explicit confirmation flag. A teardown that can reach a
resource group it did not create is a teardown that will eventually reach
the wrong one.

WHAT THIS IS NOT
----------------
Not infrastructure-as-code and not a general environment manager. One
topology, named here, for this package's live conformance suite. The
resource names below are neutral defaults; the subscription is never
defaulted and every name is overridable by the caller.

DEPENDENCIES
------------
Standard library, plus — loaded on first use, only for the commands that
need them — ``azure-mgmt-resource`` (resource group and the Log Analytics
workspace), ``azure-mgmt-authorization`` (RBAC), and the service SDKs the
provisioners already load.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from azdata.core.breaker import get_gate
from azdata.core.crud import WritePolicy
from azdata.core.envelope import is_error
from azdata.core.optional import load
from azdata.core.provision import ProvisionPolicy
from azdata.cosmos.deploy import (
    CosmosAccountProvisioner,
    CosmosContainerProvisioner,
    CosmosDatabaseProvisioner,
)
from azdata.cosmos.deploy import build_management_client as build_cosmos_client
from azdata.gremlin.deploy import GremlinDatabaseProvisioner, GremlinGraphProvisioner
from azdata.kusto.deploy import (
    KustoClusterProvisioner,
    KustoDatabaseProvisioner,
    KustoTableProvisioner,
    build_management_client as build_kusto_client,
    cluster_policy,
    lift_kusto_model,
)
from azdata.kusto.read import KqlConnector, KqlTarget
from azdata.kusto.write import KustoIngest
from azdata.live import seed as seed_data
from azdata.search.deploy import SearchIndexProvisioner, SearchServiceProvisioner

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 7.1 Topology.
# ----------------------------------------------------------------------

#: There is no default subscription. The target is supplied by the caller at
#: every entry point, so this package can never bill a subscription nobody
#: named.
RESOURCE_GROUP = "rg-azdata-live"
LOCATION = "eastus"

#: Cosmos alone sits elsewhere. East US refuses new database accounts with
#: ServiceUnavailable on zonal capacity, reproducibly and not transiently; the
#: subscription's existing Cosmos accounts are in East US 2 and it accepts them.
#: A resource group's location does not constrain its resources' locations.
COSMOS_LOCATION = "eastus2"

#: The gate on ``down``. Applied at creation, checked before deletion.
OWNER_TAG_KEY = "azdata-live-owned"
OWNER_TAG_VALUE = "true"

#: Returned by the role probe when the endpoint refuses on network grounds.
#: Distinct from 0.0, which means the grant was already effective.
UNREACHABLE = -1.0

#: A data plane refusing on network grounds, not on missing permission. Azure
#: Policy sets publicNetworkAccess=Disabled in this tenant and reverts an ARM
#: write that re-enables it, so no amount of waiting clears these.
_NETWORK_BLOCK_MARKERS = (
    "blocked by your cosmos db account firewall",
    "public network access is disabled",
    "publicnetworkaccess",
    "request originated from ip",
    "not allowed by firewall",
    "forbidden by private endpoint",
)


def _is_network_blocked(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in _NETWORK_BLOCK_MARKERS)

SEARCH_SERVICE = "srch-azdatalive"
SEARCH_INDEX = "azdata-assets"
COSMOS_ACCOUNT = "cosmos-azdata-nosql"
COSMOS_DATABASE = "azdatalive"
COSMOS_CONTAINER = "assets"
COSMOS_PARTITION_KEY = "/site"
GREMLIN_ACCOUNT = "cosmos-azdata-gremlin"
GREMLIN_DATABASE = "azdatalive"
GREMLIN_GRAPH = "assets"
KUSTO_CLUSTER = "adx-azdatalive"
KUSTO_DATABASE = "azdatalive"
KUSTO_TABLE = "Assets"
LOG_WORKSPACE = "log-azdatalive"

#: The Log Analytics workspace is created as a generic ARM resource rather
#: than through ``azure-mgmt-loganalytics``. It is a telemetry sink with no
#: read plane, no write plane and no stats in this package, so a whole
#: service folder and a sixth management SDK would be scaffolding around
#: one PUT.
LOG_WORKSPACE_API_VERSION = "2023-09-01"
LOG_WORKSPACE_TYPE = ("Microsoft.OperationalInsights", "workspaces")

#: Built-in role definition ids, subscription-scoped at use.
ROLE_CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
ROLE_SEARCH_INDEX_DATA_CONTRIBUTOR = "8ebe5a00-799e-43f5-93ac-243d3dce84a7"
ROLE_MONITORING_READER = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"

#: The Cosmos *data-plane* contributor. A management-plane Contributor does
#: not grant it, which is the single most common reason a correct-looking
#: deployment 403s on its first read.
COSMOS_DATA_CONTRIBUTOR = "00000000-0000-0000-0000-000000000002"

#: How long a role assignment may take to become usable before ``up`` calls
#: it a failure. Ten minutes is generous; the observed wait is reported.
ROLE_PROPAGATION_BUDGET_SECS = 600.0
ROLE_PROBE_INTERVAL_SECS = 10.0

#: Where ``up`` writes what it created. Identity and endpoints only.
STATE_PATH = Path(__file__).resolve().parent / "_state" / "environment.json"

# Cosmos account names are a global DNS namespace: lowercase letters,
# digits and hyphens, 3-44 characters, and somebody else may already have
# yours.
_ACCOUNT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,42}[a-z0-9]$")

# Anything matching these must never reach the state file.
_SECRET_MARKERS = (
    "accountkey=",
    "sharedaccesssignature",
    "sig=",
    "password",
    "primarykey",
    "connectionstring",
)


class LiveEnvironmentError(RuntimeError):
    """A lifecycle step failed. Carries operator language, not a stack trace."""


class NameUnavailable(LiveEnvironmentError):
    """A globally unique resource name is taken, or is not a legal name.

    Named because the SDK's version of this is an ARM conflict buried in a
    long HTTP error, and the operator's next action — pick another name —
    is not obvious from it.
    """


class TeardownRefused(LiveEnvironmentError):
    """``down`` reached a resource group it does not own, and stopped."""


@dataclass(frozen=True)
class ResourcePlan:
    """One ARM resource of the topology, as data."""

    key: str
    kind: str
    name: str
    sku: str
    notes: str = ""

    def endpoint(self, location: str) -> str:
        """The service endpoint, derived from the name. No secrets in it."""
        if self.key == "search":
            return f"https://{self.name}.search.windows.net"
        if self.key == "cosmos":
            return f"https://{self.name}.documents.azure.com:443/"
        if self.key == "gremlin":
            return f"wss://{self.name}.gremlin.cosmos.azure.com:443/"
        if self.key == "kusto":
            return f"https://{self.name}.{location}.kusto.windows.net"
        return ""


#: SPEC 7.1, verbatim, as data. ``status`` walks this; ``up`` creates in
#: this order because the ADX cluster is the long pole and everything else
#: finishes while it deploys.
TOPOLOGY: tuple[ResourcePlan, ...] = (
    ResourcePlan(
        key="search",
        kind="search-service",
        name=SEARCH_SERVICE,
        sku="basic",
        notes="a subscription's one free search tier is commonly already in use",
    ),
    ResourcePlan(
        key="cosmos",
        kind="cosmos-account",
        name=COSMOS_ACCOUNT,
        sku="serverless",
    ),
    ResourcePlan(
        key="gremlin",
        kind="cosmos-account",
        name=GREMLIN_ACCOUNT,
        sku="serverless",
        notes="EnableGremlin is an account-level capability, so it needs its own account",
    ),
    ResourcePlan(
        key="kusto",
        kind="kusto-cluster",
        name=KUSTO_CLUSTER,
        sku="Dev(No SLA)_Standard_D11_v2",
        notes="10-15 minutes to create; resumable. E2a_v4 had no capacity in eastus",
    ),
    ResourcePlan(
        key="logs",
        kind="log-analytics-workspace",
        name=LOG_WORKSPACE,
        sku="PerGB2018",
    ),
)


@dataclass(frozen=True)
class RolePlan:
    """One role assignment of SPEC 7.4, with the probe that proves it landed."""

    key: str
    role: str
    scope: str          # "resource-group" | "search" | "cosmos" | "gremlin" | "kusto"
    plane: str          # "management" | "data"
    role_id: str = ""


ROLES: tuple[RolePlan, ...] = (
    RolePlan(
        key="rg-contributor",
        role="Contributor",
        scope="resource-group",
        plane="management",
        role_id=ROLE_CONTRIBUTOR,
    ),
    RolePlan(
        key="rg-monitoring-reader",
        role="Monitoring Reader",
        scope="resource-group",
        plane="management",
        role_id=ROLE_MONITORING_READER,
    ),
    RolePlan(
        key="search-index-data-contributor",
        role="Search Index Data Contributor",
        scope="search",
        plane="management",
        role_id=ROLE_SEARCH_INDEX_DATA_CONTRIBUTOR,
    ),
    RolePlan(
        key="cosmos-data-contributor",
        role="Cosmos DB Built-in Data Contributor",
        scope="cosmos",
        plane="data",
        role_id=COSMOS_DATA_CONTRIBUTOR,
    ),
    RolePlan(
        key="gremlin-data-contributor",
        role="Cosmos DB Built-in Data Contributor",
        scope="gremlin",
        plane="data",
        role_id=COSMOS_DATA_CONTRIBUTOR,
    ),
    RolePlan(
        key="kusto-database-admin",
        role="Admin",
        scope="kusto",
        plane="data",
    ),
)


# ----------------------------------------------------------------------
# Specs. Plain dicts, handed to the provisioners unchanged.
# ----------------------------------------------------------------------


def search_service_spec(location: str = LOCATION) -> dict:
    # disable_local_auth is what makes RBAC work at all. A search service
    # defaults to authOptions apiKeyOnly, which refuses every AAD token no
    # matter which data-plane role is assigned, and the refusal is a bare
    # 403 that reads exactly like a missing role assignment.
    return {
        "location": location,
        "sku": {"name": "basic"},
        "replica_count": 1,
        "partition_count": 1,
        "disable_local_auth": True,
        "tags": {OWNER_TAG_KEY: OWNER_TAG_VALUE},
    }


def search_index_spec() -> dict:
    """Keyword fields plus one vector field, per SPEC 7.2.

    ``vector_search_dimensions`` matches ``seed.VECTOR_DIMS`` because a
    dimension mismatch is accepted at index creation and rejected at the
    first document write, which is a long way from the mistake.
    """
    return {
        "name": SEARCH_INDEX,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "site", "type": "Edm.String", "filterable": True, "facetable": True},
            {"name": "kind", "type": "Edm.String", "filterable": True},
            {"name": "status", "type": "Edm.String", "filterable": True},
            {"name": "blurb", "type": "Edm.String", "searchable": True},
            {
                "name": "vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "vector_search_dimensions": seed_data.VECTOR_DIMS,
                "vector_search_profile_name": "hc-vector",
            },
        ],
        "vector_search": {
            "profiles": [{"name": "hc-vector", "algorithm_configuration_name": "hc-hnsw"}],
            "algorithms": [{"name": "hc-hnsw", "kind": "hnsw"}],
        },
    }


def cosmos_account_spec(location: str = COSMOS_LOCATION, *, gremlin: bool = False) -> dict:
    """A serverless account. Gremlin needs the account-level capability."""
    capabilities = [{"name": "EnableServerless"}]
    if gremlin:
        capabilities.append({"name": "EnableGremlin"})
    return {
        "location": location,
        "kind": "GlobalDocumentDB",
        "tags": {OWNER_TAG_KEY: OWNER_TAG_VALUE},
        "properties": {
            "databaseAccountOfferType": "Standard",
            "locations": [{"locationName": location, "failoverPriority": 0}],
            "capabilities": capabilities,
            # Identity only, everywhere in this package.
            "disableLocalAuth": True,
        },
    }


def cosmos_database_spec() -> dict:
    return {"properties": {"resource": {"id": COSMOS_DATABASE}, "options": {}}}


def cosmos_container_spec() -> dict:
    return {
        "properties": {
            "resource": {
                "id": COSMOS_CONTAINER,
                "partitionKey": {"paths": [COSMOS_PARTITION_KEY], "kind": "Hash"},
            },
            "options": {},
        }
    }


def log_workspace_spec(location: str = LOCATION) -> dict:
    return {
        "location": location,
        "tags": {OWNER_TAG_KEY: OWNER_TAG_VALUE},
        "properties": {"sku": {"name": "PerGB2018"}, "retentionInDays": 30},
    }


def kusto_table_spec() -> dict:
    return {"columns": dict(seed_data.KUSTO_COLUMNS)}


def validate_account_name(name: str) -> str:
    """Refuse an illegal Cosmos account name before ARM does, by name.

    Global uniqueness cannot be checked here — that needs a service call,
    and :meth:`Environment._check_account_name` makes it — but the shape
    can, and a name that is uppercase or too long fails with a message
    about the name rather than a 400 from a provider.
    """
    if not _ACCOUNT_NAME.match(name):
        raise NameUnavailable(
            f"'{name}' is not a legal Cosmos account name: 3-44 characters, "
            "lowercase letters, digits and hyphens, not starting or ending "
            "with a hyphen"
        )
    return name


# ----------------------------------------------------------------------
# Identity.
# ----------------------------------------------------------------------


def principal_from_token(token: str) -> dict[str, str]:
    """The object id and principal type of whoever this token belongs to.

    A role assignment needs the caller's own principal id, and the token
    the caller is already holding carries it in the ``oid`` claim. The
    signature is deliberately not verified: this is not an authorisation
    decision — ARM authorises the assignment — it is reading our own name
    out of our own token so we do not have to shell out to
    ``az ad signed-in-user show``. Nothing from the claims is persisted
    beyond the object id.
    """
    parts = token.split(".")
    if len(parts) < 2:
        raise LiveEnvironmentError(
            "the management token is not a JWT, so the running identity's "
            "object id cannot be read from it"
        )
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - boundary
        raise LiveEnvironmentError(
            "the management token's claims could not be decoded"
        ) from exc
    oid = claims.get("oid") or claims.get("sub")
    if not oid:
        raise LiveEnvironmentError(
            "the management token carries no 'oid' claim, so the running "
            "identity cannot be named in a role assignment"
        )
    is_app = claims.get("idtyp") == "app" or (
        claims.get("appid") and not claims.get("upn") and not claims.get("unique_name")
    )
    return {
        "principal_id": str(oid),
        "principal_type": "ServicePrincipal" if is_app else "User",
        "tenant_id": str(claims.get("tid", "")),
    }


# ----------------------------------------------------------------------
# The environment.
# ----------------------------------------------------------------------


@dataclass
class StepResult:
    """One progress line: what ran, how long it took, what it read back."""

    step: str
    elapsed_secs: float
    detail: dict = field(default_factory=dict)


class Environment:
    """The live conformance topology, driven through this package's deploy plane.

    Args:
        credential_provider: Returns a ``TokenCredential``. Called per
            client, never cached here — the credential cache lives in
            ``core/credentials.py``.
        subscription_id: The subscription to build in. Required, with no
            default: a lifecycle that can pick its own billing target is
            one that will eventually pick the wrong one.
        state_path: Where ``up`` records what it created. Overridable so a
            test never writes into the package directory.
        report: Called with each :class:`StepResult` as it completes.
            Defaults to a progress line on stderr.
        clock: Monotonic seconds, injectable so a test can prove the
            propagation poll is bounded without waiting for it.
    """

    def __init__(
        self,
        *,
        credential_provider: Callable[[], Any],
        subscription_id: str,
        resource_group: str = RESOURCE_GROUP,
        location: str = LOCATION,
        cosmos_location: str = COSMOS_LOCATION,
        state_path: Path | str = STATE_PATH,
        report: Callable[[StepResult], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Any] | None = None,
        role_budget_secs: float = ROLE_PROPAGATION_BUDGET_SECS,
        role_probe_interval_secs: float = ROLE_PROBE_INTERVAL_SECS,
    ) -> None:
        # Refused here, before a credential is requested: an unusable target
        # must not cost an interactive sign-in to discover.
        if not isinstance(subscription_id, str) or not subscription_id.strip():
            raise ValueError(
                "subscription_id is required and must name a subscription; "
                "pass --subscription on the command line"
            )
        self._credential_provider = credential_provider
        self._subscription_id = subscription_id.strip()
        self._resource_group = resource_group
        self._location = location
        self._cosmos_location = cosmos_location
        self._state_path = Path(state_path)
        self._report = report or _print_step
        self._clock = clock
        self._sleep = sleep or asyncio.sleep
        self._role_budget = role_budget_secs
        self._role_interval = role_probe_interval_secs
        self._clients: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Clients. Every one is lazy, and every one goes through ``load`` so a
    # test can substitute it without a network.
    # ------------------------------------------------------------------

    def _client(self, key: str, build: Callable[[], Any]) -> Any:
        client = self._clients.get(key)
        if client is None:
            client = build()
            self._clients[key] = client
        return client

    def _resources(self) -> Any:
        def build() -> Any:
            # 26.0 stopped re-exporting at the top level; the subpackage path
            # is the one that works across both.
            mgmt = load(
                "azure.mgmt.resource.resources", dist="azure-mgmt-resource"
            )
            return mgmt.ResourceManagementClient(
                self._credential_provider(), self._subscription_id
            )

        return self._client("resource", build)

    def _authorization(self) -> Any:
        def build() -> Any:
            mgmt = load("azure.mgmt.authorization", dist="azure-mgmt-authorization")
            return mgmt.AuthorizationManagementClient(
                self._credential_provider(), self._subscription_id
            )

        return self._client("authorization", build)

    def _cosmos_mgmt(self) -> Any:
        return self._client(
            "cosmos",
            lambda: build_cosmos_client(
                self._credential_provider(), self._subscription_id
            ),
        )

    def _kusto_mgmt(self) -> Any:
        return self._client(
            "kusto",
            lambda: build_kusto_client(
                self._credential_provider(), self._subscription_id
            ),
        )

    # ------------------------------------------------------------------
    # Provisioners. Built per call: they are cheap and hold no state worth
    # sharing, and a stale one after a teardown would answer about a
    # resource that no longer exists.
    # ------------------------------------------------------------------

    def _search_service(self, policy: ProvisionPolicy) -> SearchServiceProvisioner:
        return SearchServiceProvisioner(
            subscription_id=self._subscription_id,
            resource_group=self._resource_group,
            name=SEARCH_SERVICE,
            location=self._location,
            credential=self._credential_provider(),
            policy=policy,
        )

    def _search_index(self, policy: ProvisionPolicy) -> SearchIndexProvisioner:
        return SearchIndexProvisioner(
            endpoint=self.search_endpoint,
            name=SEARCH_INDEX,
            credential=self._credential_provider(),
            policy=policy,
        )

    def _cosmos_account(self, name: str, policy: ProvisionPolicy) -> CosmosAccountProvisioner:
        return CosmosAccountProvisioner(
            client=self._cosmos_mgmt(),
            resource_group=self._resource_group,
            name=name,
            policy=policy,
        )

    def _cosmos_database(self, policy: ProvisionPolicy) -> CosmosDatabaseProvisioner:
        return CosmosDatabaseProvisioner(
            client=self._cosmos_mgmt(),
            resource_group=self._resource_group,
            account_name=COSMOS_ACCOUNT,
            name=COSMOS_DATABASE,
            policy=policy,
        )

    def _cosmos_container(self, policy: ProvisionPolicy) -> CosmosContainerProvisioner:
        return CosmosContainerProvisioner(
            client=self._cosmos_mgmt(),
            resource_group=self._resource_group,
            account_name=COSMOS_ACCOUNT,
            database=COSMOS_DATABASE,
            name=COSMOS_CONTAINER,
            policy=policy,
        )

    def _gremlin_database(self, policy: ProvisionPolicy) -> GremlinDatabaseProvisioner:
        return GremlinDatabaseProvisioner(
            name=GREMLIN_DATABASE,
            credential_provider=self._credential_provider,
            subscription_id=self._subscription_id,
            resource_group=self._resource_group,
            account_name=GREMLIN_ACCOUNT,
            location=self._location,
            policy=policy,
            client=self._cosmos_mgmt(),
        )

    def _gremlin_graph(self, policy: ProvisionPolicy) -> GremlinGraphProvisioner:
        return GremlinGraphProvisioner(
            name=GREMLIN_GRAPH,
            database_name=GREMLIN_DATABASE,
            credential_provider=self._credential_provider,
            subscription_id=self._subscription_id,
            resource_group=self._resource_group,
            account_name=GREMLIN_ACCOUNT,
            location=self._location,
            policy=policy,
            client=self._cosmos_mgmt(),
        )

    def _kusto_cluster(self, policy: ProvisionPolicy) -> KustoClusterProvisioner:
        return KustoClusterProvisioner(
            client=self._kusto_mgmt(),
            resource_group=self._resource_group,
            name=KUSTO_CLUSTER,
            location=self._location,
            policy=policy,
        )

    def _kusto_database(self, policy: ProvisionPolicy) -> KustoDatabaseProvisioner:
        return KustoDatabaseProvisioner(
            client=self._kusto_mgmt(),
            resource_group=self._resource_group,
            cluster_name=KUSTO_CLUSTER,
            name=KUSTO_DATABASE,
            location=self._location,
            policy=policy,
        )

    def _kql_connector(self) -> KqlConnector:
        target = KqlTarget(query_uri=self.kusto_endpoint, database=KUSTO_DATABASE)
        return KqlConnector(
            resolve_target=lambda: target,
            credential_provider=self._credential_provider,
            gate_provider=_lifecycle_gate,
        )

    def _kusto_table(self, policy: ProvisionPolicy) -> KustoTableProvisioner:
        return KustoTableProvisioner(
            connector=self._kql_connector(), name=KUSTO_TABLE, policy=policy
        )

    def _kusto_ingest(self, policy: WritePolicy) -> KustoIngest:
        return KustoIngest(
            connector=self._kql_connector(),
            table=KUSTO_TABLE,
            columns=seed_data.KUSTO_COLUMNS,
            policy=policy,
        )

    # ------------------------------------------------------------------
    # Endpoints.
    # ------------------------------------------------------------------

    @property
    def search_endpoint(self) -> str:
        return f"https://{SEARCH_SERVICE}.search.windows.net"

    @property
    def cosmos_endpoint(self) -> str:
        return f"https://{COSMOS_ACCOUNT}.documents.azure.com:443/"

    @property
    def gremlin_endpoint(self) -> str:
        return f"wss://{GREMLIN_ACCOUNT}.gremlin.cosmos.azure.com:443/"

    @property
    def kusto_endpoint(self) -> str:
        return f"https://{KUSTO_CLUSTER}.{self._location}.kusto.windows.net"

    def resource_id(self, provider: str, resource_type: str, name: str) -> str:
        return (
            f"/subscriptions/{self._subscription_id}"
            f"/resourceGroups/{self._resource_group}"
            f"/providers/{provider}/{resource_type}/{name}"
        )

    # ------------------------------------------------------------------
    # up
    # ------------------------------------------------------------------

    async def up(self, *, seed: bool = True) -> dict:
        """Create everything, in order, reading each resource back.

        Idempotent and resumable: every step tolerates its resource
        already existing, so a re-run after a timeout continues rather
        than restarting. The state file is written after every step, so a
        run that dies halfway still leaves a truthful record of what
        exists.
        """
        record = self._load_state()
        record.setdefault("created_utc", _utc_now())
        record["subscription_id"] = self._subscription_id
        record["resource_group"] = self._resource_group
        record["location"] = self._location

        steps: list[tuple[str, Callable[[dict], Any]]] = [
            ("resource-group", self._step_resource_group),
            ("search-service", self._step_search_service),
            ("cosmos-account", self._step_cosmos_account),
            ("gremlin-account", self._step_gremlin_account),
            ("kusto-cluster", self._step_kusto_cluster),
            ("log-workspace", self._step_log_workspace),
            ("cosmos-database", self._step_cosmos_children),
            ("gremlin-graph", self._step_gremlin_children),
            ("kusto-database", self._step_kusto_database),
            ("role-assignments", self._step_roles),
            ("search-index", self._step_search_index),
            ("kusto-table", self._step_kusto_table),
        ]
        if seed:
            steps.append(("seed", self._step_seed))

        for name, step in steps:
            started = self._clock()
            try:
                detail = await step(record) or {}
            except LiveEnvironmentError as exc:
                self._write_state(record)
                raise
            except Exception as exc:  # noqa: BLE001 - boundary: name the step
                self._write_state(record)
                raise LiveEnvironmentError(f"{name} failed: {exc}") from exc
            result = StepResult(name, self._clock() - started, detail)
            record.setdefault("steps", {})[name] = {
                "elapsed_secs": round(result.elapsed_secs, 2),
                **detail,
            }
            self._write_state(record)
            self._report(result)

        record["updated_utc"] = _utc_now()
        self._write_state(record)
        return record

    # -- steps ---------------------------------------------------------

    async def _step_resource_group(self, record: dict) -> dict:
        client = self._resources()
        await asyncio.to_thread(
            client.resource_groups.create_or_update,
            self._resource_group,
            {
                "location": self._location,
                "tags": {OWNER_TAG_KEY: OWNER_TAG_VALUE},
            },
        )
        # Read-back before the next step, not because ARM said Succeeded.
        group = await self._read_resource_group()
        if group is None:
            raise LiveEnvironmentError(
                f"resource group '{self._resource_group}' is not readable after "
                "a successful create"
            )
        tags = dict(group.get("tags") or {})
        if tags.get(OWNER_TAG_KEY) != OWNER_TAG_VALUE:
            raise LiveEnvironmentError(
                f"resource group '{self._resource_group}' did not keep the "
                f"'{OWNER_TAG_KEY}' tag; without it 'down' will refuse to "
                "delete it"
            )
        record.setdefault("resources", {})["resource-group"] = {
            "name": self._resource_group,
            "id": group.get("id", ""),
            "tags": tags,
            "read_back_utc": _utc_now(),
        }
        return {"tagged": True}

    async def _step_search_service(self, record: dict) -> dict:
        provisioner = self._search_service(ProvisionPolicy.deployable())
        detail = _require(
            await provisioner.ensure(search_service_spec(self._location)),
            "search service",
        )
        self._record_resource(
            record,
            "search",
            name=SEARCH_SERVICE,
            resource_id=self.resource_id(
                "Microsoft.Search", "searchServices", SEARCH_SERVICE
            ),
            endpoint=self.search_endpoint,
            state=detail.get("state", ""),
        )
        return {"created": detail.get("created", False)}

    async def _step_cosmos_account(self, record: dict) -> dict:
        await self._check_account_name(COSMOS_ACCOUNT)
        provisioner = self._cosmos_account(COSMOS_ACCOUNT, ProvisionPolicy.deployable())
        detail = _require(
            await provisioner.ensure(cosmos_account_spec(self._cosmos_location)),
            "cosmos account",
        )
        self._record_resource(
            record,
            "cosmos",
            name=COSMOS_ACCOUNT,
            resource_id=self.resource_id(
                "Microsoft.DocumentDB", "databaseAccounts", COSMOS_ACCOUNT
            ),
            endpoint=self.cosmos_endpoint,
            state=detail.get("state", ""),
        )
        return {"created": detail.get("created", False)}

    async def _step_gremlin_account(self, record: dict) -> dict:
        await self._check_account_name(GREMLIN_ACCOUNT)
        provisioner = self._cosmos_account(GREMLIN_ACCOUNT, ProvisionPolicy.deployable())
        detail = _require(
            await provisioner.ensure(
                cosmos_account_spec(self._cosmos_location, gremlin=True)
            ),
            "gremlin account",
        )
        self._record_resource(
            record,
            "gremlin",
            name=GREMLIN_ACCOUNT,
            resource_id=self.resource_id(
                "Microsoft.DocumentDB", "databaseAccounts", GREMLIN_ACCOUNT
            ),
            endpoint=self.gremlin_endpoint,
            state=detail.get("state", ""),
        )
        return {"created": detail.get("created", False)}

    async def _step_kusto_cluster(self, record: dict) -> dict:
        provisioner = self._kusto_cluster(cluster_policy())
        detail = _require(
            await provisioner.ensure(
                provisioner.default_spec(tags={OWNER_TAG_KEY: OWNER_TAG_VALUE})
            ),
            "kusto cluster",
        )
        self._record_resource(
            record,
            "kusto",
            name=KUSTO_CLUSTER,
            resource_id=self.resource_id("Microsoft.Kusto", "clusters", KUSTO_CLUSTER),
            endpoint=self.kusto_endpoint,
            state=detail.get("state", ""),
        )
        return {"created": detail.get("created", False)}

    async def _step_log_workspace(self, record: dict) -> dict:
        client = self._resources()
        namespace, resource_type = LOG_WORKSPACE_TYPE
        # api_version is keyword-only from azure-mgmt-resource 26; passing it
        # positionally is an arity error, not a version error.
        poller = await asyncio.to_thread(
            functools.partial(
                client.resources.begin_create_or_update,
                self._resource_group,
                namespace,
                "",
                resource_type,
                LOG_WORKSPACE,
                log_workspace_spec(self._location),
                api_version=LOG_WORKSPACE_API_VERSION,
            )
        )
        await _resolve(poller)
        live = await asyncio.to_thread(
            functools.partial(
                client.resources.get,
                self._resource_group,
                namespace,
                "",
                resource_type,
                LOG_WORKSPACE,
                api_version=LOG_WORKSPACE_API_VERSION,
            )
        )
        if live is None:
            raise LiveEnvironmentError(
                f"log analytics workspace '{LOG_WORKSPACE}' is not readable "
                "after a successful create"
            )
        self._record_resource(
            record,
            "logs",
            name=LOG_WORKSPACE,
            resource_id=self.resource_id(
                namespace, resource_type, LOG_WORKSPACE
            ),
            endpoint="",
            state=str(lift_kusto_model(live).get("provisioning_state", "")),
        )
        return {"api_version": LOG_WORKSPACE_API_VERSION}

    async def _step_cosmos_children(self, record: dict) -> dict:
        policy = ProvisionPolicy.deployable()
        _require(
            await self._cosmos_database(policy).ensure(cosmos_database_spec()),
            "cosmos database",
        )
        _require(
            await self._cosmos_container(policy).ensure(cosmos_container_spec()),
            "cosmos container",
        )
        record.setdefault("resources", {})["cosmos"] = {
            **record.get("resources", {}).get("cosmos", {}),
            "database": COSMOS_DATABASE,
            "container": COSMOS_CONTAINER,
            "partition_key": COSMOS_PARTITION_KEY,
        }
        return {"database": COSMOS_DATABASE, "container": COSMOS_CONTAINER}

    async def _step_gremlin_children(self, record: dict) -> dict:
        policy = ProvisionPolicy.deployable()
        _require(
            await self._gremlin_database(policy).ensure({}),
            "gremlin database",
        )
        _require(
            await self._gremlin_graph(policy).ensure(
                {"partition_key_paths": [COSMOS_PARTITION_KEY]}
            ),
            "gremlin graph",
        )
        record.setdefault("resources", {})["gremlin"] = {
            **record.get("resources", {}).get("gremlin", {}),
            "database": GREMLIN_DATABASE,
            "graph": GREMLIN_GRAPH,
        }
        return {"database": GREMLIN_DATABASE, "graph": GREMLIN_GRAPH}

    async def _step_kusto_database(self, record: dict) -> dict:
        provisioner = self._kusto_database(ProvisionPolicy.deployable())
        _require(
            await provisioner.ensure(provisioner.default_spec()), "kusto database"
        )
        record.setdefault("resources", {})["kusto"] = {
            **record.get("resources", {}).get("kusto", {}),
            "database": KUSTO_DATABASE,
        }
        return {"database": KUSTO_DATABASE}

    async def _step_search_index(self, record: dict) -> dict:
        _require(
            await self._search_index(ProvisionPolicy.deployable()).ensure(
                search_index_spec()
            ),
            "search index",
        )
        record.setdefault("resources", {})["search"] = {
            **record.get("resources", {}).get("search", {}),
            "index": SEARCH_INDEX,
        }
        return {"index": SEARCH_INDEX}

    async def _step_kusto_table(self, record: dict) -> dict:
        _require(
            await self._kusto_table(ProvisionPolicy.deployable()).ensure(
                kusto_table_spec()
            ),
            "kusto table",
        )
        record.setdefault("resources", {})["kusto"] = {
            **record.get("resources", {}).get("kusto", {}),
            "table": KUSTO_TABLE,
        }
        return {"table": KUSTO_TABLE}

    # ------------------------------------------------------------------
    # 7.4 Role assignments.
    # ------------------------------------------------------------------

    async def _step_roles(self, record: dict) -> dict:
        identity = self.identity()
        assigned: list[dict] = []
        for plan in ROLES:
            started = self._clock()
            try:
                await self._assign(plan, identity)
            except Exception as exc:  # noqa: BLE001 - boundary
                raise LiveEnvironmentError(
                    f"role assignment '{plan.key}' failed: {exc}"
                ) from exc
            waited = await self._await_role(plan)
            entry = {
                "role": plan.role,
                "scope": plan.scope,
                "plane": plan.plane,
                "assign_secs": round(self._clock() - started, 2),
            }
            if waited is UNREACHABLE or waited == UNREACHABLE:
                entry["propagation_secs"] = None
                entry["data_plane"] = "unreachable"
            else:
                entry["propagation_secs"] = round(waited, 2)
                entry["data_plane"] = "reachable"
            assigned.append(entry)
        record["roles"] = assigned
        record["principal_id"] = identity["principal_id"]
        unreachable = [e["scope"] for e in assigned if e["data_plane"] == "unreachable"]
        return {"assignments": len(assigned), "unreachable": unreachable}

    def identity(self) -> dict[str, str]:
        """The running identity, read out of a management token."""
        credential = self._credential_provider()
        token = credential.get_token("https://management.azure.com/.default")
        return principal_from_token(getattr(token, "token", str(token)))

    def _scope_id(self, scope: str) -> str:
        if scope == "resource-group":
            return f"/subscriptions/{self._subscription_id}/resourceGroups/{self._resource_group}"
        if scope == "search":
            return self.resource_id(
                "Microsoft.Search", "searchServices", SEARCH_SERVICE
            )
        if scope == "cosmos":
            return self.resource_id(
                "Microsoft.DocumentDB", "databaseAccounts", COSMOS_ACCOUNT
            )
        if scope == "gremlin":
            return self.resource_id(
                "Microsoft.DocumentDB", "databaseAccounts", GREMLIN_ACCOUNT
            )
        if scope == "kusto":
            return self.resource_id("Microsoft.Kusto", "clusters", KUSTO_CLUSTER)
        raise LiveEnvironmentError(f"unknown role scope '{scope}'")

    async def _assign(self, plan: RolePlan, identity: Mapping[str, str]) -> None:
        if plan.scope == "kusto":
            await self._assign_kusto_admin(identity)
            return
        if plan.plane == "data":
            await self._assign_cosmos_data_role(plan, identity)
            return
        await self._assign_arm_role(plan, identity)

    async def _assign_arm_role(self, plan: RolePlan, identity: Mapping[str, str]) -> None:
        client = self._authorization()
        scope = self._scope_id(plan.scope)
        parameters = {
            "role_definition_id": (
                f"/subscriptions/{self._subscription_id}/providers/"
                f"Microsoft.Authorization/roleDefinitions/{plan.role_id}"
            ),
            "principal_id": identity["principal_id"],
            "principal_type": identity["principal_type"],
        }
        try:
            await asyncio.to_thread(
                client.role_assignments.create,
                scope,
                str(uuid.uuid4()),
                parameters,
            )
        except Exception as exc:  # noqa: BLE001 - already-assigned is success
            if not _already_exists(exc):
                raise

    async def _assign_cosmos_data_role(
        self, plan: RolePlan, identity: Mapping[str, str]
    ) -> None:
        """The Cosmos data-plane role. Management Contributor does not grant it.

        Not every Cosmos API surface honours native data-plane RBAC —
        Gremlin in particular — so a refusal here is reported as a named
        failure naming the account, rather than surfacing as a 403 from
        the first seeding call minutes later.
        """
        account = COSMOS_ACCOUNT if plan.scope == "cosmos" else GREMLIN_ACCOUNT
        client = self._cosmos_mgmt()
        scope = self.resource_id(
            "Microsoft.DocumentDB", "databaseAccounts", account
        )
        parameters = {
            "properties": {
                "roleDefinitionId": f"{scope}/sqlRoleDefinitions/{plan.role_id}",
                "principalId": identity["principal_id"],
                "scope": scope,
            }
        }
        call = client.sql_resources.begin_create_update_sql_role_assignment
        assignment_id = str(uuid.uuid4())
        try:
            poller = await asyncio.to_thread(
                lambda: call(
                    role_assignment_id=assignment_id,
                    resource_group_name=self._resource_group,
                    account_name=account,
                    create_update_sql_role_assignment_parameters=parameters,
                )
            )
        except TypeError:
            # Older pins of azure-mgmt-cosmosdb take these positionally in
            # this order; the keyword names moved, the order did not.
            poller = await asyncio.to_thread(
                call, assignment_id, self._resource_group, account, parameters
            )
        except Exception as exc:  # noqa: BLE001 - already-assigned is success
            if _already_exists(exc):
                return
            raise
        await _resolve(poller)

    async def _assign_kusto_admin(self, identity: Mapping[str, str]) -> None:
        client = self._kusto_mgmt()
        parameters = {
            "properties": {
                "principalId": identity["principal_id"],
                "role": "Admin",
                "principalType": identity["principal_type"],
                "tenantId": identity.get("tenant_id", ""),
            }
        }
        try:
            poller = await asyncio.to_thread(
                client.database_principal_assignments.begin_create_or_update,
                self._resource_group,
                KUSTO_CLUSTER,
                KUSTO_DATABASE,
                str(uuid.uuid4()),
                parameters,
            )
        except Exception as exc:  # noqa: BLE001 - already-assigned is success
            if _already_exists(exc):
                return
            raise
        await _resolve(poller)

    async def _await_role(self, plan: RolePlan) -> float:
        """Poll a real data-plane call until it succeeds. Never sleep a guess.

        Returns the wait actually observed, in seconds, which is what
        goes in the state file and the progress line. An assignment that
        was already in place returns near zero, which is the honest
        answer and not something to round up to a comfortable-looking
        number.

        Returns ``UNREACHABLE`` when the endpoint refuses on network
        grounds. That is not a propagation delay and waiting does not
        clear it, so it is reported rather than retried.
        """
        probe = self._probe_for(plan)
        if probe is None:
            return 0.0
        started = self._clock()
        last = ""
        while self._clock() - started < self._role_budget:
            try:
                ok, last = await probe()
            except Exception as exc:  # noqa: BLE001 - a probe that raises is a 'no'
                ok, last = False, f"{type(exc).__name__}: {exc}"
            if ok:
                return self._clock() - started
            if _is_network_blocked(last):
                logger.warning(
                    "azdata.role_assigned_but_unreachable scope=%s role=%s: %s",
                    plan.scope,
                    plan.role,
                    last[:200],
                )
                return UNREACHABLE
            await self._sleep(self._role_interval)
        raise LiveEnvironmentError(
            f"role '{plan.role}' on {plan.scope} was assigned but a data-plane "
            f"call still fails after {self._role_budget:.0f}s: {last[:200]}"
        )

    def _probe_for(self, plan: RolePlan) -> Callable[[], Any] | None:
        """The real call each assignment is supposed to make possible."""
        if plan.scope == "search":

            async def search_probe() -> tuple[bool, str]:
                payload = await self._search_index(
                    ProvisionPolicy.read_only()
                ).describe()
                return (not is_error(payload)), payload

            return search_probe

        if plan.scope == "cosmos":

            async def cosmos_probe() -> tuple[bool, str]:
                aio = load("azure.cosmos.aio", dist="azure-cosmos")
                client = aio.CosmosClient(
                    url=self.cosmos_endpoint, credential=self._credential_provider()
                )
                try:
                    await client.get_database_client(COSMOS_DATABASE).read()
                    return True, ""
                finally:
                    await client.close()

            return cosmos_probe

        if plan.scope == "kusto":

            async def kusto_probe() -> tuple[bool, str]:
                # A trivial tabular query, not a control command: it runs in
                # the database's context so it proves the database role
                # landed, and it survives the read-only guard so the probe
                # does not need an unguarded connector of its own.
                payload = await self._kql_connector().execute("print probe = 1")
                return (not is_error(payload)), payload

            return kusto_probe

        # A management-plane role is proved by the very next ARM call, and
        # the Gremlin data plane has no cheap probe that does not also
        # create a client per attempt; both are left to the step that uses
        # them, where the failure names itself.
        return None

    # ------------------------------------------------------------------
    # 7.2 Seed.
    # ------------------------------------------------------------------

    async def _cosmos_network_disabled(self, account: str) -> bool:
        """Ask the management plane whether the data plane can be reached.

        Cheaper and more honest than matching error text: Gremlin reports the
        same policy block as a bare WebSocket 403 with no mention of a
        firewall, which is indistinguishable from a permission problem.
        """
        try:
            live = await asyncio.to_thread(
                self._cosmos_mgmt().database_accounts.get,
                self._resource_group,
                account,
            )
        except Exception:  # noqa: BLE001 - unreadable is not the same as blocked
            return False
        view = mapping_view(live)
        access = view.get("public_network_access") or view.get("publicNetworkAccess")
        return str(access).lower() == "disabled"

    async def _step_seed(self, record: dict) -> dict:
        # One unreachable service must not stop the others being seeded. A
        # network block is a standing condition of the estate, not a fault in
        # this run, so it is recorded per service and the step continues.
        seeders = (
            ("search", self._seed_search, None),
            ("cosmos", self._seed_cosmos, COSMOS_ACCOUNT),
            ("gremlin", self._seed_gremlin, GREMLIN_ACCOUNT),
            ("kusto", self._seed_kusto, None),
        )
        counts: dict[str, Any] = {}
        for key, seeder, account in seeders:
            if account is not None and await self._cosmos_network_disabled(account):
                logger.warning(
                    "azdata.seed_skipped_unreachable service=%s: "
                    "account '%s' has publicNetworkAccess Disabled",
                    key,
                    account,
                )
                counts[key] = "unreachable"
                continue
            try:
                counts[key] = await seeder()
            except Exception as exc:  # noqa: BLE001 - boundary: name the service
                detail = f"{type(exc).__name__}: {exc}"
                if not _is_network_blocked(detail):
                    raise LiveEnvironmentError(f"seed {key} failed: {exc}") from exc
                logger.warning(
                    "azdata.seed_skipped_unreachable service=%s: %s", key, detail[:200]
                )
                counts[key] = "unreachable"
        record["seed"] = {
            "assets": seed_data.ASSET_COUNT,
            "edges": seed_data.EDGE_COUNT,
            **counts,
        }
        return counts

    async def _seed_search(self) -> int:
        from azdata.search.write import SearchDocuments

        writer = SearchDocuments(
            endpoint=self.search_endpoint,
            index_name=SEARCH_INDEX,
            credential=self._credential_provider(),
            policy=WritePolicy.writable(),
        )
        try:
            documents = seed_data.search_documents()
            _require(await writer.upload(documents), "search seed")
            return len(documents)
        finally:
            writer.close()

    async def _seed_cosmos(self) -> int:
        from azdata.cosmos.write import CosmosItems

        writer = CosmosItems.connect(
            endpoint=self.cosmos_endpoint,
            database=COSMOS_DATABASE,
            container=COSMOS_CONTAINER,
            credential=self._credential_provider(),
            partition_key_field="site",
            policy=WritePolicy.writable(),
        )
        try:
            items = seed_data.cosmos_items()
            _require(await writer.upload(items), "cosmos seed")
            return len(items)
        finally:
            await writer.close()

    async def _seed_gremlin(self) -> dict:
        from azdata.gremlin.read import GremlinConnector, GremlinTarget
        from azdata.gremlin.write import GremlinElements

        target = GremlinTarget(
            endpoint=self.gremlin_endpoint,
            database=GREMLIN_DATABASE,
            graph=GREMLIN_GRAPH,
        )
        reader = GremlinConnector(
            resolve_target=lambda: target,
            credential_provider=self._credential_provider,
        )
        # A second connector for the generated edge traversals: the read
        # guard refuses addE, and flipping a flag on the shared connector
        # would un-guard every concurrent caller. Nothing caller-supplied
        # reaches it — the ids below are this package's own seed data.
        mutations = GremlinConnector(
            resolve_target=lambda: target,
            credential_provider=self._credential_provider,
            validate_fn=None,
            transform_query=None,
        )
        writer = GremlinElements(
            reader,
            label="asset",
            partition_key_field="site",
            policy=WritePolicy.writable(),
        )
        try:
            vertices = seed_data.gremlin_vertices()
            _require(await writer.upload(vertices), "gremlin vertex seed")
            edges = seed_data.gremlin_edges()
            for edge in edges:
                payload = await mutations.execute(
                    f"g.V({json.dumps(edge['from'])})"
                    f".addE({json.dumps(edge['label'])})"
                    f".to(g.V({json.dumps(edge['to'])}))"
                )
                if is_error(payload):
                    raise LiveEnvironmentError(
                        f"gremlin edge seed: {json.loads(payload).get('detail', '')}"
                    )
            return {"vertices": len(vertices), "edges": len(edges)}
        finally:
            await reader.close()
            await mutations.close()

    async def _seed_kusto(self) -> int:
        ingest = self._kusto_ingest(WritePolicy.writable())
        rows = seed_data.kusto_rows()
        _require(await ingest.ingest(rows), "kusto seed")
        return len(rows)

    # ------------------------------------------------------------------
    # status / pause / resume
    # ------------------------------------------------------------------

    async def status(self) -> dict:
        """Describe plus stats for everything, as one JSON-able document."""
        document: dict[str, Any] = {
            "subscription_id": self._subscription_id,
            "resource_group": self._resource_group,
            "location": self._location,
            "read_utc": _utc_now(),
            "topology": [
                {"key": plan.key, "kind": plan.kind, "name": plan.name, "sku": plan.sku}
                for plan in TOPOLOGY
            ],
            "resources": {},
            "stats": {},
            "partial": [],
        }

        try:
            group = await self._read_resource_group()
        except Exception as exc:  # noqa: BLE001 - status answers about the
            # rest of the estate even when the group read itself fails.
            group = None
            document["partial"].append(
                f"resource-group: {type(exc).__name__}: {exc}"
            )
        document["resource_group_present"] = group is not None
        document["resource_group_tags"] = dict((group or {}).get("tags") or {})

        describes: list[tuple[str, Callable[[], Any]]] = [
            ("search", self._search_service(ProvisionPolicy.read_only()).describe),
            ("search-index", self._search_index(ProvisionPolicy.read_only()).describe),
            (
                "cosmos",
                self._cosmos_account(COSMOS_ACCOUNT, ProvisionPolicy.read_only()).describe,
            ),
            (
                "cosmos-container",
                self._cosmos_container(ProvisionPolicy.read_only()).describe,
            ),
            (
                "gremlin",
                self._cosmos_account(GREMLIN_ACCOUNT, ProvisionPolicy.read_only()).describe,
            ),
            ("gremlin-graph", self._gremlin_graph(ProvisionPolicy.read_only()).describe),
            ("kusto", self._kusto_cluster(ProvisionPolicy.read_only()).describe),
            ("kusto-database", self._kusto_database(ProvisionPolicy.read_only()).describe),
            ("kusto-table", self._kusto_table(ProvisionPolicy.read_only()).describe),
        ]
        for key, describe in describes:
            try:
                document["resources"][key] = json.loads(await describe())
            except Exception as exc:  # noqa: BLE001 - one unreadable resource
                # is not a reason to answer nothing about the other eight.
                document["partial"].append(f"{key}: {type(exc).__name__}: {exc}")

        for key, provider in self._stats_providers().items():
            try:
                document["stats"][key] = json.loads(await provider())
            except Exception as exc:  # noqa: BLE001 - same reasoning
                document["partial"].append(f"stats {key}: {type(exc).__name__}: {exc}")

        document["standing_cost_note"] = (
            "Search basic is the standing charge (~US$74/mo). The ADX cluster "
            "bills ~US$0.10/hr while running and US$0 stopped; 'pause' stops it."
        )
        return document

    def _stats_providers(self) -> dict[str, Callable[[], Any]]:
        from azdata.kusto.observe import KustoStats
        from azdata.search.observe import SearchStats

        search = SearchStats(
            endpoint=self.search_endpoint,
            index_name=SEARCH_INDEX,
            credential=self._credential_provider(),
            resource_id=self.resource_id(
                "Microsoft.Search", "searchServices", SEARCH_SERVICE
            ),
        )
        kusto = KustoStats(
            connector=self._kql_connector(),
            table=KUSTO_TABLE,
            mgmt_client=self._kusto_mgmt(),
            cluster_name=KUSTO_CLUSTER,
            resource_group=self._resource_group,
            resource_id=self.resource_id(
                "Microsoft.Kusto", "clusters", KUSTO_CLUSTER
            ),
        )
        return {"search": search.stats, "kusto": kusto.stats}

    async def pause(self) -> dict:
        """Stop the ADX cluster. The one real cost lever in this topology."""
        payload = await self._kusto_cluster(cluster_policy()).stop()
        return {"kusto": _require(payload, "kusto cluster stop")}

    async def resume(self) -> dict:
        """Start the ADX cluster back up. Minutes, not the full create."""
        payload = await self._kusto_cluster(cluster_policy()).start()
        return {"kusto": _require(payload, "kusto cluster start")}

    # ------------------------------------------------------------------
    # down
    # ------------------------------------------------------------------

    async def down(self, *, confirm: bool = False) -> dict:
        """Delete the resource group, then re-read to prove it is gone.

        Two gates, and both are deliberate. The tag gate means this cannot
        reach a resource group it did not create. The ``confirm`` flag
        means it cannot be reached by a mistyped subcommand.
        """
        if not confirm:
            raise TeardownRefused(
                "down deletes the whole resource group and needs an explicit "
                "confirmation: pass --yes"
            )
        group = await self._read_resource_group()
        if group is None:
            return {"deleted": False, "present": False, "reason": "already absent"}
        tags = dict(group.get("tags") or {})
        if tags.get(OWNER_TAG_KEY) != OWNER_TAG_VALUE:
            raise TeardownRefused(
                f"resource group '{self._resource_group}' does not carry "
                f"{OWNER_TAG_KEY}={OWNER_TAG_VALUE}, so this environment did "
                "not create it and will not delete it"
            )

        client = self._resources()
        poller = await asyncio.to_thread(
            client.resource_groups.begin_delete, self._resource_group
        )
        await _resolve(poller)
        # Prove absence rather than trusting the delete response.
        still = await self._read_resource_group()
        if still is not None:
            raise LiveEnvironmentError(
                f"resource group '{self._resource_group}' is still readable "
                "after a successful delete"
            )
        self._clear_state()
        return {"deleted": True, "present": False}

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    async def _read_resource_group(self) -> dict | None:
        client = self._resources()
        try:
            group = await asyncio.to_thread(
                client.resource_groups.get, self._resource_group
            )
        except Exception as exc:  # noqa: BLE001 - absence is an answer
            if _is_not_found(exc):
                return None
            raise
        return lift_kusto_model(group) if group is not None else None

    async def _check_account_name(self, name: str) -> None:
        """Refuse a taken or illegal Cosmos account name by name, not by stack."""
        validate_account_name(name)
        client = self._cosmos_mgmt()
        check = getattr(
            getattr(client, "database_accounts", None), "check_name_exists", None
        )
        if check is None:
            return
        try:
            taken = await asyncio.to_thread(check, name)
        except Exception as exc:  # noqa: BLE001 - a probe that fails is not proof
            logger.warning("live.name_check_failed name=%s: %s", name, exc)
            return
        if not taken:
            return
        # Taken globally is only a problem when it is not *ours*: a re-run
        # sees its own account.
        provisioner = self._cosmos_account(name, ProvisionPolicy.read_only())
        if await provisioner.exists():
            return
        raise NameUnavailable(
            f"the Cosmos account name '{name}' is taken by another "
            "subscription. Cosmos account names are a global DNS namespace; "
            "choose a different name in azdata.live.environment"
        )

    def _record_resource(
        self,
        record: dict,
        key: str,
        *,
        name: str,
        resource_id: str,
        endpoint: str,
        state: str,
    ) -> None:
        resources = record.setdefault("resources", {})
        existing = dict(resources.get(key) or {})
        existing.update(
            {
                "name": name,
                "id": resource_id,
                "endpoint": endpoint,
                "state": state,
                "read_back_utc": _utc_now(),
            }
        )
        existing.setdefault("created_utc", _utc_now())
        resources[key] = existing

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning("live.state_unreadable path=%s: %s", self._state_path, exc)
            return {}

    def _write_state(self, record: dict) -> None:
        """Identity and endpoints only. A key in here would outlive the run."""
        assert_no_secrets(record)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(record, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    def _clear_state(self) -> None:
        try:
            self._state_path.unlink()
        except FileNotFoundError:
            pass

    @property
    def state_path(self) -> Path:
        return self._state_path


# ----------------------------------------------------------------------
# Module helpers.
# ----------------------------------------------------------------------


def assert_no_secrets(record: Mapping[str, Any]) -> None:
    """Refuse to persist anything key-shaped.

    A backstop, not a guarantee: it recognises the shapes Azure secrets
    actually take in this package's payloads — account keys, SAS tokens,
    connection strings — and refuses the write rather than trusting every
    future caller to remember the rule.
    """
    blob = json.dumps(record, default=str).lower()
    for marker in _SECRET_MARKERS:
        if marker in blob:
            raise LiveEnvironmentError(
                f"the environment record contains '{marker}', which looks like "
                "a credential. The state file carries identity and endpoints "
                "only and will not be written"
            )


def _require(payload: str, what: str) -> dict:
    """Unwrap an envelope, or raise with the operator-visible detail."""
    parsed = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if parsed.get("error"):
        raise LiveEnvironmentError(f"{what}: {parsed.get('detail', 'failed')}")
    return parsed


async def _resolve(poller: Any) -> Any:
    """Resolve an LRO off the loop. A pollerless value passes through."""
    result = getattr(poller, "result", None)
    if result is None:
        return poller
    return await asyncio.to_thread(result)


def _is_not_found(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 404:
        return True
    return type(exc).__name__ == "ResourceNotFoundError"


def _already_exists(exc: BaseException) -> bool:
    """True for ARM's "that assignment is already there", which is success."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 409:
        return True
    text = str(exc).lower()
    return "already exists" in text or "roleassignmentexists" in text


async def _lifecycle_gate() -> Any:
    """One shared gate for lifecycle work, at concurrency 1.

    Lifecycle calls are serial by construction, but the connector still
    needs a gate: it is where the breaker lives, and a wedged cluster
    should stop the run rather than be retried at every step.
    """
    return get_gate("azdata-live", max_concurrent=1)


def _print_step(result: StepResult) -> None:
    import sys

    print(
        f"[{result.elapsed_secs:7.1f}s] {result.step} {json.dumps(result.detail, default=str)}",
        file=sys.stderr,
        flush=True,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "COSMOS_ACCOUNT",
    "COSMOS_CONTAINER",
    "COSMOS_DATABASE",
    "COSMOS_DATA_CONTRIBUTOR",
    "COSMOS_PARTITION_KEY",
    "GREMLIN_ACCOUNT",
    "GREMLIN_DATABASE",
    "GREMLIN_GRAPH",
    "KUSTO_CLUSTER",
    "KUSTO_DATABASE",
    "KUSTO_TABLE",
    "LOCATION",
    "LOG_WORKSPACE",
    "OWNER_TAG_KEY",
    "OWNER_TAG_VALUE",
    "RESOURCE_GROUP",
    "ROLES",
    "ROLE_PROPAGATION_BUDGET_SECS",
    "SEARCH_INDEX",
    "SEARCH_SERVICE",
    "STATE_PATH",
    "TOPOLOGY",
    "Environment",
    "LiveEnvironmentError",
    "NameUnavailable",
    "ResourcePlan",
    "RolePlan",
    "StepResult",
    "TeardownRefused",
    "assert_no_secrets",
    "cosmos_account_spec",
    "cosmos_container_spec",
    "cosmos_database_spec",
    "kusto_table_spec",
    "log_workspace_spec",
    "principal_from_token",
    "search_index_spec",
    "search_service_spec",
    "validate_account_name",
]
