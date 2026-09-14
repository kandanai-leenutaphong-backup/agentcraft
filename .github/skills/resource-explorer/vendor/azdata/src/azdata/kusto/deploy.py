"""Kusto deploy plane — the cluster and database through ARM, the table on
the data plane.

WHY THIS EXISTS
---------------
Two planes again, and the split is not cosmetic. An ADX cluster and a
database are ARM resources with an ``azure-mgmt-kusto`` client in front of
them; a *table* is not an ARM resource at all and never will be. Creating
one is the control command ``.create-merge table`` executed against the
cluster's query endpoint, authorised by a database role rather than by a
management-plane role. That is exactly the split Azure AI Search already
forces on this package — ``SearchServiceProvisioner`` is ARM,
``SearchIndexProvisioner`` is the data plane — and the shape here mirrors
it deliberately, so a reader who has understood one has understood both.

Three failures specific to Kusto motivate the rest.

**A cluster create takes ten to fifteen minutes and an agent run does
not.** ``begin_create_or_update`` returns immediately and the cluster
spends the next quarter of an hour in ``provisioningState: Creating``.
:data:`CLUSTER_POLL_TIMEOUT_SECS` is therefore thirty minutes rather than
the package default of fifteen, and — more importantly — a re-run after a
timeout must *resume*, not restart. :class:`KustoClusterProvisioner`
describes before it writes: a cluster already mid-creation is waited on
rather than re-submitted, so the second ``ensure`` continues the first
one's deployment instead of queueing another.

**The third management SDK does not agree with the second.** This package
already normalises two mutually incompatible model styles (GOTCHAS G18):
``azure-mgmt-search`` 9.x is msrest — ``as_dict()`` returns flattened
snake_case, no ``properties`` block — while ``azure-mgmt-cosmosdb`` 10.x is
JSON-backed, its models are ``Mapping`` subclasses whose dict view is the
raw camelCase REST payload nested under ``properties``. Introspection of
``azure-mgmt-kusto`` 4.0.0 settles which one applies here:
``isinstance(Cluster(...), collections.abc.Mapping)`` is ``True``, the MRO
runs through ``_MyMutableMapping``, and ``Cluster(location="eastus",
enable_streaming_ingest=True).as_dict()`` is ``{'location': 'eastus',
'properties': {'enableStreamingIngest': True}}``. It is the **JSON-backed
camelCase style**, like Cosmos and unlike Search. :func:`lift_kusto_model`
flattens it, and ``tests/unit/test_kusto_planes.py`` pins that shape so an
SDK bump that reverts to msrest fails loudly instead of reporting drift on
every healthy deployment. The lift also passes an already-flat
snake_case payload through unchanged, which is what a 3.x msrest pin
would hand over.

**A stopped cluster is a healthy cluster.** ``state`` reads ``Stopped``
while ``provisioningState`` still reads ``Succeeded``; the base reads the
provisioning state first, so ``pause`` does not make ``ensure`` report a
failure. :meth:`KustoClusterProvisioner.stop` and ``start`` exist because
stopping is the only real cost lever this environment has.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Specs are plain dicts. The table provisioner knows a table has columns
with names and types; the names are the caller's and are validated as
plain identifiers before they are interpolated, never escaped.

WHAT THIS IS NOT
----------------
Not infrastructure-as-code, not a state store, no dependency graph: the
caller ensures the cluster, then the database, then the table, in that
order, because ARM will not do it for you.

DEPENDENCIES
------------
Standard library, plus ``azure-mgmt-kusto`` (cluster and database) loaded
on first use, and ``azure-kusto-data`` behind the connector the table
provisioner is handed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, Mapping, Sequence

from azdata.core.config import AzureDataConfig
from azdata.core.envelope import error_envelope, is_error, success_envelope
from azdata.core.optional import load
from azdata.core.provision import (
    ProvisionPolicy,
    ProvisionRefused,
    Provisioner,
    await_poller,
)
from azdata.kusto.write import control_connector

logger = logging.getLogger(__name__)

#: The Dev/No-SLA cluster: one instance, no availability guarantee, and the
#: only ADX shape that costs cents rather than dollars per hour.
#:
#: D11_v2 rather than E2a_v4: East US returned InsufficientResourcesForSubscription
#: for E2a_v4 and suggested a different SKU size. Both are listed as available by
#: ``az kusto cluster list-sku``, which is a catalogue of what the region offers
#: and not a statement about capacity right now.
DEV_SKU: Mapping[str, Any] = {
    "name": "Dev(No SLA)_Standard_D11_v2",
    "tier": "Basic",
    "capacity": 1,
}

# A cluster create is ten to fifteen minutes on a good day. The package
# default of 900s would time out a deployment that was going to succeed,
# so this one is stated explicitly and generously; a re-run resumes.
CLUSTER_POLL_TIMEOUT_SECS = 1800.0

# How often the resume path re-reads a cluster that is already deploying.
CLUSTER_POLL_INTERVAL_SECS = 20.0

# Kusto provisioning states that mean "still working". Anything else is
# terminal and the base class decides whether it was a good terminal.
IN_FLIGHT_STATES = frozenset({"creating", "updating", "moving", "deleting"})

# Fields ARM rewrites for legitimate reasons. ``location`` is normalised
# ("East US" -> "eastus"), ``identity`` comes back enriched with a
# principal and tenant id the caller never sent, and ``zones`` is filled in
# by the platform. Comparing any of them reports drift on a healthy
# cluster and trains the operator to ignore the field that matters.
_NORMALISED_CLUSTER_FIELDS = frozenset({"location", "identity", "zones"})

# Same, for a database. ADX re-renders ISO-8601 durations on the way out
# ("P30D" is not the spelling that comes back), and ``statistics`` is a
# live measurement, not a setting.
_NORMALISED_DATABASE_FIELDS = frozenset(
    {"location", "statistics", "soft_delete_period", "hot_cache_period"}
)

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

# The only caller values interpolated into a control command. Anything
# outside this shape is refused rather than escaped: Kusto identifier
# quoting has enough corners that refusal is the safer contract.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class KustoDeployError(RuntimeError):
    """A deploy-plane precondition failed before any Azure call was made."""


def _is_not_found(exc: BaseException) -> bool:
    """True when ``exc`` means "absent", not "the call failed".

    Duck-typed rather than caught by class: importing
    ``azure.core.exceptions`` would defeat the lazy-load rule and break the
    SDK-free import path.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 404:
        return True
    return type(exc).__name__ == "ResourceNotFoundError"


