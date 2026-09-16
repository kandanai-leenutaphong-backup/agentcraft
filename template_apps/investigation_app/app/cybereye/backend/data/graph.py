"""Read-only Cosmos DB for Gremlin access for the ontology graph tab.

The graph is a derived, historical view of the static export: vertices are observed
entities and edges are observed relationships. Nothing here writes to the graph.
"""

from __future__ import annotations

import json
import time
from typing import Any

from azdata.graph_read import GraphReadConfig, GraphUnavailable, GremlinReader, scalar as _scalar

from ..config import settings
#: Cosmos answers a traversal in roughly 700-900 ms, so identical panels are cached briefly.
CACHE_SECONDS = 120.0
MAX_NEIGHBOURS = 220
class GraphNotFound(LookupError):
    """The graph answered successfully but the requested vertex does not exist."""


#: Classes an analyst navigates *through*. Excluding DnsName and IpAddress from the
#: expansion frontier is what keeps a second hop bounded: with them included, two hops from
#: any account reach 1,296 of the 1,308 vertices by way of the DNS long tail.
CORE_LABELS = ("Host", "Identity", "KerberosService", "VaultSafe", "SoftwareReference",
               "SecurityAlert", "Domain", "Session", "Application")
#: Classes a mention in the analysis can point at.
MENTION_LABELS = CORE_LABELS + ("IpAddress",)
MAX_DEPTH = 3
#: More than this on one canvas stops being a comparison and starts being the whole graph.
MAX_SELECTION = 8

#: How much of a multi-entity selection to draw. `only` answers "how do these relate"
#: without the surrounding noise; the wider scopes are opt-in from there.
SCOPES = ("only", "shared", "all")
DEFAULT_SCOPE = "only"


def _labels(names: tuple[str, ...]) -> str:
    return ",".join(f"'{name}'" for name in names)


def _apply_scope(payload: dict[str, Any], scope: str) -> dict[str, Any]:
    """Narrow a selection to the picked entities, optionally plus where their reaches meet.

    An unrecognised scope narrows rather than widens, so a bad parameter cannot flood the
    canvas with a traversal the analyst never asked for.
    """
    if scope == "all":
        return payload | {"scope": "all"}
    chosen = scope if scope in SCOPES else DEFAULT_SCOPE
    keep = set(payload["selected"])
    if chosen == "shared":
        keep |= set(payload["shared"])
    return payload | {
        "scope": chosen,
        "nodes": [node for node in payload["nodes"] if node["id"] in keep],
        "edges": [edge for edge in payload["edges"]
                  if edge["from"] in keep and edge["to"] in keep],
    }


def _window_count(buckets: dict[str, int], start: str, end: str) -> int:
    """Sum the 15-minute buckets whose start falls inside the window."""
    if not start and not end:
        return sum(buckets.values())
    lower, upper = start[:16], end[:16]
    return sum(count for key, count in buckets.items()
               if (not lower or key >= lower) and (not upper or key <= upper))


def _apply_window(payload: dict[str, Any], start: str, end: str) -> dict[str, Any]:
    """Keep every structural edge; keep an event edge only if it fired inside the window.

    Structural edges describe what a thing *is*, so a window cannot make them untrue. Event
    edges are re-scored to the window rather than showing their whole-export total.
    """
    kept: list[dict[str, Any]] = []
    for edge in payload.get("edges", []):
        if edge.get("kind") == "structural":
            kept.append(edge)
            continue
        if not (start or end):
            continue
        count = _window_count(edge.get("buckets", {}), start, end)
        if count:
            kept.append({**edge, "event_count": count, "window_scoped": True})
    payload["edges"] = kept
    payload["window"] = {"start": start, "end": end, "bucket_minutes": 15}
    return payload


