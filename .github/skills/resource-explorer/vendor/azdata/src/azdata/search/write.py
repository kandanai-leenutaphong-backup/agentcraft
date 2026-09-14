"""Azure AI Search write plane — document CRUD against one index.

WHY THIS EXISTS
---------------
The read plane in ``search/read.py`` covers retrieval. Everything that puts
documents *into* an index is a different set of failures, and every one of
them is silent.

**An accepted upload is not an indexed document.** The service returns
``succeeded=True`` per document the moment it has durably queued the
change, and the document becomes retrievable some time afterwards. Code
that writes and immediately reads fails intermittently, acquires a
``sleep(2)``, and then fails again under load. The base class polls
instead, bounded, and ``verify=True`` is the whole reason this connector
exists rather than a two-line SDK call.

**A partial batch failure looks like a success.** ``upload_documents``
returns HTTP 200 with a per-document result list in which individual
entries carry ``succeeded=False``. A caller that checks the HTTP status
loses documents and never learns which. Every result is mapped and any
failure surfaces in the envelope's ``failed`` list.

**The SDK is synchronous.** ``SearchClient`` issues blocking HTTP. Called
directly from a coroutine it stalls the event loop for the duration of an
indexing round trip, which under a partial outage is the SDK retry budget,
not a few milliseconds. Every call here goes through
:func:`asyncio.to_thread`.

**Search has no insert-if-absent.** There is no service operation that
fails when a key already exists: ``upload`` is an upsert and would
overwrite. :meth:`SearchDocuments._do_create` therefore reads every key
first and refuses the whole batch when any already exists. That is a
deliberate deviation from the base contract's wording and it is not
atomic — another writer can insert between the check and the upload, and
the base chunks large batches so an earlier chunk stays applied when a
later one is refused. Callers that need exactly-once semantics need a
different store; callers that need idempotence should use ``upload``.

**The SDK's return types are mappings that are not dicts, and they lie under
attribute names.** ``azure-search-documents`` 12.0 made ``LookupDocument`` and
``IndexingResult`` ``MutableMapping`` subclasses. Neither is a ``dict``, so
``json.dumps(..., default=str)`` stringifies a document instead of serialising
it; and ``IndexingResult``'s mapping keys are the *wire* names, so
``result["succeeded"]`` is absent while ``result.succeeded`` is ``True``.
Both shipped: every mutation whose target existed returned 500 after its write
had landed, and every successful delete reported failure. :func:`_plain` and
:func:`_result_field` are the two answers, and the tests pin the real shapes
rather than a fake's.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
``key_field`` is a parameter and ``project_doc`` is required, never
defaulted. No field name from a consuming index appears in this module.

WHAT THIS IS NOT
----------------
Not index management — that is ``search/deploy.py``. Not a transaction
boundary; see the base class. Not a bulk loader: it does no parallel
fan-out, because the throttle gate exists precisely to keep concurrency
below what the service will start rejecting.

DEPENDENCIES
------------
Standard library, plus ``azure-search-documents`` loaded on first use, and
``azure-core`` consulted opportunistically to recognise a not-found error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from azdata.core.breaker import CircuitBreaker
from azdata.core.config import AzureDataConfig
from azdata.core.crud import CrudConnector, WritePolicy
from azdata.core.envelope import sanitize_detail
from azdata.core.optional import load

logger = logging.getLogger(__name__)

# Returned by the data plane for a document that is not in the index.
NOT_FOUND_STATUS = 404


def is_not_found(exc: BaseException) -> bool:
    """True when ``exc`` is the SDK's "no such document/resource" error.

    ``azure.core.exceptions`` is consulted through :func:`load` rather than
    imported at module scope: this package must import with no SDK
    installed, and ``azure-core`` is only present because something else
    pulled it in. When it is absent the class name and the HTTP status are
    enough, and they are also what a test fake can reproduce.
    """
    try:
        core = load("azure.core.exceptions", dist="azure-core")
    except Exception:  # noqa: BLE001 - absence is the expected case here
        core = None
    not_found = getattr(core, "ResourceNotFoundError", None)
    if isinstance(not_found, type) and isinstance(exc, not_found):
        return True
    if type(exc).__name__ == "ResourceNotFoundError":
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return status == NOT_FOUND_STATUS


class SearchDocuments(CrudConnector):
    """Create, read, upload and delete documents in one Azure AI Search index.

    Args:
        endpoint: Search service endpoint. Empty means unconfigured, and
            every operation answers with an error envelope naming the
            missing setting instead of building a client that 401s.
        index_name: The single index this instance writes to. One instance
            per index, because the SDK client is bound to one.
        credential: A ``TokenCredential``. Keys and connection strings are
            deliberately unsupported; use a data-plane role assignment.
        key_field: The index's key field name. The caller's schema, not
            this module's business.
        search_connector: Optional read-plane ``SearchConnector``. When
            given, :meth:`query` delegates to it and inherits its semantic
            fallback and per-endpoint breaker.
    """

    service = "search"

    def __init__(
        self,
        *,
        endpoint: str,
        index_name: str,
        credential: Any,
        key_field: str = "id",
        policy: WritePolicy | None = None,
        breaker: CircuitBreaker | None = None,
        gate_provider: Callable[[], Any] | None = None,
        search_connector: Any | None = None,
        default_top: int = 5,
    ) -> None:
        super().__init__(
            policy=policy,
            breaker=breaker,
            gate_provider=gate_provider,
            key_field=key_field,
        )
        self._endpoint = endpoint
        self._index_name = index_name
        self._credential = credential
        self._search = search_connector
        self._default_top = default_top
        self._client_obj: Any | None = None
        # threading, not asyncio: the client is built inside a worker thread
        # by whichever operation reaches it first.
        self._client_lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        index_name: str,
        policy: WritePolicy | None = None,
        **kwargs: Any,
    ) -> "SearchDocuments":
        kwargs.setdefault("endpoint", config.search_endpoint)
        return cls(
            index_name=index_name,
            credential=credential_provider(),
            policy=policy,
            **kwargs,
        )

    @property
    def index_name(self) -> str:
        return self._index_name

    # ------------------------------------------------------------------
    # Client.
    # ------------------------------------------------------------------

    def _client(self) -> Any:
        """The cached ``SearchClient``. Construction is not free; do it once."""
        if not self._endpoint:
            raise ValueError(
                "search endpoint is not configured (search_endpoint is empty)"
            )
        client = self._client_obj
        if client is None:
            with self._client_lock:
                client = self._client_obj
                if client is None:
                    documents = load(
                        "azure.search.documents", dist="azure-search-documents"
                    )
                    client = documents.SearchClient(
                        endpoint=self._endpoint,
                        index_name=self._index_name,
                        credential=self._credential,
                    )
                    self._client_obj = client
        return client

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    async def _do_create(self, items: Sequence[dict]) -> list[dict]:
        """Upload, but only after proving no key is already present.

        The pre-read is the only insert-if-absent Search offers. It races,
        and the module docstring says so; without it ``create`` would
        silently overwrite and be indistinguishable from ``upload``.
        """
        client = self._client()
        conflicts = [
            key
            for key in (self._key_of(item) for item in items)
            if await self._read_key(client, key) is not None
        ]
        if conflicts:
            raise ValueError(
                f"{len(conflicts)} key(s) already exist and create will not "
                f"overwrite: {sorted(str(k) for k in conflicts)[:10]}"
            )
        raw = await asyncio.to_thread(
            client.upload_documents, documents=list(items)
        )
        return _indexing_results(raw)

    async def _do_upload(self, items: Sequence[dict]) -> list[dict]:
        """Merge-or-upload: the idempotent write, and the one to prefer."""
        client = self._client()
        raw = await asyncio.to_thread(
            client.merge_or_upload_documents, documents=list(items)
        )
        return _indexing_results(raw)

    async def _do_read(self, key: Any, **kwargs: Any) -> dict | None:
        return await self._read_key(self._client(), key, **kwargs)

    async def _do_delete(self, keys: Sequence[Any], **kwargs: Any) -> list[dict]:
        client = self._client()
        # The delete API takes documents, not keys: a stub carrying the key
        # field is the whole document it needs.
        stubs = [{self._key_field: key} for key in keys]
        raw = await asyncio.to_thread(client.delete_documents, documents=stubs)
        return _indexing_results(raw, default_keys=list(keys))

    async def query(
        self,
        query: str,
        *,
        project_doc: Callable[[dict], dict],
        top: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Free-form search returning ``{"results": [...], "count": N}``.

        ``project_doc`` is required. A default projection would have to
        guess which field holds the text and would silently truncate
        somebody's schema.
        """
        limit = self._default_top if top is None else top
        if self._search is not None:
            kwargs.setdefault("index_name", self._index_name)
            kwargs.setdefault("endpoint", self._endpoint)
            kwargs.setdefault("top_k", limit)
            return await asyncio.to_thread(
                lambda: self._search.execute(query, project_doc=project_doc, **kwargs)
            )

        try:
            docs = await self._guarded(lambda: self._search_now(query, limit, kwargs))
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("query", exc)
        try:
            results = [project_doc(doc) for doc in docs]
        except Exception as exc:  # noqa: BLE001 - boundary
            return self._failure("query", exc)
        return json.dumps({"results": results, "count": len(results)}, default=str)

    def close(self) -> None:
        """Close the search client. Never the credential (G8)."""
        client, self._client_obj = self._client_obj, None
        if client is None:
            return
        closer = getattr(client, "close", None)
        if closer is None:
            return
        try:
            closer()
        except Exception as exc:  # noqa: BLE001 - a close that raises helps nobody
            logger.warning("search.client_close_failed index=%s: %s", self._index_name, exc)

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    async def _read_key(self, client: Any, key: Any, **kwargs: Any) -> dict | None:
        def _get() -> Any:
            return client.get_document(key=key, **kwargs)

        try:
            document = await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001 - absence is a value, not a failure
            if is_not_found(exc):
                return None
            raise
        return _plain(document)

    async def _search_now(self, query: str, top: int, params: dict) -> list[Any]:
        client = self._client()

        # The SDK pager is lazy, so the HTTP call may not have happened when
        # search() returns. Materialise inside the thread or the failure
        # arrives on the event loop, outside the breaker (G5).
        def _run() -> list[Any]:
            return list(client.search(search_text=query, top=top, **params))

        return await asyncio.to_thread(_run)