def _snake(name: str) -> str:
    """``enableStreamingIngest`` -> ``enable_streaming_ingest``; snake stays snake."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def mapping_view(model: Any) -> dict:
    """Dict view of an SDK model, a mapping or a fake, without importing the SDK.

    ``azure-mgmt-kusto`` 4.x models are ``Mapping`` subclasses, so the
    isinstance branch is the one that fires in production. ``as_dict`` is
    kept for the msrest-style models a 3.x pin hands over, and ``vars`` for
    a test double that is neither.
    """
    if model is None:
        return {}
    if isinstance(model, Mapping):
        return dict(model)
    converter = getattr(model, "as_dict", None)
    if callable(converter):
        return converter()
    return {k: v for k, v in vars(model).items() if not k.startswith("_")}


def _plain(value: Any) -> Any:
    """Nested SDK models as plain data, so ``==`` compares values not types."""
    if isinstance(value, Mapping):
        return {_snake(str(key)): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def lift_kusto_model(model: Any) -> dict:
    """A read-back the base's one-level drift comparison can actually see.

    ``dict(Cluster(...))`` is ``{'location', 'sku', 'properties'}`` with
    everything worth checking one level down under ``properties``, in
    camelCase — the JSON-backed style introspected on
    ``azure-mgmt-kusto`` 4.0.0. This lifts ``properties`` up one level and
    snake-cases the keys, so a live 4.x model, a flattened msrest
    ``as_dict()`` from a 3.x pin, and a plain fake dict all normalise to
    the same shape.
    """
    observed = mapping_view(model)
    lifted: dict[str, Any] = {
        _snake(str(key)): _plain(value)
        for key, value in observed.items()
        if key != "properties"
    }
    for key, value in mapping_view(observed.get("properties")).items():
        # setdefault: a top-level key is the addressable one and must win
        # over a same-named property.
        lifted.setdefault(_snake(str(key)), _plain(value))
    return lifted


def build_management_client(credential: Any, subscription_id: str) -> Any:
    """Return a ``KustoManagementClient``. The only ARM entry point here."""
    mgmt = load("azure.mgmt.kusto", dist="azure-mgmt-kusto")
    return mgmt.KustoManagementClient(credential, subscription_id)


def cluster_policy(*, allow_delete: bool = False) -> ProvisionPolicy:
    """A deploy policy sized for a cluster create, not for a database one."""
    return ProvisionPolicy.deployable(
        allow_delete=allow_delete, poll_timeout_secs=CLUSTER_POLL_TIMEOUT_SECS
    )


def _missing_coordinate(config: AzureDataConfig, fields: Sequence[str]) -> str:
    for field in fields:
        if not getattr(config, field, ""):
            return field
    return ""


class _KustoMgmtProvisioner(Provisioner):
    """Shared plumbing: a synchronous management client, run off the loop."""

    def __init__(
        self,
        *,
        client: Any,
        resource_group: str,
        name: str,
        location: str = "",
        policy: ProvisionPolicy | None = None,
    ) -> None:
        super().__init__(name=name, policy=policy)
        self._client = client
        self._resource_group = resource_group
        self._location = location

    @property
    def client(self) -> Any:
        return self._client

    @property
    def location(self) -> str:
        return self._location

    async def _off_loop(self, call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(lambda: call(*args, **kwargs))

    async def _read(self, call: Callable[..., Any], *args: Any) -> Any | None:
        """A describe: absent is None, every other failure propagates."""
        try:
            return await self._off_loop(call, *args)
        except Exception as exc:  # noqa: BLE001 - absence is an answer
            if _is_not_found(exc):
                return None
            raise


class _ResumePoller:
    """Poll an in-flight ARM deployment instead of submitting another one.

    Returned in place of an ``LROPoller`` when the resource is already
    being created. ``result()`` blocks, exactly as a real poller does, so
    a re-run after a timeout continues the first deployment rather than
    starting a second.

    It carries its own deadline as well. ``await_poller`` bounds the
    *await*, not the thread the poll runs on: an unbounded loop in here
    would keep spinning in a worker thread long after the caller gave up,
    and the process would not exit.
    """

    def __init__(
        self,
        read: Callable[[], Any],
        *,
        interval: float = CLUSTER_POLL_INTERVAL_SECS,
        deadline_secs: float = CLUSTER_POLL_TIMEOUT_SECS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read = read
        self._interval = interval
        self._deadline = deadline_secs
        self._sleep = sleep
        self._clock = clock

    def result(self) -> Any:
        started = self._clock()
        while True:
            live = self._read()
            observed = lift_kusto_model(live) if live is not None else {}
            state = str(observed.get("provisioning_state") or "")
            if state.lower() not in IN_FLIGHT_STATES:
                return live
            if self._clock() - started >= self._deadline:
                raise TimeoutError(
                    f"the cluster is still '{state}' after "
                    f"{self._deadline:.0f}s of polling"
                )
            self._sleep(self._interval)


class KustoClusterProvisioner(_KustoMgmtProvisioner):
    """One ADX cluster: ten to fifteen minutes to create, resumable, idempotent.

    ``ensure`` is safe to call again after a timeout. It describes first:
    a cluster already in ``Creating`` is waited on through
    :class:`_ResumePoller` rather than re-submitted, so the second run
    finishes the first run's deployment. A cluster that is absent, or
    present and terminal, goes through ``begin_create_or_update``, which
    ARM itself treats as idempotent.
    """

    resource_kind = "kusto-cluster"

    def __init__(self, *, poll_interval_secs: float = CLUSTER_POLL_INTERVAL_SECS, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._poll_interval = poll_interval_secs

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        name: str,
        policy: ProvisionPolicy | None = None,
        **kwargs: Any,
    ) -> "KustoClusterProvisioner | str":
        missing = _missing_coordinate(
            config, ("subscription_id", "resource_group", "location")
        )
        if missing:
            return error_envelope(f"kusto deploy plane not configured: {missing}")
        return cls(
            client=build_management_client(
                credential_provider(), config.subscription_id
            ),
            resource_group=config.resource_group,
            name=name,
            location=config.location,
            policy=policy or cluster_policy(),
            **kwargs,
        )

    def default_spec(self, **overrides: Any) -> dict:
        """The Dev/No-SLA spec this package deploys, with the location filled in."""
        spec: dict[str, Any] = {
            "location": self._location,
            "sku": dict(DEV_SKU),
        }
        spec.update(overrides)
        return spec

    async def _do_describe(self) -> Any | None:
        live = await self._read(
            self._client.clusters.get, self._resource_group, self.name
        )
        if live is None:
            return None
        return lift_kusto_model(live)

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        live = await self._do_describe()
        state = str((live or {}).get("provisioning_state") or "")
        if live is not None and state.lower() in IN_FLIGHT_STATES:
            # Resume. Re-submitting a create against a cluster that is
            # already deploying restarts the wait for no benefit.
            logger.info(
                "kusto.cluster_resume name=%s state=%s", self.name, state
            )
            return _ResumePoller(
                lambda: self._client.clusters.get(self._resource_group, self.name),
                interval=self._poll_interval,
                deadline_secs=self._policy.poll_timeout_secs,
            )
        # Returned unresolved on purpose: the base bounds the LRO against
        # the policy deadline, and resolving here blocks for a quarter hour.
        return await self._off_loop(
            self._client.clusters.begin_create_or_update,
            self._resource_group,
            self.name,
            dict(spec),
        )

    async def _do_teardown(self) -> Any:
        return await self._off_loop(
            self._client.clusters.begin_delete, self._resource_group, self.name
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            key: value
            for key, value in lift_kusto_model(spec).items()
            if key not in _NORMALISED_CLUSTER_FIELDS
        }

    # ------------------------------------------------------------------
    # The cost lever.
    # ------------------------------------------------------------------

    async def stop(self) -> str:
        """Stop the cluster. Data survives; the hourly charge does not."""
        return await self._power("stop", self._client.clusters.begin_stop)

    async def start(self) -> str:
        """Start a stopped cluster. Minutes, not the full create."""
        return await self._power("start", self._client.clusters.begin_start)

    async def _power(self, operation: str, call: Callable[..., Any]) -> str:
        if not self._policy.allow_create:
            return self._failure(
                operation,
                ProvisionRefused(
                    "kusto-cluster provisioner may not change power state. "
                    "Build it with ProvisionPolicy.deployable()."
                ),
            )
        try:
            poller = await self._off_loop(call, self._resource_group, self.name)
            await await_poller(poller, self._policy.poll_timeout_secs)
            live = await self._do_describe()
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure(operation, exc)
        return success_envelope(
            operation,
            resource_kind=self.resource_kind,
            name=self.name,
            state=str((live or {}).get("state") or ""),
        )


class KustoDatabaseProvisioner(_KustoMgmtProvisioner):
    """One ReadWrite database on a cluster. Seconds, not minutes."""

    resource_kind = "kusto-database"

    def __init__(self, *, cluster_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cluster_name = cluster_name

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        cluster_name: str,
        database: str,
        policy: ProvisionPolicy | None = None,
    ) -> "KustoDatabaseProvisioner | str":
        missing = _missing_coordinate(
            config, ("subscription_id", "resource_group", "location")
        )
        if missing:
            return error_envelope(f"kusto deploy plane not configured: {missing}")
        return cls(
            client=build_management_client(
                credential_provider(), config.subscription_id
            ),
            resource_group=config.resource_group,
            cluster_name=cluster_name,
            name=database,
            location=config.location,
            policy=policy,
        )

    @property
    def cluster_name(self) -> str:
        return self._cluster_name

    def default_spec(self, **overrides: Any) -> dict:
        """A ReadWrite database. ``kind`` is the discriminator, not a hint."""
        spec: dict[str, Any] = {"kind": "ReadWrite", "location": self._location}
        spec.update(overrides)
        return spec

    async def _do_describe(self) -> Any | None:
        live = await self._read(
            self._client.databases.get,
            self._resource_group,
            self._cluster_name,
            self.name,
        )
        if live is None:
            return None
        return lift_kusto_model(live)

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        parameters = dict(spec)
        # Without the discriminator the service cannot tell a ReadWrite
        # database from a follower and rejects the payload.
        parameters.setdefault("kind", "ReadWrite")
        parameters.setdefault("location", self._location)
        return await self._off_loop(
            self._client.databases.begin_create_or_update,
            self._resource_group,
            self._cluster_name,
            self.name,
            parameters,
        )

    async def _do_teardown(self) -> Any:
        return await self._off_loop(
            self._client.databases.begin_delete,
            self._resource_group,
            self._cluster_name,
            self.name,
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            key: value
            for key, value in lift_kusto_model(spec).items()
            if key not in _NORMALISED_DATABASE_FIELDS
        }


class KustoTableProvisioner(Provisioner):
    """One table, created by control command on the **data** plane.

    A table is not an ARM resource. ``.create-merge table`` runs against
    the cluster's query endpoint and is authorised by a database role, so
    this provisioner takes a :class:`~azdata.kusto.read.KqlConnector`
    rather than a management client — the same split as
    ``SearchIndexProvisioner`` (data plane) against
    ``SearchServiceProvisioner`` (ARM).

    Drift is the declared column set. A column the caller declared that is
    not in the live schema silently drops every value written to it, which
    is the failure worth catching; an *extra* live column is reported too,
    because the spec is an assertion about the schema and a table that is
    not the asserted schema is not the requested state.
    """

    resource_kind = "kusto-table"

    def __init__(
        self,
        *,
        connector: Any,
        name: str,
        policy: ProvisionPolicy | None = None,
    ) -> None:
        super().__init__(name=name, policy=policy)
        # Generated control commands only. Caller text never reaches it:
        # every identifier below is validated before interpolation.
        self._commands = control_connector(connector)

    @staticmethod
    def _identifier(name: str, what: str) -> str:
        if not name or not _IDENTIFIER.match(str(name)):
            raise KustoDeployError(
                f"'{name}' is not a plain Kusto identifier and will not be "
                f"interpolated as a {what}"
            )
        return str(name)

    async def _command(self, command: str) -> list[dict]:
        payload = await self._commands.execute(command)
        if is_error(payload):
            raise KustoDeployError(
                json.loads(payload).get("detail", "control command failed")
            )
        shaped = json.loads(payload)
        return list(shaped.get("rows") or []) if isinstance(shaped, dict) else []

    async def _exists(self) -> bool:
        """``.show tables`` filtered in Python — nothing is interpolated."""
        rows = await self._command(".show tables")
        return any(str(row.get("TableName")) == self.name for row in rows)

    async def _do_describe(self) -> Any | None:
        table = self._identifier(self.name, "table")
        if not await self._exists():
            return None
        rows = await self._command(f".show table {table} cslschema")
        if not rows:
            return None
        return {
            "name": table,
            "columns": _parse_cslschema(rows[0].get("Schema", "")),
        }

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        table = self._identifier(self.name, "table")
        columns = _columns(spec)
        if not columns:
            raise KustoDeployError(
                "a Kusto table spec must carry 'columns' mapping column name "
                "to Kusto type; a table with no columns cannot be created"
            )
        declared = ", ".join(
            f"{self._identifier(column, 'column name')}:"
            f"{self._identifier(ctype, 'column type')}"
            for column, ctype in columns.items()
        )
        # create-merge, not create: it is the idempotent form and the second
        # ensure of an unchanged schema is a no-op rather than an error.
        await self._command(f".create-merge table {table} ({declared})")
        return None

    async def _do_teardown(self) -> Any:
        table = self._identifier(self.name, "table")
        await self._command(f".drop table {table} ifexists")
        return None

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"columns": _columns(spec)}


def _columns(spec: Mapping[str, Any]) -> dict[str, str]:
    """The declared columns of a table spec, as ``{name: kusto_type}``.

    A mapping and a list of ``{"name", "type"}`` dicts both arrive in
    practice — the first from this package's own topology, the second from
    anything that read a schema out of the service.
    """
    columns = spec.get("columns", spec)
    if isinstance(columns, Mapping):
        return {str(k): str(v) for k, v in columns.items()}
    parsed: dict[str, str] = {}
    for column in columns or []:
        if isinstance(column, Mapping):
            name = column.get("name")
            ctype = column.get("type") or column.get("CslType")
            if name is not None:
                parsed[str(name)] = str(ctype)
    return parsed


def _parse_cslschema(schema: Any) -> dict[str, str]:
    """``"Id:string,Site:string"`` -> ``{"Id": "string", "Site": "string"}``.

    The shape ``.show table T cslschema`` answers in. An empty or
    unparseable schema returns ``{}``, which the base then reports as
    drift against any non-empty spec — the correct outcome for a table
    whose schema could not be read.
    """
    parsed: dict[str, str] = {}
    for part in str(schema or "").split(","):
        name, sep, ctype = part.partition(":")
        if sep and name.strip():
            parsed[name.strip()] = ctype.strip()
    return parsed


__all__ = [
    "CLUSTER_POLL_INTERVAL_SECS",
    "CLUSTER_POLL_TIMEOUT_SECS",
    "DEV_SKU",
    "IN_FLIGHT_STATES",
    "KustoClusterProvisioner",
    "KustoDatabaseProvisioner",
    "KustoDeployError",
    "KustoTableProvisioner",
    "build_management_client",
    "cluster_policy",
    "lift_kusto_model",
    "mapping_view",
]
