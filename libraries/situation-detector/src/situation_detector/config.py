"""Configuration validation, rule selection, stable identity and window bounds.

The component owns structure, not meaning: it never interprets a query string, a
parameter or a processing declaration, and never imports or executes caller code
named by them.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any, Mapping

from .errors import ConfigurationError

#: Bounds on a configuration, so a caller cannot make selection or hashing unbounded.
MAX_RULE_SETS = 64
MAX_RULES_PER_SET = 256
MAX_EXTRA_KEYS = 32
MAX_CONFIGURATION_BYTES = 1_048_576

_RULE_SET_KEYS = {"id", "name", "enabled", "rules"}
_RULE_KEYS = {"id", "name", "query", "parameters", "processing", "enabled", "metadata"}
_CONFIGURATION_KEYS = {"version", "max_window_seconds", "rule_sets"}


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{where} must be a JSON object")
    for key in value:
        if not isinstance(key, str):
            raise ConfigurationError(f"{where} keys must be strings")
    return dict(value)


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{where} must be a non-empty string")
    return value


def _flag(value: Any, where: str, default: bool = True) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigurationError(f"{where} must be true or false")
    return value


def _extras(source: dict[str, Any], known: set[str], where: str) -> dict[str, Any]:
    extra = {key: value for key, value in source.items() if key not in known}
    if len(extra) > MAX_EXTRA_KEYS:
        raise ConfigurationError(f"{where} declares more than {MAX_EXTRA_KEYS} additional fields")
    return copy.deepcopy(extra)


def normalize_config(configuration: Any) -> dict[str, Any]:
    """Validate a detector configuration and return a normalized deep copy.

    Required: ``version``, ``max_window_seconds``, ``rule_sets``. Each rule set
    declares ``id``, ``name``, ``enabled`` and ``rules``; each rule declares
    ``id``, ``name``, ``query``, ``parameters``, ``processing``, ``enabled`` and an
    optional ``metadata`` object. ``enabled`` defaults to true when absent;
    ``parameters``/``processing``/``metadata`` default to empty objects. Rule-set
    and rule identifiers are globally unique. Additional fields are retained
    unchanged, bounded by :data:`MAX_EXTRA_KEYS` per object.
    """
    source = _object(configuration, "configuration")
    version = _text(source.get("version"), "configuration.version")

    window_bound = source.get("max_window_seconds")
    if isinstance(window_bound, bool) or not isinstance(window_bound, (int, float)):
        raise ConfigurationError("configuration.max_window_seconds must be a number")
    if window_bound <= 0:
        raise ConfigurationError("configuration.max_window_seconds must be greater than zero")

    raw_sets = source.get("rule_sets")
    if not isinstance(raw_sets, list):
        raise ConfigurationError("configuration.rule_sets must be a list")
    if len(raw_sets) > MAX_RULE_SETS:
        raise ConfigurationError(f"configuration declares more than {MAX_RULE_SETS} rule sets")

    set_ids: set[str] = set()
    rule_ids: set[str] = set()
    rule_sets: list[dict[str, Any]] = []
    for index, raw_set in enumerate(raw_sets):
        entry = _object(raw_set, f"rule_sets[{index}]")
        set_id = _text(entry.get("id"), f"rule_sets[{index}].id")
        if set_id in set_ids:
            raise ConfigurationError(f"duplicate rule set id {set_id!r}")
        set_ids.add(set_id)

        raw_rules = entry.get("rules")
        if not isinstance(raw_rules, list):
            raise ConfigurationError(f"rule_sets[{set_id}].rules must be a list")
        if len(raw_rules) > MAX_RULES_PER_SET:
            raise ConfigurationError(f"rule set {set_id!r} declares more than {MAX_RULES_PER_SET} rules")

        rules: list[dict[str, Any]] = []
        for rule_index, raw_rule in enumerate(raw_rules):
            rule = _object(raw_rule, f"rule_sets[{set_id}].rules[{rule_index}]")
            rule_id = _text(rule.get("id"), f"rule_sets[{set_id}].rules[{rule_index}].id")
            if rule_id in rule_ids:
                raise ConfigurationError(f"duplicate rule id {rule_id!r}")
            rule_ids.add(rule_id)
            normalized_rule = {
                "id": rule_id,
                "name": _text(rule.get("name"), f"rule {rule_id} name"),
                "query": _text(rule.get("query"), f"rule {rule_id} query"),
                "parameters": _object(rule.get("parameters") or {}, f"rule {rule_id} parameters"),
                "processing": _object(rule.get("processing") or {}, f"rule {rule_id} processing"),
                "enabled": _flag(rule.get("enabled"), f"rule {rule_id} enabled"),
            }
            if rule.get("metadata") is not None:
                normalized_rule["metadata"] = _object(rule["metadata"], f"rule {rule_id} metadata")
            normalized_rule.update(_extras(rule, _RULE_KEYS, f"rule {rule_id}"))
            rules.append(normalized_rule)

        normalized_set = {
            "id": set_id,
            "name": _text(entry.get("name") or set_id, f"rule_sets[{set_id}].name"),
            "enabled": _flag(entry.get("enabled"), f"rule_sets[{set_id}].enabled"),
            "rules": rules,
        }
        normalized_set.update(_extras(entry, _RULE_SET_KEYS, f"rule_sets[{set_id}]"))
        rule_sets.append(normalized_set)

    normalized: dict[str, Any] = {
        "version": version,
        "max_window_seconds": window_bound,
        "rule_sets": rule_sets,
    }
    normalized.update(_extras(source, _CONFIGURATION_KEYS, "configuration"))
    encoded = _canonical(normalized)
    if len(encoded) > MAX_CONFIGURATION_BYTES:
        raise ConfigurationError("configuration exceeds the serialized size bound")
    return normalized


def _canonical(configuration: dict[str, Any]) -> bytes:
    try:
        return json.dumps(configuration, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"configuration is not JSON serializable: {exc}") from exc


def configuration_digest(configuration: Any) -> str:
    """Return a deterministic SHA-256 identity for a configuration's content."""
    return hashlib.sha256(_canonical(normalize_config(configuration))).hexdigest()


