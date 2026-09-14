"""The verify plane — what actually changed, and did anything change that
nobody asked for.

WHY THIS EXISTS
---------------
The write plane already verifies a write by reading back the keys it was
handed. That answers *did my item land*. It does not answer the question a
caller operating a system actually has.

A create that succeeds while a concurrent process deletes forty documents
returns ``{"ok": true, "count": 1, "verified": true}``. Every word of that
envelope is true. It is also useless: forty documents are gone and nothing
in the result says so.

This module snapshots the addressable key space before and after an
operation and diffs it. The diff is the evidence. Three consequences run
through everything below.

**A mismatch is a failure.** Not a warning, not ``ok`` with
``matched: false``. A verification that does not match returns an error
envelope — carrying the whole observation, so the caller can see exactly
what happened without a second call.

**The digest is over the sorted key set.** Enumeration order is a service
implementation detail that changes between calls, between partitions and
between SDK versions. A digest sensitive to it would report churn that did
not happen, and a digest that reports false churn gets ignored, which is
worse than not having one.

**A refusal is provable.** ``Effect.unchanged()`` against a write denied by
policy must produce a byte-identical digest. That is the negative every
positive result here is worthless without: a verifier that cannot fail
cannot pass.

BOUNDS
------
Key enumeration is capped by ``AZDATA_VERIFY_MAX_KEYS`` (default 5000).
Above the cap the snapshot carries a deterministic sample — the first
``cap`` keys in sorted order, so two snapshots of an unchanged store sample
identically — the digest covers only that sample, and ``sampled: true``
appears in the snapshot. A verification that silently degraded to a count
comparison would be the failure this module exists to prevent, committed by
the module itself.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol, runtime_checkable

from azdata.core.config import DEFAULT_VERIFY_MAX_KEYS
from azdata.core.envelope import sanitize_detail
from azdata.core.journal import OperationJournal, journal
from azdata.core.observe import utc_now

logger = logging.getLogger(__name__)


@runtime_checkable
class KeySource(Protocol):
    """What every ``<service>/verify.py`` implements.

    The service-specific answer to *what is an addressable key here, and
    how do I enumerate it*. Everything else in this module is blind to the
    service.
    """

    service: str

    async def enumerate_keys(self, target: str | None = None) -> Mapping[str, str]:
        """Return ``{key: content_digest}`` for every addressable item.

        The content digest is what makes ``changed`` distinguishable from
        ``added`` plus ``removed``. Where a service offers a cheap version
        marker — an etag — that is the digest; where it does not, hash the
        content.
        """
        ...


def key_digest(keys: Any) -> str:
    """sha256 over the sorted, deduplicated key set.

    Order-independent by construction: two enumerations of the same store
    produce the same digest whatever order the service returned them in.
    Keys are stringified first, so a service returning ints and a service
    returning strings for the same ids do not disagree.
    """
    ordered = sorted({str(key) for key in keys})
    return hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StateSnapshot:
    """The addressable state of one target at one instant."""

    service: str
    target: str
    taken_at: str
    count: int
    keys: tuple[str, ...]
    digest: str
    stats: Mapping[str, Any] = field(default_factory=dict)
    sampled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "target": self.target,
            "taken_at": self.taken_at,
            "count": self.count,
            "keys": list(self.keys),
            "digest": self.digest,
            "stats": dict(self.stats),
            "sampled": self.sampled,
        }


@dataclass(frozen=True)
class StateDelta:
    """What moved between two snapshots."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: int
    count_before: int
    count_after: int

    @classmethod
    def between(
        cls,
        before: StateSnapshot,
        after: StateSnapshot,
        before_contents: Mapping[str, str] | None = None,
        after_contents: Mapping[str, str] | None = None,
    ) -> "StateDelta":
        """Diff two snapshots, using content digests for ``changed``.

        Without content digests ``changed`` is empty rather than guessed: a
        key present in both snapshots whose content nobody looked at has
        not been shown to have changed.
        """
        before_keys = set(before.keys)
        after_keys = set(after.keys)
        common = before_keys & after_keys

        changed: tuple[str, ...] = ()
        if before_contents is not None and after_contents is not None:
            changed = tuple(
                sorted(
                    key
                    for key in common
                    if key in before_contents
                    and key in after_contents
                    and before_contents[key] != after_contents[key]
                )
            )

        return cls(
            added=tuple(sorted(after_keys - before_keys)),
            removed=tuple(sorted(before_keys - after_keys)),
            changed=changed,
            unchanged=len(common) - len(changed),
            count_before=before.count,
            count_after=after.count,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
            "unchanged": self.unchanged,
            "count_before": self.count_before,
            "count_after": self.count_after,
        }


