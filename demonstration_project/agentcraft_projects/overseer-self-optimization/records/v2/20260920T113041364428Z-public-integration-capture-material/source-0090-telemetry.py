"""Public emulation telemetry through the public async azdata contract."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit

from azdata import ConnectorConfig, Limits, OperationMetrics, Policy, QueryRequest, ResourceAddress, connect

from ..models import QueryResponse


class CosmosTelemetry:
    profile = "public-cosmos"

    def __init__(self, *, endpoint: str, database: str, container: str, partition: str,
                 source: dict[str, str], credential: Any, transport: Any = None,
                 max_rows: int = 200) -> None:
        if not re.fullmatch(r"scenario-[0-9a-f]{64}", partition):
            raise ValueError("explicit scenario partition required")
        required = ("source_id", "scenario_id", "commit", "sha256", "source_path", "source_url")
        if any(not isinstance(source.get(key), str) or not source[key] for key in required):
            raise ValueError("complete public source pin required")
        if type(max_rows) is not int or not 1 <= max_rows <= 200:
            raise ValueError("public telemetry maximum must be 1..200")
        self.partition = partition
        self.source = {key: source[key] for key in required}
        self.max_rows = max_rows
        self.connector = connect("cosmos", ConnectorConfig(endpoint,
            ResourceAddress({"database": database, "container": container}),
            (urlsplit(endpoint).hostname or "",), partition_key_field="partition"),
            credential=credential, transport=transport,
            policy=Policy("investigation:public-telemetry", grants={"query", "read"},
                          limits=Limits(max_items=max_rows + 1, max_output_bytes=1_048_576,
                                        timeout_seconds=30, max_attempts=1)))
        self.metrics = OperationMetrics()

    async def aclose(self) -> None:
        await self.connector.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            cases = await self.cases(self.partition)
            return {"provider": "cosmos", "profile": self.profile, "reachable": True,
                    "partition": self.partition, "cases": len(cases), "source": self.source}
        except (RuntimeError, ValueError):
            return {"provider": "cosmos", "profile": self.profile, "reachable": False,
                    "detail": "public telemetry unavailable"}

    def library_identity(self) -> dict[str, Any]:
        import azdata
        import importlib.metadata
        return {"distribution": "azdata", "version": importlib.metadata.version("azdata"),
                "import_origin": azdata.__file__, "profile": self.profile,
                "query_metrics": self.metrics.snapshot()}

    def _partition(self, partition: str) -> None:
        if partition != self.partition:
            raise ValueError("foreign scenario refused")

    def _document(self, document: dict[str, Any]) -> dict[str, Any]:
        if (document.get("partition") != self.partition
                or any(document.get("source", {}).get(key) != value for key, value in self.source.items())):
            raise ValueError("foreign source membership refused")
        kind = document.get("kind")
        if kind not in {"incident", "alarm", "event"}:
            raise ValueError("unknown document kind")
        if not re.fullmatch(kind + r"-[0-9a-f]{64}", document.get("id", "")):
            raise ValueError("invalid document identity")
        prefix = f"{kind}://{self.partition}"
        resource_id = document.get("resource_id", "")
        if not (resource_id == prefix or resource_id.startswith(prefix + "/")):
            raise ValueError("foreign resource identity")
        return document

    async def _select(self, predicate: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        request = QueryRequest(dialect="cosmos-sql",
            expression=f"SELECT TOP {self.max_rows + 1} * FROM c WHERE c.partition = @partition AND {predicate}",
            parameters={"@partition": self.partition, **parameters},
            service_options={"cosmos": {"partition": self.partition}})
        result = await self.metrics.run("query", lambda: self.connector.query(request))
        if result.status != "success":
            raise RuntimeError(f"Cosmos telemetry read failed ({result.status})")
        if result.truncated or result.continuation or len(result.items) > self.max_rows:
            raise ValueError("bounded result incomplete; narrow the event window or entity")
        documents = [self._document(item.content.to_native()) for item in result.items
                     if item.status == "success" and item.content is not None]
        if len(documents) != len(result.items) or len({item["id"] for item in documents}) != len(documents):
            raise ValueError("incomplete or duplicate telemetry result")
        return documents

    async def cases(self, partition: str) -> list[dict[str, Any]]:
        self._partition(partition)
        return await self._select("c.kind = @kind", {"@kind": "incident"})

    async def document(self, partition: str, identifier: str) -> dict[str, Any]:
        self._partition(partition)
        if not re.fullmatch(r"(?:incident|alarm|event)-[0-9a-f]{64}", identifier):
            raise ValueError("explicit Cosmos document ID required")
        documents = await self._select("c.id = @id", {"@id": identifier})
        if len(documents) != 1 or documents[0]["id"] != identifier:
            raise ValueError("unknown document ID")
        return documents[0]

    async def alarms(self, partition: str, case_id: str) -> list[dict[str, Any]]:
        case = await self.document(partition, case_id)
        if case["kind"] != "incident":
            raise ValueError("case ID required")
        alarms = await self._select("c.kind = @kind AND c.incident_id = @case", {
            "@kind": "alarm", "@case": case_id})
        if {item["id"] for item in alarms} != set(case["alarm_refs"]):
            raise ValueError("case alarm membership mismatch")
        return alarms

    async def evidence(self, partition: str, resource_ids: list[str]) -> list[dict[str, Any]]:
        self._partition(partition)
        if not resource_ids or len(resource_ids) > self.max_rows or len(set(resource_ids)) != len(resource_ids):
            raise ValueError("bounded unique evidence IDs required")
        if any(not re.fullmatch(re.escape(f"event://{partition}/") + r"[1-9][0-9]*", value) for value in resource_ids):
            raise ValueError("foreign or invalid evidence reference")
        documents = await self._select("c.kind = @kind AND ARRAY_CONTAINS(@ids, c.resource_id)", {
            "@kind": "event", "@ids": resource_ids})
        if {item["resource_id"] for item in documents} != set(resource_ids):
            raise ValueError("unknown evidence reference")
        return sorted(documents, key=lambda item: (item["timestamp"], item["resource_id"]))

    async def events(self, partition: str, start: datetime, end: datetime,
                     entity_id: str = "") -> list[dict[str, Any]]:
        self._partition(partition)
        if start.tzinfo is None or end.tzinfo is None or not 0 < (end - start).total_seconds() <= 48 * 3600:
            raise ValueError("explicit time-zone window of at most 48 hours required")
        def bound(value: datetime) -> str:
            utc = value.astimezone(timezone.utc)
            return utc.strftime("%Y-%m-%dT%H:%M:%S") + f".{utc.microsecond * 1000:09d}Z"
        lower, upper = bound(start), bound(end)
        predicate = "c.kind = @kind AND c.timestamp >= @start AND c.timestamp <= @end"
        parameters = {"@kind": "event", "@start": lower, "@end": upper}
        if entity_id:
            if not re.fullmatch(r"(?:host|user|domain|process)-[0-9a-f]{64}", entity_id):
                raise ValueError("explicit qualified entity ID required")
            predicate += " AND (c.entity_refs.host = @entity OR c.entity_refs.user = @entity OR c.entity_refs.domain = @entity OR c.entity_refs.process = @entity OR c.entity_refs.parent_process = @entity)"
            parameters["@entity"] = entity_id
        documents = await self._select(predicate, parameters)
        if any(not start <= datetime.fromisoformat(item["timestamp"]) <= end for item in documents):
            raise ValueError("event outside requested time window")
        if entity_id and not documents:
            raise ValueError("unknown entity in the supplied window")
        return sorted(documents, key=lambda item: (item["timestamp"], item["resource_id"]))

    @staticmethod
    def as_query(documents: list[dict[str, Any]]) -> QueryResponse:
        columns = ["timestamp", "resource_id", "id", "partition", "host", "provider", "event_id",
                   "fields", "entity_refs", "source", "label_status"]
        return QueryResponse(columns=columns, rows=[[item.get(key) for key in columns] for item in documents],
            row_count=len(documents), truncated=False, max_rows=200, elapsed_ms=0, client_request_id="public-telemetry")

    async def query(self, *_args: Any, **_kwargs: Any) -> QueryResponse:
        raise ValueError("raw queries unavailable for public Cosmos; use bounded public tools")

    async def parameterized(self, *_args: Any, **_kwargs: Any) -> QueryResponse:
        raise ValueError("KQL unavailable for public Cosmos; use bounded public tools")