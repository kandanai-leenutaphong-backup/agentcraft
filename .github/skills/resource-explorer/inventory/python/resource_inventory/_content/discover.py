"""Discover plane — enumerate what exists, one bounded answer per level.

WHY THIS EXISTS
---------------
The read, write, deploy, observe and verify planes all assume the caller
already knows the coordinates. Something has to produce them. A tree that
lazily expands one level at a time needs an enumeration call that:

* never raises, because a browsable tree renders a failed branch rather
  than losing the whole view;
* distinguishes *why* a branch is dark — a role grant fixes ``forbidden``
  and does nothing at all for ``unreachable``;
* is bounded in items and in wall-clock, because a subscription-sized
  listing behind a private endpoint is otherwise an unbounded stall;
* is deterministic, so two reads of an unchanged estate differ only in
  ``collected_at``.

Unlike the other planes, discovery returns a dataclass rather than a JSON
string. The consumer is a composing tree that must branch on status before
rendering, and re-parsing a string per node is pure cost. ``detail`` still
goes through the shared :func:`sanitize_detail`, so the redaction rule is
the same one every envelope uses.

PUBLIC SURFACE
--------------
``DiscoveryStatus`` / ``DISCOVERY_STATUSES`` — the six outcomes.
``DiscoveryScope`` / ``DiscoveryBounds``     — where to look, how much.
``DiscoveryNode`` / ``DiscoveryResult``      — what came back.
``Discoverer``                               — the protocol every service implements.
``DiscovererRegistry``                       — service lookup.
``bounded_discovery``                        — the wrapper that enforces the contract.
``classify_discovery_failure``               — the single degradation table.
``DiscoveryAbsent``                          — "the coordinate does not exist".

ADAPTED FOR THIS REPOSITORY
---------------------------
Upstream also exported ``build_discovery_registry``, which imports five
service discoverers this repository did not adopt. It is omitted rather than
stubbed: a factory that cannot build anything is worse than an absent one.
See ``PROVENANCE.md``.

DEPENDENCIES
------------
Standard library, plus ``azure.core.exceptions`` when installed — loaded
through ``optional.load`` so the mapper is testable with no SDK present.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, runtime_checkable

from .envelope import sanitize_detail
from .optional import MissingDependency, load

DiscoveryStatus = Literal[
    "ok", "empty", "forbidden", "unreachable", "unconfigured", "unavailable"
]

#: Every value ``DiscoveryResult.status`` can take. A consumer validating a
#: wire payload needs the set, not the type alias.
DISCOVERY_STATUSES: tuple[str, ...] = (
    "ok",
    "empty",
    "forbidden",
    "unreachable",
    "unconfigured",
    "unavailable",
)

# Attribute values are rendered in a browser. Anything longer is a payload,
# not a label, and a long one per node multiplies across a wide listing.
_ATTRIBUTE_VALUE_CAP = 500


class DiscoveryAbsent(Exception):
    """The coordinate answered, and there is no such thing there.

    Distinct from a raised 404 only in that the message is the one the
    operator should read; both map to ``unavailable``.
    """


class DiscoveryUnreachable(Exception):
    """The service answered, and the answer was "not from where you are".

    Needed because the wire status is not always the operator's diagnosis.
    Azure Storage refuses a request blocked by a network rule with HTTP 403
    ``AuthorizationFailure`` — the same status code it uses for a missing
    role — and classifying that as ``forbidden`` sends the operator to grant
    a role that will not help. A caller that can tell the two apart raises
    this instead, and the message it carries is the one worth reading.
    """


@dataclass(frozen=True, slots=True)
class DiscoveryScope:
    """Where to enumerate. Every field defaults to unset, never to a guess."""

    subscription_id: str = ""
    resource_group: str = ""
    endpoint: str = ""
    account_name: str = ""
    path: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiscoveryBounds:
    """How much work one expansion may cost.

    Clamped rather than validated: a caller that computed ``0`` from a
    query string should get one item, not an exception out of a plane
    whose whole contract is that failure is a value.
    """

    max_items: int = 500
    timeout_secs: float = 15.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_items", max(1, int(self.max_items)))
        timeout = float(self.timeout_secs)
        object.__setattr__(self, "timeout_secs", timeout if timeout > 0 else 0.001)


@dataclass(frozen=True, slots=True)
class DiscoveryNode:
    """One child of an expanded node.

    ``path`` is exactly the ``DiscoveryScope.path`` that expands this node.
    The consumer never composes coordinates itself, so a service is free to
    change how its levels are addressed without breaking the tree.
    """

    kind: str
    name: str
    path: tuple[str, ...]
    has_children: bool
    attributes: Mapping[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """One expansion's outcome. Never an exception, always a status."""

    service: str
    level: str
    scope: DiscoveryScope
    status: DiscoveryStatus
    nodes: tuple[DiscoveryNode, ...] = ()
    truncated: bool = False
    detail: str = ""
    collected_at: str = ""


