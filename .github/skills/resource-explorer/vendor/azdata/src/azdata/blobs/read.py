"""Blob content — the bytes, capped, with the size that was really there.

WHY A CAP AND NOT A STREAM
--------------------------
The consumer is a browser pane. Streaming a 4 GiB VHD into one is not a
feature, and a reader that *can* do it has no bound at all. This reads at
most ``bounds.max_bytes`` using a ranged download, so a large blob costs one
capped range request rather than a full transfer that is then discarded.

``size_bytes`` always carries the blob's true length, so a caller can say
"12 KiB of 4 GiB" rather than implying the file is small.

DEPENDENCIES
------------
``azure-storage-blob`` (``storage`` extra), loaded on first call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from azdata.core.content import (
    ContentBounds,
    ContentPayload,
    ContentResult,
    bounded_content,
    content_failure,
)
from azdata.blobs.discover import blob_endpoint, load_blob_sdk, raise_if_network_denial

DEFAULT_MEDIA_TYPE = "application/octet-stream"


class BlobReader:
    """One blob's bytes, bounded, with its declared media type."""

    service = "blob"

    def __init__(self, *, credential_provider: Callable[[], Any]) -> None:
        self._credential_provider = credential_provider
        self._clients: dict[str, Any] = {}

    def _client(self, endpoint: str) -> Any:
        client = self._clients.get(endpoint)
        if client is None:
            sdk = load_blob_sdk()
            client = sdk.BlobServiceClient(
                account_url=endpoint, credential=self._credential_provider()
            )
            self._clients[endpoint] = client
        return client

    async def read(
        self,
        *,
        account_name: str = "",
        endpoint: str = "",
        container: str,
        blob: str,
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        """Download at most ``bounds.max_bytes`` of one blob. Never raises."""
        resolved = endpoint or blob_endpoint(account_name)
        if not resolved or not container or not blob:
            return content_failure(
                service=self.service,
                kind="blob",
                status="unconfigured",
                detail="blob read not configured: account, container and blob",
            )

        def fetch() -> tuple[ContentPayload, bool]:
            client = self._client(resolved).get_blob_client(container, blob)
            try:
                properties = client.get_blob_properties()
            except Exception as exc:  # noqa: BLE001 - a 403 has two meanings
                raise_if_network_denial(exc, resolved)
                raise
            size = int(getattr(properties, "size", 0) or 0)
            settings = getattr(properties, "content_settings", None)
            media_type = (
                str(getattr(settings, "content_type", "") or "") or DEFAULT_MEDIA_TYPE
            )
            length = min(size, bounds.max_bytes) if size else bounds.max_bytes
            data = b""
            if length:
                data = client.download_blob(offset=0, length=length).readall()
            return (
                ContentPayload(
                    form="bytes",
                    media_type=media_type,
                    data=bytes(data),
                    size_bytes=size or len(data),
                ),
                bool(size and size > len(data)),
            )

        return await bounded_content(
            service=self.service, kind="blob", bounds=bounds, fetch=fetch
        )


__all__ = ["DEFAULT_MEDIA_TYPE", "BlobReader"]
