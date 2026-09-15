"""Accumulating graph model: nodes and edges keyed once, aggregated over every row."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .canonical import bucket_key

#: Vertex labels the builder is allowed to emit. Anything else is a bug, not a new type.
NODE_LABELS = (
    "Host", "Identity", "IpAddress", "DnsName", "KerberosService",
    "Application", "Session", "Sensor", "SecurityAlert", "VaultSafe", "SoftwareReference",
    "Domain",
)

#: Relationships that hold for the whole export because they describe what a thing *is*.
#: They carry no time buckets and are shown before any window is chosen.
STRUCTURAL_EDGES = (
    "POSSIBLY_SAME_AS", "SPN_FOR_HOST", "RESOLVES_TO_HOST", "MONITORS_HOST",
    "CUSTODIES_ACCOUNT", "MEMBER_OF_DOMAIN",
)

#: Relationships that happened at a time. Each carries per-bucket counts for windowing.
EVENT_EDGES = (
    "AUTHENTICATED_TO", "REQUESTED_SERVICE", "SIGNED_IN_FROM", "HAS_ADDRESS",
    "QUERIED", "RESOLVED_BY", "CONNECTED_TO", "USED_APPLICATION",
    "OPENED_SESSION", "SESSION_ON_HOST", "OBSERVED_BY", "ALERT_ON_HOST",
    "ALERT_NAMES_IDENTITY", "USED_ACCOUNT", "RETRIEVED_FROM_SAFE", "REFERENCED_SOFTWARE",
)

EDGE_LABELS = STRUCTURAL_EDGES + EVENT_EDGES


@dataclass(slots=True)
class Node:
    node_id: str
    label: str
    name: str
    props: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, set[str]] = field(default_factory=dict)
    event_count: int = 0
    first_seen: str = ""
    last_seen: str = ""

    def observe(self, key: str, value: str) -> None:
        if value:
            self.observed.setdefault(key, set()).add(value)

    def touch(self, source_time: str) -> None:
        self.event_count += 1
        if source_time:
            if not self.first_seen or source_time < self.first_seen:
                self.first_seen = source_time
            if not self.last_seen or source_time > self.last_seen:
                self.last_seen = source_time


@dataclass(slots=True)
class Edge:
    edge_id: str
    label: str
    from_id: str
    to_id: str
    kind: str = "event"
    props: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, set[str]] = field(default_factory=dict)
    buckets: dict[str, int] = field(default_factory=dict)
    event_count: int = 0
    first_seen: str = ""
    last_seen: str = ""

    def observe(self, key: str, value: str) -> None:
        if value:
            self.observed.setdefault(key, set()).add(value)

    def touch(self, source_time: str) -> None:
        self.event_count += 1
        if not source_time:
            return
        if not self.first_seen or source_time < self.first_seen:
            self.first_seen = source_time
        if not self.last_seen or source_time > self.last_seen:
            self.last_seen = source_time
        if self.kind == "event":
            key = bucket_key(source_time)
            if key:
                self.buckets[key] = self.buckets.get(key, 0) + 1


class Graph:
    """Insertion-ordered node and edge stores with idempotent upsert."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self.dropped: dict[str, int] = {}

    def node(self, label: str, node_id: str, name: str, **props: Any) -> Node:
        if label not in NODE_LABELS:
            raise ValueError(f"undeclared node label: {label}")
        existing = self.nodes.get(node_id)
        if existing is None:
            existing = Node(node_id=node_id, label=label, name=name, props=dict(props))
            self.nodes[node_id] = existing
        else:
            if existing.label != label:
                raise ValueError(f"node {node_id} claimed by {existing.label} and {label}")
            existing.props.update({key: value for key, value in props.items() if value not in (None, "")})
        return existing

    def edge(self, label: str, from_id: str, to_id: str, **props: Any) -> Edge:
        if label not in EDGE_LABELS:
            raise ValueError(f"undeclared edge label: {label}")
        edge_id = f"{from_id}--{label}--{to_id}"
        existing = self.edges.get(edge_id)
        if existing is None:
            existing = Edge(edge_id=edge_id, label=label, from_id=from_id, to_id=to_id,
                            kind="structural" if label in STRUCTURAL_EDGES else "event",
                            props=dict(props))
            self.edges[edge_id] = existing
        else:
            existing.props.update({key: value for key, value in props.items() if value not in (None, "")})
        return existing

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def remove_nodes(self, node_ids: set[str]) -> None:
        for node_id in node_ids:
            self.nodes.pop(node_id, None)

    def prune_dangling_edges(self) -> int:
        stale = [key for key, edge in self.edges.items()
                 if edge.from_id not in self.nodes or edge.to_id not in self.nodes]
        for key in stale:
            del self.edges[key]
        return len(stale)
