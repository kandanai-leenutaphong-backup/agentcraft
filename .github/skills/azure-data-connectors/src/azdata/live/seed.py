"""The seed dataset — forty synthetic assets, projected four ways.

WHY THIS EXISTS
---------------
Verification needs something to diff. An empty environment answers every
question with zero and every digest with the digest of nothing, so a
snapshot/operate/snapshot cycle proves nothing at all. This module is the
fixed content each live service carries so that the verification plane has
a baseline that is not trivially satisfied.

**One dataset, four projections.** :data:`ASSETS` is the source of truth;
``search_documents``, ``cosmos_items``, ``gremlin_elements`` and
``kusto_rows`` are views of it. That direction matters: if each service
had its own fixture, the four would drift, and a live test that compared
Search against Cosmos would be comparing two different truths and calling
the difference a bug. Every projection agrees on the forty asset ids by
construction, and ``tests/unit/test_live_environment.py`` pins that.

**Domain-blind.** The schema is invented — asset id, site, kind, status,
a reading, a timestamp, a short text blurb and a small vector. No
customer's field names, no customer's semantics. A library that shipped a
real schema as its test data would leak the schema of whoever it was
extracted from.

**Deterministic.** Values come from a fixed seed, so the same forty rows
appear on every machine and a digest recorded in a notebook note today
still matches next month. Nothing here reads the clock.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import random
from typing import Any, Mapping, Sequence

#: How many assets the environment carries. Small enough to seed in
#: seconds, large enough that a partition-key mistake shows up.
ASSET_COUNT = 40

#: Four sites, so the Cosmos container has four partitions and a
#: cross-partition query is genuinely cross-partition.
SITES = ("north", "south", "east", "west")

KINDS = ("pump", "valve", "sensor", "compressor", "turbine")
STATUSES = ("healthy", "degraded", "offline")

#: Vector width. Small on purpose: a realistic 1536-wide embedding would
#: make this module 60,000 numbers long for no extra test signal.
VECTOR_DIMS = 8

#: The three Gremlin edge labels of SPEC 7.2.
EDGE_LABELS = ("feeds", "monitors", "colocated_with")

#: 60 edges over 40 vertices, per SPEC 7.2.
EDGE_COUNT = 60

#: Kusto column types for the projected rows, in table order.
KUSTO_COLUMNS: Mapping[str, str] = {
    "AssetId": "string",
    "Site": "string",
    "Kind": "string",
    "Status": "string",
    "Reading": "real",
    "ObservedAt": "datetime",
}

_SEED = 20260831


def _build_assets() -> tuple[dict[str, Any], ...]:
    """The forty records, generated once from a fixed seed."""
    rng = random.Random(_SEED)
    assets: list[dict[str, Any]] = []
    for index in range(ASSET_COUNT):
        site = SITES[index % len(SITES)]
        kind = KINDS[index % len(KINDS)]
        status = STATUSES[index % len(STATUSES)]
        assets.append(
            {
                "asset_id": f"asset-{index:03d}",
                "site": site,
                "kind": kind,
                "status": status,
                "reading": round(rng.uniform(0.0, 100.0), 3),
                # Fixed date, incremented per record: nothing here reads a
                # clock, so the dataset is byte-identical on every machine.
                "observed_at": f"2026-01-{(index % 28) + 1:02d}T00:00:00Z",
                "blurb": f"{kind} {index:03d} at {site} site reporting {status}",
                "vector": [
                    round(rng.uniform(-1.0, 1.0), 6) for _ in range(VECTOR_DIMS)
                ],
            }
        )
    return tuple(assets)


#: The source of truth. Every projection below is a view of this.
ASSETS: tuple[dict[str, Any], ...] = _build_assets()


def asset_ids() -> list[str]:
    """The forty keys, in dataset order. Every projection agrees on these."""
    return [asset["asset_id"] for asset in ASSETS]


def search_documents(assets: Sequence[Mapping[str, Any]] = ASSETS) -> list[dict]:
    """Index ``azdata-assets``: keyword fields plus one vector field."""
    return [
        {
            "id": asset["asset_id"],
            "site": asset["site"],
            "kind": asset["kind"],
            "status": asset["status"],
            "blurb": asset["blurb"],
            "vector": list(asset["vector"]),
        }
        for asset in assets
    ]


def cosmos_items(assets: Sequence[Mapping[str, Any]] = ASSETS) -> list[dict]:
    """Container ``assets``, partition key ``/site`` — four partitions."""
    return [
        {
            "id": asset["asset_id"],
            "site": asset["site"],
            "kind": asset["kind"],
            "status": asset["status"],
            "reading": asset["reading"],
            "observed_at": asset["observed_at"],
        }
        for asset in assets
    ]


def gremlin_vertices(assets: Sequence[Mapping[str, Any]] = ASSETS) -> list[dict]:
    """Graph ``assets``: one vertex per record, partitioned by site."""
    return [
        {
            "id": asset["asset_id"],
            "site": asset["site"],
            "kind": asset["kind"],
            "status": asset["status"],
        }
        for asset in assets
    ]


def gremlin_edges(assets: Sequence[Mapping[str, Any]] = ASSETS) -> list[dict]:
    """Sixty edges over three labels, derived deterministically.

    Deliberately not random: the offsets rotate through the vertex list so
    the graph is connected, every label is used, and no edge is a self
    loop — which a random pairing would produce and which then reads as a
    seeding bug months later.
    """
    ids = [asset["asset_id"] for asset in assets]
    count = len(ids)
    edges: list[dict] = []
    for index in range(EDGE_COUNT):
        label = EDGE_LABELS[index % len(EDGE_LABELS)]
        source = index % count
        # Offsets 1, 3 and 7 are coprime with 40, so each label's edges
        # walk the whole ring rather than closing into a short cycle.
        offset = (1, 3, 7)[index % len(EDGE_LABELS)]
        target = (source + offset) % count
        edges.append(
            {
                "id": f"edge-{index:03d}",
                "label": label,
                "from": ids[source],
                "to": ids[target],
            }
        )
    return edges


def gremlin_elements(
    assets: Sequence[Mapping[str, Any]] = ASSETS,
) -> dict[str, list[dict]]:
    """Both halves of the graph projection, so a caller cannot seed one."""
    return {"vertices": gremlin_vertices(assets), "edges": gremlin_edges(assets)}


def kusto_rows(assets: Sequence[Mapping[str, Any]] = ASSETS) -> list[dict]:
    """Table ``Assets``: the columns declared in :data:`KUSTO_COLUMNS`."""
    return [
        {
            "AssetId": asset["asset_id"],
            "Site": asset["site"],
            "Kind": asset["kind"],
            "Status": asset["status"],
            "Reading": asset["reading"],
            "ObservedAt": asset["observed_at"],
        }
        for asset in assets
    ]


#: Field name each projection uses for the shared asset id, so a caller
#: comparing two services knows which key to join on without guessing.
KEY_FIELDS: Mapping[str, str] = {
    "search": "id",
    "cosmos": "id",
    "gremlin": "id",
    "kusto": "AssetId",
}


def projection_keys() -> dict[str, list[str]]:
    """The key list each projection produces, for the agreement check."""
    return {
        "search": [doc["id"] for doc in search_documents()],
        "cosmos": [item["id"] for item in cosmos_items()],
        "gremlin": [vertex["id"] for vertex in gremlin_vertices()],
        "kusto": [row["AssetId"] for row in kusto_rows()],
    }


__all__ = [
    "ASSETS",
    "ASSET_COUNT",
    "EDGE_COUNT",
    "EDGE_LABELS",
    "KEY_FIELDS",
    "KINDS",
    "KUSTO_COLUMNS",
    "SITES",
    "STATUSES",
    "VECTOR_DIMS",
    "asset_ids",
    "cosmos_items",
    "gremlin_edges",
    "gremlin_elements",
    "gremlin_vertices",
    "kusto_rows",
    "projection_keys",
    "search_documents",
]
