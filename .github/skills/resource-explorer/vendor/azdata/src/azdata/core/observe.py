"""The observe plane — key stats for a target, and never a wholesale failure.

WHY THIS EXISTS
---------------
A caller operating a service asks two questions after every operation:
*did it work* and *how is this doing*. The write and deploy planes answer
the first. Nothing answered the second, so every consumer wrote its own
counter-gathering, and every one of them made the same two mistakes.

**Failing the whole call because one counter was unavailable.** Stats come
from three different places — the data plane, the management plane and
Azure Monitor — behind three different role assignments. A caller with no
``Monitoring Reader`` grant is not a caller who deserves no document
count.

**Omitting a counter silently.** The opposite mistake, and the worse one:
returning ``{"document_count": 40}`` when the storage figure could not be
read looks exactly like a service with no storage figure. An operator
reads an absence as a zero.

The contract is those two sentences:

* A stats call never fails wholesale because one counter was unavailable.
* A stats call never omits a counter silently.

:func:`collector` is how both are kept. Every probe declares the stat
names it is responsible for. A probe that raises puts *all* of its names
into ``partial`` with a sanitised reason; a probe that answers without a
name it declared puts that one name into ``partial``. Nothing else can
happen to a declared name.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Nothing here knows what a stat means. Service modules declare names and
supply callables; this module routes results and shapes an envelope.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from azdata.core.envelope import sanitize_detail

#: One probe: the stat names it owns, and the callable that produces them.
#: The callable may be sync or async. With one declared name it returns the
#: value; with several it returns a mapping of name to value.
Probe = tuple[Sequence[str], Callable[[], Any]]


class StatUnavailable(RuntimeError):
    """A probe cannot produce its stat, and will not invent one.

    Raised where a value is genuinely absent rather than zero: a response
    header the service did not send, a management client nobody wired, a
    query that has not run yet. :func:`collector` turns it into a
    ``partial`` entry naming the stat, which is the honest answer. The
    dishonest one is ``0``.
    """


class StatSource(str, Enum):
    """Where the bulk of an envelope's stats came from.

    A string enum rather than a bare string so a caller cannot misspell one
    into an envelope that then reads as a fourth, non-existent source. It
    names the *principal* collector of the envelope: a data-plane envelope
    may still carry management-plane and Monitor stats, and lists the ones
    it could not reach in ``partial``.
    """

    DATA_PLANE = "data-plane"
    MANAGEMENT_PLANE = "management-plane"
    MONITOR = "monitor"


@runtime_checkable
class StatsProvider(Protocol):
    """What every ``<service>/observe.py`` implements."""

    service: str

    async def stats(self, target: str | None = None) -> str:
        """Return a ``stats`` envelope for ``target``."""
        ...


def utc_now() -> str:
    """Current UTC instant, second resolution, ISO-8601 with a ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stats_envelope(
    *,
    service: str,
    target: str | None,
    source: StatSource | str,
    stats: Mapping[str, Any],
    partial: Sequence[Mapping[str, str]] = (),
    collected_at: str | None = None,
) -> str:
    """``{"ok": true, "operation": "stats", ...}`` as a JSON string.

    Key order is insertion order and is part of the contract: ``ok``,
    ``operation``, ``service``, ``target``, ``collected_at``, ``source``,
    ``stats``, ``partial``.

    The envelope is ``ok`` even when ``partial`` is non-empty. A partial
    collection is an answer; the caller is told exactly which counters are
    missing and why, which is strictly more than an error envelope
    carrying one exception could say.
    """
    return json.dumps(
        {
            "ok": True,
            "operation": "stats",
            "service": service,
            "target": target,
            "collected_at": collected_at or utc_now(),
            "source": StatSource(source).value,
            "stats": dict(stats),
            "partial": [dict(entry) for entry in partial],
        },
        default=str,
    )


async def collector(probes: Iterable[Probe]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Run ``probes`` and route every declared name to ``stats`` or ``partial``.

    Args:
        probes: ``(names, call)`` pairs. ``call`` may be sync or async. One
            declared name means the return value *is* the stat, including
            when it is a mapping — a histogram is a value, not an
            expansion. Several declared names mean the return value is a
            mapping keyed by those names.

    Returns:
        ``(stats, partial)``. ``partial`` entries are
        ``{"stat": <name>, "detail": <sanitised>}``, in declaration order.

    A raising probe costs its own names and nothing else. Keys a
    multi-name probe returns that it did not declare are kept: an extra
    counter the service grew is more useful reported than dropped.
    """
    stats: dict[str, Any] = {}
    partial: list[dict[str, str]] = []

    for names, call in probes:
        declared = tuple(names)
        try:
            result = call()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 - one dead counter is not a dead call
            detail = sanitize_detail(f"{type(exc).__name__}: {exc}")
            partial.extend({"stat": name, "detail": detail} for name in declared)
            continue

        if len(declared) == 1:
            stats[declared[0]] = result
            continue

        if not isinstance(result, Mapping):
            detail = sanitize_detail(
                f"probe returned {type(result).__name__}, not a mapping of "
                f"{len(declared)} stat(s)"
            )
            partial.extend({"stat": name, "detail": detail} for name in declared)
            continue

        for name in declared:
            if name in result:
                stats[name] = result[name]
            else:
                partial.append(
                    {"stat": name, "detail": "not reported by the service"}
                )
        for name, value in result.items():
            if name not in declared:
                stats[name] = value

    return stats, partial


__all__ = [
    "Probe",
    "StatSource",
    "StatUnavailable",
    "StatsProvider",
    "collector",
    "stats_envelope",
    "utc_now",
]
