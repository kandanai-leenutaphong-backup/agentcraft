"""Cosmos DB Gremlin — three shaped tools instead of one raw traversal.

THE PROMOTION THIS RECORDS
--------------------------
A raw `query_gremlin(query)` tool ran at a **44% hard error rate** on a
live agent: the model authoring invalid traversals, each costing a turn.
Replacing it with shaped tools over the same graph made
`GraphSyntaxException` **unreachable** — there is no traversal text for the
caller to get wrong — and cut error noise 75%.

Three tools, because a graph is asked three questions: what is this, what
is next to it, and what does the neighbourhood look like. Each takes an id
and a label, never a traversal.

RESULT SHAPES AND THEIR CARDS
-----------------------------
`graph_node`       -> table    -> `tabular` archetype
`graph_neighbours` -> table    -> `tabular` archetype
`graph_summary`    -> {nodes, edges, summary} -> `graph` archetype

Run it::

    python3 examples/azure/graph_gremlin.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backends import FakeGremlin  # noqa: E402

from toolshape import (  # noqa: E402
    Param,
    ToolSpec,
    bounded_list,
    identifier,
    integer_range,
    one_of,
    purpose_built,
    table,
)

# Archetype each tool's envelope maps to. The selftest asserts these are
# real archetype keys, so a renamed renderer cannot silently orphan a tool.
ARCHETYPES = {
    "graph_node": "tabular",
    "graph_neighbours": "tabular",
    "graph_summary": "graph",
}

BACKEND = FakeGremlin()          # real: GremlinConnector(...).execute
NODE_LABELS = ("site", "asset")
EDGE_LABELS = ("contains", "feeds")

# Gremlin ids reach a traversal as string literals. The identifier validator
# already excludes quotes, so the id cannot break out of the literal — but
# the cap is what stops a caller pasting a whole document as an id.
_node_id = identifier(max_len=64, example="site-1")


GRAPH_NODE = ToolSpec(
    name="graph_node",
    purpose="Return one graph node and all its properties.",
    call_when=(
        "Call this FIRST when investigating anything in the graph — it "
        "returns the vocabulary (labels, property names, ids) that the other "
        "graph tools need. Use an id from a previous result."
    ),
    params=[
        Param("node_id", "Node id, as returned by any graph tool.", validator=_node_id),
    ],
    returns="A one-row table of the node's properties.",
    dedupe_on=("node_id",),
    replaces="query_gremlin",
)


@purpose_built(GRAPH_NODE)
def graph_node(node_id: str):
    """The traversal is code. There is no syntax for the caller to get wrong."""
    rows = BACKEND.submit(f"g.V('{node_id}').valueMap(true)")
    columns = sorted({key for row in rows for key in row}) or ["id", "label"]
    return columns, rows


GRAPH_NEIGHBOURS = ToolSpec(
    name="graph_neighbours",
    purpose="Return the nodes directly connected to one node.",
    call_when=(
        "After graph_node, to walk one hop out. Use the same node id and, "
        "optionally, one of the edge labels graph_node reported."
    ),
    params=[
        Param("node_id", "Node id, as returned by graph_node.", validator=_node_id),
        Param(
            "edge_label",
            "Restrict to one edge label, one of the values listed.",
            validator=one_of(EDGE_LABELS),
            required=False,
        ),
        Param(
            "limit",
            "Maximum neighbours to return; the traversal is capped either way.",
            validator=integer_range(1, 200),
            required=False,
            default=50,
        ),
    ],
    returns="A table of neighbouring nodes.",
    dedupe_on=("node_id", "edge_label"),
    replaces="query_gremlin",
)


@purpose_built(GRAPH_NEIGHBOURS)
def graph_neighbours(node_id: str, edge_label: str | None = None, limit: int = 50):
    # The limit is injected here, not asked for: an uncapped traversal on a
    # populated graph returns the graph.
    step = f".both('{edge_label}')" if edge_label else ".both()"
    rows = BACKEND.submit(f"g.V('{node_id}'){step}.valueMap(true).limit({limit})")
    columns = sorted({key for row in rows for key in row}) or ["id", "label"]
    return columns, rows


GRAPH_SUMMARY = ToolSpec(
    name="graph_summary",
    purpose="Return the neighbourhood around a node as nodes plus edges.",
    call_when=(
        "When you need the shape of a neighbourhood rather than a list — for "
        "example to see how several nodes connect. Use an id from graph_node."
    ),
    params=[
        Param("node_id", "Node id, as returned by graph_node.", validator=_node_id),
        Param(
            "labels",
            "Node labels to include, from the labels graph_node reported.",
            validator=bounded_list(one_of(NODE_LABELS), cap=4),
            required=False,
        ),
    ],
    returns="{nodes: [...], edges: [...], summary: '...'}",
    dedupe_on=("node_id",),
    replaces="query_gremlin",
)


@purpose_built(GRAPH_SUMMARY)
def graph_summary(node_id: str, labels: list[str] | None = None):
    """Returns a dict, so the wrapper serialises it as-is for the graph card."""
    nodes = BACKEND.submit(f"g.V('{node_id}').both().valueMap(true)")
    if labels:
        nodes = [n for n in nodes if n.get("label") in labels]
    edges = [e for e in FakeGremlin.EDGES if e["from"] == node_id]
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": f"{len(nodes)} node(s) and {len(edges)} edge(s) around {node_id}.",
        "scope": {"node_id": node_id},
    }


def demo() -> list[str]:
    """Every call this example makes, as returned envelopes."""
    return [
        graph_node(node_id="site-1"),
        graph_neighbours(node_id="site-1", edge_label="contains"),
        graph_neighbours(node_id="site-1", edge_label="explodes"),      # refused
        graph_summary(node_id="site-1"),
        graph_node(node_id="site-unknown"),                             # empty
    ]


if __name__ == "__main__":
    for payload in demo():
        print(json.dumps(json.loads(payload), indent=2)[:400])
        print("-" * 60)
