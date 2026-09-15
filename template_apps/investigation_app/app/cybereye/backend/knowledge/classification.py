"""Situation-type classification: symptom query, bounded model call, enforced JSON shape.

Three separable pieces so each is testable on its own:

- `build_symptom_query` is pure. It turns a scanner situation into the signs-and-symptoms
  text that corpus #2 is indexed on, deriving nothing that is not already in the envelope.
- `parse_model_output` is pure. It is the server-side shape gate: the model may only pick a
  label that was retrieved, and provenance is taken from the corpus row, never from the
  model.
- `classify` wires the two around one bounded, non-streaming model call supplied by the
  caller, so tests can drive it with a fake responder.

A classification names what recorded signs resemble. It is never evidence of malice,
authorisation, execution, or success, and this module refuses to emit a type the corpus
does not contain.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..models import Situation
from .situation_types import search_situation_types

DEFAULT_CANDIDATES = 6
MAX_OUTPUT_TOKENS = 900
MAX_QUERY_CHARS = 2000
MAX_SIGN_CHARS = 240
MAX_SIGNS = 12
MAX_BASIS = 4
MAX_ALTERNATIVES = 3
MAX_NOT_ESTABLISHED = 4
MAX_STRING_CHARS = 240
CONFIDENCE_VALUES = ("high", "medium", "low")
UNATTRIBUTED = ("", "unattributed")
_ADMIN_PREFIXES = ("adm", "admin", "sa-", "svc-adm")

_TECHNIQUE = re.compile(r"\bT(\d{4})(?:\.(\d{3}))?\b")
_EVENT_ID = re.compile(
    r"win_event_id\s*==\s*\"(\d{3,5})\"|\bevent(?:\s+id)?\s+(\d{3,5})\b", re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)

CLASSIFY_INSTRUCTIONS = (
    "Classify one deterministic situation from a historical cybersecurity replay of a static "
    "export. Choose exactly one situation_type from the supplied candidate list and copy its "
    "label verbatim. Never invent a type that is not in the list, never merge two candidates, "
    "never rename one. Justify only from the supplied situation factors: rule labels, observed "
    "facts, behaviour classes, counts, and timestamps. Never assert malice, intent, attribution, "
    "authorisation, execution, success, compromise, containment, or live monitoring; a "
    "classification names what the recorded signs resemble and nothing more. If no candidate "
    "fits well, still choose the closest one and set confidence to low. "
    "Return STRICT JSON only: one object, no prose, no markdown fence, no trailing text, with "
    "keys situation_type (string, exactly one candidate label), confidence (\"high\", \"medium\", "
    "or \"low\"), basis (array of at most 4 short strings, each naming a specific supplied "
    "factor), alternatives (array of at most 3 objects with keys label and why_not, each label "
    "being a different candidate label), and not_established (array of at most 4 short strings "
    "naming what this classification does not prove)."
)

_NOT_ESTABLISHED_FLOOR = (
    "This is a historical replay of a static export; the classification establishes no "
    "malice, authorisation, execution, or success."
)


@dataclass(frozen=True, slots=True)
class SymptomQuery:
    """The deterministic retrieval query derived from one situation's own factors."""

    text: str
    signs: tuple[str, ...]
    technique_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    behaviour_classes: tuple[str, ...]
    entity_shape: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "signs": list(self.signs),
            "technique_ids": list(self.technique_ids),
            "event_ids": list(self.event_ids),
            "behaviour_classes": list(self.behaviour_classes),
            "entity_shape": list(self.entity_shape),
        }


def _collapse(text: Any, limit: int = MAX_SIGN_CHARS) -> str:
    return " ".join(str(text or "").split())[:limit]


def _pattern_text(pattern: Any) -> str:
    """Every prose field a pattern carries, including its derived query structure."""
    derivation = pattern.derivation if isinstance(pattern.derivation, dict) else {}
    return " ".join([
        pattern.label, pattern.description, pattern.observed_fact, pattern.summary,
        pattern.evidence_semantics, json.dumps(derivation, default=str, sort_keys=True),
    ])


