"""Fixed-target synchronous Search reads through the canonical native client."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Mapping, Sequence
from contextvars import copy_context
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from azdata import (
    AsyncTransport, ConfigurationError, ConnectorConfig, DataConnector, OperationResult,
    Policy, QueryRequest, ReadRequest, RecordKey, connect,
)

from .transport import SearchError


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


def _failure(result: OperationResult) -> SearchError:
    code = result.errors[0].code if result.errors else result.status
    if result.status == "denied":
        status = 403
    elif result.status in {"invalid", "unsupported"}:
        status = 400
    elif code == "rate_limited":
        status = 429
    elif code.startswith(("transport_", "deadline_")):
        status = 0
    else:
        status = 503
    return SearchError(status, f"{result.status}:{code}")


class SearchReadClient:
    def __init__(self, config: ConnectorConfig, *, credential: Any, policy: Policy,
                 transport: AsyncTransport | None = None) -> None:
        if not isinstance(config, ConnectorConfig) or not isinstance(policy, Policy):
            raise SearchError(400, "invalid_binding")
        endpoint = urlsplit(config.endpoint)
        if (endpoint.scheme != "https" or endpoint.hostname not in config.allowed_hosts
                or endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment
                or endpoint.username or endpoint.password or endpoint.port not in {None, 443}
                or set(config.target.coordinates) != {"index"}):
            raise SearchError(400, "invalid_search_target")
        if (not policy.grants <= {"query", "read"} or policy.max_concurrency != 1
                or policy.destructive or policy.limits.max_attempts != 1
                or policy.limits.timeout_seconds > 30 or policy.limits.max_items > 100
                or policy.limits.max_output_bytes > 1_048_576):
            raise SearchError(400, "invalid_read_policy")
        self._config = config
        self._credential = credential
        self._policy = policy
        self._transport = transport
        self._index = config.target.coordinates["index"]
        self._lock = threading.Lock()
        self._runner: asyncio.Runner | None = None
        self._connector: DataConnector | None = None
        self._closed = False
        self._closing = threading.Event()
        self._active = threading.Event()
        self._metrics_lock = threading.Lock()
        self._metrics = {"submitted": 0, "completed": 0, "known_attempts": 0,
                 "unknown_attempt_operations": 0, "operations": {"query": 0, "read": 0}}

    def describe(self) -> dict[str, Any]:
        state = ("closed" if self._closed else "closing" if self._closing.is_set()
             else "active" if self._active.is_set() else "lazy" if self._runner is not None
             else "configured")
        with self._metrics_lock:
            metrics = {**self._metrics, "operations": dict(self._metrics["operations"])}
        return {"endpoint": self._config.endpoint, "index": self._index,
                "configured": True, "credential_configured": self._credential is not None,
                "transport": "azdata-native", "grants": sorted(self._policy.grants),
                "closed": self._closed, "state": state, "metrics": metrics}

    @staticmethod
    def _require_sync() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise SearchError(400, "active_event_loop_use_asyncio_to_thread")

    def _require_read(self, index: str, operation: str) -> None:
        self._require_sync()
        if self._closing.is_set():
            raise SearchError(503, "client_closing")
        if index != self._index:
            raise SearchError(403, "target_outside_scope")
        if operation not in self._policy.grants:
            raise SearchError(403, "operation_not_granted")
        if self._credential is None:
            raise SearchError(503, "credential_not_configured")
        token = getattr(self._credential, "get_token", None)
        if not callable(token) or inspect.iscoroutinefunction(token):
            raise SearchError(400, "synchronous_borrowed_credential_required")

    def search(self, index: str, text: str = "*", *, top: int = 10,
               filter: str = "", select: Sequence[str] | None = None) -> list[dict[str, Any]]:
        self._require_read(index, "query")
        if type(top) is not int or not 1 <= top <= self._policy.limits.max_items:
            raise SearchError(400, "invalid_top")
        request = QueryRequest(dialect="search", expression=text, projection=tuple(select or ()),
                               limits=replace(self._policy.limits, max_items=top),
                               service_options={"search": {"filter": filter}} if filter else {})
        result = self._execute(request)
        return [self._document(item.content.data) for item in result.items
                if item.content is not None]

    def search_count(self, index: str, text: str = "*", *, filter: str = "") -> int:
        self._require_read(index, "query")
        options: dict[str, Any] = {"count": True}
        if filter:
            options["filter"] = filter
        result = self._execute(QueryRequest(
            dialect="search", expression=text, projection=(self._config.key_field,),
            limits=replace(self._policy.limits, max_items=1), service_options={"search": options}))
        count = result.metadata.get("count")
        if type(count) is not int or count < 0:
            raise SearchError(503, "count_unknown")
        return count

    def get_document(self, index: str, key: str) -> dict[str, Any] | None:
        self._require_read(index, "read")
        result = self._execute(ReadRequest(keys=(RecordKey({self._config.key_field: key}),), missing="ok"))
        if len(result.items) != 1:
            raise SearchError(503, "invalid_keyed_result")
        item = result.items[0]
        if item.content is None:
            return None
        document = self._document(item.content.data)
        if document.get(self._config.key_field) != key:
            raise SearchError(503, "invalid_keyed_identity")
        return document

    @staticmethod
    def _document(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SearchError(503, "invalid_document")
        document = _thaw(value)
        if "@search.reranker_score" in document:
            document["@search.rerankerScore"] = document.pop("@search.reranker_score")
        return document

    async def _call(self, request: QueryRequest | ReadRequest) -> OperationResult:
        if self._connector is None:
            self._connector = connect("search", self._config, credential=self._credential,
                                      policy=self._policy, transport=self._transport)
        if isinstance(request, QueryRequest):
            return await self._connector.query(request)
        return await self._connector.read(request)

    def _execute(self, request: QueryRequest | ReadRequest) -> OperationResult:
        with self._lock:
            if self._closing.is_set():
                raise SearchError(503, "client_closing")
            if self._runner is None:
                self._runner = asyncio.Runner()
            self._active.set()
            result = None
            with self._metrics_lock:
                self._metrics["submitted"] += 1
                self._metrics["operations"]["query" if isinstance(request, QueryRequest) else "read"] += 1
            try:
                result = self._runner.run(self._call(request), context=copy_context())
            except ConfigurationError:
                self._dispose()
                raise SearchError(400, "invalid_binding") from None
            except Exception:
                self._dispose()
                raise SearchError(503, "canonical_operation_failed") from None
            except BaseException:
                self._dispose()
                raise
            finally:
                self._active.clear()
                attempts = result.metrics.get("attempts") if result is not None else None
                with self._metrics_lock:
                    self._metrics["completed"] += 1
                    if type(attempts) is int and attempts >= 0:
                        self._metrics["known_attempts"] += attempts
                    else:
                        self._metrics["unknown_attempt_operations"] += 1
            if (result.status != "success" or result.errors
                    or any(item.status != "success" or item.error for item in result.items)):
                raise _failure(result)
            if (any(caveat.code == "output_bound" for caveat in result.caveats)
                    or (result.truncated and result.continuation is None)):
                raise SearchError(503, "incomplete_result")
            if isinstance(request, QueryRequest) and any(item.content is None for item in result.items):
                raise SearchError(503, "invalid_query_item")
            return result

    def close(self) -> None:
        self._require_sync()
        self._closing.set()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._dispose()

    def _dispose(self) -> None:
        runner, connector = self._runner, self._connector
        self._runner = None
        self._connector = None
        try:
            if runner is not None and connector is not None:
                runner.run(connector.aclose(), context=copy_context())
        finally:
            if runner is not None:
                runner.close()

    def __enter__(self) -> SearchReadClient:
        self._require_sync()
        if self._closing.is_set():
            raise SearchError(503, "client_closed")
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self.close()