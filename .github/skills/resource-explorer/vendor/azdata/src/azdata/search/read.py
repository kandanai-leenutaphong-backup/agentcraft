"""Azure AI Search connector — hybrid keyword + vector + semantic retrieval.

WHY THIS EXISTS
---------------
Three behaviours that a straight SDK call gets wrong.

**One breaker per endpoint, not one per process.** A quota exhaustion on
one search service will otherwise open a global breaker and disable a
healthy second service. Breakers are keyed on the endpoint string.

**Semantic quota exhaustion is not an outage.** On the free tier, the
monthly semantic-query allowance runs out and the service returns an error
for a request it would happily serve without the paid re-ranker. Treating
that as a failure trips the breaker and takes search down for everyone.
The connector retries once without semantic ranking instead — degraded,
not failed (GOTCHAS.md G4).

**Iteration is where it fails.** The SDK returns a lazy pager, so the HTTP
call has not necessarily happened when ``search()`` returns. The quota
error frequently surfaces while iterating results, and a try/except around
the call alone misses it. Both sites are guarded (GOTCHAS.md G5).

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
``project_doc`` is required, not defaulted. Which field holds the text,
which the title, how much to keep — that is the caller's schema, and a
default would silently truncate someone's data.

The connector is synchronous, matching the SDK. Wrap in
``asyncio.to_thread`` from async code.

DEPENDENCIES
------------
Standard library, plus ``azure-search-documents`` loaded on first query.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

from azdata.core.breaker import registry
from azdata.core.config import AzureDataConfig
from azdata.core.envelope import degraded_envelope, error_envelope
from azdata.core.optional import load

logger = logging.getLogger(__name__)

# Emitted verbatim by the service when the free-tier semantic allowance is
# spent. Matching on message text is fragile and unavoidable: the failure
# arrives as a generic HTTP error with no distinguishing code.
SEMANTIC_QUOTA_MARKER = "Free Query Semantic Usage exceeded"


class SearchConnector:
    """Read-only hybrid search with per-endpoint failure isolation.

    Args:
        credential_provider: Returns a ``TokenCredential``. Key-based
            credentials are deliberately not supported; use a role
            assignment.
        default_endpoint: Used when a call does not name one.
        timeout_seconds: Passed to the SDK. Without it a degraded service
            blocks the caller for the SDK default, which is much longer
            than any interactive path can afford.
    """

    def __init__(
        self,
        *,
        credential_provider: Callable[[], Any],
        default_endpoint: str = "",
        timeout_seconds: int = 15,
        breaker_failure_threshold: int = 3,
        breaker_cooldown_secs: float = 60.0,
        breaker_key_prefix: str = "ai_search",
        degraded_detail: str = "Search temporarily unavailable.",
        not_configured_detail: str = "Search endpoint not configured.",
    ) -> None:
        self._credential_provider = credential_provider
        self._default_endpoint = default_endpoint
        self._timeout = timeout_seconds
        self._breaker_failure_threshold = breaker_failure_threshold
        self._breaker_cooldown_secs = breaker_cooldown_secs
        self._breaker_key_prefix = breaker_key_prefix
        self._degraded_detail = degraded_detail
        self._not_configured_detail = not_configured_detail

        self._clients: dict[str, Any] = {}
        self._breakers: dict[str, Any] = {}
        # threading, not asyncio: this connector runs inside worker threads.
        self._client_lock = threading.Lock()
        self._breaker_lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        **kwargs,
    ) -> "SearchConnector":
        kwargs.setdefault("default_endpoint", config.search_endpoint)
        kwargs.setdefault("breaker_failure_threshold", config.breaker_threshold)
        kwargs.setdefault("breaker_cooldown_secs", config.breaker_cooldown_secs)
        return cls(credential_provider=credential_provider, **kwargs)

    def breaker_for(self, endpoint: str | None) -> Any:
        """Return the breaker for ``endpoint``, created on first use."""
        key = f"{self._breaker_key_prefix}:{endpoint or 'default'}"
        breaker = self._breakers.get(key)
        if breaker is None:
            with self._breaker_lock:
                breaker = self._breakers.get(key)
                if breaker is None:
                    breaker = registry.get_or_create(
                        key,
                        failure_threshold=self._breaker_failure_threshold,
                        cooldown_secs=self._breaker_cooldown_secs,
                    )
                    self._breakers[key] = breaker
        return breaker

    def _get_client(self, index_name: str, endpoint: str) -> Any:
        """One client per (endpoint, index). Construction is not free."""
        cache_key = f"{endpoint}::{index_name}"
        client = self._clients.get(cache_key)
        if client is None:
            with self._client_lock:
                client = self._clients.get(cache_key)
                if client is None:
                    documents = load(
                        "azure.search.documents", dist="azure-search-documents"
                    )
                    client = documents.SearchClient(
                        endpoint=endpoint,
                        index_name=index_name,
                        credential=self._credential_provider(),
                    )
                    self._clients[cache_key] = client
        return client

    def execute(
        self,
        query: str,
        /,
        *,
        index_name: str,
        project_doc: Callable[[dict], dict],
        semantic_config: str = "",
        vector_field: str = "text_vector",
        top_k: int = 5,
        endpoint: str | None = None,
    ) -> str:
        """Run hybrid search and return a JSON string.

        Returns ``{"results": [...], "count": N}`` on success, a degraded
        envelope when the endpoint breaker is open, an error envelope
        otherwise.

        ``semantic_config`` empty means keyword + vector only, with no
        semantic re-ranking attempted. ``vector_field`` empty disables the
        vector leg for an index that has no embedding field.
        """
        resolved = endpoint or self._default_endpoint
        if not resolved:
            return error_envelope(self._not_configured_detail)

        breaker = self.breaker_for(resolved)
        if breaker.is_open():
            logger.warning("search.breaker_open index=%s", index_name)
            return degraded_envelope(self._degraded_detail)

        client = self._get_client(index_name, resolved)
        models = load("azure.search.documents.models", dist="azure-search-documents")
        logger.info("search.execute index=%s: %s", index_name, query[:200])

        def _run(use_semantic: bool) -> Any:
            params: dict[str, Any] = {
                "search_text": query,
                "top": top_k,
                "timeout": self._timeout,
            }
            if use_semantic and semantic_config:
                params["query_type"] = models.QueryType.SEMANTIC
                params["semantic_configuration_name"] = semantic_config
                params["query_caption"] = models.QueryCaptionType.EXTRACTIVE
            if vector_field:
                params["vector_queries"] = [
                    models.VectorizableTextQuery(
                        text=query,
                        k_nearest_neighbors=50,
                        fields=vector_field,
                    )
                ]
            return client.search(**params)

        try:
            results = _run(use_semantic=True)
        except Exception as exc:
            if SEMANTIC_QUOTA_MARKER not in str(exc):
                breaker.record_failure()
                logger.exception("search.failed index=%s", index_name)
                return error_envelope("Search failed", exc=exc)
            logger.warning("search.semantic_quota_exhausted index=%s", index_name)
            try:
                results = _run(use_semantic=False)
            except Exception as retry_exc:
                breaker.record_failure()
                logger.exception("search.retry_failed index=%s", index_name)
                return error_envelope("Search failed", exc=retry_exc)

        # The pager is lazy: the request may not have been issued above, so
        # the same quota error can arrive here (G5).
        try:
            formatted = [project_doc(doc) for doc in results]
        except Exception as exc:
            if SEMANTIC_QUOTA_MARKER not in str(exc):
                breaker.record_failure()
                logger.exception("search.iteration_failed index=%s", index_name)
                return error_envelope(f"Result processing failed: {exc}")
            logger.warning(
                "search.semantic_quota_exhausted_during_iteration index=%s",
                index_name,
            )
            try:
                formatted = [project_doc(doc) for doc in _run(use_semantic=False)]
            except Exception as retry_exc:
                breaker.record_failure()
                logger.exception("search.retry_failed index=%s", index_name)
                return error_envelope(f"Result processing failed: {retry_exc}")

        breaker.record_success()
        logger.info("search.complete index=%s results=%d", index_name, len(formatted))
        return json.dumps({"results": formatted, "count": len(formatted)}, default=str)

    def close(self) -> None:
        """Close every cached search client."""
        for client in self._clients.values():
            close = getattr(client, "close", None)
            if close is not None:
                try:
                    close()
                except Exception as exc:
                    logger.warning("search.client_close_failed: %s", exc)
        self._clients.clear()


__all__ = ["SEMANTIC_QUOTA_MARKER", "SearchConnector"]
