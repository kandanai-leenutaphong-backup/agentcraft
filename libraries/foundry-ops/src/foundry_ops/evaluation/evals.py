"""Foundry/OpenAI evaluation read-back over a caller-owned OpenAI client: rows, criteria, counts, target text."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
import json
import math
import time
from typing import Any

from ..core.bounds import PollResult, poll_until
from ..core.errors import BoundExceededError, FoundryOpsError, OutcomeUnknownError, RefusedError, VerificationError
from ..core.identifiers import safe_identifier, validate_version_label
from ..core.records import EvidenceLedger, error_summary, to_plain

EventSink = Callable[[dict[str, Any]], None]

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled", "cancelled"})
DATASET_VERSION_MAX = 50
NULLABLE_CRITERION_FIELDS = frozenset({"input", "labels", "model", "passing_labels"})
MAX_TEXT_BYTES = 1_000_000
MAX_BLOCKS = 128
MAX_INLINE_ITEMS = 1000
DEFAULT_INPUT_TEMPLATE = "{{item.query}}"
# Assistant tool-call blocks carry no answer text; the tool-role outputs are not assistant messages.
TOOL_CALL_BLOCKS = frozenset({"function_call", "tool_call"})


class PartialRowsError(BoundExceededError):
    """Row collection stopped early; `partial` holds rows and resume cursor for retention."""

    def __init__(self, code: str, message: str, partial: dict[str, Any]) -> None:
        super().__init__(code, message)
        self.partial = partial


def validate_dataset_version(version: str) -> str:
    """Dataset registration rejects versions over 50 characters even when pending upload accepted them."""
    return validate_version_label(version, DATASET_VERSION_MAX, what="dataset version", code="dataset_version")


def wait_for_run(client: Any, *, eval_id: str, run_id: str, attempts: int = 30, interval: float = 10.0,
                 seconds: float = 600.0, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, on_event: EventSink | None = None) -> PollResult[Any]:
    """Poll `evals.runs.retrieve` to a terminal status. Timeout cancels nothing server-side.

    `on_event` receives `{operation: "poll", attempt, utc, status, request_id}` after every read.
    """
    attempt = 0

    def read() -> Any:
        nonlocal attempt
        run = client.evals.runs.retrieve(run_id=run_id, eval_id=eval_id)
        if on_event is not None:
            on_event({"operation": "poll", "attempt": attempt, "utc": datetime.now(timezone.utc).isoformat(),
                      "status": getattr(run, "status", None), "request_id": getattr(run, "_request_id", None)})
        attempt += 1
        return run

    return poll_until(read, lambda run: getattr(run, "status", None) in TERMINAL_RUN_STATUSES,
                      attempts=attempts, interval=interval, seconds=seconds, sleep=sleep, clock=clock)


def collect_rows(client: Any, *, eval_id: str, run_id: str, expected_count: int, max_pages: int = 20,
                 seconds: float = 120.0, clock: Callable[[], float] = time.monotonic,
                 on_event: EventSink | None = None, partial_on_error: bool = False) -> list[dict[str, Any]]:
    """All output items across pages; duplicate/missing ids, surplus rows, page or time bound refuse.

    `on_event` receives `{operation: "page", index, rows, total, last_id}` per page. With
    `partial_on_error`, a transport/SDK failure raises `PartialRowsError("row_transport")` carrying the
    rows read so far and `partial["error"]`, chained from the original exception.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = None
    deadline = clock() + seconds

    def stop(code: str, message: str, error: BaseException | None = None) -> PartialRowsError:
        partial = {"eval_id": eval_id, "run_id": run_id, "rows": list(rows), "last_id": cursor, "complete": False}
        if error is not None:
            partial["error"] = error_summary(error)
        return PartialRowsError(code, message, partial)

    try:
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
            if on_event is not None:
                on_event({"operation": "page", "index": index, "rows": len(page.data), "total": len(rows),
                          "last_id": cursor})
    except FoundryOpsError:
        raise
    except Exception as error:
        if not partial_on_error:
            raise
        raise stop("row_transport", "row collection failed; retain partial rows and resume", error) from error
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
                    evaluator_version: str | None = None, kind: str = "azure_ai_evaluator",
                    strict_version: bool = False) -> bool:
    """One row criterion result; returns the provider `passed` flag after shape and identity checks.

    `strict_version` refuses a non-null `evaluator_version` the service emitted when none was requested.
    """
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
    if strict_version and evaluator_version is None and result.get("evaluator_version") is not None:
        raise VerificationError("criterion_evaluator", "service added an evaluator version the request did not set")
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
            if isinstance(block, dict) and block.get("type") in TOOL_CALL_BLOCKS:
                continue
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


_JSON_TYPES = ((bool, "boolean"), (int, "integer"), (float, "number"), (str, "string"), (dict, "object"),
               (list, "array"))


