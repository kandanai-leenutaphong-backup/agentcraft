"""Scenario-qualified graph views backed by the same public telemetry evidence."""

from collections import Counter
from datetime import datetime, timezone
import json

from .graph import GraphNotFound, GraphService, GraphUnavailable, _apply_scope
from .telemetry import CosmosTelemetry


class PublicGraphService(GraphService):
    def __init__(self, *, telemetry: CosmosTelemetry, **kwargs):
        super().__init__(**kwargs)
        self.telemetry = telemetry

    async def _snapshot(self, start="", end=""):
        partition = self.telemetry.partition
        bindings = {"partition": partition}
        nodes = await self._nodes("g.V().has('partition',partition).limit(201).valueMap(true)", bindings)
        edges = await self._edges("g.E().has('partition',partition).limit(401)"
            ".project('e','from','to').by(__.valueMap(true)).by(__.outV().id()).by(__.inV().id())", bindings)
        if len(nodes) > 200 or len(edges) > 400:
            raise GraphUnavailable("public graph bound exceeded")
        cases = await self.telemetry.cases(partition)
        refs = list(dict.fromkeys(ref for case in cases for ref in case["event_refs"]))
        try:
            events = await self.telemetry.evidence(partition, refs)
            alarms = [alarm for case in cases for alarm in await self.telemetry.alarms(partition, case["id"])]
        except ValueError as error:
            raise GraphUnavailable("graph telemetry membership unavailable") from error
        valid_ids = {item["id"] for item in [*cases, *alarms, *events]}
        valid_ids.update(entity for item in events for entity in item["entity_refs"].values())
        by_ref = {item["resource_id"]: item for item in events}
        actual_ids = {item["id"] for item in nodes}
        if actual_ids != valid_ids or len(actual_ids) != len(nodes) or len({item["id"] for item in edges}) != len(edges):
            raise GraphUnavailable("stale or unknown graph identity")
        for item in [*nodes, *edges]:
            props = item["properties"]
            for key in ("source", "evidence_refs", "observation_roles"):
                if isinstance(props.get(key), str):
                    try:
                        props[key] = json.loads(props[key])
                    except json.JSONDecodeError as error:
                        raise GraphUnavailable("invalid public graph property encoding") from error
            if props.get("partition") != partition or props.get("source") != self.telemetry.source:
                raise GraphUnavailable("foreign graph source membership")
            evidence = props.get("evidence_refs")
            if not isinstance(evidence, list) or not evidence or not set(evidence).issubset(by_ref):
                raise GraphUnavailable("stale or unknown graph evidence")
            item["event_count"] = len(evidence)
            item["first_seen"] = min(by_ref[ref]["timestamp"] for ref in evidence)
            item["last_seen"] = max(by_ref[ref]["timestamp"] for ref in evidence)
            if "from" in item and (item["from"] not in actual_ids or item["to"] not in actual_ids):
                raise GraphUnavailable("dangling public graph edge")
        for event in events:
            entities = event["entity_refs"]
            for role, entity_id in entities.items():
                node = next(item for item in nodes if item["id"] == entity_id)
                expected_label = {"host": "Host", "user": "Identity", "domain": "Domain",
                                  "process": "Process", "parent_process": "Process"}[role]
                if node["label"] != expected_label or event["resource_id"] not in node["properties"]["evidence_refs"]:
                    raise GraphUnavailable("graph entity evidence mismatch")
        expected_edges = {}

        def admit(label, from_id, to_id, ref):
            if from_id and to_id:
                expected_edges.setdefault((label, from_id, to_id), set()).add(ref)

        for event in events:
            entities = event["entity_refs"]
            ref = event["resource_id"]
            for role in ("host", "user", "process"):
                admit("EVIDENCES_ENTITY", event["id"], entities.get(role), ref)
            admit("MEMBER_OF_DOMAIN", entities.get("user"), entities.get("domain"), ref)
            admit("PROCESS_ON_HOST", entities.get("process"), entities.get("host"), ref)
            admit("PROCESS_ON_HOST", entities.get("parent_process"), entities.get("host"), ref)
            admit("EXECUTED_AS", entities.get("process"), entities.get("user"), ref)
            admit("PARENT_OF", entities.get("parent_process"), entities.get("process"), ref)
            for case in cases:
                if ref in case["event_refs"]:
                    admit("CONTAINS_EVENT", case["id"], event["id"], ref)
            for alarm in alarms:
                if ref in alarm["event_refs"]:
                    admit("HAS_ALARM", alarm["incident_id"], alarm["id"], ref)
                    admit("SUPPORTED_BY", alarm["id"], event["id"], ref)
        actual_edges = {(item["label"], item["from"], item["to"]): set(item["properties"]["evidence_refs"])
                        for item in edges}
        if len(actual_edges) != len(edges) or actual_edges != expected_edges:
            raise GraphUnavailable("graph relationship evidence mismatch")
        if start or end:
            try:
                lower = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
                upper = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
                lower = lower.replace(tzinfo=timezone.utc) if lower and lower.tzinfo is None else lower
                upper = upper.replace(tzinfo=timezone.utc) if upper and upper.tzinfo is None else upper
                if lower and upper and lower >= upper:
                    raise ValueError("invalid window")
            except ValueError as error:
                raise GraphNotFound("invalid graph window") from error
            admitted = {ref for ref, event in by_ref.items()
                        if (not lower or datetime.fromisoformat(event["timestamp"]) >= lower)
                        and (not upper or datetime.fromisoformat(event["timestamp"]) <= upper)}
            nodes = [item for item in nodes if admitted.intersection(item["properties"]["evidence_refs"])]
            keep = {item["id"] for item in nodes}
            edges = [item for item in edges if item["from"] in keep and item["to"] in keep
                     and admitted.intersection(item["properties"]["evidence_refs"])]
        return {"nodes": nodes, "edges": edges, "historical_replay": True, "partition": partition,
                "source": self.telemetry.source, "window": {"start": start, "end": end, "bucket_minutes": 0}}

    async def core(self, limit=200, start="", end=""):
        payload = await self._snapshot(start, end)
        if len(payload["nodes"]) > max(1, min(int(limit), 200)):
            raise GraphUnavailable("public graph selection exceeds requested bound")
        return {**payload, "focus": ""}

    async def overview(self):
        payload = await self._snapshot()
        nodes = payload["nodes"]
        return {"nodes_by_label": dict(Counter(item["label"] for item in nodes)),
            "edges_by_label": dict(Counter(item["label"] for item in payload["edges"])),
            "edges_by_kind": {"source-evidence": len(payload["edges"])},
            "observed_window": {"start": min((item["first_seen"] for item in nodes), default=""),
                                "end": max((item["last_seen"] for item in nodes), default="")},
            "bucket_minutes": 0, "seeds": nodes, "historical_replay": True}

    async def entities(self):
        return (await self._snapshot())["nodes"]

    async def search(self, term, limit=25):
        if not term or len(term) > 200:
            raise GraphNotFound("bounded graph search required")
        nodes = (await self._snapshot())["nodes"]
        exact = [item for item in nodes if item["id"] == term]
        return exact or [item for item in nodes if term.casefold() in item["name"].casefold()][:max(1, min(limit, 25))]

    async def selection(self, node_ids, limit=200, start="", end="", depth=1, scope="only"):
        if not 1 <= len(node_ids) <= 8 or len(set(node_ids)) != len(node_ids) or scope not in {"only", "shared", "all"}:
            raise GraphNotFound("invalid explicit graph selection")
        payload = await self._snapshot(start, end)
        known = {item["id"] for item in payload["nodes"]}
        if not set(node_ids).issubset(known):
            raise GraphNotFound("unknown or foreign graph ID in supplied window")
        reaches = []
        for node_id in node_ids:
            reach = {node_id}
            for _ in range(max(1, min(int(depth), 3))):
                reach |= {item["to"] for item in payload["edges"] if item["from"] in reach} | {
                    item["from"] for item in payload["edges"] if item["to"] in reach}
            reaches.append(reach)
        keep = set.union(*reaches)
        shared = {node_id for node_id in keep if sum(node_id in reach for reach in reaches) > 1}
        payload.update(nodes=[item for item in payload["nodes"] if item["id"] in keep],
                       edges=[item for item in payload["edges"] if item["from"] in keep and item["to"] in keep],
                       selected=node_ids, shared=sorted(shared), depth=depth)
        result = _apply_scope(payload, scope)
        if len(result["nodes"]) > max(1, min(int(limit), 200)):
            raise GraphUnavailable("public graph selection bound exceeded")
        return result

    async def neighbourhood(self, node_id, limit=200, start="", end="", depth=1):
        return {**await self.selection([node_id], limit, start, end, depth, "all"), "focus": node_id}

    async def element_count(self, element):
        if element not in {"vertices", "edges"}:
            raise ValueError("unknown_graph_element")
        return len((await self._snapshot())["nodes" if element == "vertices" else "edges"])

    async def sample(self, element, limit):
        if element not in {"vertices", "edges"}:
            raise ValueError("unknown_graph_element")
        return (await self._snapshot())["nodes" if element == "vertices" else "edges"][:max(1, min(limit, 100))]