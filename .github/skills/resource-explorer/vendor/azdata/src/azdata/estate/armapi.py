"""Generic ARM access — one HTTP client that can read any resource type.

WHY THIS EXISTS
---------------
Every ``azure-mgmt-*`` package is a per-provider client. A browser over a
whole subscription meets 26 resource types today and an unknown number
tomorrow, and installing a management SDK per provider is neither possible
nor useful: what it needs is the operation ARM has had all along —
``GET {resourceId}?api-version={v}`` — plus a way to learn ``v``.

That is this module. One credential, one HTTP client, three operations:

* :meth:`ArmApi.read` — the full property JSON of any resource, whatever it is;
* :meth:`ArmApi.list_children` — any ARM child collection of any resource;
* :meth:`ArmApi.resource_graph` — one KQL query across the whole subscription.

Azure Resource Graph is what makes a subscription-wide tree affordable. The
alternative — one ARM listing per resource group, then one read per resource
— is 200+ round trips for a view the operator wanted in one. Resource Graph
answers the same question in a single POST.

API VERSIONS ARE RESOLVED, NOT PINNED
-------------------------------------
A pinned table of api-versions is wrong the week a provider ships a new one
and silently wrong for every type not in the table. The provider metadata
endpoint lists the versions each type supports; the newest stable one is
chosen, falling back to the newest preview when a type has only previews.
A nested type the provider does not list at all — ``Microsoft.App`` omits
``containerApps/revisions`` and ``containerApps/revisions/replicas``, both
of which are readable — falls back to its nearest declared ancestor.
Resolution is cached per provider namespace for the process, because it
never changes mid-run.

WHAT THIS MODULE NEVER DOES
---------------------------
It issues ``GET`` and the Resource Graph ``POST`` and nothing else. There is
no ``put``, ``patch``, ``post`` to a resource path, or ``delete`` anywhere in
the file, which is a property a reviewer can check by reading it. A token is
held in memory, never logged, and never placed in a returned value.

DEPENDENCIES
------------
``httpx`` (``graph`` extra), loaded on first call.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote

from azdata.core.discover import DiscoveryAbsent
from azdata.core.optional import load

#: The management plane's audience. One scope for every call in this file.
ARM_SCOPE = "https://management.azure.com/.default"

ARM_ENDPOINT = "https://management.azure.com"

#: Used only to enumerate providers and resource groups — the two calls that
#: must work before any type-specific api-version is known.
PROVIDER_API_VERSION = "2021-04-01"
RESOURCE_GRAPH_API_VERSION = "2022-10-01"
SUBSCRIPTION_API_VERSION = "2020-01-01"

#: Rebuild the token this many seconds before it expires, so a request
#: cannot race an expiry mid-flight.
TOKEN_MARGIN_SECS = 300

#: Resource Graph pages at 1000 rows and refuses more in one request.
MAX_GRAPH_PAGE = 1000


class ArmApi:
    """Read-only ARM and Resource Graph access, for any resource type.

    Args:
        credential_provider: Called on first use, never at construction — a
            health check may build this object.
        endpoint: ARM endpoint. Parameterised for sovereign clouds; the
            audience is derived from it.
        timeout_secs: Per-request socket budget. The caller's own bound is
            what actually limits the operation; this stops a hung socket
            outliving it.
    """

    def __init__(
        self,
        *,
        credential_provider: Callable[[], Any],
        endpoint: str = ARM_ENDPOINT,
        timeout_secs: float = 30.0,
    ) -> None:
        self._credential_provider = credential_provider
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout_secs
        self._client: Any = None
        self._credential: Any = None
        self._tokens: dict[str, tuple[str, float]] = {}
        self._api_versions: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    # -- identity -----------------------------------------------------------

    def token(self, scope: str = ARM_SCOPE) -> str:
        """A bearer token for ``scope``, cached until shortly before expiry.

        The value is never logged and never returned into a result envelope.
        Callers pass it straight to an ``Authorization`` header.
        """
        with self._lock:
            cached = self._tokens.get(scope)
            if cached is not None and cached[1] - TOKEN_MARGIN_SECS > time.time():
                return cached[0]
            if self._credential is None:
                self._credential = self._credential_provider()
            issued = self._credential.get_token(scope)
            self._tokens[scope] = (issued.token, float(issued.expires_on))
            return issued.token

    def _http(self) -> Any:
        if self._client is None:
            httpx = load("httpx", dist="httpx>=0.27")
            self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)
        return self._client

    # -- transport ----------------------------------------------------------

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        scope: str = ARM_SCOPE,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """One authenticated ``GET``. Raises on any non-2xx, never returns junk."""
        request_headers = {"Authorization": f"Bearer {self.token(scope)}"}
        request_headers.update(headers or {})
        response = self._http().get(url, params=params, headers=request_headers)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def _post_graph(self, body: Mapping[str, Any]) -> Any:
        response = self._http().post(
            f"{self._endpoint}/providers/Microsoft.ResourceGraph/resources",
            params={"api-version": RESOURCE_GRAPH_API_VERSION},
            headers={"Authorization": f"Bearer {self.token()}"},
            json=dict(body),
        )
        response.raise_for_status()
        return response.json()

    # -- api-version resolution --------------------------------------------

    def api_version(self, resource_type: str, subscription_id: str) -> str:
        """The newest api-version ``resource_type`` supports.

        ``resource_type`` is the full ``Namespace/type[/childType...]`` form.
        Stable versions win over previews; a type that only ever shipped
        previews still resolves, because refusing it would make the branch
        dark for a reason the operator cannot act on.
        """
        namespace, _, path = resource_type.partition("/")
        versions = self._provider_versions(namespace, subscription_id)
        resolved = versions.get(path.lower())
        if resolved:
            return resolved
        raise DiscoveryAbsent(
            f"provider {namespace} declares no api-version for '{path}'"
        )

    def resolve_api_version(self, resource_type: str, subscription_id: str) -> str:
        """An api-version for ``resource_type``, or for its nearest declared ancestor.

        A provider is not obliged to list every nested type it serves.
        ``Microsoft.App`` declares ``containerApps`` but neither
        ``containerApps/revisions`` nor ``containerApps/revisions/replicas``,
        and both are readable. Refusing them because the metadata is
        incomplete would make a branch dark for a reason no operator can act
        on, so the nearest declared ancestor's version is used — which is the
        version those collections are in fact served at.
        """
        namespace, _, path = resource_type.partition("/")
        segments = [segment for segment in path.split("/") if segment]
        while segments:
            try:
                return self.api_version(f"{namespace}/" + "/".join(segments), subscription_id)
            except DiscoveryAbsent:
                segments.pop()
        raise DiscoveryAbsent(
            f"provider {namespace} declares no api-version for '{path}' or any ancestor"
        )

    def _provider_versions(self, namespace: str, subscription_id: str) -> dict[str, str]:
        key = namespace.lower()
        cached = self._api_versions.get(key)
        if cached is not None:
            return cached
        document = self.get_json(
            f"{self._endpoint}/subscriptions/{quote(subscription_id)}"
            f"/providers/{quote(namespace)}",
            params={"api-version": PROVIDER_API_VERSION},
        )
        table: dict[str, str] = {}
        for entry in document.get("resourceTypes") or ():
            name = str(entry.get("resourceType") or "").lower()
            table[name] = _newest(entry.get("apiVersions") or ())
        self._api_versions[key] = table
        return table

    # -- reads --------------------------------------------------------------

    def read(self, resource_id: str, *, api_version: str = "") -> dict[str, Any]:
        """The full ARM representation of one resource, whatever its type."""
        subscription_id = subscription_of(resource_id)
        version = api_version or self.resolve_api_version(
            type_of(resource_id), subscription_id
        )
        return self.get_json(
            f"{self._endpoint}{resource_id}", params={"api-version": version}
        )

    def list_children(
        self,
        resource_id: str,
        collection: str,
        *,
        api_version: str = "",
    ) -> list[dict[str, Any]]:
        """Every item of one ARM child collection, following ``nextLink``.

        ``collection`` is the path below the resource, so both ``revisions``
        and ``blobServices/default/containers`` are the same call.
        """
        subscription_id = subscription_of(resource_id)
        parent_type = type_of(resource_id)
        child_type = child_type_of(parent_type, collection)
        version = api_version or self.resolve_api_version(child_type, subscription_id)
        url = f"{self._endpoint}{resource_id}/{collection.strip('/')}"
        params: dict[str, Any] | None = {"api-version": version}
        items: list[dict[str, Any]] = []
        while url:
            document = self.get_json(url, params=params)
            value = document.get("value")
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
            elif isinstance(document, dict) and document.get("id"):
                items.append(document)
            url = str(document.get("nextLink") or "")
            # nextLink already carries the query string; re-adding it 400s.
            params = None
        return items

    def list_resource_groups(self, subscription_id: str) -> list[dict[str, Any]]:
        """Every resource group in one subscription. The Resource Graph fallback."""
        url = (
            f"{self._endpoint}/subscriptions/{quote(subscription_id)}/resourcegroups"
        )
        params: dict[str, Any] | None = {"api-version": PROVIDER_API_VERSION}
        groups: list[dict[str, Any]] = []
        while url:
            document = self.get_json(url, params=params)
            groups.extend(
                item for item in (document.get("value") or ()) if isinstance(item, dict)
            )
            url = str(document.get("nextLink") or "")
            params = None
        return groups

    def list_resources(
        self, subscription_id: str, resource_group: str
    ) -> list[dict[str, Any]]:
        """Every resource in one group. The Resource Graph fallback."""
        url = (
            f"{self._endpoint}/subscriptions/{quote(subscription_id)}"
            f"/resourceGroups/{quote(resource_group)}/resources"
        )
        params: dict[str, Any] | None = {"api-version": PROVIDER_API_VERSION}
        found: list[dict[str, Any]] = []
        while url:
            document = self.get_json(url, params=params)
            found.extend(
                item for item in (document.get("value") or ()) if isinstance(item, dict)
            )
            url = str(document.get("nextLink") or "")
            params = None
        return found

    def tenant_id(self, subscription_id: str) -> str:
        """The tenant a subscription belongs to. Needed for the ACR exchange."""
        document = self.get_json(
            f"{self._endpoint}/subscriptions/{quote(subscription_id)}",
            params={"api-version": SUBSCRIPTION_API_VERSION},
        )
        return str(document.get("tenantId") or "")

    def resource_graph(
        self,
        query: str,
        *,
        subscriptions: tuple[str, ...],
        top: int = MAX_GRAPH_PAGE,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        """One KQL query across the estate.

        The caller composes the query. Every value interpolated into one must
        go through :func:`kql_literal` first; this method cannot tell a
        literal from an operator and does not try.
        """
        body = {
            "subscriptions": list(subscriptions),
            "query": query,
            "options": {
                "resultFormat": "objectArray",
                "$top": max(1, min(int(top), MAX_GRAPH_PAGE)),
                "$skip": max(0, int(skip)),
            },
        }
        document = self._post_graph(body)
        data = document.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []


def _newest(versions: Any) -> str:
    """Newest stable api-version, else newest preview, else empty."""
    ordered = sorted((str(v) for v in versions or ()), reverse=True)
    for version in ordered:
        if "preview" not in version:
            return version
    return ordered[0] if ordered else ""


def kql_literal(value: str) -> str:
    """A KQL string literal that cannot end early.

    Verbatim single-quoted form: ``@'...'``, in which a backslash is an
    ordinary character and the only escape is a doubled quote. Control
    characters are stripped rather than escaped — none of them can appear in
    a resource name, and leaving them in a query is how a search box becomes
    a query builder.
    """
    cleaned = "".join(character for character in str(value) if character >= " ")
    return "@'" + cleaned.replace("'", "''") + "'"


def subscription_of(resource_id: str) -> str:
    """The subscription segment of an ARM id, or "" when there is none."""
    parts = [part for part in str(resource_id).split("/") if part]
    for index, part in enumerate(parts):
        if part.lower() == "subscriptions" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def resource_group_of(resource_id: str) -> str:
    """The resource-group segment of an ARM id, or "" when there is none."""
    parts = [part for part in str(resource_id).split("/") if part]
    for index, part in enumerate(parts):
        if part.lower() == "resourcegroups" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def name_of(resource_id: str) -> str:
    """The last segment of an ARM id."""
    parts = [part for part in str(resource_id).split("/") if part]
    return parts[-1] if parts else ""


def type_of(resource_id: str) -> str:
    """The ``Namespace/type[/childType...]`` an ARM id addresses.

    Derived from the id rather than taken on trust: everything after
    ``providers`` alternates type and name, so the type is every other
    segment. This is what makes one code path cover 26 resource types and
    the ones added next month.
    """
    parts = [part for part in str(resource_id).split("/") if part]
    lowered = [part.lower() for part in parts]
    if "providers" not in lowered:
        return ""
    start = lowered.index("providers") + 1
    tail = parts[start:]
    if not tail:
        return ""
    segments = [tail[0]]
    segments.extend(tail[index] for index in range(1, len(tail), 2))
    return "/".join(segments)


def child_type_of(parent_type: str, collection: str) -> str:
    """The ARM type of ``parent/{collection}``.

    A collection path may itself be nested — ``blobServices/default/containers``
    names a child of a child — so the name segments in it are dropped the same
    way :func:`type_of` drops them.
    """
    parts = [part for part in str(collection).strip("/").split("/") if part]
    if not parts:
        return parent_type
    segments = [parts[0]]
    segments.extend(parts[index] for index in range(2, len(parts), 2))
    return f"{parent_type}/" + "/".join(segments)


__all__ = [
    "ARM_ENDPOINT",
    "ARM_SCOPE",
    "MAX_GRAPH_PAGE",
    "PROVIDER_API_VERSION",
    "RESOURCE_GRAPH_API_VERSION",
    "ArmApi",
    "child_type_of",
    "kql_literal",
    "name_of",
    "resource_group_of",
    "subscription_of",
    "type_of",
]
