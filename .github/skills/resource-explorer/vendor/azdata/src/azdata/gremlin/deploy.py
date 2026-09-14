"""Gremlin deploy plane — a database and a graph, provisioned and read back.

WHY THIS EXISTS
---------------
An agent that stands a graph up, loads it, queries it and tears it down
inside one run has no Bicep pipeline in that loop. It needs the management
plane held to the same contract as the rest of the package: identity not
keys, failure as a value, denied by default.

Two failures motivate everything specific here.

**The partition key path is set once and never surfaces again.** A graph
created with the wrong path — ``/pk`` when the loader writes ``partitionKey``
— provisions successfully, accepts every write, and then returns nothing
from point lookups. The read-back in :meth:`._provision.Provisioner.ensure`
only catches that if the compared fields include the partition key, so
:class:`GremlinGraphProvisioner` narrows the comparison to exactly that,
normalised for the leading slash the service requires and callers forget.

**ARM says Succeeded for writes it did not keep.** An Azure Policy
``Modify`` effect at management-group scope reverts a field moments after a
200. The base class re-reads and reports drift; this module's job is to
hand it a live view whose shape can be compared, which is why
``_do_describe`` returns a normalised dict rather than the raw SDK model.
``azure-mgmt-cosmosdb`` 10 models are ``Mapping`` subclasses whose dict
view is the raw REST payload — camelCase, with ``resource`` nested under
``properties`` and no top-level ``resource`` key at all — so the shape
knowledge lives once, in ``_cosmos_infra.lift_management_model``, and is
imported here rather than restated. Two copies of it is how the two
modules drifted apart in the first place.

The management SDK is synchronous and returns an ``LROPoller`` whose
``result()`` blocks for as long as the service takes. Every call runs off
the event loop, and the base bounds the poller with a deadline, so a wedged
create fails at a timeout instead of hanging the caller forever.

WHAT THIS IS NOT
----------------
Not account provisioning. The Cosmos account, its network rules and its
role assignments are long-lived infrastructure and belong in
infrastructure-as-code; this creates and destroys the two resources inside
an account that a run legitimately owns. Not a throughput manager: the
throughput hints in a spec are passed to ARM and are not read back, so they
are excluded from the drift comparison rather than reported as false drift.

DEPENDENCIES
------------
Standard library, plus ``azure-mgmt-cosmosdb`` loaded on first use.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Mapping

from azdata.core.config import AzureDataConfig
from azdata.cosmos.deploy import lift_management_model, mapping_view
from azdata.core.envelope import error_envelope
from azdata.core.optional import load
from azdata.core.provision import ProvisionPolicy, Provisioner

logger = logging.getLogger(__name__)

# Cosmos supports Hash and MultiHash; Hash is the only one a single-path
# graph can use, and MultiHash needs a different account capability.
DEFAULT_PARTITION_KIND = "Hash"

# Spec keys that ARM accepts on the way in and does not return on the way
# out. Comparing them would report drift on every successful create.
_WRITE_ONLY_SPEC_KEYS = ("throughput", "autoscale_max_throughput")


def _is_not_found(exc: BaseException) -> bool:
    """True when ``exc`` means "the resource is absent", not "the call failed".

    Duck-typed rather than caught by class: importing
    ``azure.core.exceptions`` to name ``ResourceNotFoundError`` would defeat
    the lazy-load rule and break the SDK-free import path.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 404:
        return True
    return type(exc).__name__ == "ResourceNotFoundError"


def _normalise_paths(paths: Any) -> list[str]:
    """Partition key paths as ARM stores them: a list, each rooted with '/'.

    Callers write ``"pk"``, the service returns ``"/pk"``, and an unnormalised
    comparison reads that as drift on a graph that is perfectly correct.
    """
    if paths is None:
        return []
    if isinstance(paths, str):
        paths = [paths]
    return [p if str(p).startswith("/") else f"/{p}" for p in paths]


