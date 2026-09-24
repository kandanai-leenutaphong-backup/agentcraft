"""Foundry/OpenAI evaluation read-back over a caller-owned OpenAI client: rows, criteria, counts, target text."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import json
import math
import time
from typing import Any

from .bounds import PollResult, poll_until
from .errors import BoundExceededError, RefusedError, VerificationError
from .records import to_plain

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled", "cancelled"})
DATASET_VERSION_MAX = 50
NULLABLE_CRITERION_FIELDS = frozenset({"input", "labels", "model", "passing_labels"})
MAX_TEXT_BYTES = 1_000_000
MAX_BLOCKS = 128


class PartialRowsError(BoundExceededError):
    """Row collection stopped early; `partial` holds rows and resume cursor for retention."""

    def __init__(self, code: str, message: str, partial: dict[str, Any]) -> None:
        super().__init__(code, message)
        self.partial = partial


def validate_dataset_version(version: str) -> str:
    """Dataset registration rejects versions over 50 characters even when pending upload accepted them."""
    if not isinstance(version, str) or not version or len(version) > DATASET_VERSION_MAX:
        raise RefusedError("dataset_version", f"dataset version must be 1-{DATASET_VERSION_MAX} characters")
    return version


def wait_for_run(client: Any, *, eval_id: str, run_id: str, attempts: int = 30, interval: float = 10.0,
                 seconds: float = 600.0, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> PollResult[Any]:
    """Poll `evals.runs.retrieve` to a terminal status. Timeout cancels nothing server-side."""
    return poll_until(lambda: client.evals.runs.retrieve(run_id=run_id, eval_id=eval_id),
                      lambda run: getattr(run, "status", None) in TERMINAL_RUN_STATUSES,
                      attempts=attempts, interval=interval, seconds=seconds, sleep=sleep, clock=clock)


def collect_rows(client: Any, *, eval_id: str, run_id: str, expected_count: int, max_pages: int = 20,
                 seconds: float = 120.0, clock: Callable[[], float] = time.monotonic) -> list[dict[str, Any]]:
    """All output items across pages; duplicate/missing ids, surplus rows, page or time bound refuse."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = None
    deadline = clock() + seconds

    def stop(code: str, message: str) -> PartialRowsError:
        return PartialRowsError(code, message, {"eval_id": eval_id, "run_id": run_id, "rows": list(rows),
                                                "last_id": cursor, "complete": False})

    pager = client.evals.runs.output_items.list(eval_id=eval_id, run_id=run_id, limit=min(100, expected_count + 1))
    for index, page in enumerate(pager.iter_pages()):
        if index >= max_pages or clock() >= deadline:
            raise stop("evaluation_pages", "evaluation pagination bound exceeded; resume retained cursor")
        cursor = getattr(page, "last_id", None)
        for model in page.data:
            row = to_plain(model)
            identifier = row.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in seen:
                raise stop("row_identity", "duplicate or missing output identity")
            if len(rows) >= expected_count:
                raise stop("row_surplus", "too many evaluation rows")
            seen.add(identifier)
            rows.append(row)
    return rows


def check_counts(counts: Mapping[str, Any] | None, *, total: int, errored: int = 0, skipped: int = 0,
                 passed: int | None = None, failed: int | None = None) -> dict[str, int]:
    counts = counts or {}
    expected = {"total": total, "errored": errored, "skipped": skipped, "passed": passed, "failed": failed}
    names = [key for key, value in expected.items() if value is not None] + ["passed", "failed"]
    if any(type(counts.get(key)) is not int for key in names):
        raise VerificationError("counts_shape", "aggregate counts missing or non-integer")
    drifted = sorted(key for key, value in expected.items() if value is not None and counts[key] != value)
    if drifted or counts["passed"] + counts["failed"] + counts["errored"] + counts["skipped"] != counts["total"]:
        raise VerificationError("counts_mismatch", "aggregate counts mismatch: " + ", ".join(drifted or ["sum"]))
    return {key: counts[key] for key in ("total", "passed", "failed", "errored", "skipped")}


def check_criteria(actual: Any, expected: list[Mapping[str, Any]]) -> None:
    """Registered `testing_criteria` read-back: requested fields equal; extras only a service id or nulls."""
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise VerificationError("criteria_count", "testing criteria count mismatch")
    for observed, requested in zip(actual, expected):
        if any(observed.get(key) != value for key, value in requested.items()):
            raise VerificationError("criteria_drift", "testing criterion contract drift")
        for key in observed.keys() - requested.keys():
            if key == "id" and isinstance(observed[key], str) and observed[key]:
                continue
            if key not in NULLABLE_CRITERION_FIELDS or observed[key] is not None:
                raise VerificationError("criteria_field", f"unexpected criterion field: {key}")


