"""Selection — which sources this one request may read.

NEW IN THIS COMPONENT. Semantics and the reasoning behind them: `README.md`,
"Selection".

A frozen value built from one request header and thrown away when the request
ends. There is no server-side selection store, so two tabs differ because each
sends a different header, and this behaves identically on one replica and on
ten.

**It is not an access control.** The client declares it, so a client can
declare anything; the control that stops a request reaching data is the
registry allowlist in `registry.py`.

``X-Inventory-Selection`` takes ``all``, ``none``, or a comma-separated list of
source ids. An absent header is ``all``; an empty value is ``none``. An unknown
id and a repeated id are both refused rather than dropped — either means the
client has lost track of its own selection, and silently repairing it leaves a
switch that does nothing.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

#: Read from the request, never written to a response.
SELECTION_HEADER = "X-Inventory-Selection"

ALL = "all"
NONE = "none"

#: More ids than any plausible registry, and a hard ceiling on the work one
#: header can cause before it is even parsed.
MAX_SELECTION_IDS = 64
MAX_SELECTION_CHARS = 4096

SelectionMode = Literal["all", "none", "explicit"]

#: What the selection currently scopes. Said by the server so the client
#: cannot overstate it. Disabling a source narrows this inventory; it does
#: not retarget the replay scanner, the detection rules or the agent tools.
SELECTION_SCOPE = (
    "Selection scopes this Data sources view only: metadata and preview reads "
    "for disabled sources are refused for this browser session. It does not "
    "change the replay scanner, the detection rules, the evidence queries or "
    "the agent's tools."
)


class InvalidSelection(Exception):
    """The header is not one this server accepts. The reason never leaves here."""


@dataclass(frozen=True, slots=True)
class Selection:
    """One request's scope. Immutable by construction."""

    mode: SelectionMode
    ids: frozenset[str]

    def enabled(self, source_id: str) -> bool:
        return source_id in self.ids

    def enabled_ids(self, order: Collection[str]) -> tuple[str, ...]:
        """Enabled ids in registry order, so the wire payload is stable."""
        return tuple(source_id for source_id in order if source_id in self.ids)


def parse_selection(raw: str | None, *, allowed: Collection[str]) -> Selection:
    """Build one request's selection. Raises :class:`InvalidSelection`.

    Args:
        raw: The header value, or None when the client sent none.
        allowed: Every source id the registry declares.
    """
    every = frozenset(allowed)
    if raw is None:
        return Selection(mode="all", ids=every)
    text = raw.strip()
    if len(text) > MAX_SELECTION_CHARS:
        raise InvalidSelection("selection length")
    lowered = text.casefold()
    if lowered == ALL:
        return Selection(mode="all", ids=every)
    if lowered in (NONE, ""):
        # An empty value is "none", not "not chosen". The default lives on
        # the absent header alone.
        return Selection(mode="none", ids=frozenset())

    parts = [item.strip() for item in text.split(",")]
    if any(not item for item in parts):
        raise InvalidSelection("empty id in selection")
    if len(parts) > MAX_SELECTION_IDS:
        raise InvalidSelection("too many ids")
    if len(set(parts)) != len(parts):
        # Refused, not deduplicated. A repeated id is a client that has lost
        # track of its own selection, and quietly accepting it means the next
        # bug of that shape is invisible too.
        raise InvalidSelection("duplicate id in selection")
    unknown = [item for item in parts if item not in every]
    if unknown:
        # Named neither in the response nor in a log: the client already
        # knows what it sent, and echoing it makes this a reflection surface.
        raise InvalidSelection("unknown id in selection")
    chosen = frozenset(parts)
    if chosen == every:
        return Selection(mode="all", ids=every)
    return Selection(mode="explicit", ids=chosen)


__all__ = [
    "ALL",
    "MAX_SELECTION_CHARS",
    "MAX_SELECTION_IDS",
    "NONE",
    "SELECTION_HEADER",
    "SELECTION_SCOPE",
    "InvalidSelection",
    "Selection",
    "SelectionMode",
    "parse_selection",
]
