"""Attempt accounting for caller-owned groups of canonical operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from copy import deepcopy
from typing import Any

from .contracts import OperationResult


class OperationMetrics:
    """Async task-safe counters, independent of connector policy and execution budgets.

    Reset starts a new generation. In-flight calls finish in their original
    generation. A returned nonnegative integer attempt count (including zero)
    is known; an exception, cancellation or missing/invalid count is unknown.
    """

    def __init__(self, *, operations: Iterable[str] = ()) -> None:
        self._operations = tuple(operations)
        self.reset()

    def reset(self) -> None:
        self._metrics: dict[str, Any] = {
            "submitted": 0, "completed": 0, "known_attempts": 0,
            "unknown_attempt_operations": 0,
            "operations": dict.fromkeys(self._operations, 0), "sources": {},
        }

    def snapshot(self) -> dict[str, Any]:
        """Return a detached snapshot; no request content or credentials are retained."""
        return deepcopy(self._metrics)

    async def run(self, operation: str, call: Callable[[], Awaitable[OperationResult]],
                  *, source_id: str | None = None) -> OperationResult:
        metrics = self._metrics
        source = (metrics["sources"].setdefault(source_id, {
            "known_attempts": 0, "unknown_attempt_operations": 0,
        }) if source_id is not None else None)
        metrics["submitted"] += 1
        metrics["operations"][operation] = metrics["operations"].get(operation, 0) + 1
        result = None
        try:
            result = await call()
            return result
        finally:
            metrics["completed"] += 1
            attempts = result.metrics.get("attempts") if result is not None else None
            name, count = (("known_attempts", attempts) if type(attempts) is int and attempts >= 0
                           else ("unknown_attempt_operations", 1))
            metrics[name] += count
            if source is not None:
                source[name] += count


__all__ = ["OperationMetrics"]