def _plain(value: Any) -> Any:
    """A JSON-serialisable copy of an SDK model, recursively.

    ``get_document`` returns ``LookupDocument``, which is a ``MutableMapping``
    and is **not** a ``dict``. ``json.dumps(..., default=str)`` does not
    serialise a mapping it does not recognise — it calls ``str()`` on it, so a
    document leaves the envelope as::

        {"results": ["{'id': 'hcscratch-seed-1', 'title': 'seed row'}"]}

    A string. Every caller that then treats a read-back row as a mapping gets
    ``AttributeError: 'str' object has no attribute 'items'`` — and because
    every write here re-reads its target, that was a 500 on every mutation
    whose target existed, *after* the write had already landed. The envelope is
    the contract, so the coercion belongs on the way in, not at each caller.
    """
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, Sequence):
        return [_plain(item) for item in value]
    return value


def _result_field(entry: Any, attribute: str, *wire_keys: str) -> Any:
    """One field of an ``IndexingResult``, whatever the SDK is calling it today.

    ``IndexingResult`` is now a ``MutableMapping`` **and** carries the
    documented attributes, and the two do not agree: the mapping is keyed by
    the wire names, so ``succeeded`` is under ``status`` and ``error_message``
    is under ``errorMessage``. Reading it as a mapping by attribute name
    therefore returns ``None`` for every field, and a delete that returned
    ``succeeded=True, status_code=200`` was reported as "indexing failed with
    status None".

    Attributes first, because that is the SDK's own documented surface and it
    answers correctly for both old and new models. Mapping keys are the
    fallback, so a test fake can still be a plain dict without subclassing an
    SDK model — which is the property that let this ship, and is worth keeping
    only if the attribute path is tried first.
    """
    if hasattr(entry, attribute):
        return getattr(entry, attribute)
    if isinstance(entry, Mapping):
        for key in (attribute, *wire_keys):
            if key in entry:
                return entry[key]
    return None


def _indexing_results(raw: Any, default_keys: Sequence[Any] | None = None) -> list[dict]:
    """Map the SDK's ``IndexingResult`` list onto the base's per-item shape.

    ``IndexingResult`` carries ``key``, ``succeeded``, ``error_message`` and
    ``status_code`` as attributes, and ``key``, ``status``, ``errorMessage``
    and ``statusCode`` as mapping keys. Both are read; see
    :func:`_result_field` for why the order matters.
    """
    entries = list(raw or [])
    mapped: list[dict] = []
    for position, entry in enumerate(entries):
        key = _result_field(entry, "key")
        ok = bool(_result_field(entry, "succeeded", "status"))
        detail = _result_field(entry, "error_message", "errorMessage") or ""
        status = _result_field(entry, "status_code", "statusCode")
        if key is None and default_keys is not None and position < len(default_keys):
            # Delete stubs carry the key the caller asked for; some fakes and
            # error paths return a result without echoing it.
            key = default_keys[position]
        if not ok and not detail:
            detail = f"indexing failed with status {status}"
        mapped.append({"key": key, "ok": ok, "detail": sanitize_detail(str(detail))})
    return mapped


__all__ = ["NOT_FOUND_STATUS", "SearchDocuments", "is_not_found"]
