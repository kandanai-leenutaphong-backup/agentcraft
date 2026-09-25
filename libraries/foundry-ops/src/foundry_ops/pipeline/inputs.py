"""Caller inputs bound to a RunSpec: bytes only when pinned, rows, journeys, referenced files, dataset refs."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

from ..core import EvidenceLedger, RefusedError, safe_identifier, sha256_hex
from .spec import RunSpec

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_JOURNEYS = 20
JOURNEY_STATUSES = frozenset({"ok", "error"})
JOURNEY_FIELDS = frozenset({"id", "input", "stream", "expected_tools", "expected_answer", "notes"})


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def read_input(spec: RunSpec, kind: str, path: str | os.PathLike[str] | None = None) -> bytes:
    """Bytes of `path` (or the spec's one declared file) only when `inputs.<kind>` pins exactly these bytes."""
    if path is None:
        declared = spec.declared(kind)
        if declared is None:
            raise RefusedError(f"{kind}_missing", f"{kind} file required")
        path = spec.repo / declared
    source = Path(path)
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(spec.repo.resolve()):
        raise RefusedError("input_path", f"{kind} file missing, symlinked or outside the repository")
    data = source.read_bytes()
    if len(data) > MAX_INPUT_BYTES:
        raise RefusedError("input_size", f"{kind} file exceeds {MAX_INPUT_BYTES} bytes")
    pins = [ref.sha256 for ref in spec.inputs.get(kind, ()) if ref.sha256]
    if not pins:
        raise RefusedError("input_unpinned", f"{kind} file is not pinned in run inputs.{kind}")
    digest = sha256_hex(data)
    if digest not in pins:
        raise RefusedError("input_pin", f"{kind} file differs from run inputs.{kind}")
    spec.observed_inputs[kind] = {"path": str(source), "sha256": digest}
    return data


def parse_json(data: bytes, kind: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError as error:
        raise RefusedError(f"{kind}_syntax", f"{kind} file is not UTF-8 JSON") from error


def input_json(spec: RunSpec, kind: str, path: Any = None) -> Any:
    return parse_json(read_input(spec, kind, path), kind)


def read_rows(data: bytes, kind: str) -> list[dict[str, Any]]:
    """JSON list or JSONL of non-empty objects; empty refuses as `<kind>_missing`."""
    try:
        text = data.decode("utf-8").strip()
        rows = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError as error:
        raise RefusedError(f"{kind}_syntax", f"{kind} file is not JSON or JSONL") from error
    if not rows:
        raise RefusedError(f"{kind}_missing", f"{kind} file has no rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not row for row in rows):
        raise RefusedError(f"{kind}_shape", f"{kind} rows must be non-empty objects")
    return rows


def project_rows(rows: list[dict[str, Any]], fields: Any, allowed: frozenset[str] | None, kind: str) -> list[dict[str, Any]]:
    if fields is None:
        return rows if allowed is None else [{key: row[key] for key in row if key in allowed} for row in rows]
    if not isinstance(fields, list) or not fields or any(not isinstance(name, str) for name in fields) \
            or (allowed is not None and set(fields) - allowed):
        raise RefusedError(f"{kind}_fields", f"{kind} item_fields must be a non-empty list of allowed names")
    return [{key: row[key] for key in fields if key in row} for row in rows]


def bounded_seconds(value: Any, ceiling: float) -> float:
    if type(value) not in (int, float) or not 0 < value <= ceiling:
        raise RefusedError("wait_bound", f"wait_seconds must be in (0, {ceiling:g}]")
    return float(value)


def referenced_file(spec_path: Any, relative: Any, pinned: Any, what: str) -> bytes:
    """A file named relative to a pinned spec, itself pinned by sha256 inside that spec."""
    base = Path(spec_path).resolve().parent
    if not isinstance(relative, str) or not isinstance(pinned, str):
        raise RefusedError(f"{what}_pin", f"{what} file needs a relative path and its sha256")
    source = base / relative
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(base):
        raise RefusedError("input_path", f"{what} file missing, symlinked or outside its spec folder")
    data = source.read_bytes()
    if sha256_hex(data) != pinned:
        raise RefusedError(f"{what}_pin", f"{what} file differs from its pinned sha256")
    return data


def load_journeys(spec: RunSpec, path: Any = None) -> list[dict[str, Any]]:
    """`{"journeys": [{id, input, stream, expected_tools: [{name, status: ok|error, error_code?}], expected_answer?}]}`."""
    value = input_json(spec, "journeys", path)
    journeys = value.get("journeys") if isinstance(value, dict) else None
    limit = min(MAX_JOURNEYS, spec.bounds["max_invocations"])
    if not isinstance(journeys, list) or not journeys or len(journeys) > limit:
        raise RefusedError("journeys_missing", f"journeys file needs 1-{limit} journeys")
    seen: set[Any] = set()
    for journey in journeys:
        tools = journey.get("expected_tools") if isinstance(journey, dict) else None
        if not isinstance(tools, list) or not isinstance(journey.get("input"), str) \
                or not isinstance(journey.get("stream"), bool) or set(journey) - JOURNEY_FIELDS:
            raise RefusedError("journeys_shape", "journey needs id, input, stream (bool) and expected_tools")
        safe_identifier(journey.get("id"), "journey id")
        for tool in tools:
            if not isinstance(tool, dict) or set(tool) - {"name", "status", "error_code"} \
                    or not isinstance(tool.get("name"), str) or tool.get("status") not in JOURNEY_STATUSES \
                    or (tool["status"] == "ok") != (tool.get("error_code") is None) \
                    or not isinstance(tool.get("error_code"), (str, type(None))):
                raise RefusedError("journeys_shape", "expected tool needs name, status ok|error, error_code iff error")
        identity = (journey["id"],), (journey["input"], journey["stream"])
        if seen & set(identity):
            raise RefusedError("journeys_shape", "journey ids and (input, stream) pairs must be unique")
        seen |= set(identity)
    return journeys


# --- datasets (foundry_ops.data, imported lazily) ---------------------------------------------

def data_module() -> Any:
    try:
        return importlib.import_module("foundry_ops.data")
    except ModuleNotFoundError as error:
        raise RefusedError("data_unavailable", "data: dataset needs foundry_ops.data; use data: inline") from error


def load_rows(spec: RunSpec, kind: str, path: Any = None, *, fields: Any = None,
              allowed: frozenset[str] | None = None) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    """Local rows of a pinned file, or `(None, ref)` for a spec dataset ref. No cloud call."""
    refs = spec.inputs.get(kind, ())
    if path is None and not any(ref.path for ref in refs) and any(ref.dataset for ref in refs):
        datasets = [dict(ref.dataset) for ref in refs if ref.dataset]
        if len(datasets) != 1:
            raise RefusedError(f"{kind}_ambiguous", f"exactly one {kind} dataset ref required")
        return None, datasets[0]
    return project_rows(read_rows(read_input(spec, kind, path), kind), fields, allowed, kind), None


def register_rows(spec: RunSpec, project: Any, ledger: EvidenceLedger, kind: str,
                  rows: list[dict[str, Any]] | None, ref: dict[str, Any] | None) -> dict[str, Any] | None:
    """`data: dataset` only: register pinned rows (reused when identical) or read back a spec ref by sha256."""
    if spec.data != "dataset":
        return None
    data = data_module()
    if rows is None:
        readback = data.readback_dataset(project, name=ref["name"], version=ref["version"],
                                         expected_sha256=ref["sha256"])
        return {**ref, **readback}
    return data.register_jsonl_dataset(project, ledger, name=f"{spec.agent}-{kind}", rows=rows)
