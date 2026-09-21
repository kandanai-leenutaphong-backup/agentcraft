"""Bounded public-source tools. No user-authored query or target input."""

from ...data.telemetry import CosmosTelemetry
from ...models import ScanRequest
from .base import ToolContext, WINDOW_PROPERTIES, agent_tool, object_schema, parse_window, query_envelope


PARTITION = {"type": "string", "pattern": "^scenario-[0-9a-f]{64}$",
             "description": "Exact configured scenario partition returned by list_public_cases."}
ENTITY = {"type": "string", "description": "Exact entity_refs ID from a returned event; never a prose name."}


def telemetry(context: ToolContext) -> CosmosTelemetry:
    if not isinstance(context.adx, CosmosTelemetry):
        raise ValueError("public source profile not selected")
    return context.adx


def envelope(name, rows, partition):
    return {"kind": "cybereye_tool_result", "tool": name, "category": "public_telemetry",
            "scope": {"partition": partition, "row_count": len(rows), "max_rows": 200},
            "rows": rows, "columns": list(rows[0]) if rows else [], "truncated": False,
            "historical_replay": True, "fallback": False}


@agent_tool(name="list_public_cases", category="public_cases", datasource="cosmos",
    description="List bounded public emulation cases and their exact scenario partition. Cases are derived, not victim incidents.",
    parameters=object_schema({}, []))
async def list_public_cases(context: ToolContext):
    service = telemetry(context)
    return envelope("list_public_cases", await service.cases(service.partition), service.partition)


@agent_tool(name="list_public_alarms", category="public_alarms", datasource="cosmos",
    description="Read deterministic derived alarms for one exact public case ID, with source event references.",
    parameters=object_schema({"partition": PARTITION, "case_id": {"type": "string"}}, ["partition", "case_id"]))
async def list_public_alarms(context: ToolContext, *, partition: str, case_id: str):
    return envelope("list_public_alarms", await telemetry(context).alarms(partition, case_id), partition)


@agent_tool(name="get_public_evidence", category="cited_evidence", datasource="cosmos",
    description="Read exact event resource_id citations in one scenario. Returns original source pins, offsets and hashes; no maliciousness inference.",
    parameters=object_schema({"partition": PARTITION, "resource_ids": {
        "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 32}}, ["partition", "resource_ids"]))
async def get_public_evidence(context: ToolContext, *, partition: str, resource_ids: list[str]):
    service = telemetry(context)
    if len(resource_ids) > 32:
        raise ValueError("at most 32 evidence references")
    return query_envelope("get_public_evidence", "cited_evidence",
        service.as_query(await service.evidence(partition, resource_ids)), {"partition": partition})


@agent_tool(name="get_public_entity_activity", category="entity_activity", datasource="cosmos",
    description="Read bounded events for an exact host/user/domain/process ID and a UTC window of at most 48 hours.",
    parameters=object_schema({"partition": PARTITION, "entity_id": ENTITY, **WINDOW_PROPERTIES},
                             ["partition", "entity_id", "start", "end"]))
async def get_public_entity_activity(context: ToolContext, *, partition: str, entity_id: str, start: str, end: str):
    service = telemetry(context)
    lower, upper = parse_window(start, end)
    return query_envelope("get_public_entity_activity", "entity_activity",
        service.as_query(await service.events(partition, lower, upper, entity_id)),
        {"partition": partition, "entity_id": entity_id, "start": start, "end": end})


@agent_tool(name="get_public_graph_entity", category="entity_graph", datasource=("cosmos", "gremlin"),
    description="Read one exact entity ID and its one-hop graph, checked against the same scenario telemetry source and evidence.",
    parameters=object_schema({"partition": PARTITION, "entity_id": ENTITY}, ["partition", "entity_id"]))
async def get_public_graph_entity(context: ToolContext, *, partition: str, entity_id: str):
    service = telemetry(context)
    service._partition(partition)
    if context.graph is None:
        raise ValueError("public graph unavailable")
    return await context.graph.neighbourhood(entity_id)


@agent_tool(name="scan_public_situations", category="situation_scan", datasource="cosmos",
    description="Scan actual public Sysmon events for the package's deterministic rundll32 Temp DLL pattern. Other legacy rules are unsupported.",
    parameters=object_schema(WINDOW_PROPERTIES, ["start", "end"]))
async def scan_public_situations(context: ToolContext, *, start: str, end: str):
    telemetry(context)
    lower, upper = parse_window(start, end)
    return (await context.scanner.scan_async(ScanRequest(start=lower, end=upper))).model_dump(mode="json")