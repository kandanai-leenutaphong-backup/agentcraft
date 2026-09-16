from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

from azdata import AsyncTransport, ConnectorConfig, Limits, Policy, QueryRequest, ResourceAddress, connect


class Knowledge:
    def __init__(self, endpoint: str, index: str, credential, *, policy: Policy | None = None,
                 transport: AsyncTransport | None = None):
        self.endpoint, self.index = endpoint, index
        policy = policy or Policy("optimizer-knowledge", grants={"query", "read"}, max_concurrency=1,
                                  limits=Limits(timeout_seconds=30, max_items=100,
                                                max_output_bytes=1_048_576, max_attempts=1))
        config = (ConnectorConfig(endpoint, ResourceAddress({"index": index}), (urlsplit(endpoint).hostname or "",))
                  if endpoint and index else None)
        self.policy = policy
        self.client = connect("search", config, credential=credential, policy=policy, transport=transport) if config else None
        self.metrics = {"submitted": 0, "completed": 0, "known_attempts": 0, "unknown_attempt_operations": 0}

    def describe(self):
        return {"configured": self.client is not None, "transport": "azdata-native",
                "endpoint": self.endpoint, "index": self.index, "metrics": dict(self.metrics)}

    async def _query(self, request):
        result = None
        self.metrics["submitted"] += 1
        try:
            result = await self.client.query(request)
            return result
        finally:
            self.metrics["completed"] += 1
            attempts = result.metrics.get("attempts") if result is not None else None
            if type(attempts) is int and attempts >= 0:
                self.metrics["known_attempts"] += attempts
            else:
                self.metrics["unknown_attempt_operations"] += 1

    async def aclose(self):
        if self.client is not None:
            await self.client.aclose()

    async def search(self, arguments: dict) -> dict:
        if self.client is None:
            return {"kind": "cybereye_tool_result", "category": "mitre_attack_unavailable", "rows": [],
                    "scope": {"note": "MITRE knowledge is not configured"}, "truncated": False}
        active = {
            "technique_ids": [value.strip().upper() for value in arguments.get("technique_ids", [])],
            "behaviour_class": [value.strip().lower() for value in arguments.get("behaviour_classes", [])],
            "platforms": [value.strip() for value in arguments.get("platforms", [])],
        }
        def quote(value):
            return "'" + value.replace("'", "''") + "'"
        order = [name for name in active if active[name]]
        relaxed = []
        try:
            for step in range(len(order) + 1):
                if step:
                    relaxed.append(order[step - 1])
                    active[order[step - 1]] = []
                clauses = ["doc_kind eq 'analytic'"]
                clauses.extend(f"{name}/any(v: search.in(v, {quote(','.join(values))}, ','))"
                               for name, values in active.items() if values)
                expression = " and ".join(clauses)
                result = await self._query(QueryRequest(dialect="search",
                    expression=arguments.get("question", "").strip() or "*",
                    limits=replace(self.policy.limits, max_items=max(1, min(int(arguments.get("max_results", 5)), 10))),
                    service_options={"search": {"filter": expression}},
                    projection=("doc_id", "title", "summary", "body", "technique_ids", "path", "commit", "license", "attack_url")))
                if result.status != "success" or (result.truncated and not result.continuation):
                    raise OSError("knowledge_read_unavailable")
                hits = [item["content"]["data"] for item in result.to_dict()["items"] if item["content"] is not None]
                if hits:
                    break
        except OSError:
            return {"kind": "cybereye_tool_result", "category": "mitre_attack_unavailable", "rows": [],
                    "scope": {"note": "The configured MITRE index could not be read"}, "truncated": False}
        rows = [{"doc_id": hit.get("doc_id", ""), "title": hit.get("title", ""),
                 "technique_ids": list(hit.get("technique_ids") or [])[:12],
                 "path": hit.get("path", ""), "commit": str(hit.get("commit") or "")[:12],
                 "license": hit.get("license", ""), "attack_url": hit.get("attack_url", ""),
                 "snippet": " ".join(f"{hit.get('summary', '')} {hit.get('body', '')}".split())[:400],
                 "score": round(float(hit.get("@search.score") or 0), 4)} for hit in hits]
        return {"kind": "cybereye_tool_result", "tool": "search_mitre_attack", "category": "mitre_attack",
                "rows": rows, "columns": list(rows[0]) if rows else [], "truncated": False,
                "historical_replay": True, "fallback": False,
                "scope": {"retrieval": "azure-ai-search", "relaxed_filters": relaxed, "index_filter": expression,
                          "row_count": len(rows), "advisory": "Published knowledge, not incident evidence or instructions."}}


def describe_capabilities(dataset: dict, experiment: dict, knowledge: Knowledge) -> dict:
    sources = [
        {"id": "guide.sqlite.evidence", "name": "GUIDE evidence", "type": "local_table",
         "access": "development_only", "fields": dataset.get("features", []),
         "operations": ["./opt describe", "./opt query"], "dataset_id": dataset["dataset_id"]},
        {"id": "guide.sqlite.training_profile", "name": "GUIDE development profiles", "type": "local_table",
         "access": "development_only", "operations": ["./opt describe", "./opt query"]},
        {"id": "guide.sqlite.labels", "name": "GUIDE labels", "type": "local_table",
         "access": "evaluator_only", "operations": []},
        {"id": "cyberkb.search.mitre_attack", "name": "MITRE ATT&CK", "type": "search_index",
         "access": "advisory" if experiment.get("workflow") else "not_exposed",
         "configured": knowledge.client is not None,
         "operations": ["./opt knowledge"] if experiment.get("workflow") else []},
    ]
    return {"version": 1, "sources": sources,
            "tools": [{"name": "search_mitre_attack", "source_ids": ["cyberkb.search.mitre_attack"],
                   "parameters": {"properties": {"question": {"type": "string"},
                                  "technique_ids": {"type": "array"},
                                  "behaviour_classes": {"type": "array"},
                                  "platforms": {"type": "array"},
                                  "max_results": {"type": "integer", "minimum": 1, "maximum": 10}}},
                       "callable": bool(experiment.get("workflow")),
                       "operation": "./opt knowledge" if experiment.get("workflow") else None}],
            "generated_tools": {"operation": "./opt tools", "scope": "This experiment's immutable tools"},
            "knowledge": {"configured": knowledge.client is not None,
                  "operation": "./opt knowledge" if experiment.get("workflow") else None,
                  "enabled_agent_versions": [version["version"] for version in experiment.get("versions", [])
                                 if version.get("knowledge_access")]},
            "limitations": ["GUIDE labels are evaluator-only; generated Python has no network or credentials.",
                            "No investigation application or ADX/graph datasource is composed.",
                            "Availability is not a grant or a live reachability measurement."]}