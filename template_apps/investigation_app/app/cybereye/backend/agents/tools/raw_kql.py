"""Explicitly subordinate model-authored KQL fallback."""

from __future__ import annotations

import logging
from typing import Any

from ...config import settings
from .base import bind, ToolContext, agent_tool, object_schema, query_envelope

logger = logging.getLogger(__name__)


@agent_tool(
    name="query_events_kql",
    datasource="adx",
    category="raw_kql_fallback",
    fallback=True,
    description=bind("""
LAST-RESORT FALLBACK: run one bounded, read-only model-authored KQL pipeline rooted
at {TABLE}. Use only when no purpose-built tool covers the analyst's actual
question. Never use it merely to reproduce scanner, situation evidence, host,
authentication, privileged-session, or DNS activity tools. Explain the uncovered
shape in the query's purpose through projected categorical fields.
"""),
    parameters=object_schema({
        "query": {"type": "string", "minLength": 1, "maxLength": 12000, "description": bind("One read-only {TABLE} KQL pipeline for a shape not covered by a purpose-built tool.")},
        "max_rows": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Bounded fallback result row cap."},
    }, ["query", "max_rows"]),
)
def query_events_kql(context: ToolContext, *, query: str, max_rows: int) -> dict[str, Any]:
    logger.warning("cybereye.agent.raw_kql_fallback rows=%d", max_rows)
    result = context.adx.query(query, max_rows)
    return query_envelope(
        "query_events_kql", "raw_kql_fallback", result,
        {"reason": "no_purpose_built_tool_fit"}, fallback=True,
    )