class GraphService:
    def __init__(
        self,
        *,
        account: str = "",
        database: str = "",
        graph: str = "",
        resource_group: str = "",
        subscription: str = "",
        credential: Any = None,
        reader: GremlinReader | None = None,
    ) -> None:
        # Every coordinate is overridable so a second graph — or a second account —
        # is reachable without a second auth path, and so the read-only key is
        # resolved against the account actually being read rather than the
        # configured default. Unset means the configured default, which is what
        # every existing caller gets.
        self.account = account or settings.graph_account
        self.database = database or settings.graph_database
        self.graph = graph or settings.graph_name
        self.resource_group = resource_group or settings.graph_resource_group
        self.subscription = subscription or settings.graph_subscription_id
        self._reader = reader or GremlinReader(
            GraphReadConfig(self.account, self.database, self.graph,
                            self.subscription, self.resource_group),
            credential=credential, allow_reads=True,
        )
        self._submit = self._reader.query
        self.sample = self._reader.sample
        self.close = self._reader.close
        self._cache: dict[str, tuple[float, Any]] = {}

    @property
    def reconnects(self) -> int:
        return self._reader.reconnects

    @property
    def target(self) -> tuple[str, str, str]:
        """What this instance reads. Two instances differing here are not the same graph."""
        return (self.account, self.database, self.graph)

    @property
    def configured(self) -> bool:
        return bool(self.account and self.resource_group)

    def status(self) -> dict[str, Any]:
        if not self.configured:
            return {"available": False, "detail": "GREMLIN_ACCOUNT or GREMLIN_RESOURCE_GROUP is unset"}
        try:
            counts = self._cached("counts", lambda: {
                "vertices": int(self._submit("g.V().count()")[0]),
                "edges": int(self._submit("g.E().count()")[0]),
            })
        except Exception as exc:
            return {"available": False, "detail": str(exc)[:200], "account": self.account}
        return {
            "available": True, "account": self.account,
            "database": self.database, "graph": self.graph,
            "historical_replay": True, **counts,
        }

    # ---- traversals ---------------------------------------------------------

    def overview(self) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            vertex_labels = self._first("g.V().groupCount().by(label)") or {}
            edge_labels = self._first("g.E().groupCount().by(label)") or {}
            kinds = self._first("g.E().groupCount().by('kind')") or {}
            # Cosmos min()/max() only accept numbers, so the extent comes from an ordered limit.
            extent = _timestamp(self._submit(
                "g.E().has('kind','event').values('first_seen').order().limit(1)"))
            latest = _timestamp(self._submit(
                "g.E().has('kind','event').values('last_seen').order().by(decr).limit(1)"))
            seeds = self._nodes(
                "g.V().hasLabel('Host','Identity','SecurityAlert','VaultSafe','SoftwareReference')"
                ".order().by('event_count', decr).limit(40).valueMap(true)"
            )
            return {
                "nodes_by_label": {str(k): int(v) for k, v in vertex_labels.items()},
                "edges_by_label": {str(k): int(v) for k, v in edge_labels.items()},
                "edges_by_kind": {str(k): int(v) for k, v in kinds.items()},
                "observed_window": {"start": extent, "end": latest},
                "bucket_minutes": 15,
                "seeds": seeds,
                "historical_replay": True,
            }
        return self._cached("overview", build)

    def core(self, limit: int = 260, start: str = "", end: str = "") -> dict[str, Any]:
        """The entities an analyst navigates first.

        Sessions, applications, sensors, addresses, and DNS names are reachable by expanding
        a node or searching; putting all of them on the opening canvas buries the structure.
        """
        labels = "'Host','Identity','KerberosService','VaultSafe','SoftwareReference','SecurityAlert','Domain'"

        def build() -> dict[str, Any]:
            nodes = self._nodes(
                f"g.V().hasLabel({labels}).order().by('event_count', decr).limit({int(limit)}).valueMap(true)"
            )
            keep = {node["id"] for node in nodes}
            edges = [edge for edge in self._edges(
                f"g.V().hasLabel({labels}).bothE().dedup().limit(1200)"
                ".project('e','from','to').by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())"
            ) if edge["from"] in keep and edge["to"] in keep]
            return {"focus": "", "nodes": nodes, "edges": edges, "historical_replay": True}

        return _apply_window(dict(self._cached(f"core:{limit}", build)), start, end)

    def entities(self) -> list[dict[str, Any]]:
        """Every entity a mention in the analysis could refer to, smallest useful payload."""
        def build() -> list[dict[str, Any]]:
            rows = self._submit(
                f"g.V().hasLabel({_labels(MENTION_LABELS)})"
                ".project('id','label','name','event_count')"
                ".by(id).by(label).by('name').by('event_count')"
            )
            return [{
                "id": str(row.get("id", "")),
                "label": str(row.get("label", "")),
                "name": str(row.get("name", "")),
                "event_count": int(row.get("event_count", 0) or 0),
            } for row in rows if row.get("name")]
        return self._cached("entities", build)

    def _core_edges(self) -> list[dict[str, Any]]:
        """Every core-to-core edge, fetched once.

        There are only 113 of them over 74 vertices, so a multi-hop view filters this in
        process rather than re-running the traversal to collect edges. Re-running it silently
        truncated at three hops and returned almost no edges.
        """
        core = _labels(CORE_LABELS)
        return self._cached("core_edges", lambda: self._edges(
            f"g.V().hasLabel({core}).bothE().where(__.otherV().hasLabel({core})).dedup().limit(900)"
            ".project('e','from','to').by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())"
        ))

    def neighbourhood(self, node_id: str, limit: int = MAX_NEIGHBOURS,
                      start: str = "", end: str = "", depth: int = 1) -> dict[str, Any]:
        bounded = max(1, min(int(limit), MAX_NEIGHBOURS))
        hops = max(1, min(int(depth), MAX_DEPTH))

        def build() -> dict[str, Any]:
            focus = self._nodes("g.V(vid).valueMap(true)", {"vid": node_id})
            if not focus:
                raise GraphNotFound("unknown graph node")
            direct = self._edges(
                f"g.V(vid).bothE().limit({bounded}).project('e','from','to')"
                ".by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())",
                {"vid": node_id},
            )
            if hops == 1:
                neighbours = self._nodes(
                    f"g.V(vid).both().dedup().limit({bounded}).valueMap(true)", {"vid": node_id})
                edges = direct
            else:
                core = _labels(CORE_LABELS)
                neighbours = self._nodes(
                    f"g.V(vid).repeat(__.both().hasLabel({core}).simplePath())"
                    f".times({hops}).emit().dedup().limit({bounded}).valueMap(true)",
                    {"vid": node_id},
                )
                reach = {node["id"] for node in neighbours} | {node_id}
                edges = direct + [edge for edge in self._core_edges()
                                  if edge["from"] in reach and edge["to"] in reach]

            known = {node["id"] for node in focus + neighbours}
            seen: set[str] = set()
            unique = []
            for edge in edges:
                if edge["id"] in seen:
                    continue
                if edge["from"] not in known or edge["to"] not in known:
                    continue
                seen.add(edge["id"])
                unique.append(edge)
            return {
                "focus": node_id,
                "depth": hops,
                "nodes": focus + [node for node in neighbours if node["id"] != node_id],
                "edges": unique,
                "truncated": len(neighbours) >= bounded,
                "historical_replay": True,
            }

        return _apply_window(dict(self._cached(f"hood:{node_id}:{bounded}:{hops}", build)), start, end)

    def _reach(self, node_id: str, hops: int, bounded: int) -> list[dict[str, Any]]:
        if hops == 1:
            return self._nodes(
                f"g.V(vid).both().dedup().limit({bounded}).valueMap(true)", {"vid": node_id})
        core = _labels(CORE_LABELS)
        return self._nodes(
            f"g.V(vid).repeat(__.both().hasLabel({core}).simplePath())"
            f".times({hops}).emit().dedup().limit({bounded}).valueMap(true)",
            {"vid": node_id},
        )

    def _direct_edges(self, node_id: str, bounded: int) -> list[dict[str, Any]]:
        return self._edges(
            f"g.V(vid).bothE().limit({bounded}).project('e','from','to')"
            ".by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())",
            {"vid": node_id},
        )

    def _edges_between(self, node_id: str, others: list[str]) -> list[dict[str, Any]]:
        """Edges from one selection straight to another, asked for without the fan-out limit.

        A hub's first 220 edges need not include the one the analyst selected against, so the
        pairing cannot be left to fall out of `_direct_edges`.
        """
        if not others:
            return []
        return self._edges(
            "g.V(vid).bothE().where(__.otherV().hasId(within(others)))"
            ".project('e','from','to').by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())",
            {"vid": node_id, "others": others},
        )

    def selection(self, node_ids: list[str], limit: int = MAX_NEIGHBOURS, start: str = "",
                  end: str = "", depth: int = 2, scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
        """Several entities at once, narrowed by `scope`.

        `only` is the picks and the relationships between them, `shared` adds the nodes two or
        more of them reach, `all` is the whole union. The reach is computed either way, so the
        analyst can widen without a refetch.
        """
        wanted = [node_id for node_id in dict.fromkeys(node_ids) if node_id.strip()][:MAX_SELECTION]
        if not wanted:
            raise GraphUnavailable("no entity selected")
        bounded = max(1, min(int(limit), MAX_NEIGHBOURS))
        hops = max(1, min(int(depth), MAX_DEPTH))

        def build() -> dict[str, Any]:
            focus: list[dict[str, Any]] = []
            reaches: list[set[str]] = []
            nodes: dict[str, dict[str, Any]] = {}
            edges: dict[str, dict[str, Any]] = {}
            for node_id in wanted:
                found = self._nodes("g.V(vid).valueMap(true)", {"vid": node_id})
                if not found:
                    continue
                focus.append(found[0])
                nodes.setdefault(found[0]["id"], found[0])
                neighbours = self._reach(node_id, hops, bounded)
                for node in neighbours:
                    nodes.setdefault(node["id"], node)
                reaches.append({node["id"] for node in neighbours} | {node_id})
                for edge in self._direct_edges(node_id, bounded):
                    edges[edge["id"]] = edge
            if not focus:
                raise GraphUnavailable("none of the selected entities exist in the graph")

            present = [node["id"] for node in focus]
            for node_id in present:
                for edge in self._edges_between(node_id, [o for o in present if o != node_id]):
                    edges[edge["id"]] = edge

            if hops > 1:
                for edge in self._core_edges():
                    if edge["from"] in nodes and edge["to"] in nodes:
                        edges[edge["id"]] = edge

            shared = sorted({
                node_id for node_id in nodes
                if sum(node_id in reach for reach in reaches) > 1
            } - set(wanted))
            return {
                "focus": "",
                "selected": [node["id"] for node in focus],
                "shared": shared,
                "depth": hops,
                "nodes": list(nodes.values()),
                "edges": [edge for edge in edges.values()
                          if edge["from"] in nodes and edge["to"] in nodes],
                "historical_replay": True,
            }

        whole = dict(self._cached(f"sel:{'+'.join(wanted)}:{hops}:{bounded}", build))
        return _apply_window(_apply_scope(whole, scope), start, end)

    def search(self, term: str, limit: int = 25) -> list[dict[str, Any]]:
        needle = term.strip()
        if len(needle) < 2:
            return []
        bounded = max(1, min(int(limit), 60))
        return self._cached(f"search:{needle.casefold()}:{bounded}", lambda: self._nodes(
            f"g.V().has('name', TextP.containing(needle)).limit({bounded}).valueMap(true)",
            {"needle": needle},
        ))

    # ---- plumbing -----------------------------------------------------------

    def _cached(self, key: str, build: Any) -> Any:
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
        value = build()
        self._cache[key] = (now, value)
        return value

    def element_count(self, element: str) -> int:
        """How many vertices or edges this graph holds. Raises like every other read.

        `status()` swallows the failure to keep the health payload honest and quiet;
        a caller that must classify *why* a graph is dark needs the exception.
        """
        return self._cached(f"count:{element}", lambda: self._reader.element_count(element))

    def _first(self, script: str) -> Any:
        rows = self._submit(script)
        return rows[0] if rows else None

    def _nodes(self, script: str, bindings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [_node(row) for row in self._submit(script, bindings)]

    def _edges(self, script: str, bindings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [_edge(row) for row in self._submit(script, bindings)]


def _timestamp(rows: list[Any]) -> str:
    """Gremlin min/max over an empty set returns a float sentinel, not an empty result."""
    value = str(rows[0]) if rows else ""
    return value if len(value) >= 10 and value[4] == "-" else ""


def _node(row: dict[str, Any]) -> dict[str, Any]:
    properties = {key: _scalar(value) for key, value in row.items()
                  if key not in ("id", "label", "pk")}
    return {
        "id": str(row.get("id", "")),
        "label": str(row.get("label", "")),
        "name": str(properties.pop("name", row.get("id", ""))),
        "event_count": int(properties.pop("event_count", 0) or 0),
        "first_seen": str(properties.pop("first_seen", "")),
        "last_seen": str(properties.pop("last_seen", "")),
        "properties": properties,
    }


def _edge(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("e", {}) if isinstance(row, dict) else {}
    properties = {key: _scalar(value) for key, value in payload.items()
                  if key not in ("id", "label", "type", "inV", "outV", "inVLabel", "outVLabel")}
    raw_buckets = properties.pop("buckets", "")
    try:
        buckets = json.loads(raw_buckets) if isinstance(raw_buckets, str) and raw_buckets else {}
    except json.JSONDecodeError:
        buckets = {}
    return {
        "id": str(payload.get("id", "")),
        "label": str(payload.get("label", "")),
        "kind": str(properties.pop("kind", "event")),
        "from": str(row.get("from", "")),
        "to": str(row.get("to", "")),
        "event_count": int(properties.pop("event_count", 0) or 0),
        "first_seen": str(properties.pop("first_seen", "")),
        "last_seen": str(properties.pop("last_seen", "")),
        "buckets": {str(key): int(value) for key, value in buckets.items()},
        "properties": properties,
    }