@runtime_checkable
class Discoverer(Protocol):
    """What every service's discoverer answers to."""

    service: str
    levels: tuple[str, ...]

    def child_level(self, level: str) -> str | None:
        """The level that expands this level's children, or None for a leaf."""

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate one level. Never raises."""


def collected_now() -> str:
    """UTC ISO-8601, second resolution, ``Z``. One format, everywhere."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_attributes(
    raw: Mapping[str, Any] | None,
) -> dict[str, str | int | bool | None]:
    """Coerce SDK values to renderable scalars, capped and URL-stripped.

    Enforced here rather than at each call site: an SDK model can carry a
    full endpoint in any string field, and a value that reaches a browser
    unstripped publishes the deployment topology.
    """
    clean: dict[str, str | int | bool | None] = {}
    for key, value in (raw or {}).items():
        name = str(key)
        if value is None or isinstance(value, bool):
            clean[name] = value
        elif isinstance(value, int):
            clean[name] = value
        elif isinstance(value, float):
            clean[name] = str(value)
        else:
            clean[name] = sanitize_detail(str(value))[:_ATTRIBUTE_VALUE_CAP]
    return clean


def model_field(model: Any, name: str) -> Any:
    """Read ``name`` from an SDK model, a mapping or a fake.

    Management models are ``Mapping`` subclasses whose nested blocks keep
    camelCase keys, while the same model exposes snake_case attributes and
    a test double is usually neither. One accessor covers all three so a
    discoverer never carries a branch per SDK pin.
    """
    if model is None:
        return None
    if isinstance(model, Mapping):
        if name in model:
            return model[name]
        head, *rest = name.split("_")
        camel = head + "".join(part.title() for part in rest)
        return model.get(camel)
    return getattr(model, name, None)


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def _azure_core_exceptions() -> Any | None:
    """``azure.core.exceptions`` when present, else None. Never raises."""
    try:
        return load("azure.core.exceptions", dist="azure-core")
    except MissingDependency:
        return None


def classify_discovery_failure(exc: BaseException) -> tuple[DiscoveryStatus, str]:
    """The degradation table, in one place.

    | Observed                                   | status        |
    | ------------------------------------------ | ------------- |
    | ``MissingDependency``                      | unavailable   |
    | ``DiscoveryAbsent``                        | unavailable   |
    | ``DiscoveryUnreachable``                   | unreachable   |
    | 401/403, ``ClientAuthenticationError``     | forbidden     |
    | ``ServiceRequestError``, ``OSError``, DNS  | unreachable   |
    | 404, 429, 5xx, anything else               | unavailable   |
    """
    if isinstance(exc, MissingDependency):
        return "unavailable", str(exc)
    if isinstance(exc, DiscoveryAbsent):
        return "unavailable", str(exc)
    if isinstance(exc, DiscoveryUnreachable):
        return "unreachable", str(exc)

    detail = f"{type(exc).__name__}: {exc}"
    code = _status_code(exc)
    if code in (401, 403):
        return "forbidden", detail

    names = {base.__name__ for base in type(exc).__mro__}
    core = _azure_core_exceptions()
    if core is not None:
        auth = getattr(core, "ClientAuthenticationError", None)
        if isinstance(auth, type) and isinstance(exc, auth):
            return "forbidden", detail
        for attr in ("ServiceRequestError", "ServiceRequestTimeoutError"):
            candidate = getattr(core, attr, None)
            if isinstance(candidate, type) and isinstance(exc, candidate):
                return "unreachable", detail
    if "ClientAuthenticationError" in names:
        return "forbidden", detail
    if names & {"ServiceRequestError", "ServiceRequestTimeoutError", "gaierror"}:
        return "unreachable", detail
    # OSError last: a socket-level failure is unreachable, but an SDK
    # exception that happens to subclass it is classified by name above.
    if isinstance(exc, OSError) and code is None:
        return "unreachable", detail
    return "unavailable", detail


