"""Blob write plane — objects inside one container, never the container.

WHY THIS EXISTS
---------------
``blobs/discover.py`` lists and ``blobs/read.py`` reads. Nothing here wrote,
so every consumer that needed to put a byte back reached for the SDK
directly and re-learned the same four failures.

**A blob upload silently overwrites.** ``upload_blob`` without
``overwrite=True`` raises on an existing name; with it, the previous content
is gone and nothing in the response says a version was replaced.
:meth:`BlobObjects.create` and :meth:`BlobObjects.upload` are therefore
different operations rather than one flag, matching the base contract.

**A delete of a missing blob is not a completed delete.** The SDK raises
``ResourceNotFoundError``, and a caller that treats "already gone" as
success cannot tell a typo'd name from a real removal. It is reported as a
per-item failure with the reason.

**Soft delete makes a deleted blob still readable.** An account with a
retention policy answers ``get_blob_properties`` for a deleted blob unless
the caller opts out, so verification would pass on a delete that a listing
still shows. The read seam requests the undeleted state explicitly.

**The SDK is synchronous.** Every call goes through :func:`asyncio.to_thread`
so a megabyte upload does not stall the event loop.

THE LINE THIS MODULE DOES NOT CROSS
-----------------------------------
Objects only. There is no container create, no container delete, no account
operation, and no lifecycle or immutability policy write. That is not an
oversight and not a TODO: ``Storage Blob Data Contributor`` grants container
lifecycle, so the only place the distinction can be drawn is in code, and it
is drawn here by the absence of the verbs. A consumer that needs a container
created uses the management plane deliberately, somewhere else.

DEPENDENCIES
------------
``azure-storage-blob`` (``storage`` extra), loaded on first call.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Sequence

from azdata.blobs.discover import blob_endpoint, load_blob_sdk, raise_if_network_denial
from azdata.blobs.read import DEFAULT_MEDIA_TYPE
from azdata.core.breaker import CircuitBreaker
from azdata.core.crud import CrudConnector, WritePolicy

logger = logging.getLogger(__name__)

#: The field naming one object. ``id`` would be wrong: a blob's identity is
#: its name within its container, and callers already say ``name``.
DEFAULT_KEY_FIELD = "name"

#: One listing's ceiling. A container can hold millions; a listing that can
#: return all of them has no bound at all.
DEFAULT_MAX_LIST = 100


def _status_of(exc: BaseException) -> int | None:
    return getattr(exc, "status_code", None) or getattr(exc, "status", None)


def _is_not_found(exc: BaseException) -> bool:
    return type(exc).__name__ == "ResourceNotFoundError" or _status_of(exc) == 404


def _is_conflict(exc: BaseException) -> bool:
    return type(exc).__name__ == "ResourceExistsError" or _status_of(exc) == 409


def _as_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return str(value).encode("utf-8")


class BlobObjects(CrudConnector):
    """Create, retrieve, upload and delete blobs in one container.

    Args:
        container_client: An object exposing ``get_blob_client``,
            ``list_blobs`` and ``upload_blob``. Injected rather than
            constructed so this class is unit-testable with a double and
            carries no import-time dependency on the Azure SDK. Use
            :meth:`connect` for the normal path.
        key_field: Name of the field carrying the blob name.
        max_list: Ceiling on one :meth:`query` listing.

    Item shape, and the whole of it::

        {"name": "folder/object.json", "content": b"..." | "...",
         "contentType": "application/json"}

    ``content`` accepts ``bytes`` or ``str``; a ``str`` is encoded UTF-8.
    ``contentType`` is optional and defaults to ``application/octet-stream``.
    """

    service = "blob"

    def __init__(
        self,
        *,
        container_client: Any,
        key_field: str = DEFAULT_KEY_FIELD,
        content_field: str = "content",
        content_type_field: str = "contentType",
        max_list: int = DEFAULT_MAX_LIST,
        policy: WritePolicy | None = None,
        breaker: CircuitBreaker | None = None,
        gate_provider: Callable[[], Any] | None = None,
        service_client: Any = None,
    ) -> None:
        super().__init__(
            policy=policy,
            breaker=breaker,
            gate_provider=gate_provider,
            key_field=key_field,
        )
        self._container = container_client
        self._content_field = content_field
        self._content_type_field = content_type_field
        self._max_list = max(1, int(max_list))
        # Only set when connect() built it; close() must not close a client
        # the caller owns and may still be using.
        self._owned_client = service_client

    @classmethod
    def connect(
        cls,
        *,
        account_name: str = "",
        endpoint: str = "",
        container: str,
        credential: Any,
        **kwargs: Any,
    ) -> "BlobObjects":
        """Build the blob client and return a wired write plane.

        The container is *addressed*, never created: ``get_container_client``
        performs no I/O and no ``create_container`` call exists in this module.
        """
        resolved = endpoint or blob_endpoint(account_name)
        if not resolved or not container:
            raise ValueError(
                "blob write plane needs an account or endpoint, and a container"
            )
        sdk = load_blob_sdk()
        client = sdk.BlobServiceClient(account_url=resolved, credential=credential)
        return cls(
            container_client=client.get_container_client(container),
            service_client=client,
            **kwargs,
        )

    @property
    def max_list(self) -> int:
        return self._max_list

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    async def _do_create(self, items: Sequence[dict]) -> list[dict]:
        return await asyncio.to_thread(self._put, items, False)

    async def _do_upload(self, items: Sequence[dict]) -> list[dict]:
        return await asyncio.to_thread(self._put, items, True)

    async def _do_read(self, key: Any, **kwargs: Any) -> dict | None:
        return await asyncio.to_thread(self._properties, str(key))

    async def _do_delete(self, keys: Sequence[Any], **kwargs: Any) -> list[dict]:
        return await asyncio.to_thread(self._remove, keys)

    async def query(self, query: str, **kwargs: Any) -> str:
        """List blobs whose name starts with ``query``.

        Blob storage has no query language, and inventing one here would be a
        lie a caller then has to unlearn. A prefix is what the service
        actually indexes, so a prefix is what this accepts. Returns
        ``{"results": [...], "count": n}``, the read plane's shape.
        """
        prefix = str(query or "")
        limit = int(kwargs.get("max_rows") or self._max_list)
        try:
            rows = await self._guarded(
                lambda: asyncio.to_thread(self._list, prefix, max(1, limit))
            )
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("query", exc)
        return json.dumps({"results": rows, "count": len(rows)}, default=str)

    async def content(self, name: str, *, max_bytes: int) -> dict | None:
        """One blob's bytes, capped. ``None`` when the blob does not exist.

        Separate from :meth:`read` because ``read`` answers "is it there and
        how big", which a verification poll must be able to ask without
        downloading a megabyte per attempt.
        """
        return await self._guarded(
            lambda: asyncio.to_thread(self._download, str(name), int(max_bytes))
        )

    async def close(self) -> None:
        """Close the client this connector built. Never the credential."""
        if self._owned_client is not None:
            await asyncio.to_thread(self._owned_client.close)

    # ------------------------------------------------------------------
    # Blocking bodies. Each runs in a worker thread.
    # ------------------------------------------------------------------

    def _put(self, items: Sequence[dict], overwrite: bool) -> list[dict]:
        results: list[dict] = []
        for item in items:
            name = str(self._key_of(item))
            data = _as_bytes(item.get(self._content_field))
            content_type = str(item.get(self._content_type_field) or DEFAULT_MEDIA_TYPE)
            blob = self._container.get_blob_client(name)
            try:
                blob.upload_blob(
                    data,
                    overwrite=overwrite,
                    content_settings=self._content_settings(content_type),
                )
            except Exception as exc:  # noqa: BLE001 - 409 is an outcome
                raise_if_network_denial(exc, "")
                if not overwrite and _is_conflict(exc):
                    results.append(
                        {"key": name, "ok": False, "detail": "already exists"}
                    )
                    continue
                raise
            results.append(
                {
                    "key": name,
                    "ok": True,
                    "detail": "overwritten" if overwrite else "created",
                }
            )
        return results

    def _remove(self, keys: Sequence[Any]) -> list[dict]:
        results: list[dict] = []
        for key in keys:
            name = str(key)
            try:
                self._container.get_blob_client(name).delete_blob()
            except Exception as exc:  # noqa: BLE001 - 404 is a failed delete here
                raise_if_network_denial(exc, "")
                if not _is_not_found(exc):
                    raise
                # Not "already gone": the caller asked for this name to stop
                # existing and cannot tell a typo from a removal otherwise.
                results.append(
                    {"key": name, "ok": False, "detail": "no blob with that name"}
                )
                continue
            results.append({"key": name, "ok": True, "detail": "deleted"})
        return results

    def _properties(self, name: str) -> dict | None:
        blob = self._container.get_blob_client(name)
        try:
            properties = blob.get_blob_properties()
        except Exception as exc:  # noqa: BLE001 - absence is an answer
            raise_if_network_denial(exc, "")
            if _is_not_found(exc):
                return None
            raise
        # Soft delete keeps properties answerable after a delete; without this
        # a verification poll would confirm a removal that a listing denies.
        if bool(getattr(properties, "deleted", False)):
            return None
        settings = getattr(properties, "content_settings", None)
        return {
            self._key_field: name,
            "size": int(getattr(properties, "size", 0) or 0),
            "contentType": str(getattr(settings, "content_type", "") or ""),
            "lastModified": _text(getattr(properties, "last_modified", "")),
            "etag": _text(getattr(properties, "etag", "")),
        }

    def _download(self, name: str, max_bytes: int) -> dict | None:
        existing = self._properties(name)
        if existing is None:
            return None
        size = int(existing.get("size") or 0)
        length = min(size, max_bytes) if size else max_bytes
        data = b""
        if length:
            blob = self._container.get_blob_client(name)
            data = blob.download_blob(offset=0, length=length).readall()
        payload = dict(existing)
        payload["data"] = bytes(data)
        payload["truncated"] = bool(size and size > len(data))
        return payload

    def _list(self, prefix: str, limit: int) -> list[dict]:
        rows: list[dict] = []
        listing = self._container.list_blobs(name_starts_with=prefix or None)
        for blob in listing:
            if len(rows) >= limit:
                break
            settings = getattr(blob, "content_settings", None)
            rows.append(
                {
                    self._key_field: _text(getattr(blob, "name", "")),
                    "size": int(getattr(blob, "size", 0) or 0),
                    "contentType": _text(getattr(settings, "content_type", "")),
                    "lastModified": _text(getattr(blob, "last_modified", "")),
                }
            )
        return rows

    def _content_settings(self, content_type: str) -> Any:
        sdk = load_blob_sdk()
        return sdk.ContentSettings(content_type=content_type)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


__all__ = ["DEFAULT_KEY_FIELD", "DEFAULT_MAX_LIST", "BlobObjects"]