def infer_item_schema(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Object schema from inline items: every seen key typed from its Python value; keys in all items required."""
    items = list(items)
    if not items or any(not isinstance(item, Mapping) or not item for item in items):
        raise RefusedError("eval_items", "inline items must be non-empty objects")
    properties: dict[str, Any] = {}
    for item in items:
        for key, value in item.items():
            kind = next((name for python, name in _JSON_TYPES if isinstance(value, python)), None)
            if kind is None or properties.setdefault(key, {"type": kind})["type"] != kind:
                raise RefusedError("eval_items", f"item field has no single JSON type: {key}")
    required = sorted(set.intersection(*(set(item) for item in items)))
    return {"type": "object", "properties": properties, "required": required}


def agent_eval_definition(name: str, *, testing_criteria: Iterable[Mapping[str, Any]], item_schema: Mapping[str, Any],
                          include_sample_schema: bool = True) -> dict[str, Any]:
    """`evals.create` request for a target-completions eval: custom item schema plus the target `sample`."""
    criteria = [dict(criterion) for criterion in testing_criteria]
    if not criteria or any(not isinstance(criterion.get("name"), str) or not criterion["name"] for criterion in criteria):
        raise RefusedError("testing_criteria", "at least one named testing criterion required")
    if len({criterion["name"] for criterion in criteria}) != len(criteria):
        raise RefusedError("testing_criteria", "testing criterion names must be unique")
    return {"name": name, "data_source_config": {"type": "custom", "item_schema": dict(item_schema),
                                                 "include_sample_schema": include_sample_schema},
            "testing_criteria": criteria}


def agent_run_request(eval_id: str, *, name: str, agent_name: str, agent_version: str,
                      items: Iterable[Mapping[str, Any]] | None = None, file_id: str | None = None,
                      dataset: Mapping[str, Any] | None = None,
                      input_template: str = DEFAULT_INPUT_TEMPLATE, max_items: int = MAX_INLINE_ITEMS) -> dict[str, Any]:
    """`evals.runs.create` request targeting one hosted agent version; inline `items`, a dataset `file_id`, or a
    registered `dataset` reference (its `azureai://` `id`; same shape as `foundry_ops.data.eval_file_source`)."""
    if sum(source is not None for source in (items, file_id, dataset)) != 1:
        raise RefusedError("eval_source", "exactly one of items, file_id or dataset required")
    if dataset is not None:
        file_id = dataset.get("id") if isinstance(dataset, Mapping) else None
        if not isinstance(file_id, str) or not file_id.startswith("azureai://"):
            raise RefusedError("eval_source", "dataset reference needs an azureai:// version id")
    if items is not None:
        rows = [dict(item) for item in items]
        if not rows or len(rows) > max_items:
            raise RefusedError("eval_items", f"inline items must number 1-{max_items}")
        source: dict[str, Any] = {"type": "file_content", "content": [{"item": row} for row in rows]}
    else:
        source = {"type": "file_id", "id": file_id}
    return {"eval_id": eval_id, "name": name, "data_source": {
        "type": "azure_ai_target_completions", "source": source,
        "input_messages": {"type": "template", "template": [
            {"type": "message", "role": "user", "content": {"type": "input_text", "text": input_template}}]},
        "target": {"type": "azure_ai_agent", "name": safe_identifier(agent_name, "agent name"),
                   "version": str(agent_version)}}}


def create_eval(client: Any, ledger: EvidenceLedger, *, key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    """`evals.create` at most once per `key` (`eval-<key>-{intent,result}.json`), then definition read-back."""
    request = dict(request)

    def call() -> dict[str, Any]:
        created = client.evals.create(**request)
        return {"id": created.id, "request_id": getattr(created, "_request_id", None)}

    created = ledger.once(f"eval-{key}", request, call)
    definition = to_plain(client.evals.retrieve(created["id"]))
    if not isinstance(definition, dict) or definition.get("id") != created["id"]:
        raise VerificationError("eval_identity", "evaluation read-back identity mismatch")
    check_criteria(definition.get("testing_criteria"), request["testing_criteria"])
    return {"id": created["id"], "definition": definition}


def submit_run(client: Any, ledger: EvidenceLedger, *, key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    """`evals.runs.create` at most once per `key` (`eval-run-<key>-{intent,result}.json`)."""
    request = dict(request)

    def call() -> dict[str, Any]:
        run = client.evals.runs.create(**request)
        if not isinstance(getattr(run, "id", None), str) or not run.id:
            raise OutcomeUnknownError("run_identity_unknown", "run accepted without identity; reconcile, never resubmit")
        return {"eval_id": request["eval_id"], "run_id": run.id, "request_id": getattr(run, "_request_id", None)}

    return ledger.once(f"eval-run-{key}", request, call)


def summarize_criteria(rows: Iterable[Mapping[str, Any]], *, criteria_names: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Per-criterion counts over rows; `pass_rate = passed / rows` (errored and missing count against)."""
    rows = list(rows)
    summary = {name: {"passed": 0, "failed": 0, "errored": 0, "missing": 0} for name in criteria_names}
    for row in rows:
        results = row.get("results") or []
        for name, counts in summary.items():
            found = [result for result in results if isinstance(result, Mapping) and result.get("name") == name]
            if len(found) > 1:
                raise VerificationError("criterion_duplicate", f"duplicate criterion result: {name}")
            if not found:
                counts["missing"] += 1
            elif (found[0].get("status") != "completed" or found[0].get("error")
                  or type(found[0].get("passed")) is not bool):
                counts["errored"] += 1
            else:
                counts["passed" if found[0]["passed"] else "failed"] += 1
    for counts in summary.values():
        counts["total"] = len(rows)
        counts["pass_rate"] = counts["passed"] / len(rows) if rows else None
    return summary


def run_agent_eval(client: Any, ledger: EvidenceLedger, *, key: str, name: str, agent_name: str, agent_version: str,
                   testing_criteria: Iterable[Mapping[str, Any]], items: Iterable[Mapping[str, Any]] | None = None,
                   dataset: Mapping[str, Any] | None = None, expected_count: int | None = None,
                   item_schema: Mapping[str, Any] | None = None, input_template: str = DEFAULT_INPUT_TEMPLATE,
                   attempts: int = 60, interval: float = 10.0, seconds: float = 1800.0, max_pages: int = 20,
                   sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                   on_event: EventSink | None = None) -> dict[str, Any]:
    """Create eval, submit one run against `agent_name@agent_version`, wait, collect, summarize per criterion.

    Source is inline `items` or a registered `dataset` reference; a dataset needs `item_schema` and a row
    count (`expected_count` or the reference's `rows`). Resumes from `eval-<key>-summary.json`. Unsettled
    returns `settled: False` (nothing cancelled, never resubmitted); `PartialRowsError` carries rows for
    retention. Criteria are caller-supplied.
    """
    if (items is None) == (dataset is None):
        raise RefusedError("eval_source", "exactly one of items or dataset required")
    if dataset is not None:
        expected_count = expected_count if expected_count is not None else (
            dataset.get("rows") if isinstance(dataset, Mapping) else None)
        if item_schema is None or type(expected_count) is not int or expected_count < 1:
            raise RefusedError("eval_source", "dataset evals need item_schema and a positive row count")
    summary_record = f"eval-{key}-summary.json"
    if ledger.exists(summary_record):
        return ledger.read(summary_record)
    if items is not None:
        items = [dict(item) for item in items]
        expected_count = len(items)
        item_schema = item_schema or infer_item_schema(items)
    definition = agent_eval_definition(name, testing_criteria=testing_criteria, item_schema=item_schema)
    created = create_eval(client, ledger, key=key, request=definition)
    run = submit_run(client, ledger, key=key, request=agent_run_request(
        created["id"], name=name, agent_name=agent_name, agent_version=agent_version, items=items, dataset=dataset,
        input_template=input_template))
    polled = wait_for_run(client, eval_id=run["eval_id"], run_id=run["run_id"], attempts=attempts, interval=interval,
                          seconds=seconds, sleep=sleep, clock=clock, on_event=on_event)
    state = to_plain(polled.value)
    base = {"eval_id": run["eval_id"], "run_id": run["run_id"], "status": state.get("status"),
            "poll_attempts": polled.attempts}
    if not polled.settled:
        return {**base, "settled": False, "next": "reconcile read-only with wait_for_run; never resubmit"}
    if state.get("id") != run["run_id"] or state.get("eval_id") != run["eval_id"]:
        raise VerificationError("run_identity", "run read-back identity mismatch")
    rows = collect_rows(client, eval_id=run["eval_id"], run_id=run["run_id"], expected_count=expected_count,
                        max_pages=max_pages, clock=clock, on_event=on_event, partial_on_error=True)
    if any(row.get("eval_id") != run["eval_id"] or row.get("run_id") != run["run_id"] for row in rows):
        raise VerificationError("row_foreign", "foreign row identity")
    result = {**base, "settled": True,
              "complete": state.get("status") == "completed" and not state.get("error") and len(rows) == expected_count,
              "error": state.get("error"), "result_counts": state.get("result_counts"),
              "per_testing_criteria_results": state.get("per_testing_criteria_results"),
              "summary": summarize_criteria(rows, criteria_names=[c["name"] for c in definition["testing_criteria"]]),
              "rows": rows}
    ledger.retain(summary_record, result)
    return result