def _entity_shape(host: str, principal: str) -> list[str]:
    """Describe the entity without asserting anything a name cannot support."""
    shape = ["host is unattributed" if host.strip().lower() in UNATTRIBUTED
             else "one named host"]
    lowered = principal.strip().lower()
    if lowered in UNATTRIBUTED:
        shape.append("principal is unattributed")
    elif lowered.startswith(_ADMIN_PREFIXES):
        shape.append("principal name follows an administrative naming convention "
                     "(naming only, not an authorisation fact)")
    else:
        shape.append("one named principal")
    return shape


def build_symptom_query(situation: Situation) -> SymptomQuery:
    """Assemble the signs-and-symptoms query for one situation. Pure and deterministic."""
    patterns = sorted(situation.patterns, key=lambda item: (item.rule_id, item.label))
    signs: list[str] = []
    behaviours: list[str] = []
    techniques: set[str] = set()
    events: set[str] = set()
    for pattern in patterns:
        sign = _collapse(f"{pattern.label}: {pattern.observed_fact}")
        if sign and sign not in signs:
            signs.append(sign)
        if pattern.behaviour_class and pattern.behaviour_class not in behaviours:
            behaviours.append(pattern.behaviour_class)
        text = _pattern_text(pattern)
        techniques.update(pattern.technique_ids)
        for base, sub in _TECHNIQUE.findall(text):
            techniques.add(f"T{base}.{sub}" if sub else f"T{base}")
        for quoted, bare in _EVENT_ID.findall(text):
            events.add(quoted or bare)

    signs = signs[:MAX_SIGNS]
    shape = _entity_shape(situation.host, situation.principal)
    parts = [
        *signs,
        *(f"behaviour class {value}" for value in sorted(behaviours)),
        *(f"ATT&CK {value}" for value in sorted(techniques)),
        *(f"Windows event {value}" for value in sorted(events)),
        *shape,
    ]
    return SymptomQuery(
        text=_collapse(" ".join(parts), MAX_QUERY_CHARS),
        signs=tuple(signs),
        technique_ids=tuple(sorted(techniques)),
        event_ids=tuple(sorted(events)),
        behaviour_classes=tuple(sorted(behaviours)),
        entity_shape=tuple(shape),
    )


def build_model_input(situation: Situation, query: SymptomQuery,
                      candidates: list[dict[str, Any]]) -> str:
    """Render the one bounded prompt payload: situation facts plus the retrieved shortlist."""
    listing = []
    for index, row in enumerate(candidates, start=1):
        lines = [f"{index}. label: {row['label']}",
                 f"   family: {row.get('family') or '(none)'}",
                 f"   source: {row['source']}",
                 f"   definition: {row.get('definition') or '(none stated)'}"]
        symptoms = row.get("symptoms") or []
        lines.append("   symptoms: " + ("; ".join(symptoms) if symptoms
                                        else "(this source lists none)"))
        listing.append("\n".join(lines))
    return "\n\n".join([
        "SITUATION ENVELOPE (the only facts you may cite):",
        situation.model_dump_json(indent=2),
        "DERIVED SIGNS AND SYMPTOMS:",
        json.dumps(query.as_dict(), indent=2, ensure_ascii=False),
        f"CANDIDATE SITUATION TYPES (choose exactly one label from these {len(candidates)}):",
        "\n\n".join(listing),
    ])


