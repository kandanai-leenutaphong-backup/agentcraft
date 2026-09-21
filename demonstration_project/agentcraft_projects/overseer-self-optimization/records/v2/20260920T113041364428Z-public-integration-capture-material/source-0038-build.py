"""Build the asset/identity ontology graph from the unified event export."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical import clean
from .extract import derive_structural_edges, extract_row, prune_singleton_sessions
from .model import EDGE_LABELS, EVENT_EDGES, NODE_LABELS, STRUCTURAL_EDGES, Graph

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

NODE_COLUMNS = ["node_id", "label", "name", "event_count", "first_seen", "last_seen", "properties"]
EDGE_COLUMNS = ["edge_id", "label", "kind", "from_id", "to_id", "event_count",
                "first_seen", "last_seen", "buckets", "properties"]


def _packed(node_or_edge: Any) -> str:
    """Merge scalar props and observed value sets into one JSON property bag."""
    payload: dict[str, Any] = {key: value for key, value in node_or_edge.props.items() if value not in (None, "")}
    for key, values in node_or_edge.observed.items():
        cleaned = sorted(value for value in values if value)
        if cleaned:
            payload[key] = cleaned
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_graph(source: Path) -> tuple[Graph, dict[str, Any]]:
    graph = Graph()
    families: Counter[str] = Counter()
    rows = 0
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows += 1
            chosen = extract_row(graph, row)
            families[chosen or "unhandled"] += 1
    structural = derive_structural_edges(graph)
    singletons = prune_singleton_sessions(graph)
    pruned = graph.prune_dangling_edges()

    node_counts = Counter(node.label for node in graph.nodes.values())
    edge_counts = Counter(edge.label for edge in graph.edges.values())
    kind_counts = Counter(edge.kind for edge in graph.edges.values())
    span = [node.first_seen for node in graph.nodes.values() if node.first_seen]
    span += [node.last_seen for node in graph.nodes.values() if node.last_seen]
    report = {
        "source": str(source),
        "source_sha256": _digest(source),
        "source_rows": rows,
        "historical_replay": True,
        "nodes": sum(node_counts.values()),
        "edges": sum(edge_counts.values()),
        "nodes_by_label": {label: node_counts.get(label, 0) for label in NODE_LABELS},
        "edges_by_label": {label: edge_counts.get(label, 0) for label in EDGE_LABELS},
        "edges_by_kind": dict(kind_counts),
        "structural_edges_derived": structural,
        "observed_window": {"start": min(span) if span else "", "end": max(span) if span else ""},
        "rows_by_extractor": dict(families.most_common()),
        "singleton_sessions_pruned": singletons,
        "dangling_edges_pruned": pruned,
        "dropped": dict(sorted(graph.dropped.items())),
    }
    return graph, report


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_graph(graph: Graph, nodes_path: Path, edges_path: Path) -> None:
    nodes_path.parent.mkdir(parents=True, exist_ok=True)
    with nodes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(NODE_COLUMNS)
        for node in graph.nodes.values():
            writer.writerow([node.node_id, node.label, node.name, node.event_count,
                             node.first_seen, node.last_seen, _packed(node)])
    with edges_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(EDGE_COLUMNS)
        for edge in graph.edges.values():
            writer.writerow([edge.edge_id, edge.label, edge.kind, edge.from_id, edge.to_id,
                             edge.event_count, edge.first_seen, edge.last_seen,
                             json.dumps(edge.buckets, sort_keys=True, separators=(",", ":"))
                             if edge.buckets else "",
                             _packed(edge)])


def read_graph(nodes_path: Path, edges_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load the written CSVs back into plain dictionaries for the loader and tests."""
    with nodes_path.open(newline="", encoding="utf-8") as handle:
        nodes = [{**row, "properties": json.loads(row["properties"] or "{}"),
                  "event_count": int(row["event_count"] or 0)}
                 for row in csv.DictReader(handle)]
    with edges_path.open(newline="", encoding="utf-8") as handle:
        edges = [{**row, "properties": json.loads(row["properties"] or "{}"),
                  "buckets": json.loads(row.get("buckets") or "{}"),
                  "event_count": int(row["event_count"] or 0)}
                 for row in csv.DictReader(handle)]
    return nodes, edges


def summarize(graph: Graph, limit: int = 8) -> dict[str, list[str]]:
    """Highest-traffic node per label, for a human check that the build looks sane."""
    ranked: dict[str, list[str]] = {}
    for label in NODE_LABELS:
        members = [node for node in graph.nodes.values() if node.label == label]
        members.sort(key=lambda node: (-node.event_count, node.name))
        ranked[label] = [f"{node.name} ({node.event_count})" for node in members[:limit]]
    return ranked


__all__ = ["build_graph", "read_graph", "summarize", "write_graph", "clean",
           "EVENT_EDGES", "STRUCTURAL_EDGES", "NODE_COLUMNS", "EDGE_COLUMNS"]
