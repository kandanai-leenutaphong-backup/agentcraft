"""What every plane adapter has in common, and the paging every list needs.

PAGING IS NOT OPTIONAL
----------------------
An ARM list answers a page and a ``nextLink``. Code that reads ``value`` and
stops is correct in every small test estate and wrong in every real one: it
reports an assignment as absent because it was on page two, then creates a
duplicate. So paging lives here, is used by every adapter, and is exercised
by a two-page fixture in the selftest.

MALFORMED IS A FAILURE, NOT AN EMPTY LIST
-----------------------------------------
``{"value": null}``, a truncated body, an HTML error page from a proxy — each
would read as "no assignments" to a naive parser and produce exactly the wrong
action. Anything that is not a list of objects is a transport failure.

A CONTINUATION IS UNTRUSTED INPUT
---------------------------------
``nextLink`` is a URL chosen by whoever answered the first page. Following it
blindly, with a transport that attaches ``Authorization`` unconditionally, sent
a live ARM token to any host a hostile or proxy-injected body named — audited
and reproduced. So a continuation must be https, carry no userinfo and no
fragment, and be **same-origin** with the request that produced it; the page
and item counts are bounded; and the transport re-checks the host anyway.

LONG-RUNNING CREATES
--------------------
Two of the five planes answer ``202 Accepted`` with no body for a create that
has not finished. Calling ``created_id`` on that body raised, no ownership was
recorded, and the assignment that later landed could never be revoked by this
run. :func:`resolve_long_running_create` polls the documented Azure
async-operation protocol to a bound, then reads the target back — and when it
still cannot conclude, it raises :class:`~azaccess.errors.OperationPending`
carrying the target id, so cleanup is possible and the outcome is never
silently "absent".
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from azaccess.endpoints import origin_of, require_same_origin
from azaccess.errors import OperationPending, TransportError
from azaccess.model import AccessDeclaration, AssignmentState, OwnershipRecord
from azaccess.transport import Response, Transport, sanitize_detail

#: Hard stop so a server that returns a self-referential ``nextLink`` fails
#: loudly instead of paging forever.
MAX_PAGES = 50

#: Hard stop on total items, so a server cannot make this process page a
#: bounded number of times into an unbounded amount of memory.
MAX_ITEMS = 20_000

#: Poll budget for an accepted long-running create.
MAX_LRO_POLLS = 30

#: Wall-clock bound on the same wait, so 30 polls behind a server asking for a
#: long Retry-After cannot become an unbounded block.
MAX_LRO_WAIT_SECS = 120.0

#: The pace a server may ask for is clamped into this range.
MIN_RETRY_AFTER_SECS = 1.0
MAX_RETRY_AFTER_SECS = 30.0

#: ARM provisioning states that are not an answer yet. A 201 carrying one of
#: these is an accepted create, not a finished one.
NON_TERMINAL_STATES: frozenset[str] = frozenset(
    {"creating", "accepted", "running", "updating", "inprogress",
     "in progress", "pending", "provisioning", "deleting"}
)

FAILED_STATES: frozenset[str] = frozenset({"failed", "canceled", "cancelled"})


class Provider(Protocol):
    """The plane adapter surface the engine depends on."""

    plane: str
    #: Operation name -> support status, used to build the support matrix.
    operations: Mapping[str, str]

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:  # pragma: no cover
        ...

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:  # pragma: no cover
        ...

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:  # pragma: no cover
        ...

    def delete(self, assignment_id: str) -> None:  # pragma: no cover
        ...


#: What the engine actually calls. Checked eagerly at registration so a
#: half-implemented adapter fails with a sentence naming the missing method,
#: not with an ``AttributeError`` from inside a plan.
PROVIDER_METHODS: tuple[str, ...] = ("list_for", "matches", "create", "delete")


def require_provider(candidate: Any, plane: str = "") -> Any:
    """Return ``candidate`` if it implements :class:`Provider`, else refuse."""
    missing = [m for m in PROVIDER_METHODS if not callable(getattr(candidate, m, None))]
    name = getattr(candidate, "plane", "") or plane or type(candidate).__name__
    if missing:
        raise TransportError(
            f"adapter for plane '{name}' does not implement the Provider "
            f"protocol: missing {missing}. Register an adapter that does, or "
            f"drive this plane through its own documented interface"
        )
    return candidate


def require_ok(response: Response, what: str, *, allowed: Sequence[int] = ()) -> dict[str, Any]:
    """The body of a successful response, or an error naming the status."""
    if response.ok or response.status in allowed:
        return response.json_body()
    detail = sanitize_detail(str(response.body), limit=300)
    raise TransportError(f"{what} answered HTTP {response.status}: {detail}")


def page_values(transport: Transport, url: str, what: str) -> list[dict[str, Any]]:
    """Every item across every page, following ``nextLink`` on one origin only."""
    expected_origin = origin_of(url)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    next_url: str | None = url
    pages = 0
    while next_url:
        if next_url in seen:
            raise TransportError(f"{what} returned a self-referential nextLink")
        seen.add(next_url)
        pages += 1
        if pages > MAX_PAGES:
            raise TransportError(f"{what} exceeded {MAX_PAGES} pages")
        body = require_ok(transport.request("GET", next_url), what)
        value = body.get("value")
        if value is None or not isinstance(value, list):
            raise TransportError(
                f"{what} returned no 'value' array; refusing to read a malformed "
                f"response as 'no assignments'"
            )
        for item in value:
            if not isinstance(item, Mapping):
                raise TransportError(f"{what} returned a non-object list entry")
            items.append(dict(item))
        if len(items) > MAX_ITEMS:
            raise TransportError(
                f"{what} returned more than {MAX_ITEMS} items; refusing to keep "
                f"reading an unbounded list"
            )
        link = body.get("nextLink") or body.get("@odata.nextLink")
        if not link:
            break
        # The server chose this URL. It gets to choose the path, never the host.
        next_url = require_same_origin(
            str(link), expected_origin, what=f"{what}: nextLink"
        )
    return items


def resolve_long_running_create(
    transport: Transport,
    response: Response,
    *,
    target_id: str,
    target_url: str,
    what: str,
    max_polls: int = MAX_LRO_POLLS,
    sleeper: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    max_wait_secs: float = MAX_LRO_WAIT_SECS,
) -> dict[str, Any]:
    """The created resource's body, for a create that may be long-running.

    Handles, from the Azure "Asynchronous operations" contract:

    * ``200``/``201`` with a **terminal** body — returned as-is;
    * ``200``/``201`` with an empty body, or one whose ``provisioningState`` is
      still non-terminal — the target is read back, and a read-back that is
      itself non-terminal is pending, not success;
    * ``202 Accepted`` — ``Azure-AsyncOperation`` is polled (falling back to
      ``Location``) until it reports ``Succeeded``, then the target is read
      back; a reported ``Failed``/``Canceled`` raises with the reason.

    Never returns a guess. If polling runs out, if the wait budget is spent, or
    if any response on the way is unreadable, :class:`OperationPending` is
    raised carrying ``target_id`` — which is the id this run PUT, so an
    operator can look for it or delete it. Claiming absence there is how an
    orphan is created.

    Waiting is bounded twice, by ``max_polls`` and by ``max_wait_secs``, and is
    real: ``sleeper`` defaults to :func:`time.sleep`, so an un-injected caller
    paces its polls instead of spinning through all of them. Each pause honours
    the server's ``Retry-After`` clamped to
    ``[MIN_RETRY_AFTER_SECS, MAX_RETRY_AFTER_SECS]``; tests inject a fake
    ``sleeper``/``clock`` and take no wall-clock time at all.

    ``target_id`` is the id of a resource this run named with a freshly minted
    random name. It is a *cleanup coordinate*, not evidence of ownership; the
    caller records ownership only from a read-back that actually returns it.
    """
    origin = origin_of(target_url)
    sleep = time.sleep if sleeper is None else sleeper
    now = time.monotonic if clock is None else clock
    if response.status in (200, 201):
        body = _body_or_pending(response, target_id, what)
        state = _provisioning_state(body)
        if state in FAILED_STATES:
            raise TransportError(f"{what} reported '{state}' on the create response")
        # A 201 whose body says Creating is not a finished create. Returning it
        # would record ownership of something that may still fail.
        if body.get("id") and state not in NON_TERMINAL_STATES:
            return body
        return _read_back_target(transport, target_url, target_id, what)
    if response.status != 202:
        raise TransportError(
            f"{what} answered HTTP {response.status}: "
            f"{sanitize_detail(str(response.body), limit=300)}"
        )
    poll_url = response.header("Azure-AsyncOperation") or response.header("Location")
    if poll_url:
        try:
            poll_url = require_same_origin(
                poll_url, origin, what=f"{what}: async-operation location"
            )
        except Exception as exc:
            raise OperationPending(
                f"{what} was accepted (202) and pointed the poll at another "
                f"origin: {exc}",
                target_id=target_id,
                status=202,
            ) from None
    attempts = 0
    started = now()
    wait_secs = retry_after_secs(response)
    while poll_url and attempts < max_polls:
        if now() - started + wait_secs > max_wait_secs:
            break
        attempts += 1
        sleep(wait_secs)
        try:
            poll = transport.request("GET", poll_url)
        except TransportError as exc:
            raise OperationPending(
                f"{what} was accepted (202) and the async operation could not be "
                f"read: {sanitize_detail(str(exc), limit=160)}",
                target_id=target_id, status=202,
            ) from None
        if not poll.ok:
            raise OperationPending(
                f"{what} was accepted (202) and polling answered HTTP "
                f"{poll.status}",
                target_id=target_id, status=poll.status,
            )
        # A malformed poll body must not escape as a bare transport error: the
        # create was accepted, so the target id has to survive the failure.
        body = _body_or_pending(poll, target_id, what, accepted=True)
        state = str(body.get("status") or _provisioning_state(body) or "").lower()
        if state in ("succeeded",):
            return _read_back_target(transport, target_url, target_id, what)
        if state in FAILED_STATES:
            raise TransportError(
                f"{what} failed asynchronously ({state}): "
                f"{sanitize_detail(str(body.get('error') or ''), limit=200)}"
            )
        if body.get("id") and not state:
            # Location-style polling: a resource body means it is there now.
            return body
        wait_secs = retry_after_secs(poll)
    raise OperationPending(
        f"{what} was accepted (202) and did not reach a terminal state within "
        f"{attempts} polls and {max_wait_secs:.0f}s; the assignment may or may "
        f"not exist",
        target_id=target_id,
        status=202,
    )


def retry_after_secs(response: Response, *, default: float = 1.0) -> float:
    """The server's ``Retry-After``, clamped to a sane range.

    A hostile or broken server must not be able to set the pace: a missing,
    non-numeric or negative value falls back to ``default``, and every value is
    clamped, so no poll loop sleeps for a day or spins at zero.
    """
    raw = response.header("Retry-After").strip()
    try:
        value = float(raw)
    except ValueError:
        # An HTTP-date is legal and not worth parsing here; pace conservatively.
        value = default if not raw else MAX_RETRY_AFTER_SECS
    if value != value or value <= 0:  # NaN or non-positive
        value = default
    return min(max(value, MIN_RETRY_AFTER_SECS), MAX_RETRY_AFTER_SECS)


def _provisioning_state(body: Mapping[str, Any]) -> str:
    properties = body.get("properties")
    if isinstance(properties, Mapping):
        return str(properties.get("provisioningState") or "").lower()
    return ""


def _body_or_pending(response: Response, target_id: str, what: str, *,
                     accepted: bool = False) -> dict[str, Any]:
    """``json_body()`` that cannot lose the cleanup coordinate."""
    try:
        return response.json_body()
    except TransportError as exc:
        raise OperationPending(
            f"{what} answered HTTP {response.status} with a body that is not a "
            f"JSON object ({sanitize_detail(str(exc), limit=120)}); the create "
            f"may have landed",
            target_id=target_id,
            status=202 if accepted else response.status,
        ) from None


def _read_back_target(transport: Transport, target_url: str, target_id: str,
                      what: str) -> dict[str, Any]:
    try:
        response = transport.request("GET", target_url)
    except TransportError as exc:
        raise OperationPending(
            f"{what}: the create was accepted and the read-back failed: "
            f"{sanitize_detail(str(exc), limit=160)}",
            target_id=target_id, status=202,
        ) from None
    if response.status == 404:
        raise OperationPending(
            f"{what}: the create was accepted and the target is not readable "
            f"yet; it may still be landing",
            target_id=target_id, status=404,
        )
    if not response.ok:
        raise OperationPending(
            f"{what}: read-back answered HTTP {response.status}",
            target_id=target_id, status=response.status,
        )
    body = response.json_body()
    if not str(body.get("id") or "").strip():
        raise OperationPending(
            f"{what}: read-back returned no 'id', so ownership cannot be "
            f"recorded from it",
            target_id=target_id, status=response.status,
        )
    state = _provisioning_state(body)
    if state in FAILED_STATES:
        raise TransportError(f"{what}: the target reports '{state}'")
    if state in NON_TERMINAL_STATES:
        raise OperationPending(
            f"{what}: the target is readable but reports '{state}', so the "
            f"create has not finished",
            target_id=target_id, status=response.status,
        )
    return body


def created_id(body: Mapping[str, Any], what: str) -> str:
    """The id the service returned, or a refusal.

    Ownership is recorded from this value and from nowhere else. A create that
    does not tell us what it created leaves nothing this run may later delete,
    and saying so is safer than reconstructing a plausible id.
    """
    value = str(body.get("id") or "").strip()
    if not value:
        raise TransportError(
            f"{what} returned no 'id'; ownership cannot be recorded, so this "
            f"assignment will not be revoked by this run"
        )
    return value


def unique_ids(states: Iterable[AssignmentState]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(s.assignment_id for s in states if s.assignment_id))


__all__ = ["FAILED_STATES", "MAX_ITEMS", "MAX_LRO_POLLS", "MAX_LRO_WAIT_SECS",
           "MAX_PAGES", "MAX_RETRY_AFTER_SECS", "MIN_RETRY_AFTER_SECS",
           "NON_TERMINAL_STATES", "PROVIDER_METHODS", "Provider", "created_id",
           "page_values", "require_ok", "require_provider",
           "resolve_long_running_create", "retry_after_secs", "unique_ids"]
