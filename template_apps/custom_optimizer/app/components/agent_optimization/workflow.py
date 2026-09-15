from __future__ import annotations

import hashlib
import json
import re

from .python_tools import PythonToolRunner
from .joint import detect_rulesets, verify_rulesets, version_rulesets


def verify_detector(detector: dict) -> None:
    if detector.get("schema_version") == 2:
        verify_rulesets(detector)
        return
    for rule in detector["rules"]:
        definition = {field: rule[field] for field in ("id", "name", "description", "code")}
        if rule["digest"] != hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest():
            raise ValueError("Pinned detector rule content changed")
    payload = {field: detector[field] for field in ("name", "parent_version", "change_rationale", "rules")}
    if detector["digest"] != hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest():
        raise ValueError("Pinned detector content changed")


def detector_version(definition: dict, history: list[dict], created_at: str, scope: str = "") -> dict:
    if isinstance(definition, dict) and "configuration" in definition:
        return version_rulesets(definition, history, created_at, scope)
    if not isinstance(definition, dict) or set(definition) - {"name", "parent_version", "change_rationale", "rules"}:
        raise ValueError("Detector needs name, parent_version, change_rationale and rules")
    name = definition.get("name")
    reasons = definition.get("change_rationale")
    rules = definition.get("rules")
    parent_number = definition.get("parent_version")
    parent = next((item for item in history if type(parent_number) is int and item["version"] == parent_number), None)
    if (history and parent is None) or (not history and parent_number is not None):
        raise ValueError("Detector parent must be a saved detector version")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Detector requires a short name")
    if not isinstance(reasons, list) or not 1 <= len(reasons) <= 4 or any(not isinstance(reason, str) or not 15 <= len(reason) <= 260 for reason in reasons):
        raise ValueError("Detector change_rationale needs 1 to 4 concise bullets")
    if not isinstance(rules, list) or not 1 <= len(rules) <= 3:
        raise ValueError("Detector requires 1 to 3 bounded Python rules")
    saved_rules = []
    seen = set()
    previous_rules = {rule["id"]: rule for rule in parent["rules"]} if parent else {}
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"id", "name", "description", "code"}:
            raise ValueError("Each rule needs exactly id, name, description and code")
        identifier = rule["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", identifier) or identifier in seen:
            raise ValueError("Rule IDs must be unique lowercase identifiers")
        if any(not isinstance(rule[field], str) or not 1 <= len(rule[field].strip()) <= limit
               for field, limit in (("name", 100), ("description", 1000))):
            raise ValueError("Rules require a short name and evidence description")
        PythonToolRunner.validate(rule["code"])
        identity = hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()
        previous = previous_rules.get(identifier)
        revision = previous["revision"] + (previous["digest"] != identity) if previous else 1
        saved_rules.append({**rule, "digest": identity, "revision": revision})
        seen.add(identifier)
    payload = {"name": name.strip(), "parent_version": parent_number,
               "change_rationale": reasons, "rules": saved_rules}
    return {**payload, "version": len(history) + 1, "created_at": created_at,
            "digest": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "scope": scope}


def detect(dataset, case_id: str, detector: dict, scope: dict | None = None) -> dict:
    if detector.get("schema_version") == 2:
        return detect_rulesets(dataset, case_id, detector, scope)
    results = []
    for rule in detector["rules"]:
        envelope = dataset.run_tool(case_id, {"code": rule["code"], "language": "python"}, scope)
        result = envelope.get("data") if isinstance(envelope, dict) and envelope.get("kind") == "cybereye_tool_result" else envelope
        if not isinstance(result, dict) or set(result) != {"matched", "facts", "technique_ids"} or type(result["matched"]) is not bool:
            raise ValueError("Detector rule must return matched (boolean), facts and technique_ids only")
        if not isinstance(result["facts"], list) or not 1 <= len(result["facts"]) <= 8 or any(not isinstance(fact, str) or not 1 <= len(fact) <= 500 for fact in result["facts"]):
            raise ValueError("Detector facts require 1 to 8 bounded evidence statements")
        if not isinstance(result["technique_ids"], list) or len(result["technique_ids"]) > 16 or any(not isinstance(technique, str) or not re.fullmatch(r"T\d{4}(?:\.\d{3})?", technique) for technique in result["technique_ids"]):
            raise ValueError("Detector techniques require at most 16 ATT&CK technique IDs")
        results.append({"rule_id": rule["id"], "rule_revision": rule["revision"],
                        "name": rule["name"], **result})
    return {"version": detector["version"], "digest": detector["digest"], "rule_results": results,
            "situations": [result for result in results if result["matched"]]}


def knowledge_arguments(payload: dict, behaviour_classes=frozenset()) -> dict:
    allowed = {"question", "technique_ids", "behaviour_classes", "platforms", "max_results"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("Unknown knowledge search arguments")
    result = {"question": "", "technique_ids": [], "behaviour_classes": [], "platforms": [], "max_results": 3, **payload}
    if not isinstance(result["question"], str) or len(result["question"]) > 2000:
        raise ValueError("Knowledge question is capped at 2000 characters")
    for key, limit in (("technique_ids", 16), ("behaviour_classes", 5), ("platforms", 6)):
        values = result[key]
        if not isinstance(values, list) or len(values) > limit or any(not isinstance(value, str) or not 1 <= len(value) <= 100 for value in values):
            raise ValueError("Knowledge filters must be bounded string lists")
    if any(not re.fullmatch(r"T\d{4}(?:\.\d{3})?", value) for value in result["technique_ids"]):
        raise ValueError("Invalid ATT&CK technique filter")
    if set(result["behaviour_classes"]) - set(behaviour_classes):
        raise ValueError("Invalid knowledge behaviour filter")
    if type(result["max_results"]) is not int or not 1 <= result["max_results"] <= 10:
        raise ValueError("Knowledge result count must be 1 to 10")
    return result