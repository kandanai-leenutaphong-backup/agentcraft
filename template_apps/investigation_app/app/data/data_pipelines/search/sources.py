"""Records in, from the normalised ATT&CK corpora on disk. Read-only, one pass each.

The reviewed telemetry exports are not read here and never were the right source for a
knowledge index. Both files below are produced by `cyber_kb/normalize`, carry their own
pinned commit, and hold several mirrors; only the ATT&CK records are yielded.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from .documents import MITRE_SOURCE

#: Where the normalised corpora land.
NORMALIZED_DIR = Path("cyber_kb/normalized")
CLASSIFICATION_FILE = "classification.jsonl"
CORPUS_FILE = "corpus.jsonl"
CLASSIFICATION_BUILD = "classification_build.json"
CORPUS_BUILD = "build.json"

#: An ATT&CK object the upstream bundle has withdrawn is not active knowledge.
_RETIRED_FLAGS = ("revoked", "deprecated", "x_mitre_deprecated")


def _retired(record: Mapping[str, Any]) -> bool:
    fields = record.get("source_fields")
    fields = fields if isinstance(fields, Mapping) else {}
    return any(bool(record.get(flag)) or bool(fields.get(flag)) for flag in _RETIRED_FLAGS)


def _read(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found; build the normalised corpora under cyber_kb/normalize first"
        )
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def mitre_records(directory: Path = NORMALIZED_DIR) -> Iterator[dict[str, Any]]:
    """Every active ATT&CK record from both normalised corpora, classification first."""
    for name in (CLASSIFICATION_FILE, CORPUS_FILE):
        for record in _read(directory / name):
            if record.get("source") != MITRE_SOURCE or _retired(record):
                continue
            yield record


def mitre_provenance(directory: Path = NORMALIZED_DIR) -> dict[str, Any]:
    """The pinned commit, licence and retrieval stamp both builds agree on.

    The stamp is a property of the build on disk, not of the moment a load runs, so the
    published index name is reproducible from the same inputs.
    """
    stamps: list[str] = []
    commits: list[str] = []
    licences: list[str] = []
    mirrors: list[str] = []
    for name in (CLASSIFICATION_BUILD, CORPUS_BUILD):
        path = directory / name
        if not path.is_file():
            continue
        build = json.loads(path.read_text(encoding="utf-8"))
        record = (build.get("sources") or {}).get(MITRE_SOURCE) or {}
        for value, bucket in ((record.get("retrieved_at"), stamps),
                              (record.get("commit"), commits),
                              (record.get("license"), licences),
                              (record.get("mirror"), mirrors)):
            if value and str(value) not in bucket:
                bucket.append(str(value))
    if not stamps or not commits:
        raise FileNotFoundError(
            f"no ATT&CK provenance in {directory}/{CLASSIFICATION_BUILD} or {CORPUS_BUILD}"
        )
    return {
        "retrieved_at": max(stamps),
        "commit": commits[0],
        "license": licences[0] if licences else "",
        "mirror": mirrors[0] if mirrors else "",
    }


def index_name(retrieved_at: str, prefix: str = "mitre-attack") -> str:
    """`mitre-attack-20260829t163257z`: lowercase, digits, single dashes."""
    stamp = "".join(character for character in retrieved_at.lower()
                    if character.isalnum())
    return f"{prefix}-{stamp}"


def display_name(retrieved_at: str) -> str:
    """What an analyst reads in the data inventory."""
    return f"MITRE ATT&CK @ {retrieved_at}"


__all__ = [
    "CLASSIFICATION_FILE",
    "CORPUS_FILE",
    "NORMALIZED_DIR",
    "display_name",
    "index_name",
    "mitre_provenance",
    "mitre_records",
]
