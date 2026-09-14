"""PrincipalGuard — the second lock, behind the one an ``az`` call can undo.

WHY A SECOND LAYER
------------------
Container Apps' built-in authentication is configured imperatively. One
``az containerapp auth update --enabled false`` — a mistake, a rollback, a
half-finished script — silently removes the only thing between an anonymous
request and the names of every resource in a subscription. The edge is the
first lock; this is the second, and it lives in the artefact rather than in
platform configuration, so reverting the platform does not revert it.

This is a component-owned copy of the pattern, never an import from a
sibling component: a sibling-private edge is forbidden by the component
contract, and a shared guard would make two deployments share one lock.

It runs **before routing**, so an unknown path answers 401 to an anonymous
caller rather than 404. A 404 is information: it tells an unauthenticated
prober which paths exist.

THE DEVELOPMENT BYPASS CANNOT REACH AZURE
-----------------------------------------
``RESOURCE_EXPLORER_DEV_PRINCIPAL=1`` skips the header check. It is ignored
whenever ``CONTAINER_APP_NAME`` is set, which the Container Apps runtime
always sets, so the bypass cannot exist in Azure regardless of how the app
is configured. That is a property of the code, which is why
``tests/test_security.py`` asserts it directly rather than trusting a
deployment script.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable

#: Injected by the Container Apps authentication edge, which also strips any
#: inbound copy a client tried to forge.
PRINCIPAL_HEADERS: tuple[bytes, ...] = (
    b"x-ms-client-principal",
    b"x-ms-client-principal-id",
)

#: Liveness and readiness answer anonymously. Neither carries a resource,
#: subscription or tenant identifier, so neither leaks by answering.
ANONYMOUS_PATHS: frozenset[str] = frozenset({"/health/live", "/health/ready"})

_UNAUTHORIZED_HEADERS = [
    (b"cache-control", b"no-store, private"),
    (b"vary", b"Cookie"),
    (b"content-length", b"0"),
]


class PrincipalGuard:
    """Pure ASGI middleware. Denies before anything else looks at the path."""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        dev_principal: bool = False,
        anonymous_paths: Iterable[str] = ANONYMOUS_PATHS,
    ) -> None:
        self.app = app
        self._dev_principal = dev_principal
        self._anonymous = frozenset(anonymous_paths)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if self._permitted(scope):
            await self.app(scope, receive, send)
            return
        await self._unauthorized(send)

    def _permitted(self, scope: dict[str, Any]) -> bool:
        if scope.get("path", "") in self._anonymous:
            return True
        if self._dev_principal:
            return True
        headers = scope.get("headers") or []
        return any(
            name.lower() in PRINCIPAL_HEADERS and value for name, value in headers
        )

    @staticmethod
    async def _unauthorized(send: Any) -> None:
        """401 with a zero-length body. No hint, no path, no identifier."""
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": list(_UNAUTHORIZED_HEADERS),
            }
        )
        await send({"type": "http.response.body", "body": b""})


__all__ = ["ANONYMOUS_PATHS", "PRINCIPAL_HEADERS", "PrincipalGuard"]