def check_row(row: Mapping[str, Any], *, eval_id: str, run_id: str) -> None:
    identifier = row.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise VerificationError("row_identity", "row identity missing")
    if row.get("eval_id") != eval_id or row.get("run_id") != run_id:
        raise VerificationError("row_foreign", "foreign row identity")
    if row.get("status") != "completed" or row.get("error"):
        raise VerificationError("row_incomplete", "row incomplete or errored")


def check_membership(rows: list[Mapping[str, Any]], *, expected: Iterable[Any], key: str = "query") -> None:
    """Exactly one row per expected `datasource_item[key]`; no duplicates, no foreign or missing members."""
    wanted = set(expected)
    values = [(row.get("datasource_item") or {}).get(key) for row in rows]
    if len(rows) != len(wanted) or len(set(values)) != len(values) or set(values) != wanted:
        raise VerificationError("row_membership", "duplicate, missing or foreign row")
    if len({row.get("id") for row in rows}) != len(rows):
        raise VerificationError("row_identity", "duplicate output identity")


def check_criterion(result: Mapping[str, Any], *, name: str, metric: str, evaluator_name: str | None = None,
                    evaluator_version: str | None = None, kind: str = "azure_ai_evaluator") -> bool:
    """One row criterion result; returns the provider `passed` flag after shape and identity checks."""
    if not isinstance(result, Mapping) or (result.get("name"), result.get("metric"), result.get("type")) != (name, metric, kind):
        raise VerificationError("criterion_identity", "criterion name/type/metric mismatch")
    if result.get("status") != "completed" or result.get("error"):
        raise VerificationError("criterion_incomplete", "criterion incomplete or errored")
    score = result.get("score")
    if type(score) not in (int, float) or not math.isfinite(score):
        raise VerificationError("criterion_score", "nonfinite or nonnumeric score")
    if type(result.get("passed")) is not bool:
        raise VerificationError("criterion_passed", "criterion pass flag missing")
    for field, value in (("evaluator_name", evaluator_name), ("evaluator_version", evaluator_version)):
        if field in result and value is not None and result[field] != value:
            raise VerificationError("criterion_evaluator", "criterion evaluator identity mismatch")
    return result["passed"]


def _assistant_text(messages: Any) -> str | None:
    if not isinstance(messages, list) or len(messages) > MAX_BLOCKS:
        raise VerificationError("target_shape", "malformed target messages")
    texts = []
    for message in messages:
        if not isinstance(message, dict):
            raise VerificationError("target_shape", "malformed target message")
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            if len(content.encode()) > MAX_TEXT_BYTES:
                raise VerificationError("target_size", "target content too large")
            try:
                blocks = json.loads(content)
            except json.JSONDecodeError:
                blocks = None
            if not isinstance(blocks, list):
                texts.append(content)
                continue
        else:
            blocks = content
        if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
            raise VerificationError("target_shape", "malformed target blocks")
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "output_text" or not isinstance(block.get("text"), str):
                raise VerificationError("target_shape", "malformed target text block")
            texts.append(block["text"])
    return "".join(texts) if texts else None


def target_text(row: Any) -> str:
    """The single agreed target output of an output item across every representation the service emits."""
    row = to_plain(row)
    if not isinstance(row, dict):
        raise VerificationError("target_shape", "output row must be an object")
    item, sample = row.get("datasource_item") or {}, row.get("sample")
    if not isinstance(item, dict) or (sample is not None and not isinstance(sample, dict)):
        raise VerificationError("target_shape", "malformed target containers")
    outputs = [owner[key] for owner in (item, row) for key in ("response", "sample.output_text", "output_text")
               if key in owner]
    if "sample" in item:
        if not isinstance(item["sample"], dict) or "output_text" not in item["sample"]:
            raise VerificationError("target_shape", "malformed nested target")
        outputs.append(item["sample"]["output_text"])
    if sample:
        if sample.get("output_text") is not None:
            outputs.append(sample["output_text"])
        if "output" in sample:
            text = _assistant_text(sample["output"])
            if text is not None:
                outputs.append(text)
    if not outputs or any(not isinstance(value, str) or len(value.encode()) > MAX_TEXT_BYTES for value in outputs):
        raise VerificationError("target_missing", "target output missing or malformed")
    if any(value != outputs[0] for value in outputs):
        raise VerificationError("target_conflict", "service output representations disagree")
    return outputs[0]
