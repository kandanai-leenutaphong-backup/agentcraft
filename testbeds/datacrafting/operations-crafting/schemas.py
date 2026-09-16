"""Version-one exchange schemas; Operations expectations are mode-owned data."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator


class InvalidInput(ValueError):
    """An input violates the frozen local data contract."""


TOOLS = ("scada", "alarms", "knowledge", "topology")
RESOURCES = ("assets", *TOOLS)
ACTIONS = (
    "confirm_event", "assess_system_strength", "consult_limit_advice",
    "request_authorized_support", "notify_operator", "investigate_cooling",
    "review_protection_work", "apply_temporary_line_ratings", "verify_restoration",
    "remove_temporary_line_ratings", "request_missing_data", "request_tool_access",
    "escalate_to_operator",
)
FORBIDDEN = ("operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause")
STATUSES = ("event", "no_event", "insufficient_evidence")
TRIP_ALARM_CODES = ("GENERATOR_TRIP", "GEN_TRIP", "UNIT_TRIP", "BUS_TRIP", "BUSBAR_TRIP", "BB_TRIP")
LATCHED_TRIP_ALARM_CODES = ("UNIT_TRIP_LATCHED", "BUSBAR_TRIP_LATCHED")
RESTORATION_ALARM_CODES = ("RETURN_TO_SERVICE",)
EVENT_TYPES = ("generator_trip", "busbar_trip", "restoration", None)
GAPS = (None, "data_gap", "logic_gap", "tooling_gap", "knowledge_gap", "unsupported_inference")
TEXT = {"type": "string", "minLength": 1, "maxLength": 100000}
IDENTIFIER = {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$"}
UTC = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
PRIVATE_DETAIL = {"type": ["string", "object", "null"]}


def array(items: dict, *, minimum: int = 0, unique: bool = False) -> dict:
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": 100000, "uniqueItems": unique}


def record(properties: dict, optional: tuple[str, ...] = ()) -> dict:
    return {
        "type": "object", "properties": properties,
        "required": [key for key in properties if key not in optional],
        "additionalProperties": False,
    }


IDS = array(IDENTIFIER, unique=True)
INTERVAL = record({"start": UTC, "end": UTC})
EVENT_CONDITION = record({
    "notification_id": IDENTIFIER, "event_type": {"enum": list(EVENT_TYPES[:-1])},
    "asset_ids": array(IDENTIFIER, minimum=1, unique=True), "event_interval": INTERVAL,
    "available_at": UTC, "origin": {"const": "simulated_operator_notification"}, "synthetic": {"const": True},
})
EVENT_CONDITIONS = array(EVENT_CONDITION, minimum=1)
ENTRY = record({"id": IDENTIFIER, "path": TEXT, "sha256": HASH, "description": TEXT})
ANNOTATION = {"anyOf": [TEXT, record({"id": IDENTIFIER, "basis": TEXT, "text": TEXT})]}
MANIFEST = record({
    "schema_version": {"const": 1}, "synthetic": {"const": True}, "seed": {"const": 20260916},
    "resource_pack_id": IDENTIFIER, "resources": array(ENTRY, minimum=5),
    "authoring": array(ENTRY, minimum=2), "synthetic_assumptions": array(ANNOTATION),
    "assumptions": array(TEXT), "real_binding_gaps": array(TEXT),
    "capabilities": record({tool: {"const": tool} for tool in TOOLS}),
    "counts": record({key: {"type": "integer", "minimum": 0} for key in (
        "action_scenarios", "alarm_rows", "assets", "detection_scenarios", "deterministic_files", "knowledge_documents",
        "rdf_triples", "scada_rows", "scenarios", "source_documents", "source_events", "tables")}),
    "generation_parameters": record({"cadence_seconds": {"type": "integer", "minimum": 1},
                                     "max_latency_seconds": {"type": "integer", "minimum": 0},
                                     "noise_mw": {"type": "number", "minimum": 0}, "seed": {"const": 20260916}}),
    "generator_sha256": HASH, "generator_version": TEXT, "replay_boundary": TEXT, "report_derived_facts": TEXT,
}, ("synthetic_assumptions", "assumptions", "real_binding_gaps", "capabilities", "counts", "generation_parameters",
    "generator_sha256", "generator_version", "replay_boundary", "report_derived_facts"))
ASSET = record({
    "asset_id": IDENTIFIER, "name": TEXT, "aliases": array(TEXT, unique=True),
    "kind": TEXT, "station": TEXT, "cim_id": TEXT, "synthetic": {"const": True},
    "attributes": {"type": "object"},
})
POINT_DEFINITION = record({"unit": TEXT, "minimum": {"type": "number"}, "maximum": {"type": "number"}, "digital": {"type": "boolean"}}, ("minimum", "maximum", "digital"))
ASSETS = record({"synthetic": {"const": True}, "assets": array(ASSET, minimum=1), "schema_version": {"const": 1},
                 "state_convention": TEXT, "point_definitions": record({point: POINT_DEFINITION for point in (
                     "active_power_mw", "breaker_closed", "voltage_kv", "flow_mva", "rating_mva", "cooling_flow_pct", "vacuum_kpa", "available")})},
                ("schema_version", "state_convention", "point_definitions"))
RULE = record({
    "event_type": {"enum": list(EVENT_TYPES[:-1])}, "action_ids": array({"enum": list(ACTIONS)}, unique=True),
    "required_tools": array({"enum": list(TOOLS)}, unique=True), "rationale": TEXT,
})
KNOWLEDGE_DOCUMENT = record({
    "id": IDENTIFIER, "title": TEXT, "kind": {"enum": ["runbook", "limits", "maintenance", "forensic"]},
    "asset_ids": IDS, "valid_from": UTC, "available_at": UTC, "valid_to": UTC,
    "text": TEXT, "synthetic": {"const": True}, "action_rules": array(RULE),
    "asset_kinds": array(TEXT, unique=True), "execution": {"const": "recommendation_only"},
    "availability_basis": TEXT, "known_at": UTC, "combinations": array({"type": ["array", "object"]}),
    "line_asset_ids": IDS, "rating_duration_minutes": {"type": "number", "minimum": 0},
    "reference_rating_mva": {"type": "number", "minimum": 0}, "temporary_rating_mva": {"type": "number", "minimum": 0},
}, ("valid_to", "asset_kinds", "execution", "availability_basis", "known_at", "combinations", "line_asset_ids",
    "rating_duration_minutes", "reference_rating_mva", "temporary_rating_mva"))
KNOWLEDGE = record({"synthetic": {"const": True}, "documents": array(KNOWLEDGE_DOCUMENT), "schema_version": {"const": 1},
                    "action_semantics": TEXT, "policy_assumption": TEXT}, ("schema_version", "action_semantics", "policy_assumption"))
DOCUMENT = record({
    "id": IDENTIFIER, "pdf_path": TEXT, "pdf_sha256": HASH,
    "extraction_path": TEXT, "extraction_sha256": HASH,
    "timezone": {"const": "AEST"}, "utc_offset": {"const": "+10:00"},
    "native_path": TEXT, "native_sha256": HASH, "pages": {"type": "integer", "minimum": 1},
}, ("native_path", "native_sha256", "pages"))
SOURCE_REF = record({"document_id": IDENTIFIER, "page": {"type": "integer", "minimum": 1}, "quote": TEXT})
SOURCE_EVENT = record({
    "id": IDENTIFIER, "incident_id": IDENTIFIER, "asset_ids": IDS,
    "event_type": TEXT, "reported_time": TEXT, "precision": {"enum": ["second", "minute"]},
    "event_interval": INTERVAL, "classification": PRIVATE_DETAIL, "cause": PRIVATE_DETAIL,
    "source_refs": array(SOURCE_REF, minimum=1), "actual_actions": array({"type": ["string", "object"]}),
    "basis": TEXT, "fact_ids": IDS, "synthetic": {"const": True},
}, ("basis", "fact_ids", "synthetic"))
SOURCE_FACT = record({"id": IDENTIFIER, "basis": TEXT, "value": {}, "source_refs": array(SOURCE_REF, minimum=1), "available_at": UTC}, ("available_at",))
SOURCES = record({
    "schema_version": {"const": 1}, "visibility": {"const": "evaluator_only"},
    "documents": array(DOCUMENT, minimum=1), "events": array(SOURCE_EVENT, minimum=1),
    "synthetic": {"const": True}, "facts": array(SOURCE_FACT), "reviewed_sources_sha256": HASH, "source_manifest_sha256": HASH,
    "review": record({"later_knowledge_assumption": TEXT, "later_knowledge_time": UTC, "method": TEXT, "scope": TEXT}),
}, ("synthetic", "facts", "reviewed_sources_sha256", "source_manifest_sha256", "review"))
SCENARIO = record({
    "scenario_id": IDENTIFIER, "incident_id": IDENTIFIER,
    "split": {"enum": ["development", "holdout"]}, "kind": {"enum": ["detection", "action"]},
    "template_id": IDENTIFIER, "variant": TEXT, "source_event_ids": IDS,
    "window_start": UTC, "decision_time": UTC, "asset_ids": array(IDENTIFIER, minimum=1, unique=True),
    "tools": array({"enum": list(TOOLS)}, unique=True), "parameters": {"type": "object"},
    "assumptions": array(TEXT), "expected": {"type": "object"},
    "schema_version": {"const": 1}, "synthetic": {"const": True},
    "event_conditions": EVENT_CONDITIONS,
}, ("schema_version", "synthetic", "event_conditions"))
SCENARIO["allOf"] = [{"if": {"properties": {"kind": {"const": "action"}}},
                      "then": {"required": ["event_conditions"]}, "else": {"not": {"required": ["event_conditions"]}}}]
SCENARIOS = record({
    "schema_version": {"const": 1}, "synthetic": {"const": True},
    "visibility": {"const": "evaluator_only"}, "scenarios": array(SCENARIO, minimum=1),
    "holdout_policy": TEXT, "templates": array(record({"template_id": IDENTIFIER, "synthetic": {"const": True},
                                                       "binding_parameters": array(TEXT), "decision_rule": TEXT})),
}, ("holdout_policy", "templates"))
EXPECTED = record({
    "status": {"enum": list(STATUSES)}, "event_type": {"enum": list(EVENT_TYPES)},
    "asset_ids": IDS, "event_interval": {"anyOf": [INTERVAL, {"type": "null"}]},
    "cause_status": {"enum": ["not_established", "hypothesis", "confirmed"]},
    "action_ids": array({"enum": list(ACTIONS)}, unique=True),
    "forbidden_action_ids": array({"enum": list((*ACTIONS, *FORBIDDEN))}, unique=True),
    "gap": {"enum": list(GAPS)},
})
PREDICTION = record({
    "status": {"enum": list(STATUSES)}, "event_type": {"enum": list(EVENT_TYPES)},
    "asset_ids": IDS, "event_time": {"anyOf": [UTC, {"type": "null"}]},
    "cause_status": {"enum": ["not_established", "hypothesis", "confirmed"]},
    "action_ids": array({"enum": list((*ACTIONS, *FORBIDDEN))}, unique=True),
    "gap": {"enum": list(GAPS)}, "message": TEXT, "evidence_ids": IDS,
    "classification": {"type": ["string", "null"]},
    "action_evidence": array(record({
        "action_id": {"enum": list(ACTIONS)}, "rule_id": IDENTIFIER,
        "evidence_ids": IDS, "rationale": TEXT, "required_tools": array({"enum": list(TOOLS)}, unique=True),
    })),
    "hypotheses": array(TEXT),
    "event_interval": {"anyOf": [INTERVAL, {"type": "null"}]},
    "communication": record({
        "notification_ids": IDS, "event_type": {"enum": list(EVENT_TYPES)}, "asset_ids": IDS,
        "event_interval": INTERVAL, "decision_time": UTC,
        "state": {"enum": ["verified", "unverified", "conflicting"]},
        "cause_status": {"enum": ["not_established", "hypothesis", "confirmed"]},
        "next_steps": array({"enum": list((*ACTIONS, *FORBIDDEN))}, unique=True), "evidence_ids": IDS,
    }),
}, ("classification", "action_evidence", "hypotheses", "event_interval", "communication"))

MODE = record({"id": IDENTIFIER, "version": {"const": 1}})
RUN_MANIFEST = record({
    "schema_version": {"const": 1}, "mode": MODE, "synthetic": {"const": True},
    "resource_pack_id": IDENTIFIER, "resource_manifest_sha256": HASH, "dataset_manifest_sha256": HASH,
    "artifacts": array(record({"path": TEXT, "sha256": HASH, "bytes": {"type": "integer", "minimum": 0},
                               "visibility": {"enum": ["agent", "evaluator_only"]}}), minimum=1),
}, ("dataset_manifest_sha256",))
PUBLIC_ASSET = record({
    "asset_id": IDENTIFIER, "name": TEXT, "kind": TEXT, "station": TEXT, "synthetic": {"const": True},
    "attributes": {"type": "object", "additionalProperties": False, "properties": {
        key: {"type": ["string", "number", "boolean"]} for key in (
            "nominal_kv", "nominal_voltage_kv", "synchronous", "capacity_mw", "rated_mw",
            "system_strength_contributor", "normal_closed", "rating_mva")}},
})
QUALITY_ROW = record({"row_id": IDENTIFIER, "asset_id": IDENTIFIER, "point": TEXT, "ts": UTC, "available_at": UTC,
                      "quality": {"enum": ["good", "missing", "stale", "bad"]}})
PUBLIC_SCADA = record({**QUALITY_ROW["properties"], "quality": {"const": "good"}, "value": {"type": "number"},
                       "unit": TEXT, "synthetic": {"const": True}})
PUBLIC_ALARM = record({"row_id": IDENTIFIER, "asset_id": IDENTIFIER, "ts": UTC, "available_at": UTC,
                       "code": TEXT, "state": {"enum": ["active", "cleared"]}, "severity": TEXT,
                       "message": TEXT, "synthetic": {"const": True}})
PUBLIC_KNOWLEDGE = record({key: (value if key != "kind" else {"enum": ["runbook", "limits", "maintenance"]})
                           for key, value in KNOWLEDGE_DOCUMENT["properties"].items() if key in (
                               "id", "title", "kind", "asset_ids", "valid_from", "available_at", "valid_to", "text", "synthetic", "action_rules")}, ("valid_to",))
PUBLIC_TOPOLOGY = record({"row_id": IDENTIFIER, "asset_id": IDENTIFIER, "subject": TEXT, "predicate": TEXT, "object": {"type": "string"},
                         "object_kind": {"enum": ["literal", "resource"]}, "synthetic": {"const": True}})
PUBLIC_VIEW = record({
    "schema_version": {"const": 1}, "mode": MODE, "case_id": IDENTIFIER, "task": {"enum": ["detection", "action"]},
    "window_start": UTC, "decision_time": UTC, "assets": array(PUBLIC_ASSET, minimum=1),
    "tools": array({"enum": list(TOOLS)}, unique=True),
    "limits": record({"max_rows": {"const": 10000}, "max_age_seconds": {"type": "integer", "minimum": 1, "maximum": 300}}),
    "evidence": record({"scada": array(PUBLIC_SCADA), "alarms": array(PUBLIC_ALARM),
                        "knowledge": array(PUBLIC_KNOWLEDGE), "topology": array(PUBLIC_TOPOLOGY)}, TOOLS),
    "quality": array(QUALITY_ROW),
    "event_conditions": EVENT_CONDITIONS,
}, ("event_conditions",))
PUBLIC_VIEW["allOf"] = [{"if": {"properties": {"task": {"const": "action"}}},
                         "then": {"required": ["event_conditions"]}, "else": {"not": {"required": ["event_conditions"]}}}]
LABEL = record({
    "schema_version": {"const": 1}, "visibility": {"const": "evaluator_only"}, "mode": MODE,
    "case_id": IDENTIFIER, "scenario_id": IDENTIFIER, "incident_id": IDENTIFIER, "split": {"enum": ["development", "holdout"]},
    "kind": {"enum": ["detection", "action"]}, "template_id": IDENTIFIER, "variant": TEXT, "source_event_ids": IDS,
    "expected": EXPECTED, "observable_classification": {"type": ["string", "null"]},
    "event_time_tolerance_seconds": {"type": "integer", "minimum": 0, "maximum": 3600},
    "max_detection_latency_seconds": {"type": "integer", "minimum": 0, "maximum": 86400},
    "asset_bindings": array({"type": "object"}), "time_context": {"type": "object"},
    "forensic_truth": array({"type": "object"}), "action_prerequisites": array({"type": "object"}),
    "parameters": {"type": "object"}, "assumptions": array(TEXT),
    "action_order": array({"enum": list(ACTIONS)}, unique=True),
    "acceptable_action_alternatives": array(array({"enum": list(ACTIONS)}, unique=True)),
})


def validate(schema: dict, value: Any, name: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: str(list(error.path)))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path)
        if error.validator == "required" and "event_conditions" in error.message:
            raise InvalidInput(f"{name}.{location}: action event_conditions required; explicitly update legacy authoring and regenerate into NEW_PACK/NEW_RUN; preserve prior evidence")
        raise InvalidInput(f"{name}.{location}: {error.message}")