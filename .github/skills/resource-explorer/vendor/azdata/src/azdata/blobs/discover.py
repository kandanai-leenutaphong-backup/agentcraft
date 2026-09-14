"""Blob storage discovery — containers, and one prefix level of a container.

WHY THE DATA PLANE AND NOT ARM
------------------------------
``GET {accountId}/blobServices/default/containers`` lists containers from the
management plane and keeps working when the data plane is unreachable. It is
the wrong call anyway. An account whose ``publicNetworkAccess`` is
``Disabled`` has *no readable blobs*, and a container list that succeeds
while every expansion beneath it fails tells the operator the opposite of
what is true. Listing containers from the data plane makes the account branch
answer ``unreachable`` at the point the reachability actually breaks.

WHY ``walk_blobs`` AND NOT ``list_blobs``
-----------------------------------------
Blob storage is flat: ``nested/deep/file.txt`` is one blob whose name
contains slashes, not a file in two directories. ``walk_blobs`` with a ``/``
delimiter asks the *service* to collapse everything below the current prefix
into one ``BlobPrefix`` per folder, so a container with a million blobs costs
one bounded call per level opened rather than one listing of the lot. The
folder hierarchy is therefore real, server-computed, and cheap.

DEPENDENCIES
------------
``azure-storage-blob`` (``storage`` extra), loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from azdata.core.config import AzureDataConfig
from azdata.core.discover import (
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    DiscoveryUnreachable,
    bounded_discovery,
    discovery_failure,
    normalize_attributes,
)
from azdata.core.optional import load

#: Public-cloud blob endpoint. Overridden by ``scope.endpoint`` for sovereign
#: clouds and for accounts reached through a private endpoint alias.
BLOB_SUFFIX = "blob.core.windows.net"

#: Storage refuses a request blocked by a network rule with HTTP 403 and this
#: error code — the same status it uses for a missing role, which carries
#: ``AuthorizationPermissionMismatch`` instead. The distinction matters more
#: than the status code does: one is fixed by a role grant and the other is
#: not, and telling an operator to grant a role that cannot help is the exact
#: failure the degradation vocabulary exists to prevent.
NETWORK_DENIAL_CODE = "AuthorizationFailure"


def raise_if_network_denial(exc: BaseException, endpoint: str) -> None:
    """Re-raise a network-rule refusal as ``unreachable``, or do nothing.

    The composed message deliberately replaces the SDK's, which carries a
    request id, a timestamp and an XML body that say nothing an operator can
    act on.
    """
    code = getattr(exc, "error_code", None)
    if code != NETWORK_DENIAL_CODE and NETWORK_DENIAL_CODE not in str(exc):
        return
    raise DiscoveryUnreachable(
        "the storage data plane refused this caller's network path; "
        "public network access is disabled or an IP rule excludes it"
    ) from exc


def blob_endpoint(account_name: str) -> str:
    return f"https://{account_name}.{BLOB_SUFFIX}" if account_name else ""


def load_blob_sdk() -> Any:
    return load("azure.storage.blob", dist="azure-storage-blob>=12.19")


class BlobDiscoverer:
    """Containers of one storage account, and one prefix level of a container."""

    service = "blob"
    levels = ("account", "container")

    def __init__(
        self,
        *,
        account_name: str = "",
        credential_provider: Callable[[], Any],
    ) -> None:
        self._account_name = account_name
        self._credential_provider = credential_provider
        self._clients: dict[str, Any] = {}

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        **kwargs: Any,
    ) -> "BlobDiscoverer":
        return cls(credential_provider=credential_provider, **kwargs)

    def child_level(self, level: str) -> str | None:
        # A container expands into folders, and a folder expands into the same
        # level again with a longer prefix: depth is the prefix, not a new
        # level.
        return "container" if level in ("account", "container") else None

    def service_client(self, endpoint: str) -> Any:
        client = self._clients.get(endpoint)
        if client is None:
            sdk = load_blob_sdk()
            client = sdk.BlobServiceClient(
                account_url=endpoint, credential=self._credential_provider()
            )
            self._clients[endpoint] = client
        return client

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate containers or one prefix level. Never raises."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service blob",
            )
        endpoint = scope.endpoint or blob_endpoint(
            scope.account_name or self._account_name
        )
        if not endpoint:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail="blob discovery not configured: account name",
            )

        if level == "account":
            collect = self._containers(endpoint, bounds)
        else:
            container = scope.path[0] if scope.path else ""
            prefix = scope.path[1] if len(scope.path) > 1 else ""
            if not container:
                return discovery_failure(
                    service=self.service,
                    level=level,
                    scope=scope,
                    status="unconfigured",
                    detail="blob discovery not configured: container",
                )
            collect = self._entries(endpoint, container, prefix, bounds)

        return await bounded_discovery(
            service=self.service,
            level=level,
            scope=scope,
            bounds=bounds,
            collect=collect,
        )

    def _containers(
        self, endpoint: str, bounds: DiscoveryBounds
    ) -> Callable[[], Iterator[DiscoveryNode]]:
        def collect() -> Iterator[DiscoveryNode]:
            client = self.service_client(endpoint)
            try:
                listing = list(client.list_containers())
            except Exception as exc:  # noqa: BLE001 - a 403 has two meanings
                raise_if_network_denial(exc, endpoint)
                raise
            for index, container in enumerate(listing):
                if index > bounds.max_items:
                    return
                name = str(_field(container, "name") or "")
                yield DiscoveryNode(
                    kind="blob_container",
                    name=name,
                    path=(name, ""),
                    has_children=True,
                    attributes=normalize_attributes(
                        {
                            "publicAccess": _text(_field(container, "public_access")),
                            "lastModified": _text(_field(container, "last_modified")),
                            "hasImmutabilityPolicy": _field(
                                container, "has_immutability_policy"
                            ),
                            "deleted": _field(container, "deleted"),
                        }
                    ),
                )

        return collect

    def _entries(
        self,
        endpoint: str,
        container: str,
        prefix: str,
        bounds: DiscoveryBounds,
    ) -> Callable[[], Iterator[DiscoveryNode]]:
        def collect() -> Iterator[DiscoveryNode]:
            client = self.service_client(endpoint).get_container_client(container)
            try:
                walked = list(
                    client.walk_blobs(name_starts_with=prefix or None, delimiter="/")
                )
            except Exception as exc:  # noqa: BLE001 - a 403 has two meanings
                raise_if_network_denial(exc, endpoint)
                raise
            for index, entry in enumerate(walked):
                if index > bounds.max_items:
                    return
                full = str(_field(entry, "name") or "")
                leaf = full[len(prefix):].strip("/") if prefix else full.strip("/")
                if full.endswith("/"):
                    yield DiscoveryNode(
                        kind="blob_folder",
                        name=leaf or full,
                        path=(container, full),
                        has_children=True,
                        attributes=normalize_attributes({"prefix": full}),
                    )
                    continue
                settings = _field(entry, "content_settings")
                yield DiscoveryNode(
                    kind="blob",
                    name=leaf or full,
                    path=(container, full),
                    has_children=False,
                    attributes=normalize_attributes(
                        {
                            "blob": full,
                            "size": _field(entry, "size"),
                            "contentType": _text(_field(settings, "content_type")),
                            "lastModified": _text(_field(entry, "last_modified")),
                            "blobType": _text(_field(entry, "blob_type")),
                            "accessTier": _text(_field(entry, "access_tier")),
                        }
                    ),
                )

        return collect


def _field(model: Any, name: str) -> Any:
    """Read from an SDK model, a mapping or a fake, without a branch per pin."""
    if model is None:
        return None
    if isinstance(model, dict):
        return model.get(name)
    return getattr(model, name, None)


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "BLOB_SUFFIX",
    "NETWORK_DENIAL_CODE",
    "BlobDiscoverer",
    "blob_endpoint",
    "load_blob_sdk",
    "raise_if_network_denial",
]