def selected_rules(configuration: Any) -> list[dict[str, Any]]:
    """Return enabled rules of enabled sets, in declaration order, each with ``rule_set_id``."""
    selected: list[dict[str, Any]] = []
    for rule_set in normalize_config(configuration)["rule_sets"]:
        if not rule_set["enabled"]:
            continue
        for rule in rule_set["rules"]:
            if not rule["enabled"]:
                continue
            selected.append({"rule_set_id": rule_set["id"], **rule})
    return selected


def _instant(value: Any, where: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConfigurationError(f"{where} is not an ISO-8601 instant: {value!r}") from exc
    raise ConfigurationError(f"{where} must be a datetime or an ISO-8601 string")


def normalize_window(window: Any, max_window_seconds: float) -> dict[str, datetime]:
    """Parse and bound a scan window. ``end`` may equal ``start``.

    Aware and naive instants are both accepted, but the two ends must agree:
    mixing them is rejected rather than compared under an invented timezone.
    """
    source = _object(window, "window")
    start = _instant(source.get("start"), "window.start")
    end = _instant(source.get("end"), "window.end")
    if (start.tzinfo is None) != (end.tzinfo is None):
        raise ConfigurationError("window start and end must both be timezone-aware or both naive")
    if end < start:
        raise ConfigurationError("window end must not precede window start")
    span = (end - start).total_seconds()
    if span > max_window_seconds:
        raise ConfigurationError(f"window of {span:.0f}s exceeds max_window_seconds {max_window_seconds:g}")
    return {"start": start, "end": end}


__all__ = [
    "MAX_CONFIGURATION_BYTES",
    "MAX_EXTRA_KEYS",
    "MAX_RULES_PER_SET",
    "MAX_RULE_SETS",
    "configuration_digest",
    "normalize_config",
    "normalize_window",
    "selected_rules",
]
