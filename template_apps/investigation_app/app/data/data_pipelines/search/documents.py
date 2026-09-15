"""What one pinned MITRE ATT&CK record becomes as a search document, and nothing more.

The index holds knowledge, not telemetry. Every document originates in the pinned
enterprise-attack STIX bundle, normalised once by `cyber_kb/normalize`, and carries the
path, commit and licence of that mirror so a hit torn out of the index still says where
it came from.

TWO KINDS, ONE INDEX
--------------------
`situation_type` rows answer "given these signs, what kind of situation is this": the
ATT&CK techniques and tactics from `classification.jsonl`. `analytic` rows answer "what
detection material matches these observables": the ATT&CK analytics and detection
strategies from `corpus.jsonl`. Both are ATT&CK and both cite the same bundle, so they
share one index and one role assignment; `doc_kind` separates them at query time.

NOTHING HERE IS A DETECTOR
--------------------------
A match is advisory knowledge about a named technique. It is never evidence that replayed
activity occurred, was malicious, or succeeded; the telemetry tools remain the only source
of observation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from template_foundations.azure_search import FieldSpec, IndexSpec, safe_key

#: The searchable projection is clamped well under the service's request ceiling.
MAX_TEXT_CHARS = 8000

MITRE_DATASET = "mitre_attack"

#: The one mirror this pipeline may publish. A record from another source is skipped.
MITRE_SOURCE = "attack"

SITUATION_TYPE = "situation_type"
ANALYTIC = "analytic"

_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(name="id", type="string", key=True, filterable=True),
    FieldSpec(name="doc_kind", type="string", filterable=True, facetable=True),
    FieldSpec(name="doc_id", type="string", filterable=True),
    FieldSpec(name="source", type="string", filterable=True, facetable=True),
    FieldSpec(name="doc_type", type="string", filterable=True, facetable=True),
    FieldSpec(name="title", type="string", searchable=True),
    FieldSpec(name="family", type="string", searchable=True, filterable=True,
              facetable=True),
    FieldSpec(name="definition", type="string", searchable=True),
    FieldSpec(name="summary", type="string", searchable=True),
    FieldSpec(name="body", type="string", searchable=True),
    FieldSpec(name="symptoms", type="string_collection", searchable=True),
    FieldSpec(name="keywords", type="string_collection", searchable=True),
    FieldSpec(name="log_sources", type="string_collection", searchable=True),
    FieldSpec(name="platforms", type="string_collection", searchable=True,
              filterable=True),
    FieldSpec(name="technique_ids", type="string_collection", searchable=True,
              filterable=True, facetable=True),
    FieldSpec(name="behaviour_class", type="string_collection", searchable=True,
              filterable=True, facetable=True),
    FieldSpec(name="maturity", type="string", filterable=True),
    FieldSpec(name="native_id", type="string", filterable=True),
    FieldSpec(name="attack_url", type="string"),
    FieldSpec(name="path", type="string", filterable=True),
    FieldSpec(name="commit", type="string", filterable=True),
    FieldSpec(name="license", type="string", filterable=True),
    FieldSpec(name="retrieved_at", type="string", filterable=True, sortable=True),
    FieldSpec(name="content", type="string", searchable=True),
)

INDEX_PURPOSE = (
    "Pinned MITRE ATT&CK knowledge: techniques and tactics as candidate situation types, "
    "analytics and detection strategies as advisory detection material, derived from one "
    "pinned enterprise-attack STIX bundle. Holds no telemetry and is not a detector."
)


def mitre_index(name: str) -> IndexSpec:
    """The one index definition this pipeline creates."""
    return IndexSpec(name=name, purpose=INDEX_PURPOSE, fields=_FIELDS)


def _text(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _strings(value: Any, limit: int = 64) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out = [str(item).strip() for item in value if str(item or "").strip()]
    return out[:limit]


def _content(parts: Sequence[str]) -> str:
    return " ".join(" ".join(part.split()) for part in parts if part)[:MAX_TEXT_CHARS]


def document_key(doc_kind: str, doc_id: str) -> str:
    """The document key for a normalised record id.

    Kind-qualified: both corpora mint ids in the same `attack:<hex>` namespace, so an
    unqualified key lets an analytic silently overwrite a situation type.
    """
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
        "behaviour_class": [value.lower()
                            for value in _strings(record.get("behaviour_class"))],
        "maturity": _text(record.get("maturity"), 64),
        "native_id": _text(record.get("native_id"), 200),
        "attack_url": _text(source_fields.get("attack_url"), 400),
        "path": _text(record.get("path"), 500),
        "commit": _text(record.get("commit"), 64),
        "license": _text(record.get("license"), 200),
        "retrieved_at": _text(record.get("retrieved_at"), 64),
    }


def situation_type_document(record: Mapping[str, Any]) -> dict[str, Any]:
    """One normalised ATT&CK situation-type record as a document."""
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
    """One normalised ATT&CK analytic or detection record as a document."""
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
    """Dispatch on the record's own shape: a type_id makes it a situation type."""
    if record.get("type_id"):
        return situation_type_document(record)
    return analytic_document(record)


__all__ = [
    "ANALYTIC",
    "INDEX_PURPOSE",
    "MITRE_DATASET",
    "MITRE_SOURCE",
    "SITUATION_TYPE",
    "analytic_document",
    "build_document",
    "document_key",
    "mitre_index",
    "situation_type_document",
]