def discovery_failure(
    *,
    service: str,
    level: str,
    scope: DiscoveryScope,
    status: DiscoveryStatus,
    detail: str,
) -> DiscoveryResult:
    """A result carrying only a status. The shape of every dark branch."""
    return DiscoveryResult(
        service=service,
        level=level,
        scope=scope,
        status=status,
        nodes=(),
        truncated=False,
        detail=sanitize_detail(detail),
        collected_at=collected_now(),
    )


async def bounded_discovery(
    *,
    service: str,
    level: str,
    scope: DiscoveryScope,
    bounds: DiscoveryBounds,
    collect: Callable[[], Iterable[DiscoveryNode]],
) -> DiscoveryResult:
    """Run one blocking enumeration under the plane's contract.

    ``collect`` is synchronous and may block: every SDK used here is, and
    draining a pager on the event loop stalls every other expansion. It is
    expected to stop after ``max_items + 1`` items; the extra one is what
    proves truncation without a second call.

    The thread returns its exception as a value rather than raising, so a
    ``TimeoutError`` reaching ``wait_for`` unambiguously means the budget
    was exceeded and not that a socket timed out inside the SDK.
    """

    def _run() -> tuple[list[DiscoveryNode] | None, BaseException | None]:
        try:
            return list(collect()), None
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a status
            return None, exc

    try:
        nodes, error = await asyncio.wait_for(
            asyncio.to_thread(_run), bounds.timeout_secs
        )
    except (asyncio.TimeoutError, TimeoutError):
        return discovery_failure(
            service=service,
            level=level,
            scope=scope,
            status="unreachable",
            detail=f"discovery exceeded {bounds.timeout_secs}s",
        )
    except Exception as exc:  # noqa: BLE001 - to_thread itself can fail
        status, detail = classify_discovery_failure(exc)
        return discovery_failure(
            service=service, level=level, scope=scope, status=status, detail=detail
        )

    if error is not None:
        status, detail = classify_discovery_failure(error)
        return discovery_failure(
            service=service, level=level, scope=scope, status=status, detail=detail
        )

    ordered = sorted(nodes or (), key=lambda node: (node.kind, node.name))
    truncated = len(ordered) > bounds.max_items
    if truncated:
        ordered = ordered[: bounds.max_items]
    return DiscoveryResult(
        service=service,
        level=level,
        scope=scope,
        status="ok" if ordered else "empty",
        nodes=tuple(ordered),
        truncated=truncated,
        detail="",
        collected_at=collected_now(),
    )


class DiscovererRegistry:
    """Service name -> discoverer. No module-level singleton, by contract."""

    def __init__(self) -> None:
        self._by_service: dict[str, Discoverer] = {}

    def register(self, discoverer: Discoverer) -> None:
        self._by_service[discoverer.service] = discoverer

    def get(self, service: str) -> Discoverer | None:
        return self._by_service.get(service)

    def services(self) -> tuple[str, ...]:
        """Registration order, which is the order a tree renders branches in."""
        return tuple(self._by_service)


__all__ = [
    "DISCOVERY_STATUSES",
    "Discoverer",
    "DiscovererRegistry",
    "DiscoveryAbsent",
    "DiscoveryBounds",
    "DiscoveryNode",
    "DiscoveryResult",
    "DiscoveryScope",
    "DiscoveryStatus",
    "DiscoveryUnreachable",
    "bounded_discovery",
    "classify_discovery_failure",
    "collected_now",
    "discovery_failure",
    "model_field",
    "normalize_attributes",
]