def _strings(values: Any, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        if isinstance(value, str) and value.strip():
            cleaned.append(_collapse(value, MAX_STRING_CHARS))
        if len(cleaned) >= limit:
            break
    return cleaned


def parse_model_output(raw: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Enforce the response shape server-side. Returns None when the output is unusable."""
    text = (raw or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group("body").strip()
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    by_label = {str(row["label"]).casefold(): row for row in candidates}
    chosen = by_label.get(str(payload.get("situation_type") or "").strip().casefold())
    if chosen is None:
        return None

    confidence = str(payload.get("confidence") or "").strip().lower()
    if confidence not in CONFIDENCE_VALUES:
        return None

    alternatives: list[dict[str, str]] = []
    seen = {str(chosen["label"]).casefold()}
    for item in payload.get("alternatives") or []:
        if not isinstance(item, dict):
            continue
        row = by_label.get(str(item.get("label") or "").strip().casefold())
        if row is None or str(row["label"]).casefold() in seen:
            continue
        seen.add(str(row["label"]).casefold())
        alternatives.append({"label": row["label"],
                             "why_not": _collapse(item.get("why_not"), MAX_STRING_CHARS)})
        if len(alternatives) >= MAX_ALTERNATIVES:
            break

    not_established = _strings(payload.get("not_established"), MAX_NOT_ESTABLISHED)
    if _NOT_ESTABLISHED_FLOOR not in not_established:
        not_established.append(_NOT_ESTABLISHED_FLOOR)
    return {
        "chosen": chosen,
        "confidence": confidence,
        "basis": _strings(payload.get("basis"), MAX_BASIS),
        "alternatives": alternatives,
        "not_established": not_established,
    }


def _citation(row: dict[str, Any]) -> dict[str, str]:
    return {"type_id": row["type_id"], "label": row["label"], "source": row["source"],
            "path": row["path"], "commit": row["commit"]}


def _envelope(situation_id: str, model: str, started: float, *, situation_type: str = "",
              family: str = "", confidence: str = "low", basis: list[str] | None = None,
              citations: list[dict[str, str]] | None = None,
              alternatives: list[dict[str, str]] | None = None,
              not_established: list[str] | None = None, candidates_considered: int = 0,
              error: str = "", detail: str = "") -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "situation_id": situation_id,
        "situation_type": situation_type,
        "family": family,
        "confidence": confidence,
        "basis": list(basis or []),
        "citations": list(citations or []),
        "alternatives": list(alternatives or []),
        "not_established": list(not_established or [_NOT_ESTABLISHED_FLOOR]),
        "candidates_considered": candidates_considered,
        "model": model,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "historical_replay": True,
    }
    if error:
        envelope["error"] = error
        envelope["detail"] = detail
    return envelope


def classify(situation: Situation, invoke: Callable[[str], str], *, model: str,
             max_candidates: int = DEFAULT_CANDIDATES) -> dict[str, Any]:
    """Retrieve candidate types, make one bounded model call, and enforce the result shape."""
    started = time.monotonic()
    query = build_symptom_query(situation)
    retrieved = search_situation_types(
        query=query.text,
        technique_ids=list(query.technique_ids),
        behaviour_classes=list(query.behaviour_classes),
        max_results=max_candidates,
    )
    rows: list[dict[str, Any]] = retrieved.get("rows") or []
    if retrieved.get("category") != "situation_types":
        return _envelope(situation.situation_id, model, started,
                         error="classification_corpus_unavailable",
                         detail=str(retrieved.get("scope", {}).get("note") or ""))
    if not rows:
        return _envelope(situation.situation_id, model, started,
                         error="no_candidate_types",
                         detail="the classification corpus returned no candidate for this query")

    parsed = parse_model_output(invoke(build_model_input(situation, query, rows)), rows)
    if parsed is None:
        return _envelope(
            situation.situation_id, model, started,
            citations=[_citation(row) for row in rows[:MAX_ALTERNATIVES + 1]],
            candidates_considered=len(rows), error="unparseable_model_output",
            detail=("the model did not return a single JSON object naming one retrieved "
                    "candidate label with a valid confidence"),
        )

    chosen = parsed["chosen"]
    alternate_rows = [row for row in rows
                      if any(row["label"] == item["label"] for item in parsed["alternatives"])]
    return _envelope(
        situation.situation_id, model, started,
        situation_type=chosen["label"],
        family=chosen.get("family") or "",
        confidence=parsed["confidence"],
        basis=parsed["basis"],
        citations=[_citation(chosen)] + [_citation(row) for row in alternate_rows],
        alternatives=parsed["alternatives"],
        not_established=parsed["not_established"],
        candidates_considered=len(rows),
    )
