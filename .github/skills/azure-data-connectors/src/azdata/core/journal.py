"""In-process operation journal — the seam agent telemetry consumes.

WHY THIS EXISTS
---------------
Two facts about a plane call exist for microseconds and then are gone: the
RU charge the service reported, and whether verification actually ran.
Neither survives into a log line, and reconstructing either afterwards is
guesswork — an operator counting ``upload`` log entries cannot tell a
verified write from an accepted one, and nothing outside the connector
ever sees the charge header.

So the record is made where the facts are, and handed to whoever wants it.

FOUR DELIBERATE CONSTRAINTS
---------------------------
* **Bounded.** A ring buffer with a fixed capacity. An unbounded journal
  in a long-running agent process is a memory leak with a nice name.
* **No I/O.** Never a file, never a socket. A telemetry sink is a
  subscriber's problem; a connector that blocks on a log write during an
  incident makes the incident worse.
* **Off by default.** Disabled costs one boolean test per call and
  allocates nothing — not a record, not a timestamp. Observability that
  taxes callers who did not ask for it gets removed by the first person
  who profiles.
* **Subscribable.** Callbacks receive each record as it lands, so Hill
  Climber can stream without polling. A subscriber that raises is logged
  and dropped from the delivery, never propagated: telemetry does not get
  to fail an operation.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Enough to cover an agent turn's worth of calls without growing.
DEFAULT_CAPACITY = 256


@dataclass(frozen=True)
class JournalRecord:
    """One plane call, as it happened.

    Args:
        operation: The verb — ``"upload"``, ``"ensure"``, ``"verify"``.
        service: ``"search"``, ``"cosmos"``, ``"gremlin"``, ``"kusto"``.
        target: Index, container, graph or table.
        outcome: ``"ok"``, ``"error"``, ``"degraded"``, ``"refused"``.
        elapsed_ms: Wall time of the call.
        request_charge: RU charged, or None where the service reports none.
            None is not zero, and the two must not be collapsed.
        verified: Whether the state was read back, or None where the
            operation has no verification step.
    """

    operation: str
    service: str
    target: str | None
    outcome: str
    elapsed_ms: float
    request_charge: float | None = None
    verified: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperationJournal:
    """A bounded, subscribable ring buffer of :class:`JournalRecord`.

    Disabled until :meth:`enable` is called. Not thread-safe by design:
    ``deque.append`` under a ``maxlen`` is atomic enough for a counter, and
    a lock on every plane call to protect telemetry is the wrong trade.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._records: deque[JournalRecord] = deque(maxlen=max(1, int(capacity)))
        self._subscribers: list[Callable[[JournalRecord], None]] = []
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def capacity(self) -> int:
        return self._records.maxlen or 0

    def enable(self) -> None:
        """Start recording. Explicit, because the default is off."""
        self._enabled = True

    def disable(self) -> None:
        """Stop recording. Existing records are kept; use :meth:`clear`."""
        self._enabled = False

    def record(
        self,
        *,
        operation: str,
        service: str,
        target: str | None,
        outcome: str,
        elapsed_ms: float,
        request_charge: float | None = None,
        verified: bool | None = None,
    ) -> JournalRecord | None:
        """Append one record, or return None when disabled.

        The disabled path returns before constructing anything, so a
        disabled journal costs a boolean test and allocates nothing.
        """
        if not self._enabled:
            return None
        record = JournalRecord(
            operation=operation,
            service=service,
            target=target,
            outcome=outcome,
            elapsed_ms=elapsed_ms,
            request_charge=request_charge,
            verified=verified,
        )
        self._records.append(record)
        for subscriber in tuple(self._subscribers):
            try:
                subscriber(record)
            except Exception as exc:  # noqa: BLE001 - telemetry never fails a call
                logger.warning(
                    "journal.subscriber_failed: %s: %s", type(exc).__name__, exc
                )
        return record

    def subscribe(
        self, callback: Callable[[JournalRecord], None]
    ) -> Callable[[], None]:
        """Register ``callback``; returns a callable that unsubscribes it."""
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return _unsubscribe

    def records(self) -> tuple[JournalRecord, ...]:
        """Everything still in the buffer, oldest first."""
        return tuple(self._records)

    def clear(self) -> None:
        """Drop every record. Subscribers and the enabled flag survive."""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


#: The process-wide journal. Off until something enables it.
journal = OperationJournal()


__all__ = [
    "DEFAULT_CAPACITY",
    "JournalRecord",
    "OperationJournal",
    "journal",
]
