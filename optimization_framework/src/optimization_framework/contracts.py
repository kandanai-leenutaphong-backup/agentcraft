"""Local reference contracts. No document selects executable code or identity."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

SCHEMA_VERSION = 1
LOCAL_OPERATOR = "local-operator"
TERMINAL = frozenset({"completed", "failed", "blocked", "cancelled", "timed_out"})


class Refusal(Exception):
    """Expected refusal with a stable code and HTTP status."""

    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def text(value: object, field: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Refusal(f"invalid_{field}")
    return value


@runtime_checkable
class TaskAdapter(Protocol):
    """Trusted host code; documents can select an id, never install an adapter."""

    id: str

    def describe(self) -> dict: ...

    def baseline(self) -> dict: ...

    def validate_candidate(self, config: dict) -> None: ...

    def evaluate(self, snapshot: dict, baseline: bool) -> list[dict]: ...


def strict_json(content: str, code: str, maximum: int = 8192) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        if not isinstance(content, str) or len(content.encode("utf-8")) > maximum:
            raise ValueError("bounded JSON required")
        value = json.loads(content, object_pairs_hook=unique,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError("constant")))
        if not isinstance(value, dict):
            raise ValueError("object required")
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refusal(code, 409) from error


def experiment_document(document: dict) -> dict:
    try:
        document = strict_json(canonical(document).decode(), "invalid_experiment", 32768)
    except (ValueError, TypeError, RecursionError) as error:
        raise Refusal("invalid_experiment") from error
    required = {"schema_version", "task_id", "task_version", "executor", "limits",
                "primary_metric", "quality_constraints"}
    if not required <= set(document) or set(document) - required - {"pins"}:
        raise Refusal("invalid_experiment_fields")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise Refusal("invalid_experiment_schema_version")
    text(document["task_id"], "experiment_task_id", 128)
    if type(document["task_version"]) is not int or document["task_version"] < 1:
        raise Refusal("invalid_experiment_task_version")
    if document["executor"] not in ("deterministic", "copilot"):
        raise Refusal("unsupported_executor")
    limits = document["limits"]
    if not isinstance(limits, dict) or set(limits) != {"max_submissions", "timeout_seconds"}:
        raise Refusal("invalid_experiment_limits")
    if type(limits["max_submissions"]) is not int or not 1 <= limits["max_submissions"] <= 2:
        raise Refusal("invalid_experiment_limits_max_submissions")
    if type(limits["timeout_seconds"]) not in (int, float) or not 0 < limits["timeout_seconds"] <= 120:
        raise Refusal("invalid_experiment_limits_timeout_seconds")
    if document["primary_metric"] not in ("time_to_verified_acceptance_seconds", "elapsed_seconds"):
        raise Refusal("unknown_primary_metric")
    checks = document["quality_constraints"]
    if (not isinstance(checks, list) or not checks or any(not isinstance(name, str) for name in checks)
            or len(set(checks)) != len(checks)):
        raise Refusal("invalid_experiment_quality_constraints")
    if "pins" in document:
        pins = document["pins"]
        if (not isinstance(pins, dict) or set(pins) != {"task_digest", "evaluator_digest"}
                or any(not isinstance(value, str) or len(value) != 64
                       or any(character not in "0123456789abcdef" for character in value) for value in pins.values())):
            raise Refusal("invalid_experiment_pins")
    return document