"""The decorator — one wrapper that makes a function a purpose-built tool.

WHY THIS EXISTS
---------------
Everything the shape requires — validate, refuse legibly, suppress the
repeat, wrap the result, report failure safely, record what happened — is identical
for every tool and wrong in a different way in each hand-written copy. The
copies are also where the shape decays: the third tool skips the scope
block, the fifth raises instead of refusing, and the weight meter then
measures a population that no longer shares a contract.

``@purpose_built(spec)`` applies all of it, so the tool body is only the
part that is genuinely specific: the query, and the rows it produces.

WHAT THE WRAPPER GUARANTEES
---------------------------
1. Arguments are validated against the spec. A failure returns a refusal
   naming the parameter and the accepted form; the body never runs.
2. A repeat call within the turn returns the duplicate result without
   touching the backend.
3. The body may return rows, a ``(columns, rows)`` pair, a dict or an
    already-built JSON string. ``None`` is an explicit missing envelope,
    not a successful empty table. Anything else is wrapped.
4. Body ``Exception`` failures become fixed safe metadata, including body
    programming errors under this contract. Cancellation and other control
    exceptions propagate; validation and result-shaping errors also propagate.
5. Every delivered outcome is recorded for the weight meter.

WHAT IT DOES NOT DO
-------------------
It does not register the tool with any agent SDK. Apply the SDK's own
decorator outside this one; the two compose, and keeping them separate is
what keeps this box free of an SDK dependency.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import time
from concurrent.futures import CancelledError as FutureCancelledError
from typing import Any, Callable, Sequence

from . import _envelope as env
from ._ledger import CallRecord, emit, record_call_once
from ._spec import ToolSpec
from ._validators import Rejection

logger = logging.getLogger(__name__)


def _shape_result(value: Any, spec: ToolSpec, arguments: dict) -> tuple[str, str]:
    """Coerce a tool body's return into (payload, result_class).

    Accepting several return types is a deliberate convenience: the common
    case is "here are my rows", and forcing every body to build the full
    envelope is how the scope block starts getting omitted.
    """
    if isinstance(value, str):
        # The body built its own envelope. Classify, do not rewrite.
        return value, env.classify(value)

    if isinstance(value, tuple) and len(value) == 2:
        columns, rows = value
        payload = env.table(columns, rows, scope=spec.scope_of(arguments))
        return payload, env.classify(payload)

    if isinstance(value, list):
        # Rows only: derive column order from the first row, preserving
        # insertion order. An empty list yields no columns, which is why a
        # tool with a fixed schema should return the pair form instead.
        columns = list(value[0].keys()) if value and isinstance(value[0], dict) else []
        payload = env.table(columns, value, scope=spec.scope_of(arguments))
        return payload, env.classify(payload)

    if isinstance(value, dict):
        payload = json.dumps(value, default=str)
        return payload, env.classify(payload)

    if value is None:
        return json.dumps({"missing": True}), env.MISSING

    payload = json.dumps({"value": value}, default=str)
    return payload, env.PRODUCTIVE


def _bind(fn: Callable, args: tuple, kwargs: dict) -> dict:
    """Normalise positional and keyword arguments into one dict.

    Tools are called by name by an agent SDK and positionally by tests and
    examples; validation must see the same dict either way.
    """
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        return dict(bound.arguments)
    except TypeError:
        return dict(kwargs)


def purpose_built(spec: ToolSpec) -> Callable:
    """Wrap a function as a purpose-built tool returning a JSON string.

    Works on ``async def`` and plain ``def``. The spec is attached to the
    wrapper as ``__toolspec__`` so the catalogue and the linter can find
    every tool by introspection rather than by a hand-maintained list.
    """

    def decorate(fn: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(fn)

        def _pre(
            args: tuple, kwargs: dict
        ) -> tuple[dict | None, str | None, str, str]:
            """Validate and dedupe. Returns (arguments, early_payload, class, detail)."""
            arguments = _bind(fn, args, kwargs)

            validated = spec.validate(arguments)
            if isinstance(validated, Rejection):
                payload = env.refusal(
                    validated.parameter, validated.problem, validated.accepted
                )
                # The parameter name is the detail: it is what the meter
                # groups refusals by to name the failing affordance.
                return None, payload, env.REFUSED, validated.parameter

            if spec.dedupe_on and record_call_once(
                spec.name, spec.dedupe_key(validated), max_calls=spec.max_calls
            ):
                payload = env.duplicate(spec.name, spec.scope_of(validated))
                return None, payload, env.DUPLICATE, ""

            return validated, None, "", ""

        def _finish(
            started: float, payload: str, result_class: str, detail: str = ""
        ) -> str:
            emit(
                CallRecord(
                    tool=spec.name,
                    result_class=result_class,
                    ms=round((time.monotonic() - started) * 1000, 2),
                    detail=detail,
                )
            )
            return payload

        def _failed(started: float) -> str:
            logger.warning("tool %s failed: tool_failed", spec.name)
            return _finish(
                started, env.failure(""), env.ERROR, detail="tool_failed"
            )

        if is_async:

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> str:
                started = time.monotonic()
                arguments, early, early_class, early_detail = _pre(args, kwargs)
                if early is not None:
                    return _finish(started, early, early_class, early_detail)
                try:
                    raw = await fn(**arguments)
                except FutureCancelledError:
                    raise
                except Exception:
                    return _failed(started)
                payload, result_class = _shape_result(raw, spec, arguments)
                return _finish(started, payload, result_class)

            wrapper: Callable = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> str:
                started = time.monotonic()
                arguments, early, early_class, early_detail = _pre(args, kwargs)
                if early is not None:
                    return _finish(started, early, early_class, early_detail)
                try:
                    raw = fn(**arguments)
                except FutureCancelledError:
                    raise
                except Exception:
                    return _failed(started)
                payload, result_class = _shape_result(raw, spec, arguments)
                return _finish(started, payload, result_class)

            wrapper = sync_wrapper

        wrapper.__toolspec__ = spec  # type: ignore[attr-defined]
        # The generated description replaces whatever docstring the body had,
        # so the text the caller reads is the spec and cannot drift from it.
        wrapper.__doc__ = spec.description()
        return wrapper

    return decorate


def specs_in(*namespaces: Any) -> list[ToolSpec]:
    """Collect every ToolSpec attached to a callable in the given namespaces.

    Accepts modules or dicts. Used by the catalogue and the linter so a
    tool is discovered by being decorated, never by being added to a list
    someone has to remember to update.
    """
    found: dict[str, ToolSpec] = {}
    for namespace in namespaces:
        members = namespace if isinstance(namespace, dict) else vars(namespace)
        for value in members.values():
            spec = getattr(value, "__toolspec__", None)
            if isinstance(spec, ToolSpec):
                found[spec.name] = spec
    return sorted(found.values(), key=lambda s: s.name)


def tool_names(*namespaces: Any) -> Sequence[str]:
    """Every decorated tool name in the given namespaces."""
    return [spec.name for spec in specs_in(*namespaces)]


__all__ = ["purpose_built", "specs_in", "tool_names"]
