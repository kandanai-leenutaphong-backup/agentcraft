"""CRUD over Azure AI Search: indexes and documents.

The service reports document-level failures inside a 200 or 207 response body,
so every upload and delete result is inspected rather than trusted.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any

from .config import SearchConfig, SearchConfigError, valid_index_name
from .schema import IndexSpec, render_index
from .transport import SearchError, Transport

#: 1000 documents or ~16 MB per batch. With vectors the size limit binds first.
DEFAULT_BATCH = 50


class SearchIndexClient:
    """Create, update, delete and query indexes and their documents."""

    def __init__(self, config: SearchConfig, transport: Transport | None = None) -> None:
        self._config = config
        self._transport = transport or Transport(scope=config.scope)

    @classmethod
    def from_env(
        cls,
        prefix: str = "SEARCH_",
        *,
        transport: Transport | None = None,
        **overrides: object,
    ) -> "SearchIndexClient":
        """Build from ``<prefix>*`` environment variables read at call time."""
        return cls(SearchConfig.from_env(prefix, **overrides), transport)

    @property
    def config(self) -> SearchConfig:
        return self._config

    def _call(self, method: str, path: str, *, body: Any = None, absent_ok: bool = False) -> Any:
        return self._transport.request(
            method,
            self._config.url(path),
            body=body,
            timeout=self._config.timeout_seconds,
            max_attempts=self._config.max_attempts,
            absent_ok=absent_ok,
        )

    @staticmethod
    def _index_path(name: str, suffix: str = "") -> str:
        # Validated before it reaches a URL: an unchecked name is both a 400 and a
        # path-injection risk.
        if not valid_index_name(name):
            raise SearchConfigError(f"index name {name!r} must be lowercase letters, digits and single dashes")
        return f"indexes/{name}{suffix}"

    # --- indexes -----------------------------------------------------------

    def list_indexes(self) -> list[str]:
        """Every index name on the service."""
        body = self._call("GET", "indexes?$select=name")
        return sorted(item["name"] for item in (body or {}).get("value", []))

    def get_index(self, name: str) -> dict[str, Any] | None:
        """The stored definition, or ``None`` when the index does not exist."""
        return self._call("GET", self._index_path(name), absent_ok=True)

    def index_exists(self, name: str) -> bool:
        return self.get_index(name) is not None

    def create_or_update_index(self, spec: IndexSpec) -> dict[str, Any]:
        """Apply a declared index definition and return what the service stored.

        A field removed, retyped, rekeyed, or resized is destructive: the service
        drops every document. Compare with :meth:`get_index` before calling when
        the index already holds data.
        """
        # A create answers 201 with the definition; an update answers 204 with an
        # empty body, so the stored definition is read back rather than assumed.
        stored = self._call("PUT", self._index_path(spec.name), body=render_index(spec))
        return stored if isinstance(stored, dict) else (self.get_index(spec.name) or {})

    def delete_index(self, name: str, *, missing_ok: bool = True) -> bool:
        """Delete an index and everything in it. Returns False when it was absent."""
        before = self.index_exists(name)
        if not before and missing_ok:
            return False
        self._call("DELETE", self._index_path(name), absent_ok=missing_ok)
        return before

    def index_stats(self, name: str) -> dict[str, Any]:
        """Document count and storage size as the service reports them."""
        return self._call("GET", self._index_path(name, "/stats")) or {}

    def document_count(self, name: str) -> int:
        return int(self.index_stats(name).get("documentCount", 0))

    # --- documents ---------------------------------------------------------

    def upload_documents(
        self,
        index: str,
        documents: Iterable[Mapping[str, Any]],
        *,
        action: str = "mergeOrUpload",
        batch_size: int = DEFAULT_BATCH,
    ) -> dict[str, Any]:
        """Create or update documents. Raises when any document failed."""
        return self._write(index, documents, action=action, batch_size=batch_size)

    def delete_documents(
        self,
        index: str,
        key_field: str,
        keys: Sequence[str],
        *,
        batch_size: int = DEFAULT_BATCH,
    ) -> dict[str, Any]:
        """Delete documents by key. Raises when any deletion failed."""
        return self._write(
            index,
            ({key_field: key} for key in keys),
            action="delete",
            batch_size=batch_size,
        )

    def _write(
        self,
        index: str,
        documents: Iterable[Mapping[str, Any]],
        *,
        action: str,
        batch_size: int,
    ) -> dict[str, Any]:
        if batch_size < 1 or batch_size > 1000:
            raise SearchConfigError("batch_size must be between 1 and 1000")
        path = self._index_path(index, "/docs/index")
        succeeded = 0
        failures: list[dict[str, Any]] = []
        for batch in _chunks(documents, batch_size):
            payload = {"value": [{"@search.action": action, **dict(doc)} for doc in batch]}
            body = self._call("POST", path, body=payload) or {}
            # A 200 and a 207 carry the same per-document result array; only the
            # entries say what actually landed.
            for entry in body.get("value", []):
                if entry.get("status"):
                    succeeded += 1
                else:
                    failures.append({
                        "key": entry.get("key"),
                        "statusCode": entry.get("statusCode"),
                        "errorMessage": entry.get("errorMessage"),
                    })
        result = {"action": action, "succeeded": succeeded, "failed": len(failures), "failures": failures}
        if failures:
            first = failures[0]
            raise SearchError(
                int(first.get("statusCode") or 207),
                f"{len(failures)} of {succeeded + len(failures)} documents failed; "
                f"first: key={first.get('key')!r} {first.get('errorMessage')}",
                body=result,
            )
        return result

    def get_document(self, index: str, key: str) -> dict[str, Any] | None:
        """One document by key, or ``None`` when it is not there."""
        from urllib.parse import quote

        return self._call("GET", self._index_path(index, f"/docs/{quote(key, safe='')}"), absent_ok=True)

    # --- query -------------------------------------------------------------

    def search(
        self,
        index: str,
        text: str = "*",
        *,
        top: int = 10,
        filter: str = "",
        select: Sequence[str] | None = None,
        order_by: Sequence[str] | None = None,
        vector: Sequence[float] | None = None,
        vector_field: str = "",
        vector_k: int | None = None,
        embedder: Callable[[str], Sequence[float]] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Keyword, vector, or hybrid query. Returns the hit list.

        Supply ``vector`` directly, or an ``embedder`` that turns ``text`` into
        one — for example ``AzureLlmClient.embed``. Passing either alongside
        ``text`` makes the query hybrid.
        """
        body: dict[str, Any] = {"search": text, "top": top}
        if filter:
            body["filter"] = filter
        if select:
            body["select"] = ",".join(select)
        if order_by:
            body["orderby"] = ",".join(order_by)

        values = vector
        if values is None and embedder is not None:
            if not vector_field:
                raise SearchConfigError("vector_field is required when embedding a query")
            values = embedder(text)
        if values is not None:
            if not vector_field:
                raise SearchConfigError("vector_field is required for a vector query")
            body["vectorQueries"] = [{
                "kind": "vector",
                "vector": list(values),
                "fields": vector_field,
                "k": vector_k or top,
            }]

        body.update(kwargs)
        response = self._call("POST", self._index_path(index, "/docs/search"), body=body) or {}
        return list(response.get("value", []))

    def search_count(self, index: str, text: str = "*", *, filter: str = "") -> int:
        """Matching documents as the query engine sees them.

        Index statistics lag uploads by minutes, so a freshly loaded index reports zero
        there while every document is already retrievable. This asks the query engine.
        """
        body: dict[str, Any] = {"search": text, "top": 0, "count": True}
        if filter:
            body["filter"] = filter
        response = self._call("POST", self._index_path(index, "/docs/search"), body=body) or {}
        return int(response.get("@odata.count") or 0)

    def describe(self) -> dict[str, Any]:
        """Non-secret description of what this client would call. Makes no request."""
        return {
            "endpoint": self._config.base_url,
            "api_version": self._config.api_version,
            "scope": self._config.scope,
            "auth": "entra-id-bearer-token",
            "roles_required": ["Search Service Contributor", "Search Index Data Contributor"],
            "timeout_seconds": self._config.timeout_seconds,
            "max_attempts": self._config.max_attempts,
        }


def _chunks(items: Iterable[Mapping[str, Any]], size: int) -> Iterator[list[Mapping[str, Any]]]:
    batch: list[Mapping[str, Any]] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
