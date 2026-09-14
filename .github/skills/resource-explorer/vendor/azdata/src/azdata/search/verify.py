"""Azure AI Search verify plane — a document key is the addressable unit.

WHY THIS EXISTS
---------------
"What changed in this index" has an exact answer in Search and an
inconvenient one: the key space is enumerable only through a search, and a
search is bounded by ``top``. So enumeration is explicitly capped, one key
beyond the cap is fetched so the core plane can tell "exactly the cap" from
"more than the cap", and the snapshot says which it was.

The content digest is over the whole projected document. Search has no
etag on the data plane, so a version marker would have to be a field in
the caller's schema — and this module does not get to know one.

DEPENDENCIES
------------
Standard library, plus ``azure-search-documents`` loaded on first call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Mapping

from azdata.core.config import DEFAULT_VERIFY_MAX_KEYS, AzureDataConfig
from azdata.core.optional import load

logger = logging.getLogger(__name__)


def content_digest(document: Mapping[str, Any], key_field: str) -> str:
    """sha256 over a document's own fields, in sorted key order.

    Service metadata (``@search.score`` and friends) is excluded: it varies
    per query and would report every document as changed on every
    comparison.
    """
    payload = {
        name: value
        for name, value in document.items()
        if not str(name).startswith("@") and name != key_field
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class SearchKeys:
    """Enumerate the document keys of one Search index.

    Args:
        client: A ``SearchClient``. Injected in tests; built from the
            endpoint and index name otherwise.
        key_field: The index's key field. The caller's schema.
        stats_provider: The index's observe plane, used to populate
            ``snapshot.stats``. Optional; a snapshot without stats is still
            a valid snapshot.
        max_keys: Enumeration cap. Defaults to ``AZDATA_VERIFY_MAX_KEYS``.
    """

    service = "search"

    def __init__(
        self,
        *,
        client: Any = None,
        endpoint: str = "",
        index_name: str = "",
        credential: Any = None,
        key_field: str = "id",
        stats_provider: Any = None,
        max_keys: int = DEFAULT_VERIFY_MAX_KEYS,
    ) -> None:
        self._client = client
        self._endpoint = endpoint
        self._index_name = index_name
        self._credential = credential
        self._key_field = key_field
        self._stats = stats_provider
        self.max_keys = max_keys

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Any,
        *,
        index_name: str,
        **kwargs: Any,
    ) -> "SearchKeys":
        kwargs.setdefault("endpoint", config.search_endpoint)
        kwargs.setdefault("max_keys", config.verify_max_keys)
        return cls(
            index_name=index_name,
            credential=credential_provider(),
            **kwargs,
        )

    @property
    def target(self) -> str:
        return self._index_name

    def _search_client(self) -> Any:
        if self._client is None:
            if not self._endpoint:
                raise ValueError(
                    "search endpoint is not configured (search_endpoint is empty)"
                )
            documents = load("azure.search.documents", dist="azure-search-documents")
            self._client = documents.SearchClient(
                endpoint=self._endpoint,
                index_name=self._index_name,
                credential=self._credential,
            )
        return self._client

    async def enumerate_keys(self, target: str | None = None) -> dict[str, str]:
        """Return ``{document key: content digest}``, capped.

        One document past the cap is requested deliberately: without it a
        result of exactly ``max_keys`` is indistinguishable from a truncated
        one, and the snapshot would claim to be complete when it was not.
        """
        client = self._search_client()

        def _run() -> list[Any]:
            return list(
                client.search(search_text="*", top=self.max_keys + 1)
            )

        documents = await asyncio.to_thread(_run)
        keys: dict[str, str] = {}
        for document in documents:
            mapping = dict(document)
            key = mapping.get(self._key_field)
            if key is None:
                continue
            keys[str(key)] = content_digest(mapping, self._key_field)
        return keys

    async def count(self, target: str | None = None) -> int:
        """Total documents, or -1 when the service will not say."""
        client = self._search_client()
        counter = getattr(client, "get_document_count", None)
        if counter is None:
            return -1
        try:
            return int(await asyncio.to_thread(counter))
        except Exception as exc:  # noqa: BLE001 - -1 is the contract for unknown
            logger.info("search.count_unavailable: %s: %s", type(exc).__name__, exc)
            return -1

    async def stats(self, target: str | None = None) -> Any:
        if self._stats is None:
            return {}
        return await self._stats.stats(target or self._index_name)


__all__ = ["SearchKeys", "content_digest"]
