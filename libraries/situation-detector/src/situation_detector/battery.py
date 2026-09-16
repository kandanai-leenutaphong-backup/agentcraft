"""Ordered execution of a configured query-test battery, sync, async and streamed.

The host injects both stages. ``execute(rule, window)`` returns an opaque query
envelope; ``process(rule, envelope, window)`` returns observations. The component
times, orders and identifies; it never interprets a query, never processes rows,
and never imports or evaluates anything a configuration names.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Iterable, Mapping

from .config import configuration_digest, normalize_config, normalize_window, selected_rules
from .errors import ConfigurationError, RuleExecutionError

Rule = Mapping[str, Any]
Window = Mapping[str, Any]

RULE_STARTED = "rule_started"
RULE_COMPLETED = "rule_completed"
BATTERY_COMPLETED = "battery_completed"


def _callable(value: Any, name: str) -> Callable[..., Any]:
    if not callable(value):
        raise ConfigurationError(f"{name} must be callable")
    return value


def _observations(rule: Rule, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuleExecutionError(
            str(rule["rule_set_id"]), str(rule["id"]), "process",
            f"processing returned {type(value).__name__}, expected an object of observations",
        )
    return dict(value)


def _envelope(rule: Rule, value: Any) -> Any:
    if value is None:
        raise RuleExecutionError(
            str(rule["rule_set_id"]), str(rule["id"]), "execute",
            "query returned no envelope; an execution failure is not an empty detection",
        )
    return value


def _fail(rule: Rule, stage: str, exc: BaseException) -> RuleExecutionError:
    if isinstance(exc, RuleExecutionError):
        return exc
    return RuleExecutionError(str(rule["rule_set_id"]), str(rule["id"]), stage, f"{type(exc).__name__}: {exc}")


def _entry(rule: Rule, envelope: Any, processed: dict[str, Any], elapsed_ms: int) -> dict[str, Any]:
    return {
        "rule_set_id": rule["rule_set_id"],
        "rule_id": rule["id"],
        "name": rule["name"],
        "status": "completed",
        "query_result": envelope,
        "processed": processed,
        "elapsed_ms": elapsed_ms,
    }


def _default_summary(configuration: Mapping[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tests_run": len(rules),
        "rule_sets_run": len({rule["rule_set_id"] for rule in rules}),
        "configuration_version": configuration["version"],
    }


def _summary(
    summarize: Callable[..., Any] | None,
    configuration: Mapping[str, Any],
    rules: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    window: Window,
) -> dict[str, Any]:
    if summarize is None:
        return _default_summary(configuration, rules)
    value = _callable(summarize, "summarize")(entries, window)
    if inspect.isawaitable(value):
        raise ConfigurationError("summarize returned an awaitable; use the async battery")
    if not isinstance(value, Mapping):
        raise ConfigurationError("summarize must return an object")
    return dict(value)


def _result(
    configuration: Mapping[str, Any], bounds: dict[str, datetime],
    entries: list[dict[str, Any]], summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "configuration_digest": configuration_digest(configuration),
        "window": {"start": bounds["start"].isoformat(), "end": bounds["end"].isoformat()},
        "rules": entries,
        "summary": summary,
    }


def _prepare(configuration: Any, window: Window, execute: Any, process: Any):
    normalized = normalize_config(configuration)
    bounds = normalize_window(window, normalized["max_window_seconds"])
    return normalized, bounds, selected_rules(normalized), _callable(execute, "execute"), _callable(process, "process")


def run_battery(
    configuration: Any, window: Window, execute: Callable[..., Any], process: Callable[..., Any],
    *, summarize: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run every selected rule in declaration order and return the ordered result."""
    normalized, bounds, rules, execute, process = _prepare(configuration, window, execute, process)
    entries: list[dict[str, Any]] = []
    for rule in rules:
        started = time.monotonic()
        try:
            envelope = _envelope(rule, execute(rule, window))
        except BaseException as exc:
            raise _fail(rule, "execute", exc) from exc
        if inspect.isawaitable(envelope):
            raise RuleExecutionError(rule["rule_set_id"], rule["id"], "execute",
                                     "query returned an awaitable; use run_battery_async")
        try:
            processed = _observations(rule, process(rule, envelope, window))
        except BaseException as exc:
            raise _fail(rule, "process", exc) from exc
        entries.append(_entry(rule, envelope, processed, round((time.monotonic() - started) * 1000)))
    return _result(normalized, bounds, entries, _summary(summarize, normalized, rules, entries, window))


async def _run_rule(rule: Rule, window: Window, execute: Callable[..., Any],
                    process: Callable[..., Any]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        envelope = execute(rule, window)
        if inspect.isawaitable(envelope):
            envelope = await envelope
        envelope = _envelope(rule, envelope)
    except BaseException as exc:
        raise _fail(rule, "execute", exc) from exc
    try:
        processed = process(rule, envelope, window)
        if inspect.isawaitable(processed):
            processed = await processed
        processed = _observations(rule, processed)
    except BaseException as exc:
        raise _fail(rule, "process", exc) from exc
    return _entry(rule, envelope, processed, round((time.monotonic() - started) * 1000))


def _ordered(rules: list[dict[str, Any]], entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {entry["rule_id"]: entry for entry in entries}
    return [by_id[rule["id"]] for rule in rules if rule["id"] in by_id]


async def run_battery_async(
    configuration: Any, window: Window, execute: Callable[..., Any], process: Callable[..., Any],
    *, summarize: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run every selected rule concurrently; results stay in declaration order."""
    normalized, bounds, rules, execute, process = _prepare(configuration, window, execute, process)
    completed = await asyncio.gather(*(_run_rule(rule, window, execute, process) for rule in rules))
    entries = _ordered(rules, completed)
    return _result(normalized, bounds, entries, _summary(summarize, normalized, rules, entries, window))


async def stream_battery(
    configuration: Any, window: Window, execute: Callable[..., Any], process: Callable[..., Any],
    *, summarize: Callable[..., Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield ``rule_started`` for every selected rule, ``rule_completed`` as each finishes,
    then one ``battery_completed`` carrying the same result ``run_battery_async`` returns.

    A failing rule raises out of the iterator: the stream never ends in a
    ``battery_completed`` that hides it.
    """
    normalized, bounds, rules, execute, process = _prepare(configuration, window, execute, process)
    tasks: dict[asyncio.Task[dict[str, Any]], dict[str, Any]] = {}
    for rule in rules:
        yield {"event": RULE_STARTED,
               "data": {"rule_set_id": rule["rule_set_id"], "rule_id": rule["id"], "name": rule["name"]}}
        tasks[asyncio.create_task(_run_rule(rule, window, execute, process))] = rule
    entries: list[dict[str, Any]] = []
    try:
        for task in asyncio.as_completed(list(tasks)):
            entry = await task
            entries.append(entry)
            yield {"event": RULE_COMPLETED, "data": entry}
    except BaseException:
        for pending in tasks:
            pending.cancel()
        raise
    ordered = _ordered(rules, entries)
    yield {"event": BATTERY_COMPLETED,
           "data": _result(normalized, bounds, ordered,
                           _summary(summarize, normalized, rules, ordered, window))}


__all__ = [
    "BATTERY_COMPLETED",
    "RULE_COMPLETED",
    "RULE_STARTED",
    "run_battery",
    "run_battery_async",
    "stream_battery",
]
