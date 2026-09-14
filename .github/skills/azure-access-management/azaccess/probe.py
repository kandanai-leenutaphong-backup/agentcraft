"""The one place this package touches a data plane, and what it refuses to return.

WHY A PROBE EXISTS AT ALL
-------------------------
"The assignment is present" and "the access works" are different claims, and
the gap between them is where the expensive incidents live: an assignment that
landed at the wrong scope, a service in key-only auth mode that refuses every
token regardless of RBAC, a firewall that drops the request before authorisation
is ever evaluated. Only a real call distinguishes them.

WHAT IT WILL NOT DO
-------------------
It returns *whether* the call was permitted and the status code. It never
returns, logs, or stores a response body, a header, a token, or any application
data — so a probe cannot become a data-exfiltration path with a nicer name. The
action must be named explicitly by the caller, and the URL must sit inside the
authority policy's scope allowlist, so a probe cannot be pointed at an arbitrary
endpoint.

READS ONLY
----------
Methods are restricted to ``GET`` and ``HEAD``. Proving write access by writing
is somebody else's decision to take deliberately, not a side effect of
verifying a grant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from azaccess.authorization import AuthorityPolicy
from azaccess.errors import AuthorizationRefused
from azaccess.transport import Transport

SAFE_METHODS: tuple[str, ...] = ("GET", "HEAD")


@dataclass(frozen=True)
class ProbeResult:
    """Permitted or not, and the status that said so. No payload, ever."""

    action: str
    url: str
    status: int
    allowed: bool
    category: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "url": self.url,
            "status": self.status,
            "allowed": self.allowed,
            "category": self.category,
        }


def _category(status: int) -> str:
    if status == 401:
        return "authentication"
    if status == 403:
        return "authorization"
    if status == 404:
        return "not-found-or-hidden"
    if status in (409, 429):
        return "service"
    if 200 <= status < 300:
        return "allowed"
    if status >= 500:
        return "service"
    return "other"


class AccessProbe:
    """A narrow, explicit, read-only reachability check."""

    def __init__(self, transport: Transport, *, policy: AuthorityPolicy) -> None:
        self._transport = transport
        self._policy = policy

    def probe(self, *, action: str, url: str, scope: str,
              method: str = "GET") -> ProbeResult:
        """Make one read and report only the outcome.

        ``action`` is the caller's own description of what is being tested, and
        is required: an unlabelled probe in an audit log is indistinguishable
        from an unexplained request.
        """
        if not action.strip():
            raise AuthorizationRefused("a probe must name the action it is testing")
        if method.upper() not in SAFE_METHODS:
            raise AuthorizationRefused(
                f"{method} is not a probe method; probes are read-only"
            )
        if not self._policy.scope_in_bounds(scope):
            raise AuthorizationRefused(
                f"probe target {scope} is outside the runtime scope allowlist"
            )
        response = self._transport.request(method.upper(), url)
        # The body is deliberately not read, not returned and not logged.
        return ProbeResult(
            action=action.strip(),
            url=url.split("?")[0],
            status=response.status,
            allowed=response.ok,
            category=_category(response.status),
        )


__all__ = ["AccessProbe", "ProbeResult", "SAFE_METHODS"]
