"""Custom code evaluator registration and positive/wrong/invalid canaries over caller-owned clients.

`project` is an `AIProjectClient` (uses `project.beta.evaluators`); `client` is its OpenAI client (`evals`).
No SDK import: requests are plain mappings, which `create_version` accepts. Registration omits the metric
threshold, so canaries check scores directly, never provider `passed` flags.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
import math
import time
from typing import Any

from ..core.errors import OutcomeUnknownError, RefusedError, VerificationError
from ..core.identifiers import safe_identifier
from ..core.records import EvidenceLedger, to_plain
from .evals import EventSink, collect_rows, create_eval, submit_run, wait_for_run

DEFAULT_INIT_PARAMETERS = {"properties": {}, "required": [], "type": "object"}


def code_evaluator_definition(code_text: str, *, metric: str, data_schema: Mapping[str, Any], display_name: str,
                              description: str = "", categories: Sequence[str] = ("quality",),
                              metric_type: str = "continuous", desirable_direction: str = "increase",
                              min_value: float = 0, max_value: float = 1) -> dict[str, Any]:
    """`EvaluatorVersion` body for a `grade(sample, item)` code evaluator with one primary metric."""
    if not isinstance(code_text, str) or "def " not in code_text:
        raise RefusedError("evaluator_code", "code evaluator source must define a function")
    return {"evaluator_type": "custom", "categories": list(categories), "display_name": display_name,
            "description": description,
            "definition": {"type": "code", "code_text": code_text, "data_schema": dict(data_schema),
                           "metrics": {metric: {"type": metric_type, "desirable_direction": desirable_direction,
                                                "min_value": min_value, "max_value": max_value, "is_primary": True}}}}


def local_canary(code_text: str, cases: Iterable[Mapping[str, Any]], *, entry: str = "grade") -> dict[str, Any]:
    """Run `entry(sample, item)` for each `{item, expected, sample=None}` case; mismatch raises.

    Executes `code_text` in-process: pass only the caller's own reviewed evaluator source.
    """
    namespace: dict[str, Any] = {}
    exec(compile(code_text, "<code-evaluator>", "exec"), namespace)  # noqa: S102 - caller-owned source
    grade = namespace.get(entry)
    if not callable(grade):
        raise RefusedError("evaluator_code", f"evaluator source defines no callable {entry}")
    scores, expected = [], []
    for case in cases:
        try:
            scores.append(grade(case.get("sample"), case["item"]))
        except Exception as error:
            scores.append({"error": type(error).__name__})
        expected.append(case["expected"])
    if not scores:
        raise RefusedError("canary_cases", "at least one canary case required")
    if scores != expected:
        raise VerificationError("local_canary", "local evaluator canary scores mismatch")
    return {"scores": scores, "expected": expected, "passed": True}


def check_registered_evaluator(actual: Mapping[str, Any], *, name: str, version: str,
                               definition: Mapping[str, Any]) -> None:
    """Read-back equals the requested code definition; service defaults for init parameters/prompt text allowed."""
    expected = {"init_parameters": DEFAULT_INIT_PARAMETERS, "prompt_text": "", **dict(definition["definition"])}
    observed = {"init_parameters": DEFAULT_INIT_PARAMETERS, "prompt_text": "", **dict(actual.get("definition") or {})}
    drifted = sorted(key for key in expected.keys() | observed.keys() if expected.get(key) != observed.get(key))
    if actual.get("name") != name:
        drifted.insert(0, "name")
    if str(actual.get("version")) != str(version):
        drifted.insert(0, "version")
    if drifted:
        raise VerificationError("evaluator_readback", "registered evaluator mismatch: " + ", ".join(drifted))


def register_code_evaluator(project: Any, ledger: EvidenceLedger, *, name: str, definition: Mapping[str, Any],
                            key: str | None = None) -> dict[str, Any]:
    """`beta.evaluators.create_version` at most once (`evaluator-<key|name>-{intent,result}.json`), then read-back."""
    safe_identifier(name, "evaluator name")
    created = ledger.once(f"evaluator-{key or name}", {"name": name, "definition": dict(definition)},
                          lambda: to_plain(project.beta.evaluators.create_version(name=name,
                                                                                  evaluator_version=dict(definition))))
    version = str(created.get("version") or "")
    if not version:
        raise OutcomeUnknownError("evaluator_version_unknown", "evaluator accepted but version unknown; read back")
    actual = to_plain(project.beta.evaluators.get_version(name=name, version=version))
    check_registered_evaluator(actual, name=name, version=version, definition=definition)
    return {"name": name, "version": version, "readback": actual}


def canary_eval_request(name: str, *, evaluator_name: str, evaluator_version: str, criterion_name: str,
                        item_schema: Mapping[str, Any], data_mapping: Mapping[str, str]) -> dict[str, Any]:
    return {"name": name, "data_source_config": {"type": "custom", "item_schema": dict(item_schema)},
            "testing_criteria": [{"type": "azure_ai_evaluator", "name": criterion_name, "evaluator_name": evaluator_name,
                                  "evaluator_version": evaluator_version, "data_mapping": dict(data_mapping)}]}


def canary_run_request(eval_id: str, *, name: str, cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return {"eval_id": eval_id, "name": name, "data_source": {"type": "jsonl", "source": {
        "type": "file_content", "content": [{"item": dict(case["item"])} for case in cases]}}}


def check_canary_rows(rows: Iterable[Mapping[str, Any]], *, eval_id: str, run_id: str, criterion_name: str,
                      match_field: str, expected: Mapping[Any, float], metric: str | None = None) -> dict[str, Any]:
    """One completed row per expected `datasource_item[match_field]`; its single score must equal expected."""
    remaining = dict(expected)
    scores: dict[str, Any] = {}
    mismatches = 0
    for row in rows:
        value = (row.get("datasource_item") or {}).get(match_field)
        results = row.get("results") or []
        criterion = results[0] if len(results) == 1 and isinstance(results[0], Mapping) else {}
        score = criterion.get("score")
        good = (row.get("status") == "completed" and not row.get("error") and row.get("eval_id") == eval_id
                and row.get("run_id") == run_id and value in remaining
                and (criterion.get("name"), criterion.get("metric"), criterion.get("type"))
                == (criterion_name, metric or criterion_name, "azure_ai_evaluator")
                and criterion.get("status") == "completed" and not criterion.get("error")
                and type(score) in (int, float) and math.isfinite(score) and score == remaining[value])
        if good:
            remaining.pop(value)
        else:
            mismatches += 1
        scores[str(value)] = score
    return {"passed": not mismatches and not remaining, "mismatched_rows": mismatches, "missing": len(remaining),
            "scores": scores}


def run_code_evaluator_canary(client: Any, ledger: EvidenceLedger, *, key: str, evaluator_name: str,
                              evaluator_version: str, criterion_name: str, item_schema: Mapping[str, Any],
                              data_mapping: Mapping[str, str], cases: Sequence[Mapping[str, Any]], match_field: str,
                              metric: str | None = None, attempts: int = 30, interval: float = 10.0,
                              seconds: float = 600.0, sleep: Callable[[float], None] = time.sleep,
                              clock: Callable[[], float] = time.monotonic,
                              on_event: EventSink | None = None) -> dict[str, Any]:
    """Native canary: eval with one criterion over inline `{item, expected}` cases, scores checked exactly.

    Typical cases are positive/wrong/invalid with expected 1/0/0; `match_field` must be unique per case
    (use the native field, e.g. `sample.output_text`, when that is what the optimizer supplies).
    Retains `evaluator-canary-<key>-result.json` (passed or not); a failed canary then raises.
    """
    result_record = f"evaluator-canary-{key}-result.json"
    if ledger.exists(result_record):
        result = ledger.read(result_record)
    else:
        values = [case["item"].get(match_field) for case in cases]
        if not values or len(set(map(repr, values))) != len(values):
            raise RefusedError("canary_cases", "canary cases need unique match_field values")
        expected = {case["item"][match_field]: case["expected"] for case in cases}
        created = create_eval(client, ledger, key=f"canary-{key}", request=canary_eval_request(
            f"canary-{key}", evaluator_name=evaluator_name, evaluator_version=evaluator_version,
            criterion_name=criterion_name, item_schema=item_schema, data_mapping=data_mapping))
        run = submit_run(client, ledger, key=f"canary-{key}",
                         request=canary_run_request(created["id"], name=f"canary-{key}", cases=cases))
        polled = wait_for_run(client, eval_id=run["eval_id"], run_id=run["run_id"], attempts=attempts,
                              interval=interval, seconds=seconds, sleep=sleep, clock=clock, on_event=on_event)
        if not polled.settled:
            return {"settled": False, "passed": False, "eval_id": run["eval_id"], "run_id": run["run_id"],
                    "status": getattr(polled.value, "status", None)}
        rows = collect_rows(client, eval_id=run["eval_id"], run_id=run["run_id"], expected_count=len(cases),
                            clock=clock, on_event=on_event, partial_on_error=True)
        checked = check_canary_rows(rows, eval_id=run["eval_id"], run_id=run["run_id"], criterion_name=criterion_name,
                                    match_field=match_field, expected=expected, metric=metric)
        result = {"settled": True, "eval_id": run["eval_id"], "run_id": run["run_id"],
                  "status": getattr(polled.value, "status", None), "evaluator": {"name": evaluator_name,
                                                                                 "version": evaluator_version},
                  **checked, "rows": rows}
        ledger.retain(result_record, result)
    if not result["passed"]:
        raise VerificationError("canary_failed", "native evaluator canary scores mismatch; inspect retained result")
    return result
