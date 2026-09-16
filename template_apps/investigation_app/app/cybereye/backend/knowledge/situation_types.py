"""Candidate situation types: the ATT&CK technique and tactic slice of the same index.

`knowledge_base.py` answers "what detection material matches these observables"; this
answers "given these signs, what kind of situation is this". Both read the pinned MITRE
ATT&CK index in Azure AI Search through `backend/knowledge/search.py`. There is no local
classification corpus and no BM25 fallback: an unreachable index is reported as such.

Choosing a type names what recorded signs resemble. It establishes no malice, no
authorisation, no execution and no success, and it names no actor.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..data import MAX_RESULT_BYTES
from .search import (
    ANALYTIC, SITUATION_TYPE, KnowledgeUnavailable, get_by_doc_id, retrieve, status,
)

logger = logging.getLogger(__name__)

DEFINITION_CHARS = 320
SYMPTOM_LIMIT = 6
MAX_PAYLOAD_BYTES = MAX_RESULT_BYTES // 4

COLUMNS = ["type_id", "source", "label", "family", "definition", "symptoms",
           "technique_ids", "behaviour_class", "path", "commit", "license", "score"]

_ADVISORY = (
    "Candidate situation types from pinned MITRE ATT&CK techniques and tactics, not a "
    "verdict. Choosing a type names what the observed signs resemble; it never establishes "
    "that the replayed activity was malicious, unauthorised, or successful, and it names "
    "no actor. ATT&CK techniques carry a definition rather than a symptom list, so they "
    "match on wording and technique identifiers."
)


async def classification_status() -> dict[str, Any]:
    """Availability of the knowledge index, for the health endpoint."""
    return await status()


def _row(document: dict[str, Any]) -> dict[str, Any]:
    definition = document.get("definition") or ""
    return {
        "type_id": document.get("doc_id", ""),
        "source": document.get("source", ""),
        "label": document.get("title", ""),
        "family": document.get("family") or "",
        "definition": definition[:DEFINITION_CHARS]
        + ("…" if len(definition) > DEFINITION_CHARS else ""),
        "symptoms": list(document.get("symptoms") or [])[:SYMPTOM_LIMIT],
        "technique_ids": list(document.get("technique_ids") or [])[:12],
        "behaviour_class": list(document.get("behaviour_class") or []),
        "path": document.get("path", ""),
        "commit": str(document.get("commit") or "")[:12],
        "license": document.get("license", ""),
        "score": round(float(document.get("@search.score") or 0.0), 4),
    }


async def get_situation_type(type_id: str) -> dict[str, Any] | None:
    """Return one full knowledge document so a citation can be opened.

    Fetched by key from the same index the candidate came from, so the citation an
    analyst opens is the document the model was shown. Either slice resolves: a diagnosis
    cites the analytic documents `search_mitre_attack` returned, a classification cites
    situation-type documents, and both arrive here as one opaque id.
    """
    wanted = (type_id or "").strip()
    document = await get_by_doc_id(SITUATION_TYPE, wanted) or await get_by_doc_id(ANALYTIC, wanted)
    if document is None:
        return None
    full = dict(document)
    full["type_id"] = full.get("doc_id", "")
    full["label"] = full.get("title", "")
    return full


async def search_situation_types(*, query: str, technique_ids: list[str] | None = None,
                           behaviour_classes: list[str] | None = None,
                           families: list[str] | None = None,
                           sources: list[str] | None = None,
                           max_results: int = 6) -> dict[str, Any]:
    """Return bounded candidate situation types for one symptom query."""
    filters = {
        "technique_ids": list(technique_ids or []),
        "behaviour_classes": list(behaviour_classes or []),
        "families": list(families or []),
        "sources": list(sources or []),
    }
    terms = {
        "technique_ids": [value.strip().upper() for value in (technique_ids or [])],
        "behaviour_class": [value.strip().lower() for value in (behaviour_classes or [])],
    }
    try:
        hits, relaxed, expression = await retrieve(doc_kind=SITUATION_TYPE, query=query,
                                             terms=terms, top=max_results)
    except KnowledgeUnavailable as exc:
        logger.warning("cybereye.situation_types.unavailable %s", exc)
        return {
            "kind": "cybereye_situation_types",
            "category": "situation_types_unavailable",
            "scope": {"query": query, "filters": filters, "row_count": 0,
                      "note": (f"The MITRE ATT&CK knowledge index could not be reached: "
                               f"{exc}. Do not classify from memory; there is no local "
                               f"copy to fall back to.")},
            "columns": [], "rows": [], "truncated": False, "historical_replay": True,
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
        "kind": "cybereye_situation_types",
        "category": "situation_types",
        "scope": {
            "query": query,
            "filters": filters,
            "relaxed_filters": relaxed,
            "row_count": len(rows),
            "retrieval": "azure-ai-search",
            "index_filter": expression,
            "ranking": ("Azure AI Search keyword relevance over label, family, definition, "
                        "symptoms, and keywords"),
            "advisory": _ADVISORY,
        },
        "columns": list(COLUMNS),
        "rows": rows,
        "truncated": truncated,
        "historical_replay": True,
    }
