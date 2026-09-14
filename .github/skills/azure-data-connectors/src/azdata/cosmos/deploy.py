"""Cosmos NoSQL deploy plane — account, database and container, then proof.

WHY THIS EXISTS
---------------
An agent that has to stand a Cosmos account up, load it, query it and tear
it down inside one run has no deployment pipeline in that loop. Shelling
out to ``az`` turns every failure into a string to parse. This is the
management plane held to the package contract: identity not keys, failure
as a value, denied by default.

Three failures specific to Cosmos motivate every decision below.

**Azure Policy silently rewrites what you asked for.** ARM accepts a
``begin_create_or_update`` and returns ``provisioningState: Succeeded``
for an account whose ``public_network_access`` a ``Modify`` effect at a
management-group scope has already reverted to ``Disabled``, and whose
``disable_local_auth`` it has flipped back. Nothing in the write response
says so; the next connection attempt is what tells you, from inside a
timeout somewhere else. :meth:`Provisioner.ensure` re-reads and reports
those fields as drift, which is the entire reason this module is worth
having over a wrapper around the SDK call.

**Region names and the failover list are normalised on the way in.**
``location`` submitted as ``"Australia East"`` reads back as
``"australiaeast"``, and ``locations`` comes back reordered and enriched
with ids and failover priorities. Comparing either would report drift on
every successful deployment and train the operator to ignore the field
that matters, so both are dropped from the verified subset.

**A container created with the wrong partition key is unusable and the
mistake is invisible.** Writes succeed, point reads against the intended
key 404, and a delete silently no-ops — the failure the write plane in
``cosmos/write.py`` exists to prevent, arriving instead through the
infrastructure. :class:`CosmosContainerProvisioner` compares the partition
key paths explicitly.

**A read-back you cannot compare proves nothing.** ``azure-mgmt-cosmosdb``
10 models are ``Mapping`` subclasses whose dict view is the raw REST
payload: camelCase keys, with everything worth checking buried under
``properties``. Attribute access flattens one level, ``dict(model)`` does
not, and the base class compares dicts one level deep — so a read-back
handed over untouched reports drift on every healthy deployment, which
trains an operator to ignore the one signal this module exists to raise.
:func:`lift_management_model` does the flattening the dict view does not,
and accepts either spelling so a hand-written ARM-shaped spec and a live
model normalise to the same thing.

**Long-running operations are bounded, but Cosmos is genuinely slow.** The
management SDK is synchronous, so every call runs off the loop through
``asyncio.to_thread`` and every poller is resolved by ``await_poller``
against a deadline. An account with a private endpoint routinely takes
five to eight minutes; the package default of 900 seconds is sized for
that, and lowering it below roughly ten minutes will time out a deployment
that was going to succeed. Database and container creation are seconds.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Specs are plain dicts passed through to the SDK. The partition key path
lives in the caller's spec; no field name from any consuming application
appears here.

WHAT THIS IS NOT
----------------
Not infrastructure-as-code and not a state store. No plan, no dependency
graph: the caller ensures the account, then the database, then the
container, in that order, because ARM will not do it for you.

DEPENDENCIES
------------
Standard library, plus ``azure-mgmt-cosmosdb`` loaded on first use.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Mapping

from azdata.core.config import AzureDataConfig
from azdata.core.envelope import error_envelope
from azdata.core.optional import load
from azdata.core.provision import ProvisionPolicy, Provisioner

logger = logging.getLogger(__name__)

# ARM normalises the region name and reorders the failover list, so both
# read back different from what was submitted on a wholly successful write.
_NORMALISED_ACCOUNT_FIELDS = frozenset({"location", "locations"})

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _is_not_found(exc: Exception) -> bool:
    """True for ARM's 'no such resource'.

    Matched on the status code and the exception's type name rather than by
    importing ``azure.core.exceptions``, which would break the
    optional-SDK contract for a single comparison.
    """
    if getattr(exc, "status_code", None) == 404:
        return True
    return type(exc).__name__ == "ResourceNotFoundError"


def build_management_client(credential: Any, subscription_id: str) -> Any:
    """Return a ``CosmosDBManagementClient``. The only SDK entry point here."""
    mgmt = load("azure.mgmt.cosmosdb", dist="azure-mgmt-cosmosdb")
    return mgmt.CosmosDBManagementClient(credential, subscription_id)


def _missing_coordinate(config: AzureDataConfig, fields: tuple[str, ...]) -> str:
    """Name the first unset management coordinate, or ``""``."""
    for field in fields:
        if not getattr(config, field, ""):
            return field
    return ""


class _CosmosProvisioner(Provisioner):
    """Shared plumbing: a synchronous management client, run off the loop."""

    def __init__(
        self,
        *,
        client: Any,
        resource_group: str,
        name: str,
        policy: ProvisionPolicy | None = None,
    ) -> None:
        super().__init__(name=name, policy=policy)
        self._client = client
        self._resource_group = resource_group

    @property
    def client(self) -> Any:
        return self._client

    async def _off_loop(self, call: Callable[..., Any], *args: Any) -> Any:
        """Run a blocking management call without stalling the event loop."""
        return await asyncio.to_thread(call, *args)

    async def _read(self, call: Callable[..., Any], *args: Any) -> Any | None:
        """A describe: absent is None, every other failure propagates."""
        try:
            return await self._off_loop(call, *args)
        except Exception as exc:  # noqa: BLE001 - absence is an answer
            if _is_not_found(exc):
                return None
            raise


class CosmosAccountProvisioner(_CosmosProvisioner):
    """One Cosmos DB account, verified against Azure Policy after the write.

    ``poll_timeout_secs`` deserves a deliberate value here: an account with
    a private endpoint takes five to eight minutes, so the package default
    of 900 seconds is the floor of sanity rather than a generous margin.
    """

    resource_kind = "cosmos-account"

    async def _do_describe(self) -> Any | None:
        live = await self._read(
            self._client.database_accounts.get, self._resource_group, self.name
        )
        if live is None:
            return None
        # ``publicNetworkAccess`` and ``disableLocalAuth`` come back under
        # ``properties``; unlifted they read as absent, which is drift.
        return lift_management_model(live)

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        # Returned unresolved: the base bounds the poller against the policy
        # deadline, and resolving here would block for minutes.
        return await self._off_loop(
            self._client.database_accounts.begin_create_or_update,
            self._resource_group,
            self.name,
            dict(spec),
        )

    async def _do_teardown(self) -> Any:
        return await self._off_loop(
            self._client.database_accounts.begin_delete,
            self._resource_group,
            self.name,
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        """Everything but the fields ARM rewrites for legitimate reasons.

        The spec goes through the same lift as the read-back, so a flat
        snake-cased spec and an ARM-shaped one compare against the same
        normalised names. What survives is what a Policy ``Modify`` effect
        rewrites illegitimately — ``public_network_access`` and
        ``disable_local_auth`` above all — which is exactly why the base
        re-reads instead of trusting the write response.
        """
        return {
            key: value
            for key, value in lift_management_model(spec).items()
            if key not in _NORMALISED_ACCOUNT_FIELDS
        }

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        policy: ProvisionPolicy | None = None,
        name: str = "",
    ) -> "CosmosAccountProvisioner | str":
        """Build from config, or return an error envelope naming what is unset."""
        missing = _missing_coordinate(
            config, ("subscription_id", "resource_group", "location")
        )
        if not missing and not (name or config.cosmos_account_name):
            missing = "cosmos_account_name"
        if missing:
            return error_envelope(f"cosmos deploy plane not configured: {missing}")
        return cls(
            client=build_management_client(
                credential_provider(), config.subscription_id
            ),
            resource_group=config.resource_group,
            name=name or config.cosmos_account_name,
            policy=policy,
        )


class CosmosDatabaseProvisioner(_CosmosProvisioner):
    """One SQL database inside an account. Seconds, not minutes."""

    resource_kind = "cosmos-database"

    def __init__(self, *, account_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._account_name = account_name

    async def _do_describe(self) -> Any | None:
        live = await self._read(
            self._client.sql_resources.get_sql_database,
            self._resource_group,
            self._account_name,
            self.name,
        )
        if live is None:
            return None
        observed = lift_management_model(live)
        observed["database_id"] = _resource_id(observed) or self.name
        return observed

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        """The database id, and only that.

        Everything else in the spec is either write-only (``options``,
        throughput) or enriched by the service on the way out (``_rid``,
        ``_etag``, ``_ts``, the whole ``resource`` block), so comparing the
        spec verbatim reports drift on every healthy deployment — which is
        how an operator learns to ignore the one signal this plane exists
        to raise.
        """
        return {"database_id": _resource_id(spec) or self.name}

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        return await self._off_loop(
            self._client.sql_resources.begin_create_update_sql_database,
            self._resource_group,
            self._account_name,
            self.name,
            dict(spec),
        )

    async def _do_teardown(self) -> Any:
        return await self._off_loop(
            self._client.sql_resources.begin_delete_sql_database,
            self._resource_group,
            self._account_name,
            self.name,
        )

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        database: str,
        policy: ProvisionPolicy | None = None,
        account_name: str = "",
    ) -> "CosmosDatabaseProvisioner | str":
        missing = _missing_coordinate(config, ("subscription_id", "resource_group"))
        if not missing and not (account_name or config.cosmos_account_name):
            missing = "cosmos_account_name"
        if missing:
            return error_envelope(f"cosmos deploy plane not configured: {missing}")
        return cls(
            client=build_management_client(
                credential_provider(), config.subscription_id
            ),
            resource_group=config.resource_group,
            account_name=account_name or config.cosmos_account_name,
            name=database,
            policy=policy,
        )


class CosmosContainerProvisioner(_CosmosProvisioner):
    """One SQL container, verified on the partition key path above all else.

    The spec carries the partition key. Getting it wrong produces a
    container that accepts writes and then 404s every point read and
    no-ops every delete, so the paths are compared explicitly and
    everything else in the spec is left alone: throughput, indexing policy
    and TTL are all normalised and enriched by the service on the way in,
    and comparing them reports drift on every healthy deployment.
    """

    resource_kind = "cosmos-container"

    def __init__(self, *, account_name: str, database: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._account_name = account_name
        self._database = database

    async def _do_describe(self) -> Any | None:
        live = await self._read(
            self._client.sql_resources.get_sql_container,
            self._resource_group,
            self._account_name,
            self._database,
            self.name,
        )
        if live is None:
            return None
        # Lifted so the base's one-level drift comparison can see a value the
        # SDK nests two levels down inside ``properties.resource``.
        observed = lift_management_model(live)
        observed["partition_key_paths"] = _partition_key_paths(observed)
        return observed

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        return await self._off_loop(
            self._client.sql_resources.begin_create_update_sql_container,
            self._resource_group,
            self._account_name,
            self._database,
            self.name,
            dict(spec),
        )

    async def _do_teardown(self) -> Any:
        return await self._off_loop(
            self._client.sql_resources.begin_delete_sql_container,
            self._resource_group,
            self._account_name,
            self._database,
            self.name,
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"partition_key_paths": _partition_key_paths(spec)}

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        database: str,
        container: str,
        policy: ProvisionPolicy | None = None,
        account_name: str = "",
    ) -> "CosmosContainerProvisioner | str":
        missing = _missing_coordinate(config, ("subscription_id", "resource_group"))
        if not missing and not (account_name or config.cosmos_account_name):
            missing = "cosmos_account_name"
        if missing:
            return error_envelope(f"cosmos deploy plane not configured: {missing}")
        return cls(
            client=build_management_client(
                credential_provider(), config.subscription_id
            ),
            resource_group=config.resource_group,
            account_name=account_name or config.cosmos_account_name,
            database=database,
            name=container,
            policy=policy,
        )


def mapping_view(model: Any) -> dict:
    """Dict view of an SDK model, a mapping or a fake, without importing the SDK.

    ``azure-mgmt-cosmosdb`` 10 models are ``Mapping`` subclasses, so the
    isinstance branch is the one that fires in production; ``as_dict`` is
    kept for the msrest-style models an older pin would hand over, and
    ``vars`` for a test double that is neither.
    """
    if model is None:
        return {}
    if isinstance(model, Mapping):
        return dict(model)
    converter = getattr(model, "as_dict", None)
    if callable(converter):
        return converter()
    return {k: v for k, v in vars(model).items() if not k.startswith("_")}


def _snake(name: str) -> str:
    """``publicNetworkAccess`` -> ``public_network_access``; snake stays snake."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _plain(value: Any) -> Any:
    """Nested SDK models as plain data, so ``==`` compares values not types.

    Keys are left alone below the lifted levels: a tag dict is caller data
    and renaming its keys would be a fabrication.
    """
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def lift_management_model(model: Any) -> dict:
    """A read-back the base's one-level drift comparison can actually see.

    ``dict(SqlContainerGetResults(...))`` is ``{'id', 'name', 'type',
    'properties'}`` — the interesting values are all one level down under
    ``properties``, in camelCase, and there is no top-level ``resource``
    key however much the attribute accessor suggests otherwise. This lifts
    ``properties`` up one level and snake-cases the keys at both lifted
    levels, so a live v10 model, an ``as_dict()`` model and a plain fake
    dict all normalise to the same shape.
    """
    observed = mapping_view(model)
    lifted: dict[str, Any] = {
        _snake(str(key)): _plain(value)
        for key, value in observed.items()
        if key != "properties"
    }
    for key, value in mapping_view(observed.get("properties")).items():
        # setdefault: an ARM resource id at the top level is not the
        # resource's own id, and the top-level one is the addressable name.
        lifted.setdefault(_snake(str(key)), _plain(value))
    return lifted