@dataclass(frozen=True)
class Effect:
    """What the caller intended. Matched strictly, on purpose.

    ``Effect.added(["a"])`` against an operation that added ``"a"`` and
    ``"b"`` does **not** match. A verification that passes when something
    unrequested also changed is worth nothing at all — it is the concurrent
    delete in the module docstring, waved through.

    Use :meth:`any` when a change genuinely is not being asserted on. It
    matches everything, and says so in the envelope, which is different
    from a strict expectation that happened not to notice.
    """

    kind: str
    keys: tuple[str, ...] = ()
    delta: int | None = None

    @classmethod
    def added(cls, keys: Any) -> "Effect":
        return cls("added", tuple(sorted(str(k) for k in keys)))

    @classmethod
    def removed(cls, keys: Any) -> "Effect":
        return cls("removed", tuple(sorted(str(k) for k in keys)))

    @classmethod
    def changed(cls, keys: Any) -> "Effect":
        return cls("changed", tuple(sorted(str(k) for k in keys)))

    @classmethod
    def unchanged(cls) -> "Effect":
        return cls("unchanged")

    @classmethod
    def count_delta(cls, n: int) -> "Effect":
        return cls("count_delta", delta=int(n))

    @classmethod
    def any(cls) -> "Effect":
        return cls("any")

    def as_dict(self) -> dict[str, Any]:
        if self.kind in ("added", "removed", "changed"):
            return {self.kind: list(self.keys)}
        if self.kind == "count_delta":
            return {"count_delta": self.delta}
        return {self.kind: True}

    def matches(
        self, delta: StateDelta, *, before: StateSnapshot, after: StateSnapshot
    ) -> bool:
        """True when ``delta`` is exactly what this effect declared."""
        if self.kind == "any":
            return True

        if self.kind == "unchanged":
            # The digest, not the count. A store that lost one key and
            # gained another has the same count and is not unchanged.
            return (
                before.digest == after.digest
                and not delta.added
                and not delta.removed
                and not delta.changed
            )

        if self.kind == "added":
            return (
                delta.added == self.keys
                and not delta.removed
                and not delta.changed
            )

        if self.kind == "removed":
            return (
                delta.removed == self.keys
                and not delta.added
                and not delta.changed
            )

        if self.kind == "changed":
            return (
                delta.changed == self.keys
                and not delta.added
                and not delta.removed
            )

        if self.kind == "count_delta":
            wanted = self.delta or 0
            if delta.count_after - delta.count_before != wanted:
                return False
            # The count is necessary and not sufficient. An add-and-remove
            # nets to zero and is not "no net change"; a swap nets to +0
            # while every key in the store moved. The key sets decide.
            if delta.changed:
                return False
            if wanted >= 0:
                return len(delta.added) == wanted and not delta.removed
            return len(delta.removed) == -wanted and not delta.added

        return False


async def capture(
    source: KeySource, target: str | None = None, *, max_keys: int | None = None
) -> tuple[StateSnapshot, dict[str, str]]:
    """Snapshot ``target``, returning the snapshot and its content digests.

    The content map is returned alongside rather than carried on the
    snapshot: :class:`StateSnapshot` is a wire shape, and a per-key content
    map on a 5000-key snapshot would be the bulk of every envelope.
    """
    cap = _resolve_cap(source, max_keys)
    contents = dict(await source.enumerate_keys(target))
    ordered = sorted(str(key) for key in contents)

    sampled = len(ordered) > cap
    keys = tuple(ordered[:cap]) if sampled else tuple(ordered)
    kept = {key: str(contents[key]) for key in keys if key in contents}

    count = await _count(source, target)
    if count is None:
        count = len(ordered)

    return (
        StateSnapshot(
            service=getattr(source, "service", "unknown"),
            target=target or getattr(source, "target", "") or "",
            taken_at=utc_now(),
            count=count,
            keys=keys,
            digest=key_digest(keys),
            stats=await _stats(source, target),
            sampled=sampled,
        ),
        kept,
    )


