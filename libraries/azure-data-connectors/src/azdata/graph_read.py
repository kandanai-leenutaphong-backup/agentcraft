"""Synchronous, read-only Cosmos graph access with host-supplied identity."""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .adapters.gremlin import read_traversal
from .execution import json_bytes
from .transport import OperationFault

DROPPED_CONNECTION = (
    "connection was already closed", "connection is already closed", "websocket",
    "connection closed", "connection reset", "broken pipe", "cannot write to closing transport",
    "going away", "socket is closed", "no connection", "connection aborted",
)


class GraphUnavailable(RuntimeError):
    """A graph read was refused, incomplete, or unavailable."""


@dataclass(frozen=True)
class GraphReadConfig:
    account: str
    database: str
    graph: str
    subscription: str = ""
    resource_group: str = ""
    timeout_seconds: float = 60.0
    max_items: int = 2500
    max_output_bytes: int = 4_194_304

    def __post_init__(self):
        for value in (self.account, self.database, self.graph):
            if value and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", value):
                raise ValueError("invalid_graph_coordinate")
        if self.account and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", self.account):
            raise ValueError("invalid_graph_account")
        if (isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds)
                or not 0 < self.timeout_seconds <= 300
                or type(self.max_items) is not int or not 1 <= self.max_items <= 10_000
                or type(self.max_output_bytes) is not int or not 1 <= self.max_output_bytes <= 16_777_216):
            raise ValueError("invalid_graph_read_limits")


def scalar(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if len(value) == 1 else value
    return value


def flatten_element(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"value": row}
    return {str(key): scalar(value) for key, value in row.items()}


def flatten_edge(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"value": row}
    return {**flatten_element(row.get("e", {})),
            "outV": str(row.get("from", "")), "inV": str(row.get("to", ""))}


class GremlinReader:
    def __init__(self, config: GraphReadConfig, *, credential: Any = None,
                 allow_reads: bool = False, key_provider: Callable[[], str] | None = None,
                 client_factory: Callable[..., Any] | None = None) -> None:
        if type(allow_reads) is not bool:
            raise ValueError("explicit_graph_read_grant_required")
        self.config = config
        self._credential = credential
        self._allow_reads = allow_reads
        self._key_provider = key_provider
        self._client_factory = client_factory
        self._key = ""
        self._client: Any = None
        self._lock = threading.RLock()
        self._closed = False
        self.reconnects = 0

    def describe(self) -> dict[str, Any]:
        return {"account": self.config.account, "database": self.config.database,
                "graph": self.config.graph, "allow_reads": self._allow_reads,
                "auth": "cosmos-read-only-key", "closed": self._closed,
                "reconnects": self.reconnects}

    def _account_key(self) -> str:
        if self._key:
            return self._key
        try:
            if self._key_provider is not None:
                key = self._key_provider()
            else:
                if self._credential is None or not self.config.subscription or not self.config.resource_group:
                    raise GraphUnavailable("graph_identity_or_resource_coordinates_unconfigured")
                from azure.mgmt.cosmosdb import CosmosDBManagementClient

                management = CosmosDBManagementClient(self._credential, self.config.subscription,
                    connection_timeout=self.config.timeout_seconds, read_timeout=self.config.timeout_seconds,
                    retry_total=0)
                try:
                    result = management.database_accounts.list_read_only_keys(
                        self.config.resource_group, self.config.account)
                    key = result.primary_readonly_master_key
                finally:
                    management.close()
        except GraphUnavailable:
            raise
        except Exception as error:
            raise GraphUnavailable("cosmos_read_only_key_unavailable") from error
        if not isinstance(key, str) or not key:
            raise GraphUnavailable("cosmos_read_only_key_absent")
        self._key = key
        return key

    def _client_or_connect(self):
        if self._client is None:
            from gremlin_python.driver.client import Client
            from gremlin_python.driver.serializer import GraphSONSerializersV2d0

            self._client = (self._client_factory or Client)(
                f"wss://{self.config.account}.gremlin.cosmos.azure.com:443/gremlin", "g",
                username=f"/dbs/{self.config.database}/colls/{self.config.graph}",
                password=self._account_key(), message_serializer=GraphSONSerializersV2d0(),
                pool_size=1, max_workers=1,
            )
        return self._client

    def _discard_client(self):
        client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def query(self, expression: str, bindings: Mapping[str, Any] | None = None) -> list[Any]:
        if not self._allow_reads:
            raise GraphUnavailable("graph_read_not_granted")
        if not self.config.account or not self.config.database or not self.config.graph:
            raise GraphUnavailable("graph_target_unconfigured")
        try:
            traversal = read_traversal(expression, dict(bindings or {}))
        except OperationFault as error:
            raise GraphUnavailable(error.code) from None
        traversal += f".limit({self.config.max_items + 1})"
        with self._lock:
            if self._closed:
                raise GraphUnavailable("graph_reader_closed")
            deadline = time.monotonic() + self.config.timeout_seconds
            for attempt in (0, 1):
                try:
                    client = self._client_or_connect()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    rows = client.submit(traversal, request_options={
                        "evaluationTimeout": max(1, int(remaining * 1000)),
                        "batchSize": self.config.max_items,
                    }).all().result(timeout=remaining)
                    if not isinstance(rows, list) or len(rows) > self.config.max_items:
                        raise GraphUnavailable("gremlin_result_limit_or_shape")
                    if len(json_bytes(rows)) > self.config.max_output_bytes:
                        raise GraphUnavailable("gremlin_output_byte_limit")
                    return rows
                except GraphUnavailable:
                    raise
                except Exception as error:
                    dropped = any(marker in str(error).casefold() for marker in DROPPED_CONNECTION)
                    self._discard_client()
                    if attempt == 0 and dropped:
                        self.reconnects += 1
                        continue
                    code = "gremlin_connection_closed" if dropped else "gremlin_query_failed"
                    raise GraphUnavailable(code) from error
        raise GraphUnavailable("gremlin_query_failed")

    def element_count(self, element: str) -> int:
        if element not in {"vertices", "edges"}:
            raise ValueError("unknown_graph_element")
        rows = self.query("g.E().count()" if element == "edges" else "g.V().count()")
        return int(rows[0]) if rows else 0

    def sample(self, element: str, limit: int) -> list[dict[str, Any]]:
        if element not in {"vertices", "edges"}:
            raise ValueError("unknown_graph_element")
        bounded = max(1, min(int(limit), 100, self.config.max_items))
        if element == "edges":
            rows = self.query(f"g.E().limit({bounded}).project('e','from','to')"
                              ".by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())")
            return [flatten_edge(row) for row in rows]
        return [flatten_element(row) for row in self.query(f"g.V().limit({bounded}).valueMap(true)")]

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._discard_client()
                self._key = ""

    def __enter__(self):
        if self._closed:
            raise GraphUnavailable("graph_reader_closed")
        return self

    def __exit__(self, *exception):
        self.close()


__all__ = ["GraphReadConfig", "GremlinReader", "GraphUnavailable", "scalar", "flatten_element", "flatten_edge"]