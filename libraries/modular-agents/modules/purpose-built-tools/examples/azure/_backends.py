"""Stand-in backends for the Azure examples — no cloud account required.

Each fake records the query text or arguments it received and returns a
small canned result, so an example can be run and asserted offline while
still showing the real call shape.

Swapping in a real client is a one-line change in each example, marked
there with a `# real:` comment. These examples pair naturally with a
connector library, but this box deliberately depends on none — the tool
layer's contract is with the *result shape*, not with any SDK.
"""

from __future__ import annotations

from typing import Any


class RecordingBackend:
    """Base fake: remembers every call so an example can assert on it."""

    def __init__(self) -> None:
        self.calls: list[Any] = []


class FakeGremlin(RecordingBackend):
    """Cosmos DB Gremlin. Returns TinkerPop-shaped property maps."""

    NODES = {
        "asset-1": {"id": "asset-1", "label": "asset", "name": "Pump A", "kind": "pump"},
        "asset-2": {"id": "asset-2", "label": "asset", "name": "Valve B", "kind": "valve"},
        "site-1": {"id": "site-1", "label": "site", "name": "SITE_A"},
    }
    EDGES = [
        {"from": "site-1", "to": "asset-1", "label": "contains"},
        {"from": "site-1", "to": "asset-2", "label": "contains"},
        {"from": "asset-1", "to": "asset-2", "label": "feeds"},
    ]

    def submit(self, query: str) -> list[dict]:
        self.calls.append(query)
        if "site-unknown" in query:
            return []
        if ".both(" in query or ".out(" in query:
            return [self.NODES[e["to"]] for e in self.EDGES if e["from"] == "site-1"]
        return [self.NODES["site-1"]]


class FakeKusto(RecordingBackend):
    """Fabric Eventhouse / Azure Data Explorer. Returns {columns, rows}."""

    ROWS = [
        {"at": "2026-04-15T10:01:00", "site": "SITE_A", "kind": "trip", "value": 11.4},
        {"at": "2026-04-15T10:04:00", "site": "SITE_A", "kind": "alarm", "value": 9.8},
    ]

    def execute(self, database: str, query: str) -> dict:
        self.calls.append({"database": database, "query": query})
        if "SITE_NONE" in query:
            return {"columns": [], "rows": []}
        return {
            "columns": [
                {"name": "at", "type": "datetime"},
                {"name": "site", "type": "string"},
                {"name": "kind", "type": "string"},
                {"name": "value", "type": "real"},
            ],
            "rows": list(self.ROWS),
        }


class FakeSearch(RecordingBackend):
    """Azure AI Search. Returns raw index documents, schema and all."""

    DOCS = [
        {
            "chunk_id": "d1",
            "title": "Pump maintenance procedure",
            "chunk": "Isolate the pump before removing the coupling guard. " * 8,
            "filename": "procedures/pumps.pdf",
            "@search.score": 4.318,
        },
        {
            "chunk_id": "d2",
            "title": "Valve inspection checklist",
            "chunk": "Check the stem packing for weeping at operating pressure.",
            "filename": "procedures/valves.pdf",
            "@search.score": 2.107,
        },
    ]

    def search(self, **params: Any) -> list[dict]:
        self.calls.append(params)
        if params.get("search_text") == "nothing at all":
            return []
        return [dict(doc) for doc in self.DOCS[: params.get("top", 5)]]


class FakeGraphModel(RecordingBackend):
    """Fabric GraphModel over GQL. Returns {columns, data} or {error, detail}."""

    def execute(self, gql: str) -> dict:
        self.calls.append(gql)
        # A rejected query still arrives as HTTP 200 with a body status code.
        if "WorkOrder" in gql:
            return {"error": True, "detail": "GQL 42001: entity 'WorkOrder' is not published"}
        if "supersedes" in gql:
            return {"columns": [{"name": "asset"}], "data": []}
        return {
            "columns": [{"name": "asset"}, {"name": "site"}, {"name": "installed"}],
            "data": [
                {"asset": "Pump A", "site": "SITE_A", "installed": "2019-06-01"},
                {"asset": "Valve B", "site": "SITE_A", "installed": "2021-02-14"},
            ],
        }


class FakeCosmos(RecordingBackend):
    """Cosmos DB NoSQL. Async iteration, matching the real container client."""

    DOCS = [
        {
            "id": "note-1",
            "kind": "note",
            "title": "Commissioning note",
            "body": "# Commissioning\n\nPump A commissioned at reduced speed.",
            "updated": "2026-04-14T08:00:00",
        },
        {
            "id": "note-2",
            "kind": "note",
            "title": "Handover note",
            "body": "Valve B left in manual.",
            "updated": "2026-04-15T17:30:00",
        },
    ]

    async def query_items(self, query: str, parameters: list[dict] | None = None):
        self.calls.append({"query": query, "parameters": parameters or []})
        wanted = next(
            (p["value"] for p in (parameters or []) if p["name"] == "@id"), None
        )
        for doc in self.DOCS:
            if wanted is None or doc["id"] == wanted:
                yield dict(doc)


__all__ = [
    "FakeCosmos",
    "FakeGraphModel",
    "FakeGremlin",
    "FakeKusto",
    "FakeSearch",
    "RecordingBackend",
]
