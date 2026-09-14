"""Reading a resource's own contents, and searching the whole estate.

WHY THIS EXISTS
---------------
Sixteen of the twenty-six resource types in a real subscription have no
richer data plane than ARM itself. For those, ARM's own JSON *is* the
content, and a browser that shows only a name and a location has thrown away
everything the operator opened the node for.

Estate search is here for the same reason: Resource Graph already indexes
every resource's name, type, group, location, tags and property bag, so one
POST answers "where in this subscription is the thing I am thinking of"
without walking a single branch.

REDACTION
---------
ARM's ``GET`` does not return storage keys, Key Vault secret values or
container-app secret values — those need separate ``list*`` POSTs this
package cannot issue. Even so, every returned document passes through
:func:`redact_credentials`, because "ARM does not return secrets" is a claim
about today's providers and the cost of being wrong is a credential in a
browser pane.

DEPENDENCIES
------------
``httpx`` (``graph`` extra), through :class:`~azdata.estate.armapi.ArmApi`.
"""

from __future__ import annotations

import json
from typing import Any

from azdata.core.content import (
    ContentBounds,
    ContentPayload,
    ContentResult,
    bounded_content,
    content_failure,
    normalize_rows,
)
from azdata.estate.armapi import ArmApi, kql_literal, type_of

#: Redacted wherever they appear as an object key, at any depth. Matched as a
#: lowercase substring, so ``primaryConnectionString`` and ``clientSecret``
#: are both caught without enumerating provider spellings.
CREDENTIAL_KEY_FRAGMENTS: tuple[str, ...] = (
    "accountkey",
    "accesskey",
    "adminpassword",
    "apikey",
    "authtoken",
    "certificatepassword",
    "clientsecret",
    "connectionstring",
    "credential",
    "encryptionkey",
    "keydata",
    "password",
    "primarykey",
    "privatekey",
    "sastoken",
    "secondarykey",
    "secretvalue",
    "sharedaccesskey",
    "sharedkey",
)

REDACTED = "(redacted)"

#: How deep a property bag is walked before redaction gives up. ARM documents
#: are shallow; a cycle-free bound is still cheaper than trusting that.
MAX_REDACT_DEPTH = 24

#: Resource Graph's parser refuses ``project x = f(x)`` when ``x`` is already a
#: column: ``project kind = tostring(kind)`` is a ParserFailure on the ``=``,
#: while ``project skuName = tostring(sku.name)`` is fine because the output
#: name is new. Columns that already exist are therefore projected by name and
#: never re-derived.
SEARCH_RESOURCES_QUERY = """
Resources
| where name contains {q}
    or type contains {q}
    or resourceGroup contains {q}
    or location contains {q}
    or tostring(tags) contains {q}
    or tostring(properties) contains {q}
| extend matchedIn = case(
    name contains {q}, 'name',
    type contains {q}, 'type',
    resourceGroup contains {q}, 'resourceGroup',
    location contains {q}, 'location',
    tostring(tags) contains {q}, 'tags',
    'properties')
| project id, name, type, resourceGroup, location, kind,
    skuName = tostring(sku.name), matchedIn
| order by name asc
"""

#: ``kind`` and ``skuName`` are absent here rather than empty, for the same
#: parser reason: ``ResourceContainers`` already declares ``kind``. A hit is
#: read with ``.get``, so a missing column is not a missing hit.
SEARCH_GROUPS_QUERY = """
ResourceContainers
| where type =~ 'microsoft.resources/subscriptions/resourcegroups'
    and (name contains {q} or location contains {q})
| extend matchedIn = case(name contains {q}, 'name', 'location')
| project id, name, type, resourceGroup = name, location, matchedIn
| order by name asc
"""


