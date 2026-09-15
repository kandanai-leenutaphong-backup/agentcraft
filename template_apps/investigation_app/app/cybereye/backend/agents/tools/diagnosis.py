"""Sink tools the agent must call to record its diagnosis, plus run-scoped provenance.

Nothing here mints provenance. `EvidenceLedger` observes the tool calls the server itself
drove, so an id the model attaches to a step is either resolved against a row a tool really
returned in this run or reported as unsupported.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...config import settings
from .base import ToolContext, agent_tool, object_schema

#: What the evidence supports about the activity, from weakest to strongest claim.
ASSESSMENTS = ("insufficient_evidence", "benign_explained", "unexplained_but_low_signal",
               "suspicious_requires_review", "consistent_with_intrusion_activity")
CONFIDENCES = ("low", "medium", "high")
MAX_CITATIONS = 6
MAX_SEQUENCE_STEPS = 10
MAX_STEP_EVIDENCE = 4
#: Tool result categories whose rows carry citable knowledge-index provenance.
KNOWLEDGE_CATEGORIES = ("mitre_attack", "situation_types")
#: Row fields that identify a record an analyst or the model can cite back.
EVIDENCE_KEYS = ("resource_id", "doc_id")
#: Ledger bounds, so one run cannot grow the index without limit.
MAX_LEDGER_ROWS = 600
MAX_FIELD_CHARS = 400


def datasource_of(tool: str, result: dict[str, Any]) -> str:
    """Name the concrete store a tool result came out of, never a generic 'the database'."""
    category = str(result.get("category") or "")
    if category.startswith("mitre_attack") or category == "situation_types":
        return f"Azure AI Search index {settings.knowledge_index or 'mitre-attack (unset)'}"
    table = f"{settings.adx_database}.{settings.table}"
    if tool == "scan_situations":
        return f"Deterministic scanner over Azure Data Explorer table {table}"
    return f"Azure Data Explorer table {table}"


def _query_text(tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> str:
    """The call as issued: raw KQL where the tool takes one, otherwise the bound arguments."""
    raw = arguments.get("query")
    if isinstance(raw, str) and raw.strip():
        return " ".join(raw.split())[:MAX_FIELD_CHARS]
    issued = arguments or (result.get("scope") if isinstance(result.get("scope"), dict) else {})
    pairs = ", ".join(
        f"{key}={value}" for key, value in list(issued.items())[:8]
        if key not in {"row_count", "max_rows", "advisory"} and value not in (None, "", [], {})
    )
    return f"{tool}({pairs})"[:MAX_FIELD_CHARS]


def _bounded(row: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in list(row.items())[:24]:
        if value in (None, "", [], {}):
            continue
        text = value if isinstance(value, (int, float, bool)) else str(value)
        record[str(key)] = text[:MAX_FIELD_CHARS] if isinstance(text, str) else text
    return record


class EvidenceLedger:
    """Every tool call one diagnosis run made, and the rows each call actually returned."""

    def __init__(self) -> None:
        self._arguments: dict[str, dict[str, Any]] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self.retrievals: list[dict[str, Any]] = []

    def note_call(self, call_id: str, arguments: Any) -> None:
        """Capture the arguments as issued, before the tool runs."""
        if call_id and isinstance(arguments, dict):
            self._arguments[call_id] = arguments

    def record(self, call_id: str, tool: str, display_name: str, result: Any) -> None:
        """Index the rows one completed tool call returned, under this run's provenance."""
        if not isinstance(result, dict) or "error" in result:
            return
        rows = [row for row in (result.get("rows") or []) if isinstance(row, dict)]
        arguments = self._arguments.get(call_id, {})
        retrieval = {
            "retrieval_id": call_id or f"call-{len(self.retrievals) + 1}",
            "tool": tool,
            "display_name": display_name or tool,
            "datasource": datasource_of(tool, result),
            "query": _query_text(tool, arguments, result),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "row_count": len(rows),
        }
        self.retrievals.append(retrieval)
        for row in rows:
            if len(self._records) >= MAX_LEDGER_ROWS:
                return
            key = next((str(row[name]).strip() for name in EVIDENCE_KEYS
                        if str(row.get(name) or "").strip()), "")
            if not key or key in self._records:
                continue
            self._records[key] = {"evidence_id": key, "record": _bounded(row),
                                  "retrieval": dict(retrieval)}

    def resolve(self, evidence_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        """Only ids a tool in this run returned become evidence; the rest are named unsupported."""
        resolved: list[dict[str, Any]] = []
        unsupported: list[str] = []
        seen: set[str] = set()
        for value in evidence_ids or []:
            key = str(value or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            entry = self._records.get(key)
            if entry is None:
                unsupported.append(key)
                continue
            resolved.append({**entry, "record": dict(entry["record"]),
                             "retrieval": dict(entry["retrieval"])})
        return resolved[:MAX_STEP_EVIDENCE], unsupported[:MAX_STEP_EVIDENCE]


def index_knowledge_rows(result: Any) -> dict[str, dict[str, str]]:
    """Map doc id to citation fields for every knowledge row a run actually returned."""
    if not isinstance(result, dict) or result.get("category") not in KNOWLEDGE_CATEGORIES:
        return {}
    index: dict[str, dict[str, str]] = {}
    for row in result.get("rows") or []:
        if not isinstance(row, dict):
            continue
        type_id = str(row.get("doc_id") or row.get("type_id") or "").strip()
        if not type_id:
            continue
        index[type_id] = {
            "type_id": type_id,
            "label": str(row.get("title") or row.get("label") or "").strip(),
            "source": str(row.get("source") or "").strip(),
            "path": str(row.get("path") or "").strip(),
            "commit": str(row.get("commit") or "").strip(),
        }
    return index


def resolve_citations(
    index: dict[str, dict[str, str]], situation_type: str, citation_ids: list[str],
) -> tuple[list[dict[str, str]], list[str], bool]:
    """Keep only citations this run's own tool rows support; provenance is never minted here."""
    citations: list[dict[str, str]] = []
    unsupported: list[str] = []
    seen: set[str] = set()
    for value in citation_ids or []:
        key = str(value or "").strip()
        if not key:
            continue
        row = index.get(key) or next(
            (item for item in index.values() if item["label"].casefold() == key.casefold()),
            None,
        )
        if row is None:
            unsupported.append(key)
            continue
        if row["type_id"] in seen:
            continue
        seen.add(row["type_id"])
        citations.append(dict(row))
    wanted = (situation_type or "").strip().casefold()
    supported = bool(wanted) and any(
        item["label"].casefold() == wanted for item in index.values()
    )
    return citations[:MAX_CITATIONS], unsupported[:MAX_CITATIONS], supported


@agent_tool(
    name="record_situation_diagnosis",
    datasource="none",
    category="situation_diagnosis",
    description="""
Record the final plain-language diagnosis of one situation. Call this exactly once, only after
gathering evidence with the other tools. The headline must read as a sentence an analyst would say
out loud about what appears to be happening, naming the host, account, and activity. Describe the
historical replay in the past tense. Never claim live monitoring, prevention, containment, or a
confirmed breach.
""",
    parameters=object_schema({
        "headline": {
            "type": "string", "minLength": 20, "maxLength": 200,
            "description": "One sentence naming what appears to be happening, on which host, by which account.",
        },
        "narrative": {
            "type": "string", "minLength": 40, "maxLength": 700,
            "description": "Two to four sentences: the sequence observed, why it fits together, and what it would mean.",
        },
        "assessment": {
            "type": "string", "enum": list(ASSESSMENTS),
            "description": "How strongly the gathered evidence supports intrusion-like activity.",
        },
        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
        "supporting_observations": {
            "type": "array", "minItems": 1, "maxItems": 6,
            "items": {"type": "string", "minLength": 10, "maxLength": 220},
            "description": "Each entry states one observed fact and the tool or count it came from.",
        },
        "would_change_the_call": {
            "type": "array", "minItems": 1, "maxItems": 4,
            "items": {"type": "string", "minLength": 10, "maxLength": 220},
            "description": "Facts not established here that would raise or lower the assessment.",
        },
        "evidence_ids": {
            "type": "array", "maxItems": 8,
            "items": {"type": "string", "maxLength": 200},
            "description": "resource_id values seen in tool output that support the headline.",
        },
        "situation_type": {
            "type": "string", "minLength": 3, "maxLength": 200,
            "description": "The closest situation type: copy verbatim the title of one MITRE ATT&CK document search_mitre_attack returned in this run. Never invent a label.",
        },
        "citation_ids": {
            "type": "array", "minItems": 1, "maxItems": MAX_CITATIONS,
            "items": {"type": "string", "maxLength": 200},
            "description": "doc_id values of MITRE ATT&CK documents search_mitre_attack returned in this run, starting with the one naming situation_type.",
        },
    }, ["headline", "narrative", "assessment", "confidence", "supporting_observations",
        "would_change_the_call", "evidence_ids", "situation_type", "citation_ids"]),
)
def record_situation_diagnosis(
    context: ToolContext, *, headline: str, narrative: str, assessment: str, confidence: str,
    supporting_observations: list[str], would_change_the_call: list[str],
    evidence_ids: list[str], situation_type: str, citation_ids: list[str],
) -> dict[str, Any]:
    if assessment not in ASSESSMENTS:
        raise ValueError(f"assessment must be one of {ASSESSMENTS}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"confidence must be one of {CONFIDENCES}")
    return {
        "kind": "cybereye_tool_result",
        "tool": "record_situation_diagnosis",
        "category": "situation_diagnosis",
        "headline": headline.strip(),
        "narrative": narrative.strip(),
        "assessment": assessment,
        "confidence": confidence,
        "supporting_observations": [line.strip() for line in supporting_observations if line.strip()][:6],
        "would_change_the_call": [line.strip() for line in would_change_the_call if line.strip()][:4],
        "evidence_ids": list(dict.fromkeys(value.strip() for value in evidence_ids if value.strip()))[:8],
        "situation_type": situation_type.strip(),
        "citation_ids": list(dict.fromkeys(value.strip() for value in citation_ids if value.strip()))[:MAX_CITATIONS],
        "historical_replay": True,
        "fallback": False,
    }


@agent_tool(
    name="record_sequence_step",
    datasource="none",
    category="sequence_step",
    description="""
Record ONE step of the sequence of events, then call this again for the next step. Push the
steps one at a time in chronological order, earliest first, starting at position 1. Each step is
one short past-tense line naming the account or host and what it did. Take the timestamp verbatim
from telemetry a tool returned in this run; leave it empty rather than estimating one. evidence_ids
must be resource_id or doc_id values that a tool in THIS run returned, and only the ones that
support THIS step — the server resolves them against what the tools actually returned and marks
anything else unsupported. Never claim live monitoring, prevention, containment, or a confirmed
breach.
""",
    parameters=object_schema({
        "position": {
            "type": "integer", "minimum": 1, "maximum": MAX_SEQUENCE_STEPS,
            "description": "1-based position of this step in chronological order.",
        },
        "description": {
            "type": "string", "minLength": 10, "maxLength": 160,
            "description": "One short past-tense line: who or what, and what happened. No JSON, no tool output.",
        },
        "timestamp": {
            "type": "string", "maxLength": 40,
            "description": "The step's time copied verbatim from tool output, or an empty string if telemetry gave none.",
        },
        "evidence_ids": {
            "type": "array", "maxItems": MAX_STEP_EVIDENCE,
            "items": {"type": "string", "maxLength": 200},
            "description": "resource_id or doc_id values a tool returned in this run that support this step; may be empty.",
        },
    }, ["position", "description", "timestamp", "evidence_ids"]),
)
def record_sequence_step(
    context: ToolContext, *, position: int, description: str, timestamp: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    text = (description or "").strip()
    if not text:
        raise ValueError("a step needs a description")
    if not 1 <= int(position) <= MAX_SEQUENCE_STEPS:
        raise ValueError(f"position must be between 1 and {MAX_SEQUENCE_STEPS}")
    return {
        "kind": "cybereye_tool_result",
        "tool": "record_sequence_step",
        "category": "sequence_step",
        "position": int(position),
        "description": text,
        "timestamp": (timestamp or "").strip(),
        "evidence_ids": list(dict.fromkeys(
            str(value).strip() for value in evidence_ids or [] if str(value).strip()
        ))[:MAX_STEP_EVIDENCE],
        "historical_replay": True,
        "fallback": False,
    }


@agent_tool(
    name="complete_sequence_of_events",
    datasource="none",
    category="sequence_of_events",
    description="""
Close the sequence of events. Call this exactly once, after the last record_sequence_step call,
and then stop. It records nothing but what is uncertain about the ordering.
""",
    parameters=object_schema({
        "ordering_note": {
            "type": "string", "maxLength": 240,
            "description": "What is uncertain about the ordering, or an empty string if it is fully established by timestamps.",
        },
    }, ["ordering_note"]),
)
def complete_sequence_of_events(context: ToolContext, *, ordering_note: str = "") -> dict[str, Any]:
    return {
        "kind": "cybereye_tool_result",
        "tool": "complete_sequence_of_events",
        "category": "sequence_of_events",
        "ordering_note": (ordering_note or "").strip(),
        "historical_replay": True,
        "fallback": False,
    }
