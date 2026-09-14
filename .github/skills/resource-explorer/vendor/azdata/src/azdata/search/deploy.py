"""Azure AI Search deploy plane — the index, and the service under it.

WHY THIS EXISTS
---------------
Two planes, two SDKs, two entirely different ways of lying about success,
and an agent that stands a search stack up inside one run needs both.

**An index create-or-update is accepted before it is comparable.** The
data plane returns the index it stored, with every default it filled in:
analyzers named, ``retrievable`` set, vector profiles normalised. A
provisioner that compared the spec it sent against the index it reads back
would report drift on every single call and be switched off within a day.
:meth:`SearchIndexProvisioner._verifiable` narrows the comparison to the
two things the caller actually asserted — the index name and the field
name list — which is enough to catch the failure that matters: a field the
caller declared that is not in the live schema, so every document written
against it silently drops that value.

**A service create is a long-running operation with no natural bound.**
``begin_create_or_update`` returns an ``LROPoller`` whose ``result()``
blocks until ARM finishes, which for a fresh search service is minutes and
for a wedged one is forever, on the calling thread. The base resolves the
poller off the loop against a deadline, so a stuck deployment fails the
run instead of hanging it.

**ARM does not echo what you sent.** A requested location of
``"Australia East"`` comes back as ``"australiaeast"``, and the SDK
flattens ``properties`` into top-level model attributes, so a naive
read-back comparison reports drift for a deployment that is exactly
right. :meth:`SearchServiceProvisioner._verifiable` compares only the
keys ARM returns verbatim, which keeps the real signal — an Azure Policy
``Modify`` effect quietly rewriting a tag or a SKU — visible.

**Missing coordinates are an envelope, not a client.** An empty
subscription id builds a management client that fails on first use with an
authentication error, which is the wrong diagnosis. Each provisioner
checks its coordinates and raises a named error the base turns into an
error envelope naming the config field.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Specs are plain dicts, passed through. Field dicts are translated into SDK
models, and already-constructed SDK objects pass through untouched so a
caller with a vector profile this module has never heard of is not blocked
by the translation.

WHAT THIS IS NOT
----------------
Not infrastructure-as-code. There is no plan, no state file and no
dependency graph. It makes one index or one service match one spec and
tells you when it did not. Long-lived production infrastructure still
belongs in Bicep.

DEPENDENCIES
------------
Standard library, plus ``azure-search-documents`` (index plane) and
``azure-mgmt-search`` (service plane), each loaded on first use.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any, Callable, Mapping

from azdata.core.config import AzureDataConfig
from azdata.core.optional import load
from azdata.core.provision import ProvisionPolicy, Provisioner, as_dict
from azdata.search.write import is_not_found

logger = logging.getLogger(__name__)

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

# The two management SDKs this package uses disagree on model style, and
# guessing wrong is silent. ``azure-mgmt-cosmosdb`` 10 is JSON-backed: its
# models are Mappings whose dict view is the raw camelCase REST payload,
# nested under ``properties``. ``azure-mgmt-search`` 9 is msrest: a
# ``SearchService`` is not a Mapping, and ``as_dict()`` returns flattened
# snake_case with no ``properties`` block at all. These are the keys that
# view returns; ``location`` is excluded because ARM normalises it
# ("Australia East" -> "australiaeast") and would read as drift on a
# deployment that is exactly right.
ECHOED_SERVICE_KEYS = frozenset(
    {
        "sku",
        "tags",
        "identity",
        "hosting_mode",
        "partition_count",
        "replica_count",
        "public_network_access",
    }
)


class SearchIndexProvisioner(Provisioner):
    """Create, describe and delete one Azure AI Search index.

    Data plane, not ARM: index management is authenticated with the same
    search data-plane role as document writes, and needs no subscription.
    """

    resource_kind = "search-index"

    def __init__(
        self,
        *,
        endpoint: str,
        name: str,
        credential: Any,
        policy: ProvisionPolicy | None = None,
    ) -> None:
        super().__init__(name=name, policy=policy)
        self._endpoint = endpoint
        self._credential = credential
        self._client_obj: Any | None = None
        self._client_lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        index_name: str,
        policy: ProvisionPolicy | None = None,
    ) -> "SearchIndexProvisioner":
        return cls(
            endpoint=config.search_endpoint,
            name=index_name,
            credential=credential_provider(),
            policy=policy,
        )

    def _client(self) -> Any:
        if not self._endpoint:
            raise ValueError(
                "search index provisioner is not configured "
                "(search_endpoint is empty)"
            )
        client = self._client_obj
        if client is None:
            with self._client_lock:
                client = self._client_obj
                if client is None:
                    indexes = load_indexes()
                    client = indexes.SearchIndexClient(
                        endpoint=self._endpoint, credential=self._credential
                    )
                    self._client_obj = client
        return client

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    async def _do_describe(self) -> Any | None:
        client = self._client()

        def _get() -> Any:
            return client.get_index(self.name)

        try:
            live = await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001 - absence is a value
            if is_not_found(exc):
                return None
            raise
        return _index_view(live)

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        client = self._client()
        index = _build_index(spec)
        return await asyncio.to_thread(client.create_or_update_index, index)

    async def _do_teardown(self) -> Any:
        client = self._client()
        return await asyncio.to_thread(client.delete_index, self.name)

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        # Field objects come back with analyzers named and defaults filled in
        # that the caller never set, so only the declared name list is
        # comparable; a missing field is the failure worth catching.
        return {"name": spec.get("name", self.name), "field_names": _field_names(spec.get("fields"))}

    def close(self) -> None:
        """Close the index client. Never the credential (G8)."""
        client, self._client_obj = self._client_obj, None
        closer = getattr(client, "close", None) if client is not None else None
        if closer is None:
            return
        try:
            closer()
        except Exception as exc:  # noqa: BLE001 - a close that raises helps nobody
            logger.warning("search.index_client_close_failed name=%s: %s", self.name, exc)


class SearchServiceProvisioner(Provisioner):
    """Create, describe and delete the search service itself, through ARM."""

    resource_kind = "search-service"

    def __init__(
        self,
        *,
        subscription_id: str,
        resource_group: str,
        name: str,
        credential: Any,
        location: str = "",
        policy: ProvisionPolicy | None = None,
    ) -> None:
        super().__init__(name=name, policy=policy)
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._location = location
        self._credential = credential
        self._client_obj: Any | None = None
        self._client_lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        policy: ProvisionPolicy | None = None,
    ) -> "SearchServiceProvisioner":
        return cls(
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            name=config.search_service_name,
            location=config.location,
            credential=credential_provider(),
            policy=policy,
        )

    @property
    def location(self) -> str:
        return self._location

    def _client(self) -> Any:
        missing = [
            field
            for field, value in (
                ("subscription_id", self._subscription_id),
                ("resource_group", self._resource_group),
                ("search_service_name", self.name),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "search service provisioner is not configured "
                f"({', '.join(missing)} empty)"
            )
        client = self._client_obj
        if client is None:
            with self._client_lock:
                client = self._client_obj
                if client is None:
                    mgmt = load("azure.mgmt.search", dist="azure-mgmt-search")
                    client = mgmt.SearchManagementClient(
                        self._credential, self._subscription_id
                    )
                    self._client_obj = client
        return client

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    async def _do_describe(self) -> Any | None:
        client = self._client()

        def _get() -> Any:
            return client.services.get(self._resource_group, self.name)

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001 - absence is a value
            if is_not_found(exc):
                return None
            raise

    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        client = self._client()
        # Returned unresolved on purpose: the base bounds the LRO with a
        # deadline, and result() here would block this thread indefinitely.
        return await asyncio.to_thread(
            client.services.begin_create_or_update,
            self._resource_group,
            self.name,
            dict(spec),
        )

    async def _do_teardown(self) -> Any:
        client = self._client()
        # ``services.delete`` returns None, not a poller — a service delete is
        # not an LRO on this API version. ``await_poller`` passes a
        # pollerless value straight through, so no branch is needed here.
        return await asyncio.to_thread(
            client.services.delete, self._resource_group, self.name
        )

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        """The keys that survive the round trip, in the spelling ARM answers in.

        ``SearchService.as_dict()`` is flattened snake_case, so a spec key
        written in the wire's camelCase would be absent from the read-back
        and counted as drift on a correct deployment. Normalising the spec
        key first is what keeps a genuinely reverted
        ``public_network_access`` visible instead of buried among phantoms.
        """
        return {
            key: value
            for key, value in (
                (_snake_case(str(k)), v) for k, v in spec.items()
            )
            if key in ECHOED_SERVICE_KEYS
        }

    def close(self) -> None:
        """Close the management client. Never the credential (G8)."""
        client, self._client_obj = self._client_obj, None
        closer = getattr(client, "close", None) if client is not None else None
        if closer is None:
            return
        try:
            closer()
        except Exception as exc:  # noqa: BLE001 - a close that raises helps nobody
            logger.warning("search.mgmt_client_close_failed name=%s: %s", self.name, exc)


# ----------------------------------------------------------------------
# Spec translation.
# ----------------------------------------------------------------------


def load_indexes() -> Any:
    """The index-management module, loaded on first use."""
    return load("azure.search.documents.indexes", dist="azure-search-documents")


def load_index_models() -> Any:
    """The index model module, loaded on first use."""
    return load(
        "azure.search.documents.indexes.models", dist="azure-search-documents"
    )


def _build_vector_search(spec: Mapping[str, Any], models: Any) -> Any:
    """Turn a plain ``vector_search`` dict into SDK models.

    Handing the dict straight to ``SearchIndex`` looks like it works and
    is not: the nested keys reach the wire in snake_case, and the service
    rejects ``algorithm_configuration_name`` as a property that does not
    exist on the type. Only the models serialise to camelCase.
    """
    profiles = [
        p
        if not isinstance(p, Mapping)
        else models.VectorSearchProfile(**p)
        for p in spec.get("profiles", [])
    ]
    algorithms = []
    for algorithm in spec.get("algorithms", []):
        if not isinstance(algorithm, Mapping):
            algorithms.append(algorithm)
            continue
        fields = dict(algorithm)
        kind = str(fields.pop("kind", "hnsw")).lower()
        builder = (
            models.ExhaustiveKnnAlgorithmConfiguration
            if kind == "exhaustiveknn"
            else models.HnswAlgorithmConfiguration
        )
        algorithms.append(builder(**fields))
    return models.VectorSearch(profiles=profiles, algorithms=algorithms)


def _build_index(spec: Mapping[str, Any] | Any) -> Any:
    """Turn a plain spec dict into a ``SearchIndex``.

    A caller who already built SDK objects — a vector profile this module
    has never heard of, a custom analyzer chain — hands them through
    unchanged rather than being blocked by the dict translation.
    """
    if not isinstance(spec, Mapping):
        return spec
    models = load_index_models()
    fields = [
        field if not isinstance(field, Mapping) else models.SearchField(**field)
        for field in spec.get("fields", [])
    ]
    extras = {k: v for k, v in spec.items() if k not in ("name", "fields")}
    vector_search = extras.get("vector_search")
    if isinstance(vector_search, Mapping):
        extras["vector_search"] = _build_vector_search(vector_search, models)
    return models.SearchIndex(name=spec["name"], fields=fields, **extras)


def _snake_case(name: str) -> str:
    """``publicNetworkAccess`` -> ``public_network_access``; snake stays snake.

    Local rather than shared with ``_cosmos_infra``: that module normalises
    the opposite model style, and a helper shared between two SDKs that
    disagree is how the wrong shape gets applied to the wrong service.
    """
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _field_names(fields: Any) -> list[str]:
    names: list[str] = []
    for field in fields or []:
        if isinstance(field, Mapping):
            name = field.get("name")
        else:
            name = getattr(field, "name", None)
        if name is not None:
            names.append(str(name))
    return names


def _index_view(index: Any) -> dict:
    """A comparable dict view of a live index, with the field names lifted out."""
    view = as_dict(index)
    view["field_names"] = _field_names(view.get("fields"))
    return view


__all__ = [
    "ECHOED_SERVICE_KEYS",
    "SearchIndexProvisioner",
    "SearchServiceProvisioner",
    "load_index_models",
    "load_indexes",
]
