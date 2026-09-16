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
from contextlib import aclosing
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
            "processing must return an object of observations", code="invalid_observations",
        )
    try:
        return dict(value)
    except Exception as exc:
        raise _fail(rule, "process", exc) from None


def _envelope(rule: Rule, value: Any) -> Any:
    if value is None:
        raise RuleExecutionError(
            str(rule["rule_set_id"]), str(rule["id"]), "execute",
            "query returned no envelope; an execution failure is not an empty detection",
            code="missing_envelope",
        )
    return value


def _fail(rule: Rule, stage: str, exc: Exception) -> RuleExecutionError:
    timed_out = isinstance(exc, TimeoutError)
    return RuleExecutionError(
        str(rule["rule_set_id"]), str(rule["id"]), stage,
        "callback timed out" if timed_out else "callback failed",
        code="callback_timeout" if timed_out else "callback_failed",
    )


def _sync_value(rule: Rule, stage: str, value: Any) -> Any:
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise RuleExecutionError(
            str(rule["rule_set_id"]), str(rule["id"]), stage,
            "callback returned an awaitable; use the async battery", code="async_callback_in_sync",
        )
    return value


def _concurrency(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigurationError("max_concurrency must be a positive integer")
    return value


async def _invoke(callback: Callable[..., Any], *args: Any) -> Any:
    if inspect.iscoroutinefunction(callback) or inspect.iscoroutinefunction(getattr(callback, "__call__", None)):
        return await callback(*args)
    task = asyncio.create_task(asyncio.to_thread(callback, *args))
    try:
        value = await asyncio.shield(task)
    except asyncio.CancelledError:
        settled = await asyncio.gather(task, return_exceptions=True)
        if inspect.iscoroutine(settled[0]):
            settled[0].close()
        raise
    if inspect.isawaitable(value):
        return await value
    return value


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
        if inspect.iscoroutine(value):
            value.close()
        raise ConfigurationError("summarize returned an awaitable; use the async battery")
    if not isinstance(value, Mapping):
        raise ConfigurationError("summarize must return an object")
    return dict(value)


async def _summary_async(
    summarize: Callable[..., Any] | None,
    configuration: Mapping[str, Any],
    rules: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    window: Window,
) -> dict[str, Any]:
    if summarize is None:
        return _default_summary(configuration, rules)
    value = await _invoke(_callable(summarize, "summarize"), entries, window)
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
            envelope = execute(rule, window)
        except Exception as exc:
            raise _fail(rule, "execute", exc) from None
        envelope = _envelope(rule, _sync_value(rule, "execute", envelope))
        try:
            processed = process(rule, envelope, window)
        except Exception as exc:
            raise _fail(rule, "process", exc) from None
        processed = _observations(rule, _sync_value(rule, "process", processed))
        entries.append(_entry(rule, envelope, processed, round((time.monotonic() - started) * 1000)))
    return _result(normalized, bounds, entries, _summary(summarize, normalized, rules, entries, window))


async def _run_rule(rule: Rule, window: Window, execute: Callable[..., Any],
                    process: Callable[..., Any]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        envelope = await _invoke(execute, rule, window)
    except Exception as exc:
        raise _fail(rule, "execute", exc) from None
    envelope = _envelope(rule, envelope)
    try:
        processed = await _invoke(process, rule, envelope, window)
    except Exception as exc:
        raise _fail(rule, "process", exc) from None
    processed = _observations(rule, processed)
    return _entry(rule, envelope, processed, round((time.monotonic() - started) * 1000))


def _ordered(rules: list[dict[str, Any]], entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {entry["rule_id"]: entry for entry in entries}
    return [by_id[rule["id"]] for rule in rules if rule["id"] in by_id]


async def run_battery_async(
    configuration: Any, window: Window, execute: Callable[..., Any], process: Callable[..., Any],
    *, summarize: Callable[..., Any] | None = None, max_concurrency: int = 8,
) -> dict[str, Any]:
    """Run a bounded number of rules concurrently, returning declaration-ordered results."""
    async with aclosing(stream_battery(
        configuration, window, execute, process, summarize=summarize, max_concurrency=max_concurrency,
    )) as stream:
        async for event in stream:
            if event["event"] == BATTERY_COMPLETED:
                return event["data"]
    raise RuntimeError("battery did not produce a final result")


async def stream_battery(
    configuration: Any, window: Window, execute: Callable[..., Any], process: Callable[..., Any],
    *, summarize: Callable[..., Any] | None = None, max_concurrency: int = 8,
) -> AsyncIterator[dict[str, Any]]:
    """Yield ``rule_started`` for every selected rule, ``rule_completed`` as each finishes,
    then one ``battery_completed`` carrying the same result ``run_battery_async`` returns.

    A failing rule raises out of the iterator: the stream never ends in a
    ``battery_completed`` that hides it.
    """
    normalized, bounds, rules, execute, process = _prepare(configuration, window, execute, process)
    limit = _concurrency(max_concurrency)
    if summarize is not None:
        _callable(summarize, "summarize")
    tasks: set[asyncio.Task[dict[str, Any]]] = set()
    try:
        for index, rule in enumerate(rules):
            yield {"event": RULE_STARTED,
                   "data": {"rule_set_id": rule["rule_set_id"], "rule_id": rule["id"], "name": rule["name"]}}
            if index < limit:
                tasks.add(asyncio.create_task(_run_rule(rule, window, execute, process)))
        remaining = iter(rules[limit:])
        entries: list[dict[str, Any]] = []
        while tasks:
            completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                entry = task.result()
                tasks.remove(task)
                entries.append(entry)
                yield {"event": RULE_COMPLETED, "data": entry}
                rule = next(remaining, None)
                if rule is not None:
                    tasks.add(asyncio.create_task(_run_rule(rule, window, execute, process)))
        ordered = _ordered(rules, entries)
        yield {"event": BATTERY_COMPLETED,
               "data": _result(normalized, bounds, ordered,
                               await _summary_async(summarize, normalized, rules, ordered, window))}
    finally:
        for pending in tasks:
            if not pending.done():
                pending.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


__all__ = [
    "BATTERY_COMPLETED",
    "RULE_COMPLETED",
    "RULE_STARTED",
    "run_battery",
    "run_battery_async",
    "stream_battery",
]
