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
import logging
from collections.abc import Callable, Mapping
from typing import Any

from template_foundations.azure_llm import azure_credential
from app.components.data_connector_library import (
    ContentBounds,
    ContentResult,
    DiscoveryStatus,
    GraphReader,
    GraphTarget,
    KustoReader,
    KustoTableInspector,
    SearchReader,
    bounded_content,
    classify_discovery_failure,
    collected_now,
    content_failure,
    load,
    normalize_rows,
    ContentPayload,
)
from app.components.resource_explorer import InventorySource, ProbeReport

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


class AdxProbe:
    """One Azure Data Explorer table: its count, its schema, and a row sample."""

    connector = "adx"

    def __init__(self, *, credential_provider: Callable[[], Any] | None = None) -> None:
        provider = credential_provider or azure_credential
        self._reader = KustoReader(credential_provider=provider)
        self._inspector = KustoTableInspector(credential_provider=provider)

    def close(self) -> None:
        self._reader.close()
        self._inspector.close()

    async def metadata(self, source: InventorySource) -> ProbeReport:
        coordinates = source.binding.coordinates
        result, facts = await self._inspector.facts(
            query_uri=coordinates.get("endpoint", ""),
            database=coordinates.get("database", ""),
            table=coordinates.get("table", ""),
            bounds=ContentBounds(max_rows=1, timeout_secs=PROBE_TIMEOUT_SECS),
        )
        metrics: dict[str, Any] = {}
        if facts.row_count is not None:
            metrics["row_count"] = facts.row_count
        if facts.columns:
            metrics["column_count"] = len(facts.columns)
        return ProbeReport(
            status=result.status,
            metrics=metrics,
            schema_fields=facts.columns,
            detail=result.detail,
            total_rows=facts.row_count,
            collected_at=result.collected_at or collected_now(),
        )

    async def preview(self, source: InventorySource, *, limit: int) -> ContentResult:
        coordinates = source.binding.coordinates
        return await self._reader.rows(
            query_uri=coordinates.get("endpoint", ""),
            database=coordinates.get("database", ""),
            table=coordinates.get("table", ""),
            bounds=ContentBounds(max_rows=limit, timeout_secs=PROBE_TIMEOUT_SECS),
        )


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


class SearchProbe:
    """One Azure AI Search index: its document count and a document sample.

    Nothing is probed when the index is not configured — the service reports
    `unconfigured` and names the keys without a client ever being built. There
    is no fallback to a local corpus: BM25 files on disk are not an index, and
    labelling them as one would be the exact misreport this slot exists to
    avoid.
    """

    connector = "search"

    def __init__(self, *, credential_provider: Callable[[], Any] | None = None) -> None:
        self._credential_provider = credential_provider or azure_credential
        self._reader = SearchReader(credential_provider=self._credential_provider)
        self._clients: dict[tuple[str, str], Any] = {}

    def _client(self, endpoint: str, index: str) -> Any:
        client = self._clients.get((endpoint, index))
        if client is None:
            sdk = load("azure.search.documents", dist="azure-search-documents>=11.5")
            client = sdk.SearchClient(
                endpoint=endpoint,
                index_name=index,
                credential=self._credential_provider(),
            )
            self._clients[(endpoint, index)] = client
        return client

    async def metadata(self, source: InventorySource) -> ProbeReport:
        coordinates = source.binding.coordinates
        endpoint = coordinates.get("endpoint", "")
        index = coordinates.get("index", "")
        if not endpoint or not index:
            return ProbeReport(
                status="unconfigured",
                detail="index read not configured: endpoint and index",
                collected_at=collected_now(),
            )

        def fetch() -> tuple[ContentPayload, bool]:
            count = int(self._client(endpoint, index).get_document_count())
            rows, columns, _ = normalize_rows(
                [{"document_count": count}], max_rows=1
            )
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=rows,
                    columns=columns,
                    size_bytes=1,
                ),
                False,
            )

        result = await bounded_content(
            service="search",
            kind="facts",
            bounds=ContentBounds(max_rows=1, timeout_secs=PROBE_TIMEOUT_SECS),
            fetch=fetch,
        )
        count = None
        if result.status == "ok" and result.payload.rows:
            raw = result.payload.rows[0].get("document_count")
            count = int(raw) if isinstance(raw, int) else None
        return ProbeReport(
            status=result.status,
            metrics={"document_count": count} if count is not None else {},
            detail=result.detail,
            total_rows=count,
            collected_at=result.collected_at or collected_now(),
        )

    async def preview(self, source: InventorySource, *, limit: int) -> ContentResult:
        coordinates = source.binding.coordinates
        endpoint = coordinates.get("endpoint", "")
        index = coordinates.get("index", "")
        if not endpoint or not index:
            return content_failure(
                service="search",
                kind="documents",
                status="unconfigured",
                detail="index read not configured: endpoint and index",
            )
        return await self._reader.documents(
            endpoint=endpoint,
            index=index,
            bounds=ContentBounds(max_rows=limit, timeout_secs=PROBE_TIMEOUT_SECS),
        )


def default_probes() -> Mapping[str, Any]:
    """One probe per connector this deployment declares. Built once, at startup."""
    return {
        AdxProbe.connector: AdxProbe(),
        GremlinProbe.connector: GremlinProbe(),
        SearchProbe.connector: SearchProbe(),
    }


__all__ = [
    "PROBE_TIMEOUT_SECS",
    "AdxProbe",
    "GremlinProbe",
    "SearchProbe",
    "default_probes",
]
