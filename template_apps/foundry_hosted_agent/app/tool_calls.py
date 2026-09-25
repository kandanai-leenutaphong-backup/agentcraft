"""Generic tool-call instrumentation: every configured tool runs through one per-turn wrapper."""

import asyncio
import contextvars
import copy
import functools
import inspect
import json
import re
import time
from datetime import datetime, timezone

ERROR_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
MAX_CALL_ID_CHARACTERS = 128
MAX_ERROR_MESSAGE_CHARACTERS = 256
METADATA_PREFIX = "tool_call."
METADATA_FIELDS = ("call_id", "name", "status", "error_code", "started_at", "ended_at", "duration_ms")
_CALL = contextvars.ContextVar("tool_call", default=None)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def classify_error(error):
    """Tool-declared `error_code` attribute when well-formed, else the exception class name."""
    declared = getattr(error, "error_code", None)
    if isinstance(declared, str) and ERROR_CODE.fullmatch(declared):
        return declared, str(error)[:MAX_ERROR_MESSAGE_CHARACTERS]
    # Undeclared exception text may carry internals; neither the model nor the caller sees it.
    return type(error).__name__[:64], "tool failed"


def metadata_entry(record):
    """Response-metadata value for the fields native function_call items cannot carry (<= 512 chars)."""
    return json.dumps({key: record[key] for key in METADATA_FIELDS}, sort_keys=True, separators=(",", ":"))


class ToolCallRecorder:
    """Per turn: instrumented tools plus the llm_interface authorizer that binds each execution to its call id."""

    def __init__(self, functions):
        self.records = {}
        self._names = frozenset(function.__name__ for function in functions)
        self.tools = tuple(self._instrument(function) for function in functions)

    def authorize(self, call):
        """`authorize_tool` hook; llm_interface calls it in the executing task immediately before the tool."""
        if (call.name not in self._names or not isinstance(call.call_id, str) or not call.call_id
                or len(call.call_id) > MAX_CALL_ID_CHARACTERS or call.call_id in self.records):
            return False
        _CALL.set(call)
        return True

    def _instrument(self, function):
        @functools.wraps(function)
        async def instrumented(**arguments):
            call = _CALL.get()
            if call is None or call.name != function.__name__:
                raise LookupError("tool call identity unavailable")
            _CALL.set(None)
            record = {"call_id": call.call_id, "name": call.name, "arguments": copy.deepcopy(call.arguments),
                      "result": None, "status": "ok", "error_code": None, "started_at": _now()}
            self.records[call.call_id] = record
            started = time.perf_counter()
            try:
                if inspect.iscoroutinefunction(function):
                    result = await function(**arguments)
                else:
                    result = await asyncio.to_thread(function, **arguments)
            except Exception as error:
                code, message = classify_error(error)
                result = {"error": {"code": code, "message": message}}
                record.update(status="error", error_code=code)
            record.update(result=copy.deepcopy(result), ended_at=_now(),
                          duration_ms=round((time.perf_counter() - started) * 1000, 3))
            return result

        return instrumented
