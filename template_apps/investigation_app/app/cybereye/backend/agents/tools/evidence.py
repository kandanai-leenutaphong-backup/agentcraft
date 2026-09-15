"""Purpose-built retrieval of cited rows behind a scanner situation."""

from __future__ import annotations

from typing import Any

from ...models import ScanRequest
from .base import bind, evidence_query, ToolContext, WINDOW_PROPERTIES, agent_tool, object_schema, parse_window, query_envelope


@agent_tool(
    name="get_situation_evidence",
    datasource="adx",
    category="situation_evidence",
    description=bind("""
Return bounded {TABLE} rows cited by one deterministic scanner situation.
Call after scan_situations when the question asks why a situation exists; do not
replace this with arbitrary KQL.
"""),
    parameters=object_schema({
        "situation_id": {"type": "string", "minLength": 1, "description": "Situation id returned by scan_situations."},
        **WINDOW_PROPERTIES,
    }, ["situation_id", "start", "end"]),
)
def get_situation_evidence(context: ToolContext, *, situation_id: str, start: str,
                           end: str) -> dict[str, Any]:
    lower, upper = parse_window(start, end)
    scan = context.scanner.scan(ScanRequest(start=lower, end=upper))
    situation = next((item for item in scan.situations if item.situation_id == situation_id), None)
    if situation is None:
        return {
            "tool": "get_situation_evidence",
            "category": "not_found",
            "scope": {"situation_id": situation_id, "start": start, "end": end, "row_count": 0},
            "columns": [], "rows": [], "truncated": False,
            "historical_replay": True, "fallback": False,
        }
    ids = list(dict.fromkeys(rid for pattern in situation.patterns for rid in pattern.evidence_ids))[:32]
    if not ids:
        return {
            "tool": "get_situation_evidence", "category": "empty_evidence",
            "scope": {"situation_id": situation_id, "start": start, "end": end, "row_count": 0},
            "columns": [], "rows": [], "truncated": False,
            "historical_replay": True, "fallback": False,
        }
    names = [f"rid{index}" for index in range(len(ids))]
    query, params = evidence_query(ids)
    result = context.adx.parameterized(query, params, 100)
    return query_envelope(
        "get_situation_evidence", "cited_evidence", result,
        {"situation_id": situation_id, "start": start, "end": end},
    )