def _provisioning_state(observed: Mapping[str, Any], resource: Mapping[str, Any]) -> str:
    """The state, wherever this API version chose to put it.

    ARM reports it on the resource for a graph and on the properties block
    for a database, and the base treats an unrecognised state as terminal
    only when it can read one at all.
    """
    for source in (resource, observed):
        for key in ("provisioning_state", "provisioningState"):
            value = source.get(key)
            if isinstance(value, str):
                return value
    return ""


class _CosmosMgmtProvisioner(Provisioner):
    """Shared coordinates and client construction for the Gremlin resources."""

    def __init__(
        self,
        *,
        name: str,
        credential_provider: Callable[[], Any],
        subscription_id: str,
        resource_group: str,
        account_name: str,
        location: str = "",
        policy: ProvisionPolicy | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(name=name, policy=policy)
        self._credential_provider = credential_provider
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._account_name = account_name
        self._location = location
        self._client = client

    @staticmethod
    def _missing_coordinate(config: AzureDataConfig) -> str | None:
        for field in ("subscription_id", "resource_group", "gremlin_account_name"):
            if not getattr(config, field):
                return field
        return None

    def _resources(self) -> Any:
        """The ``gremlin_resources`` operation group, built on first use."""
        if self._client is None:
            mgmt = load("azure.mgmt.cosmosdb", dist="azure-mgmt-cosmosdb")
            self._client = mgmt.CosmosDBManagementClient(
                self._credential_provider(), self._subscription_id
            )
        return self._client.gremlin_resources

    async def _call(self, operation: Any, *args: Any) -> Any:
        """Run a synchronous management call off the event loop."""
        return await asyncio.to_thread(operation, *args)

    async def _describe_or_none(self, operation_name: str, *args: Any) -> Any:
        try:
            return await self._call(getattr(self._resources(), operation_name), *args)
        except Exception as exc:  # noqa: BLE001 - absent is an answer, not a failure
            if _is_not_found(exc):
                return None
            raise

    def _options(self, spec: Mapping[str, Any]) -> dict:
        options: dict[str, Any] = {}
        if spec.get("throughput"):
            options["throughput"] = spec["throughput"]
        if spec.get("autoscale_max_throughput"):
            options["autoscaleSettings"] = {
                "maxThroughput": spec["autoscale_max_throughput"]
            }
        return options


class GremlinDatabaseProvisioner(_CosmosMgmtProvisioner):
    """One Gremlin database inside an existing Cosmos account."""

    resource_kind = "gremlin-database"

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        name: str = "",
        policy: ProvisionPolicy | None = None,
        **kwargs: Any,
    ) -> "GremlinDatabaseProvisioner | str":
        """Build from a frozen config, or return an error envelope.

        A missing coordinate is returned as an envelope rather than raised:
        the deploy plane's whole contract is that failure is a value, and a
        provisioner that cannot name its own resource has nothing to answer
        with later.
        """
        missing = cls._missing_coordinate(config)
        if missing:
            return error_envelope(
                f"{cls.resource_kind} provisioner is not configured: "
                f"'{missing}' is empty"
            )
        database = name or config.gremlin_database
        if not database:
            return error_envelope(
                f"{cls.resource_kind} provisioner is not configured: "
                "'gremlin_database' is empty"
            )
        return cls(
            name=database,
            credential_provider=credential_provider,
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            account_name=config.gremlin_account_name,
            location=config.location,
            policy=policy,
            **kwargs,
        )

    async def _do_describe(self) -> Any | None:
        live = await self._describe_or_none(
            "get_gremlin_database",
            self._resource_group,
            self._account_name,
            self.name,
        )
        if live is None:
            return None
        observed = lift_management_model(live)
        resource = mapping_view(observed.get("resource"))
        return {
            "name": observed.get("name", self.name),
            "provisioning_state": _provisioning_state(observed, resource),
            "resource": resource,
        }

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        parameters = {
            "location": self._location,
            "properties": {
                "resource": {"id": self.name},
                "options": self._options(spec),
            },
        }
        # Returned unresolved: the base bounds the poller with a deadline.
        return await self._call(
            self._resources().begin_create_update_gremlin_database,
            self._resource_group,
            self._account_name,
            self.name,
            parameters,
        )

    async def _do_teardown(self) -> Any:
        return await self._call(
            self._resources().begin_delete_gremlin_database,
            self._resource_group,
            self._account_name,
            self.name,
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            k: v for k, v in spec.items() if k not in _WRITE_ONLY_SPEC_KEYS
        }


