"""Upload records into one keyword index. The reusable half of the publish.

WHAT THIS IS ALLOWED TO TOUCH
-----------------------------
One search service, and only the index it is told to write. It reads records the
caller supplies and writes nowhere else: no ADX, no Gremlin, no canonical
dataset, no pipeline it did not run.

RESUMING, AND WHY IT CANNOT DUPLICATE
-------------------------------------
Every key is derived from the record's own stable id and nothing else, so
a re-run of the whole file overwrites the same documents. A checkpoint file only
saves the time of re-uploading what is already there; correctness does not
depend on it. A batch is committed to the checkpoint only after the service has
reported every document in it as succeeded — `SearchIndexClient` raises on the
first per-document failure inside a 200 or 207, so a partially failed batch
never advances the mark.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from template_foundations.azure_search import IndexSpec, SearchError, SearchIndexClient, render_index

#: The service's own ceiling is 1000 documents or ~16 MB. Raw payloads here are
#: clamped to 8 KB, so 500 documents is at most ~5 MB of body.
BATCH_SIZE = 500


class LoadRefused(RuntimeError):
    """The load cannot proceed without doing something destructive or dishonest."""


@dataclass(frozen=True, slots=True)
class LoadReport:
    index: str
    rows_read: int
    uploaded: int
    skipped: int
    document_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "rows_read": self.rows_read,
            "uploaded": self.uploaded,
            "skipped_already_loaded": self.skipped,
            "document_count": self.document_count,
        }


def ensure_index(client: SearchIndexClient, spec: IndexSpec) -> str:
    """Create the index, or prove the existing one already has this exact shape.

    Returns "created" or "unchanged". An index that exists with a different
    shape is refused rather than reshaped: the service drops every document when
    a field is removed, retyped or rekeyed, and losing 800,000 documents to a
    field rename is not a thing a loader may decide on its own.
    """
    stored = client.get_index(spec.name)
    if stored is None:
        client.create_or_update_index(spec)
        if client.get_index(spec.name) is None:
            raise LoadRefused(f"index {spec.name!r} did not exist after create")
        return "created"

    wanted = render_index(spec)
    have = {field["name"]: field for field in stored.get("fields", [])}
    drift = []
    for field in wanted["fields"]:
        current = have.get(field["name"])
        if current is None:
            drift.append(f"{field['name']}: missing")
            continue
        for prop in ("type", "key", "searchable", "filterable", "sortable", "facetable"):
            if bool(current.get(prop)) != bool(field[prop]) and prop != "type":
                drift.append(f"{field['name']}.{prop}: {current.get(prop)} != {field[prop]}")
            elif prop == "type" and current.get("type") != field["type"]:
                drift.append(f"{field['name']}.type: {current.get('type')} != {field['type']}")
    if drift:
        raise LoadRefused(
            f"index {spec.name!r} exists with a different shape and holds "
            f"{client.document_count(spec.name)} documents. Changing it here would drop them. "
            f"Differences: {'; '.join(drift[:8])}"
        )
    return "unchanged"


def _checkpoint_read(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("rows_committed", 0))
    except (ValueError, OSError):
        return 0


def _checkpoint_write(path: Path | None, index: str, rows: int) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"index": index, "rows_committed": rows}, indent=2) + "\n", encoding="utf-8"
    )


def _batches(rows: Iterable[Mapping[str, Any]], size: int) -> Iterator[list[Mapping[str, Any]]]:
    batch: list[Mapping[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_documents(
    client: SearchIndexClient,
    *,
    index: str,
    rows: Iterable[Mapping[str, Any]],
    build: Callable[[Mapping[str, Any]], dict[str, Any]],
    checkpoint: Path | None = None,
    batch_size: int = BATCH_SIZE,
    progress: Callable[[int, int], None] | None = None,
) -> LoadReport:
    """Upload every row as a document. Raises on the first document the service refused."""
    already = _checkpoint_read(checkpoint)
    read = 0
    uploaded = 0
    for batch in _batches(rows, batch_size):
        read += len(batch)
        if read <= already:
            continue
        try:
            result = client.upload_documents(
                index, [build(row) for row in batch], batch_size=batch_size
            )
        except SearchError as exc:
            # The mark stays where it was, so a re-run retries this batch rather
            # than stepping over it.
            raise LoadRefused(f"index {index!r}: {exc}") from exc
        uploaded += int(result["succeeded"])
        _checkpoint_write(checkpoint, index, read)
        if progress is not None:
            progress(read, uploaded)
    return LoadReport(
        index=index,
        rows_read=read,
        uploaded=uploaded,
        skipped=min(already, read),
        document_count=client.search_count(index),
    )


__all__ = ["BATCH_SIZE", "LoadRefused", "LoadReport", "ensure_index", "load_documents"]