class EstateReader:
    """One resource's ARM document, and full-text search over the estate."""

    service = "estate"

    def __init__(self, *, arm: ArmApi, subscription_id: str = "") -> None:
        self._arm = arm
        self._subscription_id = subscription_id

    async def properties(
        self,
        resource_id: str,
        *,
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """The full ARM representation of one resource, as JSON bytes."""
        if not resource_id:
            return content_failure(
                service=self.service,
                kind="properties",
                status="unconfigured",
                detail="properties read not configured: resource id",
            )

        def fetch() -> tuple[ContentPayload, bool]:
            document = redact_credentials(self._arm.read(resource_id))
            raw = json.dumps(document, indent=2, sort_keys=True, default=str).encode(
                "utf-8"
            )
            truncated = len(raw) > bounds.max_bytes
            return (
                ContentPayload(
                    form="bytes",
                    media_type="application/json",
                    data=raw[: bounds.max_bytes],
                    size_bytes=len(raw),
                ),
                truncated,
            )

        return await bounded_content(
            service=self.service, kind="properties", bounds=bounds, fetch=fetch
        )

    async def search(
        self,
        text: str,
        *,
        subscriptions: tuple[str, ...] = (),
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """Every resource whose name, type, group, tags or properties match.

        The term is interpolated through :func:`~azdata.estate.armapi.kql_literal`
        and nothing else from the caller reaches the query, so a search box
        cannot become a query builder.
        """
        term = str(text or "").strip()
        if not term:
            return content_failure(
                service=self.service,
                kind="search",
                status="unconfigured",
                detail="search not configured: query text",
            )
        scope = subscriptions or ((self._subscription_id,) if self._subscription_id else ())
        if not scope:
            return content_failure(
                service=self.service,
                kind="search",
                status="unconfigured",
                detail="search not configured: subscription_id",
            )
        literal = kql_literal(term)

        def fetch() -> tuple[ContentPayload, bool]:
            found: list[dict[str, Any]] = []
            found.extend(
                self._arm.resource_graph(
                    SEARCH_RESOURCES_QUERY.replace("{q}", literal),
                    subscriptions=scope,
                    top=bounds.max_rows + 1,
                )
            )
            found.extend(
                self._arm.resource_graph(
                    SEARCH_GROUPS_QUERY.replace("{q}", literal),
                    subscriptions=scope,
                    top=bounds.max_rows + 1,
                )
            )
            rows, columns, truncated = normalize_rows(found, max_rows=bounds.max_rows)
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=rows,
                    columns=columns,
                    size_bytes=len(rows),
                ),
                truncated,
            )

        return await bounded_content(
            service=self.service, kind="search", bounds=bounds, fetch=fetch
        )


def redact_credentials(document: Any, *, depth: int = 0) -> Any:
    """Replace credential-shaped values anywhere in a JSON document.

    Keys are matched, not values: a heuristic over values would redact a
    resource id that happens to look like entropy, and miss a short password.

    A boolean or a number under a matching key is left alone, because it
    cannot be a credential and it is often the posture an operator opened the
    document to read — ``allowSharedKeyAccess: false`` says shared-key auth is
    off, and redacting it hides the answer while protecting nothing.
    """
    if depth > MAX_REDACT_DEPTH:
        return REDACTED
    if isinstance(document, dict):
        clean: dict[str, Any] = {}
        for key, value in document.items():
            name = str(key)
            lowered = name.lower()
            if any(fragment in lowered for fragment in CREDENTIAL_KEY_FRAGMENTS) and not (
                value is None or isinstance(value, (bool, int, float))
            ):
                clean[name] = REDACTED
            else:
                clean[name] = redact_credentials(value, depth=depth + 1)
        return clean
    if isinstance(document, list):
        return [redact_credentials(item, depth=depth + 1) for item in document]
    return document


def resource_type(resource_id: str) -> str:
    """The ARM type an id addresses. Re-exported so callers need one import."""
    return type_of(resource_id)


__all__ = [
    "CREDENTIAL_KEY_FRAGMENTS",
    "MAX_REDACT_DEPTH",
    "REDACTED",
    "SEARCH_GROUPS_QUERY",
    "SEARCH_RESOURCES_QUERY",
    "EstateReader",
    "redact_credentials",
    "resource_type",
]
