"""Synthetic MITRE fixture projection matching the already loaded knowledge index."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.cybereye.backend.knowledge.keys import safe_key

MAX_TEXT_CHARS = 8000
SITUATION_TYPE = "situation_type"
ANALYTIC = "analytic"


def _text(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _strings(value: Any, limit: int = 64) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    values = [str(item).strip() for item in value if str(item or "").strip()]
    return values[:limit]


def _content(parts: Sequence[str]) -> str:
    return " ".join(" ".join(part.split()) for part in parts if part)[:MAX_TEXT_CHARS]


def document_key(doc_kind: str, doc_id: str) -> str:
    return safe_key(f"{doc_kind}:{doc_id}")


def _envelope(record: Mapping[str, Any], *, doc_kind: str, doc_id: str,
              title: str) -> dict[str, Any]:
    source_fields = record.get("source_fields")
    source_fields = source_fields if isinstance(source_fields, Mapping) else {}
    return {
        "id": document_key(doc_kind, doc_id),
        "doc_kind": doc_kind,
        "doc_id": doc_id,
        "source": _text(record.get("source")),
        "doc_type": _text(record.get("doc_type")),
        "title": _text(title, 400),
        "family": _text(record.get("family"), 200),
        "symptoms": _strings(record.get("symptoms")),
        "keywords": _strings(record.get("keywords")),
        "log_sources": _strings(record.get("log_sources")),
        "platforms": _strings(record.get("platforms")),
        "technique_ids": [value.upper() for value in _strings(record.get("technique_ids"))],
        "behaviour_class": [value.lower() for value in _strings(record.get("behaviour_class"))],
        "maturity": _text(record.get("maturity"), 64),
        "native_id": _text(record.get("native_id"), 200),
        "attack_url": _text(source_fields.get("attack_url"), 400),
        "path": _text(record.get("path"), 500),
        "commit": _text(record.get("commit"), 64),
        "license": _text(record.get("license"), 200),
        "retrieved_at": _text(record.get("retrieved_at"), 64),
    }


def situation_type_document(record: Mapping[str, Any]) -> dict[str, Any]:
    title = _text(record.get("label"), 400)
    definition = _text(record.get("definition"))
    document = _envelope(record, doc_kind=SITUATION_TYPE,
                         doc_id=_text(record.get("type_id"), 200), title=title)
    document["definition"] = definition
    document["summary"] = ""
    document["body"] = ""
    document["content"] = _content([
        title, document["family"], definition,
        " ".join(document["symptoms"]), " ".join(document["keywords"]),
        " ".join(document["technique_ids"]),
    ])
    return document


def analytic_document(record: Mapping[str, Any]) -> dict[str, Any]:
    title = _text(record.get("title"), 400)
    document = _envelope(record, doc_kind=ANALYTIC,
                         doc_id=_text(record.get("doc_id"), 200), title=title)
    document["definition"] = ""
    document["summary"] = _text(record.get("summary"))
    document["body"] = _text(record.get("body"))
    document["content"] = _content([
        title, document["summary"], document["body"],
        " ".join(document["log_sources"]), " ".join(document["technique_ids"]),
    ])
    return document


def build_document(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("type_id"):
        return situation_type_document(record)
    return analytic_document(record)