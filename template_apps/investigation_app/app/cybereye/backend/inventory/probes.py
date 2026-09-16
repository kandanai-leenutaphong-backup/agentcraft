"""One probe per connector: what a source says about itself, and a preview of it.

A probe is the seam between the domain-blind inventory component and this
deployment's actual stores. It is handed a declared source, reads it, and
returns a status — never an exception, because one dark source must not take
its siblings' listing with it.

Every read here is bounded and read-only. There is no query parameter, no
filter and no write verb: the queries are composed from coordinates the
manifest declared and a row bound the route already clamped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from azdata import AsyncTransport, ConnectorConfig, Limits, OperationResult, Policy, QueryRequest, ResourceAddress, SchemaRequest, connect
from resource_explorer.content import (
    ContentBounds,
    ContentResult,
    DiscoveryStatus,
    GraphReader,
    GraphTarget,
    classify_discovery_failure,
    collected_now,
    content_failure,
    normalize_sample,
    ContentPayload,
)
from resource_explorer import InventorySource, ProbeReport

from ..config import settings
from ..data import GraphService, GraphUnavailable

logger = logging.getLogger(__name__)

#: One probe's budget. Shorter than the app's query timeout: a metadata read
#: that is slower than this is a dark branch worth reporting, not worth waiting
#: for behind a click.
PROBE_TIMEOUT_SECS = 20.0


def _classify(exc: BaseException) -> tuple[DiscoveryStatus, str]:
    """Classify a failure, looking through a wrapper at what actually happened.

    `GraphService` re-raises every driver failure as `GraphUnavailable`, which
    on its own is indistinguishable from a missing role. The original is kept
    as `__cause__`, and that is the exception the degradation table can read.
    """
    return classify_discovery_failure(exc.__cause__ or exc)


class _ProbeFailure(Exception):
    def __init__(self, status: DiscoveryStatus, code: str):
        self.status, self.code = status, code
        super().__init__(code)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {name: _plain(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _rows(result: OperationResult, *, allow_bound: bool = False) -> list[dict[str, Any]]:
    if result.status != "success" or result.errors:
        code = result.errors[0].code if result.errors else result.status
        status = ("forbidden" if result.status == "denied" else "unreachable"
                  if code.startswith(("transport_", "deadline_")) else "unavailable")
        raise _ProbeFailure(status, code)
    if not allow_bound and result.truncated:
        raise _ProbeFailure("unavailable", "incomplete_result")
    if result.service == "adx" and len(result.metadata.get("columns", ())) != 1:
        raise _ProbeFailure("unavailable", "multiple_or_missing_primary_tables")
    rows = []
    for item in result.items:
        if item.status != "success" or item.error or item.content is None or not isinstance(item.content.data, Mapping):
            raise _ProbeFailure("unavailable", "invalid_result_item")
        rows.append(_plain(item.content.data))
    return rows


def _sample(service: str, rows: list[dict[str, Any]], *, limit: int, maximum_bytes: int,
            columns=(), bounded=False) -> ContentResult:
    sample = normalize_sample(rows, max_rows=limit, max_bytes=maximum_bytes)
    kept, names, notes = list(sample.rows), list(sample.columns or columns), list(sample.notes)
    if len(names) > 512:
        notes.append(f"{len(names) - 512} column(s) beyond the first 512 are not shown")
        names = names[:512]
    if bounded:
        notes.append("canonical result is bounded; additional content is not in this sample")

    def size():
        return len(json.dumps({"rows": kept, "columns": names, "notes": notes},
                              ensure_ascii=False, allow_nan=False).encode("utf-8"))

    if size() > maximum_bytes:
        notes.append(f"byte limit {maximum_bytes}; trailing rows omitted")
        while kept and size() > maximum_bytes:
            kept.pop()
        if size() > maximum_bytes:
            raise _ProbeFailure("unavailable", "sample_metadata_byte_limit")
    truncated = sample.truncated or bool(notes)
    return ContentResult(service=service, kind="rows" if service == "adx" else "documents",
                         status="ok" if kept or truncated else "empty", truncated=truncated,
                         payload=ContentPayload(form="rows", media_type="application/json", rows=tuple(kept),
                                                columns=tuple(names), notes=tuple(notes), size_bytes=len(kept)),
                         collected_at=collected_now())


class _CanonicalProbe:
    connector: str

    def __init__(self, *, credential_provider: Callable[[], Any] | None = None,
                 policy: Policy | None = None, transport: AsyncTransport | None = None) -> None:
        grants = {"query"} if self.connector == "adx" else {"query", "schema.read"}
        self._policy = policy or Policy(f"inventory-{self.connector}", grants=grants, max_concurrency=1,
                                       limits=Limits(timeout_seconds=PROBE_TIMEOUT_SECS, max_attempts=1))
        if (not self._policy.grants <= grants or self._policy.max_concurrency != 1
                or self._policy.limits.max_attempts != 1 or self._policy.limits.timeout_seconds > 20
                or self._policy.limits.max_items > 100 or self._policy.limits.max_output_bytes > 1_048_576):
            raise ValueError("invalid_catalogue_read_policy")
        self._credential_provider, self._transport = credential_provider, transport
        self._clients: dict[tuple[Any, ...], Any] = {}
        self._lock = asyncio.Lock()
        self._loop = None
        self._closed = False
        self._metrics = {"submitted": 0, "completed": 0, "known_attempts": 0,
                         "unknown_attempt_operations": 0, "operations": {"query": 0, "schema": 0}, "sources": {}}

    def describe(self) -> dict[str, Any]:
        return {"transport": "azdata-native", "closed": self._closed, "metrics": _plain(self._metrics)}

    async def _operation(self, client, request: QueryRequest | SchemaRequest, source_id: str):
        metrics = self._metrics
        source = metrics["sources"].setdefault(source_id, {"known_attempts": 0, "unknown_attempt_operations": 0})
        operation = "query" if isinstance(request, QueryRequest) else "schema"
        metrics["submitted"] += 1
        metrics["operations"][operation] += 1
        result = None
        try:
            result = await client.query(request) if operation == "query" else await client.schema(request)
            return result
        finally:
            metrics["completed"] += 1
            attempts = result.metrics.get("attempts") if result is not None else None
            if type(attempts) is int and attempts >= 0:
                metrics["known_attempts"] += attempts
                source["known_attempts"] += attempts
            else:
                metrics["unknown_attempt_operations"] += 1
                source["unknown_attempt_operations"] += 1

    def _client(self, config: ConnectorConfig):
        if self._closed:
            raise _ProbeFailure("unavailable", "probe_closed")
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise _ProbeFailure("unavailable", "probe_loop_mismatch")
        if self._credential_provider is None:
            raise _ProbeFailure("unconfigured", "credential_not_configured")
        credential = self._credential_provider()
        if credential is None or not callable(getattr(credential, "get_token", None)):
            raise _ProbeFailure("unconfigured", "credential_not_configured")
        key = (config.endpoint, tuple(config.target.coordinates.items()), id(credential))
        if key not in self._clients:
            self._clients[key] = connect(self.connector, config, credential=credential,
                                         policy=self._policy, transport=self._transport)
        self._loop = loop
        return self._clients[key]

    def _limits(self, deadline: float, rows: int) -> Limits:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _ProbeFailure("unreachable", "metadata_deadline")
        return replace(self._policy.limits, timeout_seconds=min(remaining, self._policy.limits.timeout_seconds), max_items=rows)

    async def aclose(self) -> None:
        self._closed = True
        async with self._lock:
            clients, self._clients = self._clients, {}
            for client in clients.values():
                await client.aclose()


class AdxProbe(_CanonicalProbe):
    """Count, ordinal schema and bounded preview through public canonical queries."""

    connector = "adx"

    @staticmethod
    def _config(source: InventorySource) -> ConnectorConfig:
        coordinates = source.binding.coordinates
        if not all(coordinates.get(name) for name in ("endpoint", "database", "table")):
            raise _ProbeFailure("unconfigured", "adx_coordinates_not_configured")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", coordinates[name]) for name in ("database", "table")):
            raise _ProbeFailure("unavailable", "invalid_table_identifier")
        return ConnectorConfig(coordinates["endpoint"], ResourceAddress({
            "database": coordinates["database"], "table": coordinates["table"]}),
            (urlsplit(coordinates["endpoint"]).hostname or "",))

    async def metadata(self, source: InventorySource) -> ProbeReport:
        metrics, schema, status, detail = {}, (), "ok", ""
        deadline = time.monotonic() + self._policy.limits.timeout_seconds
        try:
            config = self._config(source)
            table = config.target.coordinates["table"]
            async with asyncio.timeout(self._policy.limits.timeout_seconds), self._lock:
                client = self._client(config)
                count_request = QueryRequest(dialect="kql", expression=f'["{table}"] | count', limits=self._limits(deadline, 1))
                count_rows = _rows(await self._operation(client, count_request, source.source_id))
                count = count_rows[0].get("Count") if len(count_rows) == 1 else None
                if type(count) is not int or count < 0:
                    raise _ProbeFailure("unavailable", "count_unknown")
                metrics["row_count"] = count
                expression = (f'["{table}"] | getschema | order by ColumnOrdinal asc\n'
                              '| summarize fields=make_list(bag_pack("name", ColumnName, "type", coalesce(ColumnType, DataType))), field_count=count()')
                schema_request = QueryRequest(dialect="kql", expression=expression, limits=self._limits(deadline, 1))
                schema_rows = _rows(await self._operation(client, schema_request, source.source_id))
                if len(schema_rows) != 1:
                    raise _ProbeFailure("unavailable", "invalid_schema")
                fields, count = schema_rows[0].get("fields"), schema_rows[0].get("field_count")
                if isinstance(fields, str):
                    fields = json.loads(fields)
                if (not isinstance(fields, list) or type(count) is not int or count != len(fields)
                        or any(not isinstance(field, dict) or set(field) != {"name", "type"}
                               or not all(isinstance(value, str) and value for value in field.values()) for field in fields)
                        or len({field["name"] for field in fields}) != count):
                    raise _ProbeFailure("unavailable", "invalid_schema")
                schema = tuple(fields)
                metrics["column_count"] = count
        except _ProbeFailure as error:
            status, detail = error.status, error.code
        except TimeoutError:
            status, detail = "unreachable", "metadata_deadline"
        except Exception:
            status, detail = "unavailable", "invalid_canonical_metadata"
        return ProbeReport(status=status, metrics=metrics, schema_fields=schema, detail=detail,
                           total_rows=metrics.get("row_count"), collected_at=collected_now())

    async def preview(self, source: InventorySource, *, limit: int) -> ContentResult:
        try:
            if type(limit) is not int or not 1 <= limit <= min(100, self._policy.limits.max_items):
                raise _ProbeFailure("unavailable", "invalid_limit")
            config = self._config(source)
            deadline = time.monotonic() + self._policy.limits.timeout_seconds
            async with asyncio.timeout(self._policy.limits.timeout_seconds), self._lock:
                client = self._client(config)
                request = QueryRequest(dialect="kql", expression=f'["{config.target.coordinates["table"]}"] | take {limit}',
                                       limits=self._limits(deadline, limit))
                result = await self._operation(client, request, source.source_id)
                rows = _rows(result, allow_bound=True)
                columns = tuple(field["name"] for field in result.metadata["columns"][0])
                return _sample("adx", rows, limit=limit, maximum_bytes=self._policy.limits.max_output_bytes,
                               columns=columns, bounded=result.truncated)
        except _ProbeFailure as error:
            status, detail = error.status, error.code
        except TimeoutError:
            status, detail = "unreachable", "preview_deadline"
        except Exception:
            status, detail = "unavailable", "invalid_canonical_preview"
        return content_failure(service="adx", kind="rows", status=status, detail=detail)


class GremlinProbe:
    """One Cosmos DB for Gremlin graph: its element counts and a raw sample.

    Reuses `GraphService` rather than opening a second Gremlin path. Cosmos has
    no Entra data plane, so the connection needs an account key; the one proven
    way this deployment obtains one is an ARM `readonlykeys` read performed at
    runtime with the ambient identity, which `GraphService` already does. The
    key stays in that object's memory and is never logged, imaged or returned.

    **One account.** The ARM lookup needs a subscription and a resource group,
    and this deployment declares exactly one pair — `GREMLIN_SUBSCRIPTION_ID`
    and `GREMLIN_RESOURCE_GROUP`, for the account in `GREMLIN_ACCOUNT`. A
    source naming any other account is refused here, before a client exists,
    rather than being served the configured account's data under the declared
    account's name. Supporting a second account means declaring its own ARM
    coordinates, which the manifest deliberately does not carry.

    A graph's own vocabulary is whatever wrote it. Nothing here applies one
    graph's labels to another.
    """

    connector = "gremlin"

    def __init__(
        self,
        *,
        service_factory: Callable[[GraphTarget], GraphService] | None = None,
        deployment_account: str | None = None,
    ) -> None:
        self._factory = service_factory or (
            lambda target: GraphService(
                account=target.account, database=target.database, graph=target.graph
            )
        )
        self._account = (
            settings.graph_account if deployment_account is None else deployment_account
        )
        self._services: dict[tuple[str, str, str], GraphService] = {}
        self._reader = GraphReader(resolve=self._resolve)

    def _unsupported(self, target: GraphTarget) -> str:
        """Why this target cannot be read, or "" when it can. No client is built."""
        if not self._account:
            return (
                "no Cosmos account is configured for this deployment, so no "
                "read-only key can be resolved: set GREMLIN_ACCOUNT"
            )
        if target.account != self._account:
            return (
                f"this deployment resolves a Cosmos read-only key for account "
                f"{self._account!r} only; this source declares {target.account!r}. "
                "Reading it would need that account's own subscription and "
                "resource group, which are not declared."
            )
        return ""

    def _service(self, target: GraphTarget) -> GraphService:
        # Keyed on the whole target. Two accounts with the same database and
        # graph name are two different graphs and must not share an instance.
        key = (target.account, target.database, target.graph)
        service = self._services.get(key)
        if service is None:
            service = self._factory(target)
            self._services[key] = service
        return service

    def _resolve(self, target: GraphTarget) -> GraphService | None:
        if not target.is_complete or self._unsupported(target):
            return None
        return self._service(target)

    @staticmethod
    def _target(source: InventorySource) -> GraphTarget:
        coordinates = source.binding.coordinates
        return GraphTarget(
            account=coordinates.get("account", ""),
            database=coordinates.get("database", ""),
            graph=coordinates.get("graph", ""),
        )

    async def metadata(self, source: InventorySource) -> ProbeReport:
        target = self._target(source)
        if not target.is_complete:
            return ProbeReport(
                status="unconfigured",
                detail="graph read not configured: account, database and graph",
                collected_at=collected_now(),
            )
        unsupported = self._unsupported(target)
        if unsupported:
            return ProbeReport(
                status="unconfigured",
                detail=unsupported,
                collected_at=collected_now(),
            )
        service = self._service(target)

        def counts() -> dict[str, int]:
            return {
                "vertices": int(service.element_count("vertices")),
                "edges": int(service.element_count("edges")),
            }

        try:
            observed = await asyncio.wait_for(
                asyncio.to_thread(counts), PROBE_TIMEOUT_SECS
            )
        except (asyncio.TimeoutError, TimeoutError):
            return ProbeReport(
                status="unreachable",
                detail=f"graph metadata exceeded {PROBE_TIMEOUT_SECS}s",
                collected_at=collected_now(),
            )
        except GraphUnavailable as exc:
            message = str(exc)
            if message.startswith("unset:") or "not configured" in message:
                status: DiscoveryStatus = "unconfigured"
            else:
                status, _ = _classify(exc)
            return ProbeReport(
                status=status, detail=message, collected_at=collected_now()
            )
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a status
            status, detail = _classify(exc)
            return ProbeReport(status=status, detail=detail, collected_at=collected_now())

        return ProbeReport(
            status="ok" if observed["vertices"] or observed["edges"] else "empty",
            metrics=observed,
            total_rows=observed["vertices"],
            collected_at=collected_now(),
        )

    async def preview(self, source: InventorySource, *, limit: int) -> ContentResult:
        target = self._target(source)
        unsupported = target.is_complete and self._unsupported(target)
        if unsupported:
            return content_failure(
                service="gremlin",
                kind="vertices",
                status="unconfigured",
                detail=unsupported,
            )
        return await self._reader.elements(
            target=target,
            element="vertices",
            bounds=ContentBounds(max_rows=limit, timeout_secs=PROBE_TIMEOUT_SECS),
        )


class SearchProbe(_CanonicalProbe):
    """Count, ordered index schema and bounded SDK-shaped document previews."""

    connector = "search"

    @staticmethod
    def _config(source: InventorySource) -> ConnectorConfig:
        coordinates = source.binding.coordinates
        endpoint, index = coordinates.get("endpoint", ""), coordinates.get("index", "")
        if not endpoint or not index:
            raise _ProbeFailure("unconfigured", "index_coordinates_not_configured")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", index) or len(index) > 128:
            raise _ProbeFailure("unavailable", "invalid_index_identifier")
        return ConnectorConfig(endpoint, ResourceAddress({"index": index}), (urlsplit(endpoint).hostname or "",))

    async def metadata(self, source: InventorySource) -> ProbeReport:
        metrics, schema, status, detail = {}, (), "ok", ""
        deadline = time.monotonic() + self._policy.limits.timeout_seconds
        try:
            config = self._config(source)
            async with asyncio.timeout(self._policy.limits.timeout_seconds), self._lock:
                client = self._client(config)
                request = QueryRequest(dialect="search", expression="*", projection=(config.key_field,),
                                       limits=self._limits(deadline, 1), service_options={"search": {"count": True}})
                result = await self._operation(client, request, source.source_id)
                _rows(result, allow_bound=bool(result.continuation))
                count = result.metadata.get("count")
                if type(count) is not int or count < 0:
                    raise _ProbeFailure("unavailable", "count_unknown")
                metrics["document_count"] = count
                schema_request = SchemaRequest(action="read", limits=self._limits(deadline, 1))
                schema_rows = _rows(await self._operation(client, schema_request, source.source_id))
                fields = schema_rows[0].get("fields") if len(schema_rows) == 1 else None
                if (not isinstance(fields, list) or any(not isinstance(field, dict)
                        or not isinstance(field.get("name"), str) or not field["name"]
                        or not isinstance(field.get("type"), str) for field in fields)
                        or len({field["name"] for field in fields}) != len(fields)):
                    raise _ProbeFailure("unavailable", "invalid_schema")
                schema = tuple({"name": field["name"], "type": field["type"]} for field in fields)
                metrics["column_count"] = len(schema)
        except _ProbeFailure as error:
            status, detail = error.status, error.code
        except TimeoutError:
            status, detail = "unreachable", "metadata_deadline"
        except Exception:
            status, detail = "unavailable", "invalid_canonical_metadata"
        return ProbeReport(status=status, metrics=metrics, schema_fields=schema, detail=detail,
                           total_rows=metrics.get("document_count"), collected_at=collected_now())

    async def preview(self, source: InventorySource, *, limit: int) -> ContentResult:
        try:
            if type(limit) is not int or not 1 <= limit <= min(100, self._policy.limits.max_items):
                raise _ProbeFailure("unavailable", "invalid_limit")
            config = self._config(source)
            deadline = time.monotonic() + self._policy.limits.timeout_seconds
            async with asyncio.timeout(self._policy.limits.timeout_seconds), self._lock:
                client = self._client(config)
                request = QueryRequest(dialect="search", expression="*", limits=self._limits(deadline, limit))
                result = await self._operation(client, request, source.source_id)
                rows = _rows(result, allow_bound=True)
                annotations = ("@search.score", "@search.reranker_score", "@search.highlights", "@search.captions")
                rows = [{**{name: value for name, value in row.items() if name not in annotations},
                         **{name: row.get(name) for name in annotations}} for row in rows]
                return _sample("search", rows, limit=limit, maximum_bytes=self._policy.limits.max_output_bytes,
                               bounded=result.truncated)
        except _ProbeFailure as error:
            status, detail = error.status, error.code
        except TimeoutError:
            status, detail = "unreachable", "preview_deadline"
        except Exception:
            status, detail = "unavailable", "invalid_canonical_preview"
        return content_failure(service="search", kind="documents", status=status, detail=detail)


def default_probes(*, credential_provider: Callable[[], Any] | None = None) -> Mapping[str, Any]:
    """One probe per connector this deployment declares. Built once, at startup."""
    return {
        AdxProbe.connector: AdxProbe(credential_provider=credential_provider),
        GremlinProbe.connector: GremlinProbe(),
        SearchProbe.connector: SearchProbe(credential_provider=credential_provider),
    }


__all__ = [
    "PROBE_TIMEOUT_SECS",
    "AdxProbe",
    "GremlinProbe",
    "SearchProbe",
    "default_probes",
]
