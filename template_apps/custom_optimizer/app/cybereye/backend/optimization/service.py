"""Compatibility adapter: the component service, bound to CyberEye's operator rule and GUIDE.

The component knows no `Principal` and no GUIDE fact. This wrapper supplies both, and owns the
one projection whose shape belongs to the application: the agent catalogue entries the agents
API serves.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.components.agent_optimization import (
    PROTOCOLS,
    digest,
    now,
    service as _service,
    write_json,
)

from ..security import Principal
from .dataset import GRADES
from .profile import GUIDE_PROFILE, TOOL_FAMILIES

# Bound at import so a test that replaces the component's decider does not recurse through here.
_compare_evaluation = _service.compare_evaluation


def compare_evaluation(experiment, candidate, evaluation, grades=GRADES):
    return _compare_evaluation(experiment, candidate, evaluation, grades)


def local_operator_owner(caller: Principal) -> str:
    if caller.issuer != "local-preview" or not caller.id or caller.kind != "user":
        raise PermissionError("Optimization is available only to the local operator")
    return hashlib.sha256(caller.id.encode()).hexdigest()


class OptimizationService(_service.OptimizationService):
    def __init__(self, dataset, root: Path, model: str, predict, *, authorize=local_operator_owner,
                 profile=GUIDE_PROFILE, identify=lambda caller: caller.id, knowledge_search=None,
                 detector_reference=None, knowledge_reference=None, capability_catalogue=None) -> None:
        super().__init__(dataset, root, model, predict, authorize=authorize, profile=profile,
                         identify=identify, knowledge_search=knowledge_search,
                         detector_reference=detector_reference, knowledge_reference=knowledge_reference,
                         capability_catalogue=capability_catalogue)

    def catalogue_agents(self, caller):
        snapshot = self.snapshot(caller)
        tools = {tool["id"]: tool for tool in snapshot["tools"]}
        result = []
        for experiment in snapshot["experiments"]:
            for version in experiment["versions"]:
                entries = []
                for tool_id in version["tool_ids"]:
                    tool = tools[tool_id]
                    entries.append({"id": tool_id, "name": tool["name"], "description": tool["description"],
                        "category": "guide_python" if tool.get("language") == "python" else "guide_sql_legacy", "fallback": False,
                        "parameters": {"properties": {}, "required": []}, "datasource_ids": ["guide.sqlite.evidence", "guide.sqlite.training_profile"],
                        "datasource": {"kind": "sqlite", "label": "GUIDE case evidence and development profiles",
                                       "target": experiment["dataset_id"], "target_label": "Dataset", "endpoint": "local read-only service", "configured": True},
                        "source": {"available": True, "path": f"optimization/{experiment['id']}/tools/{tool_id}.{'py' if tool.get('language') == 'python' else 'sql'}",
                                   "start_line": 1, "code": tool.get("code", tool.get("sql", "")), "truncated": False}})
                result.append({"id": f"{experiment['agent_id']}_v{version['version']}",
                    "name": f"{experiment['name']} / v{version['version']} {version['name']}",
                    "description": version["rationale"], "model": version["model"],
                    "config_id": experiment["agent_id"], "config_version": version["version"],
                    "config_digest": digest({field: version[field] for field in ("system_prompt", "model", "tool_ids")})[:12], "tools": entries,
                    "metrics": version["metrics"], "optimization_experiment_id": experiment["id"]})
        return result


__all__ = ["OptimizationService", "PROTOCOLS", "TOOL_FAMILIES", "compare_evaluation", "digest",
           "local_operator_owner", "now", "write_json"]
