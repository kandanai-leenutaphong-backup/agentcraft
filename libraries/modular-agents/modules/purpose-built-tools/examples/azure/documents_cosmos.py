"""Cosmos DB NoSQL — documents, and the async tool the SDK forces.

TWO THINGS THIS EXAMPLE SHOWS
-----------------------------
**Async all the way down.** The Cosmos async client yields documents from
an async iterator, so the tool body is `async def` and the wrapper handles
it identically. Nothing about the shape changes.

**Two tools over one container.** Listing and reading are different
questions with different answers — a table of what exists, and one
document's text — and answering both from a single tool would force one of
them into the wrong shape. The split is what lets each map to the card that
suits it.

RESULT SHAPES AND THEIR CARDS
-----------------------------
`list_documents` -> {columns, rows, scope} -> `tabular` archetype
`read_document`  -> {title, document}      -> `document` archetype

Run it::

    python3 examples/azure/documents_cosmos.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backends import FakeCosmos  # noqa: E402

from toolshape import (  # noqa: E402
    Param,
    ToolSpec,
    identifier,
    integer_range,
    one_of,
    purpose_built,
)

ARCHETYPES = {"list_documents": "tabular", "read_document": "document"}

CONTAINER = FakeCosmos()         # real: CosmosContainer.connect(...).container
DOC_KINDS = ("note", "report", "procedure")

# Listing returns metadata only. The body is frequently kilobytes, and a
# list of twenty of them is a context window spent on text nobody asked to
# read — that is what read_document is for.
LIST_COLUMNS = ["id", "kind", "title", "updated"]


LIST_DOCUMENTS = ToolSpec(
    name="list_documents",
    purpose="Return document metadata — id, kind, title, last update.",
    call_when=(
        "Call this FIRST when looking for a document. It returns the ids "
        "read_document needs, and it never returns document bodies."
    ),
    params=[
        Param("kind", "Restrict to one document kind, one of the values listed.",
              validator=one_of(DOC_KINDS), required=False),
        Param("limit", "Maximum documents to list.",
              validator=integer_range(1, 100), required=False, default=25),
    ],
    returns="A table with columns id, kind, title, updated.",
    dedupe_on=("kind", "limit"),
)


@purpose_built(LIST_DOCUMENTS)
async def list_documents(kind: str | None = None, limit: int = 25):
    parameters = []
    query = f"SELECT TOP {limit} c.id, c.kind, c.title, c.updated FROM c"
    if kind:
        query += " WHERE c.kind = @kind"
        parameters.append({"name": "@kind", "value": kind})

    rows = [
        {column: doc.get(column) for column in LIST_COLUMNS}
        async for doc in CONTAINER.query_items(query=query, parameters=parameters)
    ]
    return LIST_COLUMNS, rows


READ_DOCUMENT = ToolSpec(
    name="read_document",
    purpose="Return one document's full text.",
    call_when=(
        "After list_documents, using an id it returned. Read one document at a "
        "time — the bodies are long."
    ),
    params=[
        Param("document_id", "Document id, as returned by list_documents.",
              validator=identifier(max_len=64, example="note-1")),
    ],
    returns="{title: '...', document: '<full text>'}",
    dedupe_on=("document_id",),
)


@purpose_built(READ_DOCUMENT)
async def read_document(document_id: str):
    """Returns a dict, so the document card renders the body as prose."""
    async for doc in CONTAINER.query_items(
        query="SELECT TOP 1 * FROM c WHERE c.id = @id",
        parameters=[{"name": "@id", "value": document_id}],
    ):
        return {
            "title": doc.get("title", document_id),
            "document": doc.get("body", ""),
            "scope": {"document_id": document_id},
        }
    # No document is an answer, not a failure: an empty body renders as the
    # document card's empty state rather than an error banner.
    return {"title": document_id, "document": "", "scope": {"document_id": document_id}}


async def demo() -> list[str]:
    return [
        await list_documents(),
        await list_documents(kind="note"),
        await list_documents(kind="invoice"),          # refused: not a kind
        await read_document(document_id="note-1"),
        await read_document(document_id="note-404"),   # empty document
    ]


if __name__ == "__main__":
    for payload in asyncio.run(demo()):
        print(json.dumps(json.loads(payload), indent=2)[:400])
        print("-" * 60)