class GremlinGraphProvisioner(_CosmosMgmtProvisioner):
    """One graph inside a Gremlin database, checked on its partition key."""

    resource_kind = "gremlin-graph"

    def __init__(self, *, database_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._database_name = database_name

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        name: str = "",
        database_name: str = "",
        policy: ProvisionPolicy | None = None,
        **kwargs: Any,
    ) -> "GremlinGraphProvisioner | str":
        """Build from a frozen config, or return an error envelope."""
        missing = cls._missing_coordinate(config)
        if missing:
            return error_envelope(
                f"{cls.resource_kind} provisioner is not configured: "
                f"'{missing}' is empty"
            )
        database = database_name or config.gremlin_database
        graph = name or config.gremlin_graph
        for field, value in (("gremlin_database", database), ("gremlin_graph", graph)):
            if not value:
                return error_envelope(
                    f"{cls.resource_kind} provisioner is not configured: "
                    f"'{field}' is empty"
                )
        return cls(
            name=graph,
            database_name=database,
            credential_provider=credential_provider,
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            account_name=config.gremlin_account_name,
            location=config.location,
            policy=policy,
            **kwargs,
        )

    @property
    def database_name(self) -> str:
        return self._database_name

    async def _do_describe(self) -> Any | None:
        live = await self._describe_or_none(
            "get_gremlin_graph",
            self._resource_group,
            self._account_name,
            self._database_name,
            self.name,
        )
        if live is None:
            return None
        observed = lift_management_model(live)
        resource = mapping_view(observed.get("resource"))
        # ARM writes ``partitionKey``; a snake-cased spec or fake writes
        # ``partition_key``. Both reach this line.
        partition = mapping_view(
            resource.get("partition_key") or resource.get("partitionKey")
        )
        return {
            "name": observed.get("name", self.name),
            "partition_key_paths": _normalise_paths(partition.get("paths")),
            "provisioning_state": _provisioning_state(observed, resource),
            "resource": resource,
        }

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        paths = _normalise_paths(
            spec.get("partition_key_paths") or spec.get("partition_key_path")
        )
        if not paths:
            raise ValueError(
                "a Gremlin graph spec must carry 'partition_key_paths'; the "
                "path cannot be changed after creation"
            )
        resource: dict[str, Any] = {
            "id": self.name,
            "partitionKey": {
                "paths": paths,
                "kind": spec.get("partition_kind", DEFAULT_PARTITION_KIND),
            },
        }
        if spec.get("indexing_policy") is not None:
            resource["indexingPolicy"] = spec["indexing_policy"]
        if spec.get("default_ttl") is not None:
            resource["defaultTtl"] = spec["default_ttl"]
        parameters = {
            "location": self._location,
            "properties": {"resource": resource, "options": self._options(spec)},
        }
        # Returned unresolved: the base bounds the poller with a deadline.
        return await self._call(
            self._resources().begin_create_update_gremlin_graph,
            self._resource_group,
            self._account_name,
            self._database_name,
            self.name,
            parameters,
        )

    async def _do_teardown(self) -> Any:
        return await self._call(
            self._resources().begin_delete_gremlin_graph,
            self._resource_group,
            self._account_name,
            self._database_name,
            self.name,
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        """Compare the partition key path, and only that.

        The one field whose corruption is silent: a graph with the wrong
        path provisions, accepts writes, and returns nothing from point
        lookups weeks later. Everything else in a spec is either echoed
        verbatim or not returned at all.
        """
        return {
            "partition_key_paths": _normalise_paths(
                spec.get("partition_key_paths") or spec.get("partition_key_path")
            )
        }


__all__ = [
    "DEFAULT_PARTITION_KIND",
    "GremlinDatabaseProvisioner",
    "GremlinGraphProvisioner",
]
