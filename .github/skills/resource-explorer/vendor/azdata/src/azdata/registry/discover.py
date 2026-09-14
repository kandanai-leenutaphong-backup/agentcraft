"""Container registry — repositories and tags, with an AAD identity.

WHY THIS IS NOT ONE ``GET``
---------------------------
The registry data plane does not accept an AAD token directly. It accepts a
registry-scoped token obtained by exchanging one, in two POSTs the OAuth2
token endpoints define:

1. ``POST /oauth2/exchange`` swaps an ARM access token for a registry refresh
   token, which needs the tenant the registry lives in;
2. ``POST /oauth2/token`` swaps that refresh token for an access token scoped
   to exactly one action — ``registry:catalog:*`` to list repositories, or
   ``repository:{name}:metadata_read`` to list one repository's tags.

Both POSTs are token exchanges, not writes. Nothing in this module can
create, tag, delete or push: the only registry paths it requests are
``/acr/v1/_catalog`` and ``/acr/v1/{repository}/_tags``, both ``GET``.

The narrow second scope matters. A single ``repository:*:*`` token would be
one bug away from a delete; a token that can only read one repository's
metadata cannot become one.

DEPENDENCIES
------------
``httpx`` (``graph`` extra), plus :class:`~azdata.estate.armapi.ArmApi` for
the ARM token and the tenant id.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import quote

from azdata.core.config import AzureDataConfig
from azdata.core.discover import (
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    bounded_discovery,
    discovery_failure,
    normalize_attributes,
)
from azdata.core.optional import load
from azdata.estate.armapi import ArmApi

#: What the exchanged token is allowed to do. Read, and only read.
CATALOG_SCOPE = "registry:catalog:*"
REPOSITORY_SCOPE = "repository:{name}:metadata_read"


class RegistryClient:
    """Registry-scoped reads, behind the OAuth2 exchange the service requires."""

    def __init__(self, *, arm: ArmApi, timeout_secs: float = 30.0) -> None:
        self._arm = arm
        self._timeout = timeout_secs
        self._client: Any = None
        self._refresh: dict[str, str] = {}

    def _http(self) -> Any:
        if self._client is None:
            httpx = load("httpx", dist="httpx>=0.27")
            self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)
        return self._client

    def _refresh_token(self, login_server: str, tenant_id: str) -> str:
        cached = self._refresh.get(login_server)
        if cached:
            return cached
        response = self._http().post(
            f"https://{login_server}/oauth2/exchange",
            data={
                "grant_type": "access_token",
                "service": login_server,
                "tenant": tenant_id,
                "access_token": self._arm.token(),
            },
        )
        response.raise_for_status()
        token = str(response.json().get("refresh_token") or "")
        self._refresh[login_server] = token
        return token

    def _access_token(self, login_server: str, tenant_id: str, scope: str) -> str:
        response = self._http().post(
            f"https://{login_server}/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "service": login_server,
                "scope": scope,
                "refresh_token": self._refresh_token(login_server, tenant_id),
            },
        )
        response.raise_for_status()
        return str(response.json().get("access_token") or "")

    def _get(self, login_server: str, tenant_id: str, path: str, scope: str) -> Any:
        token = self._access_token(login_server, tenant_id, scope)
        response = self._http().get(
            f"https://{login_server}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def repositories(self, login_server: str, tenant_id: str) -> list[str]:
        document = self._get(login_server, tenant_id, "/acr/v1/_catalog", CATALOG_SCOPE)
        return [str(name) for name in (document.get("repositories") or ())]

    def tags(
        self, login_server: str, tenant_id: str, repository: str
    ) -> list[dict[str, Any]]:
        document = self._get(
            login_server,
            tenant_id,
            f"/acr/v1/{quote(repository)}/_tags",
            REPOSITORY_SCOPE.format(name=repository),
        )
        return [tag for tag in (document.get("tags") or ()) if isinstance(tag, dict)]


class RegistryDiscoverer:
    """Repositories of one registry, and the tags of one repository."""

    service = "acr"
    levels = ("registry", "repository")

    def __init__(
        self,
        *,
        subscription_id: str = "",
        credential_provider: Callable[[], Any],
        arm: ArmApi | None = None,
        client: RegistryClient | None = None,
    ) -> None:
        self._subscription_id = subscription_id
        self._arm = arm or ArmApi(credential_provider=credential_provider)
        self._client = client or RegistryClient(arm=self._arm)
        self._tenants: dict[str, str] = {}

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        **kwargs: Any,
    ) -> "RegistryDiscoverer":
        return cls(
            subscription_id=config.subscription_id,
            credential_provider=credential_provider,
            **kwargs,
        )

    def child_level(self, level: str) -> str | None:
        return "repository" if level == "registry" else None

    def _tenant(self, subscription_id: str) -> str:
        cached = self._tenants.get(subscription_id)
        if cached is None:
            cached = self._arm.tenant_id(subscription_id)
            self._tenants[subscription_id] = cached
        return cached

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate repositories or tags. Never raises."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service acr",
            )
        subscription_id = scope.subscription_id or self._subscription_id
        login_server = scope.endpoint or (scope.path[0] if scope.path else "")
        repository = scope.path[1] if len(scope.path) > 1 else ""
        if not subscription_id or not login_server:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail="registry discovery not configured: subscription and login server",
            )
        if level == "repository" and not repository:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail="registry discovery not configured: repository",
            )

        def collect() -> Iterator[DiscoveryNode]:
            tenant = self._tenant(subscription_id)
            if level == "registry":
                for index, name in enumerate(
                    self._client.repositories(login_server, tenant)
                ):
                    if index > bounds.max_items:
                        return
                    yield DiscoveryNode(
                        kind="registry_repository",
                        name=name,
                        path=(login_server, name),
                        has_children=True,
                        attributes=normalize_attributes({"repository": name}),
                    )
                return
            for index, tag in enumerate(
                self._client.tags(login_server, tenant, repository)
            ):
                if index > bounds.max_items:
                    return
                yield _tag_node(login_server, repository, tag)

        return await bounded_discovery(
            service=self.service,
            level=level,
            scope=scope,
            bounds=bounds,
            collect=collect,
        )


def _tag_node(login_server: str, repository: str, tag: dict[str, Any]) -> DiscoveryNode:
    name = str(tag.get("name") or "")
    changeable = tag.get("changeableAttributes")
    changeable = changeable if isinstance(changeable, dict) else {}
    return DiscoveryNode(
        kind="registry_tag",
        name=name,
        path=(login_server, repository, name),
        has_children=False,
        attributes=normalize_attributes(
            {
                "digest": tag.get("digest"),
                "createdTime": tag.get("createdTime"),
                "lastUpdateTime": tag.get("lastUpdateTime"),
                "signed": tag.get("signed"),
                "writeEnabled": changeable.get("writeEnabled"),
                "deleteEnabled": changeable.get("deleteEnabled"),
            }
        ),
    )


__all__ = [
    "CATALOG_SCOPE",
    "REPOSITORY_SCOPE",
    "RegistryClient",
    "RegistryDiscoverer",
]