def _resource_id(source: Mapping[str, Any]) -> str:
    """The id inside ``resource``, wherever this spelling put it.

    ``resource`` sits at the top level of a hand-written spec and under
    ``properties`` in a read-back; both arrive here in practice.
    """
    resource = source.get("resource")
    if resource is None:
        properties = mapping_view(source.get("properties"))
        resource = properties.get("resource")
    return str(mapping_view(resource).get("id") or "")


def _partition_key_paths(source: Mapping[str, Any]) -> list[str]:
    """Extract the partition key paths from a spec or a read-back container.

    ``resource`` sits at the top level of a hand-written spec and under
    ``properties`` in a read-back, and the key beneath it is ``partitionKey``
    on the wire and ``partition_key`` in a snake-cased spec. All four
    combinations arrive here in practice, so all four are accepted.
    """
    if "partition_key_paths" in source:
        return list(source.get("partition_key_paths") or [])
    resource = source.get("resource")
    if resource is None:
        properties = mapping_view(source.get("properties"))
        resource = properties.get("resource")
    resource = mapping_view(resource)
    key = mapping_view(
        resource.get("partition_key") or resource.get("partitionKey")
    )
    return list(key.get("paths") or [])


__all__ = [
    "CosmosAccountProvisioner",
    "CosmosContainerProvisioner",
    "CosmosDatabaseProvisioner",
    "build_management_client",
    "lift_management_model",
    "mapping_view",
]
