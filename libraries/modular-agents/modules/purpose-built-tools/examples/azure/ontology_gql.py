"""Fabric GraphModel (GQL) — a backend whose failures arrive as HTTP 200.

THE FAILURE THIS TOOL ABSORBS
-----------------------------
A GraphModel query reports its outcome in the *body*, not the status line.
An invalid query comes back 200 with a non-zero status code and no rows, so
a caller checking only the transport reports success with an empty result —
and the model concludes there is nothing there.

The tool converts that into the one thing the caller can act on: an error
envelope carrying the GQL diagnostic. Empty stays empty, and means empty.

RESULT SHAPES AND THEIR CARDS
-----------------------------
`query_ontology` -> {columns, rows, scope} -> `tabular` archetype
                    or {error, detail}     -> the card's error short-circuit

Run it::

    python3 examples/azure/ontology_gql.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backends import FakeGraphModel  # noqa: E402

from toolshape import (  # noqa: E402
    Param,
    ToolSpec,
    bounded_list,
    failure,
    identifier,
    integer_range,
    one_of,
    purpose_built,
)

ARCHETYPES = {"query_ontology": "tabular"}

BACKEND = FakeGraphModel()       # real: GraphConnector(...).execute
ENTITIES = ("Asset", "Site", "WorkOrder")
RELATIONS = ("locatedAt", "supersedes", "raisedAgainst")
MAX_ROWS = 200


QUERY_ONTOLOGY = ToolSpec(
    name="query_ontology",
    purpose="Return modelled entities and their related records.",
    call_when=(
        "When you need what the model *knows* about something rather than what "
        "was measured — attributes, classifications, relationships. Pick the "
        "entity and relation from the listed values."
    ),
    params=[
        Param("entity", "Entity type to return, one of the values listed.",
              validator=one_of(ENTITIES)),
        Param("related_via", "Optional relation to traverse, one of the values listed.",
              validator=one_of(RELATIONS), required=False),
        Param("properties", "Properties to return, from those the entity declares.",
              validator=bounded_list(identifier(max_len=40), cap=12), required=False),
        Param("limit", "Maximum rows to return.",
              validator=integer_range(1, MAX_ROWS), required=False, default=50),
    ],
    returns="A table of the requested properties, one row per entity.",
    dedupe_on=("entity", "related_via", "limit"),
    replaces="execute_gql",
)


@purpose_built(QUERY_ONTOLOGY)
def query_ontology(
    entity: str,
    related_via: str | None = None,
    properties: list[str] | None = None,
    limit: int = 50,
):
    projection = ", ".join(properties) if properties else "*"
    traversal = f"-[:{related_via}]->(m)" if related_via else ""
    gql = f"MATCH (n:{entity}){traversal} RETURN {projection} LIMIT {limit}"

    result = BACKEND.execute(gql)

    # HTTP 200 is not success here. Surfacing the body's diagnostic is the
    # whole reason this tool exists rather than a raw GQL passthrough.
    if result.get("error"):
        return failure(result.get("detail", "the graph model rejected the query"))

    columns = [column["name"] for column in result.get("columns", [])]
    return columns, result.get("data", [])


def demo() -> list[str]:
    return [
        query_ontology(entity="Asset"),
        query_ontology(entity="Asset", related_via="locatedAt", properties=["asset", "site"]),
        query_ontology(entity="BadLabel"),                       # refused: not an entity
        query_ontology(entity="Asset", limit=9999),              # refused: over cap
        query_ontology(entity="WorkOrder"),                      # 200 carrying a GQL error
        query_ontology(entity="Asset", related_via="supersedes"),  # genuinely empty
    ]


if __name__ == "__main__":
    for payload in demo():
        print(json.dumps(json.loads(payload), indent=2)[:400])
        print("-" * 60)
