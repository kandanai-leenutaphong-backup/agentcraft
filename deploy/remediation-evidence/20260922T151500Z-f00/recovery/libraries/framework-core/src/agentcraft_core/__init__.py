"""Shared contracts carry context, never credentials or permission grants."""

from __future__ import annotations

import contextvars
import math
import re
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Literal


@dataclass(frozen=True, slots=True)
class FailureInfo:
    code: str
    category: str = "failed"
    capability_id: str = ""
    operation: str = ""
    run_id: str = ""
    field: str | None = None
    action: str = "Inspect the configured target and public contract."
    effect: Literal["none", "accepted", "unknown"] = "none"
    retry: Literal["never", "safe_after_correction", "read_back_first", "unspecified"] = "never"

    def to_dict(self) -> dict:
        return asdict(self)


class FrameworkError(RuntimeError):
    def __init__(self, code: str, *, category: str = "invalid", **metadata):
        self.failure = FailureInfo(code, category=category, **metadata)
        super().__init__(f"{category}: {code}")


@dataclass(frozen=True, slots=True)
class CallerContext:
    principal: str
    tenant: str = ""

    def __post_init__(self):
        if not isinstance(self.principal, str) or not self.principal.strip() or len(self.principal) > 256:
            raise FrameworkError("invalid_principal")


class ExecutionBudget:
    """Atomic process-local reservations; possible delivery is never refunded."""

    def __init__(self, limits: Mapping[str, int], *, parent: ExecutionBudget | None = None):
        if not limits or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)
                             or type(value) is not int or value < 0 for name, value in limits.items()):
            raise FrameworkError("invalid_budget")
        if parent and any(name not in parent.limits or value > parent.limits[name] for name, value in limits.items()):
            raise FrameworkError("budget_cannot_widen", category="denied")
        self.limits = MappingProxyType(dict(limits))
        self._parent = parent
        self._lock = parent._lock if parent else threading.RLock()
        self._used = {name: 0 for name in limits}
        self._unknown = {name: 0 for name in limits}

    def reserve(self, name: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 1:
            raise FrameworkError("invalid_reservation")
        chain = []
        current = self
        with self._lock:
            while current is not None:
                if name not in current.limits or current._used[name] + amount > current.limits[name]:
                    raise FrameworkError("budget_exhausted", category="denied", field=name)
                chain.append(current)
                current = current._parent
            for budget in chain:
                budget._used[name] += amount

    def mark_unknown(self, name: str, amount: int = 1) -> None:
        with self._lock:
            chain = []
            current = self
            while current is not None:
                if (type(amount) is not int or amount < 1 or name not in current._used
                        or current._unknown[name] + amount > current._used[name]):
                    raise FrameworkError("unknown_requires_reservation")
                chain.append(current)
                current = current._parent
            for budget in chain:
                budget._unknown[name] += amount

    def snapshot(self) -> dict:
        with self._lock:
            return {"limits": dict(self.limits), "reserved": dict(self._used), "unknown": dict(self._unknown)}


ACTIVE_EXECUTION: contextvars.ContextVar[ExecutionContext | None] = contextvars.ContextVar("agentcraft_execution", default=None)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    caller: CallerContext
    budget: ExecutionBudget
    deadline: float
    run_id: str

    @classmethod
    def create(cls, caller: CallerContext, *, limits: Mapping[str, int], timeout_seconds: float = 30):
        if type(timeout_seconds) not in (float, int) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise FrameworkError("invalid_deadline")
        return cls(caller, ExecutionBudget(limits), time.monotonic() + timeout_seconds, uuid.uuid4().hex)

    def remaining(self) -> float:
        value = self.deadline - time.monotonic()
        if value <= 0:
            raise FrameworkError("deadline_exceeded", category="interrupted", run_id=self.run_id)
        return value

    def child(self, *, limits: Mapping[str, int], timeout_seconds: float | None = None):
        remaining = self.remaining()
        timeout = remaining if timeout_seconds is None else timeout_seconds
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= remaining:
            raise FrameworkError("deadline_cannot_widen", category="denied")
        return ExecutionContext(self.caller, ExecutionBudget(limits, parent=self.budget),
                                min(self.deadline, time.monotonic() + timeout), self.run_id)

    @contextmanager
    def activate(self):
        self.remaining()
        token = ACTIVE_EXECUTION.set(self)
        try:
            yield self
        finally:
            ACTIVE_EXECUTION.reset(token)


def current_execution() -> ExecutionContext | None:
    return ACTIVE_EXECUTION.get()


def reserve(name: str, amount: int = 1) -> None:
    context = current_execution()
    if context is not None:
        context.remaining()
        context.budget.reserve(name, amount)


__all__ = ["CallerContext", "ExecutionBudget", "ExecutionContext", "FailureInfo", "FrameworkError", "current_execution", "reserve"]