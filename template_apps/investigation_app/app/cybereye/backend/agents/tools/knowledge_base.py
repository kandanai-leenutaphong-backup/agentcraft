"""Advisory MITRE ATT&CK detection material, retrieved from Azure AI Search.

This is the `analytic` slice of the pinned ATT&CK index: the analytics and detection
strategies the bundle carries. There is no local corpus and no BM25 fallback — the client,
the filter and the relaxation order live in `backend/knowledge/search.py`; this module
supplies the row shape and the tool envelope.

It reads no telemetry, so it never replaces the telemetry tools, and no retrieved logic is
ever executed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ...data import MAX_RESULT_BYTES
from ...knowledge.search import ANALYTIC, KnowledgeUnavailable, retrieve, status
from .base import ToolContext, agent_tool, object_schema

logger = logging.getLogger(__name__)

TOOL_NAME = "search_mitre_attack"
SNIPPET_CHARS = 400
MAX_PAYLOAD_BYTES = MAX_RESULT_BYTES // 4

COLUMNS = ["doc_id", "source", "doc_type", "title", "technique_ids", "platforms",
           "log_sources", "path", "commit", "license", "attack_url", "score", "snippet"]

_ADVISORY = (
    "Advisory context from pinned MITRE ATT&CK material, not a verdict. A match means "
    "ATT&CK describes a technique whose signs resemble what the scanner recorded; it does "
    "not establish that the replayed activity was malicious, unauthorised, or successful, "
    "and ATT&CK observed nothing here. Only the telemetry tools observe. Cite path, "
    "commit, and licence for anything you repeat."
)


async def knowledge_status() -> dict[str, Any]:
    """Availability of the knowledge index, for the health endpoint."""
    return await status()


def _snippet(document: dict[str, Any]) -> str:
    text = " ".join(f"{document.get('summary', '')} {document.get('body', '')}".split())
    return text[:SNIPPET_CHARS] + ("…" if len(text) > SNIPPET_CHARS else "")


def _row(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": document.get("doc_id", ""),
        "source": document.get("source", ""),
        "doc_type": document.get("doc_type", ""),
        "title": document.get("title", ""),
        "technique_ids": list(document.get("technique_ids") or [])[:12],
        "platforms": list(document.get("platforms") or [])[:8],
        "log_sources": list(document.get("log_sources") or [])[:6],
        "path": document.get("path", ""),
        "commit": str(document.get("commit") or "")[:12],
        "license": document.get("license", ""),
        "attack_url": document.get("attack_url", ""),
        "score": round(float(document.get("@search.score") or 0.0), 4),
        "snippet": _snippet(document),
    }


@agent_tool(
    name=TOOL_NAME,
    category="mitre_attack",
    datasource="search",
    description="""
Search pinned MITRE ATT&CK knowledge in Azure AI Search: the analytics and detection
strategies of one pinned enterprise-attack bundle. Use it to characterise a situation the
scanner already produced — pass the situation's technique ids or behaviour class as
filters and the analyst question as free text. Results are advisory ATT&CK context with
provenance, never a verdict and never proof that replayed activity was malicious. It reads
no telemetry, so it never replaces the telemetry tools.
""",
    parameters=object_schema({
        "question": {"type": "string", "maxLength": 2000, "description": "Analyst question in free text; ranks the filtered set. May be empty."},
        "technique_ids": {"type": "array", "maxItems": 16, "items": {"type": "string"}, "description": "ATT&CK ids such as T1087.002. Empty array applies no technique filter."},
        "behaviour_classes": {"type": "array", "maxItems": 5, "items": {"type": "string", "enum": ["beaconing", "credential_use", "directory_discovery", "privileged_session", "volume_anomaly"]}, "description": "Closed behaviour vocabulary carried by scanner factors. Empty array applies no behaviour filter."},
        "platforms": {"type": "array", "maxItems": 6, "items": {"type": "string"}, "description": "ATT&CK platforms such as Windows or Linux. Empty array applies no platform filter."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Bounded result cap."},
    }, ["question", "technique_ids", "behaviour_classes", "platforms", "max_results"]),
)
async def search_mitre_attack(context: ToolContext, *, question: str, technique_ids: list[str],
                        behaviour_classes: list[str], platforms: list[str],
                        max_results: int) -> dict[str, Any]:
    terms = {
        "technique_ids": [value.strip().upper() for value in technique_ids],
        "behaviour_class": [value.strip().lower() for value in behaviour_classes],
        "platforms": [value.strip() for value in platforms],
    }
    filters = {"technique_ids": list(technique_ids),
               "behaviour_classes": list(behaviour_classes),
               "platforms": list(platforms)}
    try:
        hits, relaxed, expression = await retrieve(doc_kind=ANALYTIC, query=question,
                                             terms=terms, top=max_results)
    except KnowledgeUnavailable as exc:
        logger.warning("cybereye.mitre_attack.unavailable %s", exc)
        return {
            "kind": "cybereye_tool_result", "tool": TOOL_NAME,
            "category": "mitre_attack_unavailable",
            "scope": {"question": question, "filters": filters, "row_count": 0,
                      "note": (f"The MITRE ATT&CK knowledge index could not be reached: "
                               f"{exc}. Answer from replay telemetry only until it is "
                               f"back; there is no local copy to fall back to.")},
            "columns": [], "rows": [], "truncated": False,
            "historical_replay": True, "fallback": False,
        }

    rows: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for hit in hits:
        row = _row(hit)
        size = len(json.dumps(row, ensure_ascii=False).encode("utf-8"))
        if used + size > MAX_PAYLOAD_BYTES:
            truncated = True
            break
        used += size
        rows.append(row)

    return {
        "kind": "cybereye_tool_result",
        "tool": TOOL_NAME,
        "category": "mitre_attack",
        "scope": {
            "question": question,
            "filters": filters,
            "relaxed_filters": relaxed,
            "row_count": len(rows),
            "retrieval": "azure-ai-search",
            "index_filter": expression,
            "ranking": "Azure AI Search keyword relevance over the ATT&CK text surface",
            "advisory": _ADVISORY,
        },
        "columns": list(COLUMNS),
        "rows": rows,
        "truncated": truncated,
        "historical_replay": True,
        "fallback": False,
    }
