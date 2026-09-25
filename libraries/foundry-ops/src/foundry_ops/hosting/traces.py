"""Tool-call records from a stored or streamed Responses response and hosted-agent tool events.

Sources, merged by `call_id` in first-seen order:
- native output items: `function_call` / `function_call_output`, `custom_tool_call` / `_output`, `mcp_call`;
- streamed `response.output_item.added|done` items retained by `hosted.invoke(stream=True)` (timing);
- hosted-agent (llm_interface / MAF) events `{kind: tool.call.ready|tool.started|tool.result|tool.failed, data}`,
  passed directly, found in a JSON envelope in the assistant text (`envelope_key`), or in response
  metadata (`metadata_key` holding a JSON list);
- caller-declared metadata records: every `metadata[<metadata_prefix><id>]` JSON object with `call_id`.
A declared source that is absent or malformed, or an expected tool without a record, raises.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from typing import Any

from ..core.errors import BoundExceededError, VerificationError
from ..core.records import to_plain

FIELDS = ("call_id", "name", "arguments", "output", "status", "error_code", "started_at", "ended_at",
          "duration_ms", "sources")
FAILED_STATUSES = frozenset({"failed", "error", "incomplete", "cancelled"})
EVENT_TIME_KEYS = ("timestamp", "at", "created_at", "time")


def output_text(response: Any) -> str:
    """Concatenated `output_text` blocks of assistant message items."""
    response = to_plain(response) or {}
    return "".join(block.get("text", "") for item in response.get("output") or []
                   if isinstance(item, Mapping) and item.get("type") == "message" and item.get("role", "assistant") == "assistant"
                   for block in item.get("content") or []
                   if isinstance(block, Mapping) and block.get("type") == "output_text")


def _parse(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def _loads_list(value: Any, what: str) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as error:
            raise VerificationError("trace_source_malformed", f"{what} is not JSON") from error
    if not isinstance(value, list):
        raise VerificationError("trace_source_malformed", f"{what} must be a list")
    return value


class _Collector:
    def __init__(self, max_calls: int) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.max_calls = max_calls
        self.native_seen: set[tuple[str, str]] = set()

    def record(self, call_id: Any, source: str) -> dict[str, Any]:
        if not isinstance(call_id, str) or not call_id:
            raise VerificationError("trace_call_id", "tool call without call id")
        if call_id not in self.records:
            if len(self.records) >= self.max_calls:
                raise BoundExceededError("trace_calls", "tool call bound exceeded")
            self.records[call_id] = {field: None for field in FIELDS} | {"call_id": call_id, "sources": []}
        record = self.records[call_id]
        if source not in record["sources"]:
            record["sources"].append(source)
        return record

    @staticmethod
    def set(record: dict[str, Any], field: str, value: Any) -> None:
        if value is None:
            return
        if field == "name" and record["name"] is not None and record["name"] != value:
            raise VerificationError("trace_conflict", "tool name disagrees across sources")
        if field == "call_id":
            return
        if record[field] is None or (field == "status" and value in FAILED_STATUSES
                                     and record["status"] not in FAILED_STATUSES):
            record[field] = _parse(value) if field == "arguments" else value

    def native(self, item: Mapping[str, Any], source: str) -> None:
        kind = item.get("type")
        if kind in ("function_call", "custom_tool_call", "mcp_call"):
            call_id = item.get("id") if kind == "mcp_call" else item.get("call_id")
            if (kind, call_id) in self.native_seen:
                raise VerificationError("trace_duplicate", "duplicate tool call item")
            self.native_seen.add((kind, call_id))
            record = self.record(call_id, source)
            self.set(record, "name", item.get("name"))
            self.set(record, "arguments", item.get("input" if kind == "custom_tool_call" else "arguments"))
            if kind == "mcp_call":
                error = item.get("error")
                if error:
                    self.set(record, "error_code", error.get("code") if isinstance(error, Mapping) else str(error))
                    self.set(record, "status", "failed")
                self.set(record, "output", item.get("output"))
            self.set(record, "status", item.get("status"))
        elif kind in ("function_call_output", "custom_tool_call_output"):
            record = self.record(item.get("call_id"), source)
            self.set(record, "output", item.get("output"))
            self.set(record, "status", item.get("status"))

    def stream_item(self, entry: Mapping[str, Any]) -> None:
        item = entry.get("item") or {}
        if not isinstance(item, Mapping) or item.get("type") not in ("function_call", "custom_tool_call", "mcp_call"):
            return
        call_id = item.get("id") if item.get("type") == "mcp_call" else item.get("call_id")
        record = self.record(call_id, "stream")
        self.set(record, "name", item.get("name"))
        if entry.get("type") == "response.output_item.added":
            self.set(record, "started_at", entry.get("seconds"))
        elif entry.get("type") == "response.output_item.done":
            self.set(record, "ended_at", entry.get("seconds"))
            self.set(record, "arguments", item.get("input" if item.get("type") == "custom_tool_call" else "arguments"))

    def event(self, event: Mapping[str, Any], source: str) -> None:
        kind = event.get("kind") or event.get("type")
        data = event.get("data") if isinstance(event.get("data"), Mapping) else event
        if kind not in ("tool.call.ready", "tool.started", "tool.result", "tool.failed"):
            return
        record = self.record(data.get("call_id"), source)
        self.set(record, "name", data.get("name"))
        at = next((value for value in (event.get(key) for key in EVENT_TIME_KEYS) if value is not None),
                  next((data.get(key) for key in EVENT_TIME_KEYS if data.get(key) is not None), None))
        if kind == "tool.call.ready":
            self.set(record, "arguments", data.get("arguments"))
        elif kind == "tool.started":
            self.set(record, "started_at", data.get("started_at", at))
        elif kind == "tool.result":
            self.set(record, "output", data.get("result"))
            self.set(record, "ended_at", data.get("ended_at", at))
            self.set(record, "status", "completed")
        else:
            self.set(record, "error_code", data.get("code") or data.get("error_code"))
            self.set(record, "ended_at", data.get("ended_at", at))
            self.set(record, "status", "failed")
        self.set(record, "duration_ms", data.get("duration_ms"))

    def fields(self, entry: Mapping[str, Any], source: str) -> None:
        record = self.record(entry.get("call_id"), source)
        for field in FIELDS[1:-1]:
            self.set(record, field, entry.get("result") if field == "output" and "output" not in entry
                     else entry.get(field))


def tool_calls(response: Any = None, *, events: Iterable[Mapping[str, Any]] | None = None,
               stream_items: Iterable[Mapping[str, Any]] | None = None, envelope_key: str | None = None,
               metadata_key: str | None = None, metadata_prefix: str | None = None, expected: Iterable[str] = (),
               max_calls: int = 1000) -> list[dict[str, Any]]:
    """One record per `call_id`, first-seen order, fields `FIELDS` (None when no source carried one):
    `call_id, name, arguments` (JSON-decoded when possible), `output` (raw tool output / result), `status`
    (any failure status wins), `error_code, started_at, ended_at, duration_ms, sources`.

    `response` may be an SDK model, a Responses dict, or a `hosted.invoke` result (`{response, stream}`),
    whose streamed items give stream-relative `started_at`/`ended_at` seconds; numeric pairs yield
    `duration_ms` when no source declared one.
    """
    response = to_plain(response)
    if isinstance(response, Mapping) and "response" in response and "output" not in response:
        if stream_items is None:
            stream_items = (response.get("stream") or {}).get("items")
        response = response["response"]
    collector = _Collector(max_calls)
    for item in (response or {}).get("output") or []:
        if isinstance(item, Mapping):
            collector.native(item, "output")
    for entry in stream_items or []:
        collector.stream_item(entry)
    sources: list[tuple[str, Iterable[Any]]] = [("events", events or [])]
    if envelope_key is not None:
        text = output_text(response)
        try:
            envelope = json.loads(text)
        except ValueError as error:
            raise VerificationError("trace_source_missing", "assistant text is not a JSON envelope") from error
        if not isinstance(envelope, Mapping) or envelope_key not in envelope:
            raise VerificationError("trace_source_missing", f"envelope key absent: {envelope_key}")
        sources.append(("envelope", _loads_list(envelope[envelope_key], "envelope tool events")))
    if metadata_key is not None:
        metadata = (response or {}).get("metadata") or {}
        if metadata_key not in metadata:
            raise VerificationError("trace_source_missing", f"metadata key absent: {metadata_key}")
        sources.append(("metadata", _loads_list(metadata[metadata_key], "metadata tool events")))
    if metadata_prefix:
        metadata = (response or {}).get("metadata") or {}
        entries = []
        for name in sorted(key for key in metadata if str(key).startswith(metadata_prefix)):
            value = _parse(metadata[name])
            if not isinstance(value, Mapping) or not value.get("call_id"):
                raise VerificationError("trace_source_malformed", f"metadata tool record malformed: {name}")
            entries.append(value)
        sources.append(("metadata", entries))
    for source, entries in sources:
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise VerificationError("trace_source_malformed", "tool event must be an object")
            if "kind" in entry or str(entry.get("type", "")).startswith("tool."):
                collector.event(entry, source)
            elif "call_id" in entry:
                collector.fields(entry, source)
    records = list(collector.records.values())
    for record in records:
        started, ended = record["started_at"], record["ended_at"]
        if record["duration_ms"] is None and all(type(value) in (int, float) for value in (started, ended)):
            record["duration_ms"] = round((ended - started) * 1000, 3)
    missing = sorted(set(expected) - {record["name"] for record in records})
    if missing:
        raise VerificationError("tool_call_missing", "expected tool without record: " + ", ".join(missing))
    return records
