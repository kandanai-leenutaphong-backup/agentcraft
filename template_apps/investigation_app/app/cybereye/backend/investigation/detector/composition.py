"""Adapters between the declared Perth rules and the shared detector component.

The rule declarations stay in `rules.py`; this module only expresses them as a
component configuration and reads a configuration back into `Rule` objects, so a
caller can add, remove, disable or tune rules without the component learning any
Perth semantics.
"""

from __future__ import annotations

from typing import Any, Mapping
import json
from pathlib import Path

from template_foundations.situation_detector import normalize_config

from .rules import Rule, registry

#: The application's own window cap, restated as the component's bound.
MAX_WINDOW_SECONDS = 48 * 3600

DEFAULT_RULE_SET_ID = "perth_replay"
CONFIGURATION_VERSION = "perth-replay-1.0.0"


def declaration(rule: Rule) -> dict[str, Any]:
    """Express one declared rule as a component rule entry."""
    return {
        "id": rule.rule_id,
        "name": rule.name,
        "query": rule.query,
        "enabled": True,
        "parameters": {
            "version": rule.version,
            "description": rule.description,
            "threshold": rule.threshold,
            "score": rule.score,
            "confidence": rule.confidence,
            "role": rule.role,
            "evidence_semantics": rule.evidence_semantics,
            "behaviour_class": rule.behaviour_class,
            "technique_ids": list(rule.technique_ids),
        },
        "processing": {"kind": "entity_groups", "max_rows": 100},
    }


def rule_from_declaration(entry: Mapping[str, Any]) -> Rule:
    """Read a component rule entry back into a `Rule`.

    Defaults keep an added or partially tuned rule executable: a rule that omits
    scoring inputs contributes nothing to severity rather than failing the scan.
    """
    parameters = entry.get("parameters") or {}
    return Rule(
        rule_id=str(entry["id"]),
        version=str(parameters.get("version", "1.0.0")),
        name=str(entry["name"]),
        description=str(parameters.get("description", entry["name"])),
        query=str(entry["query"]),
        threshold=int(parameters.get("threshold", 1)),
        score=int(parameters.get("score", 0)),
        confidence=str(parameters.get("confidence", "low")),  # type: ignore[arg-type]
        role=str(parameters.get("role", "contextual")),  # type: ignore[arg-type]
        evidence_semantics=str(parameters.get("evidence_semantics", "")),
        behaviour_class=str(parameters.get("behaviour_class", "")),  # type: ignore[arg-type]
        technique_ids=tuple(str(item) for item in parameters.get("technique_ids", ())),
    )


def default_configuration() -> dict[str, Any]:
    """The five declared Perth rules as one enabled rule set."""
    return normalize_config({
        "version": CONFIGURATION_VERSION,
        "max_window_seconds": MAX_WINDOW_SECONDS,
        "rule_sets": [{
            "id": DEFAULT_RULE_SET_ID,
            "name": "Perth replay detection rules",
            "enabled": True,
            "rules": [declaration(rule) for rule in registry()],
        }],
    })


def load_configuration(path: Path) -> dict[str, Any]:
    source = json.loads(path.read_text())
    if not isinstance(source, dict) or set(source) - {"version", "max_window_seconds", "rule_sets"}:
        raise ValueError("Detector configuration declares version, max_window_seconds and rule_sets")
    builtins = {rule.rule_id: declaration(rule) for rule in registry()}
    if not isinstance(source.get("rule_sets"), list):
        raise ValueError("Detector configuration requires rule_sets")
    sets = []
    for group in source["rule_sets"]:
        if not isinstance(group, dict) or not isinstance(group.get("rules"), list):
            raise ValueError("Each ruleset requires a rule list")
        rules = []
        for selection in group["rules"]:
            if not isinstance(selection, dict):
                raise ValueError("Rule selection must be an object")
            if "builtin" in selection:
                if selection["builtin"] not in builtins or set(selection) - {"builtin", "enabled", "parameters", "processing"}:
                    raise ValueError("Unknown builtin rule or override field")
                base = builtins[selection["builtin"]]
                entry = {**base, "enabled": selection.get("enabled", True),
                         "parameters": {**base["parameters"], **selection.get("parameters", {})},
                         "processing": {**base["processing"], **selection.get("processing", {})}}
            else:
                entry = selection
            parameters, processing = entry.get("parameters", {}), entry.get("processing", {})
            if type(parameters.get("threshold", 1)) is not int or parameters.get("threshold", 1) < 1:
                raise ValueError("Rule threshold must be a positive integer")
            if type(parameters.get("score", 0)) is not int or not 0 <= parameters.get("score", 0) <= 100:
                raise ValueError("Rule score must be an integer from 0 to 100")
            if parameters.get("role", "contextual") not in {"anchor", "corroborator", "contextual"} or parameters.get("confidence", "low") not in {"high", "medium", "low"}:
                raise ValueError("Invalid rule role or confidence")
            if processing.get("kind") != "entity_groups" or type(processing.get("max_rows", 100)) is not int or not 1 <= processing.get("max_rows", 100) <= 200:
                raise ValueError("Main detector processing requires entity_groups and max_rows from 1 to 200")
            rules.append(entry)
        sets.append({**group, "rules": rules})
    config = normalize_config({**source, "rule_sets": sets})
    if config["max_window_seconds"] > MAX_WINDOW_SECONDS:
        raise ValueError("Main detector window remains capped at 48 hours")
    return config


__all__ = [
    "CONFIGURATION_VERSION",
    "DEFAULT_RULE_SET_ID",
    "MAX_WINDOW_SECONDS",
    "declaration",
    "default_configuration",
    "load_configuration",
    "rule_from_declaration",
]
