"""Data-plane client: queries, control commands, and parameter binding.

One :class:`AdxClient` owns one pooled `KustoClient` per endpoint. Construct it
once and share it; constructing per call discards the token cache and the HTTP
connection pool.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Iterator, Mapping, Sequence

from azure.kusto.data import ClientRequestProperties, KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.response import KustoResponseDataSet

from .config import AdxConfig
from .errors import AdxAuthError, AdxQueryError
from .identifiers import validate_identifier
from .models import QueryResult
from .retry import call_with_retry

LOGGER = logging.getLogger("adx_connector.client")

# KQL scalar type names, keyed by the Python type a caller is likely to pass.
_PARAM_TYPES: dict[type, str] = {
    bool: "bool",
    int: "long",
    float: "real",
    str: "string",
    datetime: "datetime",
    timedelta: "timespan",
}

# Collections cross the wire as KQL `dynamic`, serialised to JSON.
_DYNAMIC_TYPES: tuple[type, ...] = (list, tuple, set, frozenset, dict)


def _kusto_type_of(value: Any) -> str | None:
    """KQL scalar type for ``value``, or None when it cannot be bound."""
    if isinstance(value, _DYNAMIC_TYPES):
        return "dynamic"
    # bool before int: bool is a subclass of int and must not bind as long.
    if isinstance(value, bool):
        return "bool"
    kusto_type = _PARAM_TYPES.get(type(value))
    if kusto_type is not None:
        return kusto_type
    for python_type, candidate in _PARAM_TYPES.items():
        if isinstance(value, python_type):
            return candidate
    return None


def _bindable(value: Any) -> Any:
    """Render ``value`` in the form the service expects for its declared type."""
    if isinstance(value, _DYNAMIC_TYPES):
        import json

        return json.dumps(sorted(value) if isinstance(value, (set, frozenset)) else value, default=str)
    return value


class AdxClient:
    """Executes queries and control commands against one database."""

    def __init__(self, config: AdxConfig, credential: Any | None = None) -> None:
        self._config = config
        self._credential = credential
        self._client: KustoClient | None = None

    # ------------------------------------------------------------------ setup

    @property
    def config(self) -> AdxConfig:
        return self._config

    def _connection_string(self) -> KustoConnectionStringBuilder:
        uri = self._config.cluster_uri
        if self._credential is not None:
            builder = KustoConnectionStringBuilder.with_azure_token_credential(uri, self._credential)
        else:
            # Chained credential: managed identity in Azure, developer sign-in locally.
            from azure.identity import DefaultAzureCredential

            builder = KustoConnectionStringBuilder.with_azure_token_credential(
                uri, DefaultAzureCredential(exclude_interactive_browser_credential=False)
            )
        builder.application_for_tracing = self._config.application_name
        return builder

    @property
    def raw(self) -> KustoClient:
        """The underlying SDK client, created on first use."""
        if self._client is None:
            try:
                self._client = KustoClient(self._connection_string())
            except Exception as exc:  # noqa: BLE001
                raise AdxAuthError(f"could not build a Kusto client for {self._config.cluster_uri}: {exc}") from exc
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "AdxClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------- properties

    def _request_properties(
        self,
        parameters: Mapping[str, Any] | None,
        *,
        timeout_seconds: int | None,
        client_request_id: str | None,
    ) -> tuple[ClientRequestProperties, str]:
        properties = ClientRequestProperties()
        request_id = client_request_id or f"{self._config.application_name};{uuid.uuid4()}"
        properties.client_request_id = request_id
        timeout = timeout_seconds or self._config.query_timeout_seconds
        properties.set_option(properties.request_timeout_option_name, timedelta(seconds=timeout))
        for key, value in (parameters or {}).items():
            validate_identifier(key, kind="query parameter")
            properties.set_parameter(key, _bindable(value))
        return properties, request_id

    @staticmethod
    def declare_parameters(parameters: Mapping[str, Any] | None) -> str:
        """Render the ``declare query_parameters`` prologue for ``parameters``.

        This is the injection boundary for values: the rendered prologue names
        and types the parameters, and the values themselves travel out-of-band
        in the request properties rather than in the query text.
        """
        if not parameters:
            return ""
        fragments = []
        for name, value in parameters.items():
            validate_identifier(name, kind="query parameter")
            kusto_type = _kusto_type_of(value)
            if kusto_type is None:
                raise AdxQueryError(f"parameter {name!r} has unsupported type {type(value).__name__}")
            fragments.append(f"{name}:{kusto_type}")
        return "declare query_parameters(" + ", ".join(fragments) + ");\n"

    # ---------------------------------------------------------------- execute

    @staticmethod
    def _to_result(response: KustoResponseDataSet, request_id: str, elapsed: float) -> QueryResult:
        tables = response.primary_results
        if not tables:
            return QueryResult(columns=(), rows=(), client_request_id=request_id, elapsed_seconds=elapsed)
        table = tables[0]
        columns = tuple(column.column_name for column in table.columns)
        rows = tuple(tuple(row) for row in table.rows)
        return QueryResult(columns=columns, rows=rows, client_request_id=request_id, elapsed_seconds=elapsed)

    def query(
        self,
        kql: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: int | None = None,
        declare: bool = True,
        client_request_id: str | None = None,
    ) -> QueryResult:
        """Run a read-only KQL query.

        Args:
            kql: Query text. Reference parameters by name; never interpolate values.
            parameters: Values bound out-of-band as declared query parameters.
            declare: Prepend the ``declare query_parameters`` prologue. Set False
                only when ``kql`` already declares them.
        """
        properties, request_id = self._request_properties(
            parameters, timeout_seconds=timeout_seconds, client_request_id=client_request_id
        )
        text = (self.declare_parameters(parameters) if declare else "") + kql
        started = time.monotonic()
        deadline = started + (timeout_seconds or self._config.query_timeout_seconds)

        response = call_with_retry(
            lambda: self.raw.execute_query(self._config.database, text, properties),
            max_retries=self._config.max_retries,
            base=self._config.backoff_base_seconds,
            cap=self._config.backoff_cap_seconds,
            deadline=deadline,
            description=f"query {request_id}",
        )
        elapsed = time.monotonic() - started
        LOGGER.debug("query %s completed in %.3fs", request_id, elapsed)
        return self._to_result(response, request_id, elapsed)

    def command(
        self,
        kql: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: int | None = None,
        client_request_id: str | None = None,
    ) -> QueryResult:
        """Run a control command, meaning any statement beginning with a dot.

        Most control commands take no parameters, but those carrying an embedded
        query — ``.delete table T records <| ...`` and ``.set-or-replace`` among
        them — resolve declared parameters from the request properties. Passing
        ``parameters`` keeps values out of the command text there too.

        Every identifier reaching this method must already have passed
        :func:`validate_identifier`.
        """
        stripped = kql.lstrip()
        if not stripped.startswith("."):
            raise AdxQueryError("command() expects a control command starting with '.'")
        properties, request_id = self._request_properties(
            parameters, timeout_seconds=timeout_seconds, client_request_id=client_request_id
        )
        started = time.monotonic()
        deadline = started + (timeout_seconds or self._config.query_timeout_seconds)

        response = call_with_retry(
            lambda: self.raw.execute_mgmt(self._config.database, stripped, properties),
            max_retries=self._config.max_retries,
            base=self._config.backoff_base_seconds,
            cap=self._config.backoff_cap_seconds,
            deadline=deadline,
            description=f"command {request_id}",
        )
        elapsed = time.monotonic() - started
        LOGGER.debug("command %s completed in %.3fs", request_id, elapsed)
        return self._to_result(response, request_id, elapsed)

    # ------------------------------------------------------------ convenience

    def scalar(self, kql: str, parameters: Mapping[str, Any] | None = None, default: Any = None) -> Any:
        """First cell of the first row of ``kql``."""
        return self.query(kql, parameters).scalar(default)

    def iter_pages(
        self,
        kql: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        page_size: int = 10_000,
        order_by: Sequence[str] = ("source_time asc", "resource_id asc"),
    ) -> Iterator[QueryResult]:
        """Page a large result deterministically.

        Kusto has no cursor. Pages are cut with ``serialize`` plus a row number,
        which requires a total order — hence the explicit ``order_by``. Without
        one, page boundaries are not reproducible.
        """
        if page_size <= 0:
            raise AdxQueryError("page_size must be positive")
        for clause in order_by:
            column = clause.split()[0]
            validate_identifier(column, kind="order column")
        ordering = ", ".join(order_by)
        offset = 0
        while True:
            paged = (
                f"{kql}\n| order by {ordering}\n| serialize _rn = row_number()\n"
                f"| where _rn > {offset} and _rn <= {offset + page_size}\n| project-away _rn"
            )
            page = self.query(paged, parameters)
            if page.is_empty:
                return
            yield page
            if len(page) < page_size:
                return
            offset += page_size

    def ping(self) -> bool:
        """True when the cluster answers a trivial query."""
        return self.query("print ping = 1").scalar() == 1