async def snapshot(
    source: KeySource, target: str | None = None, *, max_keys: int | None = None
) -> StateSnapshot:
    """The snapshot alone, for a caller that only wants the digest."""
    taken, _ = await capture(source, target, max_keys=max_keys)
    return taken


async def verify_effect(
    connector: KeySource,
    target: str | None = None,
    *,
    expect: Effect,
    operation: Callable[[], Awaitable[Any]],
    max_keys: int | None = None,
    journal_: OperationJournal | None = None,
) -> str:
    """Snapshot, run ``operation``, snapshot again, diff, and report.

    Returns a ``verify`` envelope: ``ok`` when the observation matches
    ``expect``, and an **error** envelope carrying the same observation
    when it does not.

    ``operation`` is not wrapped in a try block. A connector in this
    library returns failure as a value, so a refused write arrives here as
    an envelope string and is diffed like any other outcome; an exception
    escaping ``operation`` is a caller-side fault and is not this
    function's to reinterpret.
    """
    started = time.monotonic()
    before, before_contents = await capture(connector, target, max_keys=max_keys)
    await operation()
    after, after_contents = await capture(connector, target, max_keys=max_keys)

    delta = StateDelta.between(before, after, before_contents, after_contents)
    matched = expect.matches(delta, before=before, after=after)
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)

    service = before.service
    label = before.target or (target or "")
    # `is not None`, never `or`: OperationJournal defines __len__, so an
    # empty journal is falsy and `journal_ or journal` would silently write
    # into the process-wide one instead.
    sink = journal if journal_ is None else journal_
    sink.record(
        operation="verify",
        service=service,
        target=label,
        outcome="ok" if matched else "error",
        elapsed_ms=elapsed_ms,
        verified=matched,
    )

    body = {
        "operation": "verify",
        "service": service,
        "target": label,
        "matched": matched,
        "expected": expect.as_dict(),
        "observed": delta.as_dict(),
        "before": before.as_dict(),
        "after": after.as_dict(),
        "elapsed_ms": elapsed_ms,
    }
    if matched:
        return json.dumps({"ok": True, **body}, default=str)

    logger.warning(
        "azdata.verify_mismatch service=%s target=%s expected=%s",
        service, label, expect.as_dict(),
    )
    return json.dumps(
        {
            "error": True,
            "detail": sanitize_detail(
                f"{service} {label}: expected {expect.as_dict()}, observed "
                f"{delta.as_dict()}"
            ),
            **body,
        },
        default=str,
    )


def _resolve_cap(source: Any, max_keys: int | None) -> int:
    if max_keys is not None:
        return max(1, int(max_keys))
    configured = getattr(source, "max_keys", None)
    if configured:
        return max(1, int(configured))
    return DEFAULT_VERIFY_MAX_KEYS


async def _count(source: Any, target: str | None) -> int | None:
    """The service's own count, or None to fall back to the key count.

    A service that cannot count cheaply reports ``-1`` and says so, rather
    than making the caller believe the sampled key count is a total.
    """
    counter = getattr(source, "count", None)
    if counter is None:
        return None
    return int(await counter(target))


async def _stats(source: Any, target: str | None) -> Mapping[str, Any]:
    """The observe-plane stats at capture time, or ``{}``.

    Never load-bearing: a snapshot whose stats could not be collected is
    still a valid snapshot, and failing the verification because a counter
    was unavailable would defeat the observe plane's whole contract.
    """
    provider = getattr(source, "stats", None)
    if provider is None:
        return {}
    try:
        result = await provider(target)
    except Exception as exc:  # noqa: BLE001 - stats never fail a verification
        logger.info("verify.stats_unavailable: %s: %s", type(exc).__name__, exc)
        return {}
    if isinstance(result, Mapping):
        return dict(result)
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError):
        return {}
    if isinstance(parsed, Mapping):
        inner = parsed.get("stats")
        return dict(inner) if isinstance(inner, Mapping) else dict(parsed)
    return {}


__all__ = [
    "Effect",
    "KeySource",
    "StateDelta",
    "StateSnapshot",
    "capture",
    "key_digest",
    "snapshot",
    "verify_effect",
]
