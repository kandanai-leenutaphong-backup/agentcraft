from __future__ import annotations

from dataclasses import dataclass

from .errors import AdxConfigError, AdxPermissionError

GRANTS = frozenset({"ingest", "schema", "delete", "provision", "command"})


@dataclass(frozen=True)
class EventStorePolicy:
    """Host-established operator authority; no Azure role or authentication is granted."""

    principal: str | None = None
    grants: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if (not isinstance(self.grants, (set, frozenset, tuple, list))
                or any(not isinstance(grant, str) or grant not in GRANTS for grant in self.grants)):
            raise AdxConfigError("unknown event-store grant")
        if ((self.grants or self.principal is not None)
                and (not isinstance(self.principal, str) or not self.principal.strip() or len(self.principal) > 256)):
            raise AdxConfigError("mutation grants require a bounded host-established principal")
        object.__setattr__(self, "grants", frozenset(self.grants))

    def require(self, *grants: str) -> None:
        if not set(grants) <= self.grants:
            raise AdxPermissionError("event-store operation requires explicit grants: " + ", ".join(grants))